import { ComponentFixture, TestBed, fakeAsync, tick } from '@angular/core/testing';
import { BrowserAnimationsModule } from '@angular/platform-browser/animations';
import { provideRouter } from '@angular/router';
import { of, throwError } from 'rxjs';
import { ProcessingMonitorComponent } from './processing-monitor.component';
import { ProcessingService, JobStatus } from '../../services/processing.service';
import { ResultsService } from '../../services/results.service';

describe('ProcessingMonitorComponent', () => {
  let component: ProcessingMonitorComponent;
  let fixture: ComponentFixture<ProcessingMonitorComponent>;
  let mockProcessingService: jasmine.SpyObj<ProcessingService>;
  let mockResultsService: jasmine.SpyObj<ResultsService>;

  beforeEach(async () => {
    mockProcessingService = jasmine.createSpyObj('ProcessingService', ['pollStatus']);
    mockResultsService = jasmine.createSpyObj('ResultsService', ['getResults']);

    await TestBed.configureTestingModule({
      imports: [
        ProcessingMonitorComponent,
        BrowserAnimationsModule
      ],
      providers: [
        provideRouter([
          { path: 'upload', component: ProcessingMonitorComponent },
          { path: 'processing/:jobId', component: ProcessingMonitorComponent }
        ]),
        { provide: ProcessingService, useValue: mockProcessingService },
        { provide: ResultsService, useValue: mockResultsService }
      ]
    }).compileComponents();

    fixture = TestBed.createComponent(ProcessingMonitorComponent);
    component = fixture.componentInstance;
  });

  it('should create', () => {
    expect(component).toBeTruthy();
  });

  describe('Initialization', () => {
    it('should start polling when jobId is provided', fakeAsync(() => {
      const mockStatus: JobStatus = {
        status: 'pending',
        progress: 0,
        completedRows: 0,
        totalRows: 100
      };
      mockProcessingService.pollStatus.and.returnValue(of(mockStatus));

      component.jobId = 'test-job-123';
      component.ngOnInit();
      tick();

      expect(mockProcessingService.pollStatus).toHaveBeenCalledWith('test-job-123');
      expect(component.jobStatus).toEqual(mockStatus);
    }));

    it('should not start polling when jobId is empty', () => {
      component.jobId = '';
      component.ngOnInit();

      expect(mockProcessingService.pollStatus).not.toHaveBeenCalled();
    });
  });

  describe('Status Updates', () => {
    it('should update status to pending', fakeAsync(() => {
      const mockStatus: JobStatus = {
        status: 'pending',
        progress: 0,
        completedRows: 0,
        totalRows: 100
      };
      mockProcessingService.pollStatus.and.returnValue(of(mockStatus));

      component.jobId = 'test-job';
      component.ngOnInit();
      tick();

      expect(component.currentStep).toBe(0);
      expect(component.isComplete).toBeFalsy();
    }));

    it('should update status to processing', fakeAsync(() => {
      const mockStatus: JobStatus = {
        status: 'processing',
        progress: 50,
        completedRows: 50,
        totalRows: 100
      };
      mockProcessingService.pollStatus.and.returnValue(of(mockStatus));

      component.jobId = 'test-job';
      component.ngOnInit();
      tick();

      expect(component.currentStep).toBe(1);
      expect(component.isComplete).toBeFalsy();
    }));

    it('should update status to completed', async () => {
      const mockStatus: JobStatus = {
        status: 'completed',
        progress: 100,
        completedRows: 100,
        totalRows: 100
      };
      mockProcessingService.pollStatus.and.returnValue(of(mockStatus));
      mockResultsService.getResults.and.returnValue(of({
        downloadUrl: 'https://example.com/file.csv',
        aggregateAnalysis: 'Test analysis'
      }));

      component.jobId = 'test-job';
      component.ngOnInit();
      // Wait for marked.parse() Promise to resolve
      await new Promise(resolve => setTimeout(resolve, 100));

      expect(component.currentStep).toBe(3);
      expect(component.isComplete).toBeTruthy();
    });

    it('should handle failed status', fakeAsync(() => {
      const mockStatus: JobStatus = {
        status: 'failed',
        progress: 30,
        completedRows: 30,
        totalRows: 100,
        error: 'Processing error occurred'
      };
      mockProcessingService.pollStatus.and.returnValue(of(mockStatus));

      component.jobId = 'test-job';
      component.ngOnInit();
      tick();

      expect(component.hasFailed).toBeTruthy();
      expect(component.jobStatus?.error).toBe('Processing error occurred');
    }));
  });

  describe('Progress Calculation', () => {
    it('should calculate progress percentage correctly', fakeAsync(() => {
      const mockStatus: JobStatus = {
        status: 'processing',
        progress: 50,
        completedRows: 50,
        totalRows: 100
      };
      mockProcessingService.pollStatus.and.returnValue(of(mockStatus));

      component.jobId = 'test-job';
      component.ngOnInit();
      tick();

      expect(component.progressPercentage).toBe(50);
    }));

    it('should return 0 when totalRows is 0', () => {
      component.jobStatus = {
        status: 'processing',
        progress: 0,
        completedRows: 0,
        totalRows: 0
      };

      expect(component.progressPercentage).toBe(0);
    });

    it('should return 0 when jobStatus is null', () => {
      component.jobStatus = null;
      expect(component.progressPercentage).toBe(0);
    });

    it('should round progress percentage', fakeAsync(() => {
      const mockStatus: JobStatus = {
        status: 'processing',
        progress: 33.33,
        completedRows: 33,
        totalRows: 100
      };
      mockProcessingService.pollStatus.and.returnValue(of(mockStatus));

      component.jobId = 'test-job';
      component.ngOnInit();
      tick();

      expect(component.progressPercentage).toBe(33);
    }));
  });

  describe('Status Messages', () => {
    it('should show initializing message when no status', () => {
      component.jobStatus = null;
      expect(component.statusMessage).toBe('Initializing...');
    });

    it('should show pending message', () => {
      component.jobStatus = {
        status: 'pending',
        progress: 0,
        completedRows: 0,
        totalRows: 100
      };
      expect(component.statusMessage).toBe('Preparing to process your file...');
    });

    it('should show processing message with row counts', () => {
      component.jobStatus = {
        status: 'processing',
        progress: 50,
        completedRows: 50,
        totalRows: 100
      };
      expect(component.statusMessage).toBe('Processing 50 of 100 rows...');
    });

    it('should show completed message', () => {
      component.jobStatus = {
        status: 'completed',
        progress: 100,
        completedRows: 100,
        totalRows: 100
      };
      expect(component.statusMessage).toBe('Processing complete!');
    });

    it('should show error message when failed', () => {
      component.jobStatus = {
        status: 'failed',
        progress: 30,
        completedRows: 30,
        totalRows: 100,
        error: 'Custom error message'
      };
      expect(component.statusMessage).toBe('Custom error message');
    });

    it('should show default error message when no error provided', () => {
      component.jobStatus = {
        status: 'failed',
        progress: 30,
        completedRows: 30,
        totalRows: 100
      };
      expect(component.statusMessage).toBe('Processing failed. Please try again.');
    });
  });

  describe('Error Handling', () => {
    it('should handle polling errors', fakeAsync(() => {
      mockProcessingService.pollStatus.and.returnValue(
        throwError(() => new Error('Network error'))
      );

      spyOn(console, 'error');
      component.jobId = 'test-job';
      component.ngOnInit();
      tick();

      expect(component.hasFailed).toBeTruthy();
      expect(console.error).toHaveBeenCalled();
    }));
  });

  describe('Cleanup', () => {
    it('should unsubscribe on destroy', fakeAsync(() => {
      const mockStatus: JobStatus = {
        status: 'processing',
        progress: 50,
        completedRows: 50,
        totalRows: 100
      };
      mockProcessingService.pollStatus.and.returnValue(of(mockStatus));

      component.jobId = 'test-job';
      component.ngOnInit();
      tick();

      spyOn(component['destroy$'], 'next');
      spyOn(component['destroy$'], 'complete');

      component.ngOnDestroy();

      expect(component['destroy$'].next).toHaveBeenCalled();
      expect(component['destroy$'].complete).toHaveBeenCalled();
    }));
  });

  describe('Display', () => {
    it('should display completion notification when complete', (done) => {
      const mockStatus: JobStatus = {
        status: 'completed',
        progress: 100,
        completedRows: 100,
        totalRows: 100
      };
      mockProcessingService.pollStatus.and.returnValue(of(mockStatus));
      mockResultsService.getResults.and.returnValue(of({
        downloadUrl: 'https://example.com/file.csv',
        aggregateAnalysis: 'Test analysis'
      }));

      component.jobId = 'test-job';
      fixture.detectChanges(); // Initial change detection
      component.ngOnInit();

      setTimeout(() => {
        fixture.detectChanges();
        fixture.detectChanges(); // Second pass for nested *ngIf updates
        const compiled = fixture.nativeElement;
        expect(component.currentStep).toBe(3);
        expect(compiled.textContent).toContain('Your analysis is ready!');
        done();
      }, 500);
    });

    it('should display progress percentage', fakeAsync(() => {
      const mockStatus: JobStatus = {
        status: 'processing',
        progress: 75,
        completedRows: 75,
        totalRows: 100
      };
      mockProcessingService.pollStatus.and.returnValue(of(mockStatus));

      component.jobId = 'test-job';
      component.ngOnInit();
      tick();
      fixture.detectChanges();

      const compiled = fixture.nativeElement;
      expect(compiled.textContent).toContain('75% complete');
      expect(compiled.textContent).toContain('75 / 100 rows');
    }));
  });
});
