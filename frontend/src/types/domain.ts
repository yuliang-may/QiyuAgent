import type {
  AttachmentApi,
  ContractDisplayApi,
  MessageRowApi,
  ModuleArtifactApi,
  SceneKey,
  SessionMode,
} from "./api";

export type DrawerTab = "contract" | "evidence" | "gate" | "reference";

export type ComposerMode =
  | "new-chat"
  | "chat-message"
  | "new-scene-session"
  | "pending-answer";

export interface AuthUser {
  userId: string;
  username: string;
  displayName: string;
}

export interface SessionSummary {
  sessionId: string;
  status: string;
  statusLabel: string;
  createdAt: string;
  updatedAt: string;
  sceneKey: SceneKey;
  sceneLabel: string;
  projectTitle: string;
  projectSummary: string;
  pendingSlotLabel: string;
  hasContract: boolean;
  hasArtifact: boolean;
}

export interface TranscriptMessage {
  id: string;
  role: "user" | "assistant" | "system" | "note";
  text: string;
  referenceCards: ReferenceCardDisplay[];
  referenceImages: ReferenceImageDisplay[];
  raw: MessageRowApi;
}

export interface EvidenceCardDisplay {
  id: string;
  title: string;
  summary: string;
  meta: string;
  imageUrls: string[];
}

export interface ReferenceCardDisplay {
  id: string;
  title: string;
  summary: string;
  source: string;
  scoreLabel: string;
  imageUrls: string[];
}

export interface ReferenceImageDisplay {
  id: string;
  url: string;
  title: string;
  source: string;
}

export interface PreferenceChip {
  id: string;
  label: string;
  value: string;
}

export interface PlaybookCard {
  id: string;
  title: string;
  summary: string;
}

export interface MemoryCard {
  id: string;
  title: string;
  summary: string;
}

export interface AttachmentDisplay {
  id: string;
  name: string;
  note: string;
  downloadUrl: string;
  linkedLabel: string;
  createdAt: string;
  raw: AttachmentApi;
}

export interface ExecutionDisplay {
  raw: {
    summary: {
      stepTotal: number;
      stepDone: number;
      checkpointTotal: number;
      checkpointConfirmed: number;
      hasBlocker: boolean;
    };
  };
  steps: Array<{
    stepNumber: number;
    status: string;
    note: string;
    updatedAt: string;
  }>;
  checkpoints: Array<{
    checkpointId: string;
    status: string;
    note: string;
    updatedAt: string;
  }>;
  records: Array<{
    type: string;
    targetId: string;
    status: string;
    note: string;
    updatedAt: string;
  }>;
  stepLookup: Record<string, { status: string; note: string; updatedAt: string }>;
  checkpointLookup: Record<string, { status: string; note: string; updatedAt: string }>;
}

export interface ContractPanelModel {
  display: ContractDisplayApi;
}

export interface EvidencePanelModel {
  cards: EvidenceCardDisplay[];
  kind: "chat" | "contract" | "artifact" | "empty";
}

export interface GatePanelModel {
  status: "needs-input" | "blocked" | "review" | "safe";
  headline: string;
  reason: string;
  requiredItems: string[];
  blockingItems: string[];
  pendingQuestion: string;
  pendingQuestionReason: string;
}

export interface ReferencePanelModel {
  artifact: ModuleArtifactApi | null;
  cards: ReferenceCardDisplay[];
  rememberedPreferences: PreferenceChip[];
  learnedPlaybooks: PlaybookCard[];
  agentMemories: MemoryCard[];
}

export interface ArtifactModel {
  contract: ContractPanelModel | null;
  evidence: EvidencePanelModel;
  gate: GatePanelModel;
  reference: ReferencePanelModel;
}

export interface WorkbenchState {
  sessionId: string;
  status: string;
  sceneKey: SceneKey;
  sceneLabel: string;
  sessionMode: SessionMode;
  projectTitle: string;
  projectSummary: string;
  questionsAsked: number;
  pendingQuestion: string;
  pendingQuestionReason: string;
  filledSlots: Array<{ label: string; value: string }>;
  missingHardGates: Array<{ label: string }>;
  contractDisplay: ContractDisplayApi | null;
  execution: ExecutionDisplay;
  retrievedEvidence: EvidenceCardDisplay[];
  chatReferences: ReferenceCardDisplay[];
  moduleArtifact: ModuleArtifactApi | null;
  rememberedPreferences: PreferenceChip[];
  learnedPlaybooks: PlaybookCard[];
  agentMemories: MemoryCard[];
  attachments: AttachmentDisplay[];
  suggestedSceneKeys: SceneKey[];
  transcript: TranscriptMessage[];
  artifact: ArtifactModel;
}

export interface HomeViewModel {
  user: AuthUser;
  recentSessions: SessionSummary[];
  rememberedPreferences: PreferenceChip[];
  learnedPlaybooks: PlaybookCard[];
  agentMemories: MemoryCard[];
  recentTopics: string[];
  totalSessions: number;
  completedSessions: number;
}
