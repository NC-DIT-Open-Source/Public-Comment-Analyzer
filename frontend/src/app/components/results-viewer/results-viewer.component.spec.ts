import { ComponentFixture, TestBed, fakeAsync, tick } from '@angular/core/testing';
import { BrowserAnimationsModule } from '@angular/platform-browser/animations';
import { provideRouter } from '@angular/router';
import { of, throwError } from 'rxjs';
import { ResultsViewerComponent } from './results-viewer.component';
import { ResultsService, ResultsResponse } from '../../services/results.service';
import { DashboardService } from '../../services/dashboard.service';
import { MatSnackBar } from '@angular/material/snack-bar';

describe('ResultsViewerComponent', () => {
  let component: ResultsViewerComponent;
  let fixture: ComponentFixture<ResultsViewerComponent>;
  let mockResultsService: jasmine.SpyObj<ResultsService>;
  let mockDashboardService: jasmine.SpyObj<DashboardService>;
  let mockSnackBar: jasmine.SpyObj<MatSnackBar>;

  beforeEach(async () => {
    mockResultsService = jasmine.createSpyObj('ResultsService', ['getResults']);
    mockDashboardService = jasmine.createSpyObj('DashboardService', ['generateDashboard']);
    mockSnackBar = jasmine.createSpyObj('MatSnackBar', ['open']);

    await TestBed.configureTestingModule({
      imports: [
        ResultsViewerComponent,
        BrowserAnimationsModule
      ],
      providers: [
        provideRouter([]),
        { provide: ResultsService, useValue: mockResultsService },
        { provide: DashboardService, useValue: mockDashboardService },
        { provide: MatSnackBar, useValue: mockSnackBar }
      ]
    }).compileComponents();

    fixture = TestBed.createComponent(ResultsViewerComponent);
    component = fixture.componentInstance;
  });

  it('should create', () => {
    expect(component).toBeTruthy();
  });

  describe('Initialization', () => {
    it('should load results when jobId is provided', fakeAsync(() => {
      const mockResponse: ResultsResponse = {
        downloadUrl: 'https://example.com/file.csv',
        aggregateAnalysis: 'Test analysis'
      };
      mockResultsService.getResults.and.returnValue(of(mockResponse));

      component.jobId = 'test-job-123';
      component.ngOnInit();
      tick();

      expect(mockResultsService.getResults).toHaveBeenCalledWith('test-job-123');
      expect(component.results).toEqual(mockResponse);
      expect(component.isLoading).toBeFalsy();
    }));

    it('should not load results when jobId is empty', () => {
      component.jobId = '';
      component.ngOnInit();

      expect(mockResultsService.getResults).not.toHaveBeenCalled();
    });
  });

  describe('Loading Results', () => {
    it('should clear loading state after successful fetch', fakeAsync(() => {
      const mockResponse: ResultsResponse = {
        downloadUrl: 'https://example.com/file.csv',
        aggregateAnalysis: 'Test analysis'
      };
      mockResultsService.getResults.and.returnValue(of(mockResponse));

      component.jobId = 'test-job';
      component.loadResults();
      tick();

      expect(component.isLoading).toBeFalsy();
      expect(component.results).toEqual(mockResponse);
      expect(component.error).toBeNull();
    }));

    it('should handle errors when loading results', fakeAsync(() => {
      mockResultsService.getResults.and.returnValue(
        throwError(() => new Error('Network error'))
      );

      spyOn(console, 'error');
      component.jobId = 'test-job';
      component.loadResults();
      tick();

      expect(component.isLoading).toBeFalsy();
      expect(component.error).toBe('Failed to load results. Please try again.');
      expect(console.error).toHaveBeenCalled();
    }));

    it('should clear previous error when retrying', fakeAsync(() => {
      mockResultsService.getResults.and.returnValue(
        throwError(() => new Error('Error'))
      );

      component.jobId = 'test-job';
      component.loadResults();
      tick();

      expect(component.error).toBeTruthy();

      // Retry with success
      mockResultsService.getResults.and.returnValue(of({
        downloadUrl: 'https://example.com/file.csv',
        aggregateAnalysis: 'Analysis'
      }));

      component.loadResults();
      tick();

      expect(component.error).toBeNull();
      expect(component.results).toBeTruthy();
    }));
  });

  describe('Download File', () => {
    it('should open download URL in new tab', () => {
      spyOn(window, 'open');
      component.results = {
        downloadUrl: 'https://example.com/file.csv',
        aggregateAnalysis: 'Analysis'
      };

      component.downloadFile();

      expect(window.open).toHaveBeenCalledWith('https://example.com/file.csv', '_blank');
    });

    it('should not download if no results', () => {
      spyOn(window, 'open');
      component.results = null;

      component.downloadFile();

      expect(window.open).not.toHaveBeenCalled();
    });

    it('should not download if no downloadUrl', () => {
      spyOn(window, 'open');
      component.results = {
        downloadUrl: '',
        aggregateAnalysis: 'Analysis'
      };

      component.downloadFile();

      expect(window.open).not.toHaveBeenCalled();
    });
  });

  describe('Copy Analysis', () => {
    it('should not copy if no results', () => {
      spyOn(navigator.clipboard, 'writeText');
      component.results = null;
      component.copyAnalysis();

      expect(navigator.clipboard.writeText).not.toHaveBeenCalled();
    });

    it('should not copy if no aggregateAnalysis', () => {
      spyOn(navigator.clipboard, 'writeText');
      component.results = {
        downloadUrl: 'https://example.com/file.csv',
        aggregateAnalysis: ''
      };
      component.copyAnalysis();

      expect(navigator.clipboard.writeText).not.toHaveBeenCalled();
    });
  });

  describe('Display', () => {
    it('should display loading state', () => {
      component.isLoading = true;
      fixture.detectChanges();

      const compiled = fixture.nativeElement;
      expect(compiled.textContent).toContain('Loading your results...');
    });

    it('should display error state', fakeAsync(() => {
      mockResultsService.getResults.and.returnValue(
        throwError(() => new Error('any error'))
      );
      spyOn(console, 'error');
      component.jobId = 'test-job';
      fixture.detectChanges();
      tick();
      component.error = 'Test error message';
      component.isLoading = false;
      fixture.detectChanges();

      const compiled = fixture.nativeElement;
      expect(compiled.textContent).toContain('Error Loading Results');
      expect(compiled.textContent).toContain('Test error message');
    }));

    it('should display results when loaded', fakeAsync(() => {
      const mockResponse: ResultsResponse = {
        downloadUrl: 'https://example.com/file.csv',
        aggregateAnalysis: 'This is the aggregate analysis'
      };
      mockResultsService.getResults.and.returnValue(of(mockResponse));

      component.jobId = 'test-job';
      component.ngOnInit();
      tick();
      fixture.detectChanges();
      tick();
      fixture.detectChanges();

      const compiled = fixture.nativeElement;
      expect(compiled.textContent).toContain('Download Processed File');
      expect(compiled.textContent).toContain('Aggregate Analysis');
      expect(compiled.textContent).toContain('This is the aggregate analysis');
    }));
  });
});
