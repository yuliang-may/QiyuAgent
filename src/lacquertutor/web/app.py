"""FastAPI product shell for the LacquerTutor web app."""

from __future__ import annotations

import json
import mimetypes
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal
from uuid import uuid4

from fastapi import FastAPI, File, Form, HTTPException, Query, Request, Response, UploadFile, status
from fastapi.responses import FileResponse, HTMLResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from lacquertutor.agent.pipeline import LacquerTutorAgent
from lacquertutor.agent.state import ConversationState
from lacquertutor.agent.session_modes import (
    DEFAULT_SESSION_MODE,
    get_session_mode_options,
    normalize_session_mode,
)
from lacquertutor.config import Settings
from lacquertutor.models.evidence import EvidenceStore
from lacquertutor.models.execution import (
    CHECKPOINT_STATUSES,
    STEP_STATUSES,
    ExecutionCheckpointState,
    ExecutionRecord,
    ExecutionStepState,
)
from lacquertutor.models.attachment import AttachmentMeta
from lacquertutor.storage.session_store import SessionStore
from lacquertutor.web.auth import create_session_token, hash_password, read_session_token, verify_password
from lacquertutor.web.chat import AssistantChatService
from lacquertutor.web.presenter import (
    derive_project_summary,
    derive_project_title,
    display_missing_slot_items,
    display_slot_items,
    humanize_slot_value,
    infer_scene_key,
    scene_label,
    serialize_contract_display,
    slot_label,
)
from lacquertutor.web.teaching import TeachingAssistantService

SceneKey = Literal["chat", "planning", "troubleshooting", "knowledge", "learning", "safety"]


class RegisterRequest(BaseModel):
    username: str = Field(min_length=3, max_length=48)
    password: str = Field(min_length=8, max_length=128)
    display_name: str = Field(default="", max_length=64)


class LoginRequest(BaseModel):
    username: str = Field(min_length=3, max_length=48)
    password: str = Field(min_length=8, max_length=128)


class CreateSessionRequest(BaseModel):
    query: str = Field(min_length=1, max_length=4000)
    mode: Literal["workflow", "agent"] = DEFAULT_SESSION_MODE
    scene_key: SceneKey | None = None


class AnswerRequest(BaseModel):
    answer: str = Field(min_length=1, max_length=4000)


class MessageRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4000)


class UpdateExecutionStepRequest(BaseModel):
    status: Literal["pending", "in_progress", "done", "blocked"]
    note: str = Field(default="", max_length=1000)


class UpdateCheckpointRequest(BaseModel):
    status: Literal["pending", "confirmed", "failed"]
    note: str = Field(default="", max_length=1000)


def _public_user_payload(user: dict[str, Any]) -> dict[str, str]:
    return {
        "user_id": user["user_id"],
        "username": user["username"],
        "display_name": user.get("display_name") or user["username"],
    }


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _kb_image_dir() -> Path:
    path = _repo_root() / "kb" / "image_mirror"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _upload_root(settings: Settings) -> Path:
    root = Path(settings.upload_dir)
    if not root.is_absolute():
        root = _repo_root() / root
    root.mkdir(parents=True, exist_ok=True)
    return root.resolve()


def _session_upload_dir(settings: Settings, *, user_id: str, session_id: str) -> Path:
    path = _upload_root(settings) / user_id / session_id
    path.mkdir(parents=True, exist_ok=True)
    return path


def _find_attachment(state: ConversationState, attachment_id: str) -> AttachmentMeta | None:
    for item in state.attachments:
        if item.attachment_id == attachment_id:
            return item
    return None


def _allowed_upload_mime_types() -> set[str]:
    return {"image/jpeg", "image/png", "image/webp"}


def _ensure_execution_state(state: ConversationState) -> None:
    contract = state.final_contract
    if contract is None:
        return

    step_map = {item.step_number: item for item in state.execution_steps}
    state.execution_steps = [
        step_map.get(
            step.step_number,
            ExecutionStepState(step_number=step.step_number),
        )
        for step in contract.steps
    ]

    checkpoint_map = {item.checkpoint_id: item for item in state.execution_checkpoints}
    state.execution_checkpoints = [
        checkpoint_map.get(
            checkpoint.checkpoint_id,
            ExecutionCheckpointState(checkpoint_id=checkpoint.checkpoint_id),
        )
        for checkpoint in contract.checkpoints
    ]


def _append_execution_record(
    state: ConversationState,
    *,
    record_type: str,
    target_id: str,
    status_value: str,
    note: str,
) -> None:
    state.execution_records.append(
        ExecutionRecord(
            record_type=record_type,
            target_id=target_id,
            status=status_value,
            note=note.strip(),
            updated_at=_utc_now_iso(),
        )
    )


