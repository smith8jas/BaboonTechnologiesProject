const REPORT_STYLE = `
  @import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Serif:wght@400;500;600;700&family=IBM+Plex+Sans:wght@400;500;600;700&family=IBM+Plex+Mono:wght@400;500;600&display=swap');

  :root {
    color-scheme: light;
    --memo-ink: #16191c;
    --memo-body: #23262b;
    --memo-muted: #5c6066;
    --memo-faint: #9a9690;
    --memo-line: #e3e0d9;
    --memo-page: #e8e6e1;
    --memo-panel: #f7f5f1;
    --memo-red: #b22a1d;
    --memo-amber: #c98b2e;
    --memo-serif: "IBM Plex Serif", Georgia, "Times New Roman", serif;
    --memo-sans: "IBM Plex Sans", Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    --memo-mono: "IBM Plex Mono", "SFMono-Regular", Consolas, monospace;
  }

  * { box-sizing: border-box; }

  body {
    margin: 0;
    background: var(--memo-page);
    color: var(--memo-ink);
    font-family: var(--memo-sans);
    -webkit-font-smoothing: antialiased;
  }

  .downloaded-report-shell {
    min-height: 100vh;
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 18px;
    padding: 44px 0 60px;
  }

  .downloaded-report-chrome {
    width: min(816px, calc(100vw - 28px));
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 18px;
    color: #8a867f;
    font-family: var(--memo-mono);
    font-size: 10px;
    letter-spacing: 0.16em;
    line-height: 1.4;
    text-transform: uppercase;
  }

  .downloaded-report-brand {
    display: inline-flex;
    align-items: center;
    gap: 10px;
    min-width: 0;
    color: var(--memo-ink);
    font-weight: 600;
  }

  .downloaded-report-brand-mark {
    width: 30px;
    height: 30px;
    display: inline-grid;
    place-items: center;
    flex: 0 0 auto;
    border: 1.5px solid var(--memo-ink);
    color: #ffffff;
    background: var(--memo-red);
    font-family: var(--memo-mono);
    font-size: 10px;
    font-weight: 700;
    letter-spacing: 0;
  }

  .downloaded-report-card {
    width: min(816px, calc(100vw - 28px));
    min-height: 1056px;
    padding: 60px 64px 48px;
    border: 0;
    border-radius: 0;
    background: #ffffff;
    box-shadow: 0 2px 10px rgba(0, 0, 0, 0.14);
  }

  .downloaded-report-card::before {
    content: "Valuation Desk / Equity Research";
    display: flex;
    justify-content: space-between;
    margin-bottom: 14px;
    padding-bottom: 14px;
    border-bottom: 1.5px solid var(--memo-ink);
    color: #8a867f;
    font-family: var(--memo-mono);
    font-size: 10px;
    letter-spacing: 0.16em;
    text-transform: uppercase;
  }

  .report-markdown {
    counter-reset: memo-section;
    color: var(--memo-body);
    font-size: 14.5px;
    line-height: 1.65;
  }

  .report-markdown > :first-child { margin-top: 0; }
  .report-markdown > :last-child { margin-bottom: 0; }

  .report-markdown h1 {
    max-width: 590px;
    margin: 0 0 14px;
    color: var(--memo-ink);
    font-family: var(--memo-serif);
    font-size: 52px;
    line-height: 1.02;
    font-weight: 600;
    letter-spacing: -0.02em;
  }

  .report-markdown h1 + p {
    max-width: 620px;
    color: #3a3e44;
    font-family: var(--memo-serif);
    font-size: 21px;
    line-height: 1.35;
  }

  .report-markdown h2 {
    position: relative;
    counter-increment: memo-section;
    margin: 34px 0 18px;
    padding: 0 0 8px 34px;
    border-bottom: 1.5px solid var(--memo-ink);
    color: var(--memo-ink);
    font-family: var(--memo-serif);
    font-size: 21px;
    line-height: 1.2;
    font-weight: 600;
    letter-spacing: -0.01em;
    text-transform: none;
  }

  .report-markdown h2::before {
    content: counter(memo-section, decimal-leading-zero);
    position: absolute;
    left: 0;
    top: 3px;
    color: var(--memo-red);
    font-family: var(--memo-mono);
    font-size: 11px;
    font-weight: 600;
    letter-spacing: 0.12em;
  }

  .report-markdown h3 {
    margin: 22px 0 8px;
    color: var(--memo-ink);
    font-size: 15px;
    font-weight: 600;
  }

  .report-markdown p {
    margin: 0 0 14px;
    color: var(--memo-body);
    text-wrap: pretty;
  }

  .report-markdown strong { color: var(--memo-ink); }

  .report-markdown ul,
  .report-markdown ol {
    margin: 0 0 16px;
    padding-left: 22px;
  }

  .report-markdown li { margin: 6px 0; }

  .report-markdown .md-table-wrap {
    margin: 16px 0 24px;
    overflow-x: auto;
    border: 1px solid var(--memo-line);
    border-radius: 0;
    background: #ffffff;
  }

  .report-markdown table {
    width: 100%;
    border-spacing: 0;
    border-collapse: collapse;
  }

  .report-markdown th,
  .report-markdown td {
    padding: 10px 8px;
    border-bottom: 1px solid #ece9e3;
    text-align: left;
    vertical-align: top;
    font-size: 12.5px;
    line-height: 1.45;
  }

  .report-markdown th {
    border-bottom: 1.5px solid var(--memo-ink);
    color: var(--memo-muted);
    background: #ffffff;
    font-family: var(--memo-mono);
    font-size: 10px;
    font-weight: 600;
    letter-spacing: 0.08em;
    text-transform: uppercase;
  }

  .report-markdown td {
    color: var(--memo-body);
    font-family: var(--memo-mono);
    font-size: 12px;
  }

  .report-markdown tr:last-child td { border-bottom: 0; }

  .report-markdown blockquote {
    margin: 18px 0 22px;
    padding: 15px 18px;
    border: 1.5px solid var(--memo-ink);
    border-left: 5px solid var(--memo-red);
    border-radius: 0;
    color: var(--memo-ink);
    background: var(--memo-panel);
  }

  .report-markdown blockquote p:last-child { margin-bottom: 0; }

  .report-markdown code {
    padding: 2px 5px;
    border-radius: 0;
    color: var(--memo-ink);
    background: var(--memo-panel);
    font-family: var(--memo-mono);
    font-size: 0.92em;
  }

  .report-markdown hr {
    margin: 24px 0;
    border: 0;
    border-top: 1.5px solid var(--memo-ink);
  }

  .downloaded-report-footer {
    width: min(816px, calc(100vw - 28px));
    color: #8a867f;
    font-family: var(--memo-mono);
    font-size: 9px;
    letter-spacing: 0.07em;
    line-height: 1.5;
    text-align: center;
    text-transform: uppercase;
  }

  @media (max-width: 720px) {
    .downloaded-report-shell { padding: 18px 0 32px; }
    .downloaded-report-chrome { align-items: flex-start; flex-direction: column; letter-spacing: 0.08em; }
    .downloaded-report-card { min-height: 0; padding: 34px 24px; }
    .report-markdown h1 { font-size: 38px; }
    .report-markdown h2 { padding-left: 30px; font-size: 19px; }
  }

  @media print {
    @page { size: letter; margin: 0; }
    body { background: #ffffff !important; }
    .downloaded-report-shell { display: block; width: 100%; min-height: 0; padding: 0; }
    .downloaded-report-chrome,
    .downloaded-report-footer { display: none; }
    .downloaded-report-card {
      width: 100%;
      min-height: 100vh;
      padding: 0.62in 0.66in 0.5in;
      box-shadow: none;
    }
    .report-markdown h2 { break-after: avoid; page-break-after: avoid; }
    .report-markdown table,
    .report-markdown blockquote { break-inside: avoid; page-break-inside: avoid; }
  }
`;

