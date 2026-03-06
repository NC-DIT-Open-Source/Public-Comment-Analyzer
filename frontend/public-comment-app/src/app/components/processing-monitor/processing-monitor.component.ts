import { Component, Input, OnInit, OnDestroy, ViewEncapsulation } from '@angular/core';
import { CommonModule } from '@angular/common';
import { Router } from '@angular/router';
import { MatStepperModule } from '@angular/material/stepper';
import { MatProgressBarModule } from '@angular/material/progress-bar';
import { MatCardModule } from '@angular/material/card';
import { MatIconModule } from '@angular/material/icon';
import { MatButtonModule } from '@angular/material/button';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { DomSanitizer, SafeHtml } from '@angular/platform-browser';
import { ProcessingService, JobStatus } from '../../services/processing.service';
import { ResultsService, ResultsResponse } from '../../services/results.service';
import { Subject, takeUntil } from 'rxjs';
import { marked } from 'marked';

@Component({
  selector: 'app-processing-monitor',
  standalone: true,
  imports: [
    CommonModule,
    MatStepperModule,
    MatProgressBarModule,
    MatCardModule,
    MatIconModule,
    MatButtonModule,
    MatProgressSpinnerModule
  ],
  templateUrl: './processing-monitor.component.html',
  styleUrl: './processing-monitor.component.scss',
  encapsulation: ViewEncapsulation.None
})
export class ProcessingMonitorComponent implements OnInit, OnDestroy {
  @Input() jobId: string = '';

  jobStatus: JobStatus | null = null;
  currentStep: number = 0;
  isComplete: boolean = false;
  hasFailed: boolean = false;
  private destroy$ = new Subject<void>();

  // Results
  results: ResultsResponse | null = null;
  renderedAnalysis: SafeHtml = '';
  isLoadingResults: boolean = false;
  resultsError: string | null = null;
  private analysisRetryTimer: any = null;
  private analysisRetryCount: number = 0;
  private readonly MAX_ANALYSIS_RETRIES = 60; // 60 retries * 5s = 5 minutes max wait

  constructor(
    private processingService: ProcessingService,
    private resultsService: ResultsService,
    private router: Router,
    private sanitizer: DomSanitizer
  ) {
    const navigation = this.router.getCurrentNavigation();
    if (navigation?.extras.state) {
      this.jobId = navigation.extras.state['jobId'] || '';
    }
  }

  ngOnInit(): void {
    if (!this.jobId) {
      const state = history.state;
      if (state && state.jobId) {
        this.jobId = state.jobId;
      }
    }

    if (this.jobId) {
      this.startPolling();
    }
  }

  ngOnDestroy(): void {
    this.destroy$.next();
    this.destroy$.complete();
    if (this.analysisRetryTimer) {
      clearTimeout(this.analysisRetryTimer);
    }
  }

  startPolling(): void {
    this.processingService.pollStatus(this.jobId)
      .pipe(takeUntil(this.destroy$))
      .subscribe({
        next: (status) => {
          this.jobStatus = status;
          this.updateStepFromStatus(status);

          if (status.status === 'completed' && !this.isComplete) {
            this.isComplete = true;
            this.currentStep = 3;
            this.loadResults();
          } else if (status.status === 'failed') {
            this.hasFailed = true;
          }
        },
        error: (error) => {
          console.error('Error polling job status:', error);
          this.hasFailed = true;
        }
      });
  }

  private updateStepFromStatus(status: JobStatus): void {
    switch (status.status) {
      case 'pending': this.currentStep = 0; break;
      case 'processing': this.currentStep = 1; break;
      case 'completed': this.currentStep = 3; break;
      case 'failed': this.currentStep = 1; break;
    }
  }

  async loadResults(): Promise<void> {
    this.isLoadingResults = true;
    this.resultsError = null;

    this.resultsService.getResults(this.jobId).subscribe({
      next: async (response) => {
        this.results = response;
        if (response.aggregateAnalysis) {
          const html = await marked.parse(response.aggregateAnalysis);
          this.renderedAnalysis = this.sanitizer.bypassSecurityTrustHtml(html);
          this.isLoadingResults = false;
          this.analysisRetryCount = 0;
        } else if (response.analysisStatus === 'generating') {
          this.analysisRetryCount++;
          if (this.analysisRetryCount >= this.MAX_ANALYSIS_RETRIES) {
            this.isLoadingResults = false;
            this.resultsError = 'Aggregate analysis is taking longer than expected. Your processed file is still available for download. You can retry the analysis or download your results now.';
          } else {
            this.analysisRetryTimer = setTimeout(() => this.loadResults(), 5000);
          }
        } else {
          this.isLoadingResults = false;
        }
      },
      error: (err) => {
        console.error('Error loading results:', err);
        this.resultsError = 'Failed to load results. Please try again.';
        this.isLoadingResults = false;
      }
    });
  }

  downloadResults(): void {
    if (this.results?.downloadUrl) {
      window.open(this.results.downloadUrl, '_blank');
    }
  }

  retryResults(): void {
    this.analysisRetryCount = 0;
    this.loadResults();
  }

  get progressPercentage(): number {
    if (!this.jobStatus || this.jobStatus.totalRows === 0) return 0;
    return Math.round((this.jobStatus.completedRows / this.jobStatus.totalRows) * 100);
  }

  get statusMessage(): string {
    if (!this.jobStatus) return 'Initializing...';
    switch (this.jobStatus.status) {
      case 'pending': return 'Preparing to process your file...';
      case 'processing': return `Processing ${this.jobStatus.completedRows} of ${this.jobStatus.totalRows} rows...`;
      case 'completed': return 'Processing complete!';
      case 'failed': return this.jobStatus.error || 'Processing failed. Please try again.';
      default: return 'Unknown status';
    }
  }
}
