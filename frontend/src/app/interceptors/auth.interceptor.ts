import { HttpInterceptorFn } from '@angular/common/http';
import { inject } from '@angular/core';
import { tap } from 'rxjs/operators';
import { AuthService } from '../services/auth.service';

export const authInterceptor: HttpInterceptorFn = (req, next) => {
  const authService = inject(AuthService);
  // AuthService holds the access key in memory only — it is the single source of
  // truth. The interceptor never reads web storage directly.
  const accessKey = authService.getAccessKey();

  // Don't attach the key to the auth/validate call itself
  if (accessKey && !req.url.includes('/auth/validate')) {
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
