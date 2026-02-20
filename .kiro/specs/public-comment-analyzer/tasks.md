# Implementation Plan: Public Comment Analyzer

## Overview

This implementation plan breaks down the Public Comment Analyzer into discrete coding tasks. The system uses Python for AWS Lambda backend functions, Angular with Material Design for the frontend, and AWS cloud-native services (S3, API Gateway, CloudFront, Bedrock, DynamoDB).

The implementation follows this sequence:
1. Set up project structure and infrastructure-as-code
2. Implement backend Lambda functions (file handling, processing, analysis)
3. Implement Angular frontend with Material Design
4. Wire components together and deploy
5. Add comprehensive testing

## Tasks

- [x] 1. Set up project structure and AWS infrastructure
  - Create directory structure for Lambda functions (Python), Angular frontend, and infrastructure code
  - Set up Terraform for infrastructure-as-code
  - Define S3 buckets (data storage, static website hosting), DynamoDB table (job tracking), API Gateway, CloudFront distribution
  - Configure IAM roles and policies for Lambda functions (S3 access, Bedrock access, DynamoDB access)
  - Add resource tagging: Application=PublicCommentAnalyzer, Environment, ManagedBy
  - _Requirements: 7.1, 7.5, 7.6, 7.7, 7.8, 7.10, 7.11_

- [ ] 2. Implement file parser module
  - [x] 2.1 Create FileParser class with CSV and XLSX support
    - Implement CSV parsing using Python csv module with proper encoding detection
    - Implement XLSX parsing using openpyxl library (first worksheet only)
    - Return uniform ParsedFile data structure with headers, rows, and row count
    - _Requirements: 1.1, 1.2, 1.4, 1.6_
  
  - [ ]* 2.2 Write property test for file parser
    - **Property 3: Column Header Extraction**
    - **Validates: Requirements 1.4**
  
  - [ ]* 2.3 Write property test for data preservation
    - **Property 2: Data Preservation and Augmentation** (parser portion)
    - **Validates: Requirements 1.2**
  
  - [ ]* 2.4 Write unit tests for file parser edge cases
    - Test with empty file, single row, special characters, unicode
    - Test XLSX with multiple worksheets
    - _Requirements: 1.1, 1.6_

- [ ] 3. Implement file writer module
  - [x] 3.1 Create FileWriter class for CSV and XLSX output
    - Implement CSV writing with proper escaping and formatting
    - Implement XLSX writing using openpyxl
    - Preserve input file format in output
    - _Requirements: 5.1, 5.2, 5.5_
  
  - [ ]* 3.2 Write property test for format preservation
    - **Property 15: Format Preservation**
    - **Validates: Requirements 5.1**
  
  - [ ]* 3.3 Write property test for special character escaping
    - **Property 16: Special Character Escaping**
    - **Validates: Requirements 5.5**

- [ ] 4. Implement Upload Handler Lambda function
  - [x] 4.1 Create upload handler with file validation
    - Accept multipart file upload from API Gateway
    - Validate file format (CSV or XLSX)
    - Parse file to extract headers and row count
    - Generate unique file ID (UUID)
    - Store file in S3 at uploads/{fileId}/input.{ext}
    - Return file metadata (fileId, columns, rowCount)
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5_
  
  - [ ]* 4.2 Write property test for file format validation
    - **Property 1: File Format Validation and Rejection**
    - **Validates: Requirements 1.1, 1.3**
  
  - [ ]* 4.3 Write unit tests for upload handler
    - Test with valid CSV and XLSX files
    - Test with invalid file formats
    - Test S3 upload failure handling
    - _Requirements: 1.1, 1.3, 1.5_

- [ ] 5. Implement Row Processor Lambda function
  - [x] 5.1 Create main row processor orchestrator
    - Read input file from S3 using FileParser
    - Create job record in DynamoDB with status tracking
    - Split rows into batches for concurrent processing
    - Invoke worker Lambda instances asynchronously (10 concurrent)
    - Aggregate results and write to S3 using FileWriter
    - Update job status and progress in DynamoDB
    - _Requirements: 3.1, 3.4, 3.6, 4.1, 5.1, 5.2, 5.3_
  
  - [x] 5.2 Implement Bedrock integration for row processing
    - Construct prompt with comment text and analysis column instructions
    - Call AWS Bedrock with Claude Haiku model ID
    - Parse JSON response and map to analysis columns
    - Implement retry logic with exponential backoff (3 attempts)
    - Handle errors and continue processing remaining rows
    - _Requirements: 3.1, 3.2, 3.3, 3.5, 7.2, 7.3, 9.1_
  
  - [ ]* 5.3 Write property test for complete row processing
    - **Property 9: Complete Row Processing**
    - **Validates: Requirements 3.1**
  
  - [ ]* 5.4 Write property test for prompt completeness
    - **Property 10: Prompt Completeness**
    - **Validates: Requirements 3.2**
  
  - [ ]* 5.5 Write property test for row order preservation
    - **Property 13: Row Order Preservation**
    - **Validates: Requirements 3.6, 5.3**
  
  - [ ]* 5.6 Write property test for error resilience
    - **Property 12: Error Resilience**
    - **Validates: Requirements 3.5**
  
  - [ ]* 5.7 Write property test for retry with exponential backoff
    - **Property 20: Retry with Exponential Backoff**
    - **Validates: Requirements 9.1**
  
  - [ ]* 5.8 Write unit tests for row processor
    - Test with sample CSV data and column definitions
    - Test with simulated Bedrock failures
    - Test concurrent processing behavior
    - _Requirements: 3.1, 3.4, 3.5, 9.1_

