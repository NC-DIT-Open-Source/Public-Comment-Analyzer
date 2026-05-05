"""Lambda handler for aggregate sentiment analysis."""

import json
import os
import tempfile
from typing import Dict, Any, List
from datetime import datetime, timezone
from concurrent.futures import ThreadPoolExecutor, as_completed
import boto3
from botocore.exceptions import ClientError
from botocore.config import Config

# Shared modules are provided via Lambda Layer (/opt/python/) at runtime.
# For local testing, fall back to the sibling shared/ directory.
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'shared'))

from auth import validate_access_key, build_unauthorized_response
from file_parser import FileParser, ParsedFile
import logging
import time
import traceback

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


# Environment variables
DATA_BUCKET = os.environ.get('DATA_BUCKET')
JOBS_TABLE_NAME = os.environ.get('JOBS_TABLE')

# Constants
CLAUDE_OPUS_MODEL_ID = "us.anthropic.claude-opus-4-7"
CLAUDE_HAIKU_MODEL_ID = "us.anthropic.claude-haiku-4-5-20251001-v1:0"
CHUNK_SIZE = 150  # rows per chunk for map-reduce summarization
MAX_SUMMARY_WORKERS = 10  # parallel Haiku calls for chunk summarization


def _sanitize_for_prompt(text: str) -> str:
    """Strip characters and patterns commonly used in prompt injection."""
    sanitized = text.replace('```', '')
    sanitized = ' '.join(sanitized.split())
    return sanitized[:5000]


def _cors_origin() -> str:
    """Return the allowed CORS origin from environment.

    Fails closed (empty string) if ALLOWED_ORIGIN is unset so the browser
    rejects the response — mirrors validate_access_key, which fails closed
    when no auth secret is configured.
    """
    origin = os.environ.get('ALLOWED_ORIGIN')
    if not origin:
        logger.error("ALLOWED_ORIGIN is not set; CORS will fail closed")
        return ''
    return origin


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
    Generate aggregate sentiment analysis using Claude Opus 4.7.
    
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

        # Validate access key for API Gateway invocations (skip for async)
        if not is_async and not validate_access_key(event):
            return build_unauthorized_response(_cors_origin())
        
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
        logger.info(f"Generating aggregate analysis for job {job_id}")
        
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

        context_description = job_record.get('contextDescription', '')

        # Construct prompt for Claude Opus
        prompt = _construct_aggregate_prompt(formatted_data, job_record['analysisColumns'],
                                            context_description=context_description)
        
        # Call Bedrock with Claude Opus 4.7
        aggregate_analysis = _call_bedrock_opus(prompt)
        
        # Store analysis in DynamoDB
        _update_job_with_analysis(job_id, aggregate_analysis)
        
        logger.info(f"Aggregate analysis completed and cached for job {job_id}")
        
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
        
        logger.error("AWS service error in aggregate analyzer")
        logger.error(f"Error code: {error_code}")
        logger.error(f"Error message: {error_message}")
        logger.error(f"Job ID: {event.get('pathParameters', {}).get('jobId')}")
        
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
        
        logger.error("Aggregate analysis failed")
        logger.error(f"Error type: {error_type}")
        logger.error(f"Error message: {error_message}")
        logger.error(f"Job ID: {event.get('pathParameters', {}).get('jobId')}")
        logger.error("Stack trace:", exc_info=True)
        
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
    
    Uses a map-reduce approach for open text columns:
    - Categorized columns: exact distribution counts (computed in Python)
    - Open text columns: chunked and summarized via Haiku, then fed to Opus
    
    Args:
        parsed_file: Parsed file data
        analysis_columns: Analysis column definitions
        
    Returns:
        Formatted data string for prompt
    """
    total_rows = parsed_file.row_count
    
    # Separate categorized vs open text columns
    categorized_cols = {}
    open_text_cols = {}
    for col in analysis_columns:
        col_type = col.get('type', 'open_text')
        if col_type == 'categorized' and col.get('options'):
            categorized_cols[col['name']] = [opt['value'] for opt in col['options']]
        else:
            open_text_cols[col['name']] = col.get('instructions', '')
    
    all_col_names = [col['name'] for col in analysis_columns]
    
    # --- Categorized columns: exact distributions ---
    categorized_text = []
    for col_name, valid_options in categorized_cols.items():
        value_counts = {}
        for row in parsed_file.rows:
            value = row.get(col_name, '')
            if value:
                value_counts[value] = value_counts.get(value, 0) + 1
        
        categorized_text.append(f"\n{col_name} (Categorized):")
        for opt in valid_options:
            count = value_counts.get(opt, 0)
            percentage = (count / total_rows) * 100 if total_rows > 0 else 0
            categorized_text.append(f"  - {opt}: {count} ({percentage:.1f}%)")
        matched_count = sum(value_counts.get(opt, 0) for opt in valid_options)
        unmatched = total_rows - matched_count
        if unmatched > 0:
            categorized_text.append(f"  - (unmatched/blank): {unmatched} ({(unmatched / total_rows) * 100:.1f}%)")
    
    # --- Open text columns: map-reduce summarization ---
    logger.info(f"Starting map-reduce summarization for {len(open_text_cols)} open text column(s)")
    open_text_summaries = []
    for col_name, instructions in open_text_cols.items():
        values = [row.get(col_name, '') for row in parsed_file.rows if row.get(col_name, '').strip()]
        summary = _summarize_open_text_chunks(col_name, values, instructions)
        open_text_summaries.append(summary)
    
    # --- Sample rows for cross-column context ---
    sample_size = min(5, total_rows)
    sample_rows = parsed_file.rows[:sample_size]
    if total_rows > sample_size:
        sample_rows.extend(parsed_file.rows[-sample_size:])
    
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

Open Text Column Analysis (summarized via map-reduce):
{chr(10).join(open_text_summaries) if open_text_summaries else '  (none)'}

Sample Processed Comments (for cross-column context):
{''.join(sample_text)}"""
    
    return formatted_data


