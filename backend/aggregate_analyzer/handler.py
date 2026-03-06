"""Lambda handler for aggregate sentiment analysis."""

import json
import os
import tempfile
from typing import Dict, Any, List
from datetime import datetime, timezone
import boto3
from botocore.exceptions import ClientError
from botocore.config import Config

# Import shared modules
import sys
sys.path.append('/opt/python')  # Lambda layer path
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'shared'))

try:
    from file_parser import FileParser, ParsedFile
except ImportError:
    # Fallback for local testing
    import importlib.util
    shared_path = os.path.join(os.path.dirname(__file__), '..', 'shared')
    
    spec = importlib.util.spec_from_file_location("file_parser", 
                                                   os.path.join(shared_path, "file_parser.py"))
    file_parser_module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(file_parser_module)
    FileParser = file_parser_module.FileParser
    ParsedFile = file_parser_module.ParsedFile


# Environment variables
DATA_BUCKET = os.environ.get('DATA_BUCKET')
JOBS_TABLE_NAME = os.environ.get('JOBS_TABLE')

# Constants
CLAUDE_OPUS_MODEL_ID = "us.anthropic.claude-opus-4-6-v1"


def _cors_origin() -> str:
    """Return the allowed CORS origin from environment, falling back to '*'."""
    return os.environ.get('ALLOWED_ORIGIN') or '*'


# AWS clients (initialized lazily)
_s3_client = None
_dynamodb = None
_bedrock_runtime = None


def _get_s3_client():
    """Get or create S3 client."""
    global _s3_client
    if _s3_client is None:
        _s3_client = boto3.client('s3')
    return _s3_client


def _get_dynamodb():
    """Get or create DynamoDB resource."""
    global _dynamodb
    if _dynamodb is None:
        _dynamodb = boto3.resource('dynamodb')
    return _dynamodb


def _get_bedrock_runtime():
    """Get or create Bedrock runtime client with extended timeout for Opus."""
    global _bedrock_runtime
    if _bedrock_runtime is None:
        _bedrock_runtime = boto3.client(
            'bedrock-runtime',
            config=Config(read_timeout=600, connect_timeout=10)
        )
    return _bedrock_runtime


