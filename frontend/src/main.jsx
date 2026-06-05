import React from 'react';
import { createRoot } from 'react-dom/client';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import {
  Activity,
  ArrowRight,
  BarChart3,
  Bot,
  BrainCircuit,
  Circle,
  LineChart,
  MessageSquarePlus,
  PanelTop,
  RotateCcw,
  Send,
  Sparkles,
  User,
} from 'lucide-react';

import heroImage from './assets/valuation-hero.png';
import './styles.css';

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? 'http://127.0.0.1:8000';
const STORAGE_KEY = 'baboon-chat-state';

const navItems = [
  { label: 'Features', path: '/' },
  { label: 'Chat', path: '/chat' },
];

const capabilities = [
  {
    title: 'Financial statements',
    body: 'Normalized SEC filing data for historical income statements, balance sheets, cash flows, and share counts.',
    icon: PanelTop,
  },
  {
    title: 'Ratios and growth',
    body: 'Liquidity, solvency, profitability, and year-over-year trend calculations from the same backend pipeline.',
    icon: BarChart3,
  },
  {
    title: 'DCF valuation',
    body: 'Market data, sector assumptions, derived inputs, and intrinsic value output through a valuation endpoint.',
    icon: LineChart,
  },
  {
    title: 'Agent research',
    body: 'A chat interface connected to the LangGraph analyst that can call the valuation tools behind the scenes.',
    icon: BrainCircuit,
  },
];

const sampleQuestions = [
  'Build an investor thesis for NVDA.',
  'Compare Apple liquidity and profitability over five years.',
  'Run a DCF valuation for Tesla.',
];

const initialMessages = [
  {
    id: crypto.randomUUID(),
    role: 'assistant',
    content: 'Bring me a public company and I will build the investment case from the data.',
    timestamp: new Date().toISOString(),
  },
];

function loadState() {
  try {
    const saved = JSON.parse(localStorage.getItem(STORAGE_KEY) ?? 'null');
    if (saved?.messages?.length) {
      return saved;
    }
  } catch {
    localStorage.removeItem(STORAGE_KEY);
  }

  return {
    threadId: null,
    messages: initialMessages,
  };
}

function App() {
  const [path, setPath] = React.useState(() => window.location.pathname);
  const [threadId, setThreadId] = React.useState(() => loadState().threadId);
  const [messages, setMessages] = React.useState(() => loadState().messages);
  const [draft, setDraft] = React.useState('');
  const [isSending, setIsSending] = React.useState(false);
  const [apiStatus, setApiStatus] = React.useState('checking');
  const messagesEndRef = React.useRef(null);

  React.useEffect(() => {
    function handlePopState() {
      setPath(window.location.pathname);
    }

    window.addEventListener('popstate', handlePopState);
    return () => window.removeEventListener('popstate', handlePopState);
  }, []);

  React.useEffect(() => {
    localStorage.setItem(STORAGE_KEY, JSON.stringify({ threadId, messages }));
  }, [threadId, messages]);

  React.useEffect(() => {
    let cancelled = false;

    async function checkHealth() {
      try {
        const response = await fetch(`${API_BASE_URL}/health`);
        if (!cancelled) {
          setApiStatus(response.ok ? 'online' : 'offline');
        }
      } catch {
        if (!cancelled) {
          setApiStatus('offline');
        }
      }
    }

    checkHealth();
    const intervalId = window.setInterval(checkHealth, 15000);

    return () => {
      cancelled = true;
      window.clearInterval(intervalId);
    };
  }, []);

  React.useEffect(() => {
    if (path === '/chat') {
      messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
    }
  }, [messages, isSending, path]);

  function navigate(nextPath) {
    if (nextPath === path) {
      return;
    }

    window.history.pushState({}, '', nextPath);
    setPath(nextPath);
  }

  async function sendMessage(event, overrideText) {
    event?.preventDefault();
    const text = (overrideText ?? draft).trim();

    if (!text || isSending) {
      return;
    }

    if (path !== '/chat') {
      navigate('/chat');
    }

    const userMessage = {
      id: crypto.randomUUID(),
      role: 'user',
      content: text,
      timestamp: new Date().toISOString(),
    };

    setDraft('');
    setIsSending(true);
    setMessages((current) => [...current, userMessage]);

    try {
      const response = await fetch(`${API_BASE_URL}/agent/chat`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          message: text,
          thread_id: threadId,
        }),
      });

      const payload = await response.json().catch(() => ({}));

      if (!response.ok) {
        throw new Error(readError(payload) || `Request failed with ${response.status}`);
      }

      setThreadId(payload.thread_id);
      setMessages((current) => [
        ...current,
        {
          id: crypto.randomUUID(),
          role: 'assistant',
          content: payload.response || 'I did not receive a response from the analyst agent.',
          timestamp: new Date().toISOString(),
        },
      ]);
    } catch (error) {
      setMessages((current) => [
        ...current,
        {
          id: crypto.randomUUID(),
          role: 'assistant',
          content: `I could not reach the backend cleanly. ${error.message}`,
          timestamp: new Date().toISOString(),
          tone: 'error',
        },
      ]);
    } finally {
      setIsSending(false);
    }
  }

  function resetChat() {
    const fresh = {
      threadId: null,
      messages: initialMessages.map((message) => ({
        ...message,
        id: crypto.randomUUID(),
        timestamp: new Date().toISOString(),
      })),
    };

    setThreadId(fresh.threadId);
    setMessages(fresh.messages);
  }

  const activePath = path === '/chat' ? '/chat' : '/';

  return (
    <main className="site-shell">
      <Navbar
        activePath={activePath}
        apiStatus={apiStatus}
        navigate={navigate}
      />

      {activePath === '/chat' ? (
        <ChatPage
          draft={draft}
          isSending={isSending}
          messages={messages}
          messagesEndRef={messagesEndRef}
          resetChat={resetChat}
          sendMessage={sendMessage}
          setDraft={setDraft}
          threadId={threadId}
        />
      ) : (
        <LandingPage navigate={navigate} sendMessage={sendMessage} />
      )}
    </main>
  );
}

