import { Component, OnInit, ChangeDetectionStrategy } from '@angular/core';
import { CommonModule } from '@angular/common';
import { Router } from '@angular/router';
import { FormBuilder, FormGroup, ReactiveFormsModule, Validators } from '@angular/forms';
import { MatCardModule } from '@angular/material/card';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { MatSelectModule } from '@angular/material/select';
import { MatButtonModule } from '@angular/material/button';
import { FileMetadata } from '../../services/file-upload.service';

@Component({
  selector: 'app-comment-column-picker',
  standalone: true,
  imports: [
    CommonModule,
    ReactiveFormsModule,
    MatCardModule,
    MatFormFieldModule,
    MatInputModule,
    MatSelectModule,
    MatButtonModule
  ],
  templateUrl: './comment-column-picker.component.html',
  changeDetection: ChangeDetectionStrategy.Eager,
  styleUrl: './comment-column-picker.component.scss'
})
export class CommentColumnPickerComponent implements OnInit {
  pickerForm: FormGroup;
  fileMetadata: FileMetadata | null = null;
  fileName: string = '';

  constructor(private fb: FormBuilder, private router: Router) {
    this.pickerForm = this.fb.group({
      commentColumn: ['', Validators.required],
      contextDescription: ['', [Validators.required, Validators.minLength(10), Validators.maxLength(200)]]
    });
  }

  ngOnInit(): void {
    const state = history.state;
    if (state?.fileMetadata) {
      this.fileMetadata = state.fileMetadata;
      this.fileName = state.fileName || 'uploaded file';
    } else {
      this.router.navigate(['/upload']);
    }
  }

  proceed(): void {
    if (this.pickerForm.invalid || !this.fileMetadata) return;
    this.router.navigate(['/define-columns'], {
      state: {
        fileMetadata: this.fileMetadata,
        fileName: this.fileName,
        selectedCommentColumn: this.pickerForm.value.commentColumn,
        contextDescription: this.pickerForm.value.contextDescription
      }
    });
  }

  goBack(): void {
    this.router.navigate(['/upload']);
  }
}
