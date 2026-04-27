import type { ArtifactModel, AttachmentDisplay, DrawerTab, ExecutionDisplay } from "../../../types/domain";
import { ContractTab } from "./ContractTab";
import { EvidenceTab } from "./EvidenceTab";
import { GateTab } from "./GateTab";
import { ReferenceTab } from "./ReferenceTab";

interface ArtifactDrawerProps {
  artifact: ArtifactModel;
  activeTab: DrawerTab;
  open: boolean;
  onClose: () => void;
  onTabChange: (tab: DrawerTab) => void;
  execution: ExecutionDisplay;
  attachments: AttachmentDisplay[];
  busy: boolean;
  onUpdateStep: (stepNumber: number, status: string, note: string) => Promise<void>;
  onUpdateCheckpoint: (checkpointId: string, status: string, note: string) => Promise<void>;
  onUploadAttachment: (file: File, target: string, note: string) => Promise<void>;
}

const TABS: DrawerTab[] = ["contract", "evidence", "gate", "reference"];

const TAB_LABEL: Record<DrawerTab, string> = {
  contract: "工艺计划",
  evidence: "实证记录",
  gate: "安全门控",
  reference: "知识引用",
};

export function ArtifactDrawer(props: ArtifactDrawerProps) {
  const {
    artifact,
    activeTab,
    open,
    onClose,
    onTabChange,
    execution,
    attachments,
    busy,
    onUpdateStep,
    onUpdateCheckpoint,
    onUploadAttachment,
  } = props;

  return (
    <>
      <div className={`drawer-backdrop ${open ? "visible" : ""}`} onClick={onClose} />
      <aside className={`artifact-drawer ${open ? "open" : ""}`}>
        <header className="drawer-header">
          <div>
            <span className="eyebrow">项目资料</span>
            <h2>本会话的结构化产物</h2>
          </div>
          <button type="button" className="ghost-button" onClick={onClose}>
            收起
          </button>
        </header>

        <div className="drawer-tabs" role="tablist">
          {TABS.map((tab) => (
            <button
              key={tab}
              type="button"
              role="tab"
              aria-selected={activeTab === tab}
              className={activeTab === tab ? "active" : ""}
              onClick={() => onTabChange(tab)}
            >
              {TAB_LABEL[tab]}
            </button>
          ))}
        </div>

        <div className="drawer-panel">
          {activeTab === "contract" ? (
            <ContractTab
              model={artifact.contract}
              execution={execution}
              attachments={attachments}
              busy={busy}
              onUpdateStep={onUpdateStep}
              onUpdateCheckpoint={onUpdateCheckpoint}
              onUploadAttachment={onUploadAttachment}
            />
          ) : null}
          {activeTab === "evidence" ? <EvidenceTab model={artifact.evidence} /> : null}
          {activeTab === "gate" ? <GateTab model={artifact.gate} /> : null}
          {activeTab === "reference" ? <ReferenceTab model={artifact.reference} /> : null}
        </div>
      </aside>
    </>
  );
}