- [x] 6. Checkpoint - Ensure backend file processing works
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 7. Implement Aggregate Analyzer Lambda function
  - [x] 7.1 Create aggregate analyzer with Claude Opus integration
    - Read processed file from S3
    - Format data for aggregate analysis prompt
    - Construct prompt requesting sentiment distribution and key themes
    - Call AWS Bedrock with Claude Opus 4.6 model ID
    - Parse and format aggregate analysis response
    - Store analysis in DynamoDB job record
    - Return analysis to client
    - _Requirements: 6.1, 6.2, 6.3, 6.5, 7.2, 7.4_
  
  - [ ]* 7.2 Write property test for Bedrock exclusivity
    - **Property 17: Bedrock Exclusivity**
    - **Validates: Requirements 7.2**
  
  - [ ]* 7.3 Write unit tests for aggregate analyzer
    - Test with sample processed data
    - Test prompt construction
    - Test with mocked Bedrock responses
    - _Requirements: 6.1, 6.2, 6.3_

- [ ] 8. Implement API Gateway endpoints and Lambda integrations
  - [x] 8.1 Define API Gateway REST API with endpoints
    - POST /api/upload - integrate with Upload Handler Lambda
    - POST /api/process - integrate with Row Processor Lambda
    - GET /api/status/{jobId} - query DynamoDB for job status
    - GET /api/results/{jobId} - integrate with Aggregate Analyzer Lambda
    - Configure CORS for Angular frontend
    - Add request validation and throttling
    - _Requirements: 7.7_
  
  - [ ]* 8.2 Write integration tests for API endpoints
    - Test each endpoint with sample requests
    - Test error responses
    - _Requirements: 7.7_

- [ ] 9. Set up Angular project with Material Design
  - [x] 9.1 Create Angular application structure
    - Initialize Angular 17+ project
    - Install Angular Material and configure theme
    - Set up routing for main workflow pages
    - Create shared services (FileUploadService, ProcessingService, ResultsService)
    - Configure environment files for API endpoints
    - _Requirements: 8.1, 8.2_
  
  - [x] 9.2 Configure build for S3 deployment
    - Set up production build configuration
    - Configure base href for CloudFront distribution
    - Add build scripts for deployment
    - _Requirements: 7.8, 8.1_

- [ ] 10. Implement file upload component
  - [x] 10.1 Create FileUploadComponent with Material Design
    - Use mat-card for upload area
    - Implement drag-and-drop file upload
    - Add file picker button with mat-button
    - Display file validation errors using mat-error
    - Show uploaded file details (name, size, columns)
    - Call FileUploadService to upload file to API
    - _Requirements: 1.1, 1.3, 1.4, 8.3, 8.5_
  
  - [ ]* 10.2 Write unit tests for FileUploadComponent
    - Test file selection and validation
    - Test drag-and-drop functionality
    - Test error display
    - _Requirements: 1.1, 1.3, 8.5_

- [ ] 11. Implement column definition component
  - [x] 11.1 Create ColumnDefinitionComponent with Material Design
    - Use mat-form-field and mat-input for column name and instructions
    - Add mat-chip-list to display defined columns
    - Implement add, edit, and remove column functionality
    - Validate that name and instructions are non-empty
    - Use mat-button for actions
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 8.3, 8.4_
  
  - [ ]* 11.2 Write property test for analysis column validation
    - **Property 4: Analysis Column Validation**
    - **Validates: Requirements 2.1, 9.4**
  
  - [ ]* 11.3 Write property test for multiple column support
    - **Property 5: Multiple Column Support**
    - **Validates: Requirements 2.2**
  
  - [ ]* 11.4 Write unit tests for ColumnDefinitionComponent
    - Test adding, editing, removing columns
    - Test validation errors
    - Test display of column definitions
    - _Requirements: 2.1, 2.2, 2.4, 2.5_

- [ ] 12. Implement processing monitor component
  - [x] 12.1 Create ProcessingMonitorComponent with Material Design
    - Use mat-stepper to show workflow steps
    - Use mat-progress-bar for processing progress
    - Poll ProcessingService for job status updates
    - Display current status and percentage complete
    - Show completion notification when done
    - _Requirements: 4.3, 4.4, 8.3, 8.5_
  
  - [ ]* 12.2 Write property test for progress accuracy
    - **Property 14: Progress Accuracy**
    - **Validates: Requirements 4.3**
  
  - [ ]* 12.3 Write unit tests for ProcessingMonitorComponent
    - Test status polling
    - Test progress display
    - Test completion notification
    - _Requirements: 4.3, 4.4, 8.5_

