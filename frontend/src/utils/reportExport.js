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

const PDF_PAGE = {
  width: 612,
  height: 792,
  marginX: 54,
  bodyTop: 690,
  bodyBottom: 58,
};

const PDF_COLORS = {
  ink: '0.067 0.094 0.153',
  muted: '0.322 0.376 0.439',
  faint: '0.478 0.529 0.584',
  accent: '0.114 0.306 0.847',
  line: '0.859 0.890 0.929',
};

export function downloadReportPdf(reportElement, markdown) {
  const pdf = buildReportPdf(reportElement, markdown);
  const title = reportTitle(markdown);
  const blob = new Blob([pdf], { type: 'application/pdf' });
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = `${slugify(title)}.pdf`;
  document.body.append(link);
  link.click();
  link.remove();
  window.setTimeout(() => URL.revokeObjectURL(url), 1000);
}

export function printReport(reportElement, markdown) {
  const html = buildReportDocument(reportElement, markdown, { autoPrint: true });
  const printWindow = window.open('', '_blank', 'noopener,noreferrer,width=1100,height=800');
  if (!printWindow) {
    downloadReportPdf(reportElement, markdown);
    return;
  }

  printWindow.document.open();
  printWindow.document.write(html);
  printWindow.document.close();
}

function buildReportPdf(reportElement, markdown) {
  const generatedAt = new Intl.DateTimeFormat(undefined, {
    dateStyle: 'medium',
    timeStyle: 'short',
  }).format(new Date());
  const sourceText = markdown?.trim() || reportElement?.textContent?.trim() || 'Baboon Analyst Report';
  const pages = buildPdfPages(sourceText, generatedAt);

  pages.forEach((page, index) => {
    drawFooter(page.commands, index + 1, pages.length);
  });

  return renderPdfDocument(pages);
}

function buildPdfPages(markdown, generatedAt) {
  const pages = [];
  let currentPage = createPdfPage(generatedAt);
  pages.push(currentPage);

  markdownToPdfBlocks(markdown).forEach((block, index) => {
    if (block.type === 'space') {
      currentPage.y = Math.max(PDF_PAGE.bodyBottom, currentPage.y - block.height);
      return;
    }

    const x = PDF_PAGE.marginX + (block.indent || 0);
    const maxWidth = PDF_PAGE.width - PDF_PAGE.marginX * 2 - (block.indent || 0);
    const wrappedLines = wrapPdfText(block.text, block.size, maxWidth);
    const gapBefore = index === 0 ? 0 : block.gapBefore || 0;
    const gapAfter = block.gapAfter || 0;
    const lineHeight = block.lineHeight || block.size * 1.38;

    if (currentPage.y - gapBefore - wrappedLines.length * lineHeight < PDF_PAGE.bodyBottom) {
      currentPage = createPdfPage(generatedAt);
      pages.push(currentPage);
    } else {
      currentPage.y -= gapBefore;
    }

    wrappedLines.forEach((line) => {
      if (currentPage.y - lineHeight < PDF_PAGE.bodyBottom) {
        currentPage = createPdfPage(generatedAt);
        pages.push(currentPage);
      }

      drawText(currentPage.commands, line, x, currentPage.y, block.size, block.font, block.color);
      currentPage.y -= lineHeight;
    });

    currentPage.y -= gapAfter;
  });

  return pages;
}

function createPdfPage(generatedAt) {
  const commands = [];

  drawText(commands, 'Baboon Analyst', PDF_PAGE.marginX, 746, 11, 'bold', PDF_COLORS.accent);
  drawText(commands, `Generated ${generatedAt}`, 404, 746, 8.5, 'regular', PDF_COLORS.faint);
  drawLine(commands, PDF_PAGE.marginX, 724, PDF_PAGE.width - PDF_PAGE.marginX, 724, PDF_COLORS.line, 0.8);

  return { commands, y: PDF_PAGE.bodyTop };
}

function drawFooter(commands, pageNumber, pageCount) {
  const note = 'Research output generated from public financial data and AI analysis. Not personalized investment advice.';
  const pageLabel = `Page ${pageNumber} of ${pageCount}`;

  drawLine(commands, PDF_PAGE.marginX, 44, PDF_PAGE.width - PDF_PAGE.marginX, 44, PDF_COLORS.line, 0.6);
  drawText(commands, note, PDF_PAGE.marginX, 31, 7.5, 'regular', PDF_COLORS.faint);
  drawText(
    commands,
    pageLabel,
    PDF_PAGE.width - PDF_PAGE.marginX - approximatePdfWidth(pageLabel, 7.5),
    31,
    7.5,
    'regular',
    PDF_COLORS.faint,
  );
}

