from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient

from lacquertutor.agent.state import ConversationState
from lacquertutor.models.contract import Checkpoint, PlanContract, PlanStep
from lacquertutor.models.evidence import EvidenceStore
from lacquertutor.storage.session_store import SessionStore
from lacquertutor.config import Settings
from lacquertutor.web.app import _state_scene_key, create_app
from lacquertutor.web.presenter import humanize_slot_value, serialize_contract_display
from lacquertutor.web.teaching import ModuleArtifact, ModuleReference

PNG_BYTES = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\rIDATx\x9cc\xf8\xff\xff?"
    b"\x00\x05\xfe\x02\xfeA\xdd\x8d\xb1\x00\x00\x00\x00IEND\xaeB`\x82"
)


class FakeAgent:
    def __init__(self) -> None:
        self.advance_calls: list[dict] = []
        self.memory_engine = None
        self.mem0_service = None

    async def start_session(self, query: str, *, user_id: str = "") -> ConversationState:
        state = ConversationState(original_query=query, user_id=user_id)
        state.add_user_turn(query)
        state.task_type = "planning"
        state.stage = "preparation"
        state.slot_state.fill("substrate_material", "wood", source="user", confirmed=True)
        state.slot_state.fill("target_finish", "semi_gloss", source="user", confirmed=True)
        return state

    async def advance(self, state: ConversationState, **kwargs) -> dict:
        self.advance_calls.append(kwargs)

        if not state.slot_state.is_filled("lacquer_system"):
            state.pending_slot_name = "lacquer_system"
            state.pending_question = "你现在使用的漆体系是什么？"
            state.questions_asked += 1
            state.add_system_turn(state.pending_question, slot_name=state.pending_slot_name)
            return {
                "type": "question",
                "slot_name": state.pending_slot_name,
                "text": state.pending_question,
                "priority": 3,
                "reason": "漆体系会直接影响后续可用步骤和安全边界。",
            }

        contract = PlanContract(
            task_type=state.task_type,
            stage=state.stage,
            steps=[
                PlanStep(
                    step_number=1,
                    action="确认漆体系后开始样板测试",
                    checkpoint_id="CP-01",
                    is_irreversible=False,
                )
            ],
            checkpoints=[Checkpoint(checkpoint_id="CP-01", description="确认样板测试条件")],
            stop_reason="all_filled",
        )
        state.final_contract = contract
        state.pending_slot_name = None
        state.pending_question = ""
        return {"type": "contract", "contract": contract}

    async def submit_answer(self, state: ConversationState, answer: str) -> None:
        state.add_user_turn(answer)
        state.slot_state.fill(
            "lacquer_system",
            answer,
            source="user",
            confirmed=True,
            turn=state.questions_asked,
        )
        state.pending_slot_name = None
        state.pending_question = ""

    async def close(self) -> None:
        return None


class FakeTeachingService:
    async def retrieve_references(self, query: str, *, limit: int = 4):
        return [
            ModuleReference(
                segment_id="seg-1",
                source_label="kb",
                title="木胎处理",
                excerpt=f"针对“{query}”的参考片段。",
                score=9.0,
                image_urls=[],
            )
        ][:limit]

    async def create_artifact(self, scene_key: str, query: str) -> ModuleArtifact:
        return ModuleArtifact(
            artifact_type=(
                "knowledge_brief"
                if scene_key == "knowledge"
                else "feasibility_verdict"
                if scene_key == "safety"
                else "learning_path"
            ),
            title="教学结果",
            summary=f"已为场景 {scene_key} 生成教学结果。",
            verdict="conditional" if scene_key == "safety" else "",
            verdict_label="有条件可行" if scene_key == "safety" else "",
            verdict_reason="需要先补齐关键信息。" if scene_key == "safety" else "",
            highlights=["关键点一", "关键点二"],
            recommendations=["建议先做样板", "建议记录环境"],
            safety_notes=["涉及不可逆步骤前先确认条件"],
            follow_up_questions=["下一步想转成执行计划吗？"],
            required_conditions=["漆体系", "环境湿度"] if scene_key == "safety" else [],
            blocking_factors=["旧涂层体系不明"] if scene_key == "safety" else [],
            markdown=f"# 教学结果\n\n场景：{scene_key}\n\n查询：{query}",
        )


