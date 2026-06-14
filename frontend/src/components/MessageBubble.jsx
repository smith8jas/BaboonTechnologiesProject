import React from 'react';
import { Check, Copy, Download, Printer } from 'lucide-react';

import ReportMarkdown, { isReportContent } from './ReportMarkdown.jsx';
import { downloadReportPdf, printReport } from '../utils/reportExport.js';

export default function MessageBubble({ message }) {
  const [copied, setCopied] = React.useState(false);
  const [downloaded, setDownloaded] = React.useState(false);
  const reportRef = React.useRef(null);
  const isUser = message.role === 'user';
  const isError = message.tone === 'error';
  const isStreaming = Boolean(message.isStreaming);
  const thoughts = message.thoughts;
  const statusText = message.statusText;
  const hasThoughts = thoughts?.length > 0;
  const isReport = !isUser && !isError && isReportContent(message.content);
  const rowClass = isUser ? 'user-row' : 'assistant-row';
  const bubbleClass = isUser ? 'user-bubble' : isReport ? 'report-bubble' : 'assistant-bubble';

  async function copyMessage() {
    await navigator.clipboard.writeText(message.content);
    setCopied(true);
    window.setTimeout(() => setCopied(false), 1400);
  }

  function downloadReport() {
    downloadReportPdf(reportRef.current, message.content);
    setDownloaded(true);
    window.setTimeout(() => setDownloaded(false), 1400);
  }

  function saveReportAsPdf() {
    printReport(reportRef.current, message.content);
  }

  return (
    <div className={`message-row ${rowClass}`}>
      <div className={`bubble ${bubbleClass} ${isError ? 'error-bubble' : ''}`}>
        {!isUser && !isError && message.content && (
          <div className={isReport ? 'report-actions' : 'message-actions'}>
            {isReport && (
              <>
                <button type="button" onClick={downloadReport} title="Download report as PDF">
                  {downloaded ? <Check size={15} /> : <Download size={15} />}
                </button>
                <button type="button" onClick={saveReportAsPdf} title="Print report">
                  <Printer size={15} />
                </button>
              </>
            )}
            <button type="button" onClick={copyMessage} title="Copy response">
              {copied ? <Check size={15} /> : <Copy size={15} />}
            </button>
          </div>
        )}

        {isUser || isError ? (
          <p className="message-text">{message.content}</p>
        ) : (
          <>
            {hasThoughts && (
              <div className="thought-steps">
                {thoughts.map((thought, i) => (
                  <div
                    key={i}
                    className={`thought-step${isStreaming && i === thoughts.length - 1 ? ' thought-step-active' : ''}`}
                  >
                    <span className="thought-dot" />
                    {thought}
                  </div>
                ))}
              </div>
            )}
            {message.content ? (
              <div ref={isReport ? reportRef : undefined}>
                <ReportMarkdown content={message.content} isReport={isReport} />
              </div>
            ) : isStreaming ? (
              <div className="inline-typing" aria-label={statusText || 'Analyst is writing'}>
                {statusText ? <span className="status-label">{statusText}</span> : null}
                <span />
                <span />
                <span />
              </div>
            ) : null}
          </>
        )}
        {message.timestamp && (
          <time dateTime={message.timestamp}>{formatTime(message.timestamp)}</time>
        )}
      </div>
    </div>
  );
}

function formatTime(timestamp) {
  const date = new Date(timestamp);
  if (Number.isNaN(date.getTime())) {
    return '';
  }
  return new Intl.DateTimeFormat(undefined, {
    hour: 'numeric',
    minute: '2-digit',
  }).format(date);
}
