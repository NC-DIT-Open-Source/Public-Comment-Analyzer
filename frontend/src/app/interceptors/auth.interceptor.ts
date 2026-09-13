import { HttpInterceptorFn } from '@angular/common/http';
import { inject } from '@angular/core';
import { tap } from 'rxjs/operators';
import { environment } from '../../environments/environment';
import { AuthService } from '../services/auth.service';

export const authInterceptor: HttpInterceptorFn = (req, next) => {
  const authService = inject(AuthService);
  // AuthService holds the access key in memory only — it is the single source of
  // truth. The interceptor never reads web storage directly.
  const accessKey = authService.getAccessKey();

  // Credentials only travel to this deployment's API, never arbitrary URLs.
  const api = new URL(environment.apiBaseUrl + '/', window.location.origin);
  const target = new URL(req.url, window.location.origin);
  const protectedApi = target.origin === api.origin && target.pathname.startsWith(api.pathname)
    && target.pathname !== api.pathname + 'auth/validate' && target.pathname !== api.pathname + 'config';
  if (accessKey && protectedApi) {
    const cloned = req.clone({
      setHeaders: { 'X-Access-Key': accessKey }
    });
    return next(cloned).pipe(
      tap({
        error: (err) => {
          if (err.status === 401) {
            authService.logout();
          }
        }
      })
    );
  }

  return next(req);
};
