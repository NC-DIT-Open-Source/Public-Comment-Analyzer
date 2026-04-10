import { Injectable } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable } from 'rxjs';
import { environment } from '../../environments/environment';

export interface FileMetadata {
  fileId: string;
  columns: string[];
  rowCount: number;
  selectedCommentColumn?: string | null;
  contextDescription?: string | null;
}

@Injectable({
  providedIn: 'root'
})
export class FileUploadService {
  private apiUrl = environment.apiBaseUrl;

  constructor(private http: HttpClient) { }

  uploadFile(file: File): Observable<FileMetadata> {
    const formData = new FormData();
    formData.append('file', file);
    
    return this.http.post<FileMetadata>(`${this.apiUrl}/upload`, formData);
  }
}