def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Generate aggregate sentiment analysis using Claude Opus 4.6.
    
    Supports two invocation modes:
    1. Async invocation (from row_processor): Generates and caches analysis
    2. API Gateway invocation: Returns cached analysis or 'generating' status
    
    Args:
        event: Event with jobId (from path parameters)
        context: Lambda context
        
    Returns:
        Response with aggregate analysis and download URL
    """
    try:
        # Extract jobId from path parameters
        job_id = event.get('pathParameters', {}).get('jobId')
        is_async = event.get('asyncAnalysis', False)
        
        if not job_id:
            return {
                'statusCode': 400,
                'headers': {
                    'Content-Type': 'application/json',
                    'Access-Control-Allow-Origin': _cors_origin()
                },
                'body': json.dumps({
                    'error': {
                        'code': 'MISSING_JOB_ID',
                        'message': 'jobId is required'
                    }
                })
            }
        
        # Get job record from DynamoDB
        job_record = _get_job_record(job_id)
        
        if not job_record:
            return {
                'statusCode': 404,
                'headers': {
                    'Content-Type': 'application/json',
                    'Access-Control-Allow-Origin': _cors_origin()
                },
                'body': json.dumps({
                    'error': {
                        'code': 'JOB_NOT_FOUND',
                        'message': f'Job {job_id} not found'
                    }
                })
            }
        
        # Check if job is completed
        if job_record.get('status') != 'completed':
            return {
                'statusCode': 400,
                'headers': {
                    'Content-Type': 'application/json',
                    'Access-Control-Allow-Origin': _cors_origin()
                },
                'body': json.dumps({
                    'error': {
                        'code': 'JOB_NOT_COMPLETED',
                        'message': 'Job processing is not yet completed'
                    }
                })
            }
        
        # Check if aggregate analysis already exists
        if job_record.get('aggregateAnalysis'):
            # Return cached analysis
            download_url = _generate_presigned_url(job_record['outputFileKey'])
            return {
                'statusCode': 200,
                'headers': {
                    'Content-Type': 'application/json',
                    'Access-Control-Allow-Origin': _cors_origin()
                },
                'body': json.dumps({
                    'downloadUrl': download_url,
                    'aggregateAnalysis': job_record['aggregateAnalysis']
                })
            }
        
        # No cached analysis yet
        if not is_async:
            # Called from API Gateway — don't block, tell the client to retry
            download_url = _generate_presigned_url(job_record['outputFileKey'])
            return {
                'statusCode': 200,
                'headers': {
                    'Content-Type': 'application/json',
                    'Access-Control-Allow-Origin': _cors_origin()
                },
                'body': json.dumps({
                    'downloadUrl': download_url,
                    'aggregateAnalysis': None,
                    'analysisStatus': 'generating',
                    'message': 'Aggregate analysis is being generated. Please retry shortly.'
                })
            }
        
        # Async invocation — generate the analysis now
        print(f"Generating aggregate analysis for job {job_id}")
        
        # Read processed file from S3
        output_key = job_record['outputFileKey']
        file_type = _get_file_type(output_key)
        
        with tempfile.NamedTemporaryFile(delete=False, suffix=f'.{file_type}') as tmp_file:
            file_path = tmp_file.name
            _get_s3_client().download_file(DATA_BUCKET, output_key, file_path)
        
        # Parse processed file
        parser = FileParser()
        parsed_file = parser.parse(file_path, file_type)
        
        # Clean up temp file
        os.unlink(file_path)
        
        # Format data for aggregate analysis
        formatted_data = _format_data_for_analysis(parsed_file, job_record['analysisColumns'])
        
        # Construct prompt for Claude Opus
        prompt = _construct_aggregate_prompt(formatted_data, job_record['analysisColumns'])
        
        # Call Bedrock with Claude Opus 4.6
        aggregate_analysis = _call_bedrock_opus(prompt)
        
        # Store analysis in DynamoDB
        _update_job_with_analysis(job_id, aggregate_analysis)
        
        print(f"Aggregate analysis completed and cached for job {job_id}")
        
        # Generate presigned URL for download
        download_url = _generate_presigned_url(output_key)
        
        return {
            'statusCode': 200,
            'headers': {
                'Content-Type': 'application/json',
                'Access-Control-Allow-Origin': _cors_origin()
            },
            'body': json.dumps({
                'downloadUrl': download_url,
                'aggregateAnalysis': aggregate_analysis
            })
        }
        
    except ClientError as e:
        error_code = e.response['Error']['Code']
        error_message = e.response['Error']['Message']
        
        print(f"ERROR: AWS service error in aggregate analyzer")
        print(f"  Error code: {error_code}")
        print(f"  Error message: {error_message}")
        print(f"  Job ID: {event.get('pathParameters', {}).get('jobId')}")
        
        # Provide user-friendly error messages
        if error_code == 'NoSuchKey':
            user_message = 'The processed file could not be found. The job may have expired or been deleted.'
        elif error_code == 'AccessDenied':
            user_message = 'Access to the file was denied. Please contact support.'
        else:
            user_message = f'An AWS service error occurred. Please try again later.'
        
        return {
            'statusCode': 500,
            'headers': {
                'Content-Type': 'application/json',
                'Access-Control-Allow-Origin': _cors_origin()
            },
            'body': json.dumps({
                'error': {
                    'code': 'AWS_ERROR',
                    'message': user_message
                }
            })
        }
    
    except Exception as e:
        error_type = type(e).__name__
        error_message = str(e)
        
        print(f"ERROR: Aggregate analysis failed")
        print(f"  Error type: {error_type}")
        print(f"  Error message: {error_message}")
        print(f"  Job ID: {event.get('pathParameters', {}).get('jobId')}")
        
        import traceback
        print(f"  Stack trace:")
        traceback.print_exc()
        
        # Provide user-friendly error message
        if 'bedrock' in error_message.lower():
            user_message = 'AI analysis service is temporarily unavailable. Please try again in a few moments.'
        elif 'timeout' in error_message.lower():
            user_message = 'Analysis took too long to complete. Please try again.'
        else:
            user_message = 'An error occurred during aggregate analysis. Please try again or contact support if the issue persists.'
        
        return {
            'statusCode': 500,
            'headers': {
                'Content-Type': 'application/json',
                'Access-Control-Allow-Origin': _cors_origin()
            },
            'body': json.dumps({
                'error': {
                    'code': 'ANALYSIS_ERROR',
                    'message': user_message
                }
            })
        }


def _get_job_record(job_id: str) -> Dict[str, Any]:
    """
    Get job record from DynamoDB.
    
    Args:
        job_id: Job ID
        
    Returns:
        Job record dictionary or None if not found
    """
    table = _get_dynamodb().Table(JOBS_TABLE_NAME)
    
    response = table.get_item(Key={'jobId': job_id})
    
    return response.get('Item')


def _get_file_type(file_key: str) -> str:
    """
    Extract file type from S3 key.
    
    Args:
        file_key: S3 object key
        
    Returns:
        File type ('csv' or 'xlsx')
    """
    if file_key.endswith('.csv'):
        return 'csv'
    elif file_key.endswith('.xlsx'):
        return 'xlsx'
    else:
        raise ValueError(f"Unknown file type for key: {file_key}")


def _format_data_for_analysis(parsed_file: ParsedFile, 
                              analysis_columns: List[Dict[str, str]]) -> str:
    """
    Format processed data for aggregate analysis prompt.
    
    Creates a summary of the data including:
    - Total number of comments
    - Sample of processed rows
    - Distribution of analysis column values
    - Exact counts for categorized columns
    
    Args:
        parsed_file: Parsed file data
        analysis_columns: Analysis column definitions
        
    Returns:
        Formatted data string for prompt
    """
    total_rows = parsed_file.row_count
    
    # Separate categorized vs open text columns
    categorized_cols = {}
    open_text_cols = []
    for col in analysis_columns:
        col_type = col.get('type', 'open_text')
        if col_type == 'categorized' and col.get('options'):
            categorized_cols[col['name']] = [opt['value'] for opt in col['options']]
        else:
            open_text_cols.append(col['name'])
    
    all_col_names = [col['name'] for col in analysis_columns]
    
    # Calculate value distributions for all analysis columns
    distributions = {}
    for col_name in all_col_names:
        value_counts = {}
        for row in parsed_file.rows:
            value = row.get(col_name, '')
            if value:
                value_counts[value] = value_counts.get(value, 0) + 1
        distributions[col_name] = value_counts
    
    # Format categorized column distributions (exact counts)
    categorized_text = []
    for col_name, valid_options in categorized_cols.items():
        value_counts = distributions.get(col_name, {})
        categorized_text.append(f"\n{col_name} (Categorized):")
        for opt in valid_options:
            count = value_counts.get(opt, 0)
            percentage = (count / total_rows) * 100 if total_rows > 0 else 0
            categorized_text.append(f"  - {opt}: {count} ({percentage:.1f}%)")
        # Count blanks/unmatched
        matched_count = sum(value_counts.get(opt, 0) for opt in valid_options)
        unmatched = total_rows - matched_count
        if unmatched > 0:
            categorized_text.append(f"  - (unmatched/blank): {unmatched} ({(unmatched / total_rows) * 100:.1f}%)")
    
    # Format open text column distributions (top values)
    open_text_distribution = []
    for col_name in open_text_cols:
        value_counts = distributions.get(col_name, {})
        open_text_distribution.append(f"\n{col_name} (Open Text):")
        sorted_values = sorted(value_counts.items(), key=lambda x: x[1], reverse=True)
        for value, count in sorted_values[:10]:
            percentage = (count / total_rows) * 100
            open_text_distribution.append(f"  - {value}: {count} ({percentage:.1f}%)")
    
    # Get sample rows (first 5 and last 5)
    sample_size = min(5, total_rows)
    sample_rows = parsed_file.rows[:sample_size]
    if total_rows > sample_size:
        sample_rows.extend(parsed_file.rows[-sample_size:])
    
    # Format sample rows
    sample_text = []
    for i, row in enumerate(sample_rows[:10]):
        sample_text.append(f"\nSample {i+1}:")
        for col_name in all_col_names:
            value = row.get(col_name, '')
            sample_text.append(f"  {col_name}: {value}")
    
    # Combine all parts
    formatted_data = f"""Total Comments: {total_rows}

