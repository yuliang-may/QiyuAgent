import type { GatePanelModel } from "../../../types/domain";

export function GateTab({ model }: { model: GatePanelModel }) {
  return (
    <div className="drawer-content">
      <section className={`gate-summary ${model.status}`}>
        <strong>{model.headline}</strong>
        <p>{model.reason}</p>
      </section>

      {model.pendingQuestion ? (
        <section>
          <div className="tab-subheading">当前待确认项</div>
          <article className="stack-card">
            <strong>{model.pendingQuestion}</strong>
            <p>
              {model.pendingQuestionReason ||
                "补齐此项后方可推进至下一步。"}
            </p>
          </article>
        </section>
      ) : null}

      <section>
        <div className="tab-subheading">待补齐条件</div>
        <div className="chip-grid">
          {model.requiredItems.length ? (
            model.requiredItems.map((item) => (
              <span key={item} className="chip warn">
                {item}
              </span>
            ))
          ) : (
            <span className="chip subdued">无</span>
          )}
        </div>
      </section>

      <section>
        <div className="tab-subheading">当前阻断项</div>
        <div className="stack-list">
          {model.blockingItems.length ? (
            model.blockingItems.map((item) => (
              <article key={item} className="stack-card danger-accent">
                <p>{item}</p>
              </article>
            ))
          ) : (
            <div className="side-empty">无阻断项。</div>
          )}
        </div>
      </section>
    </div>
  );
}