def _state_scene_key(state: ConversationState) -> str:
    if state.scene_key:
        return state.scene_key
    if (
        not state.final_contract
        and not state.module_artifact
        and not state.pending_slot_name
        and not state.task_type
        and (
            state.stage == "conversation"
            or state.chat_references
            or state.chat_suggested_scene_keys
            or any(turn.role == "assistant" for turn in state.dialogue_history)
        )
    ):
        return "chat"
    return infer_scene_key(state.original_query)


def _derive_session_status_from_state(state: ConversationState) -> str:
    if _state_scene_key(state) == "chat":
        return "active"
    if state.module_artifact:
        return "completed"
    if state.final_contract is None:
        return "active" if state.pending_slot_name else "active"

    _ensure_execution_state(state)
    if any(item.status == "blocked" for item in state.execution_steps):
        return "blocked"
    if any(item.status == "failed" for item in state.execution_checkpoints):
        return "blocked"
    steps_complete = state.execution_steps and all(
        item.status == "done" for item in state.execution_steps
    )
    checkpoints_complete = (
        not state.execution_checkpoints
        or all(item.status == "confirmed" for item in state.execution_checkpoints)
    )
    if steps_complete and checkpoints_complete:
        return "completed"
    if any(item.status != "pending" for item in state.execution_steps) or any(
        item.status != "pending" for item in state.execution_checkpoints
    ):
        return "execution_in_progress"
    return "planned"


def _serialize_execution(state: ConversationState) -> dict[str, Any]:
    _ensure_execution_state(state)
    step_lookup = {item.step_number: item for item in state.execution_steps}
    checkpoint_lookup = {item.checkpoint_id: item for item in state.execution_checkpoints}
    done_steps = sum(1 for item in state.execution_steps if item.status == "done")
    confirmed_checkpoints = sum(
        1 for item in state.execution_checkpoints if item.status == "confirmed"
    )
    return {
        "steps": [
            {
                "step_number": item.step_number,
                "status": item.status,
                "note": item.note,
                "updated_at": item.updated_at,
            }
            for item in state.execution_steps
        ],
        "checkpoints": [
            {
                "checkpoint_id": item.checkpoint_id,
                "status": item.status,
                "note": item.note,
                "updated_at": item.updated_at,
            }
            for item in state.execution_checkpoints
        ],
        "records": [item.model_dump() for item in state.execution_records[-12:]],
        "summary": {
            "step_total": len(state.execution_steps),
            "step_done": done_steps,
            "checkpoint_total": len(state.execution_checkpoints),
            "checkpoint_confirmed": confirmed_checkpoints,
            "has_blocker": any(item.status == "blocked" for item in state.execution_steps)
            or any(item.status == "failed" for item in state.execution_checkpoints),
        },
        "step_lookup": {
            str(step_number): step_state.model_dump()
            for step_number, step_state in step_lookup.items()
        },
        "checkpoint_lookup": {
            checkpoint_id: checkpoint_state.model_dump()
            for checkpoint_id, checkpoint_state in checkpoint_lookup.items()
        },
    }


def _serialize_session_overview(
    session_id: str,
    status_value: str,
    state: ConversationState,
    *,
    created_at: str = "",
    updated_at: str = "",
) -> dict[str, Any]:
    scene_key = _state_scene_key(state)
    return {
        "session_id": session_id,
        "status": status_value,
        "created_at": created_at,
        "updated_at": updated_at,
        "scene_key": scene_key,
        "scene_label": scene_label(scene_key),
        "project_title": derive_project_title(state.original_query, scene_key=scene_key),
        "project_summary": derive_project_summary(
            state.original_query,
            scene_key=scene_key,
            fallback="等待继续",
        ),
        "session_mode": state.session_mode,
        "task_type": state.task_type,
        "stage": state.stage,
        "questions_asked": state.questions_asked,
        "filled_slots_count": len(state.slot_state.filled_dict),
        "pending_slot_label": slot_label(state.pending_slot_name) if state.pending_slot_name else "",
        "has_contract": state.final_contract is not None,
        "has_artifact": bool(state.module_artifact),
    }


