import React from 'react';

import { checkHealth, streamChatMessage } from './api/client.js';
import Navbar from './components/Navbar.jsx';
import ChatPage from './pages/ChatPage.jsx';
import LandingPage from './pages/LandingPage.jsx';

const STORAGE_KEY = 'baboon-chat-state';
const THEME_KEY = 'baboon-theme';

function createInitialMessages() {
  return [
    {
      id: crypto.randomUUID(),
      role: 'assistant',
      content: 'Bring me a public company and I will build the investment case from the data.',
      timestamp: new Date().toISOString(),
    },
  ];
}

function createSession(overrides = {}) {
  const messages = overrides.messages ?? createInitialMessages();
  const updatedAt = overrides.updatedAt ?? latestMessageTimestamp(messages);

  return {
    id: overrides.id ?? crypto.randomUUID(),
    title: overrides.title ?? sessionTitle(messages),
    threadId: overrides.threadId ?? null,
    messages,
    updatedAt,
  };
}

function loadState() {
  try {
    const saved = JSON.parse(localStorage.getItem(STORAGE_KEY) ?? 'null');

    // Current persistence format: multiple named research sessions.
    if (saved?.sessions?.length) {
      return {
        activeSessionId: saved.activeSessionId ?? saved.sessions[0].id,
        sessions: saved.sessions,
      };
    }

    // Migration path for earlier builds that stored a single message list.
    if (saved?.messages?.length) {
      const session = createSession({
        threadId: saved.threadId,
        messages: saved.messages,
      });

      return {
        activeSessionId: session.id,
        sessions: [session],
      };
    }
  } catch {
    localStorage.removeItem(STORAGE_KEY);
  }

  const session = createSession();
  return {
    activeSessionId: session.id,
    sessions: [session],
  };
}

function latestMessageTimestamp(messages) {
  return messages[messages.length - 1]?.timestamp ?? new Date().toISOString();
}

function sessionTitle(messages) {
  const firstUserMessage = messages.find((message) => message.role === 'user');
  const source = firstUserMessage?.content ?? 'New research thread';
  return source.length > 42 ? `${source.slice(0, 39)}...` : source;
}

function updateSessionMetadata(session) {
  return {
    ...session,
    title: sessionTitle(session.messages),
    updatedAt: latestMessageTimestamp(session.messages),
  };
}

