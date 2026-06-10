import { fakeAsync, TestBed, tick } from '@angular/core/testing';
import { provideHttpClient, withXhr } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';

import { JobStatus, ProcessingService } from './processing.service';

const API = 'http://localhost:3000/api';
const STATUS_URL = (jobId: string) => `${API}/status/${jobId}`;

function statusResponse(overrides: Partial<JobStatus> = {}): JobStatus {
  return {
    status: 'preview_ready',
    progress: 16,
    completedRows: 20,
    totalRows: 125,
    ...overrides
  };
}

describe('ProcessingService.pollStatus', () => {
  let service: ProcessingService;
  let httpMock: HttpTestingController;

  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [
        ProcessingService,
        provideHttpClient(withXhr()),
        provideHttpClientTesting()
      ]
    });
    service = TestBed.inject(ProcessingService);
    httpMock = TestBed.inject(HttpTestingController);
  });

  afterEach(() => httpMock.verify());

  it('does NOT cancel an in-flight request when the next interval fires (regression for OAIP-73)', fakeAsync(() => {
    const emitted: JobStatus[] = [];
    const sub = service.pollStatus('job-1', 100).subscribe(s => emitted.push(s));

    // First request fires immediately via startWith(0)
    const req1 = httpMock.expectOne(STATUS_URL('job-1'));

    // Advance past the next interval tick BEFORE responding to req1.
    // With switchMap this would cancel req1; with concatMap req1 must complete
    // before the next request fires.
    tick(150);

    // req1 is still open — confirm by responding now and seeing it land.
    req1.flush(statusResponse({ status: 'preview_ready' }));

    expect(emitted.length).toBe(1);
    expect(emitted[0].status).toBe('preview_ready');

    // After req1 completes, concatMap immediately emits the queued tick.
    const req2 = httpMock.expectOne(STATUS_URL('job-1'));
    req2.flush(statusResponse({ status: 'completed', progress: 100, completedRows: 125 }));

    expect(emitted.length).toBe(2);
    expect(emitted[1].status).toBe('completed');

    sub.unsubscribe();
  }));

  it('stops polling once a terminal status arrives', fakeAsync(() => {
    const emitted: JobStatus[] = [];
    const sub = service.pollStatus('job-2', 100).subscribe(s => emitted.push(s));

    httpMock.expectOne(STATUS_URL('job-2')).flush(statusResponse({ status: 'completed', progress: 100 }));

    // Advance several intervals — no further requests should fire.
    tick(500);
    httpMock.expectNone(STATUS_URL('job-2'));

    expect(emitted.length).toBe(1);
    expect(emitted[0].status).toBe('completed');

    sub.unsubscribe();
  }));

  it('keeps polling through preview_ready (non-terminal — user must confirm)', fakeAsync(() => {
    const emitted: JobStatus[] = [];
    const sub = service.pollStatus('job-3', 100).subscribe(s => emitted.push(s));

    httpMock.expectOne(STATUS_URL('job-3')).flush(statusResponse({ status: 'preview_ready' }));
    tick(100);

    // A second poll must fire after preview_ready.
    httpMock.expectOne(STATUS_URL('job-3')).flush(statusResponse({ status: 'processing', progress: 50, completedRows: 62 }));

    expect(emitted.length).toBe(2);
    expect(emitted[0].status).toBe('preview_ready');
    expect(emitted[1].status).toBe('processing');

    sub.unsubscribe();
  }));
});
