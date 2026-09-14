import { Marked } from 'marked';

function escapeText(value: string): string {
  return value.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}

// Model output must not trigger automatic requests to image or HTML endpoints.
// Angular sanitization remains the final step before inserting the generated HTML.
const analysisMarkdown = new Marked({
  renderer: {
    image: ({ text }) => escapeText(text),
    html: ({ text }) => escapeText(text)
  }
});

export function renderAnalysisMarkdown(source: string): string | Promise<string> {
  return analysisMarkdown.parse(source);
}