const PDF_PAGE = {
  width: 612,
  height: 792,
  marginX: 48,
  bodyTop: 690,
  bodyBottom: 58,
  coverBodyTop: 438,
};

const PDF_COLORS = {
  ink: '0.086 0.098 0.110',
  body: '0.137 0.149 0.169',
  muted: '0.361 0.376 0.400',
  faint: '0.604 0.588 0.565',
  line: '0.890 0.878 0.851',
  softLine: '0.925 0.914 0.890',
  panel: '0.969 0.961 0.945',
  panelDeep: '0.812 0.792 0.749',
  red: '0.698 0.165 0.114',
  amber: '0.788 0.545 0.180',
  white: '1 1 1',
};

const PDF_FONTS = {
  regular: 'F1',
  bold: 'F2',
  serif: 'F3',
  serifBold: 'F4',
  mono: 'F5',
  monoBold: 'F6',
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
    drawFooter(page.commands, sourceText, index + 1, pages.length);
  });

  return renderPdfDocument(pages);
}

function buildPdfPages(markdown, generatedAt) {
  const title = reportTitle(markdown);
  const reportKind = inferReportKind(title, markdown);
  const ticker = inferTicker(title, markdown);
  const signal = inferSignal(markdown);
  const metricCards = extractMetricCards(markdown);
  const blocks = markdownToPdfBlocks(markdown);
  const contentBlocks = blocks.filter((block, index) => !(index === 0 && block.type === 'heading' && block.level === 1));
  const pages = [];
  let sectionNumber = 0;
  let currentSection = 'MEMO';
  let currentPage = createCoverPage({ title, reportKind, ticker, signal, metricCards, generatedAt });

  pages.push(currentPage);

  const addPage = (sectionLabel = currentSection) => {
    currentPage = createPdfPage({ title, reportKind, sectionLabel, generatedAt });
    pages.push(currentPage);
  };

  const ensureSpace = (height, gapBefore = 0, sectionLabel = currentSection) => {
    if (currentPage.y - gapBefore - height < PDF_PAGE.bodyBottom) {
      addPage(sectionLabel);
      return;
    }
    currentPage.y -= gapBefore;
  };

  contentBlocks.forEach((block) => {
    if (block.type === 'space') {
      currentPage.y = Math.max(PDF_PAGE.bodyBottom, currentPage.y - block.height);
      return;
    }

    if (block.type === 'heading') {
      if (block.level === 2) {
        sectionNumber += 1;
        currentSection = stripMarkdown(block.text).toUpperCase();
        drawPdfSectionHeading({ currentPageRef: () => currentPage, block, sectionNumber, ensureSpace });
        return;
      }

      drawPdfSubheading({ currentPageRef: () => currentPage, block, ensureSpace });
      return;
    }

    if (block.type === 'table') {
      drawPdfTable({ block, currentPageRef: () => currentPage, setCurrentPage: (page) => { currentPage = page; }, addPage });
      return;
    }

    if (block.type === 'list') {
      drawPdfList({ block, currentPageRef: () => currentPage, addPage, ensureSpace });
      return;
    }

    if (block.type === 'quote') {
      drawPdfQuote({ block, currentPageRef: () => currentPage, addPage, ensureSpace });
      return;
    }

    drawPdfParagraph({ block, currentPageRef: () => currentPage, addPage, ensureSpace });
  });

  return pages;
}