def _serialize_state(state: ConversationState) -> dict[str, Any]:
    contract = state.final_contract
    scene_key = _state_scene_key(state)
    execution = _serialize_execution(state)
    return {
        "scene_key": scene_key,
        "scene_label": scene_label(scene_key),
        "project_title": derive_project_title(state.original_query, scene_key=scene_key),
        "project_summary": derive_project_summary(state.original_query, scene_key=scene_key),
        "session_mode": state.session_mode,
        "task_type": state.task_type,
        "stage": state.stage,
        "failure_mode": state.failure_mode,
        "questions_asked": state.questions_asked,
        "pending_slot_name": state.pending_slot_name,
        "pending_slot_label": slot_label(state.pending_slot_name) if state.pending_slot_name else "",
        "pending_question": state.pending_question,
        "pending_question_reason": state.pending_question_reason,
        "filled_slots": state.slot_state.filled_dict,
        "filled_slots_display": display_slot_items(state.slot_state.filled_dict),
        "missing_hard_gates": state.slot_state.unfilled_hard_gates,
        "missing_hard_gates_display": display_missing_slot_items(
            state.slot_state.unfilled_hard_gates
        ),
        "retrieved_evidence": [
            {
                "evidence_id": card.evidence_id,
                "stage": card.stage,
                "failure_mode": card.failure_mode,
                "summary_en": card.summary_en,
            }
            for card in state.retrieved_evidence
        ],
        "remembered_preferences": [
            {
                **item.model_dump(),
                "label": slot_label(item.slot_name),
                "display_value": humanize_slot_value(item.slot_name, item.value),
            }
            for item in state.remembered_preferences
        ],
        "recalled_sessions": [item.model_dump() for item in state.recalled_sessions],
        "learned_playbooks": [item.model_dump() for item in state.learned_playbooks],
        "agent_memories": state.agent_memories,
        "chat_references": state.chat_references,
        "chat_suggested_scene_keys": state.chat_suggested_scene_keys,
        "module_artifact": state.module_artifact,
        "execution": execution,
        "attachments": [item.model_dump() for item in state.attachments],
        "contract": contract.model_dump() if contract else None,
        "contract_display": serialize_contract_display(contract),
        "parent_session_id": state.parent_session_id,
        "parent_message_id": state.parent_message_id,
    }


def _serialize_result(session_id: str, result: dict[str, Any], state: ConversationState) -> dict[str, Any]:
    payload = {
        "session_id": session_id,
        "state": _serialize_state(state),
    }
    result_type = result["type"]
    if result_type == "question":
        payload["response"] = {
            "type": "question",
            "slot_name": result["slot_name"],
            "slot_label": slot_label(result["slot_name"]),
            "text": result["text"],
            "reason": result.get("reason", ""),
            "priority": result.get("priority", 0),
        }
        return payload

    if result_type == "artifact":
        payload["response"] = {
            "type": "artifact",
            "artifact": state.module_artifact,
            "markdown": state.module_artifact.get("markdown", ""),
        }
        return payload

    if result_type == "message":
        payload["response"] = {
            "type": "message",
            "text": result.get("text", ""),
            "suggested_scene_keys": result.get("suggested_scene_keys", []),
            "references": result.get("references", []),
        }
        return payload

    payload["response"] = {
        "type": "contract",
        "contract": state.final_contract.model_dump() if state.final_contract else None,
        "contract_display": serialize_contract_display(state.final_contract),
        "markdown": state.final_contract.to_markdown() if state.final_contract else "",
    }
    return payload


def _message_payload(result: dict[str, Any], state: ConversationState) -> str:
    result_type = result["type"]
    if result_type == "contract":
        contract = result.get("contract")
        return json.dumps(
            {
                "type": "contract",
                "contract": contract.model_dump() if contract else None,
            },
            ensure_ascii=False,
        )
    if result_type == "artifact":
        return json.dumps(
            {
                "type": "artifact",
                "artifact": state.module_artifact,
            },
            ensure_ascii=False,
        )
    if result_type == "message":
        return json.dumps(
            {
                "type": "message",
                "text": result.get("text", ""),
                "suggested_scene_keys": result.get("suggested_scene_keys", []),
                "references": result.get("references", []),
            },
            ensure_ascii=False,
        )
    return json.dumps(result, ensure_ascii=False)


def _sync_state_from_result(state: ConversationState, result: dict[str, Any]) -> None:
    if result["type"] == "question":
        state.pending_slot_name = result["slot_name"]
        state.pending_question = result["text"]
        state.pending_question_reason = result.get("reason", "")
        return

    state.pending_slot_name = None
    state.pending_question = ""
    state.pending_question_reason = ""
    if result["type"] == "contract":
        _ensure_execution_state(state)


def _summarize_result_for_memory(result: dict[str, Any], state: ConversationState) -> str:
    result_type = result["type"]
    if result_type == "question":
        return result.get("text", "")
    if result_type == "message":
        return result.get("text", "")
    if result_type == "artifact":
        artifact = state.module_artifact
        highlights = "；".join(artifact.get("highlights", [])[:2])
        return f"{artifact.get('title', '教学结果')}：{artifact.get('summary', '')} {highlights}".strip()
    if state.final_contract is None:
        return "系统已整理出当前工艺方案。"
    step_titles = [step.action for step in state.final_contract.steps[:3]]
    return (
        f"系统已生成工艺方案，包含 {len(state.final_contract.steps)} 个步骤、"
        f"{len(state.final_contract.checkpoints)} 个检查点。"
        f"前几个动作是：{'；'.join(step_titles) or '暂无'}。"
    )


def _load_index_html() -> str:
    return _index_html_path().read_text(encoding="utf-8")


def _assets_dir() -> Path:
    return _frontend_dist_dir() / "assets"


def _frontend_dist_dir() -> Path:
    return Path(__file__).with_name("dist")


def _index_html_path() -> Path:
    return _frontend_dist_dir() / "index.html"