Categorized Column Results:
{''.join(categorized_text) if categorized_text else '  (none)'}

Open Text Column Distributions:
{''.join(open_text_distribution) if open_text_distribution else '  (none)'}

Sample Processed Comments:
{''.join(sample_text)}"""
    
    return formatted_data


def _construct_aggregate_prompt(formatted_data: str, 
                                analysis_columns: List[Dict[str, str]]) -> str:
    """
    Construct prompt for Claude Opus aggregate analysis.
    
    Args:
        formatted_data: Formatted data summary
        analysis_columns: Analysis column definitions
        
    Returns:
        Prompt string for Bedrock
    """
    # Get column descriptions, noting type
    column_descriptions = []
    for col in analysis_columns:
        col_type = col.get('type', 'open_text')
        if col_type == 'categorized' and col.get('options'):
            option_values = [opt['value'] for opt in col['options']]
            column_descriptions.append(
                f"- {col['name']} (Categorized — valid values: {', '.join(option_values)})"
            )
        else:
            column_descriptions.append(f"- {col['name']} (Open Text): {col['instructions']}")
    
    prompt = f"""You are analyzing a dataset of public comments that have been individually processed and categorized.

The following analysis columns were applied to each comment:
{chr(10).join(column_descriptions)}

Here is a summary of the processed data:

