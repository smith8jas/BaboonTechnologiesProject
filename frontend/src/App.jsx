import React from 'react';

import {
  checkHealth,
  createChatSession,
  deleteChatSession,
  getMe,
  listChatMessages,
  listChatSessions,
  streamChatMessage,
  updateChatSession,
  updateMe,
} from './api/client.js';
import { useAuth } from './auth/AuthProvider.jsx';
import Navbar from './components/Navbar.jsx';
import AuthPage from './pages/AuthPage.jsx';
import ChatPage from './pages/ChatPage.jsx';
import LandingPage from './pages/LandingPage.jsx';
import ProfilePage from './pages/ProfilePage.jsx';

const THEME_KEY = 'baboon-theme';

function createInitialMessages() {
  return [
    {
      id: 'intro-message',
      role: 'assistant',
      content: 'Bring me a public company and I will build the investment case from the data.',
      timestamp: new Date().toISOString(),
    },
  ];
}

function latestMessageTimestamp(messages) {
  return messages[messages.length - 1]?.timestamp ?? new Date().toISOString();
}

function sessionTitle(source) {
  const text = source?.trim() || 'New research thread';
  return text.length > 42 ? `${text.slice(0, 39)}...` : text;
}

function normalizeSession(row) {
  return {
    id: row.id,
    title: row.title || 'New research thread',
    threadId: row.thread_id ?? null,
    updatedAt: row.updated_at ?? row.created_at ?? new Date().toISOString(),
  };
}

function normalizeMessage(row) {
  return {
    id: row.id,
    role: row.role,
    content: row.content,
    timestamp: row.created_at,
  };
}

function updateSessionMetadata(session, messages) {
  return {
    ...session,
    title: session.title === 'New research thread' ? sessionTitle(messages.find((m) => m.role === 'user')?.content) : session.title,
    updatedAt: latestMessageTimestamp(messages),
  };
}

