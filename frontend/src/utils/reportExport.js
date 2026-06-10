const REPORT_STYLE = `
  :root {
    color-scheme: light;
    --ink: #111827;
    --muted: #526070;
    --faint: #7a8795;
    --line: #dbe3ed;
    --accent: #1d4ed8;
    --accent-soft: #eff6ff;
    --surface: #ffffff;
    --page: #f8fafc;
  }

  * { box-sizing: border-box; }

  body {
    margin: 0;
    background: var(--page);
    color: var(--ink);
    font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    -webkit-font-smoothing: antialiased;
  }

  .downloaded-report-shell {
    width: min(100%, 980px);
    margin: 0 auto;
    padding: 42px 22px 56px;
  }

  .downloaded-report-chrome {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 18px;
    margin-bottom: 18px;
    color: var(--faint);
    font-size: 12px;
  }

  .downloaded-report-brand {
    display: inline-flex;
    align-items: center;
    gap: 10px;
    color: var(--accent);
    font-weight: 850;
    letter-spacing: 0;
  }

  .downloaded-report-brand-mark {
    width: 32px;
    height: 32px;
    display: inline-grid;
    place-items: center;
    border: 1px solid #bfdbfe;
    border-radius: 8px;
    background: var(--accent-soft);
    font-weight: 900;
  }

  .downloaded-report-card {
    overflow: hidden;
    border: 1px solid var(--line);
    border-radius: 8px;
    background: var(--surface);
    box-shadow: 0 28px 80px rgba(17, 24, 39, 0.12);
  }

  .report-markdown {
    padding: 34px;
    color: var(--muted);
    font-size: 15px;
    line-height: 1.68;
  }

  .report-markdown > :first-child { margin-top: 0; }
  .report-markdown > :last-child { margin-bottom: 0; }

  .report-markdown h1 {
    margin: 0 0 22px;
    padding-bottom: 18px;
    border-bottom: 1px solid var(--line);
    color: var(--ink);
    font-size: 36px;
    line-height: 1.08;
    letter-spacing: 0;
  }

  .report-markdown h2 {
    margin: 28px 0 11px;
    color: var(--accent);
    font-size: 12px;
    font-weight: 850;
    letter-spacing: 0.08em;
    text-transform: uppercase;
  }

  .report-markdown h3 {
    margin: 22px 0 8px;
    color: var(--ink);
    font-size: 17px;
  }

  .report-markdown p { margin: 0 0 14px; }
  .report-markdown strong { color: var(--ink); }

  .report-markdown ul,
  .report-markdown ol {
    margin: 0 0 16px;
    padding-left: 22px;
  }

  .report-markdown li { margin: 6px 0; }

  .report-markdown .md-table-wrap {
    margin: 16px 0 20px;
    overflow-x: auto;
    border: 1px solid var(--line);
    border-radius: 8px;
    background: var(--surface);
  }

  .report-markdown table {
    width: 100%;
    border-spacing: 0;
  }

  .report-markdown th,
  .report-markdown td {
    padding: 12px 14px;
    border-bottom: 1px solid var(--line);
    text-align: left;
    vertical-align: top;
    font-size: 13px;
    line-height: 1.45;
  }

  .report-markdown th {
    color: var(--ink);
    background: var(--accent-soft);
    font-weight: 850;
  }

  .report-markdown tr:last-child td { border-bottom: 0; }

  .report-markdown blockquote {
    margin: 18px 0;
    padding: 13px 15px;
    border-left: 3px solid var(--accent);
    border-radius: 0 8px 8px 0;
    color: var(--ink);
    background: var(--accent-soft);
  }

  .report-markdown code {
    padding: 2px 5px;
    border-radius: 5px;
    color: var(--ink);
    background: rgba(17, 24, 39, 0.07);
    font-family: "DM Mono", "SFMono-Regular", Consolas, monospace;
    font-size: 0.92em;
  }

  .downloaded-report-footer {
    margin-top: 18px;
    color: var(--faint);
    font-size: 11px;
    line-height: 1.5;
    text-align: center;
  }

  @media print {
    body { background: #ffffff; }
    .downloaded-report-shell { width: 100%; padding: 0; }
    .downloaded-report-card { border: 0; box-shadow: none; }
    .downloaded-report-chrome { margin-bottom: 14px; }
  }
`;

export function downloadReportHtml(reportElement, markdown) {
  const html = buildReportDocument(reportElement, markdown);
  const title = reportTitle(markdown);
  const blob = new Blob([html], { type: 'text/html;charset=utf-8' });
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = `${slugify(title)}.html`;
  document.body.append(link);
  link.click();
  link.remove();
  window.setTimeout(() => URL.revokeObjectURL(url), 1000);
}

export function printReport(reportElement, markdown) {
  const html = buildReportDocument(reportElement, markdown, { autoPrint: true });
  const printWindow = window.open('', '_blank', 'noopener,noreferrer,width=1100,height=800');
  if (!printWindow) {
    downloadReportHtml(reportElement, markdown);
    return;
  }

  printWindow.document.open();
  printWindow.document.write(html);
  printWindow.document.close();
}

function buildReportDocument(reportElement, markdown, { autoPrint = false } = {}) {
  const title = escapeHtml(reportTitle(markdown));
  const generatedAt = new Intl.DateTimeFormat(undefined, {
    dateStyle: 'medium',
    timeStyle: 'short',
  }).format(new Date());
  const reportHtml = reportElement?.outerHTML || `<article class="report-markdown"><pre>${escapeHtml(markdown)}</pre></article>`;

  return `<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>${title}</title>
  <style>${REPORT_STYLE}</style>
</head>
<body>
  <main class="downloaded-report-shell">
    <header class="downloaded-report-chrome">
      <div class="downloaded-report-brand">
        <span class="downloaded-report-brand-mark">BA</span>
        <span>Baboon Analyst</span>
      </div>
      <span>Generated ${escapeHtml(generatedAt)}</span>
    </header>
    <section class="downloaded-report-card">
      ${reportHtml}
    </section>
    <footer class="downloaded-report-footer">
      Research output generated from public financial data and AI analysis. Not personalized investment advice.
    </footer>
  </main>
  ${autoPrint ? '<script>window.addEventListener("load", () => { window.focus(); window.print(); });</script>' : ''}
</body>
</html>`;
}

function reportTitle(markdown) {
  const heading = markdown.match(/^#\s+(.+)$/m)?.[1]?.trim();
  return heading || 'Baboon Analyst Report';
}

function slugify(value) {
  return value
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '')
    .slice(0, 72) || 'baboon-analyst-report';
}

function escapeHtml(value) {
  return String(value)
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#039;');
}
