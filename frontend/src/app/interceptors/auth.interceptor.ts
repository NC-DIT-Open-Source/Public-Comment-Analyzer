import { HttpInterceptorFn } from '@angular/common/http';
import { inject } from '@angular/core';
import { tap } from 'rxjs/operators';
import { AuthService } from '../services/auth.service';

const ACCESS_KEY_STORAGE_KEY = 'pca_access_key';

export const authInterceptor: HttpInterceptorFn = (req, next) => {
  const authService = inject(AuthService);
  const accessKey = localStorage.getItem(ACCESS_KEY_STORAGE_KEY);

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
