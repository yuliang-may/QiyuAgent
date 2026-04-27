import { useEffect } from "react";
import { useNavigate, useParams, useSearchParams } from "react-router-dom";

import { ArtifactDrawer } from "../features/artifact/components/ArtifactDrawer";
import { Composer } from "../features/chat/components/Composer";
import { ConversationPane } from "../features/chat/components/ConversationPane";
import { GateChip } from "../features/chat/components/GateChip";
import { Sidebar } from "../features/sessions/components/Sidebar";
import { sceneTitle } from "../features/app/adapters";
import { useAppStore } from "../features/app/store";
import type { DrawerTab } from "../types/domain";

export function WorkbenchPage() {
  const { sessionId = "" } = useParams();
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();

  const home = useAppStore((state) => state.home);
  const activeSession = useAppStore((state) => state.activeSession);
  const selectedScene = useAppStore((state) => state.selectedScene);
  const drawerOpen = useAppStore((state) => state.drawerOpen);
  const drawerTab = useAppStore((state) => state.drawerTab);
  const mutating = useAppStore((state) => state.mutating);
  const loadingSession = useAppStore((state) => state.loadingSession);
  const error = useAppStore((state) => state.error);
  const loadSession = useAppStore((state) => state.loadSession);
  const setDrawerOpen = useAppStore((state) => state.setDrawerOpen);
  const setDrawerTab = useAppStore((state) => state.setDrawerTab);
  const setSelectedScene = useAppStore((state) => state.setSelectedScene);
  const submitWorkbenchInput = useAppStore((state) => state.submitWorkbenchInput);
  const updateExecutionStep = useAppStore((state) => state.updateExecutionStep);
  const updateCheckpoint = useAppStore((state) => state.updateCheckpoint);
  const uploadAttachment = useAppStore((state) => state.uploadAttachment);
  const getComposerMode = useAppStore((state) => state.getComposerMode);
  const logout = useAppStore((state) => state.logout);

  useEffect(() => {
    if (!sessionId) return;
    const requestedTab = searchParams.get("tab");
    void loadSession(sessionId, isDrawerTab(requestedTab) ? requestedTab : undefined);
  }, [loadSession, searchParams, sessionId]);

  useEffect(() => {
    if (activeSession) {
      setSelectedScene(activeSession.sceneKey);
    }
  }, [activeSession, setSelectedScene]);

  if (!sessionId) {
    return <div className="screen-loader">正在加载会话…</div>;
  }

  const composerMode = getComposerMode();
  const canExport = Boolean(activeSession);
  const isChat = activeSession?.sceneKey === "chat";

  // 标题里已经包含 summary 时，不再重复。
  const titleText = activeSession?.projectTitle || sceneTitle(selectedScene);
  const summaryText = activeSession?.projectSummary || "";
  const showSummary = Boolean(summaryText) && !titleText.includes(summaryText.trim().slice(0, 12));
  const sceneHomeUrl = `/?scene=${activeSession?.sceneKey ?? selectedScene}`;
  const sceneLabel = activeSession?.sceneLabel || sceneTitle(selectedScene);

  return (
    <main className="app-shell">
      <Sidebar
        home={home}
        activeSession={activeSession}
        selectedScene={selectedScene}
        onSelectScene={setSelectedScene}
        onLogout={logout}
      />

      <section className={`workspace-stage ${isChat ? "chat-workspace" : ""}`}>
        <header className="workspace-header">
          <div className="workspace-title-area">
            <button
              type="button"
              className="back-button"
              onClick={() => navigate(sceneHomeUrl)}
            >
              <span aria-hidden>←</span>
              <span>返回首页</span>
            </button>
            <nav className="workspace-breadcrumb" aria-label="当前位置">
              <button type="button" onClick={() => navigate(sceneHomeUrl)}>
                首页
              </button>
              <span aria-hidden>›</span>
              <span>{sceneLabel}</span>
              <span aria-hidden>›</span>
              <span>当前会话</span>
            </nav>
            <span className="eyebrow">当前会话</span>
            <h2>{titleText}</h2>
            {showSummary ? (
              <p>
                {isChat
                  ? summaryText
                  : summaryText || "会话加载中。"}
              </p>
            ) : null}
          </div>
          <div className="header-actions">
            <button
              type="button"
              className="ghost-button"
              onClick={() => setDrawerOpen(!drawerOpen)}
            >
              {drawerOpen ? "收起资料" : "项目资料"}
            </button>
            {canExport ? (
              <a
                className="ghost-button"
                href={`/api/sessions/${encodeURIComponent(sessionId)}/export/markdown`}
                target="_blank"
                rel="noreferrer"
              >
                导出
              </a>
            ) : null}
            <button
              type="button"
              className="ghost-button"
              onClick={() => navigate(sceneHomeUrl)}
            >
              回到首页新建
            </button>
          </div>
        </header>

        {activeSession && !isChat ? (
          <GateChip
            gate={activeSession.artifact.gate}
            onOpen={() => {
              setDrawerTab("gate");
              setDrawerOpen(true);
              setSearchParams((current) => {
                current.set("tab", "gate");
                return current;
              });
            }}
          />
        ) : null}

        {error ? <p className="form-error inline-error">{error}</p> : null}

        <section className="workspace-panel">
          {loadingSession || !activeSession ? (
            <div className="screen-loader">正在加载会话…</div>
          ) : (
            <>
              <ConversationPane messages={activeSession.transcript} thinking={mutating} />
              <Composer
                mode={composerMode}
                sceneKey={activeSession.sceneKey}
                pendingSlotLabel={activeSession.pendingQuestion ? activeSession.artifact.gate.headline : ""}
                busy={mutating}
                onSubmit={async (text) => {
                  const nextSessionId = await submitWorkbenchInput(text);
                  if (nextSessionId !== activeSession.sessionId) {
                    navigate(`/p/${nextSessionId}`);
                  }
                }}
              />
            </>
          )}
        </section>
      </section>

      {activeSession ? (
        <ArtifactDrawer
          artifact={activeSession.artifact}
          activeTab={drawerTab}
          open={drawerOpen}
          onClose={() => setDrawerOpen(false)}
          onTabChange={(tab) => {
            setDrawerTab(tab);
            setSearchParams((current) => {
              current.set("tab", tab);
              return current;
            });
          }}
          execution={activeSession.execution}
          attachments={activeSession.attachments}
          busy={mutating}
          onUpdateStep={updateExecutionStep}
          onUpdateCheckpoint={updateCheckpoint}
          onUploadAttachment={uploadAttachment}
        />
      ) : null}
    </main>
  );
}

function isDrawerTab(value: string | null): value is DrawerTab {
  return value === "contract" || value === "evidence" || value === "gate" || value === "reference";
}
