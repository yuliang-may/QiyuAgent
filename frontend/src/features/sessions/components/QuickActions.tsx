import { SCENES } from "../../app/config";
import type { SceneKey } from "../../../types/api";

interface QuickActionsProps {
  currentScene: SceneKey;
  onSelect: (scene: SceneKey) => void;
}

const ORDER: SceneKey[] = ["chat", "planning", "troubleshooting", "safety", "knowledge", "learning"];

export function QuickActions({ currentScene, onSelect }: QuickActionsProps) {
  return (
    <div className="quick-actions">
      {ORDER.map((sceneKey) => {
        const scene = SCENES[sceneKey];
        return (
          <button
            key={scene.key}
            type="button"
            className={`quick-action ${currentScene === sceneKey ? "active" : ""}`}
            onClick={() => onSelect(sceneKey)}
          >
            <span>{scene.title}</span>
            <small>{scene.summary}</small>
          </button>
        );
      })}
    </div>
  );
}