export default function App() {
  const [initialChatState] = React.useState(loadState);
  const [path, setPath] = React.useState(() => window.location.pathname);
  const [activeSessionId, setActiveSessionId] = React.useState(initialChatState.activeSessionId);
  const [sessions, setSessions] = React.useState(initialChatState.sessions);
  const [draft, setDraft] = React.useState('');
  const [isSending, setIsSending] = React.useState(false);
  const [apiStatus, setApiStatus] = React.useState('checking');
  const [theme, setTheme] = React.useState(() => {
    const saved = localStorage.getItem(THEME_KEY);
    return saved === 'light' || saved === 'dark' ? saved : 'dark';
  });
  const messagesEndRef = React.useRef(null);

  const activePath = path === '/chat' ? '/chat' : '/';
  const activeSession = sessions.find((session) => session.id === activeSessionId) ?? sessions[0];
  const messages = activeSession?.messages ?? [];

  React.useEffect(() => {
    function handlePopState() {
      setPath(window.location.pathname);
    }

    window.addEventListener('popstate', handlePopState);
    return () => window.removeEventListener('popstate', handlePopState);
  }, []);

  React.useEffect(() => {
    localStorage.setItem(STORAGE_KEY, JSON.stringify({ activeSessionId, sessions }));
  }, [activeSessionId, sessions]);

  React.useEffect(() => {
    document.documentElement.setAttribute('data-theme', theme);
    localStorage.setItem(THEME_KEY, theme);
  }, [theme]);

  React.useEffect(() => {
    let cancelled = false;

    async function updateHealth() {
      const isOnline = await checkHealth();
      if (!cancelled) {
        setApiStatus(isOnline ? 'online' : 'offline');
      }
    }

    updateHealth();
    const intervalId = window.setInterval(updateHealth, 15000);

    return () => {
      cancelled = true;
      window.clearInterval(intervalId);
    };
  }, []);

  React.useEffect(() => {
    if (activePath === '/chat') {
      messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
    }
  }, [messages, isSending, activePath]);

  function toggleTheme() {
    setTheme((current) => (current === 'dark' ? 'light' : 'dark'));
  }

  function navigate(nextPath) {
    if (nextPath.startsWith('#')) {
      document.querySelector(nextPath)?.scrollIntoView({ behavior: 'smooth', block: 'start' });
      return;
    }

    if (nextPath === path) {
      return;
    }

    window.history.pushState({}, '', nextPath);
    setPath(nextPath);
  }

  function startNewChat() {
    const session = createSession();
    setSessions((current) => [session, ...current]);
    setActiveSessionId(session.id);
    setDraft('');

    if (path !== '/chat') {
      navigate('/chat');
    }
  }

  function selectSession(sessionId) {
    setActiveSessionId(sessionId);
    setDraft('');

    if (path !== '/chat') {
      navigate('/chat');
    }
  }

  async function sendMessage(event, overrideText) {
    event?.preventDefault();
    const text = (overrideText ?? draft).trim();

    if (!text || isSending) {
      return;
    }

    const session = activeSession ?? createSession();
    const sessionId = session.id;

    if (!activeSession) {
      setSessions((current) => [session, ...current]);
      setActiveSessionId(sessionId);
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
    const assistantMessageId = crypto.randomUUID();
    // Insert a placeholder immediately so streamed status and deltas have
    // a stable message to update in place.
    const assistantMessage = {
      id: assistantMessageId,
      role: 'assistant',
      content: '',
      statusText: '',
      timestamp: new Date().toISOString(),
      isStreaming: true,
      thoughts: [],
    };

    setDraft('');
    setIsSending(true);
    setSessions((current) =>
      current.map((currentSession) =>
        currentSession.id === sessionId
          ? updateSessionMetadata({
              ...currentSession,
              messages: [...currentSession.messages, userMessage, assistantMessage],
            })
          : currentSession,
      ),
    );

    let streamedContent = '';

    try {
      await streamChatMessage({
        message: text,
        threadId: session.threadId,
        onThreadId: (threadId) => {
          setSessions((current) =>
            current.map((currentSession) =>
              currentSession.id === sessionId
                ? {
                    ...currentSession,
                    threadId,
                  }
                : currentSession,
            ),
          );
        },
        onStatus: (text) => {
          setSessions((current) =>
            current.map((currentSession) =>
              currentSession.id === sessionId
                ? {
                    ...currentSession,
                    messages: currentSession.messages.map((message) =>
                      message.id === assistantMessageId ? { ...message, statusText: text } : message,
                    ),
                  }
                : currentSession,
            ),
          );
        },
        onThought: (thought) => {
          setSessions((current) =>
            current.map((currentSession) =>
              currentSession.id === sessionId
                ? {
                    ...currentSession,
                    messages: currentSession.messages.map((message) =>
                      message.id === assistantMessageId
                        ? { ...message, thoughts: [...(message.thoughts || []), thought] }
                        : message,
                    ),
                  }
                : currentSession,
            ),
          );
        },
        onDelta: (chunk) => {
          streamedContent += chunk;
          setSessions((current) =>
            current.map((currentSession) =>
              currentSession.id === sessionId
                ? updateSessionMetadata({
                    ...currentSession,
                    messages: currentSession.messages.map((message) =>
                      message.id === assistantMessageId
                        ? {
                            ...message,
                            content: streamedContent,
                            statusText: '',
                          }
                        : message,
                    ),
                  })
                : currentSession,
            ),
          );
        },
      });

      setSessions((current) =>
        current.map((currentSession) =>
          currentSession.id === sessionId
            ? updateSessionMetadata({
                ...currentSession,
                messages: currentSession.messages.map((message) =>
                  message.id === assistantMessageId
                    ? {
                        ...message,
                        content: streamedContent || 'I did not receive a response from the analyst agent.',
                        isStreaming: false,
                        timestamp: new Date().toISOString(),
                      }
                    : message,
                ),
              })
            : currentSession,
        ),
      );
    } catch (error) {
      const content = streamedContent
        ? `${streamedContent}\n\nStream interrupted: ${error.message}`
        : `I could not reach the backend cleanly. ${error.message}`;

      setSessions((current) =>
        current.map((currentSession) =>
          currentSession.id === sessionId
            ? updateSessionMetadata({
                ...currentSession,
                messages: currentSession.messages.map((message) =>
                  message.id === assistantMessageId
                    ? {
                        ...message,
                        content,
                        isStreaming: false,
                        timestamp: new Date().toISOString(),
                        tone: streamedContent ? undefined : 'error',
                      }
                    : message,
                ),
              })
            : currentSession,
        ),
      );
    } finally {
      setIsSending(false);
    }
  }

  return (
    <main className="site-shell">
      {activePath === '/chat' ? (
        <ChatPage
          activeSessionId={activeSession?.id}
          apiStatus={apiStatus}
          draft={draft}
          isSending={isSending}
          messages={messages}
          messagesEndRef={messagesEndRef}
          navigate={navigate}
          onToggleTheme={toggleTheme}
          selectSession={selectSession}
          sendMessage={sendMessage}
          sessions={sessions}
          setDraft={setDraft}
          startNewChat={startNewChat}
          theme={theme}
        />
      ) : (
        <>
          <Navbar apiStatus={apiStatus} navigate={navigate} onToggleTheme={toggleTheme} theme={theme} />
          <LandingPage navigate={navigate} />
        </>
      )}
    </main>
  );
}
