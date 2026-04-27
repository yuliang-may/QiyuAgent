import type {
  AttachmentApi,
  HomeResponseApi,
  MessageResponseApi,
  MessageRowApi,
  ModuleArtifactApi,
  MutationResponseApi,
  ReferenceApi,
  RetrievedEvidenceApi,
  SceneKey,
  SessionDetailApi,
  SessionOverviewApi,
  SessionStateApi,
} from "../../types/api";
import type {
  ArtifactModel,
  AttachmentDisplay,
  DrawerTab,
  EvidenceCardDisplay,
  ExecutionDisplay,
  GatePanelModel,
  HomeViewModel,
  MemoryCard,
  PlaybookCard,
  PreferenceChip,
  ReferenceCardDisplay,
  ReferenceImageDisplay,
  SessionSummary,
  TranscriptMessage,
  WorkbenchState,
} from "../../types/domain";
import { SCENES } from "./config";

const MAX_MESSAGE_REFERENCE_IMAGES = 4;

export function adaptHomeResponse(
  home: HomeResponseApi,
  sessions: SessionOverviewApi[],
): HomeViewModel {
  return {
    user: {
      userId: home.user.user_id,
      username: home.user.username,
      displayName: home.user.display_name,
    },
    recentSessions: sessions.map(adaptSessionSummary),
    rememberedPreferences: adaptPreferences(home.memory.remembered_preferences),
    learnedPlaybooks: adaptPlaybooks(home.memory.learned_playbooks),
    agentMemories: adaptMemories(home.memory.agent_memories),
    recentTopics: home.memory.recent_topics || [],
    totalSessions: home.stats.total_sessions,
    completedSessions: home.stats.completed_sessions,
  };
}

export function adaptSessionSummary(raw: SessionOverviewApi): SessionSummary {
  return {
    sessionId: raw.session_id,
    status: raw.status,
    statusLabel: statusLabel(raw.status),
    createdAt: raw.created_at,
    updatedAt: raw.updated_at,
    sceneKey: raw.scene_key,
    sceneLabel: raw.scene_label,
    projectTitle: raw.project_title,
    projectSummary: raw.project_summary,
    pendingSlotLabel: raw.pending_slot_label,
    hasContract: raw.has_contract,
    hasArtifact: raw.has_artifact,
  };
}

function statusLabel(status: string): string {
  const labels: Record<string, string> = {
    active: "进行中",
    completed: "已完成",
    blocked: "待处理",
    planned: "已规划",
    execution_in_progress: "执行中",
    abandoned: "已结束",
  };
  return labels[status] || "进行中";
}

export function adaptSessionDetail(raw: SessionDetailApi): WorkbenchState {
  const sceneKey = raw.state.scene_key;
  const moduleArtifact = hasArtifact(raw.state.module_artifact) ? raw.state.module_artifact : null;
  const transcript = raw.messages.map(adaptTranscriptMessage);
  const execution = adaptExecution(raw.state);
  const retrievedEvidence = raw.state.retrieved_evidence.map(adaptRetrievedEvidence);
  const chatReferences = raw.state.chat_references.map(adaptReferenceCard);
  const rememberedPreferences = adaptPreferences(raw.state.remembered_preferences);
  const learnedPlaybooks = adaptPlaybooks(raw.state.learned_playbooks);
  const agentMemories = adaptMemories(raw.state.agent_memories);
  const attachments = raw.state.attachments.map((item) => adaptAttachment(raw.session_id, item));
  const artifact = adaptArtifactModel(raw.state, raw.session_id);

  return {
    sessionId: raw.session_id,
    status: raw.status,
    sceneKey,
    sceneLabel: raw.state.scene_label,
    sessionMode: raw.state.session_mode,
    projectTitle: raw.state.project_title,
    projectSummary: raw.state.project_summary,
    questionsAsked: raw.state.questions_asked,
    pendingQuestion: raw.state.pending_question || "",
    pendingQuestionReason: raw.state.pending_question_reason || "",
    filledSlots: raw.state.filled_slots_display.map((item) => ({
      label: item.label,
      value: item.value || "未说明",
    })),
    missingHardGates: raw.state.missing_hard_gates_display.map((item) => ({
      label: item.label,
    })),
    contractDisplay: raw.state.contract_display,
    execution,
    retrievedEvidence,
    chatReferences,
    moduleArtifact,
    rememberedPreferences,
    learnedPlaybooks,
    agentMemories,
    attachments,
    suggestedSceneKeys: raw.state.chat_suggested_scene_keys || [],
    transcript,
    artifact,
  };
}