class FakeChatService:
    async def reply(self, state: ConversationState, message: str) -> dict:
        state.scene_key = "chat"
        state.stage = "conversation"
        references = [
            {
                "segment_id": "seg-1",
                "source_label": "kb",
                "title": "生漆基础",
                "excerpt": "生漆需要在合适环境下观察固化与表面状态。",
                "score": 9.0,
                "image_urls": ["/kb-images/demo.jpeg"],
            }
        ]
        state.chat_references = references
        state.chat_suggested_scene_keys = []
        latest_user_turn = state.dialogue_history[-1].content if state.dialogue_history else message
        reply = f"通用聊天回复：{latest_user_turn}"
        state.add_assistant_turn(reply)
        return {
            "type": "message",
            "text": reply,
            "suggested_scene_keys": [],
            "references": references,
        }


def register(client: TestClient, username: str = "teacher_li") -> dict:
    resp = client.post(
        "/api/auth/register",
        json={
            "display_name": "李老师",
            "username": username,
            "password": "secret123",
        },
    )
    assert resp.status_code == 200
    return resp.json()


def login(client: TestClient, username: str = "teacher_li") -> dict:
    resp = client.post(
        "/api/auth/login",
        json={"username": username, "password": "secret123"},
    )
    assert resp.status_code == 200
    return resp.json()


def test_root_page_serves_react_shell():
    app = create_app(
        agent=FakeAgent(),
        session_store=SessionStore(":memory:"),
        teaching_service=FakeTeachingService(),
    )

    with TestClient(app) as client:
        resp = client.get("/")
        assert resp.status_code == 200
        assert '<div id="root"></div>' in resp.text
        assert "漆语 · 漆艺教学的随身助手" in resp.text
        assert "/src/main.tsx" not in resp.text


def test_assets_are_served_from_frontend_dist():
    app = create_app(
        agent=FakeAgent(),
        session_store=SessionStore(":memory:"),
        teaching_service=FakeTeachingService(),
    )

    with TestClient(app) as client:
        css_resp = client.get("/assets/app.css")
        js_resp = client.get("/assets/app.js")
        assert css_resp.status_code == 200
        assert "text/css" in css_resp.headers["content-type"]
        assert js_resp.status_code == 200
        assert "javascript" in js_resp.headers["content-type"]


def test_spa_fallback_serves_index_for_session_routes():
    app = create_app(
        agent=FakeAgent(),
        session_store=SessionStore(":memory:"),
        teaching_service=FakeTeachingService(),
    )

    with TestClient(app) as client:
        resp = client.get("/p/demo-session?tab=contract")
        assert resp.status_code == 200
        assert '<div id="root"></div>' in resp.text


def test_register_and_home_dashboard_work():
    app = create_app(
        agent=FakeAgent(),
        session_store=SessionStore(":memory:"),
        teaching_service=FakeTeachingService(),
    )

    with TestClient(app) as client:
        register_data = register(client)
        assert register_data["authenticated"] is True
        assert register_data["user"]["username"] == "teacher_li"

        me_resp = client.get("/api/me")
        assert me_resp.status_code == 200
        assert me_resp.json()["authenticated"] is True

        home_resp = client.get("/api/home")
        assert home_resp.status_code == 200
        home_data = home_resp.json()
        assert home_data["user"]["display_name"] == "李老师"
        assert home_data["stats"]["total_sessions"] == 0


