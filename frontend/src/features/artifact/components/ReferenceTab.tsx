import type { ReferencePanelModel } from "../../../types/domain";
import { ReferenceImageStrip } from "../../../shared/components/ReferenceImageStrip";

export function ReferenceTab({ model }: { model: ReferencePanelModel }) {
  return (
    <div className="drawer-content">
      {model.artifact ? (
        <section className="stack-list">
          <article className="stack-card">
            <strong>{model.artifact.title}</strong>
            <p>{model.artifact.summary}</p>
            {model.artifact.verdict_label ? <small>{model.artifact.verdict_label}</small> : null}
          </article>

          {model.artifact.highlights?.length ? (
            <article className="stack-card">
              <strong>核心要点</strong>
              <ul className="plain-list">
                {model.artifact.highlights.map((item) => (
                  <li key={item}>{item}</li>
                ))}
              </ul>
            </article>
          ) : null}

          {model.artifact.recommendations?.length ? (
            <article className="stack-card">
              <strong>建议操作</strong>
              <ul className="plain-list">
                {model.artifact.recommendations.map((item) => (
                  <li key={item}>{item}</li>
                ))}
              </ul>
            </article>
          ) : null}
        </section>
      ) : null}

      <section>
        <div className="tab-subheading">检索到的知识片段</div>
        <div className="stack-list">
          {model.cards.length ? (
            model.cards.map((card) => (
              <article key={card.id} className="stack-card">
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
            ))
          ) : (
            <div className="side-empty">本轮未命中相关知识片段。</div>
          )}
        </div>
      </section>
    </div>
  );
}
