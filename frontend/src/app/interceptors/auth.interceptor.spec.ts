import { HttpClient, provideHttpClient, withInterceptors } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';

import { authInterceptor } from './auth.interceptor';
import { AuthService } from '../services/auth.service';

const STORAGE_KEY = 'pca_access_key';
const API = 'http://localhost:3000/api';

describe('authInterceptor', () => {
  let http: HttpClient;
  let httpMock: HttpTestingController;
  let authServiceSpy: jasmine.SpyObj<AuthService>;

  beforeEach(() => {
    sessionStorage.clear();
    localStorage.clear();

    authServiceSpy = jasmine.createSpyObj<AuthService>('AuthService', ['logout']);

    TestBed.configureTestingModule({
      providers: [
        provideHttpClient(withInterceptors([authInterceptor])),
        provideHttpClientTesting(),
        { provide: AuthService, useValue: authServiceSpy }
      ]
    });

    http = TestBed.inject(HttpClient);
    httpMock = TestBed.inject(HttpTestingController);
  });

  afterEach(() => {
    httpMock.verify();
    sessionStorage.clear();
    localStorage.clear();
  });

  it('attaches X-Access-Key from sessionStorage on protected requests', () => {
    sessionStorage.setItem(STORAGE_KEY, 'session-password');

    http.get(`${API}/upload`).subscribe();
    const req = httpMock.expectOne(`${API}/upload`);

    expect(req.request.headers.get('X-Access-Key')).toBe('session-password');
    req.flush({});
  });

  it('does NOT attach X-Access-Key when sessionStorage is empty', () => {
    http.get(`${API}/upload`).subscribe();
    const req = httpMock.expectOne(`${API}/upload`);

    expect(req.request.headers.has('X-Access-Key')).toBeFalse();
    req.flush({});
  });

  it('does NOT read from localStorage (storage source is pinned to sessionStorage)', () => {
    // A localStorage value must not leak into the header. This guards against
    // regressing commit d3bc1df, which moved auth.service.ts to sessionStorage
    // but left the interceptor reading localStorage.
    localStorage.setItem(STORAGE_KEY, 'leaked-from-localstorage');

    http.get(`${API}/upload`).subscribe();
    const req = httpMock.expectOne(`${API}/upload`);

    expect(req.request.headers.has('X-Access-Key')).toBeFalse();
    req.flush({});
  });

  it('does NOT attach X-Access-Key on /auth/validate even with sessionStorage set', () => {
    sessionStorage.setItem(STORAGE_KEY, 'session-password');

    http.post(`${API}/auth/validate`, { password: 'foo' }).subscribe();
    const req = httpMock.expectOne(`${API}/auth/validate`);

    expect(req.request.headers.has('X-Access-Key')).toBeFalse();
    req.flush({ valid: true });
  });

  it('calls AuthService.logout() when a protected request returns 401', () => {
    sessionStorage.setItem(STORAGE_KEY, 'session-password');

    http.get(`${API}/upload`).subscribe({
      next: () => fail('expected 401 error'),
      error: () => undefined
    });
    const req = httpMock.expectOne(`${API}/upload`);
    req.flush({ error: 'Unauthorized' }, { status: 401, statusText: 'Unauthorized' });

    expect(authServiceSpy.logout).toHaveBeenCalledTimes(1);
  });
});
