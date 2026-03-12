import { Component, Input, OnInit, OnDestroy, ViewEncapsulation, ChangeDetectorRef, ViewChildren, QueryList, ElementRef } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { Router, ActivatedRoute } from '@angular/router';
import { MatStepperModule } from '@angular/material/stepper';
import { MatProgressBarModule } from '@angular/material/progress-bar';
import { MatCardModule } from '@angular/material/card';
import { MatIconModule } from '@angular/material/icon';
import { MatButtonModule } from '@angular/material/button';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { MatSnackBar, MatSnackBarModule } from '@angular/material/snack-bar';
import { DomSanitizer, SafeHtml } from '@angular/platform-browser';
import { ProcessingService, JobStatus } from '../../services/processing.service';
import { ResultsService, ResultsResponse } from '../../services/results.service';
import { DashboardService, ChartDefinition, DashboardResponse } from '../../services/dashboard.service';
import { Subject, takeUntil } from 'rxjs';
import { marked } from 'marked';
import { Chart, registerables } from 'chart.js';

Chart.register(...registerables);

@Component({
  selector: 'app-processing-monitor',
  imports: [
    CommonModule,
    FormsModule,
    MatStepperModule,
    MatProgressBarModule,
    MatCardModule,
    MatIconModule,
    MatButtonModule,
    MatProgressSpinnerModule,
    MatFormFieldModule,
    MatInputModule,
    MatSnackBarModule
  ],
  templateUrl: './processing-monitor.component.html',
  styleUrl: './processing-monitor.component.scss',
  encapsulation: ViewEncapsulation.None
})
export class ProcessingMonitorComponent implements OnInit, OnDestroy {
  @Input() jobId: string = '';
  @ViewChildren('chartCanvas') chartCanvases!: QueryList<ElementRef<HTMLCanvasElement>>;

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

  // Dashboard state
  dashboardPrompt: string = '';
  dashboardCharts: ChartDefinition[] = [];
  dashboardNarrative: SafeHtml = '';
  dashboardRawNarrative: string = '';
  isDashboardLoading: boolean = false;
  dashboardError: string | null = null;
  private chartInstances: Chart[] = [];

  constructor(
    private processingService: ProcessingService,
    private resultsService: ResultsService,
    private dashboardService: DashboardService,
    private router: Router,
    private route: ActivatedRoute,
    private sanitizer: DomSanitizer,
    private cdr: ChangeDetectorRef,
    private snackBar: MatSnackBar
  ) {
    const navigation = this.router.getCurrentNavigation();
    if (navigation?.extras.state) {
      this.jobId = navigation.extras.state['jobId'] || '';
    }
  }

  ngOnInit(): void {
    // If jobId is already set (e.g., in tests), start polling immediately
    if (this.jobId) {
      this.startPolling();
      return;
    }

    // Get jobId from route parameter first, then fall back to state
    this.route.paramMap.pipe(takeUntil(this.destroy$)).subscribe(params => {
      const jobIdFromRoute = params.get('jobId');
      if (jobIdFromRoute) {
        this.jobId = jobIdFromRoute;
        this.startPolling();
      } else {
        // Fall back to history state
        const state = history.state;
        if (state && state.jobId) {
          this.jobId = state.jobId;
          this.startPolling();
        } else {
          // No jobId found, redirect to upload
          this.router.navigate(['/upload']);
        }
      }
    });
  }

  ngOnDestroy(): void {
    this.destroy$.next();
    this.destroy$.complete();
    if (this.analysisRetryTimer) {
      clearTimeout(this.analysisRetryTimer);
    }
    this.destroyCharts();
  }

