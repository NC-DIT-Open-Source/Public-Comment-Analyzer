import { ComponentFixture, TestBed } from '@angular/core/testing';
import { ReactiveFormsModule } from '@angular/forms';
import { BrowserAnimationsModule } from '@angular/platform-browser/animations';
import { provideHttpClient, withXhr } from '@angular/common/http';
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
        provideHttpClient(withXhr()),
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

    it('starts with zero examples', () => {
      expect(component.examplesArray.length).toBe(0);
    });

    it('addExample adds an example with empty commentText and label', () => {
      component.addExample();
      expect(component.examplesArray.length).toBe(1);
      expect(component.examplesArray.at(0).get('commentText')?.value).toBe('');
      expect(component.examplesArray.at(0).get('label')?.value).toBe('');
    });

    it('removeExample removes the example at the given index', () => {
      component.addExample();
      component.addExample();
      component.removeExample(0);
      expect(component.examplesArray.length).toBe(1);
    });

    it('caps examples at 14 per column', () => {
      for (let i = 0; i < 20; i++) {
        component.addExample();
      }
      expect(component.examplesArray.length).toBe(14);
    });

    it('persists examples on the saved categorized column', () => {
      component.columnForm.patchValue({ name: 'Stance' });
      component.optionsArray.at(0).patchValue({ value: 'Pro', description: 'Supports' });
      component.optionsArray.at(1).patchValue({ value: 'Against', description: 'Opposes' });
      component.addExample();
      component.examplesArray.at(0).patchValue({
        commentText: 'I love this proposal.',
        label: 'Pro'
      });

      component.addColumn();

      expect(component.columns.length).toBe(1);
      expect(component.columns[0].examples?.length).toBe(1);
      expect(component.columns[0].examples?.[0].commentText).toBe('I love this proposal.');
      expect(component.columns[0].examples?.[0].label).toBe('Pro');
    });

    it('blocks save when an example has commentText but no label', () => {
      component.columnForm.patchValue({ name: 'Stance' });
      component.optionsArray.at(0).patchValue({ value: 'Pro', description: 'Supports' });
      component.optionsArray.at(1).patchValue({ value: 'Against', description: 'Opposes' });
      component.addExample();
      component.examplesArray.at(0).patchValue({
        commentText: 'Has text but no label',
        label: ''
      });

      component.addColumn();

      expect(component.columns.length).toBe(0);
      expect(component.errorMessage).toBeTruthy();
    });

    it('drops fully-empty example rows on save (so users can leave a blank slot)', () => {
      component.columnForm.patchValue({ name: 'Stance' });
      component.optionsArray.at(0).patchValue({ value: 'Pro', description: 'Supports' });
      component.optionsArray.at(1).patchValue({ value: 'Against', description: 'Opposes' });
      component.addExample();
      // Leave both fields empty

      component.addColumn();

      expect(component.columns.length).toBe(1);
      expect(component.columns[0].examples?.length || 0).toBe(0);
    });

    it('renders an Add Example button only when column type is categorized', () => {
      // Already in categorized mode via outer describe's beforeEach
      fixture.detectChanges();
      const compiled = fixture.nativeElement as HTMLElement;
      const addExampleBtn = compiled.querySelector('.add-example-btn');
      expect(addExampleBtn).toBeTruthy();
    });

    it('renders example rows after addExample is called', () => {
      component.addExample();
      fixture.detectChanges();
      const compiled = fixture.nativeElement as HTMLElement;
      const exampleRows = compiled.querySelectorAll('.example-row');
      expect(exampleRows.length).toBe(1);
    });

    it('repopulates examples when editing a categorized column', () => {
      component.columns = [{
        name: 'Stance',
        instructions: 'Pro: Supports; Against: Opposes',
        type: 'categorized',
        options: [
          { value: 'Pro', description: 'Supports' },
          { value: 'Against', description: 'Opposes' }
        ],
        examples: [
          { commentText: 'Yes please', label: 'Pro' },
          { commentText: 'No way', label: 'Against' }
        ]
      }];

      component.editColumn(0);

      expect(component.examplesArray.length).toBe(2);
      expect(component.examplesArray.at(0).get('commentText')?.value).toBe('Yes please');
      expect(component.examplesArray.at(0).get('label')?.value).toBe('Pro');
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

  describe('Description Lint Warnings', () => {
    beforeEach(() => {
      component.onColumnTypeChange('categorized');
    });

    it('flags a description containing the poison word "default"', () => {
      const warnings = component.getDescriptionWarnings(
        'This is the default for comments that say "Legalize it".'
      );
      expect(warnings.some(w => w.toLowerCase().includes('default'))).toBeTruthy();
    });

    it('flags a description containing the poison word "usually"', () => {
      const warnings = component.getDescriptionWarnings(
        'They usually oppose recreational use.'
      );
      expect(warnings.some(w => w.toLowerCase().includes('usually'))).toBeTruthy();
    });

    it('flags a description containing the poison phrase "most likely"', () => {
      const warnings = component.getDescriptionWarnings(
        'Pick this when the comment is most likely about cannabis.'
      );
      expect(warnings.some(w => w.toLowerCase().includes('most likely'))).toBeTruthy();
    });

    it('does not flag a clean description', () => {
      const warnings = component.getDescriptionWarnings(
        'The commenter supports broad medical access for chronic conditions.'
      );
      expect(warnings.length).toBe(0);
    });

    it('matches poison words case-insensitively but only as whole words', () => {
      // "Defaulted" should NOT match "default" — substring matching would over-trigger
      const warnings = component.getDescriptionWarnings('They defaulted on payment.');
      expect(warnings.length).toBe(0);
    });

    it('warns when categorized column has more than 5 options without examples', () => {
      // Add 4 more options so we have 6 total
      for (let i = 0; i < 4; i++) {
        component.addOption();
      }
      expect(component.optionsArray.length).toBe(6);
      expect(component.getCategoryStructureWarning()).toContain('5');
    });

    it('does not warn when categorized column has 5 or fewer options', () => {
      // Default is 2 options — add 3 more for 5 total
      for (let i = 0; i < 3; i++) {
        component.addOption();
      }
      expect(component.optionsArray.length).toBe(5);
      expect(component.getCategoryStructureWarning()).toBeNull();
    });

    it('renders the description warning in the UI when a poison word is typed', () => {
      component.optionsArray.at(0).patchValue({
        value: '6',
        description: 'This is the default for legalize-it comments.'
      });
      fixture.detectChanges();

      const compiled = fixture.nativeElement as HTMLElement;
      const warningEl = compiled.querySelector('.option-warning');
      expect(warningEl).toBeTruthy();
      expect(warningEl?.textContent?.toLowerCase()).toContain('default');
    });

    it('renders the structure warning in the UI when more than 5 options exist', () => {
      for (let i = 0; i < 4; i++) {
        component.addOption();
      }
      fixture.detectChanges();

      const compiled = fixture.nativeElement as HTMLElement;
      const structureWarning = compiled.querySelector('.structure-warning');
      expect(structureWarning).toBeTruthy();
      expect(structureWarning?.textContent).toContain('5');
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
