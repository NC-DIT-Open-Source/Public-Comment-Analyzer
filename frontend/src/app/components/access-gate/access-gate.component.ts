import { Component, ChangeDetectorRef } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { AuthService } from '../../services/auth.service';

@Component({
  selector: 'app-access-gate',
  standalone: true,
  imports: [CommonModule, FormsModule],
  templateUrl: './access-gate.component.html',
  styleUrl: './access-gate.component.scss'
})
export class AccessGateComponent {
  password = '';
  error = '';
  loading = false;

  constructor(private authService: AuthService, private cdr: ChangeDetectorRef) {}

  submit(): void {
    if (!this.password.trim()) {
      this.error = 'Please enter the access password.';
      return;
    }

    this.loading = true;
    this.error = '';

    this.authService.validate(this.password).subscribe({
      next: (valid) => {
        this.loading = false;
        if (!valid) {
          this.error = 'Invalid password. Please try again.';
          this.password = '';
        }
        this.cdr.detectChanges();
      },
      error: () => {
        this.loading = false;
        this.error = 'Unable to validate. Please try again.';
        this.password = '';
        this.cdr.detectChanges();
      }
    });
  }
}
