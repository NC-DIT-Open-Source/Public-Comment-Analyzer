import { Injectable } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable } from 'rxjs';
import { environment } from '../../environments/environment';

export interface ResultsResponse {
  downloadUrl: string;
  aggregateAnalysis: string | null;
  analysisStatus?: 'generating';
  message?: string;
}

@Injectable({
  providedIn: 'root'
})
export class ResultsService {
  private apiUrl = environment.apiBaseUrl;

  constructor(private http: HttpClient) { }

  getResults(jobId: string): Observable<ResultsResponse> {
    return this.http.get<ResultsResponse>(`${this.apiUrl}/results/${jobId}`);
  }
}