export function chooseDrawerTabFromState(state: WorkbenchState): DrawerTab {
  if (state.pendingQuestion) return "gate";
  if (state.contractDisplay) return "contract";
  if (state.moduleArtifact) {
    if (state.artifact.gate.status === "blocked" || state.artifact.gate.status === "review") {
      return "gate";
    }
    return "reference";
  }
  if (state.chatReferences.length > 0 || state.retrievedEvidence.length > 0) return "evidence";
  return "reference";
}

export function chooseDrawerTabFromMutation(raw: MutationResponseApi, sceneKey: SceneKey): DrawerTab {
  if (raw.type === "question") return "gate";
  if (raw.type === "contract") return "contract";
  if (raw.type === "artifact") {
    const verdict = raw.artifact.verdict || "";
    return verdict === "conditional" || verdict === "not_feasible" ? "gate" : "reference";
  }
  return sceneKey === "chat" ? "evidence" : "reference";
}

function adaptExecution(state: SessionStateApi): ExecutionDisplay {
  return {
    raw: {
      summary: {
        stepTotal: state.execution.summary.step_total,
        stepDone: state.execution.summary.step_done,
        checkpointTotal: state.execution.summary.checkpoint_total,
        checkpointConfirmed: state.execution.summary.checkpoint_confirmed,
        hasBlocker: state.execution.summary.has_blocker,
      },
    },
    steps: state.execution.steps.map((item) => ({
      stepNumber: item.step_number,
      status: item.status,
      note: item.note,
      updatedAt: item.updated_at,
    })),
    checkpoints: state.execution.checkpoints.map((item) => ({
      checkpointId: item.checkpoint_id,
      status: item.status,
      note: item.note,
      updatedAt: item.updated_at,
    })),
    records: state.execution.records.map((item) => ({
      type: item.record_type,
      targetId: item.target_id,
      status: item.status,
      note: item.note,
      updatedAt: item.updated_at,
    })),
    stepLookup: Object.fromEntries(
      Object.entries(state.execution.step_lookup).map(([key, value]) => [
        key,
        {
          status: value.status,
          note: value.note,
          updatedAt: value.updated_at,
        },
      ]),
    ),
    checkpointLookup: Object.fromEntries(
      Object.entries(state.execution.checkpoint_lookup).map(([key, value]) => [
        key,
        {
          status: value.status,
          note: value.note,
          updatedAt: value.updated_at,
        },
      ]),
    ),
  };
}

function adaptRetrievedEvidence(item: RetrievedEvidenceApi): EvidenceCardDisplay {
  return {
    id: item.evidence_id,
    title: item.evidence_id,
    summary: item.summary_en,
    meta: [item.stage, item.failure_mode].filter(Boolean).join(" · "),
    imageUrls: [],
  };
}

function adaptReferenceCard(item: ReferenceApi): ReferenceCardDisplay {
  return {
    id: item.segment_id || item.title || crypto.randomUUID(),
    title: item.title || "参考片段",
    summary: item.excerpt || "暂无摘要",
    source: item.source_label || "资料",
    scoreLabel: typeof item.score === "number" ? `${item.score.toFixed(1)} 分` : "",
    imageUrls: item.image_urls || [],
  };
}

function adaptTranscriptMessage(message: MessageRowApi): TranscriptMessage {
  if (message.role === "user") {
    return {
      id: String(message.message_id),
      role: "user",
      text: message.content,
      referenceCards: [],
      referenceImages: [],
      raw: message,
    };
  }

  try {
    const payload = JSON.parse(message.content) as Record<string, unknown>;
    const type = String(payload.type || "");

    if (type === "question") {
      return {
        id: String(message.message_id),
        role: "system",
        text: String(payload.text || "系统提出了一个关键问题。"),
        referenceCards: [],
        referenceImages: [],
        raw: message,
      };
    }

    if (type === "message") {
      const referenceCards = readReferenceList(payload.references).map(adaptReferenceCard);
      return {
        id: String(message.message_id),
        role: "assistant",
        text: String(payload.text || ""),
        referenceCards,
        referenceImages: adaptReferenceImages(referenceCards),
        raw: message,
      };
    }

    if (type === "artifact") {
      const artifact = payload.artifact as ModuleArtifactApi | undefined;
      return {
        id: String(message.message_id),
        role: "note",
        text: artifact?.summary || artifact?.title || "系统已生成参考结果。",
        referenceCards: [],
        referenceImages: [],
        raw: message,
      };
    }

    if (type === "contract") {
      return {
        id: String(message.message_id),
        role: "note",
        text: "系统已生成一份可执行方案。",
        referenceCards: [],
        referenceImages: [],
        raw: message,
      };
    }
  } catch {
    // ignore parse failure and fall back to raw content
  }

  return {
    id: String(message.message_id),
    role: "assistant",
    text: message.content,
    referenceCards: [],
    referenceImages: [],
    raw: message,
  };
}

