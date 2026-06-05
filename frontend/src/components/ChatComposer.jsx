import React from 'react';
import { Send } from 'lucide-react';

import { chatPromptChips } from '../data/landingContent.js';

export default function ChatComposer({
  draft,
  isSending,
  sendMessage,
  setDraft,
}) {
  const textareaRef = React.useRef(null);

  React.useEffect(() => {
    const textarea = textareaRef.current;
    if (!textarea) {
      return;
    }

    textarea.style.height = 'auto';
    textarea.style.height = `${Math.min(textarea.scrollHeight, 132)}px`;
  }, [draft]);

  function prefillPrompt(prompt) {
    setDraft(prompt);
    textareaRef.current?.focus();
  }

  return (
    <div className="composer-shell">
      <form className="composer" onSubmit={sendMessage}>
        <textarea
          ref={textareaRef}
          value={draft}
          onChange={(event) => setDraft(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === 'Enter' && !event.shiftKey) {
              sendMessage(event);
            }
          }}
          placeholder="Ask about a company, ticker, or valuation..."
          rows={1}
          aria-label="Message"
        />
        <button className="send-button" type="submit" disabled={!draft.trim() || isSending} title="Send">
          <Send size={18} />
        </button>
      </form>

      <div className="composer-prompts" aria-label="Example prompts">
        {chatPromptChips.map((prompt) => (
          <button key={prompt} type="button" onClick={() => prefillPrompt(prompt)}>
            {prompt}
          </button>
        ))}
      </div>
    </div>
  );
}
