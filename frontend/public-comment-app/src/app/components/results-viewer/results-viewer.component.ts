import { Component, Input, OnInit, OnDestroy } from '@angular/core';
import { CommonModule } from '@angular/common';
import { Router } from '@angular/router';
import { MatCardModule } from '@angular/material/card';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { MatSnackBar, MatSnackBarModule } from '@angular/material/snack-bar';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { DomSanitizer, SafeHtml } from '@angular/platform-browser';
import { ResultsService, ResultsResponse } from '../../services/results.service';
import { marked } from 'marked';

@Component({
  selector: 'app-results-viewer',
  standalone: true,
  imports: [
    CommonModule,
    MatCardModule,
    MatButtonModule,
    MatIconModule,
    MatSnackBarModule,
    MatProgressSpinnerModule
  ],
  templateUrl: './results-viewer.component.html',
  styleUrl: './results-viewer.component.scss'
})
export class ResultsViewerComponent implements OnInit, OnDestroy {
  @Input() jobId: string = '';
  
  results: ResultsResponse | null = null;
  isLoading: boolean = false;
  error: string | null = null;
  renderedAnalysis: SafeHtml = '';
  private analysisRetryTimer: any = null;
  private analysisRetryCount: number = 0;
  private readonly MAX_ANALYSIS_RETRIES = 60;

  constructor(
    private resultsService: ResultsService,
    private snackBar: MatSnackBar,
    private sanitizer: DomSanitizer,
    private router: Router
  ) {
    // Get jobId from navigation state
    const navigation = this.router.getCurrentNavigation();
    if (navigation?.extras.state) {
      this.jobId = navigation.extras.state['jobId'] || '';
    }
  }

  ngOnInit(): void {
    console.log('ResultsViewerComponent ngOnInit, jobId:', this.jobId);
    
    // Also check history.state if not set from navigation
    if (!this.jobId) {
      const state = history.state;
      if (state && state.jobId) {
        console.log('Found jobId in history.state:', state.jobId);
        this.jobId = state.jobId;
      }
    }
    
    if (this.jobId) {
      console.log('Loading results for jobId:', this.jobId);
      this.loadResults();
    } else {
      console.error('No jobId found, cannot load results');
      this.error = 'No job ID provided. Please start from the upload page.';
    }
  }

  ngOnDestroy(): void {
    if (this.analysisRetryTimer) {
      clearTimeout(this.analysisRetryTimer);
    }
  }

  async loadResults(): Promise<void> {
    this.isLoading = true;
    this.error = null;

    this.resultsService.getResults(this.jobId).subscribe({
      next: async (response) => {
        this.results = response;
        if (response.aggregateAnalysis) {
          // Render markdown to HTML
          const html = await marked.parse(response.aggregateAnalysis);
          this.renderedAnalysis = this.sanitizer.sanitize(1, html) || '';
          this.isLoading = false;
          this.analysisRetryCount = 0;
        } else if (response.analysisStatus === 'generating') {
          this.analysisRetryCount++;
          if (this.analysisRetryCount >= this.MAX_ANALYSIS_RETRIES) {
            this.isLoading = false;
            this.error = 'Aggregate analysis is taking longer than expected. Your processed file is still available for download.';
          } else {
            this.analysisRetryTimer = setTimeout(() => this.loadResults(), 5000);
          }
        } else {
          this.isLoading = false;
        }
      },
      error: (err) => {
        console.error('Error loading results:', err);
        this.error = 'Failed to load results. Please try again.';
        this.isLoading = false;
      }
    });
  }

  downloadFile(): void {
    if (this.results?.downloadUrl) {
      window.open(this.results.downloadUrl, '_blank');
      this.snackBar.open('Download started', 'Close', {
        duration: 3000
      });
    }
  }

  copyAnalysis(): void {
    if (this.results?.aggregateAnalysis) {
      navigator.clipboard.writeText(this.results.aggregateAnalysis).then(() => {
        this.snackBar.open('Analysis copied to clipboard', 'Close', {
          duration: 3000
        });
      }).catch(err => {
        console.error('Failed to copy:', err);
        this.snackBar.open('Failed to copy to clipboard', 'Close', {
          duration: 3000
        });
      });
    }
  }
}
