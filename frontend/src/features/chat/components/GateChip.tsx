import type { GatePanelModel } from "../../../types/domain";

export function GateChip({
  gate,
  onOpen,
}: {
  gate: GatePanelModel;
  onOpen: () => void;
}) {
  if (gate.status === "safe") {
    return null;
  }

  return (
    <button type="button" className={`gate-chip ${gate.status}`} onClick={onOpen}>
      <span>{gate.headline}</span>
      <small>{gate.reason}</small>
    </button>
  );
}
