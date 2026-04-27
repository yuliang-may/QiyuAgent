import { useEffect } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";

import { Sidebar } from "../features/sessions/components/Sidebar";
import { SCENES } from "../features/app/config";
import { useAppStore } from "../features/app/store";
import type { SceneKey } from "../types/api";

interface SeedGroup {
  key: "pre" | "in" | "post";
  label: string;
  hint: string;
  items: SeedExample[];
}

interface SeedExample {
  title: string;
  goal: string;
  piece?: string;
  known?: string;
}

const SCENE_EXAMPLES: Record<SceneKey, SeedGroup[]> = {
  chat: [
    {
      key: "pre",
      label: "课前",
      hint: "快速备课",
      items: [
        { title: "备课问答", goal: "明天讲底胎处理，请用教师能直接讲给学生听的方式说明为什么要先做封固。" },
        { title: "概念梳理", goal: "把生漆、腰果漆、水性木器漆的课堂讲解重点列成一张对照表。" },
      ],
    },
    {
      key: "in",
      label: "课中",
      hint: "现场答疑",
      items: [
        { title: "学生追问", goal: "同一件作品打磨后局部发白，可能与哪些因素有关？请列出下一步需要观察的材料、环境和打磨情况。" },
        { title: "操作提醒", goal: "学生正在刷第二遍漆，请提醒最容易忽略的环境、厚薄和入荫条件。" },
      ],
    },
    {
      key: "post",
      label: "课后",
      hint: "复盘巩固",
      items: [
        { title: "课后小结", goal: "把今天的封固、刮灰、打磨三个动作整理成学生课后复盘提纲。" },
        { title: "答疑备忘", goal: "整理一份学生常问的五个漆艺基础问题和简短回答。" },
      ],
    },
  ],
  planning: [
    {
      key: "pre",
      label: "课前",
      hint: "教师备料",
      items: [
        {
          title: "木托盘样板",
          piece: "木托盘",
          goal: "生成一份适合课堂演示的半光黑漆面工艺单。",
          known: "学生第一次做完整流程，课堂时长有限，需要先做样板。",
        },
        {
          title: "贝壳镶嵌练习",
          piece: "小木牌",
          goal: "规划一节课内可完成的贝壳镶嵌预处理和封固流程。",
          known: "希望避免不可逆返工，先确认关键条件。",
        },
      ],
    },
    {
      key: "in",
      label: "课中",
      hint: "分步推进",
      items: [
        {
          title: "分组操作",
          piece: "学生分组木片",
          goal: "把封固、刮灰、打磨拆成可检查的课堂任务单。",
          known: "每组材料略有差异，需要留检查点。",
        },
      ],
    },
    {
      key: "post",
      label: "课后",
      hint: "延续任务",
      items: [
        {
          title: "下次课衔接",
          piece: "已封固木胎",
          goal: "安排下一次课从检查干燥状态到进入下一层工序的计划。",
          known: "需要先判断是否能继续上漆。",
        },
      ],
    },
  ],
  troubleshooting: [
    {
      key: "pre",
      label: "课前",
      hint: "预设风险",
      items: [
        {
          title: "潮湿天气预案",
          piece: "木胎封固阶段",
          goal: "学生作品在潮湿天气里容易发白，帮我准备课堂排查问题。",
          known: "环境湿度偏高，上一层刚干不久。",
        },
      ],
    },
    {
      key: "in",
      label: "课中",
      hint: "现场诊断",
      items: [
        {
          title: "表面发白",
          piece: "木托盘第二遍漆后",
          goal: "判断表面发白可能来自水汽、打磨粉还是上一层未干，并给学生下一步处理建议。",
          known: "不确定是否可以继续打磨。",
        },
        {
          title: "打磨发黄",
          piece: "砂纸打磨后",
          goal: "排查表面发黄的可能原因，并告诉我哪些情况不能继续上下一层。",
          known: "学生用的是旧砂纸，力度不均匀。",
        },
      ],
    },
    {
      key: "post",
      label: "课后",
      hint: "复盘记录",
      items: [
        {
          title: "问题归档",
          piece: "本周学生作品",
          goal: "把课堂上出现的发白、起粒、厚薄不均整理成复盘清单。",
          known: "希望下次课能按现象逐项检查。",
        },
      ],
    },
  ],
  safety: [
    {
      key: "pre",
      label: "课前",
      hint: "开课前判断",
      items: [
        {
          title: "旧涂层重涂",
          piece: "旧木盒",
          goal: "评估旧涂层成分不明时是否能直接重涂，并列出必须先确认的信息。",
          known: "学生带来的旧物没有施工记录。",
        },
        {
          title: "过敏说明",
          piece: "生漆体验课",
          goal: "帮我准备课堂前的生漆接触风险说明和防护检查表。",
          known: "有学生第一次接触生漆。",
        },
      ],
    },
    {
      key: "in",
      label: "课中",
      hint: "放行判断",
      items: [
        {
          title: "是否停步",
          piece: "正在打磨的旧漆面",
          goal: "判断出现刺激性气味和粉尘时是否需要暂停课堂操作。",
          known: "现场通风一般，学生未佩戴完整防护。",
        },
      ],
    },
    {
      key: "post",
      label: "课后",
      hint: "风险复盘",
      items: [
        {
          title: "安全复盘",
          piece: "课堂操作记录",
          goal: "把今天需要改进的防护、通风、材料标识整理成下次课前检查清单。",
          known: "希望不责备学生，只给清楚可执行的改进项。",
        },
      ],
    },
  ],
  knowledge: [
    {
      key: "pre",
      label: "课前",
      hint: "知识讲解",
      items: [
        {
          title: "材料对照",
          piece: "生漆与腰果漆",
          goal: "对比生漆与腰果漆的课堂讲解重点，说明哪些结论有知识库依据，哪些需要补充条件。",
          known: "面向非材料专业学生。",
        },
        {
          title: "工具说明",
          piece: "规尺",
          goal: "用知识库里的图片和片段讲清楚规尺在标记和测量中的作用。",
          known: "希望能配合课堂示范。",
        },
      ],
    },
    {
      key: "in",
      label: "课中",
      hint: "即时解释",
      items: [
        {
          title: "学生提问",
          piece: "封固",
          goal: "学生问为什么封固后才能继续刮灰，请给一个有依据但容易听懂的解释。",
          known: "学生已经看过一次演示。",
        },
      ],
    },
    {
      key: "post",
      label: "课后",
      hint: "题目生成",
      items: [
        {
          title: "课后练习",
          piece: "底胎处理",
          goal: "基于知识库生成三道判断题和一道开放题，并附简短参考答案。",
          known: "题目用于课后巩固，不要太难。",
        },
      ],
    },
  ],
  learning: [
    {
      key: "pre",
      label: "课前",
      hint: "路径设计",
      items: [
        {
          title: "零基础入门",
          piece: "初学者",
          goal: "为零基础学生设计一周底胎处理练习路径。",
          known: "每天最多练 40 分钟，需要安全提醒。",
        },
        {
          title: "进阶补弱",
          piece: "已经能刷涂的学生",
          goal: "安排从封固到打磨稳定性的阶段化练习。",
          known: "学生容易急着进入正式作品。",
        },
      ],
    },
    {
      key: "in",
      label: "课中",
      hint: "分层指导",
      items: [
        {
          title: "水平差异",
          piece: "同一班学生",
          goal: "把同一节课拆成基础、进阶、挑战三档任务。",
          known: "班里有人第一次做，也有人做过小样。",
        },
      ],
    },
    {
      key: "post",
      label: "课后",
      hint: "持续练习",
      items: [
        {
          title: "家庭练习",
          piece: "课后自学",
          goal: "设计不需要危险材料、但能巩固观察和记录能力的课后练习。",
          known: "学生不一定有专业工具。",
        },
      ],
    },
  ],
};

