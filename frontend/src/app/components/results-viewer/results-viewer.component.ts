import { Component, Input, OnInit, OnDestroy, ViewChildren, QueryList, ElementRef } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { Router } from '@angular/router';
import { MatCardModule } from '@angular/material/card';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { MatSnackBar, MatSnackBarModule } from '@angular/material/snack-bar';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { DomSanitizer, SafeHtml } from '@angular/platform-browser';
import { ResultsService, ResultsResponse } from '../../services/results.service';
import { DashboardService, ChartDefinition, DashboardResponse } from '../../services/dashboard.service';
import { marked } from 'marked';
import { Chart, registerables } from 'chart.js';

Chart.register(...registerables);

@Component({
  selector: 'app-results-viewer',
  imports: [
    CommonModule,
    FormsModule,
    MatCardModule,
    MatButtonModule,
    MatIconModule,
    MatSnackBarModule,
    MatProgressSpinnerModule,
    MatFormFieldModule,
    MatInputModule
  ],
  templateUrl: './results-viewer.component.html',
  styleUrl: './results-viewer.component.scss'
})
export class ResultsViewerComponent implements OnInit, OnDestroy {
  @Input() jobId: string = '';
  @ViewChildren('chartCanvas') chartCanvases!: QueryList<ElementRef<HTMLCanvasElement>>;
  
  results: ResultsResponse | null = null;
  isLoading: boolean = false;
  error: string | null = null;
  renderedAnalysis: SafeHtml = '';
  private analysisRetryTimer: any = null;
  private analysisRetryCount: number = 0;
  private readonly MAX_ANALYSIS_RETRIES = 60;

  // Dashboard state
  dashboardPrompt: string = '';
  dashboardCharts: ChartDefinition[] = [];
  dashboardNarrative: SafeHtml = '';
  dashboardRawNarrative: string = '';
  isDashboardLoading: boolean = false;
  dashboardError: string | null = null;
  private chartInstances: Chart[] = [];

  constructor(
    private resultsService: ResultsService,
    private dashboardService: DashboardService,
    private snackBar: MatSnackBar,
    private sanitizer: DomSanitizer,
    private router: Router
  ) {
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
    this.destroyCharts();
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
          this.dashboardNarrative = this.sanitizer.sanitize(1, html) || '';
        }
        this.isDashboardLoading = false;

        // Render charts after Angular updates the DOM
        setTimeout(() => this.renderCharts(), 100);
      },
      error: (err) => {
        console.error('Dashboard generation failed:', err);
        this.dashboardError = err.error?.error?.message || 'Failed to generate dashboard. Please try again.';
        this.isDashboardLoading = false;
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
