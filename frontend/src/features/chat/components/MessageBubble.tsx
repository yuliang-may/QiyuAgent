import { useEffect, useRef, useState } from "react";

import type { TranscriptMessage } from "../../../types/domain";
import { ReferenceImageStrip } from "../../../shared/components/ReferenceImageStrip";

const ROLE_LABEL: Record<TranscriptMessage["role"], string> = {
  user: "用户",
  assistant: "漆语",
  system: "系统",
  note: "结果",
};

export function MessageBubble({ message }: { message: TranscriptMessage }) {
  const [evidenceOpen, setEvidenceOpen] = useState(false);
  const evidenceRef = useRef<HTMLElement | null>(null);
  const evidenceCount = message.referenceCards.length;

  useEffect(() => {
    if (evidenceOpen) {
      evidenceRef.current?.scrollIntoView({ block: "start" });
    }
  }, [evidenceOpen]);

  return (
    <article className={`message-bubble ${message.role}`}>
      <span className="message-role">{ROLE_LABEL[message.role] ?? message.role}</span>
      <p>{message.text}</p>
      {message.role === "assistant" ? (
        <>
          <ReferenceImageStrip images={message.referenceImages} variant="message" />
          {evidenceCount ? (
            <div className="message-actions">
              <button
                type="button"
                className="evidence-toggle"
                aria-expanded={evidenceOpen}
                onClick={() => setEvidenceOpen((open) => !open)}
              >
                {evidenceOpen ? "收起本轮证据" : `查看本轮证据（${evidenceCount}）`}
              </button>
            </div>
          ) : null}
          {evidenceOpen ? (
            <section ref={evidenceRef} className="message-evidence" aria-label="本轮回答证据">
              <div className="message-evidence-heading">本轮回答引用的知识片段</div>
              <div className="message-evidence-list">
                {message.referenceCards.map((card) => (
                  <article key={card.id} className="message-evidence-card">
                    <strong>{card.title}</strong>
                    <p>{card.summary}</p>
                    <small>{[card.source, card.scoreLabel].filter(Boolean).join(" · ")}</small>
                    <ReferenceImageStrip
                      imageUrls={card.imageUrls}
                      title={card.title}
                      source={card.source}
                      idPrefix={card.id}
                    />
                  </article>
                ))}
              </div>
            </section>
          ) : null}
        </>
      ) : null}
    </article>
  );
}
