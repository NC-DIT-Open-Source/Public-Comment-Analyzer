import { ComponentFixture, TestBed } from '@angular/core/testing';
import { ReactiveFormsModule } from '@angular/forms';
import { BrowserAnimationsModule } from '@angular/platform-browser/animations';
import { ColumnDefinitionComponent } from './column-definition.component';
import { AnalysisColumn } from '../../services/processing.service';

describe('ColumnDefinitionComponent', () => {
  let component: ColumnDefinitionComponent;
  let fixture: ComponentFixture<ColumnDefinitionComponent>;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [
        ColumnDefinitionComponent,
        ReactiveFormsModule,
        BrowserAnimationsModule
      ]
    }).compileComponents();

    fixture = TestBed.createComponent(ColumnDefinitionComponent);
    component = fixture.componentInstance;
    fixture.detectChanges();
  });

  it('should create', () => {
    expect(component).toBeTruthy();
  });

  describe('Form Validation', () => {
    it('should require column name', () => {
      const nameControl = component.columnForm.get('name');
      expect(nameControl?.valid).toBeFalsy();
      expect(nameControl?.hasError('required')).toBeTruthy();
    });

    it('should require instructions', () => {
      const instructionsControl = component.columnForm.get('instructions');
      expect(instructionsControl?.valid).toBeFalsy();
      expect(instructionsControl?.hasError('required')).toBeTruthy();
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
      
      // Form is technically valid but trimming results in empty strings
      // so no column should be added
      expect(component.columns.length).toBe(0);
    });
  });

  describe('Adding Columns', () => {
    it('should add a new column when form is valid', () => {
      component.columnForm.patchValue({
        name: 'Category',
        instructions: 'Categorize the comment'
      });

      component.addColumn();

      expect(component.columns.length).toBe(1);
      expect(component.columns[0].name).toBe('Category');
      expect(component.columns[0].instructions).toBe('Categorize the comment');
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

    it('should not add column when form is invalid', () => {
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

  describe('Editing Columns', () => {
    beforeEach(() => {
      component.columns = [
        { name: 'Category', instructions: 'Categorize the comment' },
        { name: 'Sentiment', instructions: 'Analyze sentiment' }
      ];
    });

    it('should populate form with column data when editing', () => {
      component.editColumn(0);

      expect(component.columnForm.get('name')?.value).toBe('Category');
      expect(component.columnForm.get('instructions')?.value).toBe('Categorize the comment');
      expect(component.editingIndex).toBe(0);
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

    it('should reset editing state after update', () => {
      component.editColumn(1);
      component.columnForm.patchValue({
        name: 'New Name',
        instructions: 'New instructions'
      });

      component.addColumn();

      expect(component.isEditing).toBeFalsy();
      expect(component.columnForm.get('name')?.value).toBeNull();
    });

    it('should cancel editing and reset form', () => {
      component.editColumn(0);
      component.columnForm.patchValue({
        name: 'Modified',
        instructions: 'Modified instructions'
      });

      component.cancelEdit();

      expect(component.editingIndex).toBeNull();
      expect(component.columnForm.get('name')?.value).toBeNull();
      expect(component.columns[0].name).toBe('Category'); // Original unchanged
    });
  });

  describe('Removing Columns', () => {
    beforeEach(() => {
      component.columns = [
        { name: 'Category', instructions: 'Categorize' },
        { name: 'Sentiment', instructions: 'Analyze' },
        { name: 'Rating', instructions: 'Rate' }
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

    it('should not affect editing state when removing different column', () => {
      component.editColumn(1);
      component.removeColumn(0);

      expect(component.editingIndex).not.toBeNull();
    });
  });

  describe('Display', () => {
    it('should show both name and instructions for each column', () => {
      component.columns = [
        { name: 'Test Column', instructions: 'Test instructions' }
      ];
      fixture.detectChanges();

      const compiled = fixture.nativeElement;
      expect(compiled.textContent).toContain('Test Column');
      expect(compiled.textContent).toContain('Test instructions');
    });

    it('should display column count', () => {
      component.columns = [
        { name: 'Col1', instructions: 'Inst1' },
        { name: 'Col2', instructions: 'Inst2' }
      ];
      fixture.detectChanges();

      const compiled = fixture.nativeElement;
      expect(compiled.textContent).toContain('Defined Columns (2)');
    });
  });
});