def _export_chat_markdown(
    *,
    session_id: str,
    title: str,
    messages: list[dict[str, Any]],
) -> str:
    def quote_block(text: str) -> str:
        parts = str(text or "").splitlines() or [""]
        return "\n".join(f"> {line}" if line else ">" for line in parts)

    lines = [f"# {title}", "", f"会话 ID: `{session_id}`", "", "## 对话记录", ""]
    for message in messages:
        if message["role"] == "user":
            lines.append(f"### 用户\n{quote_block(message['content'])}\n")
            continue
        try:
            payload = json.loads(message["content"])
        except Exception:
            payload = {"type": "message", "text": message["content"]}

        if payload.get("type") == "message":
            lines.append(f"### 助手\n{quote_block(payload.get('text', '').strip())}\n")
        elif payload.get("type") == "question":
            lines.append(f"### 系统追问\n{quote_block(payload.get('text', '').strip())}\n")
        elif payload.get("type") == "artifact":
            lines.append("### 系统结果\n> 系统已生成教学结果，请在线查看详细内容。\n")
        elif payload.get("type") == "contract":
            lines.append("### 系统结果\n> 系统已生成可执行方案，请在线查看详细步骤与检查点。\n")
        else:
            lines.append(f"### 助手\n{quote_block(message['content'])}\n")
    return "\n".join(lines).strip()


async def _set_session_status(
    session_store: SessionStore,
    session_id: str,
    state: ConversationState,
) -> None:
    status_value = _derive_session_status_from_state(state)
    await session_store.update_status(session_id, status_value)


