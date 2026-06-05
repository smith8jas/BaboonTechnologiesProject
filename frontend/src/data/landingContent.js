import {
  BarChart3,
  Bot,
  FileText,
  LineChart,
  PanelTop,
  Ruler,
} from 'lucide-react';

export const navItems = [
  { label: 'Product', path: '#product-preview' },
  { label: 'Capabilities', path: '#capabilities' },
  { label: 'Examples', path: '#example-questions' },
];

const heroReportMarkdown = `# Apple (AAPL) Investment Report

## Executive View
Apple remains a cash-rich compounder with durable margins and an expanding services mix. The franchise is high quality, but the valuation already prices in continued execution.

## Financial Snapshot
| Metric | Value | YoY |
| --- | --- | --- |
| Revenue | $391.0B | +2.0% |
| Gross margin | 46.2% | +210 bps |
| Free cash flow | $108.8B | +9.3% |

## Bottom Line
A durable franchise trading at a full price. Watch free cash flow, buyback pace, and services growth.`;

export const heroReportMessage = {
  id: 'hero-sample-report',
  role: 'assistant',
  content: heroReportMarkdown,
  // No timestamp: the hero sample intentionally hides the message time.
};

export const capabilityCards = [
  {
    label: 'STATEMENTS',
    title: 'Financial Statements',
    body: 'Income, balance sheet, and cash flow data from public filings.',
    icon: PanelTop,
  },
  {
    label: 'RATIOS',
    title: 'Ratios & Growth',
    body: 'Liquidity, profitability, leverage, and growth metrics calculated automatically.',
    icon: Ruler,
  },
  {
    label: 'VALUATION',
    title: 'DCF Valuation',
    body: 'Discounted cash flow models with assumptions prepared for deeper review.',
    icon: LineChart,
  },
  {
    label: 'AGENT',
    title: 'AI Research Chat',
    body: 'Ask questions in plain language and get structured analyst-style responses.',
    icon: Bot,
  },
  {
    label: 'REPORTS',
    title: 'Report-Style Output',
    body: 'Formatted research documents ready for review or future download workflows.',
    icon: FileText,
  },
];

export const promptExamples = [
  'Build an investor thesis for AAPL',
  'Run a DCF valuation for MSFT',
  'Compare NVDA and AMD on growth and margins',
  "Summarize Tesla's risks and current valuation",
  "What's the P/E and EV/EBITDA for Google?",
  "Analyze Amazon's free cash flow trend",
];

export const productPromptChips = [
  'Build an investor thesis for AAPL',
  'Run a DCF for TSLA',
  'Compare NVDA and AMD growth',
];

export const chatPromptChips = [
  'Thesis: AAPL',
  'DCF: TSLA',
  'Compare: NVDA vs AMD',
  'Risks: MSFT',
];

export const workflowSteps = [
  {
    number: '01',
    title: 'Ask',
    body: 'Type a research question or company ticker.',
  },
  {
    number: '02',
    title: 'Fetch',
    body: 'Backend tools pull public financial data and market information.',
  },
  {
    number: '03',
    title: 'Analyze',
    body: 'The AI agent routes tools, runs calculations, and interprets the results.',
  },
  {
    number: '04',
    title: 'Report',
    body: 'You receive a structured investment research document.',
  },
];

export const trustStatements = [
  {
    title: 'Powered by public financial data',
    icon: BarChart3,
  },
  {
    title: 'Built for research, not trading signals',
    icon: FileText,
  },
  {
    title: 'Not financial advice',
    icon: Ruler,
  },
];
