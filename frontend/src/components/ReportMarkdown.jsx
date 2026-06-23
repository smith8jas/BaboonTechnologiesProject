import React from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';

const remarkPlugins = [[remarkGfm, { singleTilde: false }]];

const markdownComponents = {
  // Wrap tables so they can scroll horizontally while still filling the bubble width.
  table: ({ node, ...props }) => (
    <div className="md-table-wrap">
      <table {...props} />
    </div>
  ),
};

export default function ReportMarkdown({ content, isReport }) {
  return (
    <article className={isReport ? 'report-markdown' : 'assistant-markdown'} data-pdf-report={isReport || undefined}>
      <ReactMarkdown remarkPlugins={remarkPlugins} components={markdownComponents}>
        {content}
      </ReactMarkdown>
    </article>
  );
}

export function isReportContent(content) {
  return (
    /^# .*\b(report|thesis|analysis|valuation)\b/im.test(content) ||
    /^## (Executive View|Key Findings|Financial Snapshot|Valuation View|Risks and Unknowns|Bottom Line)/im.test(content) ||
    /^\|.+\|\s*$/m.test(content)
  );
}