export default function App() {
  const auth = useAuth();
  const [path, setPath] = React.useState(() => window.location.pathname);
  const [activeSessionId, setActiveSessionId] = React.useState(null);
  const [sessions, setSessions] = React.useState([]);
  const [messagesBySessionId, setMessagesBySessionId] = React.useState({});
  const [profile, setProfile] = React.useState(null);
  const [draft, setDraft] = React.useState('');
  const [isSending, setIsSending] = React.useState(false);
  const [apiStatus, setApiStatus] = React.useState('checking');
  const [theme, setTheme] = React.useState(() => {
    const saved = localStorage.getItem(THEME_KEY);
    return saved === 'light' || saved === 'dark' ? saved : 'dark';
  });
  const lastBackendSuccessRef = React.useRef(0);
  const messagesEndRef = React.useRef(null);

  const activePath = ['/chat', '/login', '/signup', '/profile'].includes(path) ? path : '/';
  const activeSession = sessions.find((session) => session.id === activeSessionId) ?? null;
  const emptyMessages = React.useMemo(createInitialMessages, [activeSessionId, auth.user?.id]);
  const persistedMessages = activeSession ? messagesBySessionId[activeSession.id] ?? [] : [];
  const messages = persistedMessages.length > 0 ? persistedMessages : emptyMessages;

  React.useEffect(() => {
    function handlePopState() {
      setPath(window.location.pathname);
    }

    window.addEventListener('popstate', handlePopState);
    return () => window.removeEventListener('popstate', handlePopState);
  }, []);

  React.useEffect(() => {
    document.documentElement.setAttribute('data-theme', theme);
    localStorage.setItem(THEME_KEY, theme);
  }, [theme]);

  React.useEffect(() => {
    let cancelled = false;

    async function updateHealth() {
      const isOnline = await checkHealth();
      if (!cancelled) {
        if (isOnline) {
          markApiOnline();
        } else if (Date.now() - lastBackendSuccessRef.current > 60000) {
          setApiStatus('offline');
        }
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

  React.useEffect(() => {
    if (auth.loading) {
      return;
    }

    if ((activePath === '/chat' || activePath === '/profile') && !auth.isAuthenticated) {
      navigate('/login');
    }

    if ((activePath === '/login' || activePath === '/signup') && auth.isAuthenticated) {
      navigate('/');
    }
  }, [activePath, auth.isAuthenticated, auth.loading]);

  React.useEffect(() => {
    if (!auth.accessToken) {
      setSessions([]);
      setMessagesBySessionId({});
      setActiveSessionId(null);
      setProfile(null);
      return undefined;
    }

    let cancelled = false;

    async function loadSessions() {
      try {
        const rows = await listChatSessions({ accessToken: auth.accessToken });
        markApiOnline();
        if (cancelled) {
          return;
        }
        const normalized = rows.map(normalizeSession);
        setSessions(normalized);
        setActiveSessionId((current) => {
          if (normalized.some((session) => session.id === current)) {
            return current;
          }
          return normalized[0]?.id ?? null;
        });
      } catch {
        if (!cancelled) {
          setSessions([]);
          setActiveSessionId(null);
        }
      }
    }

    loadSessions();

    return () => {
      cancelled = true;
    };
  }, [auth.accessToken]);

  React.useEffect(() => {
    if (!auth.accessToken) {
      setProfile(null);
      return undefined;
    }

    let cancelled = false;

    async function loadProfile() {
      try {
        const nextProfile = await getMe({ accessToken: auth.accessToken });
        markApiOnline();
        if (!cancelled) {
          setProfile(nextProfile);
        }
      } catch {
        if (!cancelled) {
          setProfile(null);
        }
      }
    }

    loadProfile();

    return () => {
      cancelled = true;
    };
  }, [auth.accessToken]);

  React.useEffect(() => {
    if (!auth.accessToken || !activeSessionId || messagesBySessionId[activeSessionId]) {
      return undefined;
    }

    let cancelled = false;

    async function loadMessages() {
      try {
        const rows = await listChatMessages({
          accessToken: auth.accessToken,
          sessionId: activeSessionId,
        });
        markApiOnline();
        if (!cancelled) {
          setMessagesBySessionId((current) => ({
            ...current,
            [activeSessionId]: rows.map(normalizeMessage),
          }));
        }
      } catch {
        if (!cancelled) {
          setMessagesBySessionId((current) => ({ ...current, [activeSessionId]: [] }));
        }
      }
    }

    loadMessages();

    return () => {
      cancelled = true;
    };
  }, [activeSessionId, auth.accessToken, messagesBySessionId]);

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

  function markApiOnline() {
    lastBackendSuccessRef.current = Date.now();
    setApiStatus('online');
  }

  async function handleSignOut() {
    await auth.signOut();
    setDraft('');
    setSessions([]);
    setMessagesBySessionId({});
    setActiveSessionId(null);
    setProfile(null);
    navigate('/');
  }

  async function saveProfile(profileDraft) {
    const nextProfile = await updateMe({
      accessToken: auth.accessToken,
      profile: profilePayloadFromDraft(profileDraft),
    });
    markApiOnline();
    setProfile(nextProfile);
    return nextProfile;
  }

  async function startNewChat() {
    if (!auth.isAuthenticated) {
      navigate('/login');
      return;
    }

    const row = await createChatSession({
      accessToken: auth.accessToken,
      title: 'New research thread',
    });
    markApiOnline();
    const session = normalizeSession(row);
    setSessions((current) => [session, ...current]);
    setMessagesBySessionId((current) => ({ ...current, [session.id]: [] }));
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

  async function removeSession(sessionId) {
    const session = sessions.find((item) => item.id === sessionId);
    const title = session?.title || 'this chat';
    const confirmed = window.confirm(`Delete "${title}"? This will permanently remove the chat history.`);
    if (!confirmed) {
      return;
    }

    await deleteChatSession({
      accessToken: auth.accessToken,
      sessionId,
    });
    markApiOnline();

    setMessagesBySessionId((current) => {
      const next = { ...current };
      delete next[sessionId];
      return next;
    });

    setSessions((current) => {
      const nextSessions = current.filter((item) => item.id !== sessionId);
      if (sessionId === activeSessionId) {
        setActiveSessionId(nextSessions[0]?.id ?? null);
      }
      return nextSessions;
    });
  }

  async function renameSession(sessionId, title) {
    const cleanTitle = title.trim();
    if (!cleanTitle) {
      return;
    }

    const previous = sessions.find((item) => item.id === sessionId);
    updateSession(sessionId, (current) => ({ ...current, title: cleanTitle }));

    try {
      const row = await updateChatSession({
        accessToken: auth.accessToken,
        sessionId,
        title: cleanTitle,
      });
      markApiOnline();
      const renamed = normalizeSession(row);
      updateSession(sessionId, (current) => ({ ...current, ...renamed }));
    } catch (error) {
      if (previous) {
        updateSession(sessionId, () => previous);
      }
      throw error;
    }
  }

  function updateMessages(sessionId, updater) {
    setMessagesBySessionId((current) => ({
      ...current,
      [sessionId]: updater(current[sessionId] ?? []),
    }));
  }

  function updateSession(sessionId, updater) {
    setSessions((current) =>
      current.map((session) => (session.id === sessionId ? updater(session) : session)),
    );
  }

  async function ensureSessionForMessage(text) {
    if (activeSession) {
      return activeSession;
    }

    const row = await createChatSession({
      accessToken: auth.accessToken,
      title: sessionTitle(text),
    });
    markApiOnline();
    const session = normalizeSession(row);
    setSessions((current) => [session, ...current]);
    setMessagesBySessionId((current) => ({ ...current, [session.id]: [] }));
    setActiveSessionId(session.id);
    return session;
  }

  async function sendMessage(event, overrideText) {
    event?.preventDefault();
    const text = (overrideText ?? draft).trim();

    if (!text || isSending) {
      return;
    }

    if (!auth.isAuthenticated || !auth.accessToken) {
      navigate('/login');
      return;
    }

    if (path !== '/chat') {
      navigate('/chat');
    }

    setDraft('');
    setIsSending(true);

    let session;
    try {
      session = await ensureSessionForMessage(text);
    } catch (error) {
      setIsSending(false);
      throw error;
    }

    const sessionId = session.id;
    const userMessage = {
      id: crypto.randomUUID(),
      role: 'user',
      content: text,
      timestamp: new Date().toISOString(),
    };
    const assistantMessageId = crypto.randomUUID();
    const assistantMessage = {
      id: assistantMessageId,
      role: 'assistant',
      content: '',
      statusText: '',
      timestamp: new Date().toISOString(),
      isStreaming: true,
      thoughts: [],
    };

    updateMessages(sessionId, (current) => [...current, userMessage, assistantMessage]);
    updateSession(sessionId, (current) => updateSessionMetadata(current, [userMessage]));

    let streamedContent = '';

    try {
      await streamChatMessage({
        accessToken: auth.accessToken,
        message: text,
        sessionId,
        threadId: session.threadId,
        onSessionId: (nextSessionId) => {
          markApiOnline();
          if (nextSessionId && nextSessionId !== sessionId) {
            setActiveSessionId(nextSessionId);
          }
        },
        onThreadId: (threadId) => {
          markApiOnline();
          updateSession(sessionId, (current) => ({ ...current, threadId }));
        },
        onStatus: (statusText) => {
          markApiOnline();
          updateMessages(sessionId, (current) =>
            current.map((message) =>
              message.id === assistantMessageId ? { ...message, statusText } : message,
            ),
          );
        },
        onThought: (thought) => {
          markApiOnline();
          updateMessages(sessionId, (current) =>
            current.map((message) =>
              message.id === assistantMessageId
                ? { ...message, thoughts: [...(message.thoughts || []), thought] }
                : message,
            ),
          );
        },
        onClear: () => {
          markApiOnline();
          streamedContent = '';
          updateMessages(sessionId, (current) =>
            current.map((message) =>
              message.id === assistantMessageId
                ? { ...message, content: '', statusText: '' }
                : message,
            ),
          );
        },
        onDelta: (chunk) => {
          markApiOnline();
          streamedContent += chunk;
          updateMessages(sessionId, (current) =>
            current.map((message) =>
              message.id === assistantMessageId
                ? {
                    ...message,
                    content: streamedContent,
                    statusText: '',
                  }
                : message,
            ),
          );
        },
      });
      markApiOnline();

      updateMessages(sessionId, (current) => {
        const next = current.map((message) =>
          message.id === assistantMessageId
            ? {
                ...message,
                content: streamedContent || 'I did not receive a response from the analyst agent.',
                isStreaming: false,
                timestamp: new Date().toISOString(),
              }
            : message,
        );
        updateSession(sessionId, (sessionRow) => updateSessionMetadata(sessionRow, next));
        return next;
      });
    } catch (error) {
      const content = streamedContent
        ? `${streamedContent}\n\nStream interrupted: ${error.message}`
        : `I could not reach the backend cleanly. ${error.message}`;

      updateMessages(sessionId, (current) =>
        current.map((message) =>
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
      );
    } finally {
      setIsSending(false);
    }
  }

  if (auth.loading) {
    return <main className="site-shell app-loading">Loading...</main>;
  }

  if (activePath === '/login' || activePath === '/signup') {
    return (
      <AuthPage
        mode={activePath === '/signup' ? 'signup' : 'login'}
        navigate={navigate}
        onSignIn={auth.signIn}
        onSignUp={auth.signUp}
      />
    );
  }

  return (
    <main className="site-shell">
      {activePath === '/profile' && auth.isAuthenticated ? (
        <ProfilePage
          apiStatus={apiStatus}
          navigate={navigate}
          onSaveProfile={saveProfile}
          profile={profile}
          user={auth.user}
        />
      ) : activePath === '/chat' && auth.isAuthenticated ? (
        <ChatPage
          activeSessionId={activeSession?.id}
          apiStatus={apiStatus}
          draft={draft}
          isSending={isSending}
          messages={messages}
          messagesEndRef={messagesEndRef}
          navigate={navigate}
          onOpenProfile={() => navigate('/profile')}
          onDeleteSession={removeSession}
          onRenameSession={renameSession}
          onSignOut={handleSignOut}
          onToggleTheme={toggleTheme}
          selectSession={selectSession}
          sendMessage={sendMessage}
          sessions={sessions}
          setDraft={setDraft}
          startNewChat={startNewChat}
          theme={theme}
          user={auth.user}
        />
      ) : (
        <>
          <Navbar
            apiStatus={apiStatus}
            isAuthenticated={auth.isAuthenticated}
            navigate={navigate}
            onOpenProfile={() => navigate('/profile')}
            onSignOut={handleSignOut}
            onToggleTheme={toggleTheme}
            theme={theme}
            user={auth.user}
          />
          <LandingPage navigate={navigate} />
        </>
      )}
    </main>
  );
}

function profilePayloadFromDraft(draft) {
  return {
    display_name: blankToNull(draft.display_name),
    username: blankToNull(draft.username),
    full_name: blankToNull(draft.full_name),
    age: numberOrNull(draft.age),
    role_title: blankToNull(draft.role_title),
    company: blankToNull(draft.company),
    avatar_url: blankToNull(draft.avatar_url),
    bio: blankToNull(draft.bio),
  };
}

function blankToNull(value) {
  return typeof value === 'string' && !value.trim() ? null : value;
}

function numberOrNull(value) {
  if (value === null || value === undefined) {
    return null;
  }

  if (typeof value === 'string' && !value.trim()) {
    return null;
  }

  const numberValue = Number(value);
  return Number.isNaN(numberValue) ? null : numberValue;
}
