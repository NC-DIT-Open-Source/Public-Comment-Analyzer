import { Component, EventEmitter, Output, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { Router, RouterModule } from '@angular/router';
import { FormBuilder, FormGroup, FormArray, ReactiveFormsModule, Validators } from '@angular/forms';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { MatButtonModule } from '@angular/material/button';
import { MatChipsModule } from '@angular/material/chips';
import { MatIconModule } from '@angular/material/icon';
import { MatCardModule } from '@angular/material/card';
import { MatButtonToggleModule } from '@angular/material/button-toggle';
import { AnalysisColumn, CategoryOption, ProcessingService } from '../../services/processing.service';
import { FileMetadata } from '../../services/file-upload.service';

@Component({
  selector: 'app-column-definition',
  imports: [
    CommonModule,
    RouterModule,
    ReactiveFormsModule,
    MatFormFieldModule,
    MatInputModule,
    MatButtonModule,
    MatChipsModule,
    MatIconModule,
    MatCardModule,
    MatButtonToggleModule
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
  selectedCommentColumn: string | null = null;
  contextDescription: string | null = null;
  isProcessing = false;
  errorMessage: string | null = null;
  columnType: 'open_text' | 'categorized' = 'open_text';

  constructor(
    private fb: FormBuilder,
    private router: Router,
    private processingService: ProcessingService
  ) {
    this.columnForm = this.fb.group({
      name: [''],
      instructions: [''],
      options: this.fb.array([])
    });

    // Get file metadata from navigation state
    const navigation = this.router.getCurrentNavigation();
    if (navigation?.extras.state) {
      this.fileMetadata = navigation.extras.state['fileMetadata'];
      this.fileName = navigation.extras.state['fileName'] || 'uploaded file';
      this.selectedCommentColumn = navigation.extras.state['selectedCommentColumn'] || null;
      this.contextDescription = navigation.extras.state['contextDescription'] || null;
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
        this.selectedCommentColumn = state.selectedCommentColumn || null;
        this.contextDescription = state.contextDescription || null;
      } else {
        console.log('No fileMetadata found, redirecting to upload');
        this.router.navigate(['/upload']);
      }
    }
  }

  get optionsArray(): FormArray {
    return this.columnForm.get('options') as FormArray;
  }

  onColumnTypeChange(type: 'open_text' | 'categorized'): void {
    this.columnType = type;
    if (type === 'categorized') {
      // Clear instructions, ensure at least 2 options
      this.columnForm.patchValue({ instructions: '' });
      while (this.optionsArray.length < 2) {
        this.addOption();
      }
    } else {
      // Clear options
      while (this.optionsArray.length > 0) {
        this.optionsArray.removeAt(0);
      }
    }
  }

  addOption(): void {
    if (this.optionsArray.length >= 50) return;
    this.optionsArray.push(this.fb.group({
      value: [''],
      description: ['']
    }));
  }

  removeOption(index: number): void {
    if (this.optionsArray.length <= 2) return;
    this.optionsArray.removeAt(index);
  }

  addColumn(): void {
    const name = this.columnForm.value.name?.trim() || '';

    if (!name) {
      this.columnForm.get('name')?.markAsTouched();
      this.columnForm.get('name')?.setErrors({ required: true });
      return;
    }

    this.columnForm.get('name')?.setErrors(null);

    if (this.columnType === 'open_text') {
      const instructions = this.columnForm.value.instructions?.trim() || '';
      if (!instructions) {
        this.columnForm.get('instructions')?.markAsTouched();
        this.columnForm.get('instructions')?.setErrors({ required: true });
        return;
      }
      this.columnForm.get('instructions')?.setErrors(null);

      const newColumn: AnalysisColumn = { name, instructions, type: 'open_text' };
      if (this.editingIndex !== null) {
        this.columns[this.editingIndex] = newColumn;
        this.editingIndex = null;
      } else {
        this.columns.push(newColumn);
      }
    } else {
      // Categorized
      const rawOptions = this.columnForm.value.options || [];
      const options: CategoryOption[] = [];
      let hasError = false;

      for (const opt of rawOptions) {
        const value = opt.value?.trim() || '';
        const description = opt.description?.trim() || '';
        if (!value || !description) {
          hasError = true;
          break;
        }
        options.push({ value, description });
      }

      if (hasError || options.length < 2) {
        this.errorMessage = 'Each option needs both a value and description, with at least 2 options.';
        return;
      }

      // Build instructions string from options for backend compatibility
      const instructions = options.map(o => `${o.value}: ${o.description}`).join('; ');

      const newColumn: AnalysisColumn = {
        name,
        instructions,
        type: 'categorized',
        options
      };

      if (this.editingIndex !== null) {
        this.columns[this.editingIndex] = newColumn;
        this.editingIndex = null;
      } else {
        this.columns.push(newColumn);
      }
    }

    this.errorMessage = null;
    this.columnForm.reset();
    this.resetForm();
    this.columnsChanged.emit(this.columns);
  }

  private resetForm(): void {
    this.columnType = 'open_text';
    while (this.optionsArray.length > 0) {
      this.optionsArray.removeAt(0);
    }
  }

  editColumn(index: number): void {
    const column = this.columns[index];
    this.columnType = column.type || 'open_text';

    // Clear existing options
    while (this.optionsArray.length > 0) {
      this.optionsArray.removeAt(0);
    }

    if (this.columnType === 'categorized' && column.options) {
      for (const opt of column.options) {
        this.optionsArray.push(this.fb.group({
          value: [opt.value],
          description: [opt.description]
        }));
      }
      this.columnForm.patchValue({ name: column.name, instructions: '' });
    } else {
      this.columnForm.patchValue({
        name: column.name,
        instructions: column.instructions
      });
    }
    this.editingIndex = index;
  }

  removeColumn(index: number): void {
    this.columns.splice(index, 1);
    if (this.editingIndex === index) {
      this.editingIndex = null;
      this.columnForm.reset();
      this.resetForm();
    }
    this.columnsChanged.emit(this.columns);
  }

  cancelEdit(): void {
    this.editingIndex = null;
    this.columnForm.reset();
    this.resetForm();
  }

  get isEditing(): boolean {
    return this.editingIndex !== null;
  }

  startProcessing(): void {
    if (!this.fileMetadata || !this.selectedCommentColumn || !this.contextDescription) {
      this.router.navigate(['/upload']);
      return;
    }

    if (this.columns.length === 0) {
      this.errorMessage = 'Please define at least one analysis column';
      return;
    }

    this.isProcessing = true;
    this.errorMessage = null;

    const request = {
      fileId: this.fileMetadata.fileId,
      selectedCommentColumn: this.selectedCommentColumn!,
      contextDescription: this.contextDescription!,
      analysisColumns: this.columns
    };

    this.processingService.startProcessing(request).subscribe({
      next: (response) => {
        this.isProcessing = false;
        this.router.navigate(['/processing', response.jobId], {
          state: {
            fileMetadata: this.fileMetadata,
            fileName: this.fileName
          }
        });
      },
      error: (error) => {
        this.isProcessing = false;
        const body = error.error;
        const code = body?.error?.code;
        const msg = body?.error?.message;

        const friendlyMessages: Record<string, string> = {
          'INSTRUCTIONS_TOO_LONG': 'Your analysis instructions are too long. Try shortening the descriptions on your options or instructions.',
          'TOO_MANY_COLUMNS': 'You have too many analysis columns. Please remove some and try again.',
          'TOO_MANY_OPTIONS': 'One of your categorized columns has too many options (max 50).',
          'INVALID_CATEGORIZED_COLUMN': 'Categorized columns need at least 2 options.',
          'INVALID_OPTION': 'Each option needs both a value and a description.',
          'COLUMN_NAME_TOO_LONG': 'One of your column names is too long. Please shorten it.',
          'MISSING_FILE_ID': 'No file was found. Please go back and upload your file again.',
          'MISSING_ANALYSIS_COLUMNS': 'Please define at least one analysis column.',
          'INVALID_ANALYSIS_COLUMN': 'One of your columns is missing required fields. Please check and try again.',
          'MISSING_COMMENT_COLUMN': 'Session expired or page was cached. Please go back to upload and start again.',
          'MISSING_CONTEXT_DESCRIPTION': 'Session expired or page was cached. Please go back to upload and start again.',
          'COMMENT_COLUMN_TOO_LONG': 'The selected comment column name is too long.',
          'CONTEXT_TOO_LONG': 'Your context description is too long (max 200 characters).',
          'UNAUTHORIZED': 'Access denied. Please check your access key and try again.',
        };

        this.errorMessage = friendlyMessages[code] || msg || 'Failed to start processing. Please try again.';
      }
    });
  }
}
