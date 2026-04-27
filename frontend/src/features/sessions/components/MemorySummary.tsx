import type { HomeViewModel, WorkbenchState } from "../../../types/domain";

interface MemorySummaryProps {
  home: HomeViewModel | null;
  activeSession: WorkbenchState | null;
}

export function MemorySummary({ home, activeSession }: MemorySummaryProps) {
  const preferences = activeSession?.rememberedPreferences || home?.rememberedPreferences || [];
  const playbooks = activeSession?.learnedPlaybooks || home?.learnedPlaybooks || [];
  const memories = activeSession?.agentMemories || home?.agentMemories || [];

  return (
    <div className="memory-summary">
      <section>
        <div className="side-heading">已记忆偏好</div>
        <div className="chip-grid">
          {preferences.length ? (
            preferences.slice(0, 4).map((item) => (
              <span key={item.id} className="chip">
                {item.label}：{item.value}
              </span>
            ))
          ) : (
            <span className="chip subdued">无</span>
          )}
        </div>
      </section>

      <section>
        <div className="side-heading">历史流程</div>
        <div className="stack-list">
          {playbooks.length ? (
            playbooks.slice(0, 3).map((item) => (
              <article key={item.id} className="stack-card">
                <strong>{item.title}</strong>
                <p>{item.summary}</p>
              </article>
            ))
          ) : (
            <div className="side-empty">完成一次会话后，该流程将自动归档。</div>
          )}
        </div>
      </section>

      <section>
        <div className="side-heading">长期记忆</div>
        <div className="stack-list">
          {memories.length ? (
            memories.slice(0, 2).map((item) => (
              <article key={item.id} className="stack-card">
                <strong>{item.title}</strong>
                <p>{item.summary}</p>
              </article>
            ))
          ) : (
            <div className="side-empty">持续使用后，系统会沉淀长期记忆。</div>
          )}
        </div>
      </section>
    </div>
  );
}