function createCoverPage({ title, reportKind, ticker, signal, metricCards, generatedAt }) {
  const commands = [];
  const left = PDF_PAGE.marginX;
  const right = PDF_PAGE.width - PDF_PAGE.marginX;

  drawText(commands, 'VALUATION DESK / EQUITY RESEARCH', left, 746, 7.4, 'monoBold', PDF_COLORS.faint);
  drawRightText(commands, 'CONFIDENTIAL / INTERNAL USE', right, 746, 7.4, 'monoBold', PDF_COLORS.faint);
  drawLine(commands, left, 728, right, 728, PDF_COLORS.ink, 1.1);

  drawText(commands, ticker ? `PUBLIC EQUITY / ${ticker}` : 'PUBLIC EQUITY / RESEARCH MEMO', left, 696, 8.6, 'monoBold', PDF_COLORS.red);
  const afterTitleY = drawWrappedText(commands, title, left, 672, 340, {
    size: 34,
    lineHeight: 36,
    font: 'serifBold',
    color: PDF_COLORS.ink,
    maxLines: 3,
  });
  drawText(commands, reportKind, left, afterTitleY - 8, 13, 'serif', PDF_COLORS.muted);

  drawText(commands, 'GENERATED', 420, 692, 7.4, 'monoBold', PDF_COLORS.faint);
  drawText(commands, generatedAt, 420, 677, 8, 'mono', PDF_COLORS.muted);
  drawText(commands, 'FORECAST BASIS', 420, 654, 7.4, 'monoBold', PDF_COLORS.faint);
  drawText(commands, reportKind.includes('DCF') ? '5-YR MODEL VIEW' : 'ANALYST SYNTHESIS', 420, 639, 8, 'monoBold', PDF_COLORS.ink);

  drawHeroBand(commands, signal, 574);
  drawMetricStrip(commands, metricCards, 500);

  drawText(commands, '01', left, 456, 8.5, 'monoBold', PDF_COLORS.red);
  drawText(commands, 'Investment Thesis', left + 26, 456, 15.5, 'serifBold', PDF_COLORS.ink);
  drawLine(commands, left, 446, right, 446, PDF_COLORS.ink, 1.1);

  return { commands, y: PDF_PAGE.coverBodyTop };
}

function createPdfPage({ title, sectionLabel, generatedAt }) {
  const commands = [];
  const left = PDF_PAGE.marginX;
  const right = PDF_PAGE.width - PDF_PAGE.marginX;

  drawText(commands, headerTitle(title), left, 746, 7.4, 'monoBold', PDF_COLORS.faint);
  drawRightText(commands, sectionLabel || 'ANALYSIS', right, 746, 7.4, 'monoBold', PDF_COLORS.faint);
  drawText(commands, `Generated ${generatedAt}`, left, 724, 7, 'mono', PDF_COLORS.faint);
  drawLine(commands, left, 712, right, 712, PDF_COLORS.line, 0.8);

  return { commands, y: PDF_PAGE.bodyTop };
}

