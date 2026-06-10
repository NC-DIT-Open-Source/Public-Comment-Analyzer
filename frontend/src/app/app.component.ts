import { Component, ChangeDetectionStrategy } from '@angular/core';
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

  constructor(public authService: AuthService) {}
}
