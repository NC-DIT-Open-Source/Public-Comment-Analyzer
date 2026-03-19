import { Routes } from '@angular/router';

export const routes: Routes = [
  { path: '', redirectTo: '/upload', pathMatch: 'full' },
  { path: 'upload', loadComponent: () => import('./components/file-upload/file-upload.component').then(m => m.FileUploadComponent) },
  { path: 'define-columns', loadComponent: () => import('./components/column-definition/column-definition.component').then(m => m.ColumnDefinitionComponent) },
  { path: 'processing/:jobId', loadComponent: () => import('./components/processing-monitor/processing-monitor.component').then(m => m.ProcessingMonitorComponent) },
  { path: 'results', loadComponent: () => import('./components/results-viewer/results-viewer.component').then(m => m.ResultsViewerComponent) }
];