function drawHeroBand(commands, signal, y) {
  const left = PDF_PAGE.marginX;
  const width = PDF_PAGE.width - PDF_PAGE.marginX * 2;
  const height = 74;
  const signalColor = signal === 'BEARISH' ? PDF_COLORS.red : signal === 'BULLISH' ? '0.086 0.478 0.259' : PDF_COLORS.ink;

  drawRect(commands, left, y, width, height, { stroke: PDF_COLORS.ink, strokeWidth: 1.1 });
  drawRect(commands, left, y, 148, height, { fill: signalColor });
  drawText(commands, signal === 'ANALYSIS' ? 'REPORT MODE' : 'MODEL SIGNAL', left + 18, y + 51, 7.3, 'monoBold', PDF_COLORS.white);
  drawText(commands, signal, left + 18, y + 25, 24, 'serifBold', PDF_COLORS.white);

  const labels = ['DOCUMENT', 'SOURCE', 'STATUS'];
  const values = ['RESEARCH MEMO', 'PUBLIC DATA', 'INTERNAL USE'];
  const cellWidth = (width - 148) / 3;

  labels.forEach((label, index) => {
    const cellX = left + 148 + index * cellWidth;
    if (index > 0) {
      drawLine(commands, cellX, y, cellX, y + height, PDF_COLORS.line, 0.7);
    }
    drawText(commands, label, cellX + 16, y + 50, 7, 'monoBold', PDF_COLORS.muted);
    drawWrappedText(commands, values[index], cellX + 16, y + 30, cellWidth - 28, {
      size: 11.5,
      lineHeight: 13,
      font: 'monoBold',
      color: index === 0 ? PDF_COLORS.red : PDF_COLORS.ink,
      maxLines: 2,
    });
  });
}

function drawMetricStrip(commands, cards, y) {
  const left = PDF_PAGE.marginX;
  const width = PDF_PAGE.width - PDF_PAGE.marginX * 2;
  const height = 56;
  const count = 4;
  const cellWidth = width / count;

  drawRect(commands, left, y, width, height, { fill: PDF_COLORS.line, stroke: PDF_COLORS.line, strokeWidth: 0.5 });

  cards.slice(0, count).forEach((card, index) => {
    const cellX = left + index * cellWidth;
    drawRect(commands, cellX + 0.5, y + 0.5, cellWidth - 1, height - 1, { fill: PDF_COLORS.panel });
    drawWrappedText(commands, card.label.toUpperCase(), cellX + 12, y + 39, cellWidth - 24, {
      size: 6.6,
      lineHeight: 7.5,
      font: 'monoBold',
      color: PDF_COLORS.faint,
      maxLines: 1,
    });
    drawWrappedText(commands, card.value, cellX + 12, y + 20, cellWidth - 24, {
      size: 13,
      lineHeight: 14,
      font: 'monoBold',
      color: index === 0 ? PDF_COLORS.red : PDF_COLORS.ink,
      maxLines: 1,
    });
    if (card.note) {
      drawWrappedText(commands, card.note, cellX + 12, y + 8, cellWidth - 24, {
        size: 6.8,
        lineHeight: 7.5,
        font: 'mono',
        color: PDF_COLORS.faint,
        maxLines: 1,
      });
    }
  });
}

function drawPdfSectionHeading({ currentPageRef, block, sectionNumber, ensureSpace }) {
  const pageBeforeBreak = currentPageRef();
  ensureSpace(34, pageBeforeBreak.y < PDF_PAGE.coverBodyTop ? 8 : 16, stripMarkdown(block.text).toUpperCase());
  const currentPage = currentPageRef();
  const y = currentPage.y;
  drawText(currentPage.commands, String(sectionNumber).padStart(2, '0'), PDF_PAGE.marginX, y, 8.5, 'monoBold', PDF_COLORS.red);
  drawWrappedText(currentPage.commands, stripMarkdown(block.text), PDF_PAGE.marginX + 26, y + 1, 390, {
    size: 15.5,
    lineHeight: 17,
    font: 'serifBold',
    color: PDF_COLORS.ink,
    maxLines: 2,
  });
  drawLine(currentPage.commands, PDF_PAGE.marginX, y - 10, PDF_PAGE.width - PDF_PAGE.marginX, y - 10, PDF_COLORS.ink, 1.1);
  currentPage.y = y - 27;
}

function drawPdfSubheading({ currentPageRef, block, ensureSpace }) {
  const text = stripMarkdown(block.text);
  const size = block.level === 1 ? 21 : block.level === 3 ? 12.2 : 10.8;
  const font = block.level === 1 ? 'serifBold' : 'bold';
  const lines = wrapPdfText(text, size, PDF_PAGE.width - PDF_PAGE.marginX * 2, font);
  const lineHeight = block.level === 1 ? 24 : 15;
  ensureSpace(lines.length * lineHeight + 8, block.level === 1 ? 8 : 12);
  const currentPage = currentPageRef();
  lines.forEach((line) => {
    drawText(currentPage.commands, line, PDF_PAGE.marginX, currentPage.y, size, font, PDF_COLORS.ink);
    currentPage.y -= lineHeight;
  });
  currentPage.y -= 2;
}

