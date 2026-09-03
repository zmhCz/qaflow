<template>
  <div class="quality-backlog">
    <section class="hero-panel">
      <div>
        <span class="eyebrow">Quality Backlog</span>
        <h1>质量待办中心</h1>
        <p>
          聚合 APP 执行失败、AI
          探索疑似问题、等待中的任务和证据不完整项，先形成一个“今天该处理什么”的队列。
          当前仍是视图层能力，不引入缺陷表和工作流审批。
        </p>
      </div>
      <div class="hero-actions">
        <el-button type="primary" @click="navigate('/platform/executions')"
          >查看统一执行</el-button
        >
        <el-button plain @click="navigate('/platform/evidence')"
          >查看证据中心</el-button
        >
      </div>
    </section>

    <section class="summary-grid">
      <article
        v-for="item in summaryCards"
        :key="item.key"
        class="summary-card"
        @click="activeFilter = item.key"
      >
        <span class="summary-label">{{ item.label }}</span>
        <strong>{{ item.value }}</strong>
        <p>{{ item.desc }}</p>
      </article>
    </section>

    <section class="backlog-layout">
      <aside class="filter-panel">
        <div class="section-title">待办筛选</div>
        <button
          v-for="item in filterOptions"
          :key="item.key"
          class="filter-item"
          :class="{ active: activeFilter === item.key }"
          @click="activeFilter = item.key"
        >
          <span>{{ item.label }}</span>
          <em>{{ item.count }}</em>
        </button>
      </aside>

      <main class="backlog-list-panel">
        <div class="list-toolbar">
          <div>
            <h2>质量待办队列</h2>
            <p>优先级来自任务状态、失败/问题数量、证据完整度和是否仍在执行。</p>
          </div>
          <div class="toolbar-actions">
            <el-input
              v-model="keyword"
              clearable
              placeholder="搜索任务 / 设备 / 原因 / 建议"
              style="width: 280px"
            />
            <el-button :loading="loading" @click="loadBacklog">刷新</el-button>
          </div>
        </div>

        <el-alert
          v-if="loadErrors.length"
          class="load-alert"
          type="warning"
          show-icon
          :closable="false"
          title="部分待办来源加载失败"
        >
          <template #default>{{ loadErrors.join("；") }}</template>
        </el-alert>

        <el-table
          v-loading="loading"
          :data="filteredBacklog"
          border
          empty-text="暂无质量待办"
        >
          <el-table-column
            label="待办对象"
            min-width="260"
            show-overflow-tooltip
          >
            <template #default="{ row }">
              <div class="backlog-name">
                <span>{{ row.name }}</span>
                <el-tag size="small" :type="row.tagType" effect="plain">{{
                  row.sourceName
                }}</el-tag>
              </div>
            </template>
          </el-table-column>
          <el-table-column label="优先级" width="110">
            <template #default="{ row }">
              <el-tag :type="priorityType(row.priority)" size="small">{{
                priorityText(row.priority)
              }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column label="待办类型" width="130">
            <template #default="{ row }">{{ row.typeName }}</template>
          </el-table-column>
          <el-table-column label="原因" min-width="220" show-overflow-tooltip>
            <template #default="{ row }">{{ row.reason }}</template>
          </el-table-column>
          <el-table-column
            label="建议动作"
            min-width="210"
            show-overflow-tooltip
          >
            <template #default="{ row }">{{ row.action }}</template>
          </el-table-column>
          <el-table-column
            label="设备/范围"
            min-width="150"
            show-overflow-tooltip
          >
            <template #default="{ row }">{{
              row.device || row.scope || "-"
            }}</template>
          </el-table-column>
          <el-table-column label="最近时间" width="170">
            <template #default="{ row }">{{
              formatDate(row.updatedAt)
            }}</template>
          </el-table-column>
          <el-table-column label="操作" width="230" fixed="right">
            <template #default="{ row }">
              <el-button link type="primary" @click="goPrimary(row)">{{
                row.primaryAction
              }}</el-button>
              <el-button link type="primary" @click="goExecution(row)"
                >执行</el-button
              >
              <el-button link type="primary" @click="goEvidence(row)"
                >证据</el-button
              >
            </template>
          </el-table-column>
        </el-table>
      </main>
    </section>

    <section class="principle-panel">
      <div class="section-title">待办中心第一版边界</div>
      <div class="principle-grid">
        <div
          v-for="item in principles"
          :key="item.title"
          class="principle-card"
        >
          <strong>{{ item.title }}</strong>
          <p>{{ item.desc }}</p>
        </div>
      </div>
    </section>
  </div>
