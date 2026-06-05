import React from 'react';
import { Activity, Home, Menu, Moon, Sun } from 'lucide-react';

import ChatComposer from '../components/ChatComposer.jsx';
import ChatDataBackground from '../components/ChatDataBackground.jsx';
import MessageBubble from '../components/MessageBubble.jsx';
import SessionSidebar from '../components/SessionSidebar.jsx';

export default function ChatPage({
  activeSessionId,
  apiStatus,
  draft,
  isSending,
  messages,
  messagesEndRef,
  navigate,
  onToggleTheme,
  selectSession,
  sendMessage,
  sessions,
  setDraft,
  startNewChat,
  theme,
}) {
  const [isMobileSidebarOpen, setIsMobileSidebarOpen] = React.useState(false);
  const [isSidebarCollapsed, setIsSidebarCollapsed] = React.useState(false);

  function toggleSidebar() {
    if (window.matchMedia('(max-width: 820px)').matches) {
      setIsMobileSidebarOpen((current) => !current);
      return;
    }

    setIsSidebarCollapsed((current) => !current);
  }

  function handleSelectSession(sessionId) {
    selectSession(sessionId);
    setIsMobileSidebarOpen(false);
  }

  function handleStartNewChat() {
    startNewChat();
    setIsMobileSidebarOpen(false);
  }

  return (
    <section
      className={`chat-page ${isSidebarCollapsed ? 'sidebar-collapsed' : ''}`}
      aria-label="Baboon analyst chat"
    >
      <SessionSidebar
        activeSessionId={activeSessionId}
        isOpen={isMobileSidebarOpen}
        onSelectSession={handleSelectSession}
        onStartNewChat={handleStartNewChat}
        sessions={sessions}
      />

      <div className="chat-main-panel">
        <ChatDataBackground />

        <header className="chat-topbar">
          <div className="chat-topbar-left">
            <button
              className="topbar-icon"
              type="button"
              onClick={toggleSidebar}
              title="Toggle session history"
            >
              <Menu size={19} />
            </button>
            <button
              className="topbar-icon"
              type="button"
              onClick={() => navigate('/')}
              title="Back to homepage"
            >
              <Home size={18} />
            </button>
          </div>

          <div className="chat-logotype">
            <span aria-hidden="true">
              <Activity size={19} />
            </span>
            <strong>Baboon Analyst</strong>
          </div>

          <div className="chat-topbar-actions">
            <button
              className="theme-toggle"
              type="button"
              onClick={onToggleTheme}
              title="Toggle light / dark mode"
              aria-label="Toggle color theme"
            >
              {theme === 'dark' ? <Sun size={16} /> : <Moon size={16} />}
            </button>
            <div className={`chat-status ${apiStatus}`} aria-live="polite">
              <span />
              <strong>{apiStatus === 'online' ? 'Connected' : apiStatus}</strong>
            </div>
          </div>
        </header>

        <div className="messages-panel">
          <div className="messages-list">
            {messages.map((message) => (
              <MessageBubble key={message.id} message={message} />
            ))}

            {isSending && (
              <div className="message-row assistant-row">
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

        <ChatComposer
          draft={draft}
          isSending={isSending}
          sendMessage={sendMessage}
          setDraft={setDraft}
        />
      </div>
    </section>
  );
}