def test_chat_scene_roundtrip_supports_messages_and_export():
    app = create_app(
        agent=FakeAgent(),
        chat_service=FakeChatService(),
        session_store=SessionStore(":memory:"),
        teaching_service=FakeTeachingService(),
    )

    with TestClient(app) as client:
        register(client)
        create_resp = client.post(
            "/api/sessions",
            json={"query": "你好，先和我聊聊生漆入门。", "mode": "agent", "scene_key": "chat"},
        )
        assert create_resp.status_code == 200
        create_data = create_resp.json()
        assert create_data["response"]["type"] == "message"
        assert create_data["state"]["scene_key"] == "chat"
        assert create_data["response"]["text"].startswith("通用聊天回复")
        assert create_data["response"]["references"][0]["image_urls"] == ["/kb-images/demo.jpeg"]

        follow_resp = client.post(
            f"/api/sessions/{create_data['session_id']}/messages",
            json={"message": "我接下来想做一个计划。"},
        )
        assert follow_resp.status_code == 200
        follow_data = follow_resp.json()
        assert follow_data["response"]["type"] == "message"
        assert follow_data["response"]["suggested_scene_keys"] == []
        assert follow_data["response"]["text"].endswith("我接下来想做一个计划。")

        detail_resp = client.get(f"/api/sessions/{create_data['session_id']}")
        assert detail_resp.status_code == 200
        detail_data = detail_resp.json()
        assert detail_data["state"]["scene_key"] == "chat"
        assert detail_data["state"]["chat_references"][0]["image_urls"] == ["/kb-images/demo.jpeg"]
        assert len(detail_data["messages"]) == 4
        assistant_payload = json.loads(detail_data["messages"][1]["content"])
        assert assistant_payload["type"] == "message"
        assert assistant_payload["references"][0]["image_urls"] == ["/kb-images/demo.jpeg"]

        export_resp = client.get(f"/api/sessions/{create_data['session_id']}/export/markdown")
        assert export_resp.status_code == 200
        assert "## 对话记录" in export_resp.text
        assert "通用聊天回复" in export_resp.text


def test_chat_export_quotes_markdown_content():
    app = create_app(
        agent=FakeAgent(),
        chat_service=FakeChatService(),
        session_store=SessionStore(":memory:"),
        teaching_service=FakeTeachingService(),
    )

    with TestClient(app) as client:
        register(client, username="chat_export_user")
        create_resp = client.post(
            "/api/sessions",
            json={"query": "# 标题\n- 列表项", "mode": "agent", "scene_key": "chat"},
        )
        assert create_resp.status_code == 200
        session_id = create_resp.json()["session_id"]

        export_resp = client.get(f"/api/sessions/{session_id}/export/markdown")
        assert export_resp.status_code == 200
        assert "### 用户" in export_resp.text
        assert "> # 标题" in export_resp.text
        assert "> - 列表项" in export_resp.text


def test_messages_endpoint_rejects_non_chat_sessions():
    app = create_app(
        agent=FakeAgent(),
        chat_service=FakeChatService(),
        session_store=SessionStore(":memory:"),
        teaching_service=FakeTeachingService(),
    )

    with TestClient(app) as client:
        register(client)
        create_resp = client.post(
            "/api/sessions",
            json={"query": "我想生成一份可执行工艺计划。\n对象 / 基底: 木托盘\n你想做成什么效果: 半光黑漆面", "mode": "workflow"},
        )
        session_id = create_resp.json()["session_id"]
        message_resp = client.post(
            f"/api/sessions/{session_id}/messages",
            json={"message": "继续聊聊"},
        )
        assert message_resp.status_code == 409


def test_state_scene_key_falls_back_to_chat_for_legacy_chat_states():
    state = ConversationState(original_query="你好")
    state.stage = "conversation"
    state.add_user_turn("你好")
    state.add_assistant_turn("欢迎继续提问。")

    assert _state_scene_key(state) == "chat"


