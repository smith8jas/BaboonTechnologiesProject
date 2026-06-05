import React from 'react';
import { Plus } from 'lucide-react';

export default function SessionSidebar({
  activeSessionId,
  isOpen,
  onSelectSession,
  onStartNewChat,
  sessions,
}) {
  return (
    <aside className={`chat-sidebar ${isOpen ? 'open' : ''}`} aria-label="Chat session history">
      <div className="sidebar-header">
        <span>Research Threads</span>
        <button type="button" onClick={onStartNewChat}>
          <Plus size={16} />
          <span>New Chat</span>
        </button>
      </div>

      <div className="session-list">
        {sessions.map((session) => (
          <button
            key={session.id}
            className={`session-item ${session.id === activeSessionId ? 'active' : ''}`}
            type="button"
            onClick={() => onSelectSession(session.id)}
          >
            <span>{session.title}</span>
            <time dateTime={session.updatedAt}>{formatSessionTime(session.updatedAt)}</time>
          </button>
        ))}
      </div>
    </aside>
  );
}

function formatSessionTime(timestamp) {
  return new Intl.DateTimeFormat(undefined, {
    month: 'short',
    day: 'numeric',
    hour: 'numeric',
    minute: '2-digit',
  }).format(new Date(timestamp));
}
