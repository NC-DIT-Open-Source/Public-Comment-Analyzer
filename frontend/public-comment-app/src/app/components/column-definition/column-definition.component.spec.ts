import { ComponentFixture, TestBed } from '@angular/core/testing';
import { ReactiveFormsModule } from '@angular/forms';
import { BrowserAnimationsModule } from '@angular/platform-browser/animations';
import { provideHttpClient } from '@angular/common/http';
import { provideHttpClientTesting } from '@angular/common/http/testing';
import { provideRouter } from '@angular/router';
import { ColumnDefinitionComponent } from './column-definition.component';
import { AnalysisColumn, ProcessingService } from '../../services/processing.service';

describe('ColumnDefinitionComponent', () => {
  let component: ColumnDefinitionComponent;
  let fixture: ComponentFixture<ColumnDefinitionComponent>;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [
        ColumnDefinitionComponent,
        ReactiveFormsModule,
        BrowserAnimationsModule
      ],
      providers: [
        provideHttpClient(),
        provideHttpClientTesting(),
        provideRouter([])
      ]
    }).compileComponents();

    fixture = TestBed.createComponent(ColumnDefinitionComponent);
    component = fixture.componentInstance;
    // Prevent ngOnInit from redirecting to /upload by setting fileMetadata
    component.fileMetadata = { fileId: 'test-file', columns: ['col1', 'col2'], rowCount: 10 };
    fixture.detectChanges();
  });

  it('should create', () => {
    expect(component).toBeTruthy();
  });

  describe('Form Validation', () => {
    it('should not show errors initially', () => {
      const nameControl = component.columnForm.get('name');
      const instructionsControl = component.columnForm.get('instructions');
      expect(nameControl?.hasError('required')).toBeFalsy();
      expect(instructionsControl?.hasError('required')).toBeFalsy();
    });

    it('should show errors when addColumn is called with empty fields', () => {
      component.addColumn();
      const nameControl = component.columnForm.get('name');
      expect(nameControl?.hasError('required')).toBeTruthy();
    });

    it('should be valid when both fields are filled', () => {
      component.columnForm.patchValue({
        name: 'Sentiment',
        instructions: 'Categorize as positive or negative'
      });
      expect(component.columnForm.valid).toBeTruthy();
    });

    it('should not add columns with only whitespace', () => {
      component.columnForm.patchValue({
        name: '   ',
        instructions: '   '
      });
      
      component.addColumn();
      
      expect(component.columns.length).toBe(0);
    });
  });

  describe('Adding Open Text Columns', () => {
    it('should add a new open text column when form is valid', () => {
      component.columnType = 'open_text';
      component.columnForm.patchValue({
        name: 'Category',
        instructions: 'Categorize the comment'
      });

      component.addColumn();

      expect(component.columns.length).toBe(1);
      expect(component.columns[0].name).toBe('Category');
      expect(component.columns[0].instructions).toBe('Categorize the comment');
      expect(component.columns[0].type).toBe('open_text');
    });

    it('should emit columnsChanged event when adding column', (done) => {
      component.columnsChanged.subscribe((columns: AnalysisColumn[]) => {
        expect(columns.length).toBe(1);
        expect(columns[0].name).toBe('Rating');
        done();
      });

      component.columnForm.patchValue({
        name: 'Rating',
        instructions: 'Rate from 1 to 5'
      });

      component.addColumn();
    });

    it('should reset form after adding column', () => {
      component.columnForm.patchValue({
        name: 'Theme',
        instructions: 'Identify main theme'
      });

      component.addColumn();

      expect(component.columnForm.get('name')?.value).toBeNull();
      expect(component.columnForm.get('instructions')?.value).toBeNull();
    });

    it('should not add column when name is empty', () => {
      component.columnForm.patchValue({
        name: '',
        instructions: 'Some instructions'
      });

      component.addColumn();

      expect(component.columns.length).toBe(0);
    });

    it('should trim whitespace from column values', () => {
      component.columnForm.patchValue({
        name: '  Sentiment  ',
        instructions: '  Analyze sentiment  '
      });

      component.addColumn();

      expect(component.columns[0].name).toBe('Sentiment');
      expect(component.columns[0].instructions).toBe('Analyze sentiment');
    });

    it('should support adding multiple columns', () => {
      const columns = [
        { name: 'Category', instructions: 'Categorize' },
        { name: 'Sentiment', instructions: 'Analyze sentiment' },
        { name: 'Rating', instructions: 'Rate 1-5' }
      ];

      columns.forEach(col => {
        component.columnForm.patchValue(col);
        component.addColumn();
      });

      expect(component.columns.length).toBe(3);
      expect(component.columns[0].name).toBe('Category');
      expect(component.columns[1].name).toBe('Sentiment');
      expect(component.columns[2].name).toBe('Rating');
    });
  });

  describe('Adding Categorized Columns', () => {
    beforeEach(() => {
      component.onColumnTypeChange('categorized');
    });

    it('should initialize with 2 empty options when switching to categorized', () => {
      expect(component.optionsArray.length).toBe(2);
    });

    it('should add a categorized column with valid options', () => {
      component.columnForm.patchValue({ name: 'Stance' });
      component.optionsArray.at(0).patchValue({ value: 'Pro', description: 'Supports the proposal' });
      component.optionsArray.at(1).patchValue({ value: 'Against', description: 'Opposes the proposal' });

      component.addColumn();

      expect(component.columns.length).toBe(1);
      expect(component.columns[0].type).toBe('categorized');
      expect(component.columns[0].options?.length).toBe(2);
      expect(component.columns[0].options?.[0].value).toBe('Pro');
    });

    it('should not add categorized column with empty option values', () => {
      component.columnForm.patchValue({ name: 'Stance' });
      component.optionsArray.at(0).patchValue({ value: '', description: 'Supports' });
      component.optionsArray.at(1).patchValue({ value: 'Against', description: 'Opposes' });

      component.addColumn();

      expect(component.columns.length).toBe(0);
      expect(component.errorMessage).toBeTruthy();
    });

    it('should allow adding more options', () => {
      component.addOption();
      expect(component.optionsArray.length).toBe(3);
    });

    it('should not allow removing below 2 options', () => {
      component.removeOption(0);
      expect(component.optionsArray.length).toBe(2);
    });

    it('should not allow more than 50 options', () => {
      for (let i = 0; i < 50; i++) {
        component.addOption();
      }
      expect(component.optionsArray.length).toBeLessThanOrEqual(50);
    });
  });

  describe('Column Type Toggle', () => {
    it('should default to open_text', () => {
      expect(component.columnType).toBe('open_text');
    });

    it('should switch to categorized and create options', () => {
      component.onColumnTypeChange('categorized');
      expect(component.columnType).toBe('categorized');
      expect(component.optionsArray.length).toBe(2);
    });

    it('should switch back to open_text and clear options', () => {
      component.onColumnTypeChange('categorized');
      component.onColumnTypeChange('open_text');
      expect(component.columnType).toBe('open_text');
      expect(component.optionsArray.length).toBe(0);
    });
  });

  describe('Editing Columns', () => {
    beforeEach(() => {
      component.columns = [
        { name: 'Category', instructions: 'Categorize the comment', type: 'open_text' },
        { name: 'Stance', instructions: 'Pro: Supports; Against: Opposes', type: 'categorized',
          options: [
            { value: 'Pro', description: 'Supports' },
            { value: 'Against', description: 'Opposes' }
          ]
        }
      ];
    });

    it('should populate form with open text column data when editing', () => {
      component.editColumn(0);

      expect(component.columnForm.get('name')?.value).toBe('Category');
      expect(component.columnForm.get('instructions')?.value).toBe('Categorize the comment');
      expect(component.columnType).toBe('open_text');
      expect(component.editingIndex).toBe(0);
    });

    it('should populate form with categorized column data when editing', () => {
      component.editColumn(1);

      expect(component.columnForm.get('name')?.value).toBe('Stance');
      expect(component.columnType).toBe('categorized');
      expect(component.optionsArray.length).toBe(2);
      expect(component.optionsArray.at(0).value.value).toBe('Pro');
    });

    it('should update column when submitting in edit mode', () => {
      component.editColumn(0);
      component.columnForm.patchValue({
        name: 'Updated Category',
        instructions: 'Updated instructions'
      });

      component.addColumn();

      expect(component.columns[0].name).toBe('Updated Category');
      expect(component.columns[0].instructions).toBe('Updated instructions');
      expect(component.editingIndex).toBeNull();
    });

    it('should cancel editing and reset form', () => {
      component.editColumn(0);
      component.cancelEdit();

      expect(component.editingIndex).toBeNull();
      expect(component.columnForm.get('name')?.value).toBeNull();
      expect(component.columns[0].name).toBe('Category');
      expect(component.columnType).toBe('open_text');
    });
  });

  describe('Removing Columns', () => {
    beforeEach(() => {
      component.columns = [
        { name: 'Category', instructions: 'Categorize', type: 'open_text' },
        { name: 'Sentiment', instructions: 'Analyze', type: 'open_text' },
        { name: 'Rating', instructions: 'Rate', type: 'open_text' }
      ];
    });

    it('should remove column at specified index', () => {
      component.removeColumn(1);

      expect(component.columns.length).toBe(2);
      expect(component.columns[0].name).toBe('Category');
      expect(component.columns[1].name).toBe('Rating');
    });

    it('should emit columnsChanged event when removing column', (done) => {
      component.columnsChanged.subscribe((columns: AnalysisColumn[]) => {
        expect(columns.length).toBe(2);
        done();
      });

      component.removeColumn(0);
    });

    it('should cancel editing if removing the column being edited', () => {
      component.editColumn(1);
      component.removeColumn(1);

      expect(component.editingIndex).toBeNull();
      expect(component.columnForm.get('name')?.value).toBeNull();
    });
  });

  describe('Display', () => {
    it('should show both name and instructions for open text columns', () => {
      component.columns = [
        { name: 'Test Column', instructions: 'Test instructions', type: 'open_text' }
      ];
      fixture.detectChanges();

      const compiled = fixture.nativeElement;
      expect(compiled.textContent).toContain('Test Column');
      expect(compiled.textContent).toContain('Test instructions');
    });

    it('should show type badge for categorized columns', () => {
      component.columns = [
        { name: 'Stance', instructions: 'Pro: Supports; Against: Opposes', type: 'categorized',
          options: [
            { value: 'Pro', description: 'Supports' },
            { value: 'Against', description: 'Opposes' }
          ]
        }
      ];
      fixture.detectChanges();

      const compiled = fixture.nativeElement;
      expect(compiled.textContent).toContain('Categorized');
      expect(compiled.textContent).toContain('Pro');
      expect(compiled.textContent).toContain('Against');
    });

    it('should display column count', () => {
      component.columns = [
        { name: 'Col1', instructions: 'Inst1', type: 'open_text' },
        { name: 'Col2', instructions: 'Inst2', type: 'open_text' }
      ];
      fixture.detectChanges();

      const compiled = fixture.nativeElement;
      expect(compiled.textContent).toContain('Defined Columns (2)');
    });
  });
});
