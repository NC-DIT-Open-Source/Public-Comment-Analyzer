import { Injectable } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable } from 'rxjs';
import { environment } from '../../environments/environment';

export interface ChartDefinition {
  title: string;
  description: string;
  type: string;
  config: any;
}

export interface DashboardResponse {
  charts: ChartDefinition[];
  narrative: string;
}

@Injectable({
  providedIn: 'root'
})
export class DashboardService {
  private apiUrl = environment.apiBaseUrl;

  constructor(private http: HttpClient) {}

  generateDashboard(jobId: string, prompt: string): Observable<DashboardResponse> {
    return this.http.post<DashboardResponse>(
      `${this.apiUrl}/dashboard/${jobId}`,
      { prompt }
    );
  }
}
