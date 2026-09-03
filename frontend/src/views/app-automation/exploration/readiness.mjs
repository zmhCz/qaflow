export function buildAINextRoundReadiness({
  hasAnalysis = false,
  targetCount = 0,
  acceptanceFailedCount = 0,
  pendingIssueCount = 0,
} = {}) {
  if (!hasAnalysis) {
    return {
      visible: false,
      ready: false,
      title: "",
      description: "",
      blocker: "",
    };
  }

  if (!targetCount) {
    return {
      visible: true,
      ready: false,
      title: "AI 暂未给出可执行的下一轮目标",
      description:
        "可以先查看 AI 分析详情，确认是否需要调整探索目标或重新分析报告。",
      blocker: "缺少目标",
    };
  }

  if (acceptanceFailedCount) {
    return {
      visible: true,
      ready: false,
      title: "先处理巡检验收，再扩下一轮",
      description: `当前还有 ${acceptanceFailedCount} 个验收指标未达标。先把稳定性问题处理掉，否则下一轮容易继续放大误差。`,
      blocker: "验收未过",
    };
  }

  if (pendingIssueCount) {
    return {
      visible: true,
      ready: false,
      title: "先复核疑似问题，再生成下一轮",
      description: `当前还有 ${pendingIssueCount} 个疑似问题未归档。先确认是缺陷、误报还是规则例外，再决定是否继续扩展。`,
      blocker: "待复核",
    };
  }

  return {
    visible: true,
    ready: true,
    title: "AI 已准备好下一轮巡检草稿",
    description: `已整理 ${targetCount} 个候选目标。点击后只会预填新任务，需要你确认设备、入口和风险项后再保存执行。`,
    blocker: "",
  };
}
