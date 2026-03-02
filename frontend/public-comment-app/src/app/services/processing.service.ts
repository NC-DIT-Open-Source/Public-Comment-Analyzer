import { Injectable } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable, interval, switchMap, takeWhile } from 'rxjs';
import { environment } from '../../environments/environment';

export interface CategoryOption {
  value: string;
  description: string;
}

export interface AnalysisColumn {
  name: string;
  instructions: string;
  type: 'open_text' | 'categorized';
  options?: CategoryOption[];
}

export interface ProcessingRequest {
  fileId: string;
  analysisColumns: AnalysisColumn[];
}

export interface ProcessingResponse {
  jobId: string;
  status: string;
}

export interface JobStatus {
  status: 'pending' | 'processing' | 'completed' | 'failed';
  progress: number;
  completedRows: number;
  totalRows: number;
  error?: string;
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
    return interval(intervalMs).pipe(
      switchMap(() => this.getStatus(jobId)),
      takeWhile(status => status.status === 'pending' || status.status === 'processing', true)
    );
  }
}