def test_workflow_mode_session_roundtrip_requires_auth_and_exports_contract():
    agent = FakeAgent()
    app = create_app(
        agent=agent,
        session_store=SessionStore(":memory:"),
        teaching_service=FakeTeachingService(),
    )

    with TestClient(app) as client:
        unauth_resp = client.post(
            "/api/sessions",
            json={"query": "我想给木托盘做一道半光漆面", "mode": "workflow"},
        )
        assert unauth_resp.status_code == 401

        register(client)
        create_resp = client.post(
            "/api/sessions",
            json={"query": "我想生成一份可执行工艺计划。\n对象 / 基底: 木托盘\n你想做成什么效果: 半光黑漆面", "mode": "workflow"},
        )
        assert create_resp.status_code == 200
        create_data = create_resp.json()
        assert create_data["response"]["type"] == "question"
        assert create_data["state"]["session_mode"] == "workflow"
        assert create_data["state"]["filled_slots_display"][0]["value"] == "木材"
        assert agent.advance_calls[0]["slot_selection"] == "prompt"

        answer_resp = client.post(
            f"/api/sessions/{create_data['session_id']}/answer",
            json={"answer": "生漆体系"},
        )
        assert answer_resp.status_code == 200
        answer_data = answer_resp.json()
        assert answer_data["response"]["type"] == "contract"
        assert answer_data["response"]["contract"]["steps"][0]["action"] == "确认漆体系后开始样板测试"

        export_resp = client.get(f"/api/sessions/{create_data['session_id']}/export/markdown")
        assert export_resp.status_code == 200
        assert "# 可执行工艺计划" in export_resp.text
        assert "## C. 操作步骤" in export_resp.text


def test_contract_execution_updates_steps_and_checkpoints():
    agent = FakeAgent()
    app = create_app(
        agent=agent,
        session_store=SessionStore(":memory:"),
        teaching_service=FakeTeachingService(),
    )

    with TestClient(app) as client:
        register(client)
        create_resp = client.post(
            "/api/sessions",
            json={"query": "我想生成一份可执行工艺计划。\n对象 / 基底: 木托盘\n你想做成什么效果: 半光黑漆面", "mode": "workflow"},
        )
        session_id = create_resp.json()["session_id"]
        answer_resp = client.post(
            f"/api/sessions/{session_id}/answer",
            json={"answer": "生漆体系"},
        )
        assert answer_resp.status_code == 200
        answer_data = answer_resp.json()
        assert answer_data["response"]["type"] == "contract"
        assert answer_data["state"]["execution"]["summary"]["step_total"] == 1
        assert answer_data["state"]["execution"]["summary"]["checkpoint_total"] == 1

        step_resp = client.post(
            f"/api/sessions/{session_id}/execution/steps/1",
            json={"status": "in_progress", "note": "开始样板测试"},
        )
        assert step_resp.status_code == 200
        step_data = step_resp.json()
        assert step_data["state"]["execution"]["steps"][0]["status"] == "in_progress"
        assert step_data["state"]["execution"]["records"][-1]["target_id"] == "1"

        done_resp = client.post(
            f"/api/sessions/{session_id}/execution/steps/1",
            json={"status": "done", "note": "已完成第一步"},
        )
        assert done_resp.status_code == 200
        done_data = done_resp.json()
        assert done_data["state"]["execution"]["steps"][0]["status"] == "done"
        assert done_data["state"]["execution"]["summary"]["step_done"] == 1

        checkpoint_resp = client.post(
            f"/api/sessions/{session_id}/execution/checkpoints/CP-01",
            json={"status": "confirmed", "note": "条件已确认"},
        )
        assert checkpoint_resp.status_code == 200
        checkpoint_data = checkpoint_resp.json()
        assert checkpoint_data["state"]["execution"]["checkpoints"][0]["status"] == "confirmed"
        assert checkpoint_data["state"]["execution"]["summary"]["checkpoint_confirmed"] == 1

        session_resp = client.get(f"/api/sessions/{session_id}")
        assert session_resp.status_code == 200
        assert session_resp.json()["status"] == "completed"