  startPolling(): void {
    this.processingService.pollStatus(this.jobId)
      .pipe(takeUntil(this.destroy$))
      .subscribe({
        next: (status) => {
          console.log('Received status:', status);
          this.jobStatus = status;
          this.updateStepFromStatus(status);

          if (status.status === 'completed') {
            if (!this.isComplete) {
              console.log('Setting isComplete to true and loading results');
              this.isComplete = true;
              this.currentStep = 3;
              this.cdr.detectChanges(); // Force change detection
              this.loadResults();
            }
          } else if (status.status === 'failed') {
            this.hasFailed = true;
            this.cdr.detectChanges(); // Force change detection
          }
        },
        error: (error) => {
          console.error('Error polling job status:', error);
          this.hasFailed = true;
          this.cdr.detectChanges(); // Force change detection
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
    this.cdr.detectChanges(); // Force change detection

    this.resultsService.getResults(this.jobId).subscribe({
      next: async (response) => {
        this.results = response;
        if (response.aggregateAnalysis) {
          const html = await marked.parse(response.aggregateAnalysis);
          this.renderedAnalysis = this.sanitizer.bypassSecurityTrustHtml(html);
          this.isLoadingResults = false;
          this.analysisRetryCount = 0;
          this.cdr.detectChanges(); // Force change detection
        } else if (response.analysisStatus === 'generating') {
          this.analysisRetryCount++;
          if (this.analysisRetryCount >= this.MAX_ANALYSIS_RETRIES) {
            this.isLoadingResults = false;
            this.resultsError = 'Aggregate analysis is taking longer than expected. Your processed file is still available for download. You can retry the analysis or download your results now.';
            this.cdr.detectChanges(); // Force change detection
          } else {
            this.analysisRetryTimer = setTimeout(() => this.loadResults(), 5000);
          }
        } else {
          this.isLoadingResults = false;
          this.cdr.detectChanges(); // Force change detection
        }
      },
      error: (err) => {
        console.error('Error loading results:', err);
        this.resultsError = 'Failed to load results. Please try again.';
        this.isLoadingResults = false;
        this.cdr.detectChanges(); // Force change detection
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

  async generateDashboard(): Promise<void> {
    if (!this.dashboardPrompt.trim() || !this.jobId) return;

    this.isDashboardLoading = true;
    this.dashboardError = null;
    this.destroyCharts();

    this.dashboardService.generateDashboard(this.jobId, this.dashboardPrompt).subscribe({
      next: async (response: DashboardResponse) => {
        this.dashboardCharts = response.charts || [];
        this.dashboardRawNarrative = response.narrative || '';
        if (this.dashboardRawNarrative) {
          const html = await marked.parse(this.dashboardRawNarrative);
          this.dashboardNarrative = this.sanitizer.bypassSecurityTrustHtml(html);
        }
        this.isDashboardLoading = false;
        this.cdr.detectChanges();

        // Render charts after Angular updates the DOM
        setTimeout(() => this.renderCharts(), 100);
      },
      error: (err) => {
        console.error('Dashboard generation failed:', err);
        this.dashboardError = err.error?.error?.message || 'Failed to generate dashboard. Please try again.';
        this.isDashboardLoading = false;
        this.cdr.detectChanges();
      }
    });
  }

  private renderCharts(): void {
    this.destroyCharts();
    const canvases = this.chartCanvases?.toArray() || [];
    
    canvases.forEach((canvasRef, index) => {
      if (index < this.dashboardCharts.length) {
        const chartDef = this.dashboardCharts[index];
        const ctx = canvasRef.nativeElement.getContext('2d');
        if (ctx && chartDef.config) {
          try {
            const config = { ...chartDef.config };
            // Ensure responsive
            if (!config.options) config.options = {};
            config.options.responsive = true;
            config.options.maintainAspectRatio = false;
            
            const chart = new Chart(ctx, config);
            this.chartInstances.push(chart);
          } catch (e) {
            console.error(`Failed to render chart ${index}:`, e);
          }
        }
      }
    });
  }

  private destroyCharts(): void {
    this.chartInstances.forEach(c => c.destroy());
    this.chartInstances = [];
  }

  copyDashboardNarrative(): void {
    if (this.dashboardRawNarrative) {
      navigator.clipboard.writeText(this.dashboardRawNarrative).then(() => {
        this.snackBar.open('Dashboard narrative copied to clipboard', 'Close', { duration: 3000 });
      });
    }
  }
}