function Navbar({ activePath, apiStatus, navigate }) {
  return (
    <header className="navbar">
      <button className="nav-brand" type="button" onClick={() => navigate('/')}>
        <span className="brand-mark" aria-hidden="true">
          <Activity size={22} strokeWidth={2.4} />
        </span>
        <span>Baboon Analyst</span>
      </button>

      <nav aria-label="Primary navigation">
        {navItems.map((item) => (
          <button
            key={item.path}
            className={activePath === item.path ? 'active' : ''}
            type="button"
            onClick={() => navigate(item.path)}
          >
            {item.label}
          </button>
        ))}
      </nav>

      <div className={`status-pill ${apiStatus}`} aria-live="polite">
        <Circle size={9} fill="currentColor" strokeWidth={0} />
        <span>{apiStatus}</span>
      </div>
    </header>
  );
}

function LandingPage({ navigate, sendMessage }) {
  return (
    <div className="landing-page">
      <section
        className="hero-section"
        style={{ backgroundImage: `linear-gradient(180deg, rgba(9, 11, 14, 0.78), rgba(9, 11, 14, 0.9)), url(${heroImage})` }}
      >
        <div className="hero-content">
          <div className="eyebrow">
            <Sparkles size={16} />
            <span>Agentic public-company research</span>
          </div>
          <h1>Analyze faster. Invest with more context.</h1>
          <p>
            One workspace for SEC financials, market data, growth rates, ratios, DCF output,
            and an AI analyst that can move from question to thesis.
          </p>
          <div className="hero-actions">
            <button className="primary-action" type="button" onClick={() => navigate('/chat')}>
              <span>Start analysis</span>
              <ArrowRight size={18} />
            </button>
            <button
              className="secondary-action"
              type="button"
              onClick={() => sendMessage(null, 'Build an investor thesis for AAPL.')}
            >
              <span>Try AAPL thesis</span>
            </button>
          </div>
          <div className="proof-row" aria-label="Product promises">
            <span>Public filings</span>
            <span>DCF engine</span>
            <span>Agent chat</span>
          </div>
        </div>
      </section>

      <section className="stats-section" aria-label="Platform metrics">
        <div>
          <strong>5</strong>
          <span>financial years</span>
        </div>
        <div>
          <strong>3</strong>
          <span>ratio families</span>
        </div>
        <div>
          <strong>DCF</strong>
          <span>valuation engine</span>
        </div>
        <div>
          <strong>API</strong>
          <span>frontend ready</span>
        </div>
      </section>

      <section className="product-preview-section" aria-label="Baboon Analyst dashboard preview">
        <div className="dashboard-preview">
          <div className="dashboard-window-bar">
            <span />
            <span />
            <span />
            <strong>valuation-workspace.json</strong>
          </div>
          <img src={heroImage} alt="Financial valuation dashboard workspace" />
          <div className="dashboard-caption">
            <span>Live research workspace</span>
            <span>Financials • Ratios • Growth • DCF</span>
          </div>
        </div>
      </section>

      <section className="capability-section" aria-labelledby="capabilities-heading">
        <div className="section-heading">
          <span>The problem</span>
          <h2 id="capabilities-heading">You do not need more tabs. You need a faster way to interpret the data.</h2>
          <p>Public-company research often sprawls across filings, screeners, spreadsheets, and half-finished valuation notes.</p>
        </div>

        <div className="capability-grid">
          {capabilities.map((item) => (
            <article className="capability-card" key={item.title}>
              <item.icon size={22} />
              <h3>{item.title}</h3>
              <p>{item.body}</p>
            </article>
          ))}
        </div>
      </section>

      <section className="preview-section">
        <div className="preview-copy">
          <span>The solution</span>
          <h2>Ask once. Let the backend gather the context.</h2>
          <p>
            The chat page keeps message history in a familiar conversation layout while the backend
            keeps the agent thread alive across turns.
          </p>
          <button className="inline-link" type="button" onClick={() => navigate('/chat')}>
            <span>Go to chat</span>
            <ArrowRight size={17} />
          </button>
        </div>

        <div className="preview-chat" aria-label="Chat preview">
          <div className="preview-message user">Run a DCF valuation for MSFT.</div>
          <div className="preview-message assistant">
            I will gather financials, market data, sector assumptions, and derive the valuation.
          </div>
          <div className="preview-message user">Now summarize the upside risk.</div>
        </div>
      </section>

      <section className="question-band" aria-label="Sample prompts">
        <div className="question-band-copy">
          <span>Sample prompts</span>
          <h2>Start with a ticker.Then sharpen the thesis.</h2>
        </div>
        {sampleQuestions.map((question) => (
          <button key={question} type="button" onClick={() => sendMessage(null, question)}>
            {question}
          </button>
        ))}
      </section>
    </div>
  );
}

