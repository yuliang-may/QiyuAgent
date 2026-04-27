import type { EvidencePanelModel } from "../../../types/domain";
import { ReferenceImageStrip } from "../../../shared/components/ReferenceImageStrip";

const KIND_LABEL: Record<EvidencePanelModel["kind"], string> = {
  chat: "对话相关知识片段",
  contract: "工艺计划依据",
  artifact: "产物依据",
  empty: "相关知识",
};

export function EvidenceTab({ model }: { model: EvidencePanelModel }) {
  if (!model.cards.length) {
    return (
      <div className="drawer-empty">
        本轮未命中相关知识片段。请补充材料、对象或现象信息以提升检索命中率。
      </div>
    );
  }

  const heading = KIND_LABEL[model.kind] ?? "相关知识";

  return (
    <div className="drawer-content">
      <div className="tab-subheading">{heading}</div>
      <div className="stack-list">
        {model.cards.map((card) => (
          <article key={card.id} className="stack-card">
            <strong>{card.title}</strong>
            <p>{card.summary}</p>
            <small>{card.meta}</small>
            <ReferenceImageStrip
              imageUrls={card.imageUrls}
              title={card.title}
              source={card.meta}
              idPrefix={card.id}
            />
          </article>
        ))}
      </div>
    </div>
  );
}
