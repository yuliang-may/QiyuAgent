export type SceneKey =
  | "chat"
  | "planning"
  | "troubleshooting"
  | "knowledge"
  | "learning"
  | "safety";

export type SessionMode = "agent" | "workflow";

export interface UserApi {
  user_id: string;
  username: string;
  display_name: string;
}

export interface SessionOverviewApi {
  session_id: string;
  status: string;
  created_at: string;
  updated_at: string;
  scene_key: SceneKey;
  scene_label: string;
  project_title: string;
  project_summary: string;
  task_type: string;
  stage: string;
  questions_asked: number;
  filled_slots_count: number;
  pending_slot_label: string;
  has_contract: boolean;
  has_artifact: boolean;
}

export interface HomeResponseApi {
  user: UserApi;
  recent_sessions: SessionOverviewApi[];
  memory: {
    remembered_preferences: Array<Record<string, unknown>>;
    learned_playbooks: Array<Record<string, unknown>>;
    completed_sessions: number;
    recent_topics: string[];
    agent_memories: Array<Record<string, unknown>>;
  };
  stats: {
    total_sessions: number;
    completed_sessions: number;
  };
}

export interface SessionsListResponseApi {
  sessions: SessionOverviewApi[];
}

export interface MessageRowApi {
  message_id: number;
  session_id: string;
  role: string;
  content: string;
  created_at: string;
}

export interface DisplayItemApi {
  name: string;
  label: string;
  value?: string;
}

export interface ExecutionRecordApi {
  record_type: string;
  target_id: string;
  status: string;
  note: string;
  updated_at: string;
}

export interface ExecutionStateApi {
  steps: Array<{
    step_number: number;
    status: string;
    note: string;
    updated_at: string;
  }>;
  checkpoints: Array<{
    checkpoint_id: string;
    status: string;
    note: string;
    updated_at: string;
  }>;
  records: ExecutionRecordApi[];
  summary: {
    step_total: number;
    step_done: number;
    checkpoint_total: number;
    checkpoint_confirmed: number;
    has_blocker: boolean;
  };
  step_lookup: Record<
    string,
    {
      step_number: number;
      status: string;
      note: string;
      updated_at: string;
    }
  >;
  checkpoint_lookup: Record<
    string,
    {
      checkpoint_id: string;
      status: string;
      note: string;
      updated_at: string;
    }
  >;
}

export interface ContractDisplayApi {
  assumptions: Array<{
    slot_name: string;
    label: string;
    value: string;
    confirmed: boolean;
    note: string;
  }>;
  missing_critical_slots: DisplayItemApi[];
  steps: Array<{
    step_number: number;
    action: string;
    parameters: string;
    timing_window: string;
    checkpoint_id: string;
    evidence_refs: string[];
    is_irreversible: boolean;
  }>;
  high_risk_warnings: Array<{
    label: string;
    action: string;
    requires_slots: DisplayItemApi[];
    required_checkpoint: string;
    consequence: string;
  }>;
  checkpoints: Array<{
    checkpoint_id: string;
    description: string;
    evidence_refs: string[];
  }>;
  contingencies: Array<{
    condition: string;
    action: string;
    recheck_checkpoint: string;
    evidence_refs: string[];
  }>;
  summary: {
    step_count: number;
    warning_count: number;
    checkpoint_count: number;
    contingency_count: number;
    stop_reason: string;
  };
}

export interface AttachmentApi {
  attachment_id: string;
  filename: string;
  stored_name: string;
  relative_path: string;
  mime_type: string;
  size_bytes: number;
  created_at: string;
  linked_step_number: number | null;
  linked_checkpoint_id: string;
  note: string;
}

export interface ReferenceApi {
  segment_id?: string;
  source_label?: string;
  title?: string;
  excerpt?: string;
  score?: number;
  image_urls?: string[];
}

export interface RetrievedEvidenceApi {
  evidence_id: string;
  stage: string;
  failure_mode?: string | null;
  summary_en: string;
}

export interface ModuleArtifactApi {
  artifact_type: string;
  title: string;
  summary: string;
  verdict?: string;
  verdict_label?: string;
  verdict_reason?: string;
  highlights?: string[];
  recommendations?: string[];
  safety_notes?: string[];
  follow_up_questions?: string[];
  required_conditions?: string[];
  blocking_factors?: string[];
  phases?: Array<{
    phase: string;
    focus: string;
    practice: string;
    completion_signal: string;
  }>;
  references?: ReferenceApi[];
  markdown?: string;
}

export interface SessionStateApi {
  scene_key: SceneKey;
  scene_label: string;
  project_title: string;
  project_summary: string;
  session_mode: SessionMode;
  task_type: string;
  stage: string;
  failure_mode?: string | null;
  questions_asked: number;
  pending_slot_name?: string | null;
  pending_slot_label?: string;
  pending_question: string;
  pending_question_reason: string;
  filled_slots_display: DisplayItemApi[];
  missing_hard_gates_display: DisplayItemApi[];
  retrieved_evidence: RetrievedEvidenceApi[];
  remembered_preferences: Array<Record<string, unknown>>;
  recalled_sessions: Array<Record<string, unknown>>;
  learned_playbooks: Array<Record<string, unknown>>;
  agent_memories: Array<Record<string, unknown>>;
  chat_references: ReferenceApi[];
  chat_suggested_scene_keys: SceneKey[];
  module_artifact: ModuleArtifactApi | Record<string, never>;
  execution: ExecutionStateApi;
  attachments: AttachmentApi[];
  contract: Record<string, unknown> | null;
  contract_display: ContractDisplayApi | null;
}

export interface SessionDetailApi {
  session_id: string;
  status: string;
  overview: SessionOverviewApi;
  state: SessionStateApi;
  messages: MessageRowApi[];
}

export interface QuestionResponseApi {
  type: "question";
  slot_name: string;
  slot_label: string;
  text: string;
  reason?: string;
  priority?: number;
}

export interface MessageResponseApi {
  type: "message";
  text: string;
  suggested_scene_keys?: SceneKey[];
  references?: ReferenceApi[];
}

export interface ArtifactResponseApi {
  type: "artifact";
  artifact: ModuleArtifactApi;
  markdown: string;
}

export interface ContractResponseApi {
  type: "contract";
  contract: Record<string, unknown> | null;
  contract_display: ContractDisplayApi | null;
  markdown: string;
}

export type MutationResponseApi =
  | QuestionResponseApi
  | MessageResponseApi
  | ArtifactResponseApi
  | ContractResponseApi;

export interface SessionMutationApi {
  session_id: string;
  state: SessionStateApi;
  response: MutationResponseApi;
}

export interface MeResponseApi {
  authenticated: boolean;
  user?: UserApi;
}
