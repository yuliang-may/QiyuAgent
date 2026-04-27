import type { ReferenceCardDisplay } from "../../../types/domain";
import { ReferenceImageStrip } from "../../../shared/components/ReferenceImageStrip";

export function ReferencePanel({ references }: { references: ReferenceCardDisplay[] }) {
  return (
    <aside className="reference-panel">
      <div className="panel-header compact">
        <div>
          <span className="eyebrow">知识引用</span>
          <h3>本轮命中的知识片段</h3>
        </div>
      </div>

      <div className="stack-list">
        {references.length ? (
          references.map((item) => (
            <article key={item.id} className="stack-card">
              <strong>{item.title}</strong>
              <p>{item.summary}</p>
              <small>{[item.source, item.scoreLabel].filter(Boolean).join(" · ")}</small>
              <ReferenceImageStrip
                imageUrls={item.imageUrls}
                title={item.title}
                source={item.source}
                idPrefix={item.id}
              />
            </article>
          ))
        ) : (
          <div className="side-empty">
            本轮未命中相关知识片段。请补充材料、对象或现象信息以提升检索命中率。
          </div>
        )}
      </div>
    </aside>
  );
}