function adaptPreferences(items: Array<Record<string, unknown>>): PreferenceChip[] {
  return items.map((item, index) => ({
    id: String(item.slot_name || item.label || index),
    label: String(item.label || item.slot_name || "偏好"),
    value: String(item.display_value || item.value || "未说明"),
  }));
}

function adaptPlaybooks(items: Array<Record<string, unknown>>): PlaybookCard[] {
  return items.map((item, index) => {
    const keySteps = readStringArrayField(item, "key_steps");
    const fallbackSummary = keySteps.length
      ? `关键步骤：${keySteps.slice(0, 3).join("、")}`
      : "已归档的历史流程，可在相似任务中参考。";

    return {
      id: String(item.source_session_id || item.session_id || item.title || index),
      title: publicTitle(item.title || item.scene_label, "历史流程"),
      summary: publicText(item.when_to_use || item.summary || item.first_step || item.stage, fallbackSummary),
    };
  });
}

function adaptMemories(items: Array<Record<string, unknown>>): MemoryCard[] {
  return items.map((item, index) => {
    const sceneTitle = sceneTitleFromKey(readMetadataSceneKey(item.metadata));
    const fallbackTitle = sceneTitle ? `${sceneTitle}长期记忆` : "长期记忆";

    return {
      id: String(item.id || item.memory_id || index),
      title: publicTitle(item.title || fallbackTitle, fallbackTitle),
      summary: publicText(
        item.summary || item.text || item.memory,
        sceneTitle ? `已记录一条与${sceneTitle}相关的长期记忆。` : "这条长期记忆尚未整理为中文。",
      ),
    };
  });
}

function adaptAttachment(sessionId: string, item: AttachmentApi): AttachmentDisplay {
  return {
    id: item.attachment_id,
    name: item.filename,
    note: item.note || "未填写说明",
    downloadUrl: `/api/sessions/${encodeURIComponent(sessionId)}/attachments/${encodeURIComponent(item.attachment_id)}`,
    linkedLabel: item.linked_step_number
      ? `步骤 ${item.linked_step_number}`
      : item.linked_checkpoint_id
        ? `检查点 ${item.linked_checkpoint_id}`
        : "会话记录",
    createdAt: item.created_at,
    raw: item,
  };
}

function adaptArtifactModel(state: SessionStateApi, sessionId: string): ArtifactModel {
  const artifact = hasArtifact(state.module_artifact) ? state.module_artifact : null;
  const referenceCards = (artifact?.references?.length ? artifact.references : state.chat_references).map(
    adaptReferenceCard,
  );
  const evidenceCards = state.retrieved_evidence.length
    ? state.retrieved_evidence.map(adaptRetrievedEvidence)
    : artifact?.references?.map(adaptReferenceToEvidence) || state.chat_references.map(adaptReferenceToEvidence);

  const gate = buildGatePanel(state, artifact);

  return {
    contract: state.contract_display ? { display: state.contract_display } : null,
    evidence: {
      cards: evidenceCards,
      kind: state.retrieved_evidence.length
        ? "contract"
        : artifact?.references?.length
          ? "artifact"
          : state.chat_references.length
            ? "chat"
            : "empty",
    },
    gate,
    reference: {
      artifact,
      cards: referenceCards,
      rememberedPreferences: adaptPreferences(state.remembered_preferences),
      learnedPlaybooks: adaptPlaybooks(state.learned_playbooks),
      agentMemories: adaptMemories(state.agent_memories),
    },
  };
}