function drawPdfParagraph({ block, currentPageRef, addPage, ensureSpace }) {
  let currentPage = currentPageRef();
  const size = block.emphasis ? 10.8 : 10.2;
  const font = block.emphasis ? 'serif' : 'regular';
  const color = block.emphasis ? PDF_COLORS.ink : PDF_COLORS.body;
  const lineHeight = block.emphasis ? 15.4 : 14.4;
  const lines = wrapPdfText(block.text, size, PDF_PAGE.width - PDF_PAGE.marginX * 2, font);

  ensureSpace(Math.min(lines.length, 2) * lineHeight, block.gapBefore || 4);
  currentPage = currentPageRef();

  lines.forEach((line) => {
    if (currentPage.y - lineHeight < PDF_PAGE.bodyBottom) {
      addPage();
      currentPage = currentPageRef();
    }
    drawText(currentPage.commands, line, PDF_PAGE.marginX, currentPage.y, size, font, color);
    currentPage.y -= lineHeight;
  });

  currentPage.y -= block.gapAfter || 2;
}

function drawPdfList({ block, currentPageRef, addPage, ensureSpace }) {
  let currentPage = currentPageRef();
  const lineHeight = 13.8;
  ensureSpace(22, 4);
  currentPage = currentPageRef();

  block.items.forEach((item, index) => {
    const marker = block.ordered ? `${index + 1}.` : '-';
    const lines = wrapPdfText(item, 9.7, PDF_PAGE.width - PDF_PAGE.marginX * 2 - 30, 'regular');
    lines.forEach((line, lineIndex) => {
      if (currentPage.y - lineHeight < PDF_PAGE.bodyBottom) {
        addPage();
        currentPage = currentPageRef();
      }
      if (lineIndex === 0) {
        drawText(currentPage.commands, marker, PDF_PAGE.marginX + 8, currentPage.y, 9.7, 'monoBold', PDF_COLORS.red);
      }
      drawText(currentPage.commands, line, PDF_PAGE.marginX + 28, currentPage.y, 9.7, 'regular', PDF_COLORS.body);
      currentPage.y -= lineHeight;
    });
    currentPage.y -= 1.5;
  });

  currentPage.y -= 4;
}

function drawPdfQuote({ block, currentPageRef, addPage, ensureSpace }) {
  let currentPage = currentPageRef();
  const width = PDF_PAGE.width - PDF_PAGE.marginX * 2;
  const lines = wrapPdfText(block.text, 9.8, width - 34, 'regular');
  const height = lines.length * 13.8 + 22;

  if (height > PDF_PAGE.bodyTop - PDF_PAGE.bodyBottom) {
    drawPdfParagraph({ block: { ...block, text: block.text }, currentPageRef, addPage, ensureSpace });
    return;
  }

  ensureSpace(height, 8);
  currentPage = currentPageRef();
  const y = currentPage.y - height + 8;
  drawRect(currentPage.commands, PDF_PAGE.marginX, y, width, height, {
    fill: PDF_COLORS.panel,
    stroke: PDF_COLORS.ink,
    strokeWidth: 0.9,
  });
  drawRect(currentPage.commands, PDF_PAGE.marginX, y, 5, height, { fill: PDF_COLORS.red });
  let textY = currentPage.y - 8;
  lines.forEach((line) => {
    drawText(currentPage.commands, line, PDF_PAGE.marginX + 18, textY, 9.8, 'regular', PDF_COLORS.ink);
    textY -= 13.8;
  });
  currentPage.y = y - 10;
}