</template>

<script setup>
import { computed, onMounted, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import api from "@/utils/api";

const router = useRouter();
const route = useRoute();
const loading = ref(false);
const keyword = ref("");
const activeFilter = ref("all");
const backlogItems = ref([]);
const loadErrors = ref([]);

const principles = [
  {
    title: "先做可处理队列",
    desc: "第一版只聚合风险项和跳转入口，不新增缺陷、指派、流转等流程模型。",
  },
  {
    title: "优先服务日常排查",
    desc: "让测试同学先知道失败、疑似问题、证据缺口分别该去哪里处理。",
  },
  {
    title: "保留来源追溯",
    desc: "每条待办都能回到执行中心、证据中心和原始模块。",
  },
  {
    title: "后续再接缺陷",
    desc: "稳定后再把待办升级为缺陷草稿、企微通知和团队协同看板。",
  },
];

const normalizeList = (response) => {
  const data = response?.data;
  if (Array.isArray(data)) return data;
  if (Array.isArray(data?.results)) return data.results;
  if (Array.isArray(data?.data)) return data.data;
  return [];
};

const normalizeStatus = (status) => String(status || "").toLowerCase();

const pickDate = (item) =>
  item.finished_at ||
  item.updated_at ||
  item.started_at ||
  item.created_at ||
  "";

const statusText = (status) => {
  const text = normalizeStatus(status);
  if (["passed", "success", "completed"].includes(text)) return "通过";
  if (text === "failed") return "失败";
  if (text === "error") return "异常";
  if (text === "running") return "执行中";
  if (text === "pending") return "等待中";
  if (text === "stopped") return "已停止";
  return status || "未标记";
};

const toAppBacklog = (item, index) => {
  const status = normalizeStatus(item.result || item.status);
  const failedSteps = Number(item.failed_steps || 0);
  const hasReport = Boolean(item.report_path || item.report_url);
  const hasPerformance = Boolean(
    item.performance_enabled || item.performance_summary?.enabled,
  );
  const name =
    item.case_name ||
    item.test_case_name ||
    item.name ||
    `APP 执行 #${item.id || index + 1}`;
  const pending = status === "pending";
  const running = status === "running";
  const failed =
    ["failed", "error", "stopped"].includes(status) || failedSteps > 0;
  const evidenceMissing =
    ["passed", "success", "completed", "failed", "error"].includes(status) &&
    (!hasReport || !hasPerformance);

  if (!pending && !running && !failed && !evidenceMissing) return null;

  let type = "evidence";
  let typeName = "证据缺口";
  let priority = "low";
  let reason = "执行已结束，但报告或性能证据不完整";
  let action = "补齐报告、logcat 或性能数据后再复盘";
  let primaryAction = "补证据";

  if (failed) {
    type = "failure";
    typeName = "执行失败";
    priority = failedSteps >= 2 || status === "error" ? "high" : "medium";
    reason = `状态${statusText(status)}，失败步骤 ${failedSteps} 个`;
    action = "优先查看报告、截图和 logcat，判断缺陷/脚本/环境归因";
    primaryAction = "查失败";
  } else if (running || pending) {
    type = running ? "running" : "pending";
    typeName = running ? "执行中" : "等待中";
    priority = running ? "medium" : "low";
    reason = `任务当前${statusText(status)}`;
    action = running
      ? "观察进度，必要时进入执行记录确认卡点"
      : "确认设备、队列或调度是否正常";
    primaryAction = "看进度";
  }

  return {
    id: `app-${item.id || index}`,
    source: "app_execution",
    sourceName: "APP 执行",
    tagType: "primary",
    name,
    type,
    typeName,
    priority,
    reason,
    action,
    primaryAction,
    device: item.device_name || item.device || "",
    scope: item.project_name || item.suite_name || "",
    updatedAt: pickDate(item),
    sourceRoute: "/app-automation/executions",
  };
};

const toExplorationBacklog = (item, index) => {
  const status = normalizeStatus(item.result || item.status);
  const issueCount = Number(item.issue_count || 0);
  const hasLogcat = Boolean(
    item.logcat?.available || item.summary?.logcat?.available,
  );
  const hasAI = Boolean(
    item.summary?.ai_analysis || item.insights?.ai_analysis,
  );
  const name =
    item.name || item.objective || `AI 探索 #${item.id || index + 1}`;
  const pending = status === "pending";
  const running = status === "running";
  const suspicious = issueCount > 0;
  const missingAnalysis =
    ["completed", "success", "passed"].includes(status) &&
    (!hasAI || !hasLogcat);

  if (!pending && !running && !suspicious && !missingAnalysis) return null;

  let type = "analysis";
  let typeName = "分析缺口";
  let priority = "low";
  let reason = "探索已结束，但 AI 分析或 logcat 证据不完整";
  let action = "补跑 AI 分析或导出日志后再复核";
  let primaryAction = "补分析";

  if (suspicious) {
    type = "suspicious";
    typeName = "疑似问题";
    priority = issueCount >= 3 ? "high" : "medium";
    reason = `AI 探索发现 ${issueCount} 个疑似问题`;
    action = "进入探索报告复核，确认误报、有效问题或转用例";
    primaryAction = "去复核";
  } else if (running || pending) {
    type = running ? "running" : "pending";
    typeName = running ? "探索中" : "等待中";
    priority = running ? "medium" : "low";
    reason = `探索任务当前${statusText(status)}`;
    action = running
      ? "观察探索轨迹和日志，避免长时间无反馈"
      : "确认设备、包名和探索入口是否可用";
    primaryAction = "看进度";
  }

  return {
    id: `exploration-${item.id || index}`,
    source: "ai_exploration",
    sourceName: "AI 探索",
    tagType: "success",
    name,
    type,
    typeName,
    priority,
    reason,
    action,
    primaryAction,
    device: item.device_name || item.device || "",
    scope: item.package_name || item.objective || "",
    updatedAt: pickDate(item),
    sourceRoute: "/app-automation/exploration",
  };
};

const loadBacklog = async () => {
  loading.value = true;
  loadErrors.value = [];
  const requests = [
    api.get("/app-automation/executions/", {
      params: { page: 1, page_size: 30 },
    }),
    api.get("/app-automation/exploration-tasks/", {
      params: { page: 1, page_size: 30 },
    }),
  ];
  const results = await Promise.allSettled(requests);
  const next = [];

  if (results[0].status === "fulfilled") {
    next.push(
      ...normalizeList(results[0].value).map(toAppBacklog).filter(Boolean),
    );
  } else {
    loadErrors.value.push(
      `APP 执行：${results[0].reason?.userMessage || results[0].reason?.message || "加载失败"}`,
    );
  }

  if (results[1].status === "fulfilled") {
    next.push(
      ...normalizeList(results[1].value)
        .map(toExplorationBacklog)
        .filter(Boolean),
    );
  } else {
    loadErrors.value.push(
      `AI 探索：${results[1].reason?.userMessage || results[1].reason?.message || "加载失败"}`,
    );
  }

  backlogItems.value = next.sort((a, b) => {
    const priorityDiff =
      priorityWeight(b.priority) - priorityWeight(a.priority);
    if (priorityDiff) return priorityDiff;
    return new Date(b.updatedAt || 0) - new Date(a.updatedAt || 0);
  });
  loading.value = false;
};

const summaryCards = computed(() => [
  {
    key: "all",
    label: "全部待办",
    value: backlogItems.value.length,
    desc: "需要关注的质量事项",
  },
  {
    key: "high",
    label: "高优先级",
    value: backlogItems.value.filter((item) => item.priority === "high").length,
    desc: "建议优先处理",
  },
  {
    key: "failure",
    label: "失败/异常",
    value: backlogItems.value.filter((item) => item.type === "failure").length,
    desc: "执行失败或异常停止",
  },
  {
    key: "suspicious",
    label: "疑似问题",
    value: backlogItems.value.filter((item) => item.type === "suspicious")
      .length,
    desc: "AI 探索待复核",
  },
  {
    key: "pending",
    label: "等待/执行中",
    value: backlogItems.value.filter((item) =>
      ["pending", "running"].includes(item.type),
    ).length,
    desc: "需要确认进度",
  },
  {
    key: "evidence",
    label: "证据缺口",
    value: backlogItems.value.filter((item) =>
      ["evidence", "analysis"].includes(item.type),
    ).length,
    desc: "报告或日志不完整",
  },
]);

const filterOptions = computed(() =>
  summaryCards.value.map((item) => ({
    key: item.key,
    label: item.label,
    count: item.value,
  })),
);

const filteredBacklog = computed(() => {
  const text = keyword.value.trim().toLowerCase();
  return backlogItems.value.filter((item) => {
    if (activeFilter.value === "high" && item.priority !== "high") return false;
    if (activeFilter.value === "failure" && item.type !== "failure")
      return false;
    if (activeFilter.value === "suspicious" && item.type !== "suspicious")
      return false;
    if (
      activeFilter.value === "pending" &&
      !["pending", "running"].includes(item.type)
    )
      return false;
    if (
      activeFilter.value === "evidence" &&
      !["evidence", "analysis"].includes(item.type)
    )
      return false;
    if (!text) return true;
    return [
      item.name,
      item.sourceName,
      item.typeName,
      item.reason,
      item.action,
      item.device,
      item.scope,
    ].some((value) =>
      String(value || "")
        .toLowerCase()
        .includes(text),
    );
  });
});

const navigate = (path) => router.push(path);

const goPrimary = (row) => {
  if (row.type === "suspicious" || row.source === "ai_exploration") {
    navigate("/app-automation/exploration");
    return;
  }
  if (row.type === "failure" || ["evidence", "analysis"].includes(row.type)) {
    goEvidence(row);
    return;
  }
  goExecution(row);
};

const goExecution = (row) => {
  router.push({
    path: "/platform/executions",
    query: {
      q: row.name,
      filter: row.type === "failure" ? "failed" : "all",
    },
  });
};

const goEvidence = (row) => {
  router.push({
    path: "/platform/evidence",
    query: {
      q: row.name,
      filter: row.source === "ai_exploration" ? "exploration" : "execution",
    },
  });
};

const applyRouteQuery = () => {
  const queryKeyword = route.query.q;
  const queryFilter = route.query.filter;
  if (typeof queryKeyword === "string") keyword.value = queryKeyword;
  if (
    typeof queryFilter === "string" &&
    ["all", "high", "failure", "suspicious", "pending", "evidence"].includes(
      queryFilter,
    )
  ) {
    activeFilter.value = queryFilter;
  }
};

const priorityWeight = (priority) => {
  if (priority === "high") return 3;
  if (priority === "medium") return 2;
  return 1;
};

const priorityText = (priority) => {
  if (priority === "high") return "高";
  if (priority === "medium") return "中";
  return "低";
};

const priorityType = (priority) => {
  if (priority === "high") return "danger";
  if (priority === "medium") return "warning";
  return "info";
};

const formatDate = (value) => {
  if (!value) return "-";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return String(value).slice(0, 19);
  return date.toLocaleString("zh-CN", { hour12: false });
};

watch(
  () => route.query,
  () => {
    applyRouteQuery();
  },
  { immediate: true },
);

onMounted(loadBacklog);
</script>

<style scoped lang="scss">
.quality-backlog {
  min-height: 100%;
  padding: 8px 4px 20px;
  display: flex;
  flex-direction: column;
  gap: 22px;
}

.hero-panel {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: 20px;
  padding: 28px;
  border-radius: 24px;
  color: #f8fbff;
  background:
    radial-gradient(
      circle at top right,
      rgba(248, 113, 113, 0.25),
      transparent 30%
    ),
    linear-gradient(135deg, #1f2937 0%, #3f1d32 48%, #b91c1c 100%);
  box-shadow: 0 20px 50px rgba(15, 23, 42, 0.16);
}

.hero-panel h1 {
  margin: 8px 0 12px;
  font-size: 32px;
}

.hero-panel p {
  max-width: 800px;
  margin: 0;
  color: rgba(248, 251, 255, 0.84);
  line-height: 1.75;
}

.eyebrow {
  display: inline-flex;
  padding: 6px 12px;
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.12);
  border: 1px solid rgba(255, 255, 255, 0.16);
  font-size: 12px;
  letter-spacing: 0.08em;
}

.hero-actions,
.toolbar-actions {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 10px;
}

.summary-grid {
  display: grid;
  grid-template-columns: repeat(6, minmax(0, 1fr));
  gap: 14px;
}

.summary-card,
.filter-panel,
.backlog-list-panel,
.principle-panel {
  border-radius: 20px;
  background: #fff;
  border: 1px solid #e8eef5;
  box-shadow: 0 10px 30px rgba(17, 42, 70, 0.06);
}

.summary-card {
  padding: 18px;
  cursor: pointer;
  transition:
    transform 0.2s ease,
    border-color 0.2s ease;
}

.summary-card:hover {
  transform: translateY(-3px);
  border-color: #fca5a5;
}

.summary-label {
  color: #64748b;
  font-size: 13px;
}

.summary-card strong {
  display: block;
  margin-top: 10px;
  color: #122033;
  font-size: 30px;
}

.summary-card p {
  margin: 6px 0 0;
  color: #64748b;
}

.backlog-layout {
  display: grid;
  grid-template-columns: 220px minmax(0, 1fr);
  gap: 18px;
}

.filter-panel,
.backlog-list-panel,
.principle-panel {
  padding: 18px;
}

.section-title {
  margin-bottom: 14px;
  color: #172033;
  font-size: 18px;
  font-weight: 700;
}

.filter-item {
  width: 100%;
  border: 0;
  border-radius: 14px;
  padding: 12px 14px;
  margin-bottom: 8px;
  background: transparent;
  color: #475569;
  display: flex;
  justify-content: space-between;
  cursor: pointer;
}

.filter-item.active,
.filter-item:hover {
  background: #fef2f2;
  color: #b91c1c;
}

.filter-item em {
  font-style: normal;
  font-weight: 700;
}

.list-toolbar {
  display: flex;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 14px;
}

.list-toolbar h2 {
  margin: 0 0 6px;
  color: #172033;
}

.list-toolbar p {
  margin: 0;
  color: #64748b;
}

.load-alert {
  margin-bottom: 14px;
}

.backlog-name {
  display: flex;
  align-items: center;
  gap: 8px;
}

.principle-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 14px;
}

.principle-card {
  padding: 16px;
  border-radius: 16px;
  background: #fff7ed;
  border: 1px solid #fed7aa;
}

.principle-card strong {
  color: #172033;
}

.principle-card p {
  margin: 8px 0 0;
  color: #64748b;
  line-height: 1.6;
}

@media (max-width: 1280px) {
  .summary-grid {
    grid-template-columns: repeat(3, minmax(0, 1fr));
  }

  .principle-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

@media (max-width: 960px) {
  .hero-panel,
  .list-toolbar {
    flex-direction: column;
    align-items: stretch;
  }

  .summary-grid,
  .backlog-layout,
  .principle-grid {
    grid-template-columns: 1fr;
  }
}
</style>
