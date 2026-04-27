import { useEffect, useRef, useState } from "react";

import type { ComposerMode } from "../../../types/domain";
import type { SceneKey } from "../../../types/api";

interface ComposerProps {
  mode: ComposerMode;
  sceneKey: SceneKey;
  pendingSlotLabel?: string;
  busy: boolean;
  onSubmit: (text: string) => Promise<void>;
}

export function Composer({ mode, sceneKey, pendingSlotLabel, busy, onSubmit }: ComposerProps) {
  const [value, setValue] = useState("");
  const textareaRef = useRef<HTMLTextAreaElement | null>(null);

  useEffect(() => {
    setValue("");
  }, [mode, sceneKey]);

  const placeholder =
    mode === "pending-answer"
      ? pendingSlotLabel
        ? `请回答当前待确认项：${pendingSlotLabel}。若信息不足，可直接说明。`
        : "请回答当前待确认项。若信息不足，可直接说明。"
      : sceneKey === "chat"
        ? "输入你的问题或任务。例如：请诊断木胎表面发白现象。"
        : "继续补充目标、现象或前置条件。";

  const submitLabel =
    busy ? "发送中…"
      : mode === "pending-answer" ? "提交"
      : "发送";

  async function doSubmit() {
    if (busy) return;
    if (!value.trim()) return;
    await onSubmit(value);
  }

  function onKeyDown(event: React.KeyboardEvent<HTMLTextAreaElement>) {
    if ((event.metaKey || event.ctrlKey) && event.key === "Enter") {
      event.preventDefault();
      void doSubmit();
    }
  }

  async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    await doSubmit();
  }

  return (
    <form className="composer" onSubmit={(event) => void handleSubmit(event)}>
      {mode === "pending-answer" && pendingSlotLabel ? (
        <label htmlFor="composer-input">待确认 · {pendingSlotLabel}</label>
      ) : null}
      <textarea
        id="composer-input"
        ref={textareaRef}
        value={value}
        onChange={(event) => setValue(event.target.value)}
        onKeyDown={onKeyDown}
        placeholder={placeholder}
      />
      <div className="composer-row">
        <span className="composer-hint">⌘↵ 发送  ·  ↵ 换行</span>
        <button type="submit" className="primary-button" disabled={busy || !value.trim()}>
          {submitLabel}
        </button>
      </div>
    </form>
  );
}