function markdownToPdfBlocks(markdown) {
  const blocks = [];
  const lines = String(markdown || '').replace(/\r\n?/g, '\n').split('\n');

  lines.forEach((line) => {
    const trimmed = line.trim();

    if (!trimmed) {
      blocks.push({ type: 'space', height: 7 });
      return;
    }

    if (isMarkdownTableSeparator(trimmed)) {
      return;
    }

    const heading = trimmed.match(/^(#{1,6})\s+(.+)$/);
    if (heading) {
      const level = heading[1].length;
      blocks.push({
        text: stripMarkdown(heading[2]),
        size: level === 1 ? 20 : level === 2 ? 13 : 11.5,
        font: 'bold',
        color: level === 1 ? PDF_COLORS.ink : PDF_COLORS.accent,
        gapBefore: level === 1 ? 5 : 13,
        gapAfter: level === 1 ? 9 : 3,
        lineHeight: level === 1 ? 24 : 16,
      });
      return;
    }

    if (isMarkdownTableRow(trimmed)) {
      const cells = trimmed
        .replace(/^\|/, '')
        .replace(/\|$/, '')
        .split('|')
        .map((cell) => stripMarkdown(cell))
        .filter(Boolean);

      blocks.push({
        text: cells.join(' | '),
        size: 8.8,
        font: 'regular',
        color: PDF_COLORS.muted,
        gapBefore: 2,
        gapAfter: 2,
        lineHeight: 12,
      });
      return;
    }

    const unorderedListItem = trimmed.match(/^[-*]\s+(.+)$/);
    if (unorderedListItem) {
      blocks.push({
        text: `- ${stripMarkdown(unorderedListItem[1])}`,
        size: 10.3,
        font: 'regular',
        color: PDF_COLORS.muted,
        indent: 12,
        gapBefore: 2,
        lineHeight: 14,
      });
      return;
    }

    const orderedListItem = trimmed.match(/^(\d+\.)\s+(.+)$/);
    if (orderedListItem) {
      blocks.push({
        text: `${orderedListItem[1]} ${stripMarkdown(orderedListItem[2])}`,
        size: 10.3,
        font: 'regular',
        color: PDF_COLORS.muted,
        indent: 12,
        gapBefore: 2,
        lineHeight: 14,
      });
      return;
    }

    const quote = trimmed.match(/^>\s*(.+)$/);
    if (quote) {
      blocks.push({
        text: stripMarkdown(quote[1]),
        size: 10,
        font: 'regular',
        color: PDF_COLORS.ink,
        indent: 14,
        gapBefore: 7,
        gapAfter: 3,
        lineHeight: 14,
      });
      return;
    }

    blocks.push({
      text: stripMarkdown(trimmed),
      size: 10.5,
      font: 'regular',
      color: PDF_COLORS.muted,
      gapBefore: 4,
      gapAfter: 1,
      lineHeight: 14.5,
    });
  });

  return blocks;
}

function isMarkdownTableSeparator(line) {
  return /^\|?[\s:-]+\|[\s|:-]+$/.test(line) && /-{3,}/.test(line);
}

function isMarkdownTableRow(line) {
  return line.includes('|') && (line.startsWith('|') || line.endsWith('|') || /\s\|\s/.test(line));
}

function stripMarkdown(value) {
  return String(value || '')
    .replace(/!\[([^\]]*)]\([^)]+\)/g, '$1')
    .replace(/\[([^\]]+)]\(([^)]+)\)/g, '$1 ($2)')
    .replace(/`([^`]+)`/g, '$1')
    .replace(/\*\*([^*]+)\*\*/g, '$1')
    .replace(/__([^_]+)__/g, '$1')
    .replace(/\*([^*]+)\*/g, '$1')
    .replace(/_([^_]+)_/g, '$1')
    .replace(/<br\s*\/?>/gi, ' ')
    .replace(/<[^>]+>/g, '')
    .replace(/\s+/g, ' ')
    .trim();
}

function wrapPdfText(value, fontSize, maxWidth) {
  const text = sanitizePdfText(value);
  const maxChars = Math.max(24, Math.floor(maxWidth / (fontSize * 0.52)));
  const words = text.split(/\s+/).filter(Boolean);
  const lines = [];
  let current = '';

  words.forEach((word) => {
    const chunks = splitLongWord(word, maxChars);

    chunks.forEach((chunk) => {
      const next = current ? `${current} ${chunk}` : chunk;
      if (next.length > maxChars && current) {
        lines.push(current);
        current = chunk;
      } else {
        current = next;
      }
    });
  });

  if (current) {
    lines.push(current);
  }

  return lines.length ? lines : [''];
}

function splitLongWord(word, maxChars) {
  if (word.length <= maxChars) {
    return [word];
  }

  const chunks = [];
  for (let index = 0; index < word.length; index += maxChars) {
    chunks.push(word.slice(index, index + maxChars));
  }
  return chunks;
}

function sanitizePdfText(value) {
  return String(value || '')
    .normalize('NFKD')
    .replace(/[\u0300-\u036f]/g, '')
    .replace(/[“”]/g, '"')
    .replace(/[‘’]/g, "'")
    .replace(/[–—]/g, '-')
    .replace(/[•·]/g, '-')
    .replace(/\u00a0/g, ' ')
    .replace(/≤/g, '<=')
    .replace(/≥/g, '>=')
    .replace(/×/g, 'x')
    .replace(/[^\x20-\x7e]/g, '?');
}

function drawText(commands, text, x, y, size, font, color) {
  commands.push(`${color} rg`);
  commands.push(`BT /${font === 'bold' ? 'F2' : 'F1'} ${formatPdfNumber(size)} Tf ${formatPdfNumber(x)} ${formatPdfNumber(y)} Td (${escapePdfString(text)}) Tj ET`);
}

function drawLine(commands, x1, y1, x2, y2, color, width) {
  commands.push(`q ${color} RG ${formatPdfNumber(width)} w ${formatPdfNumber(x1)} ${formatPdfNumber(y1)} m ${formatPdfNumber(x2)} ${formatPdfNumber(y2)} l S Q`);
}

function renderPdfDocument(pages) {
  const pageRefs = pages.map((_, index) => `${5 + index * 2} 0 R`);
  const objects = [
    { id: 1, body: '<< /Type /Catalog /Pages 2 0 R >>' },
    { id: 2, body: `<< /Type /Pages /Kids [${pageRefs.join(' ')}] /Count ${pages.length} >>` },
    { id: 3, body: '<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>' },
    { id: 4, body: '<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold >>' },
  ];

  pages.forEach((page, index) => {
    const pageId = 5 + index * 2;
    const contentId = pageId + 1;
    const stream = page.commands.join('\n');

    objects.push({
      id: pageId,
      body: `<< /Type /Page /Parent 2 0 R /MediaBox [0 0 ${PDF_PAGE.width} ${PDF_PAGE.height}] /Resources << /Font << /F1 3 0 R /F2 4 0 R >> >> /Contents ${contentId} 0 R >>`,
    });
    objects.push({
      id: contentId,
      body: `<< /Length ${stream.length} >>\nstream\n${stream}\nendstream`,
    });
  });

  objects.sort((a, b) => a.id - b.id);

  let pdf = '%PDF-1.4\n';
  const offsets = [];

  objects.forEach((object) => {
    offsets[object.id] = pdf.length;
    pdf += `${object.id} 0 obj\n${object.body}\nendobj\n`;
  });

  const maxId = objects.at(-1).id;
  const xrefStart = pdf.length;
  pdf += `xref\n0 ${maxId + 1}\n0000000000 65535 f \n`;

  for (let id = 1; id <= maxId; id += 1) {
    pdf += `${String(offsets[id]).padStart(10, '0')} 00000 n \n`;
  }

  pdf += `trailer\n<< /Size ${maxId + 1} /Root 1 0 R >>\nstartxref\n${xrefStart}\n%%EOF\n`;
  return pdf;
}

function escapePdfString(value) {
  return sanitizePdfText(value)
    .replace(/\\/g, '\\\\')
    .replace(/\(/g, '\\(')
    .replace(/\)/g, '\\)');
}

function approximatePdfWidth(text, fontSize) {
  return sanitizePdfText(text).length * fontSize * 0.48;
}

function formatPdfNumber(value) {
  return Number(value).toFixed(2).replace(/\.?0+$/, '');
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
