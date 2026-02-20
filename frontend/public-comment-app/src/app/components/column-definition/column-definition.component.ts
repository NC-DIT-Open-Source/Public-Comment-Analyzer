import { Component, EventEmitter, Output, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { Router, RouterModule } from '@angular/router';
import { FormBuilder, FormGroup, ReactiveFormsModule, Validators } from '@angular/forms';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { MatButtonModule } from '@angular/material/button';
import { MatChipsModule } from '@angular/material/chips';
import { MatIconModule } from '@angular/material/icon';
import { MatCardModule } from '@angular/material/card';
import { AnalysisColumn, ProcessingService } from '../../services/processing.service';
import { FileMetadata } from '../../services/file-upload.service';

@Component({
  selector: 'app-column-definition',
  standalone: true,
  imports: [
    CommonModule,
    RouterModule,
    ReactiveFormsModule,
    MatFormFieldModule,
    MatInputModule,
    MatButtonModule,
    MatChipsModule,
    MatIconModule,
    MatCardModule
  ],
  templateUrl: './column-definition.component.html',
  styleUrl: './column-definition.component.scss'
})
export class ColumnDefinitionComponent implements OnInit {
  @Output() columnsChanged = new EventEmitter<AnalysisColumn[]>();
  
  columnForm: FormGroup;
  columns: AnalysisColumn[] = [];
  editingIndex: number | null = null;
  fileMetadata: FileMetadata | null = null;
  fileName: string = '';
  isProcessing = false;
  errorMessage: string | null = null;

  constructor(
    private fb: FormBuilder,
    private router: Router,
    private processingService: ProcessingService
  ) {
    this.columnForm = this.fb.group({
      name: ['', [Validators.required, Validators.minLength(1)]],
      instructions: ['', [Validators.required, Validators.minLength(1)]]
    });

    // Get file metadata from navigation state
    const navigation = this.router.getCurrentNavigation();
    if (navigation?.extras.state) {
      this.fileMetadata = navigation.extras.state['fileMetadata'];
      this.fileName = navigation.extras.state['fileName'] || 'uploaded file';
    }
  }

  ngOnInit(): void {
    console.log('ColumnDefinitionComponent ngOnInit');
    console.log('Initial fileMetadata:', this.fileMetadata);
    console.log('History state:', history.state);
    
    // If no file metadata, redirect back to upload
    if (!this.fileMetadata) {
      const state = history.state;
      if (state && state.fileMetadata) {
        console.log('Found fileMetadata in history.state');
        this.fileMetadata = state.fileMetadata;
        this.fileName = state.fileName || 'uploaded file';
      } else {
        console.log('No fileMetadata found, redirecting to upload');
        this.router.navigate(['/upload']);
      }
    }
  }

  addColumn(): void {
    if (this.columnForm.valid) {
      const name = this.columnForm.value.name.trim();
      const instructions = this.columnForm.value.instructions.trim();
      
      // Don't add if trimmed values are empty
      if (!name || !instructions) {
        return;
      }

      const newColumn: AnalysisColumn = { name, instructions };

      if (this.editingIndex !== null) {
        // Update existing column
        this.columns[this.editingIndex] = newColumn;
        this.editingIndex = null;
      } else {
        // Add new column
        this.columns.push(newColumn);
      }

      this.columnForm.reset();
      this.columnsChanged.emit(this.columns);
    }
  }

  editColumn(index: number): void {
    const column = this.columns[index];
    this.columnForm.patchValue({
      name: column.name,
      instructions: column.instructions
    });
    this.editingIndex = index;
  }

  removeColumn(index: number): void {
    this.columns.splice(index, 1);
    if (this.editingIndex === index) {
      this.editingIndex = null;
      this.columnForm.reset();
    }
    this.columnsChanged.emit(this.columns);
  }

  cancelEdit(): void {
    this.editingIndex = null;
    this.columnForm.reset();
  }

  get isEditing(): boolean {
    return this.editingIndex !== null;
  }

  startProcessing(): void {
    if (this.columns.length === 0 || !this.fileMetadata) {
      this.errorMessage = 'Please define at least one analysis column';
      return;
    }

    this.isProcessing = true;
    this.errorMessage = null;

    const request = {
      fileId: this.fileMetadata.fileId,
      analysisColumns: this.columns
    };

    this.processingService.startProcessing(request).subscribe({
      next: (response) => {
        this.isProcessing = false;
        // Navigate to processing monitor
        this.router.navigate(['/processing'], {
          state: { 
            jobId: response.jobId,
            fileMetadata: this.fileMetadata,
            fileName: this.fileName
          }
        });
      },
      error: (error) => {
        this.isProcessing = false;
        this.errorMessage = error.error?.message || 'Failed to start processing. Please try again.';
      }
    });
  }
}
