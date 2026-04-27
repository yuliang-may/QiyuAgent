import type { SceneKey, SessionMode } from "../../types/api";

export interface SceneDefinition {
  key: SceneKey;
  title: string;
  summary: string;
  /** 工作台 hero 大字标题 */
  heroHeadline: string;
  /** 标题下的一句产品定义 */
  heroLede: string;
  pieceLabel: string;
  goalLabel: string;
  piecePlaceholder: string;
  goalPlaceholder: string;
  knownPlaceholder: string;
  requestLine: string;
}

export const SCENES: Record<SceneKey, SceneDefinition> = {
  chat: {
    key: "chat",
    title: "通用对话",
    summary: "基于专业知识库的常规问答",
    heroHeadline: "通用对话。",
    heroLede: "面向漆艺非遗教学的常规问答入口。系统将优先在专业知识库中检索后再作答。",
    pieceLabel: "对象 / 主题",
    goalLabel: "你的问题",
    piecePlaceholder: "例如：木托盘、生漆入门、底胎处理",
    goalPlaceholder: "请输入完整的问题或任务描述。",
    knownPlaceholder: "可补充已知的前置条件。",
    requestLine: "请像通用漆艺助手一样直接回答，并优先基于知识片段给出可靠说明。",
  },
  planning: {
    key: "planning",
    title: "工艺计划",
    summary: "为作品生成可执行工艺单",
    heroHeadline: "工艺计划。",
    heroLede: "结合材料、工艺规范与安全要求，生成分步骤、含关键节点的可执行工艺计划。",
    pieceLabel: "对象 / 基底",
    goalLabel: "目标效果",
    piecePlaceholder: "例如：木盒、木托盘、底胎",
    goalPlaceholder: "例如：耐用的半光黑漆面。",
    knownPlaceholder: "例如：尚未确定漆体系；环境温湿度偏高。",
    requestLine: "请先识别当前必须确认的关键条件，再一次只问我一个真正关键的问题，最后输出可执行方案。",
  },
  troubleshooting: {
    key: "troubleshooting",
    title: "故障排查",
    summary: "针对现象逐步追问并定位原因",
    heroHeadline: "故障排查。",
    heroLede: "针对现场现象逐步追问，先定位安全边界，再分析可能成因与处置策略。",
    pieceLabel: "当前阶段",
    goalLabel: "出现的现象",
    piecePlaceholder: "例如：木盒已刷 2 层；木托盘正在固化",
    goalPlaceholder: "例如：表面发白发雾，待确认是否可继续打磨重涂。",
    knownPlaceholder: "例如：环境偏潮；上一层施工时间为两天前。",
    requestLine: "请先判断是否要安全停步，再逐步追问并定位原因，不要一上来就让我返工。",
  },
  knowledge: {
    key: "knowledge",
    title: "知识问答",
    summary: "基于专业知识库的有据回答",
    heroHeadline: "知识问答。",
    heroLede: "基于 5000+ 条漆艺非遗专业知识，提供有出处、有上下文的结构化回答。",
    pieceLabel: "主题 / 当前对象",
    goalLabel: "你的问题",
    piecePlaceholder: "例如：生漆、水性木器漆、木胎",
    goalPlaceholder: "例如：生漆与腰果漆的成膜机理与适用场景。",
    knownPlaceholder: "可补充教学场景或已知背景。",
    requestLine: "请基于知识库先给我一个有依据的回答，再补两到三个值得继续追问的问题。",
  },
  learning: {
    key: "learning",
    title: "学习路径",
    summary: "按水平与目标排阶段化练习",
    heroHeadline: "学习路径。",
    heroLede: "依据当前水平与学习目标，输出含安全规范、练习顺序与样板验证的阶段化路径。",
    pieceLabel: "当前水平 / 学习目标",
    goalLabel: "重点补强方向",
    piecePlaceholder: "例如：零基础入门；已掌握基础刷涂",
    goalPlaceholder: "例如：系统学习底胎处理与成膜稳定性。",
    knownPlaceholder: "例如：可接受先做样板，不急于上正式作品。",
    requestLine: "请给我一条阶段化学习路径，兼顾安全、练习顺序、样板验证和进阶目标。",
  },
  safety: {
    key: "safety",
    title: "安全评估",
    summary: "先判断方案可行性再行动",
    heroHeadline: "安全评估。",
    heroLede: "在动手之前评估方案可行性。识别阻断项、必须补齐的条件与失败后果。",
    pieceLabel: "关键步骤 / 当前方案",
    goalLabel: "需先确认的事项",
    piecePlaceholder: "例如：重涂、固化、打磨、旧涂层覆盖",
    goalPlaceholder: "例如：旧涂层成分不明时是否可直接重涂。",
    knownPlaceholder: "例如：环境偏潮；旧涂层施工记录缺失。",
    requestLine: "请基于真实知识先判断当前方案是可行、有条件可行还是暂不可行，再告诉我阻断项和必须补齐的条件。",
  },
};

export const SESSION_MODES: Record<
  SessionMode,
  { title: string; description: string }
> = {
  agent: {
    title: "智能引导",
    description: "由系统判断追问顺序——适用于多数场景。",
  },
  workflow: {
    title: "严格工作流",
    description: "按固定流程逐项补齐——适用于高风险操作。",
  },
};

export function buildSceneQuery(input: {
  sceneKey: SceneKey;
  piece: string;
  goal: string;
  known: string;
  mode: SessionMode;
}): string {
  const scene = SCENES[input.sceneKey];
  if (input.sceneKey === "chat") {
    return input.goal.trim();
  }

  const lines = [scene.summary];

  if (input.piece.trim()) {
    lines.push(`${scene.pieceLabel}: ${input.piece.trim()}`);
  }

  if (input.goal.trim()) {
    lines.push(`${scene.goalLabel}: ${input.goal.trim()}`);
  }

  if (input.known.trim()) {
    lines.push(`我已经知道的信息: ${input.known.trim()}`);
  }

  lines.push(scene.requestLine);
  lines.push(`当前希望的引导方式: ${SESSION_MODES[input.mode].title}。`);
  return lines.join("\n");
}

export function buildQuickFollowupQuery(sceneKey: SceneKey, text: string, mode: SessionMode): string {
  return buildSceneQuery({
    sceneKey,
    piece: "",
    goal: text,
    known: "",
    mode,
  });
}
