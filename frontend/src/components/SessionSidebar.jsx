import React from 'react';
import { Check, Pencil, Plus, Trash2, X } from 'lucide-react';

export default function SessionSidebar({
  activeSessionId,
  isOpen,
  onDeleteSession,
  onRenameSession,
  onSelectSession,
  onStartNewChat,
  sessions,
}) {
  const [editingSessionId, setEditingSessionId] = React.useState(null);
  const [draftTitle, setDraftTitle] = React.useState('');
  const [isSavingTitle, setIsSavingTitle] = React.useState(false);

  function startEditing(session) {
    setEditingSessionId(session.id);
    setDraftTitle(session.title);
  }

  function cancelEditing() {
    setEditingSessionId(null);
    setDraftTitle('');
    setIsSavingTitle(false);
  }

  async function submitRename(event, sessionId) {
    event.preventDefault();
    const nextTitle = draftTitle.trim();
    if (!nextTitle || isSavingTitle) {
      return;
    }

    setIsSavingTitle(true);
    try {
      await onRenameSession(sessionId, nextTitle);
      cancelEditing();
    } catch {
      setIsSavingTitle(false);
    }
  }

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
        {sessions.map((session) => {
          const isEditing = editingSessionId === session.id;

          return (
            <div
              key={session.id}
              className={`session-item ${session.id === activeSessionId ? 'active' : ''} ${isEditing ? 'editing' : ''}`}
            >
              {isEditing ? (
                <form className="session-edit-form" onSubmit={(event) => submitRename(event, session.id)}>
                  <input
                    autoFocus
                    maxLength={120}
                    type="text"
                    value={draftTitle}
                    onChange={(event) => setDraftTitle(event.target.value)}
                    onKeyDown={(event) => {
                      if (event.key === 'Escape') {
                        cancelEditing();
                      }
                    }}
                    aria-label="Chat name"
                  />
                  <button
                    className="session-action"
                    type="submit"
                    disabled={!draftTitle.trim() || isSavingTitle}
                    title="Save chat name"
                    aria-label="Save chat name"
                  >
                    <Check size={14} />
                  </button>
                  <button
                    className="session-action"
                    type="button"
                    onClick={cancelEditing}
                    title="Cancel rename"
                    aria-label="Cancel rename"
                  >
                    <X size={14} />
                  </button>
                </form>
              ) : (
                <>
                  <button
                    className="session-select"
                    type="button"
                    onClick={() => onSelectSession(session.id)}
                  >
                    <span>{session.title}</span>
                    <time dateTime={session.updatedAt}>{formatSessionTime(session.updatedAt)}</time>
                  </button>
                  <button
                    className="session-action session-rename"
                    type="button"
                    onClick={() => startEditing(session)}
                    title="Rename chat"
                    aria-label={`Rename ${session.title}`}
                  >
                    <Pencil size={14} />
                  </button>
                  <button
                    className="session-action session-delete"
                    type="button"
                    onClick={() => onDeleteSession(session.id)}
                    title="Delete chat"
                    aria-label={`Delete ${session.title}`}
                  >
                    <Trash2 size={14} />
                  </button>
                </>
              )}
            </div>
          );
        })}
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
