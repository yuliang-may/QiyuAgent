import type { ContractPanelModel, ExecutionDisplay, AttachmentDisplay } from "../../../types/domain";
import { ExecutionControls } from "../../execution/components/ExecutionControls";

interface ContractTabProps {
  model: ContractPanelModel | null;
  execution: ExecutionDisplay;
  attachments: AttachmentDisplay[];
  busy: boolean;
  onUpdateStep: (stepNumber: number, status: string, note: string) => Promise<void>;
  onUpdateCheckpoint: (checkpointId: string, status: string, note: string) => Promise<void>;
  onUploadAttachment: (file: File, target: string, note: string) => Promise<void>;
}

const STATUS_LABEL: Record<string, string> = {
  pending: "待开始",
  in_progress: "进行中",
  done: "已完成",
  blocked: "已阻断",
};

function dash(value: string | null | undefined) {
  return value && value.trim() ? value : "—";
}

export function ContractTab({
  model,
  execution,
  attachments,
  busy,
  onUpdateStep,
  onUpdateCheckpoint,
  onUploadAttachment,
}: ContractTabProps) {
  if (!model) {
    return <div className="drawer-empty">尚未生成工艺计划。在对话中明确目标与前置条件后，系统将自动生成。</div>;
  }

  const display = model.display;

  return (
    <div className="drawer-content">
      <section>
        <div className="tab-subheading">已确认的条件</div>
        <div className="chip-grid">
          {display.assumptions.length ? (
            display.assumptions.map((item) => (
              <span
                key={`${item.slot_name}-${item.value}`}
                className={`chip ${item.confirmed ? "ok" : "warn"}`}
              >
                {item.label}：{item.value || "未填写"}
              </span>
            ))
          ) : (
            <span className="chip subdued">尚无已确认条件</span>
          )}
        </div>
      </section>

      <section>
        <div className="tab-subheading">待确认的关键变量</div>
        <div className="chip-grid">
          {display.missing_critical_slots.length ? (
            display.missing_critical_slots.map((item) => (
              <span key={item.name} className="chip warn">
                {item.label}
              </span>
            ))
          ) : (
            <span className="chip ok">已全部补齐</span>
          )}
        </div>
      </section>

      <section>
        <div className="tab-subheading">工艺步骤</div>
        <div className="stack-list">
          {display.steps.map((step) => {
            const status = execution.stepLookup[String(step.step_number)]?.status || "pending";
            return (
              <article
                key={step.step_number}
                className={`stack-card ${step.is_irreversible ? "danger-accent" : ""}`}
              >
                <strong>第 {step.step_number} 步 · {step.action}</strong>
                <p>参数：{dash(step.parameters)}</p>
                <p>时机：{dash(step.timing_window)}</p>
                <p>检查点：{dash(step.checkpoint_id)}</p>
                <p>引用：{step.evidence_refs.length ? step.evidence_refs.join("、") : "—"}</p>
                <small>状态：{STATUS_LABEL[status] || status}</small>
              </article>
            );
          })}
        </div>
      </section>

      <section>
        <div className="tab-subheading">高风险步骤提醒</div>
        <div className="stack-list">
          {display.high_risk_warnings.length ? (
            display.high_risk_warnings.map((warning) => (
              <article key={warning.label} className="stack-card danger-accent">
                <strong>{warning.label}</strong>
                <p>动作：{dash(warning.action)}</p>
                <p>需先确认：{warning.requires_slots.map((item) => item.label).join("、") || "—"}</p>
                <p>前置检查：{dash(warning.required_checkpoint)}</p>
                <p>失败后果：{dash(warning.consequence)}</p>
              </article>
            ))
          ) : (
            <div className="side-empty">本方案无需特别标注的高风险步骤。</div>
          )}
        </div>
      </section>

      <ExecutionControls
        execution={execution}
        attachments={attachments}
        onUpdateStep={onUpdateStep}
        onUpdateCheckpoint={onUpdateCheckpoint}
        onUploadAttachment={onUploadAttachment}
        busy={busy}
      />
    </div>
  );
}
