import { Injectable } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { BehaviorSubject, Observable, of } from 'rxjs';
import { map, catchError } from 'rxjs/operators';
import { environment } from '../../environments/environment';

@Injectable({
  providedIn: 'root'
})
export class AuthService {
  // The shared access key is held in memory only on this root-scoped singleton.
  // It is deliberately NOT persisted to sessionStorage/localStorage so the
  // credential never lands in any JS-readable web storage. The trade-off is that
  // a full page reload clears it and the access gate is shown again — acceptable
  // because job state is not persisted across reloads either.
  private accessKey: string | null = null;

  private authenticatedSubject = new BehaviorSubject<boolean>(this.hasStoredKey());
  authenticated$ = this.authenticatedSubject.asObservable();

  constructor(private http: HttpClient) {}

  hasStoredKey(): boolean {
    return !!this.accessKey;
  }

  getAccessKey(): string {
    return this.accessKey ?? '';
  }

  validate(password: string): Observable<boolean> {
    return this.http.post<{ valid: boolean }>(`${environment.apiBaseUrl}/auth/validate`, { password }).pipe(
      map(res => {
        if (res.valid) {
          this.accessKey = password;
          this.authenticatedSubject.next(true);
        }
        return res.valid;
      }),
      catchError(() => of(false))
    );
  }

  logout(): void {
    this.accessKey = null;
    this.authenticatedSubject.next(false);
  }
}
