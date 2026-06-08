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

export async function sendChatMessage({ message, threadId }) {
  const response = await fetch(`${API_BASE_URL}/agent/chat`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({
      message,
      thread_id: threadId,
    }),
  });

  const payload = await response.json().catch(() => ({}));

  if (!response.ok) {
    throw new Error(readError(payload) || `Request failed with ${response.status}`);
  }

  return payload;
}

export async function streamChatMessage({
  message,
  threadId,
  onDelta,
  onDone,
  onError,
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
    },
    body: JSON.stringify({
      message,
      thread_id: threadId,
    }),
  });

  if (!response.ok) {
    const payload = await response.json().catch(() => ({}));
    throw new Error(readError(payload) || `Request failed with ${response.status}`);
  }

  if (!response.body) {
    const payload = await sendChatMessage({ message, threadId });
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
      readStreamEvent(line, { onDelta, onDone, onError, onThreadId, onStatus, onThought });
    }
  }

  buffer += decoder.decode();

  if (buffer.trim()) {
    readStreamEvent(buffer, { onDelta, onDone, onError, onThreadId, onStatus, onThought });
  }
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