def _construct_aggregate_prompt(formatted_data: str,
                                analysis_columns: List[Dict[str, str]],
                                context_description: str = None) -> str:
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
    
    sanitized_context = _sanitize_for_prompt(context_description) if context_description else None
    preamble = "You are analyzing a dataset of public comments that have been individually processed and categorized."
    if sanitized_context:
        preamble += f"\n\n<context_description>{sanitized_context}</context_description>"

    prompt = f"""{preamble}

The following analysis columns were applied to each comment:
{chr(10).join(column_descriptions)}

Here is a summary of the processed data. Categorized columns include exact counts. Open text columns have been pre-summarized in chunks by a faster model — synthesize these chunk summaries into a cohesive analysis.

{formatted_data}

Please provide a comprehensive aggregate analysis including:

1. Categorized Column Breakdown: For each categorized column, present the exact counts and percentages from the data above. Highlight the dominant category and any notable splits.

2. Open Text Themes and Patterns: Synthesize the chunk summaries for each open text column into a unified thematic analysis. Identify the most prominent themes across all chunks, estimate their overall prevalence, and include representative quotes where available.

3. Cross-Column Insights: Describe any interesting relationships between the categorized results and the open text themes. For example, do certain themes correlate with certain categories?

4. Notable Trends or Outliers: Highlight any interesting trends, unusual patterns, or outliers in the data.

5. Quantitative Summary: Provide relevant statistics such as most common categories, distribution metrics, and any actionable takeaways.

Be specific and cite percentages where applicable. Focus on actionable insights that would be valuable for understanding the overall sentiment and themes in this dataset."""
    
    return prompt