function drawPdfTable({ block, currentPageRef, setCurrentPage, addPage }) {
  let currentPage = currentPageRef();
  const width = PDF_PAGE.width - PDF_PAGE.marginX * 2;
  const rows = [block.header, ...block.rows].filter(Boolean);
  const columnCount = Math.min(Math.max(...rows.map((row) => row.length)), 5);
  const columnWidth = width / columnCount;
  const paddingX = 6;
  const lineHeight = 10.5;
  const fontSize = 7.5;

  const normalizedRows = rows.map((row) => Array.from({ length: columnCount }, (_, index) => row[index] || ''));
  const header = normalizedRows[0];
  const bodyRows = normalizedRows.slice(1);

  const drawRow = (row, rowIndex, isHeader) => {
    const cellLines = row.map((cell) => wrapPdfText(cell, fontSize, columnWidth - paddingX * 2, isHeader ? 'monoBold' : 'mono'));
    const rowHeight = Math.max(24, Math.max(...cellLines.map((lines) => lines.length)) * lineHeight + 12);

    if (currentPage.y - rowHeight < PDF_PAGE.bodyBottom) {
      addPage();
      currentPage = currentPageRef();
      setCurrentPage(currentPage);
      if (!isHeader && header?.length) {
        drawRow(header, -1, true);
      }
    }

    const y = currentPage.y - rowHeight;
    const fill = isHeader ? PDF_COLORS.white : rowIndex % 2 === 0 ? PDF_COLORS.white : PDF_COLORS.panel;
    drawRect(currentPage.commands, PDF_PAGE.marginX, y, width, rowHeight, { fill });
    drawLine(currentPage.commands, PDF_PAGE.marginX, y, PDF_PAGE.width - PDF_PAGE.marginX, y, isHeader ? PDF_COLORS.ink : PDF_COLORS.softLine, isHeader ? 1 : 0.55);

    row.forEach((cell, index) => {
      const x = PDF_PAGE.marginX + index * columnWidth;
      if (index > 0) {
        drawLine(currentPage.commands, x, y, x, y + rowHeight, PDF_COLORS.softLine, 0.45);
      }
      let textY = currentPage.y - 11;
      cellLines[index].forEach((line) => {
        drawText(
          currentPage.commands,
          line,
          x + paddingX,
          textY,
          fontSize,
          isHeader ? 'monoBold' : 'mono',
          isHeader ? PDF_COLORS.muted : PDF_COLORS.body,
        );
        textY -= lineHeight;
      });
    });

    currentPage.y = y;
  };

  if (currentPage.y - 34 < PDF_PAGE.bodyBottom) {
    addPage();
    currentPage = currentPageRef();
    setCurrentPage(currentPage);
  } else {
    currentPage.y -= 8;
  }

  drawRect(currentPage.commands, PDF_PAGE.marginX, currentPage.y - 1, width, 1, { fill: PDF_COLORS.ink });
  drawRow(header, -1, true);
  bodyRows.forEach((row, index) => drawRow(row, index, false));
  currentPage.y -= 14;
}

function drawFooter(commands, markdown, pageNumber, pageCount) {
  const left = PDF_PAGE.marginX;
  const right = PDF_PAGE.width - PDF_PAGE.marginX;
  const title = headerTitle(reportTitle(markdown));
  const note = 'Research output generated from public financial data and AI analysis. Not personalized investment advice.';
  const pageLabel = `${String(pageNumber).padStart(2, '0')} / ${String(pageCount).padStart(2, '0')}`;

  drawLine(commands, left, 44, right, 44, PDF_COLORS.line, 0.6);
  drawText(commands, title, left, 30, 6.8, 'monoBold', PDF_COLORS.faint);
  drawCenteredText(commands, 'BABOON ANALYST RESEARCH MEMO', PDF_PAGE.width / 2, 30, 6.8, 'monoBold', PDF_COLORS.faint);
  drawRightText(commands, pageLabel, right, 30, 6.8, 'monoBold', PDF_COLORS.faint);
  drawWrappedText(commands, note, left, 18, right - left, {
    size: 6.2,
    lineHeight: 7,
    font: 'mono',
    color: PDF_COLORS.faint,
    maxLines: 1,
  });
}