{formatted_data}

Please provide a comprehensive aggregate analysis including:

1. Categorized Column Breakdown: For each categorized column, present the exact counts and percentages from the data above. Highlight the dominant category and any notable splits.

2. Open Text Themes and Patterns: For open text columns, identify the most prominent themes, topics, or patterns that emerge across all comments.

3. Cross-Column Insights: Describe any interesting relationships between the categorized results and the open text themes.

4. Notable Trends or Outliers: Highlight any interesting trends, unusual patterns, or outliers in the data.

5. Quantitative Summary: Provide relevant statistics such as most common categories, distribution metrics, and any actionable takeaways.

Be specific and cite percentages where applicable. Focus on actionable insights that would be valuable for understanding the overall sentiment and themes in this dataset."""
    
    return prompt


def _call_bedrock_opus(prompt: str) -> str:
    """
    Call AWS Bedrock with Claude Opus 4.6 model.
    
    Args:
        prompt: Analysis prompt
        
    Returns:
        Aggregate analysis text
        
    Raises:
        Exception: If Bedrock call fails after retries
    """
    max_retries = 3
    
    for attempt in range(max_retries):
        try:
            response = _get_bedrock_runtime().invoke_model(
                modelId=CLAUDE_OPUS_MODEL_ID,
                contentType="application/json",
                accept="application/json",
                body=json.dumps({
                    "anthropic_version": "bedrock-2023-05-31",
                    "max_tokens": 4096,  # Increased from 2000 to allow complete analysis
                    "messages": [
                        {
                            "role": "user",
                            "content": prompt
                        }
                    ]
                })
            )
            
            # Parse response
            response_body = json.loads(response['body'].read())
            content = response_body['content'][0]['text']
            
            return content
        
        except Exception as e:
            if attempt < max_retries - 1:
                # Exponential backoff: 1s, 2s, 4s
                import time
                time.sleep(2 ** attempt)
                print(f"Bedrock call failed (attempt {attempt + 1}/{max_retries}): {str(e)}")
                continue
            else:
                # Final attempt failed
                print(f"Bedrock call failed after {max_retries} attempts: {str(e)}")
                raise e


def _update_job_with_analysis(job_id: str, aggregate_analysis: str) -> None:
    """
    Update job record in DynamoDB with aggregate analysis.
    
    Args:
        job_id: Job ID
        aggregate_analysis: Aggregate analysis text
    """
    table = _get_dynamodb().Table(JOBS_TABLE_NAME)
    
    now = datetime.now(timezone.utc).isoformat()
    
    table.update_item(
        Key={'jobId': job_id},
        UpdateExpression="SET aggregateAnalysis = :analysis, updatedAt = :updated",
        ExpressionAttributeValues={
            ':analysis': aggregate_analysis,
            ':updated': now
        }
    )


def _generate_presigned_url(s3_key: str, expiration: int = 3600) -> str:
    """
    Generate presigned URL for S3 object download.
    
    Args:
        s3_key: S3 object key
        expiration: URL expiration time in seconds (default 1 hour)
        
    Returns:
        Presigned URL string
    """
    url = _get_s3_client().generate_presigned_url(
        'get_object',
        Params={
            'Bucket': DATA_BUCKET,
            'Key': s3_key
        },
        ExpiresIn=expiration
    )
    
    return url
