import { Injectable } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable, interval, switchMap, takeWhile, startWith } from 'rxjs';
import { environment } from '../../environments/environment';

export interface CategoryOption {
  value: string;
  description: string;
}

export interface CategoryExample {
  commentText: string;
  label: string;
}

export interface AnalysisColumn {
  name: string;
  instructions: string;
  type: 'open_text' | 'categorized';
  options?: CategoryOption[];
  examples?: CategoryExample[];
}

export interface ProcessingRequest {
  fileId: string;
  selectedCommentColumn: string;
  contextDescription: string;
  analysisColumns: AnalysisColumn[];
}

export interface ProcessingResponse {
  jobId: string;
  status: string;
}

export type JobStatusValue =
  | 'pending'
  | 'preview_processing'
  | 'preview_ready'
  | 'processing'
  | 'completed'
  | 'failed';

export interface JobStatus {
  status: JobStatusValue;
  progress: number;
  completedRows: number;
  totalRows: number;
  error?: string;
  previewRows?: Array<Record<string, string>>;
  analysisColumns?: AnalysisColumn[];
  selectedCommentColumn?: string;
}

@Injectable({
  providedIn: 'root'
})
export class ProcessingService {
  private apiUrl = environment.apiBaseUrl;

  constructor(private http: HttpClient) { }

  startProcessing(request: ProcessingRequest): Observable<ProcessingResponse> {
    return this.http.post<ProcessingResponse>(`${this.apiUrl}/process`, request);
  }

  getStatus(jobId: string): Observable<JobStatus> {
    return this.http.get<JobStatus>(`${this.apiUrl}/status/${jobId}`);
  }

  pollStatus(jobId: string, intervalMs: number = 2000): Observable<JobStatus> {
    // Keep polling through every non-terminal state. preview_ready is non-terminal
    // because the user can confirm and we want polling to continue post-confirmation.
    const nonTerminal = new Set<JobStatusValue>([
      'pending', 'preview_processing', 'preview_ready', 'processing'
    ]);
    return interval(intervalMs).pipe(
      startWith(0),
      switchMap(() => this.getStatus(jobId)),
      takeWhile(status => nonTerminal.has(status.status), true)
    );
  }

  confirmPreview(jobId: string): Observable<ProcessingResponse> {
    return this.http.post<ProcessingResponse>(
      `${this.apiUrl}/process/${jobId}/preview-confirm`, {}
    );
  }
}
