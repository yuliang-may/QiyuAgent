import { useMemo, useState } from "react";

import type { AttachmentDisplay, ExecutionDisplay } from "../../../types/domain";

interface ExecutionControlsProps {
  execution: ExecutionDisplay;
  attachments: AttachmentDisplay[];
  onUpdateStep: (stepNumber: number, status: string, note: string) => Promise<void>;
  onUpdateCheckpoint: (checkpointId: string, status: string, note: string) => Promise<void>;
  onUploadAttachment: (file: File, target: string, note: string) => Promise<void>;
  busy: boolean;
}

export function ExecutionControls({
  execution,
  attachments,
  onUpdateStep,
  onUpdateCheckpoint,
  onUploadAttachment,
  busy,
}: ExecutionControlsProps) {
  const [selectedTarget, setSelectedTarget] = useState("session");
  const [note, setNote] = useState("");
  const [file, setFile] = useState<File | null>(null);

  const targets = useMemo(() => {
    const options = [{ value: "session", label: "整个会话" }];
    execution.steps.forEach((item) => {
      options.push({ value: `step:${item.stepNumber}`, label: `第 ${item.stepNumber} 步` });
    });
    execution.checkpoints.forEach((item) => {
      options.push({
        value: `checkpoint:${item.checkpointId}`,
        label: `检查点 ${item.checkpointId}`,
      });
    });
    return options;
  }, [execution.checkpoints, execution.steps]);

  return (
    <div className="execution-controls">
      <section>
        <div className="tab-subheading">步骤控制</div>
        <div className="action-grid">
          {execution.steps.map((step) => (
            <div key={step.stepNumber} className="inline-actions">
              <strong>第 {step.stepNumber} 步</strong>
              <div className="action-row">
                <button
                  type="button"
                  onClick={() => void onUpdateStep(step.stepNumber, "in_progress", step.note)}
                  disabled={busy}
                >
                  进行中
                </button>
                <button
                  type="button"
                  onClick={() => void onUpdateStep(step.stepNumber, "done", step.note)}
                  disabled={busy}
                >
                  已完成
                </button>
                <button
                  type="button"
                  onClick={() => void onUpdateStep(step.stepNumber, "blocked", step.note)}
                  disabled={busy}
                >
                  阻断
                </button>
              </div>
            </div>
          ))}

          {execution.checkpoints.map((checkpoint) => (
            <div key={checkpoint.checkpointId} className="inline-actions">
              <strong>检查点 {checkpoint.checkpointId}</strong>
              <div className="action-row">
                <button
                  type="button"
                  onClick={() => void onUpdateCheckpoint(checkpoint.checkpointId, "confirmed", checkpoint.note)}
                  disabled={busy}
                >
                  通过
                </button>
                <button
                  type="button"
                  onClick={() => void onUpdateCheckpoint(checkpoint.checkpointId, "failed", checkpoint.note)}
                  disabled={busy}
                >
                  未通过
                </button>
              </div>
            </div>
          ))}
        </div>
      </section>

      <section>
        <div className="tab-subheading">现场记录上传</div>
        <div className="attachment-uploader">
          <select value={selectedTarget} onChange={(event) => setSelectedTarget(event.target.value)}>
            {targets.map((target) => (
              <option key={target.value} value={target.value}>
                {target.label}
              </option>
            ))}
          </select>
          <input
            type="file"
            accept="image/png,image/jpeg,image/webp"
            onChange={(event) => setFile(event.target.files?.[0] || null)}
          />
          <input
            value={note}
            onChange={(event) => setNote(event.target.value)}
            placeholder="备注（可选）"
          />
          <button
            type="button"
            className="primary-button"
            disabled={busy || !file}
            onClick={async () => {
              if (!file) return;
              await onUploadAttachment(file, selectedTarget, note);
              setFile(null);
              setNote("");
            }}
          >
            上传
          </button>
        </div>
        <div className="stack-list">
          {attachments.length ? (
            attachments.map((item) => (
              <article key={item.id} className="stack-card">
                <strong>{item.name}</strong>
                <p>{item.note || "—"}</p>
                <div className="meta-row">
                  <span>{item.linkedLabel}</span>
                  <a href={item.downloadUrl} target="_blank" rel="noreferrer">
                    打开
                  </a>
                </div>
              </article>
            ))
          ) : (
            <div className="side-empty">暂无附件。请选择一个关联位置后上传。</div>
          )}
        </div>
      </section>
    </div>
  );
}