def test_attachment_upload_list_download_and_cross_user_protection(tmp_path: Path):
    settings = Settings(
        upload_dir=str(tmp_path / "uploads"),
        max_upload_size_mb=1,
        max_uploads_per_session=3,
    )
    app = create_app(
        settings=settings,
        agent=FakeAgent(),
        session_store=SessionStore(":memory:"),
        teaching_service=FakeTeachingService(),
    )

    with TestClient(app) as client:
        register(client, username="attachment_owner")
        create_resp = client.post(
            "/api/sessions",
            json={"query": "我想生成一份可执行工艺计划。\n对象 / 基底: 木托盘\n你想做成什么效果: 半光黑漆面", "mode": "workflow"},
        )
        session_id = create_resp.json()["session_id"]
        answer_resp = client.post(
            f"/api/sessions/{session_id}/answer",
            json={"answer": "生漆体系"},
        )
        assert answer_resp.status_code == 200

        upload_resp = client.post(
            f"/api/sessions/{session_id}/attachments",
            files={"file": ("surface.png", PNG_BYTES, "image/png")},
            data={"linked_step_number": "1", "note": "当前样板表面状态"},
        )
        assert upload_resp.status_code == 200
        upload_data = upload_resp.json()
        attachment_id = upload_data["attachment"]["attachment_id"]
        assert upload_data["attachment"]["linked_step_number"] == 1
        assert upload_data["state"]["attachments"][0]["filename"] == "surface.png"

        list_resp = client.get(f"/api/sessions/{session_id}/attachments")
        assert list_resp.status_code == 200
        assert len(list_resp.json()["attachments"]) == 1

        file_resp = client.get(f"/api/sessions/{session_id}/attachments/{attachment_id}")
        assert file_resp.status_code == 200
        assert file_resp.content.startswith(b"\x89PNG")

        client.post("/api/auth/logout")
        register(client, username="attachment_other")
        other_resp = client.get(f"/api/sessions/{session_id}/attachments/{attachment_id}")
        assert other_resp.status_code == 404


def test_attachment_upload_rejects_invalid_type(tmp_path: Path):
    settings = Settings(upload_dir=str(tmp_path / "uploads"))
    app = create_app(
        settings=settings,
        agent=FakeAgent(),
        session_store=SessionStore(":memory:"),
        teaching_service=FakeTeachingService(),
    )

    with TestClient(app) as client:
        register(client)
        create_resp = client.post(
            "/api/sessions",
            json={"query": "我想快速查一个漆艺知识点。\n主题 / 当前对象: 生漆\n你想知道什么: 生漆是什么", "mode": "agent"},
        )
        session_id = create_resp.json()["session_id"]
        upload_resp = client.post(
            f"/api/sessions/{session_id}/attachments",
            files={"file": ("bad.txt", b"not-image", "text/plain")},
        )
        assert upload_resp.status_code == 415


def test_attachment_upload_rejects_oversized_file(tmp_path: Path):
    settings = Settings(
        upload_dir=str(tmp_path / "uploads"),
        max_upload_size_mb=1,
    )
    app = create_app(
        settings=settings,
        agent=FakeAgent(),
        session_store=SessionStore(":memory:"),
        teaching_service=FakeTeachingService(),
    )

    with TestClient(app) as client:
        register(client)
        create_resp = client.post(
            "/api/sessions",
            json={"query": "我想快速查一个漆艺知识点。\n主题 / 当前对象: 生漆\n你想知道什么: 生漆是什么", "mode": "agent"},
        )
        session_id = create_resp.json()["session_id"]
        big_payload = b"x" * (1024 * 1024 + 1)
        upload_resp = client.post(
            f"/api/sessions/{session_id}/attachments",
            files={"file": ("big.png", big_payload, "image/png")},
        )
        assert upload_resp.status_code == 413