def _call_bedrock_haiku(prompt: str) -> str:
    """
    Call AWS Bedrock with Claude Haiku model for chunk summarization.
    
    Args:
        prompt: Summarization prompt
        
    Returns:
        Summary text
    """
    max_retries = 3
    
    for attempt in range(max_retries):
        try:
            response = _get_bedrock_runtime().invoke_model(
                modelId=CLAUDE_HAIKU_MODEL_ID,
                contentType="application/json",
                accept="application/json",
                body=json.dumps({
                    "anthropic_version": "bedrock-2023-05-31",
                    "max_tokens": 1024,
                    "messages": [
                        {
                            "role": "user",
                            "content": prompt
                        }
                    ]
                })
            )
            
            response_body = json.loads(response['body'].read())
            return response_body['content'][0]['text']
        
        except Exception as e:
            if attempt < max_retries - 1:
                time.sleep(2 ** attempt)
                logger.warning(f"Haiku call failed (attempt {attempt + 1}/{max_retries}): {str(e)}")
                continue
            else:
                logger.error(f"Haiku call failed after {max_retries} attempts: {str(e)}")
                raise e


def _summarize_open_text_chunks(col_name: str, values: List[str], 
                                 col_instructions: str) -> str:
    """
    Map-reduce summarization of open text column values.
    
    Chunks the values, sends each chunk to Haiku for a mini-summary,
    then returns all chunk summaries combined for Opus to synthesize.
    
    Args:
        col_name: Column name
        values: All non-empty values for this column
        col_instructions: The original instructions for this column
        
    Returns:
        Combined chunk summaries as a formatted string
    """
    if not values:
        return f"{col_name}: No responses."
    
    # If small enough, just include all values directly (no need for map step)
    if len(values) <= CHUNK_SIZE:
        numbered = [f"  {i+1}. {v}" for i, v in enumerate(values)]
        return f"{col_name} — All {len(values)} responses:\n" + "\n".join(numbered)
    
    # Chunk the values
    chunks = []
    for i in range(0, len(values), CHUNK_SIZE):
        chunks.append(values[i:i + CHUNK_SIZE])
    
    logger.info(f"Map step: {len(values)} values in {len(chunks)} chunks for '{col_name}'")
    
    def summarize_chunk(chunk_index: int, chunk: List[str]) -> str:
        numbered = "\n".join(f"{i+1}. {v}" for i, v in enumerate(chunk))
        prompt = f"""Below are {len(chunk)} responses from a public comment dataset for the column "{col_name}".
Column description: {col_instructions}

<responses>
{numbered}
</responses>

Summarize the key themes, arguments, and patterns in these responses. For each theme you identify:
- Name the theme clearly
- Estimate how many of the {len(chunk)} responses relate to it
- Give 1-2 representative short quotes

Be concise but thorough. Focus on substance, not style."""
        
        summary = _call_bedrock_haiku(prompt)
        return f"Chunk {chunk_index + 1} ({len(chunk)} responses):\n{summary}"
    
    # Run chunk summarizations in parallel
    chunk_summaries = [None] * len(chunks)
    with ThreadPoolExecutor(max_workers=MAX_SUMMARY_WORKERS) as executor:
        futures = {
            executor.submit(summarize_chunk, i, chunk): i 
            for i, chunk in enumerate(chunks)
        }
        for future in as_completed(futures):
            idx = futures[future]
            try:
                chunk_summaries[idx] = future.result()
            except Exception as e:
                logger.warning(f"Chunk {idx} summarization failed: {e}")
                chunk_summaries[idx] = f"Chunk {idx + 1}: (summarization failed)"
    
    logger.info(f"Map step complete for '{col_name}': {sum(1 for s in chunk_summaries if s and 'failed' not in s)}/{len(chunks)} chunks succeeded")
    
    return f"{col_name} — {len(values)} total responses, summarized in {len(chunks)} chunks:\n\n" + \
           "\n\n".join(s for s in chunk_summaries if s)


def _call_bedrock_opus(prompt: str) -> str:
    """
    Call AWS Bedrock with Claude Opus 4.7 model.
    
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
                time.sleep(2 ** attempt)
                logger.warning(f"Bedrock call failed (attempt {attempt + 1}/{max_retries}): {str(e)}")
                continue
            else:
                # Final attempt failed
                logger.error(f"Bedrock call failed after {max_retries} attempts: {str(e)}")
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