function markdownToPdfBlocks(markdown) {
  const blocks = [];
  const lines = String(markdown || '').replace(/\r\n?/g, '\n').split('\n');
  let index = 0;

  while (index < lines.length) {
    const rawLine = lines[index];
    const trimmed = rawLine.trim();

    if (!trimmed) {
      blocks.push({ type: 'space', height: 7 });
      index += 1;
      continue;
    }

    const heading = trimmed.match(/^(#{1,6})\s+(.+)$/);
    if (heading) {
      blocks.push({
        type: 'heading',
        level: heading[1].length,
        text: stripMarkdown(heading[2]),
      });
      index += 1;
      continue;
    }

    if (isMarkdownTableRow(trimmed) && isMarkdownTableSeparator(lines[index + 1]?.trim() || '')) {
      const header = parseMarkdownTableRow(trimmed);
      index += 2;
      const rows = [];
      while (index < lines.length && isMarkdownTableRow(lines[index].trim())) {
        rows.push(parseMarkdownTableRow(lines[index].trim()));
        index += 1;
      }
      blocks.push({ type: 'table', header, rows });
      continue;
    }

    const unordered = trimmed.match(/^[-*]\s+(.+)$/);
    const ordered = trimmed.match(/^(\d+)\.\s+(.+)$/);
    if (unordered || ordered) {
      const orderedList = Boolean(ordered);
      const items = [];

      while (index < lines.length) {
        const listLine = lines[index].trim();
        const itemMatch = orderedList ? listLine.match(/^(\d+)\.\s+(.+)$/) : listLine.match(/^[-*]\s+(.+)$/);
        if (!itemMatch) {
          break;
        }
        items.push(stripMarkdown(itemMatch[orderedList ? 2 : 1]));
        index += 1;
      }

      blocks.push({ type: 'list', ordered: orderedList, items });
      continue;
    }

    if (trimmed.startsWith('>')) {
      const quoteLines = [];
      while (index < lines.length && lines[index].trim().startsWith('>')) {
        quoteLines.push(lines[index].trim().replace(/^>\s?/, ''));
        index += 1;
      }
      blocks.push({ type: 'quote', text: stripMarkdown(quoteLines.join(' ')) });
      continue;
    }

    const paragraphLines = [trimmed];
    index += 1;
    while (index < lines.length) {
      const next = lines[index].trim();
      if (
        !next ||
        /^(#{1,6})\s+/.test(next) ||
        (isMarkdownTableRow(next) && isMarkdownTableSeparator(lines[index + 1]?.trim() || '')) ||
        /^[-*]\s+/.test(next) ||
        /^\d+\.\s+/.test(next) ||
        next.startsWith('>')
      ) {
        break;
      }
      paragraphLines.push(next);
      index += 1;
    }

    blocks.push({
      type: 'paragraph',
      text: stripMarkdown(paragraphLines.join(' ')),
      emphasis: paragraphLines.join(' ').length < 180 && /bottom line|executive view|thesis|summary/i.test(paragraphLines.join(' ')),
    });
  }

  return blocks;
}

function isMarkdownTableSeparator(line) {
  return /^\|?[\s:-]+\|[\s|:-]+$/.test(line) && /-{3,}/.test(line);
}

function isMarkdownTableRow(line) {
  return line.includes('|') && (line.startsWith('|') || line.endsWith('|') || /\s\|\s/.test(line));
}

function parseMarkdownTableRow(line) {
  return line
    .replace(/^\|/, '')
    .replace(/\|$/, '')
    .split('|')
    .map((cell) => stripMarkdown(cell))
    .filter((cell) => cell.length > 0);
}

function extractMetricCards(markdown) {
  const lines = String(markdown || '').replace(/\r\n?/g, '\n').split('\n');

  for (let index = 0; index < lines.length - 2; index += 1) {
    const row = lines[index].trim();
    const separator = lines[index + 1].trim();
    if (!isMarkdownTableRow(row) || !isMarkdownTableSeparator(separator)) {
      continue;
    }

    const rows = [];
    let rowIndex = index + 2;
    while (rowIndex < lines.length && isMarkdownTableRow(lines[rowIndex].trim())) {
      rows.push(parseMarkdownTableRow(lines[rowIndex].trim()));
      rowIndex += 1;
    }

    const cards = rows
      .filter((cells) => cells.length >= 2)
      .slice(0, 4)
      .map((cells) => ({
        label: cells[0],
        value: cells[1],
        note: cells.slice(2).join(' / '),
      }));

    if (cards.length) {
      return padMetricCards(cards);
    }
  }

  const sectionCount = (String(markdown || '').match(/^##\s+/gm) || []).length;
  return [
    { label: 'Report Type', value: inferReportKind(reportTitle(markdown), markdown).replace(' Memo', '') },
    { label: 'Sections', value: String(Math.max(sectionCount, 1)) },
    { label: 'Coverage', value: inferTicker(reportTitle(markdown), markdown) || 'Equity' },
    { label: 'Format', value: 'Research Memo' },
  ];
}

function padMetricCards(cards) {
  const fallback = [
    { label: 'Coverage', value: 'Equity' },
    { label: 'Format', value: 'Research Memo' },
    { label: 'Source', value: 'Public Data' },
  ];

  return [...cards, ...fallback].slice(0, 4);
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

function wrapPdfText(value, fontSize, maxWidth, font = 'regular') {
  const text = sanitizePdfText(value);
  const widthFactor = font === 'mono' || font === 'monoBold' ? 0.6 : font === 'serif' || font === 'serifBold' ? 0.5 : 0.52;
  const maxChars = Math.max(12, Math.floor(maxWidth / (fontSize * widthFactor)));
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

function drawWrappedText(commands, text, x, y, maxWidth, options = {}) {
  const {
    size = 10,
    lineHeight = size * 1.35,
    font = 'regular',
    color = PDF_COLORS.body,
    maxLines,
  } = options;
  let lines = wrapPdfText(text, size, maxWidth, font);

  if (maxLines && lines.length > maxLines) {
    lines = lines.slice(0, maxLines);
    const lastIndex = lines.length - 1;
    lines[lastIndex] = `${lines[lastIndex].replace(/\.*$/, '').slice(0, Math.max(0, lines[lastIndex].length - 3))}...`;
  }

  lines.forEach((line, index) => {
    drawText(commands, line, x, y - index * lineHeight, size, font, color);
  });

  return y - lines.length * lineHeight;
}

function drawText(commands, text, x, y, size, font, color) {
  commands.push(`${color} rg`);
  commands.push(`BT /${PDF_FONTS[font] || PDF_FONTS.regular} ${formatPdfNumber(size)} Tf ${formatPdfNumber(x)} ${formatPdfNumber(y)} Td (${escapePdfString(text)}) Tj ET`);
}

function drawRightText(commands, text, rightX, y, size, font, color) {
  drawText(commands, text, rightX - approximatePdfWidth(text, size, font), y, size, font, color);
}

function drawCenteredText(commands, text, centerX, y, size, font, color) {
  drawText(commands, text, centerX - approximatePdfWidth(text, size, font) / 2, y, size, font, color);
}

function drawLine(commands, x1, y1, x2, y2, color, width) {
  commands.push(`q ${color} RG ${formatPdfNumber(width)} w ${formatPdfNumber(x1)} ${formatPdfNumber(y1)} m ${formatPdfNumber(x2)} ${formatPdfNumber(y2)} l S Q`);
}

function drawRect(commands, x, y, width, height, options = {}) {
  const { fill, stroke, strokeWidth = 1 } = options;
  const parts = ['q'];

  if (fill) {
    parts.push(`${fill} rg`);
  }
  if (stroke) {
    parts.push(`${stroke} RG ${formatPdfNumber(strokeWidth)} w`);
  }

  parts.push(`${formatPdfNumber(x)} ${formatPdfNumber(y)} ${formatPdfNumber(width)} ${formatPdfNumber(height)} re`);
  parts.push(fill && stroke ? 'B' : fill ? 'f' : stroke ? 'S' : 'n');
  parts.push('Q');
  commands.push(parts.join(' '));
}

function renderPdfDocument(pages) {
  const pageRefs = pages.map((_, index) => `${9 + index * 2} 0 R`);
  const objects = [
    { id: 1, body: '<< /Type /Catalog /Pages 2 0 R >>' },
    { id: 2, body: `<< /Type /Pages /Kids [${pageRefs.join(' ')}] /Count ${pages.length} >>` },
    { id: 3, body: '<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>' },
    { id: 4, body: '<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold >>' },
    { id: 5, body: '<< /Type /Font /Subtype /Type1 /BaseFont /Times-Roman >>' },
    { id: 6, body: '<< /Type /Font /Subtype /Type1 /BaseFont /Times-Bold >>' },
    { id: 7, body: '<< /Type /Font /Subtype /Type1 /BaseFont /Courier >>' },
    { id: 8, body: '<< /Type /Font /Subtype /Type1 /BaseFont /Courier-Bold >>' },
  ];

  pages.forEach((page, index) => {
    const pageId = 9 + index * 2;
    const contentId = pageId + 1;
    const stream = page.commands.join('\n');

    objects.push({
      id: pageId,
      body: `<< /Type /Page /Parent 2 0 R /MediaBox [0 0 ${PDF_PAGE.width} ${PDF_PAGE.height}] /Resources << /Font << /F1 3 0 R /F2 4 0 R /F3 5 0 R /F4 6 0 R /F5 7 0 R /F6 8 0 R >> >> /Contents ${contentId} 0 R >>`,
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
    pdf += `${String(offsets[id] || 0).padStart(10, '0')} 00000 n \n`;
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

function approximatePdfWidth(text, fontSize, font = 'regular') {
  const widthFactor = font === 'mono' || font === 'monoBold' ? 0.6 : font === 'serif' || font === 'serifBold' ? 0.5 : 0.48;
  return sanitizePdfText(text).length * fontSize * widthFactor;
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
  const heading = String(markdown || '').match(/^#\s+(.+)$/m)?.[1]?.trim();
  return heading || 'Baboon Analyst Report';
}

function headerTitle(title) {
  return sanitizePdfText(title)
    .replace(/\s+/g, ' ')
    .toUpperCase()
    .slice(0, 54);
}

function inferReportKind(title, markdown) {
  const text = `${title} ${markdown || ''}`.toLowerCase();
  if (/\bdcf\b|discounted cash flow|valuation/.test(text)) {
    return 'Discounted Cash Flow Valuation Memo';
  }
  if (/deep analysis|investment thesis|thesis/.test(text)) {
    return 'Investment Research Memo';
  }
  if (/comparison|compare|versus|\bvs\b/.test(text)) {
    return 'Comparative Equity Research Memo';
  }
  return 'Equity Research Memo';
}

function inferTicker(title, markdown) {
  const text = `${title} ${markdown || ''}`;
  const parenthetical = text.match(/\(([A-Z][A-Z0-9.]{0,5})\)/)?.[1];
  if (parenthetical) {
    return parenthetical;
  }
  return text.match(/\b([A-Z]{1,5})(?:\s+Deep Analysis|\s+Investment Report|\s+Valuation|\s+DCF)\b/)?.[1] || '';
}

function inferSignal(markdown) {
  const text = String(markdown || '').toLowerCase();
  if (/\bbearish\b|significant downside|overvalued|downside risk|sell\b/.test(text)) {
    return 'BEARISH';
  }
  if (/\bbullish\b|significant upside|undervalued|upside potential|buy\b/.test(text)) {
    return 'BULLISH';
  }
  if (/\bneutral\b|\bhold\b|fairly valued|balanced view/.test(text)) {
    return 'NEUTRAL';
  }
  return 'ANALYSIS';
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