function ChatPage({
  draft,
  isSending,
  messages,
  messagesEndRef,
  resetChat,
  sendMessage,
  setDraft,
  threadId,
}) {
  return (
    <section className="chat-page" aria-label="Baboon analyst chat">
      <div className="chat-frame">
        <header className="chat-topbar">
          <div>
            <h1>Research Chat</h1>
            <p>{threadId ? shortThread(threadId) : 'New session'}</p>
          </div>

          <div className="chat-actions">
            <button className="icon-button" type="button" onClick={resetChat} title="New chat">
              <MessageSquarePlus size={18} />
            </button>
          </div>
        </header>

        <div className="messages-panel">
          <div className="messages-list">
            {messages.map((message) => (
              <MessageBubble key={message.id} message={message} />
            ))}

            {isSending && (
              <div className="message-row assistant-row">
                <Avatar role="assistant" />
                <div className="bubble assistant-bubble typing-bubble">
                  <span />
                  <span />
                  <span />
                </div>
              </div>
            )}

            <div ref={messagesEndRef} />
          </div>
        </div>

        <form className="composer" onSubmit={sendMessage}>
          <button
            className="icon-button secondary"
            type="button"
            onClick={resetChat}
            title="Reset chat"
          >
            <RotateCcw size={18} />
          </button>
          <textarea
            value={draft}
            onChange={(event) => setDraft(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === 'Enter' && !event.shiftKey) {
                sendMessage(event);
              }
            }}
            placeholder="Ask about AAPL, NVDA, ratios, growth, or DCF..."
            rows={1}
            aria-label="Message"
          />
          <button className="send-button" type="submit" disabled={!draft.trim() || isSending} title="Send">
            <Send size={18} />
          </button>
        </form>
      </div>
    </section>
  );
}

function MessageBubble({ message }) {
  const isUser = message.role === 'user';
  const isError = message.tone === 'error';
  const isReport = !isUser && !isError && isReportContent(message.content);
  const rowClass = isUser ? 'user-row' : `assistant-row ${isReport ? 'report-row' : ''}`;
  const bubbleClass = isUser ? 'user-bubble' : isReport ? 'report-bubble' : 'assistant-bubble';

  return (
    <div className={`message-row ${rowClass}`}>
      {!isUser && <Avatar role="assistant" />}
      <div className={`bubble ${bubbleClass} ${isError ? 'error-bubble' : ''}`}>
        {isUser || isError ? (
          <p className="message-text">{message.content}</p>
        ) : (
          <ReportMarkdown content={message.content} isReport={isReport} />
        )}
        <time dateTime={message.timestamp}>{formatTime(message.timestamp)}</time>
      </div>
      {isUser && <Avatar role="user" />}
    </div>
  );
}

function ReportMarkdown({ content, isReport }) {
  return (
    <article className={isReport ? 'report-markdown' : 'assistant-markdown'} data-pdf-report={isReport || undefined}>
      <ReactMarkdown remarkPlugins={[remarkGfm]}>{content}</ReactMarkdown>
    </article>
  );
}

function isReportContent(content) {
  return (
    /^# .*\b(report|thesis|analysis|valuation)\b/im.test(content) ||
    /^## (Executive View|Key Findings|Financial Snapshot|Valuation View|Risks and Unknowns|Bottom Line)/im.test(content) ||
    /^\|.+\|\s*$/m.test(content)
  );
}

function Avatar({ role }) {
  return (
    <div className={`avatar ${role}`} aria-hidden="true">
      {role === 'user' ? <User size={17} /> : <Bot size={17} />}
    </div>
  );
}

function formatTime(timestamp) {
  return new Intl.DateTimeFormat(undefined, {
    hour: 'numeric',
    minute: '2-digit',
  }).format(new Date(timestamp));
}

function shortThread(value) {
  return value.replace('api-session-', 'session ').slice(0, 22);
}

function readError(payload) {
  if (typeof payload?.detail === 'string') {
    return payload.detail;
  }

  return payload?.detail?.message;
}

createRoot(document.getElementById('root')).render(<App />);
