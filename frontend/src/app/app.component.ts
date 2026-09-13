import { Component, ChangeDetectionStrategy, ChangeDetectorRef } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { environment } from '../environments/environment';
import { CommonModule } from '@angular/common';
import { RouterOutlet } from '@angular/router';
import { AuthService } from './services/auth.service';
import { AccessGateComponent } from './components/access-gate/access-gate.component';

@Component({
  selector: 'app-root',
  imports: [CommonModule, RouterOutlet, AccessGateComponent],
  templateUrl: './app.component.html',
  changeDetection: ChangeDetectionStrategy.Eager,
  styleUrl: './app.component.scss'
})
export class AppComponent {
  title = 'Public Comment Analyzer';

  demoMode: boolean | null = null;
  configurationUnavailable = false;

  constructor(public authService: AuthService, http: HttpClient, cdr: ChangeDetectorRef) {
    http.get<{ demoMode: boolean }>(`${environment.apiBaseUrl}/config`).subscribe({
      next: config => { this.demoMode = config.demoMode; cdr.markForCheck(); },
      error: () => { this.configurationUnavailable = true; cdr.markForCheck(); }
    });
  }
}
