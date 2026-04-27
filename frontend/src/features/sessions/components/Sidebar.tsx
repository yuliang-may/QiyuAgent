import { useNavigate } from "react-router-dom";

import type { SceneKey } from "../../../types/api";
import type { HomeViewModel, WorkbenchState } from "../../../types/domain";
import { SCENES } from "../../app/config";
import { QuickActions } from "./QuickActions";
import { RecentSessionList } from "./RecentSessionList";
import { MemorySummary } from "./MemorySummary";

interface SidebarProps {
  home: HomeViewModel | null;
  activeSession: WorkbenchState | null;
  selectedScene: SceneKey;
  onSelectScene: (scene: SceneKey) => void;
  onLogout: () => Promise<void>;
}

export function Sidebar({
  home,
  activeSession,
  selectedScene,
  onSelectScene,
  onLogout,
}: SidebarProps) {
  const navigate = useNavigate();
  const isInSession = Boolean(activeSession);
  const currentSceneTitle = SCENES[selectedScene].title;

  function openSceneHome(scene: SceneKey) {
    onSelectScene(scene);
    navigate(`/?scene=${scene}`);
  }

  function handleSelectScene(scene: SceneKey) {
    if (isInSession) {
      openSceneHome(scene);
      return;
    }
    onSelectScene(scene);
  }

  return (
    <aside className="sidebar">
      <div className="brand-block">
        <div className="brand-mark">
          <span className="seal" aria-hidden>漆</span>
          <span className="wordmark">漆语<em>LacquerTutor</em></span>
        </div>
        <p>服务漆艺非遗教学的工坊导学智能体。</p>
      </div>

      <button
        type="button"
        className={`sidebar-home ${isInSession ? "" : "active"}`}
        onClick={() => openSceneHome(selectedScene)}
      >
        <span>工作台首页</span>
        <small>
          {isInSession ? `返回${currentSceneTitle}入口` : `当前在${currentSceneTitle}首页`}
        </small>
      </button>

      <section>
        <div className="side-heading">智能体</div>
        <p className="side-note">
          {isInSession ? "选择智能体会回到对应首页，再发起新任务。" : "选择智能体只切换当前首页内容。"}
        </p>
        <QuickActions
          currentScene={selectedScene}
          onSelect={handleSelectScene}
        />
      </section>

      <section>
        <div className="side-heading">最近会话</div>
        <RecentSessionList
          sessions={home?.recentSessions || []}
          activeSessionId={activeSession?.sessionId}
          onOpen={(sessionId) => navigate(`/p/${sessionId}`)}
        />
      </section>

      <MemorySummary home={home} activeSession={activeSession} />

      <section className="sidebar-account">
        <div>
          <strong>{home?.user.displayName || "未登录"}</strong>
          <p>@{home?.user.username || "guest"}</p>
        </div>
        <button type="button" className="ghost-button" onClick={() => void onLogout()}>
          退出
        </button>
      </section>
    </aside>
  );
}
