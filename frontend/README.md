# Public Comment Analyzer - Angular Frontend

This is the Angular 21 frontend application for the Public Comment Analyzer system.

## Features

- File upload with drag-and-drop support
- Dynamic column definition interface
- Real-time processing progress monitoring
- Results viewer with aggregate analysis display
- Material Design UI components

## Prerequisites

- Node.js 22+ (LTS version recommended)
- npm 10+

## Installation

```bash
npm install
```

## Development Server

Run the development server:

```bash
npm start
```

Navigate to `http://localhost:4200/`. The application will automatically reload if you change any of the source files.

## Build

Build the project for production:

```bash
npm run build
```

The build artifacts will be stored in the `dist/public-comment-app/` directory.

## Project Structure

```
src/
├── app/
│   ├── components/
│   │   ├── file-upload/           # File upload component
│   │   ├── column-definition/     # Column definition component
│   │   ├── processing-monitor/    # Processing progress component
│   │   └── results-viewer/        # Results display component
│   ├── services/
│   │   ├── file-upload.service.ts    # File upload API calls
│   │   ├── processing.service.ts     # Processing job management
│   │   └── results.service.ts        # Results retrieval
│   ├── app.component.*            # Root component
│   ├── app.config.ts              # Application configuration
│   └── app.routes.ts              # Routing configuration
├── environments/
│   ├── environment.ts             # Development environment config
│   └── environment.prod.ts        # Production environment config
└── styles.scss                    # Global styles
```

## Services

### FileUploadService
Handles file upload operations to the backend API.

**Methods:**
- `uploadFile(file: File): Observable<FileMetadata>` - Upload a CSV/XLSX file

### ProcessingService
Manages processing job lifecycle and status polling.

**Methods:**
- `startProcessing(request: ProcessingRequest): Observable<ProcessingResponse>` - Start processing job
- `getStatus(jobId: string): Observable<JobStatus>` - Get current job status
- `pollStatus(jobId: string, intervalMs?: number): Observable<JobStatus>` - Poll job status until complete

### ResultsService
Retrieves processed results and aggregate analysis.

**Methods:**
- `getResults(jobId: string): Observable<ResultsResponse>` - Get results and download URL

## Environment Configuration

### Development (`environment.ts`)
```typescript
export const environment = {
  production: false,
  apiBaseUrl: 'http://localhost:3000/api'
};
```

### Production (`environment.prod.ts`)
```typescript
export const environment = {
  production: true,
  apiBaseUrl: '/api'
};
```

## Deployment to AWS S3

1. Build the production version:
```bash
npm run build
```

2. Upload to S3 bucket:
```bash
aws s3 sync dist/public-comment-app/ s3://your-frontend-bucket/ --delete
```

3. Invalidate CloudFront cache (if using CloudFront):
```bash
aws cloudfront create-invalidation --distribution-id YOUR_DIST_ID --paths "/*"
```

## Material Design Theme

The application uses the Indigo/Pink prebuilt theme from Angular Material. To customize the theme, modify `src/styles.scss`.

## Routing

The application uses lazy-loaded routes for better performance:

- `/upload` - File upload page
- `/define-columns` - Column definition page
- `/processing` - Processing monitor page
- `/results` - Results viewer page

## Testing

Run unit tests:
```bash
npm test
```

## Code Scaffolding

Generate a new component:
```bash
ng generate component component-name --standalone
```

Generate a new service:
```bash
ng generate service service-name
```

## Further Help

For more help on Angular CLI, use `ng help` or check out the [Angular CLI Documentation](https://angular.io/cli).
