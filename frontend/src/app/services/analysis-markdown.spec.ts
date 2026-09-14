import { renderAnalysisMarkdown } from './analysis-markdown';

describe('analysis markdown', () => {
  it('keeps useful markdown without loading model-supplied resources', async () => {
    const html = await renderAnalysisMarkdown('**Draft** ![chart](https://example.org/collect?value=synthetic)');
    expect(html).toContain('<strong>Draft</strong>');
    expect(html).toContain('chart');
    expect(html).not.toContain('<img');
    expect(html).not.toContain('example.org');
  });

  it('renders raw model HTML as text', async () => {
    const html = await renderAnalysisMarkdown('<img src="https://example.org/collect"><iframe src="https://example.org"></iframe>');
    expect(html).not.toContain('<img');
    expect(html).not.toContain('<iframe');
    expect(html).toContain('&lt;');
  });
});