def create_app(
    *,
    settings: Settings | None = None,
    evidence_store: EvidenceStore | None = None,
    agent: LacquerTutorAgent | None = None,
    session_store: SessionStore | None = None,
    teaching_service: TeachingAssistantService | None = None,
    chat_service: AssistantChatService | None = None,
) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app_settings = settings or Settings()
        app_evidence_store = evidence_store
        app_agent = agent
        if app_agent is None:
            if app_evidence_store is None:
                evidence_path = app_settings.evidence_cards_path
                app_evidence_store = (
                    EvidenceStore.from_json(evidence_path)
                    if evidence_path.exists()
                    else EvidenceStore([])
                )
            app_agent = LacquerTutorAgent(app_settings, app_evidence_store)
        app_session_store = session_store or SessionStore(app_settings.session_db_path)
        await app_session_store.initialize()
        if hasattr(app_agent, "bind_session_store"):
            app_agent.bind_session_store(app_session_store)
        app_teaching_service = teaching_service or TeachingAssistantService.from_repo(app_settings)
        if hasattr(app_teaching_service, "prepare_rag"):
            await app_teaching_service.prepare_rag()
        app_chat_service = chat_service or AssistantChatService.from_services(
            settings=app_settings,
            teaching_service=app_teaching_service,
            memory_engine=getattr(app_agent, "memory_engine", None),
            mem0_service=getattr(app_agent, "mem0_service", None),
        )
        app.state.settings = app_settings
        app.state.agent = app_agent
        app.state.session_store = app_session_store
        app.state.teaching_service = app_teaching_service
        app.state.chat_service = app_chat_service
        try:
            yield
        finally:
            await app_agent.close()
            await app_session_store.close()

    app = FastAPI(title="LacquerTutor", version="0.2.0", lifespan=lifespan)

    @app.middleware("http")
    async def prevent_frontend_cache(request: Request, call_next):
        response = await call_next(request)
        path = request.url.path
        if path == "/" or path.startswith("/assets/") or (
            not path.startswith(("/api/", "/kb-images/"))
            and "text/html" in response.headers.get("content-type", "")
        ):
            response.headers["Cache-Control"] = "no-store"
        return response

    app.mount("/assets", StaticFiles(directory=_assets_dir()), name="assets")
    app.mount("/kb-images", StaticFiles(directory=_kb_image_dir()), name="kb-images")

    async def current_user(request: Request) -> dict[str, Any] | None:
        app_settings: Settings = app.state.settings
        session_store: SessionStore = app.state.session_store
        raw_token = request.cookies.get(app_settings.auth_cookie_name, "")
        if not raw_token:
            return None
        user_id = read_session_token(
            raw_token,
            app_settings.auth_secret_key,
            max_age_sec=app_settings.auth_session_max_age_sec,
        )
        if not user_id:
            return None
        return await session_store.get_user_by_id(user_id)

    async def require_user(request: Request) -> dict[str, Any]:
        user = await current_user(request)
        if user is None:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="authentication required")
        return user

    async def ensure_session_owner(session_id: str, user: dict[str, Any]) -> dict[str, Any]:
        session_store: SessionStore = app.state.session_store
        session = await session_store.get_session(session_id)
        if session is None:
            raise HTTPException(status_code=404, detail="session not found")
        if session.get("user_id") != user["user_id"]:
            raise HTTPException(status_code=404, detail="session not found")
        return session

    async def remember_exchange(
        *,
        user_id: str,
        session_id: str,
        user_text: str,
        assistant_text: str,
        state: ConversationState,
    ) -> None:
        mem0_service = getattr(app.state.agent, "mem0_service", None)
        if mem0_service is None or not user_id:
            return
        await mem0_service.remember_turns(
            user_id=user_id,
            run_id=session_id,
            messages=[
                {"role": "user", "content": user_text},
                {"role": "assistant", "content": assistant_text},
            ],
            metadata={
                "scene_key": _state_scene_key(state),
                "task_type": state.task_type,
                "stage": state.stage,
            },
        )

    async def start_agent_session(
        agent_instance: Any,
        query: str,
        user_id: str,
    ) -> ConversationState:
        try:
            return await agent_instance.start_session(query, user_id=user_id)
        except TypeError:
            state = await agent_instance.start_session(query)
            state.user_id = user_id
            return state

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/", response_class=HTMLResponse)
    async def index() -> str:
        return _load_index_html()

    @app.post("/api/auth/register")
    async def register(
        req: RegisterRequest,
        response: Response,
    ) -> dict[str, Any]:
        session_store: SessionStore = app.state.session_store
        settings_obj: Settings = app.state.settings

        existing = await session_store.get_user_by_username(req.username)
        if existing is not None:
            raise HTTPException(status_code=409, detail="username already exists")

        user = await session_store.create_user(
            username=req.username.strip(),
            password_hash=hash_password(req.password),
            display_name=req.display_name.strip(),
        )
        token = create_session_token(user["user_id"], settings_obj.auth_secret_key)
        response.set_cookie(
            settings_obj.auth_cookie_name,
            token,
            httponly=True,
            samesite="lax",
            secure=False,
            max_age=settings_obj.auth_session_max_age_sec,
        )
        return {"authenticated": True, "user": _public_user_payload(user)}

    @app.post("/api/auth/login")
    async def login(
        req: LoginRequest,
        response: Response,
    ) -> dict[str, Any]:
        session_store: SessionStore = app.state.session_store
        settings_obj: Settings = app.state.settings
        user = await session_store.get_user_by_username(req.username)
        if user is None or not verify_password(req.password, user["password_hash"]):
            raise HTTPException(status_code=401, detail="invalid credentials")
        token = create_session_token(user["user_id"], settings_obj.auth_secret_key)
        response.set_cookie(
            settings_obj.auth_cookie_name,
            token,
            httponly=True,
            samesite="lax",
            secure=False,
            max_age=settings_obj.auth_session_max_age_sec,
        )
        return {"authenticated": True, "user": _public_user_payload(user)}

    @app.post("/api/auth/logout")
    async def logout(response: Response) -> dict[str, bool]:
        settings_obj: Settings = app.state.settings
        response.delete_cookie(settings_obj.auth_cookie_name)
        return {"ok": True}

    @app.get("/api/me")
    async def me(request: Request) -> dict[str, Any]:
        user = await current_user(request)
        if user is None:
            return {"authenticated": False}
        return {"authenticated": True, "user": _public_user_payload(user)}

    @app.get("/api/home")
    async def home(request: Request) -> dict[str, Any]:
        user = await require_user(request)
        session_store: SessionStore = app.state.session_store
        agent_instance: LacquerTutorAgent = app.state.agent

        recent_rows = await session_store.list_user_sessions(user["user_id"], limit=6)
        recent_sessions: list[dict[str, Any]] = []
        for row in recent_rows:
            context_json = row.get("context_json") or ""
            if not context_json.strip():
                continue
            state = ConversationState.from_json(context_json)
            recent_sessions.append(
                _serialize_session_overview(
                    row["session_id"],
                    row["status"],
                    state,
                    created_at=row.get("created_at", ""),
                    updated_at=row.get("updated_at", ""),
                )
            )

        memory_engine = getattr(agent_instance, "memory_engine", None)
        snapshot = (
            await memory_engine.build_snapshot(user_id=user["user_id"])
            if memory_engine is not None
            else {
                "remembered_preferences": [],
                "learned_playbooks": [],
                "completed_sessions": 0,
                "recent_topics": [],
                "agent_memories": [],
            }
        )
        snapshot["remembered_preferences"] = [
            {
                **item,
                "label": slot_label(item.get("slot_name", "")),
                "display_value": humanize_slot_value(item.get("slot_name", ""), item.get("value")),
            }
            for item in snapshot.get("remembered_preferences", [])
        ]

        return {
            "user": _public_user_payload(user),
            "recent_sessions": recent_sessions,
            "memory": snapshot,
            "stats": {
                "total_sessions": await session_store.count_sessions_for_user(user["user_id"]),
                "completed_sessions": snapshot.get("completed_sessions", 0),
            },
        }

    @app.post("/api/sessions")
    async def create_session(req: CreateSessionRequest, request: Request) -> dict[str, Any]:
        user = await require_user(request)
        agent_instance: LacquerTutorAgent = app.state.agent
        session_store: SessionStore = app.state.session_store
        teacher: TeachingAssistantService = app.state.teaching_service
        chat_assistant: AssistantChatService = app.state.chat_service

        scene_key = req.scene_key or infer_scene_key(req.query)
        session_id = await session_store.create_session(user_id=user["user_id"])

        if scene_key == "chat":
            state = ConversationState(
                original_query=req.query,
                scene_key=scene_key,
                session_mode="agent",
                user_id=user["user_id"],
                stage="conversation",
            )
            state.add_user_turn(req.query)
            result = await chat_assistant.reply(state, req.query)
        elif scene_key in {"knowledge", "learning", "safety"}:
            state = ConversationState(
                original_query=req.query,
                scene_key=scene_key,
                session_mode=normalize_session_mode(req.mode),
                user_id=user["user_id"],
                task_type=scene_key,
                stage="general",
            )
            state.add_user_turn(req.query)
            if getattr(agent_instance, "memory_engine", None) is not None:
                await agent_instance.memory_engine.hydrate_state(state)
            artifact = await teacher.create_artifact(scene_key, req.query)
            state.module_artifact = artifact.model_dump()
            result = {"type": "artifact", "artifact": artifact}
        else:
            state = await start_agent_session(agent_instance, req.query, user["user_id"])
            state.scene_key = scene_key
            state.session_mode = normalize_session_mode(req.mode)
            result = await agent_instance.advance(
                state,
                **get_session_mode_options(state.session_mode),
            )
            _sync_state_from_result(state, result)

        await session_store.add_message(session_id, "user", req.query)
        await session_store.update_context(session_id, state.to_json())
        await _set_session_status(session_store, session_id, state)
        await session_store.add_message(
            session_id,
            "assistant",
            _message_payload(result, state),
        )
        if result["type"] in {"artifact", "contract", "message"}:
            await remember_exchange(
                user_id=user["user_id"],
                session_id=session_id,
                user_text=req.query,
                assistant_text=_summarize_result_for_memory(result, state),
                state=state,
            )
        return _serialize_result(session_id, result, state)

    @app.get("/api/sessions")
    async def list_sessions(
        request: Request,
        limit: int = Query(default=6, ge=1, le=20),
    ) -> dict[str, Any]:
        user = await require_user(request)
        session_store: SessionStore = app.state.session_store
        rows = await session_store.list_sessions(user_id=user["user_id"], limit=limit)
        sessions: list[dict[str, Any]] = []

        for row in rows:
            context_json = row.get("context_json") or ""
            if not context_json.strip():
                continue
            state = ConversationState.from_json(context_json)
            sessions.append(
                _serialize_session_overview(
                    row["session_id"],
                    row["status"],
                    state,
                    created_at=row.get("created_at", ""),
                    updated_at=row.get("updated_at", ""),
                )
            )

        return {"sessions": sessions}

    @app.post("/api/sessions/{session_id}/messages")
    async def send_session_message(
        session_id: str,
        req: MessageRequest,
        request: Request,
    ) -> dict[str, Any]:
        user = await require_user(request)
        session_store: SessionStore = app.state.session_store
        session = await ensure_session_owner(session_id, user)
        state = ConversationState.from_json(session["context_json"])
        if _state_scene_key(state) != "chat":
            raise HTTPException(status_code=409, detail="session does not support generic chat messages")

        chat_assistant: AssistantChatService = app.state.chat_service
        state.add_user_turn(req.message)
        await session_store.add_message(session_id, "user", req.message)
        result = await chat_assistant.reply(state, req.message)
        await session_store.update_context(session_id, state.to_json())
        await _set_session_status(session_store, session_id, state)
        await session_store.add_message(
            session_id,
            "assistant",
            _message_payload(result, state),
        )
        await remember_exchange(
            user_id=user["user_id"],
            session_id=session_id,
            user_text=req.message,
            assistant_text=_summarize_result_for_memory(result, state),
            state=state,
        )
        return _serialize_result(session_id, result, state)

    @app.post("/api/sessions/{session_id}/answer")
    async def answer_session(session_id: str, req: AnswerRequest, request: Request) -> dict[str, Any]:
        user = await require_user(request)
        agent_instance: LacquerTutorAgent = app.state.agent
        session_store: SessionStore = app.state.session_store

        session = await ensure_session_owner(session_id, user)
        state = ConversationState.from_json(session["context_json"])
        if not state.pending_slot_name:
            raise HTTPException(status_code=409, detail="session is not waiting for an answer")

        await agent_instance.submit_answer(state, req.answer)
        await session_store.add_message(session_id, "user", req.answer)
        result = await agent_instance.advance(
            state,
            **get_session_mode_options(state.session_mode),
        )
        _sync_state_from_result(state, result)
        await session_store.update_context(session_id, state.to_json())
        await _set_session_status(session_store, session_id, state)
        await session_store.add_message(
            session_id,
            "assistant",
            _message_payload(result, state),
        )
        if result["type"] in {"artifact", "contract", "message"}:
            await remember_exchange(
                user_id=user["user_id"],
                session_id=session_id,
                user_text=req.answer,
                assistant_text=_summarize_result_for_memory(result, state),
                state=state,
            )
        return _serialize_result(session_id, result, state)

    @app.post("/api/sessions/{session_id}/execution/steps/{step_number}")
    async def update_execution_step(
        session_id: str,
        step_number: int,
        req: UpdateExecutionStepRequest,
        request: Request,
    ) -> dict[str, Any]:
        user = await require_user(request)
        session_store: SessionStore = app.state.session_store
        session = await ensure_session_owner(session_id, user)
        state = ConversationState.from_json(session["context_json"])
        if state.final_contract is None:
            raise HTTPException(status_code=409, detail="session has no contract yet")

        _ensure_execution_state(state)
        step_state = next((item for item in state.execution_steps if item.step_number == step_number), None)
        if step_state is None:
            raise HTTPException(status_code=404, detail="step not found")

        step_state.status = req.status
        step_state.note = req.note.strip()
        step_state.updated_at = _utc_now_iso()
        _append_execution_record(
            state,
            record_type="step",
            target_id=str(step_number),
            status_value=req.status,
            note=req.note,
        )
        await session_store.update_context(session_id, state.to_json())
        await session_store.update_status(session_id, _derive_session_status_from_state(state))
        return {
            "session_id": session_id,
            "execution": _serialize_execution(state),
            "state": _serialize_state(state),
        }

    @app.post("/api/sessions/{session_id}/execution/checkpoints/{checkpoint_id}")
    async def update_execution_checkpoint(
        session_id: str,
        checkpoint_id: str,
        req: UpdateCheckpointRequest,
        request: Request,
    ) -> dict[str, Any]:
        user = await require_user(request)
        session_store: SessionStore = app.state.session_store
        session = await ensure_session_owner(session_id, user)
        state = ConversationState.from_json(session["context_json"])
        if state.final_contract is None:
            raise HTTPException(status_code=409, detail="session has no contract yet")

        _ensure_execution_state(state)
        checkpoint_state = next(
            (item for item in state.execution_checkpoints if item.checkpoint_id == checkpoint_id),
            None,
        )
        if checkpoint_state is None:
            raise HTTPException(status_code=404, detail="checkpoint not found")

        checkpoint_state.status = req.status
        checkpoint_state.note = req.note.strip()
        checkpoint_state.updated_at = _utc_now_iso()
        _append_execution_record(
            state,
            record_type="checkpoint",
            target_id=checkpoint_id,
            status_value=req.status,
            note=req.note,
        )
        await session_store.update_context(session_id, state.to_json())
        await session_store.update_status(session_id, _derive_session_status_from_state(state))
        return {
            "session_id": session_id,
            "execution": _serialize_execution(state),
            "state": _serialize_state(state),
        }

    @app.post("/api/sessions/{session_id}/attachments")
    async def upload_attachment(
        session_id: str,
        request: Request,
        file: UploadFile = File(...),
        linked_step_number: int | None = Form(default=None),
        linked_checkpoint_id: str = Form(default=""),
        note: str = Form(default=""),
    ) -> dict[str, Any]:
        user = await require_user(request)
        settings_obj: Settings = app.state.settings
        session_store: SessionStore = app.state.session_store
        session = await ensure_session_owner(session_id, user)
        state = ConversationState.from_json(session["context_json"])

        if linked_step_number is not None and linked_checkpoint_id.strip():
            raise HTTPException(status_code=400, detail="attachment can link to either step or checkpoint, not both")

        if len(state.attachments) >= settings_obj.max_uploads_per_session:
            raise HTTPException(status_code=409, detail="session attachment limit reached")

        if linked_step_number is not None or linked_checkpoint_id.strip():
            if state.final_contract is None:
                raise HTTPException(status_code=409, detail="session has no contract yet")
            _ensure_execution_state(state)
            if linked_step_number is not None and not any(
                item.step_number == linked_step_number for item in state.execution_steps
            ):
                raise HTTPException(status_code=404, detail="step not found")
            if linked_checkpoint_id.strip() and not any(
                item.checkpoint_id == linked_checkpoint_id.strip()
                for item in state.execution_checkpoints
            ):
                raise HTTPException(status_code=404, detail="checkpoint not found")

        filename = Path(file.filename or "upload").name
        mime_type = file.content_type or mimetypes.guess_type(filename)[0] or ""
        if mime_type not in _allowed_upload_mime_types():
            raise HTTPException(status_code=415, detail="only jpg, png, and webp images are supported")

        payload = await file.read()
        if not payload:
            raise HTTPException(status_code=400, detail="empty upload is not allowed")

        max_bytes = settings_obj.max_upload_size_mb * 1024 * 1024
        if len(payload) > max_bytes:
            raise HTTPException(
                status_code=413,
                detail=f"file exceeds {settings_obj.max_upload_size_mb} MB limit",
            )

        ext = Path(filename).suffix.lower() or {
            "image/jpeg": ".jpg",
            "image/png": ".png",
            "image/webp": ".webp",
        }.get(mime_type, "")
        stored_name = f"{uuid4().hex}{ext}"
        session_dir = _session_upload_dir(settings_obj, user_id=user["user_id"], session_id=session_id)
        destination = session_dir / stored_name
        destination.write_bytes(payload)

        attachment = AttachmentMeta(
            attachment_id=uuid4().hex,
            filename=filename,
            stored_name=stored_name,
            relative_path=str(destination.relative_to(_upload_root(settings_obj))),
            mime_type=mime_type,
            size_bytes=len(payload),
            created_at=_utc_now_iso(),
            linked_step_number=linked_step_number,
            linked_checkpoint_id=linked_checkpoint_id.strip(),
            note=note.strip(),
        )
        state.attachments.append(attachment)
        _append_execution_record(
            state,
            record_type="attachment",
            target_id=attachment.attachment_id,
            status_value="uploaded",
            note=attachment.note or attachment.filename,
        )
        await session_store.update_context(session_id, state.to_json())
        await session_store.update_status(session_id, _derive_session_status_from_state(state))
        return {
            "session_id": session_id,
            "attachment": attachment.model_dump(),
            "state": _serialize_state(state),
        }

    @app.get("/api/sessions/{session_id}/attachments")
    async def list_attachments(session_id: str, request: Request) -> dict[str, Any]:
        user = await require_user(request)
        session = await ensure_session_owner(session_id, user)
        state = ConversationState.from_json(session["context_json"])
        return {
            "session_id": session_id,
            "attachments": [item.model_dump() for item in state.attachments],
        }

    @app.get("/api/sessions/{session_id}/attachments/{attachment_id}")
    async def download_attachment(
        session_id: str,
        attachment_id: str,
        request: Request,
    ) -> FileResponse:
        user = await require_user(request)
        settings_obj: Settings = app.state.settings
        session = await ensure_session_owner(session_id, user)
        state = ConversationState.from_json(session["context_json"])
        attachment = _find_attachment(state, attachment_id)
        if attachment is None:
            raise HTTPException(status_code=404, detail="attachment not found")

        file_path = (_upload_root(settings_obj) / attachment.relative_path).resolve()
        root = _upload_root(settings_obj)
        if root not in file_path.parents or not file_path.exists():
            raise HTTPException(status_code=404, detail="attachment file missing")

        return FileResponse(
            path=file_path,
            media_type=attachment.mime_type,
            filename=attachment.filename,
        )

    @app.get("/api/sessions/{session_id}")
    async def get_session(session_id: str, request: Request) -> dict[str, Any]:
        user = await require_user(request)
        session_store: SessionStore = app.state.session_store
        session = await ensure_session_owner(session_id, user)
        state = ConversationState.from_json(session["context_json"])
        return {
            "session_id": session_id,
            "status": session["status"],
            "overview": _serialize_session_overview(
                session_id,
                session["status"],
                state,
                created_at=session.get("created_at", ""),
                updated_at=session.get("updated_at", ""),
            ),
            "state": _serialize_state(state),
            "messages": await session_store.get_messages(session_id),
        }

    @app.get("/api/sessions/{session_id}/export/markdown", response_class=PlainTextResponse)
    async def export_session_markdown(session_id: str, request: Request) -> PlainTextResponse:
        user = await require_user(request)
        session_store: SessionStore = app.state.session_store
        session = await ensure_session_owner(session_id, user)
        state = ConversationState.from_json(session["context_json"])

        scene_key = _state_scene_key(state)
        title = derive_project_title(state.original_query, scene_key=scene_key)
        if state.final_contract is not None:
            markdown = f"# {title}\n\n{state.final_contract.to_markdown()}"
            filename = f"lacquertutor-contract-{session_id[:8]}.md"
        elif state.module_artifact:
            markdown = state.module_artifact.get("markdown", "")
            if not markdown:
                raise HTTPException(status_code=409, detail="session has no exportable content")
            filename = f"lacquertutor-module-{session_id[:8]}.md"
        elif scene_key == "chat":
            messages = await session_store.get_messages(session_id)
            markdown = _export_chat_markdown(
                session_id=session_id,
                title=title,
                messages=messages,
            )
            filename = f"lacquertutor-chat-{session_id[:8]}.md"
        else:
            raise HTTPException(status_code=409, detail="session has no exportable content")

        headers = {"Content-Disposition": f'attachment; filename="{filename}"'}
        return PlainTextResponse(markdown, headers=headers)

    @app.get("/{full_path:path}", response_class=HTMLResponse)
    async def spa_fallback(full_path: str) -> str:
        if full_path.startswith("api/"):
            raise HTTPException(status_code=404, detail="not found")
        return _load_index_html()

    return app
