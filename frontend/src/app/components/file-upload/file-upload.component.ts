import { Component, Output, EventEmitter } from '@angular/core';
import { CommonModule } from '@angular/common';
import { Router } from '@angular/router';
import { MatCardModule } from '@angular/material/card';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { FileUploadService, FileMetadata } from '../../services/file-upload.service';

@Component({
  selector: 'app-file-upload',
  imports: [
    CommonModule,
    MatCardModule,
    MatButtonModule,
    MatIconModule,
    MatProgressSpinnerModule
  ],
  templateUrl: './file-upload.component.html',
  styleUrl: './file-upload.component.scss'
})
export class FileUploadComponent {
  @Output() fileUploaded = new EventEmitter<FileMetadata>();

  selectedFile: File | null = null;
  uploadedFileMetadata: FileMetadata | null = null;
  isDragging = false;
  isUploading = false;
  errorMessage: string | null = null;

  constructor(
    private fileUploadService: FileUploadService,
    private router: Router
  ) {}

  onDragOver(event: DragEvent): void {
    event.preventDefault();
    event.stopPropagation();
    this.isDragging = true;
  }

  onDragLeave(event: DragEvent): void {
    event.preventDefault();
    event.stopPropagation();
    this.isDragging = false;
  }

  onDrop(event: DragEvent): void {
    event.preventDefault();
    event.stopPropagation();
    this.isDragging = false;

    const files = event.dataTransfer?.files;
    if (files && files.length > 0) {
      this.handleFile(files[0]);
    }
  }

  onFileSelected(event: Event): void {
    const input = event.target as HTMLInputElement;
    if (input.files && input.files.length > 0) {
      this.handleFile(input.files[0]);
    }
  }

  private handleFile(file: File): void {
    this.errorMessage = null;
    this.uploadedFileMetadata = null;

    // Validate file format
    const validExtensions = ['.csv', '.xlsx'];
    const fileExtension = file.name.substring(file.name.lastIndexOf('.')).toLowerCase();
    
    if (!validExtensions.includes(fileExtension)) {
      this.errorMessage = `Invalid file format. Please upload a CSV or XLSX file.`;
      this.selectedFile = null;
      return;
    }

    this.selectedFile = file;
    this.uploadFile();
  }

  private uploadFile(): void {
    if (!this.selectedFile) return;

    this.isUploading = true;
    this.errorMessage = null;

    console.log('Starting file upload:', this.selectedFile.name);

    this.fileUploadService.uploadFile(this.selectedFile).subscribe({
      next: (metadata) => {
        console.log('Upload successful, received metadata:', metadata);
        this.uploadedFileMetadata = metadata;
        this.isUploading = false;
        this.fileUploaded.emit(metadata);
        
        // Navigate to column definition page
        console.log('Navigating to column definition with state:', {
          fileMetadata: metadata,
          fileName: this.selectedFile?.name
        });
        this.router.navigate(['/define-columns'], {
          state: { 
            fileMetadata: metadata,
            fileName: this.selectedFile?.name || 'uploaded file'
          }
        });
      },
      error: (error) => {
        console.error('Upload failed:', error);
        this.isUploading = false;
        this.errorMessage = error.error?.message || 'Failed to upload file. Please try again.';
        this.selectedFile = null;
      }
    });
  }

  formatFileSize(bytes: number): string {
    if (bytes === 0) return '0 Bytes';
    const k = 1024;
    const sizes = ['Bytes', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return Math.round(bytes / Math.pow(k, i) * 100) / 100 + ' ' + sizes[i];
  }

  reset(): void {
    this.selectedFile = null;
    this.uploadedFileMetadata = null;
    this.errorMessage = null;
    this.isUploading = false;
  }
}
