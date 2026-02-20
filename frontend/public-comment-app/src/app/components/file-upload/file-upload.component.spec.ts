import { ComponentFixture, TestBed } from '@angular/core/testing';
import { HttpClientTestingModule } from '@angular/common/http/testing';
import { FileUploadComponent } from './file-upload.component';
import { FileUploadService } from '../../services/file-upload.service';
import { of, throwError } from 'rxjs';

describe('FileUploadComponent', () => {
  let component: FileUploadComponent;
  let fixture: ComponentFixture<FileUploadComponent>;
  let fileUploadService: jasmine.SpyObj<FileUploadService>;

  beforeEach(async () => {
    const fileUploadServiceSpy = jasmine.createSpyObj('FileUploadService', ['uploadFile']);

    await TestBed.configureTestingModule({
      imports: [FileUploadComponent, HttpClientTestingModule],
      providers: [
        { provide: FileUploadService, useValue: fileUploadServiceSpy }
      ]
    }).compileComponents();

    fileUploadService = TestBed.inject(FileUploadService) as jasmine.SpyObj<FileUploadService>;
    fixture = TestBed.createComponent(FileUploadComponent);
    component = fixture.componentInstance;
    fixture.detectChanges();
  });

  it('should create', () => {
    expect(component).toBeTruthy();
  });

  it('should validate file format and reject invalid files', () => {
    const invalidFile = new File(['content'], 'test.txt', { type: 'text/plain' });
    component['handleFile'](invalidFile);
    
    expect(component.errorMessage).toContain('Invalid file format');
    expect(component.selectedFile).toBeNull();
  });

  it('should accept valid CSV file', () => {
    const validFile = new File(['content'], 'test.csv', { type: 'text/csv' });
    fileUploadService.uploadFile.and.returnValue(of({
      fileId: '123',
      columns: ['col1', 'col2'],
      rowCount: 10
    }));

    component['handleFile'](validFile);
    
    expect(component.selectedFile).toBe(validFile);
    expect(component.errorMessage).toBeNull();
  });

  it('should accept valid XLSX file', () => {
    const validFile = new File(['content'], 'test.xlsx', { 
      type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' 
    });
    fileUploadService.uploadFile.and.returnValue(of({
      fileId: '123',
      columns: ['col1', 'col2'],
      rowCount: 10
    }));

    component['handleFile'](validFile);
    
    expect(component.selectedFile).toBe(validFile);
    expect(component.errorMessage).toBeNull();
  });

  it('should display error message on upload failure', async () => {
    const validFile = new File(['content'], 'test.csv', { type: 'text/csv' });
    const errorResponse = { error: { message: 'Upload failed' } };
    fileUploadService.uploadFile.and.returnValue(throwError(() => errorResponse));

    component['handleFile'](validFile);
    
    // Wait for async operation
    await fixture.whenStable();
    expect(component.errorMessage).toBe('Upload failed');
    expect(component.selectedFile).toBeNull();
  });

  it('should emit fileUploaded event on successful upload', (done) => {
    const validFile = new File(['content'], 'test.csv', { type: 'text/csv' });
    const metadata = {
      fileId: '123',
      columns: ['col1', 'col2'],
      rowCount: 10
    };
    fileUploadService.uploadFile.and.returnValue(of(metadata));

    component.fileUploaded.subscribe((emittedMetadata) => {
      expect(emittedMetadata).toEqual(metadata);
      done();
    });

    component['handleFile'](validFile);
  });

  it('should format file size correctly', () => {
    expect(component.formatFileSize(0)).toBe('0 Bytes');
    expect(component.formatFileSize(1024)).toBe('1 KB');
    expect(component.formatFileSize(1048576)).toBe('1 MB');
    expect(component.formatFileSize(1073741824)).toBe('1 GB');
  });

  it('should reset component state', () => {
    component.selectedFile = new File(['content'], 'test.csv', { type: 'text/csv' });
    component.uploadedFileMetadata = {
      fileId: '123',
      columns: ['col1'],
      rowCount: 10
    };
    component.errorMessage = 'Some error';
    component.isUploading = true;

    component.reset();

    expect(component.selectedFile).toBeNull();
    expect(component.uploadedFileMetadata).toBeNull();
    expect(component.errorMessage).toBeNull();
    expect(component.isUploading).toBe(false);
  });

  it('should handle drag over event', () => {
    const event = new DragEvent('dragover');
    spyOn(event, 'preventDefault');
    spyOn(event, 'stopPropagation');

    component.onDragOver(event);

    expect(event.preventDefault).toHaveBeenCalled();
    expect(event.stopPropagation).toHaveBeenCalled();
    expect(component.isDragging).toBe(true);
  });

  it('should handle drag leave event', () => {
    component.isDragging = true;
    const event = new DragEvent('dragleave');
    spyOn(event, 'preventDefault');
    spyOn(event, 'stopPropagation');

    component.onDragLeave(event);

    expect(event.preventDefault).toHaveBeenCalled();
    expect(event.stopPropagation).toHaveBeenCalled();
    expect(component.isDragging).toBe(false);
  });

  it('should handle drop event with file', () => {
    const file = new File(['content'], 'test.csv', { type: 'text/csv' });
    const dataTransfer = new DataTransfer();
    dataTransfer.items.add(file);
    
    const event = new DragEvent('drop', { dataTransfer });
    spyOn(event, 'preventDefault');
    spyOn(event, 'stopPropagation');
    spyOn<any>(component, 'handleFile');

    component.onDrop(event);

    expect(event.preventDefault).toHaveBeenCalled();
    expect(event.stopPropagation).toHaveBeenCalled();
    expect(component.isDragging).toBe(false);
    expect(component['handleFile']).toHaveBeenCalled();
  });
});
