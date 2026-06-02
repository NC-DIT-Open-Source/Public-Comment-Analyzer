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

    authServiceSpy = jasmine.createSpyObj<AuthService>('AuthService', ['logout', 'getAccessKey']);
    authServiceSpy.getAccessKey.and.returnValue('');

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

  it('attaches X-Access-Key from AuthService on protected requests', () => {
    authServiceSpy.getAccessKey.and.returnValue('session-password');

    http.get(`${API}/upload`).subscribe();
    const req = httpMock.expectOne(`${API}/upload`);

    expect(req.request.headers.get('X-Access-Key')).toBe('session-password');
    req.flush({});
  });

  it('does NOT attach X-Access-Key when AuthService has no key', () => {
    http.get(`${API}/upload`).subscribe();
    const req = httpMock.expectOne(`${API}/upload`);

    expect(req.request.headers.has('X-Access-Key')).toBeFalse();
    req.flush({});
  });

  it('does NOT read the access key from web storage — AuthService is the only source', () => {
    // The access key must never be sourced from sessionStorage/localStorage.
    // Even when both contain a value, nothing is attached unless AuthService
    // (in-memory) returns it. This guards against regressing back to a
    // web-storage-backed credential (CodeQL js/clear-text-storage-of-sensitive-data).
    sessionStorage.setItem(STORAGE_KEY, 'leaked-from-sessionstorage');
    localStorage.setItem(STORAGE_KEY, 'leaked-from-localstorage');

    http.get(`${API}/upload`).subscribe();
    const req = httpMock.expectOne(`${API}/upload`);

    expect(req.request.headers.has('X-Access-Key')).toBeFalse();
    req.flush({});
  });

  it('does NOT attach X-Access-Key on /auth/validate even when a key is set', () => {
    authServiceSpy.getAccessKey.and.returnValue('session-password');

    http.post(`${API}/auth/validate`, { password: 'foo' }).subscribe();
    const req = httpMock.expectOne(`${API}/auth/validate`);

    expect(req.request.headers.has('X-Access-Key')).toBeFalse();
    req.flush({ valid: true });
  });

  it('calls AuthService.logout() when a protected request returns 401', () => {
    authServiceSpy.getAccessKey.and.returnValue('session-password');

    http.get(`${API}/upload`).subscribe({
      next: () => fail('expected 401 error'),
      error: () => undefined
    });
    const req = httpMock.expectOne(`${API}/upload`);
    req.flush({ error: 'Unauthorized' }, { status: 401, statusText: 'Unauthorized' });

    expect(authServiceSpy.logout).toHaveBeenCalledTimes(1);
  });
});
