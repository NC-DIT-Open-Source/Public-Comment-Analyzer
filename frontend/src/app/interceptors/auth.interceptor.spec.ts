import { HttpClient, provideHttpClient, withInterceptors } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';

import { authInterceptor } from './auth.interceptor';
import { AuthService } from '../services/auth.service';

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
    // Guard against regressing to a web-storage-backed credential
    // (CodeQL js/clear-text-storage-of-sensitive-data / Checkmarx CWE-922).
    // We prove the interceptor never consults web storage by spying on the
    // storage *reads* — and we deliberately never write a credential to storage,
    // so this test introduces no insecure-storage sink of its own.
    const getItemSpy = spyOn(Storage.prototype, 'getItem').and.callThrough();

    http.get(`${API}/upload`).subscribe();
    const req = httpMock.expectOne(`${API}/upload`);

    expect(req.request.headers.has('X-Access-Key')).toBeFalse();
    expect(getItemSpy).not.toHaveBeenCalled();
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
