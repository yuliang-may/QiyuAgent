import type { SessionSummary } from "../../../types/domain";

interface RecentSessionListProps {
  sessions: SessionSummary[];
  activeSessionId?: string;
  onOpen: (sessionId: string) => void;
}

export function RecentSessionList({ sessions, activeSessionId, onOpen }: RecentSessionListProps) {
  if (!sessions.length) {
    return <div className="side-empty">暂无会话。新建一个即可在此查看。</div>;
  }

  return (
    <div className="recent-list">
      {sessions.map((session) => (
        <button
          key={session.sessionId}
          type="button"
          className={`recent-item ${activeSessionId === session.sessionId ? "active" : ""}`}
          onClick={() => onOpen(session.sessionId)}
        >
          <strong>{session.projectTitle}</strong>
          <span>{session.projectSummary || session.sceneLabel}</span>
          <small>{session.sceneLabel} · {session.statusLabel}</small>
        </button>
      ))}
    </div>
  );
}