const SCENE_ORDER: SceneKey[] = [
  "knowledge",
  "troubleshooting",
  "learning",
  "planning",
  "safety",
];

export function HomePage() {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();

  const home = useAppStore((state) => state.home);
  const selectedScene = useAppStore((state) => state.selectedScene);
  const kickoff = useAppStore((state) => state.kickoff);
  const mutating = useAppStore((state) => state.mutating);
  const error = useAppStore((state) => state.error);
  const setSelectedScene = useAppStore((state) => state.setSelectedScene);
  const updateKickoff = useAppStore((state) => state.updateKickoff);
  const createSessionFromKickoff = useAppStore((state) => state.createSessionFromKickoff);
  const refreshHome = useAppStore((state) => state.refreshHome);
  const logout = useAppStore((state) => state.logout);

  useEffect(() => {
    void refreshHome();
  }, [refreshHome]);

  useEffect(() => {
    const requested = searchParams.get("scene");
    if (requested && requested in SCENES) {
      setSelectedScene(requested as SceneKey);
    }
  }, [searchParams, setSelectedScene]);

  function applyExample(example: SeedExample) {
    updateKickoff({
      piece: example.piece || "",
      goal: example.goal,
      known: example.known || "",
    });
  }

  function selectScene(sceneKey: SceneKey) {
    setSelectedScene(sceneKey);
    updateKickoff({ piece: "", goal: "", known: "" });
  }

  async function askDirect() {
    const text = kickoff.goal.trim();
    if (!text) return;
    const sessionId = await createSessionFromKickoff();
    navigate(`/p/${sessionId}`);
  }

  function onAskKey(event: React.KeyboardEvent<HTMLTextAreaElement>) {
    if ((event.metaKey || event.ctrlKey) && event.key === "Enter") {
      event.preventDefault();
      void askDirect();
    }
  }

  const recent = home?.recentSessions ?? [];
  const totalSessions = home?.totalSessions ?? 0;
  const showStats = totalSessions > 0;
  const scene = SCENES[selectedScene];
  const sceneExamples = SCENE_EXAMPLES[selectedScene];

  return (
    <main className="app-shell">
      <Sidebar
        home={home}
        activeSession={null}
        selectedScene={selectedScene}
        onSelectScene={selectScene}
        onLogout={logout}
      />

      <section className="home-stage">
        <header className="hero-poster">
          <span className="eyebrow">漆语 · {scene.title}</span>
          <h2>
            <span className="accent">{scene.title}</span>教学工作台
          </h2>
          <p>{scene.heroLede}</p>
          {showStats ? (
            <div className="hero-stats">
              <div>
                <strong>{totalSessions}</strong>
                <span>累计会话</span>
              </div>
              <div>
                <strong>{home?.completedSessions ?? 0}</strong>
                <span>已完成</span>
              </div>
              <div>
                <strong>{home?.recentTopics.length ?? 0}</strong>
                <span>近期主题</span>
              </div>
            </div>
          ) : null}
        </header>

        <section className="ask-block" aria-label="发起对话">
          <label htmlFor="ask-input">{scene.title} · 输入教学任务或问题</label>
          <textarea
            id="ask-input"
            value={kickoff.goal}
            onChange={(event) => updateKickoff({ goal: event.target.value })}
            onKeyDown={onAskKey}
            placeholder={scene.goalPlaceholder}
          />
          <div className="ask-row">
            <span className="composer-hint">当前页面：{scene.title} · 案例只会填入输入框</span>
            <button
              type="button"
              className="primary-button"
              disabled={mutating || !kickoff.goal.trim()}
              onClick={() => void askDirect()}
            >
              {mutating ? "发起中…" : `在${scene.title}中开始`}
            </button>
          </div>
          {error ? <p className="form-error">{error}</p> : null}
        </section>

        <section className="seed-section" aria-label="按课堂时序的示例任务">
          <header className="section-head">
            <span className="eyebrow">{scene.title}案例</span>
            <h3>选择案例只会填入当前页面，不会直接跳转</h3>
          </header>
          <div className="seed-groups">
            {sceneExamples.map((group) => (
              <article key={group.key} className={`seed-group seed-group-${group.key}`}>
                <header className="seed-group-head">
                  <span className="seed-group-label">{group.label}</span>
                  <span className="seed-group-hint">{group.hint}</span>
                </header>
                <div className="seed-list">
                  {group.items.map((item) => (
                    <button
                      key={item.title}
                      type="button"
                      className="seed-line"
                      onClick={() => applyExample(item)}
                      disabled={mutating}
                    >
                      <span className="seed-line-text">
                        <strong>{item.title}</strong>
                        <small>{item.goal}</small>
                      </span>
                      <span className="seed-line-arrow" aria-hidden>填入</span>
                    </button>
                  ))}
                </div>
              </article>
            ))}
          </div>
        </section>

        <section className="scene-grid-section" aria-label="专用智能体">
          <header className="section-head">
            <span className="eyebrow">五个专用智能体</span>
            <h3>按任务类型进入对应工作位</h3>
          </header>
          <div className="scene-grid">
            {SCENE_ORDER.map((key) => {
              const item = SCENES[key];
              return (
                <button
                  key={key}
                  type="button"
                  className={`scene-card ${selectedScene === key ? "active" : ""}`}
                  onClick={() => selectScene(key)}
                  disabled={mutating}
                >
                  <strong>{item.title}</strong>
                  <p>{item.summary}</p>
                  <small>{selectedScene === key ? "当前页面" : "切换页面"}</small>
                </button>
              );
            })}
          </div>
        </section>

        {recent.length ? (
          <section className="continue-section" aria-label="进行中的会话">
            <header className="section-head">
              <span className="eyebrow">进行中</span>
              <h3>继续上一次会话</h3>
            </header>
            <div className="continue-grid">
              {recent.slice(0, 6).map((session) => (
                <button
                  key={session.sessionId}
                  type="button"
                  className="continue-card"
                  onClick={() => navigate(`/p/${session.sessionId}`)}
                >
                  <span className="continue-meta">{session.sceneLabel} · {session.statusLabel}</span>
                  <strong>{session.projectTitle}</strong>
                  <p>{session.projectSummary}</p>
                </button>
              ))}
            </div>
          </section>
        ) : null}
      </section>
    </main>
  );
}
