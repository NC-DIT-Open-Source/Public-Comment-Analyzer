import { Injectable } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { BehaviorSubject, Observable, of } from 'rxjs';
import { map, catchError } from 'rxjs/operators';
import { environment } from '../../environments/environment';

const ACCESS_KEY_STORAGE_KEY = 'pca_access_key';

@Injectable({
  providedIn: 'root'
})
export class AuthService {
  private authenticatedSubject = new BehaviorSubject<boolean>(this.hasStoredKey());
  authenticated$ = this.authenticatedSubject.asObservable();

  constructor(private http: HttpClient) {}

  hasStoredKey(): boolean {
    return !!sessionStorage.getItem(ACCESS_KEY_STORAGE_KEY);
  }

  getAccessKey(): string {
    return sessionStorage.getItem(ACCESS_KEY_STORAGE_KEY) || '';
  }

  validate(password: string): Observable<boolean> {
    return this.http.post<{ valid: boolean }>(`${environment.apiBaseUrl}/auth/validate`, { password }).pipe(
      map(res => {
        if (res.valid) {
          sessionStorage.setItem(ACCESS_KEY_STORAGE_KEY, password);
          this.authenticatedSubject.next(true);
        }
        return res.valid;
      }),
      catchError(() => of(false))
    );
  }

  logout(): void {
    sessionStorage.removeItem(ACCESS_KEY_STORAGE_KEY);
    this.authenticatedSubject.next(false);
  }
}