- [ ] 13. Implement results viewer component
  - [x] 13.1 Create ResultsViewerComponent with Material Design
    - Use mat-card to display aggregate analysis
    - Add mat-button for downloading processed file
    - Add mat-button for copying analysis text
    - Call ResultsService to fetch results from API
    - Generate presigned S3 URL for file download
    - _Requirements: 5.4, 6.3, 6.5, 8.3_
  
  - [ ]* 13.2 Write unit tests for ResultsViewerComponent
    - Test results display
    - Test download functionality
    - Test copy functionality
    - _Requirements: 5.4, 6.3, 6.5_

- [ ] 14. Implement Angular services
  - [x] 14.1 Create FileUploadService
    - Implement uploadFile method calling POST /api/upload
    - Handle file upload with multipart/form-data
    - Return observable with file metadata
    - Handle errors and return user-friendly messages
    - _Requirements: 1.1, 1.3, 9.2_
  
  - [x] 14.2 Create ProcessingService
    - Implement startProcessing method calling POST /api/process
    - Implement getStatus method calling GET /api/status/{jobId}
    - Implement polling mechanism with RxJS interval
    - Handle errors and return user-friendly messages
    - _Requirements: 4.3, 9.2_
  
  - [x] 14.3 Create ResultsService
    - Implement getResults method calling GET /api/results/{jobId}
    - Return observable with download URL and aggregate analysis
    - Handle errors and return user-friendly messages
    - _Requirements: 5.4, 6.3, 9.2_
  
  - [ ]* 14.4 Write property test for error message generation
    - **Property 21: Error Message Generation**
    - **Validates: Requirements 9.2**
  
  - [ ]* 14.5 Write unit tests for Angular services
    - Test each service method with mocked HTTP calls
    - Test error handling
    - Test polling mechanism
    - _Requirements: 9.2_

- [x] 15. Checkpoint - Ensure frontend components work
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 16. Implement DynamoDB job tracking
  - [x] 16.1 Create DynamoDB table and data access layer
    - Define table schema for job records (jobId, status, progress, etc.)
    - Implement Python functions for create, read, update operations
    - Add indexes for efficient querying
    - _Requirements: 3.6, 4.3_
  
  - [ ]* 16.2 Write unit tests for DynamoDB operations
    - Test create, read, update with mocked DynamoDB
    - Test error handling
    - _Requirements: 4.3_

- [ ] 17. Implement error handling and partial results
  - [x] 17.1 Add error handling throughout backend
    - Implement error logging for all Lambda functions
    - Add error annotations to partial result files
    - Generate downloadable partial results when errors occur
    - Identify and report problematic rows
    - _Requirements: 9.2, 9.3, 9.5_
  
  - [ ]* 17.2 Write property test for invalid data detection
    - **Property 22: Invalid Data Detection**
    - **Validates: Requirements 9.3**
  
  - [ ]* 17.3 Write property test for partial results with error annotations
    - **Property 23: Partial Results with Error Annotations**
    - **Validates: Requirements 9.5**
  
  - [ ]* 17.4 Write unit tests for error handling
    - Test error logging
    - Test partial results generation
    - Test error message formatting
    - _Requirements: 9.2, 9.3, 9.5_

- [ ] 18. Wire everything together and deploy
  - [x] 18.1 Deploy infrastructure with CDK/Terraform
    - Deploy S3 buckets, DynamoDB table, Lambda functions, API Gateway, CloudFront using Terraform
    - Configure environment variables for Lambda functions
    - Set up CloudFront distribution pointing to S3 and API Gateway
    - Verify all resource tags are applied
    - _Requirements: 7.1, 7.5, 7.6, 7.7, 7.8, 7.10, 7.11_
  
  - [x] 18.2 Build and deploy Angular frontend
    - Run production build
    - Upload build artifacts to S3 static website bucket
    - Invalidate CloudFront cache
    - _Requirements: 7.8, 8.1_
  
  - [x] 18.3 Configure API Gateway CORS and CloudFront
    - Set CORS headers for Angular frontend domain
    - Configure CloudFront behaviors for API and static content
    - Test end-to-end workflow
    - _Requirements: 7.7, 7.8_
  
  - [ ]* 18.4 Write property test for S3 storage consistency
    - **Property 18: S3 Storage Consistency**
    - **Validates: Requirements 7.5**
  
  - [ ]* 18.5 Write property test for resource tagging compliance
    - **Property 19: Resource Tagging Compliance**
    - **Validates: Requirements 7.10, 7.11**
  
  - [ ]* 18.6 Write integration tests for end-to-end workflow
    - Test complete workflow with sample file
    - Test with 1,000 row file
    - Test with 10,000 row file (capacity test)
    - _Requirements: 1.5, 4.1_

- [x] 19. Final checkpoint - Complete system verification
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Backend uses Python for Lambda functions
- Frontend uses Angular 17+ with Material Design
- Infrastructure uses AWS CDK or Terraform
- Property tests validate universal correctness properties
- Unit tests validate specific examples and edge cases
- Integration tests verify end-to-end workflows