function buildGatePanel(state: SessionStateApi, artifact: ModuleArtifactApi | null): GatePanelModel {
  const requiredItems = [
    ...state.missing_hard_gates_display.map((item) => item.label),
    ...(artifact?.required_conditions || []),
  ];
  const blockingItems = [
    ...(artifact?.blocking_factors || []),
    ...(state.contract_display?.high_risk_warnings || []).map((item) => item.label),
  ];

  if (state.pending_question) {
    return {
      status: "needs-input",
      headline: "当前还缺一个关键条件",
      reason: state.pending_question_reason || "这是当前最影响安全或结果质量的变量。",
      requiredItems,
      blockingItems,
      pendingQuestion: state.pending_question,
      pendingQuestionReason: state.pending_question_reason || "",
    };
  }

  if (artifact?.verdict === "not_feasible") {
    return {
      status: "blocked",
      headline: "暂未找到直接依据",
      reason:
        artifact.verdict_reason ||
        "当前资料不足以支持明确结论。可以补充对象、材料、工艺阶段或现象细节后继续追问。",
      requiredItems,
      blockingItems,
      pendingQuestion: "",
      pendingQuestionReason: "",
    };
  }

  if (state.execution.summary.has_blocker || state.missing_hard_gates_display.length > 0) {
    return {
      status: "blocked",
      headline: "需要先补齐关键条件",
      reason:
        "仍有影响判断或执行安全的条件尚未确认。补充信息后，系统会继续给出下一步建议。",
      requiredItems,
      blockingItems,
      pendingQuestion: "",
      pendingQuestionReason: "",
    };
  }

  if (artifact?.verdict === "conditional") {
    return {
      status: "review",
      headline: "当前是有条件可行",
      reason: artifact.verdict_reason || "系统建议先补齐条件，再决定是否放行。",
      requiredItems,
      blockingItems,
      pendingQuestion: "",
      pendingQuestionReason: "",
    };
  }

  return {
    status: "safe",
    headline: "当前没有显式阻断",
    reason: "你可以继续查看合同、证据和参考资料。",
    requiredItems,
    blockingItems,
    pendingQuestion: "",
    pendingQuestionReason: "",
  };
}

function adaptReferenceToEvidence(item: ReferenceApi): EvidenceCardDisplay {
  return {
    id: item.segment_id || item.title || crypto.randomUUID(),
    title: item.title || "参考片段",
    summary: item.excerpt || "暂无摘要",
    meta: item.source_label || "资料",
    imageUrls: item.image_urls || [],
  };
}

function adaptReferenceImages(
  cards: ReferenceCardDisplay[],
  limit = MAX_MESSAGE_REFERENCE_IMAGES,
): ReferenceImageDisplay[] {
  const images: ReferenceImageDisplay[] = [];
  const seenUrls = new Set<string>();

  for (const card of cards) {
    for (const url of card.imageUrls) {
      const trimmedUrl = url.trim();
      if (!trimmedUrl || seenUrls.has(trimmedUrl)) continue;
      seenUrls.add(trimmedUrl);
      images.push({
        id: `${card.id}-${images.length}-${trimmedUrl}`,
        url: trimmedUrl,
        title: card.title,
        source: card.source,
      });
      if (images.length >= limit) {
        return images;
      }
    }
  }

  return images;
}

function readReferenceList(value: unknown): ReferenceApi[] {
  if (!Array.isArray(value)) return [];

  return value
    .filter((item): item is Record<string, unknown> => Boolean(item && typeof item === "object"))
    .map((item) => ({
      segment_id: readStringField(item, "segment_id"),
      source_label: readStringField(item, "source_label"),
      title: readStringField(item, "title"),
      excerpt: readStringField(item, "excerpt"),
      score: typeof item.score === "number" ? item.score : undefined,
      image_urls: readStringArrayField(item, "image_urls"),
    }));
}

function readStringField(item: Record<string, unknown>, key: string): string | undefined {
  const value = item[key];
  return typeof value === "string" ? value : undefined;
}

function readStringArrayField(item: Record<string, unknown>, key: string): string[] {
  const value = item[key];
  if (!Array.isArray(value)) return [];
  return value.filter((entry): entry is string => typeof entry === "string" && entry.trim().length > 0);
}

function hasArtifact(value: SessionStateApi["module_artifact"]): value is ModuleArtifactApi {
  return Boolean(value && typeof value === "object" && "artifact_type" in value);
}

function readMetadataSceneKey(value: unknown): string {
  if (!value || typeof value !== "object") {
    return "";
  }
  const sceneKey = (value as Record<string, unknown>).scene_key;
  return typeof sceneKey === "string" ? sceneKey : "";
}

function publicTitle(value: unknown, fallback: string): string {
  const sceneTitle = sceneTitleFromKey(value);
  return sceneTitle || publicText(value, fallback);
}

function publicText(value: unknown, fallback: string): string {
  const text = String(value || "").trim();
  if (!text) return fallback;

  const sceneTitle = sceneTitleFromKey(text);
  if (sceneTitle) return sceneTitle;

  if (!containsCjk(text) && containsLatinWords(text)) {
    return fallback;
  }

  return text;
}

function sceneTitleFromKey(value: unknown): string {
  const key = String(value || "").trim();
  return isSceneKey(key) ? SCENES[key].title : "";
}

function isSceneKey(value: string): value is SceneKey {
  return Object.prototype.hasOwnProperty.call(SCENES, value);
}

function containsCjk(value: string): boolean {
  return /[\u3400-\u9fff]/.test(value);
}

function containsLatinWords(value: string): boolean {
  return /[A-Za-z]{3,}/.test(value);
}

export function sceneTitle(sceneKey: SceneKey): string {
  return SCENES[sceneKey].title;
}
