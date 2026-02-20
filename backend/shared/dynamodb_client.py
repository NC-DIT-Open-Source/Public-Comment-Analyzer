"""DynamoDB data access layer for job tracking."""

import os
import time
from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import boto3
from boto3.dynamodb.conditions import Key


class JobStatus:
    """Job status constants."""
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class DynamoDBClient:
    """Data access layer for DynamoDB job tracking."""
    
    def __init__(self, table_name: Optional[str] = None):
        """
        Initialize DynamoDB client.
        
        Args:
            table_name: Name of the DynamoDB table. If None, reads from JOBS_TABLE env var.
        """
        self.table_name = table_name or os.environ.get('JOBS_TABLE')
        if not self.table_name:
            raise ValueError("Table name must be provided or set in JOBS_TABLE environment variable")
        
        self.dynamodb = boto3.resource('dynamodb')
        self.table = self.dynamodb.Table(self.table_name)
    
    def create_job(
        self,
        job_id: str,
        file_id: str,
        total_rows: int,
        analysis_columns: List[Dict[str, str]],
        input_file_key: str,
        file_type: str
    ) -> Dict[str, Any]:
        """
        Create a new job record in DynamoDB.
        
        Args:
            job_id: Unique job identifier (UUID)
            file_id: File identifier
            total_rows: Total number of rows to process
            analysis_columns: List of analysis column definitions
            input_file_key: S3 key for input file
            file_type: File type (csv or xlsx)
            
        Returns:
            Created job record
        """
        now = datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')
        ttl = int((datetime.now(timezone.utc) + timedelta(days=7)).timestamp())
        
        job_record = {
            'jobId': job_id,
            'fileId': file_id,
            'status': JobStatus.PENDING,
            'totalRows': total_rows,
            'completedRows': 0,
            'analysisColumns': analysis_columns,
            'inputFileKey': input_file_key,
            'fileType': file_type,
            'outputFileKey': '',
            'aggregateAnalysis': '',
            'createdAt': now,
            'updatedAt': now,
            'errors': [],
            'ttl': ttl
        }
        
        self.table.put_item(Item=job_record)
        return job_record
    
    def get_job(self, job_id: str) -> Optional[Dict[str, Any]]:
        """
        Retrieve a job record by job ID.
        
        Args:
            job_id: Job identifier
            
        Returns:
            Job record if found, None otherwise
        """
        response = self.table.get_item(Key={'jobId': job_id})
        return response.get('Item')
    
    def update_job_status(
        self,
        job_id: str,
        status: str,
        completed_rows: Optional[int] = None,
        errors: Optional[List[Dict[str, str]]] = None
    ) -> None:
        """
        Update job status and progress.
        
        Args:
            job_id: Job identifier
            status: New status (pending, processing, completed, failed)
            completed_rows: Number of completed rows (optional)
            errors: List of error records (optional)
        """
        now = datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')
        
        update_expression = "SET #status = :status, updatedAt = :updated"
        expression_attribute_names = {'#status': 'status'}
        expression_attribute_values = {
            ':status': status,
            ':updated': now
        }
        
        if completed_rows is not None:
            update_expression += ", completedRows = :completed"
            expression_attribute_values[':completed'] = completed_rows
        
        if errors is not None:
            update_expression += ", errors = :errors"
            expression_attribute_values[':errors'] = errors
        
        self.table.update_item(
            Key={'jobId': job_id},
            UpdateExpression=update_expression,
            ExpressionAttributeNames=expression_attribute_names,
            ExpressionAttributeValues=expression_attribute_values
        )
    
    def update_job_progress(
        self,
        job_id: str,
        completed_rows: int
    ) -> None:
        """
        Update job progress (completed rows count).
        
        Args:
            job_id: Job identifier
            completed_rows: Number of completed rows
        """
        now = datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')
        
        self.table.update_item(
            Key={'jobId': job_id},
            UpdateExpression="SET completedRows = :completed, updatedAt = :updated",
            ExpressionAttributeValues={
                ':completed': completed_rows,
                ':updated': now
            }
        )
    
    def update_output_file(
        self,
        job_id: str,
        output_file_key: str
    ) -> None:
        """
        Update the output file key for a job.
        
        Args:
            job_id: Job identifier
            output_file_key: S3 key for output file
        """
        now = datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')
        
        self.table.update_item(
            Key={'jobId': job_id},
            UpdateExpression="SET outputFileKey = :output, updatedAt = :updated",
            ExpressionAttributeValues={
                ':output': output_file_key,
                ':updated': now
            }
        )
    
    def update_aggregate_analysis(
        self,
        job_id: str,
        aggregate_analysis: str
    ) -> None:
        """
        Update the aggregate analysis for a job.
        
        Args:
            job_id: Job identifier
            aggregate_analysis: Aggregate analysis text
        """
        now = datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')
        
        self.table.update_item(
            Key={'jobId': job_id},
            UpdateExpression="SET aggregateAnalysis = :analysis, updatedAt = :updated",
            ExpressionAttributeValues={
                ':analysis': aggregate_analysis,
                ':updated': now
            }
        )
    
    def add_job_error(
        self,
        job_id: str,
        error_message: str,
        row_number: Optional[int] = None
    ) -> None:
        """
        Add an error to a job's error list.
        
        Args:
            job_id: Job identifier
            error_message: Error message
            row_number: Row number where error occurred (optional)
        """
        error_record = {
            'message': error_message,
            'timestamp': datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')
        }
        
        if row_number is not None:
            error_record['rowNumber'] = row_number
        
        # Get current job to append to errors list
        job = self.get_job(job_id)
        if job:
            errors = job.get('errors', [])
            errors.append(error_record)
            
            self.table.update_item(
                Key={'jobId': job_id},
                UpdateExpression="SET errors = :errors, updatedAt = :updated",
                ExpressionAttributeValues={
                    ':errors': errors,
                    ':updated': datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')
                }
            )
    
    def increment_completed_rows(
        self,
        job_id: str,
        increment: int = 1
    ) -> None:
        """
        Atomically increment the completed rows counter.
        
        Args:
            job_id: Job identifier
            increment: Number to increment by (default 1)
        """
        now = datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')
        
        self.table.update_item(
            Key={'jobId': job_id},
            UpdateExpression="ADD completedRows :inc SET updatedAt = :updated",
            ExpressionAttributeValues={
                ':inc': increment,
                ':updated': now
            }
        )
    
    def get_job_progress(self, job_id: str) -> Dict[str, Any]:
        """
        Get job progress information.
        
        Args:
            job_id: Job identifier
            
        Returns:
            Dictionary with status, progress percentage, completed rows, and total rows
        """
        job = self.get_job(job_id)
        
        if not job:
            return {
                'status': 'not_found',
                'progress': 0,
                'completedRows': 0,
                'totalRows': 0
            }
        
        total_rows = job.get('totalRows', 0)
        completed_rows = job.get('completedRows', 0)
        
        # Calculate progress percentage
        progress = 0
        if total_rows > 0:
            progress = round((completed_rows / total_rows) * 100, 2)
        
        return {
            'jobId': job.get('jobId'),
            'status': job.get('status'),
            'progress': progress,
            'completedRows': completed_rows,
            'totalRows': total_rows,
            'errors': job.get('errors', [])
        }