def test_knowledge_scene_returns_artifact_and_can_export():
    app = create_app(
        agent=FakeAgent(),
        session_store=SessionStore(":memory:"),
        teaching_service=FakeTeachingService(),
    )

    with TestClient(app) as client:
        register(client)
        resp = client.post(
            "/api/sessions",
            json={
                "query": "我想快速查一个漆艺知识点。\n主题 / 当前对象: 生漆 / 腰果漆\n你想知道什么: 想快速弄清两者差异",
                "mode": "agent",
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["response"]["type"] == "artifact"
        assert data["response"]["artifact"]["title"] == "教学结果"
        assert data["state"]["module_artifact"]["summary"].startswith("已为场景 knowledge")

        export_resp = client.get(f"/api/sessions/{data['session_id']}/export/markdown")
        assert export_resp.status_code == 200
        assert "场景：knowledge" in export_resp.text


def test_safety_scene_returns_feasibility_verdict():
    app = create_app(
        agent=FakeAgent(),
        session_store=SessionStore(":memory:"),
        teaching_service=FakeTeachingService(),
    )

    with TestClient(app) as client:
        register(client)
        resp = client.post(
            "/api/sessions",
            json={
                "query": "我想先判断当前方案到底可不可行。\n关键步骤 / 当前方案: 已有旧涂层的木盒重涂\n你最想先确认什么: 现在能不能直接继续重涂",
                "mode": "agent",
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["response"]["type"] == "artifact"
        assert data["response"]["artifact"]["verdict"] == "conditional"
        assert data["response"]["artifact"]["required_conditions"] == ["漆体系", "环境湿度"]


def test_sessions_are_scoped_to_the_authenticated_user():
    app = create_app(
        agent=FakeAgent(),
        session_store=SessionStore(":memory:"),
        teaching_service=FakeTeachingService(),
    )

    with TestClient(app) as client:
        register(client, username="teacher_a")
        create_resp = client.post(
            "/api/sessions",
            json={
                "query": "我想生成一份可执行工艺计划。\n对象 / 基底: 木托盘\n你想做成什么效果: 半光黑漆面",
                "mode": "agent",
            },
        )
        assert create_resp.status_code == 200

        list_resp = client.get("/api/sessions")
        assert list_resp.status_code == 200
        assert len(list_resp.json()["sessions"]) == 1

        client.post("/api/auth/logout")
        register(client, username="teacher_b")

        list_resp_b = client.get("/api/sessions")
        assert list_resp_b.status_code == 200
        assert list_resp_b.json()["sessions"] == []


def test_presenter_helpers_still_humanize_contract_fields():
    assert humanize_slot_value("substrate_material", "wood") == "木材"
    assert humanize_slot_value("target_finish", "semi_gloss") == "半光"
    assert humanize_slot_value("environment_humidity_pct", "55") == "55%"

    contract = PlanContract(
        missing_critical_slots=["lacquer_system"],
        steps=[PlanStep(step_number=1, action="样板测试", checkpoint_id="CP-01")],
    )
    display = serialize_contract_display(contract)
    assert display is not None
    assert display["missing_critical_slots"][0]["label"] == "漆种/体系"
    assert display["steps"][0]["checkpoint_id"] == "CP-01"


def test_app_starts_when_mem0_is_unavailable(monkeypatch):
    from lacquertutor.agent import pipeline as pipeline_module

    def raise_mem0(_settings):
        raise RuntimeError("mem0 locked")

    monkeypatch.setattr(pipeline_module.Mem0MemoryService, "from_settings", raise_mem0)

    app = create_app(
        settings=Settings(),
        evidence_store=EvidenceStore([]),
        session_store=SessionStore(":memory:"),
    )

    with TestClient(app) as client:
        resp = client.get("/health")
        assert resp.status_code == 200
        assert resp.json() == {"status": "ok"}
