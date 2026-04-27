import { useEffect, useRef } from "react";

import type { TranscriptMessage } from "../../../types/domain";
import { MessageBubble } from "./MessageBubble";

interface ConversationPaneProps {
  messages: TranscriptMessage[];
  thinking?: boolean;
}

export function ConversationPane({ messages, thinking = false }: ConversationPaneProps) {
  const endRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    endRef.current?.scrollIntoView({ block: "end" });
  }, [messages.length, thinking]);

  if (!messages.length && !thinking) {
    return (
      <div className="conversation-empty">
        会话尚未开始。请在下方输入你的问题或任务，或使用示例快速发起对话。
      </div>
    );
  }

  return (
    <div className="conversation-pane">
      {messages.map((message) => (
        <MessageBubble key={message.id} message={message} />
      ))}
      {thinking ? (
        <article className="message-bubble assistant typing" aria-live="polite">
          <span className="message-role">漆语</span>
          <p className="typing-dots" aria-hidden>
            <span /><span /><span />
          </p>
        </article>
      ) : null}
      <div ref={endRef} aria-hidden />
    </div>
  );
}
