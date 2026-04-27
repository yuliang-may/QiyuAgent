import { create } from "zustand";

import { apiRequest, ApiError } from "../../shared/api/client";
import type {
  HomeResponseApi,
  MeResponseApi,
  SceneKey,
  SessionDetailApi,
  SessionMode,
  SessionMutationApi,
  SessionOverviewApi,
  SessionsListResponseApi,
} from "../../types/api";
import type { ComposerMode, DrawerTab, HomeViewModel, WorkbenchState } from "../../types/domain";
import {
  adaptHomeResponse,
  adaptSessionDetail,
  chooseDrawerTabFromMutation,
  chooseDrawerTabFromState,
} from "./adapters";
import { buildQuickFollowupQuery, buildSceneQuery } from "./config";

type AuthStatus = "unknown" | "authenticated" | "guest";

interface KickoffDraft {
  piece: string;
  goal: string;
  known: string;
}

interface AppStore {
  authStatus: AuthStatus;
  home: HomeViewModel | null;
  activeSession: WorkbenchState | null;
  selectedScene: SceneKey;
  selectedMode: SessionMode;
  kickoff: KickoffDraft;
  drawerOpen: boolean;
  drawerTab: DrawerTab;
  error: string;
  booting: boolean;
  loadingSession: boolean;
  mutating: boolean;
  initializeAuth: () => Promise<void>;
  refreshHome: () => Promise<void>;
  loadSession: (sessionId: string, preferredTab?: DrawerTab | null) => Promise<void>;
  login: (username: string, password: string) => Promise<void>;
  register: (displayName: string, username: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
  setSelectedScene: (scene: SceneKey) => void;
  setSelectedMode: (mode: SessionMode) => void;
  updateKickoff: (patch: Partial<KickoffDraft>) => void;
  clearKickoff: () => void;
  setDrawerTab: (tab: DrawerTab) => void;
  setDrawerOpen: (open: boolean) => void;
  clearError: () => void;
  getComposerMode: () => ComposerMode;
  createSessionFromKickoff: () => Promise<string>;
  createSessionFromQuickText: (sceneKey: SceneKey, text: string) => Promise<string>;
  submitWorkbenchInput: (text: string) => Promise<string>;
  updateExecutionStep: (stepNumber: number, status: string, note: string) => Promise<void>;
  updateCheckpoint: (checkpointId: string, status: string, note: string) => Promise<void>;
  uploadAttachment: (file: File, target: string, note: string) => Promise<void>;
}

export const useAppStore = create<AppStore>((set, get) => ({
  authStatus: "unknown",
  home: null,
  activeSession: null,
  selectedScene: "chat",
  selectedMode: "agent",
  kickoff: {
    piece: "",
    goal: "",
    known: "",
  },
  drawerOpen: false,
  drawerTab: "reference",
  error: "",
  booting: true,
  loadingSession: false,
  mutating: false,

  async initializeAuth() {
    set({ booting: true, error: "" });
    try {
      const me = await apiRequest<MeResponseApi>("/api/me");
      if (!me.authenticated || !me.user) {
        set({
          authStatus: "guest",
          home: null,
          activeSession: null,
          booting: false,
        });
        return;
      }

      set({ authStatus: "authenticated" });
      await get().refreshHome();
      set({ booting: false });
    } catch (error) {
      set({
        authStatus: "guest",
        home: null,
        activeSession: null,
        error: normalizeError(error),
        booting: false,
      });
    }
  },

  async refreshHome() {
    const [home, sessions] = await Promise.all([
      apiRequest<HomeResponseApi>("/api/home"),
      apiRequest<SessionsListResponseApi>("/api/sessions?limit=20"),
    ]);

    set({
      home: adaptHomeResponse(home, sessions.sessions as SessionOverviewApi[]),
    });
  },

  async loadSession(sessionId, preferredTab) {
    set({ loadingSession: true, error: "" });
    try {
      const detail = await apiRequest<SessionDetailApi>(`/api/sessions/${encodeURIComponent(sessionId)}`);
      const adapted = adaptSessionDetail(detail);
      const shouldOpenDrawer = Boolean(
        preferredTab ||
          (adapted.sceneKey !== "chat" &&
            (adapted.pendingQuestion ||
              adapted.contractDisplay ||
              adapted.moduleArtifact ||
              adapted.retrievedEvidence.length)),
      );
      set({
        activeSession: adapted,
        selectedScene: adapted.sceneKey,
        selectedMode: adapted.sessionMode,
        drawerTab: preferredTab || chooseDrawerTabFromState(adapted),
        drawerOpen: shouldOpenDrawer,
        loadingSession: false,
      });
    } catch (error) {
      set({
        error: normalizeError(error),
        loadingSession: false,
      });
      throw error;
    }
  },

  async login(username, password) {
    set({ mutating: true, error: "" });
    try {
      await apiRequest("/api/auth/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ username, password }),
      });
      set({ authStatus: "authenticated", mutating: false });
      await get().refreshHome();
    } catch (error) {
      set({ error: normalizeError(error), mutating: false });
      throw error;
    }
  },

  async register(displayName, username, password) {
    set({ mutating: true, error: "" });
    try {
      await apiRequest("/api/auth/register", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          display_name: displayName,
          username,
          password,
        }),
      });
      set({ authStatus: "authenticated", mutating: false });
      await get().refreshHome();
    } catch (error) {
      set({ error: normalizeError(error), mutating: false });
      throw error;
    }
  },

  async logout() {
    set({ mutating: true, error: "" });
    try {
      await apiRequest("/api/auth/logout", {
        method: "POST",
      });
      set({
        authStatus: "guest",
        home: null,
        activeSession: null,
        selectedScene: "chat",
        selectedMode: "agent",
        kickoff: { piece: "", goal: "", known: "" },
        drawerOpen: false,
        drawerTab: "reference",
        mutating: false,
      });
    } catch (error) {
      set({ error: normalizeError(error), mutating: false });
      throw error;
    }
  },

  setSelectedScene(scene) {
    set({ selectedScene: scene });
  },

  setSelectedMode(mode) {
    set({ selectedMode: mode });
  },

  updateKickoff(patch) {
    set((state) => ({
      kickoff: {
        ...state.kickoff,
        ...patch,
      },
    }));
  },

  clearKickoff() {
    set({
      kickoff: { piece: "", goal: "", known: "" },
    });
  },

  setDrawerTab(tab) {
    set({ drawerTab: tab, drawerOpen: true });
  },

  setDrawerOpen(open) {
    set({ drawerOpen: open });
  },

  clearError() {
    set({ error: "" });
  },

  getComposerMode() {
    const state = get();
    const active = state.activeSession;
    if (!active) {
      return "new-chat";
    }
    if (active.sceneKey === "chat") {
      return "chat-message";
    }
    if (active.pendingQuestion) {
      return "pending-answer";
    }
    return "new-scene-session";
  },

  async createSessionFromKickoff() {
    const state = get();
    const query = buildSceneQuery({
      sceneKey: state.selectedScene,
      piece: state.kickoff.piece,
      goal: state.kickoff.goal,
      known: state.kickoff.known,
      mode: state.selectedMode,
    });

    if (!query.trim()) {
      throw new ApiError("请先输入当前要处理的问题或目标。", 400);
    }

    return createSession(set, get, query, state.selectedScene);
  },

  async createSessionFromQuickText(sceneKey, text) {
    const state = get();
    const query =
      sceneKey === "chat"
        ? text.trim()
        : buildQuickFollowupQuery(sceneKey, text.trim(), state.selectedMode);

    if (!query.trim()) {
      throw new ApiError("请输入要处理的内容。", 400);
    }

    return createSession(set, get, query, sceneKey);
  },

  async submitWorkbenchInput(text) {
    const trimmed = text.trim();
    if (!trimmed) {
      throw new ApiError("请输入内容。", 400);
    }

    const state = get();
    const active = state.activeSession;
    if (!active) {
      return get().createSessionFromQuickText(state.selectedScene, trimmed);
    }

    set({ mutating: true, error: "" });

    try {
      if (active.sceneKey === "chat") {
        await apiRequest<SessionMutationApi>(`/api/sessions/${encodeURIComponent(active.sessionId)}/messages`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ message: trimmed }),
        });
        await get().loadSession(active.sessionId, null);
        set({ mutating: false });
        return active.sessionId;
      }

      if (active.pendingQuestion) {
        const response = await apiRequest<SessionMutationApi>(
          `/api/sessions/${encodeURIComponent(active.sessionId)}/answer`,
          {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ answer: trimmed }),
          },
        );
        await get().loadSession(
          active.sessionId,
          chooseDrawerTabFromMutation(response.response, active.sceneKey),
        );
        set({ mutating: false });
        return active.sessionId;
      }

      set({ mutating: false });
      return await get().createSessionFromQuickText(active.sceneKey, trimmed);
    } catch (error) {
      set({ error: normalizeError(error), mutating: false });
      throw error;
    }
  },

  async updateExecutionStep(stepNumber, status, note) {
    const active = requireActiveSession(get);
    set({ mutating: true, error: "" });
    try {
      await apiRequest(`/api/sessions/${encodeURIComponent(active.sessionId)}/execution/steps/${stepNumber}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ status, note }),
      });
      await get().loadSession(active.sessionId, "contract");
      set({ mutating: false });
    } catch (error) {
      set({ error: normalizeError(error), mutating: false });
      throw error;
    }
  },

  async updateCheckpoint(checkpointId, status, note) {
    const active = requireActiveSession(get);
    set({ mutating: true, error: "" });
    try {
      await apiRequest(
        `/api/sessions/${encodeURIComponent(active.sessionId)}/execution/checkpoints/${encodeURIComponent(checkpointId)}`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ status, note }),
        },
      );
      await get().loadSession(active.sessionId, "contract");
      set({ mutating: false });
    } catch (error) {
      set({ error: normalizeError(error), mutating: false });
      throw error;
    }
  },

  async uploadAttachment(file, target, note) {
    const active = requireActiveSession(get);
    const formData = new FormData();
    formData.append("file", file);
    formData.append("note", note.trim());
    if (target.startsWith("step:")) {
      formData.append("linked_step_number", target.split(":")[1] || "");
    } else if (target.startsWith("checkpoint:")) {
      formData.append("linked_checkpoint_id", target.split(":")[1] || "");
    }

    set({ mutating: true, error: "" });
    try {
      await apiRequest(`/api/sessions/${encodeURIComponent(active.sessionId)}/attachments`, {
        method: "POST",
        body: formData,
      });
      await get().loadSession(active.sessionId, "contract");
      set({ mutating: false });
    } catch (error) {
      set({ error: normalizeError(error), mutating: false });
      throw error;
    }
  },
}));

async function createSession(
  set: (partial: Partial<AppStore> | ((state: AppStore) => Partial<AppStore>)) => void,
  get: () => AppStore,
  query: string,
  sceneKey: SceneKey,
): Promise<string> {
  set({ mutating: true, error: "" });
  try {
    const response = await apiRequest<SessionMutationApi>("/api/sessions", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        query,
        mode: get().selectedMode,
        scene_key: sceneKey,
      }),
    });
    await get().refreshHome();
    const preferredTab =
      response.state.scene_key === "chat"
        ? null
        : chooseDrawerTabFromMutation(response.response, response.state.scene_key);
    await get().loadSession(
      response.session_id,
      preferredTab,
    );
    set({
      mutating: false,
      kickoff: { piece: "", goal: "", known: "" },
    });
    return response.session_id;
  } catch (error) {
    set({ error: normalizeError(error), mutating: false });
    throw error;
  }
}

function normalizeError(error: unknown): string {
  if (error instanceof Error) return error.message;
  return "请求失败。";
}

function requireActiveSession(get: () => AppStore): WorkbenchState {
  const active = get().activeSession;
  if (!active) {
    throw new ApiError("当前没有活动项目。", 400);
  }
  return active;
}
