const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? 'http://127.0.0.1:8000';

export async function checkHealth() {
  // The UI only needs a boolean status; callers should not handle transport details.
  try {
    const response = await fetch(`${API_BASE_URL}/health`);
    return response.ok;
  } catch {
    return false;
  }
}

export async function sendChatMessage({ accessToken, message, sessionId, threadId }) {
  const response = await fetch(`${API_BASE_URL}/agent/chat`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      ...authHeaders(accessToken),
    },
    body: JSON.stringify({
      message,
      session_id: sessionId,
      thread_id: threadId,
    }),
  });

  const payload = await response.json().catch(() => ({}));

  if (!response.ok) {
    throw new Error(readError(payload) || `Request failed with ${response.status}`);
  }

  return payload;
}

export async function getMe({ accessToken }) {
  return requestJson('/me', { accessToken });
}

export async function updateMe({ accessToken, profile }) {
  return requestJson('/me', {
    accessToken,
    method: 'PATCH',
    body: profile,
  });
}

export async function listChatSessions({ accessToken }) {
  return requestJson('/chat/sessions', { accessToken });
}

export async function createChatSession({ accessToken, title }) {
  return requestJson('/chat/sessions', {
    accessToken,
    method: 'POST',
    body: { title },
  });
}

export async function updateChatSession({ accessToken, sessionId, title }) {
  return requestJson(`/chat/sessions/${sessionId}`, {
    accessToken,
    method: 'PATCH',
    body: { title },
  });
}

export async function deleteChatSession({ accessToken, sessionId }) {
  return requestJson(`/chat/sessions/${sessionId}`, {
    accessToken,
    method: 'DELETE',
  });
}

export async function listChatMessages({ accessToken, sessionId }) {
  return requestJson(`/chat/sessions/${sessionId}/messages`, { accessToken });
}

export async function streamChatMessage({
  accessToken,
  message,
  sessionId,
  threadId,
  onDelta,
  onDone,
  onError,
  onSessionId,
  onThreadId,
  onStatus,
  onThought,
}) {
  // Prefer the streaming endpoint for live status and token deltas.
  // Fall back to the non-streaming request if the browser lacks a readable body.
  const response = await fetch(`${API_BASE_URL}/agent/chat/stream`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      ...authHeaders(accessToken),
    },
    body: JSON.stringify({
      message,
      session_id: sessionId,
      thread_id: threadId,
    }),
  });

  if (!response.ok) {
    const payload = await response.json().catch(() => ({}));
    throw new Error(readError(payload) || `Request failed with ${response.status}`);
  }

  if (!response.body) {
    const payload = await sendChatMessage({ accessToken, message, sessionId, threadId });
    onSessionId?.(payload.session_id);
    onThreadId?.(payload.thread_id);
    onDelta?.(payload.response || '');
    onDone?.();
    return;
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';

  while (true) {
    const { done, value } = await reader.read();
    if (done) {
      break;
    }

    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split('\n');
    buffer = lines.pop() ?? '';

    for (const line of lines) {
      readStreamEvent(line, { onDelta, onDone, onError, onSessionId, onThreadId, onStatus, onThought });
    }
  }

  buffer += decoder.decode();

  if (buffer.trim()) {
    readStreamEvent(buffer, { onDelta, onDone, onError, onSessionId, onThreadId, onStatus, onThought });
  }
}

async function requestJson(path, { accessToken, method = 'GET', body } = {}) {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    method,
    headers: {
      'Content-Type': 'application/json',
      ...authHeaders(accessToken),
    },
    body: body ? JSON.stringify(body) : undefined,
  });

  const payload = await response.json().catch(() => ({}));

  if (!response.ok) {
    throw new Error(readError(payload) || `Request failed with ${response.status}`);
  }

  return payload;
}

function authHeaders(accessToken) {
  return accessToken ? { Authorization: `Bearer ${accessToken}` } : {};
}

function readError(payload) {
  // FastAPI may return either a string detail or the structured shape built in routes.py.
  if (typeof payload?.detail === 'string') {
    return payload.detail;
  }

  return payload?.detail?.message;
}

function readStreamEvent(line, handlers) {
  // The backend emits newline-delimited JSON events so partial chunks are buffered upstream.
  if (!line.trim()) {
    return;
  }

  const event = JSON.parse(line);

  if (event.type === 'thread') {
    handlers.onSessionId?.(event.session_id);
    handlers.onThreadId?.(event.thread_id);
    return;
  }

  if (event.type === 'thought') {
    handlers.onThought?.(event.content ?? '');
    return;
  }

  if (event.type === 'status') {
    handlers.onStatus?.(event.text ?? event.content ?? '');
    return;
  }

  if (event.type === 'delta' || event.type === 'token') {
    handlers.onDelta?.(event.content ?? event.text ?? '');
    return;
  }

  if (event.type === 'error') {
    const error = new Error(event.message || 'The stream ended with an error.');
    handlers.onError?.(error);
    throw error;
  }

  if (event.type === 'done') {
    handlers.onDone?.();
  }
}
