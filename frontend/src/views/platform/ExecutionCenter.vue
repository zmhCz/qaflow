<template>
  <div class="execution-center">
    <section class="hero-panel">
      <div>
        <span class="eyebrow">Execution Center</span>
        <h1>统一执行中心</h1>
        <p>
          先把 APP 自动化执行和 AI
          探索任务聚合到同一个视图，统一查看等待中、执行中、失败和已完成状态。
          这一版只做视图层收口，不迁移底层任务表。
        </p>
      </div>
      <div class="hero-actions">
        <el-button
          type="primary"
          @click="navigate('/app-automation/test-cases')"
          >发起 APP 执行</el-button
        >
        <el-button plain @click="navigate('/app-automation/exploration')"
          >发起 AI 探索</el-button
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

    <section class="execution-layout">
      <aside class="filter-panel">
        <div class="section-title">任务筛选</div>
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

      <main class="execution-list-panel">
        <div class="list-toolbar">
          <div>
            <h2>统一执行视图</h2>
            <p>
              聚合最近的 APP 执行记录和 AI
              探索任务，先解决“任务到底跑到哪了”的问题。
            </p>
          </div>
          <div class="toolbar-actions">
            <el-input
              v-model="keyword"
              clearable
              placeholder="搜索任务 / 设备 / 状态 / 来源"
              style="width: 260px"
            />
            <el-switch
              v-model="autoRefresh"
              active-text="自动刷新"
              inactive-text="手动"
            />
            <el-button :loading="loading" @click="loadExecutions"
              >刷新</el-button
            >
          </div>
        </div>

        <el-alert
          v-if="runningCount > 0"
          class="load-alert"
          type="info"
          show-icon
          :closable="false"
          :title="`当前有 ${runningCount} 个任务仍在执行或等待，已开启轻量轮询时会自动更新状态`"
        />

        <el-alert
          v-if="loadErrors.length"
          class="load-alert"
          type="warning"
          show-icon
          :closable="false"
          title="部分任务来源加载失败"
        >
          <template #default>{{ loadErrors.join("；") }}</template>
        </el-alert>

        <el-table
          v-loading="loading"
          :data="filteredExecutions"
          border
          empty-text="暂无执行任务"
        >
          <el-table-column
            label="任务名称"
            min-width="250"
            show-overflow-tooltip
          >
            <template #default="{ row }">
              <div class="execution-name">
                <span>{{ row.name }}</span>
                <el-tag size="small" :type="row.tagType" effect="plain">{{
                  row.sourceName
                }}</el-tag>
              </div>
            </template>
          </el-table-column>
          <el-table-column label="状态" width="120">
            <template #default="{ row }">
              <el-tag :type="statusType(row)" size="small">{{
                row.statusText
              }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column label="进度" min-width="180">
            <template #default="{ row }">
              <div class="progress-cell">
                <el-progress :percentage="row.progress" :stroke-width="8" />
                <small>{{ row.stage }}</small>
              </div>
            </template>
          </el-table-column>
          <el-table-column label="失败/问题" width="110">
            <template #default="{ row }">
              <span :class="{ danger: row.issueCount > 0 }">{{
                row.issueCount
              }}</span>
            </template>
          </el-table-column>
          <el-table-column
            label="设备/范围"
            min-width="160"
            show-overflow-tooltip
          >
            <template #default="{ row }">{{
              row.device || row.scope || "-"
            }}</template>
          </el-table-column>
          <el-table-column label="耗时" width="110">
            <template #default="{ row }">{{
              formatDuration(row.duration)
            }}</template>
          </el-table-column>
          <el-table-column label="最近时间" width="170">
            <template #default="{ row }">{{
              formatDate(row.updatedAt)
            }}</template>
          </el-table-column>
          <el-table-column label="操作" width="220" fixed="right">
            <template #default="{ row }">
              <el-button link type="primary" @click="goEvidence(row)"
                >证据</el-button
              >
              <el-button link type="primary" @click="navigate(row.route)"
                >打开来源</el-button
              >
              <el-button
                v-if="row.reportUrl"
                link
                type="primary"
                @click="openReport(row)"
                >报告</el-button
              >
            </template>
          </el-table-column>
        </el-table>
      </main>
    </section>

    <section class="principle-panel">
      <div class="section-title">统一执行中心第一版边界</div>
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
import { computed, onBeforeUnmount, onMounted, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import api from "@/utils/api";

const router = useRouter();
const route = useRoute();
const loading = ref(false);
const keyword = ref("");
const activeFilter = ref("all");
const autoRefresh = ref(true);
const executionItems = ref([]);
const loadErrors = ref([]);
let refreshTimer = null;

const principles = [
  {
    title: "先统一入口",
    desc: "第一版只聚合任务状态和跳转入口，不改 APP 执行和 AI 探索各自的数据结构。",
  },
  {
    title: "先服务排查",
    desc: "优先让用户知道任务是否还在跑、是否失败、失败后去哪里看报告和证据。",
  },
  {
    title: "保留来源",
    desc: "每条任务都能回到原始模块，避免统一视图变成新的信息孤岛。",
  },
  {
    title: "后续再建模",
    desc: "稳定后再抽象 ExecutionJob，逐步接入 API 自动化、Web UI 自动化和调度任务。",
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

const normalizeProgress = (item) => {
  const raw = Number(item.progress);
  if (Number.isFinite(raw)) return Math.max(0, Math.min(100, Math.round(raw)));
  const status = normalizeStatus(item.result || item.status);
  if (["passed", "success", "completed"].includes(status)) return 100;
  if (["failed", "error", "stopped"].includes(status)) return 100;
  if (status === "running") return 1;
  return 0;
};

const pickDate = (item) =>
  item.finished_at ||
  item.updated_at ||
  item.started_at ||
  item.created_at ||
  "";

const toAppExecution = (item, index) => {
  const status = item.result || item.status || "";
  const failedSteps = Number(item.failed_steps || 0);
  return {
    id: `app-execution-${item.id || index}`,
    source: "app_execution",
    sourceName: "APP 执行",
    tagType: "primary",
    name:
      item.case_name ||
      item.test_case_name ||
      item.name ||
      `APP 执行 #${item.id || index + 1}`,
    status,
    statusText: statusText(status),
    progress: normalizeProgress(item),
    stage:
      item.current_step_name ||
      item.current_step ||
      item.message ||
      stageText(status),
    issueCount: failedSteps,
    device: item.device_name || item.device || "",
    scope: item.project_name || item.suite_name || "",
    duration: item.duration,
    updatedAt: pickDate(item),
    route: "/app-automation/executions",
    reportUrl: item.id
      ? `/api/app-automation/executions/${item.id}/report/`
      : "",
  };
};

const toExplorationTask = (item, index) => {
  const status = item.result || item.status || "";
  const issueCount = Number(item.issue_count || 0);
  const totalSteps = Number(item.total_steps || 0);
  const exploredPages = Number(item.explored_pages || 0);
  return {
    id: `ai-exploration-${item.id || index}`,
    source: "ai_exploration",
    sourceName: "AI 探索",
    tagType: "success",
    name: item.name || item.objective || `AI 探索 #${item.id || index + 1}`,
    status,
    statusText: statusText(status),
    progress: normalizeProgress(item),
    stage: item.current_action || `${totalSteps} 步 / ${exploredPages} 页`,
    issueCount,
    device: item.device_name || item.device || "",
    scope: item.package_name || item.objective || "",
    duration: item.duration,
    updatedAt: pickDate(item),
    route: "/app-automation/exploration",
    reportUrl: "",
  };
};

const loadExecutions = async () => {
  loading.value = true;
  loadErrors.value = [];
  const requests = [
    api.get("/app-automation/executions/", {
      params: { page: 1, page_size: 20 },
    }),
    api.get("/app-automation/exploration-tasks/", {
      params: { page: 1, page_size: 20 },
    }),
  ];
  const results = await Promise.allSettled(requests);
  const next = [];

  if (results[0].status === "fulfilled") {
    next.push(...normalizeList(results[0].value).map(toAppExecution));
  } else {
    loadErrors.value.push(
      `APP 执行：${results[0].reason?.userMessage || results[0].reason?.message || "加载失败"}`,
    );
  }

  if (results[1].status === "fulfilled") {
    next.push(...normalizeList(results[1].value).map(toExplorationTask));
  } else {
    loadErrors.value.push(
      `AI 探索：${results[1].reason?.userMessage || results[1].reason?.message || "加载失败"}`,
    );
  }

  executionItems.value = next.sort(
    (a, b) => new Date(b.updatedAt || 0) - new Date(a.updatedAt || 0),
  );
  loading.value = false;
};

const runningCount = computed(
  () =>
    executionItems.value.filter((item) => isRunningLike(item.status)).length,
);

const summaryCards = computed(() => [
  {
    key: "all",
    label: "全部任务",
    value: executionItems.value.length,
    desc: "最近 APP 执行与 AI 探索",
  },
  {
    key: "running",
    label: "执行中",
    value: executionItems.value.filter(
      (item) => normalizeStatus(item.status) === "running",
    ).length,
    desc: "正在运行的任务",
  },
  {
    key: "pending",
    label: "等待中",
    value: executionItems.value.filter(
      (item) => normalizeStatus(item.status) === "pending",
    ).length,
    desc: "排队或尚未开始",
  },
  {
    key: "failed",
    label: "失败/异常",
    value: executionItems.value.filter(isFailedLike).length,
    desc: "需要排查的任务",
  },
  {
    key: "completed",
    label: "已完成",
    value: executionItems.value.filter(isCompletedLike).length,
    desc: "已产生结论的任务",
  },
]);

const filterOptions = computed(() =>
  summaryCards.value.map((item) => ({
    key: item.key,
    label: item.label,
    count: item.value,
  })),
);

const filteredExecutions = computed(() => {
  const text = keyword.value.trim().toLowerCase();
  return executionItems.value.filter((item) => {
    if (
      activeFilter.value === "running" &&
      normalizeStatus(item.status) !== "running"
    )
      return false;
    if (
      activeFilter.value === "pending" &&
      normalizeStatus(item.status) !== "pending"
    )
      return false;
    if (activeFilter.value === "failed" && !isFailedLike(item)) return false;
    if (activeFilter.value === "completed" && !isCompletedLike(item))
      return false;
    if (!text) return true;
    return [
      item.name,
      item.statusText,
      item.device,
      item.scope,
      item.sourceName,
      item.stage,
    ].some((value) =>
      String(value || "")
        .toLowerCase()
        .includes(text),
    );
  });
});

const startPolling = () => {
  stopPolling();
  if (!autoRefresh.value) return;
  refreshTimer = window.setInterval(() => {
    if (!loading.value) loadExecutions();
  }, 8000);
};

const stopPolling = () => {
  if (!refreshTimer) return;
  window.clearInterval(refreshTimer);
  refreshTimer = null;
};

const navigate = (path) => router.push(path);

const goEvidence = (row) => {
  router.push({
    path: "/platform/evidence",
    query: {
      q: row.name,
      filter: row.source === "ai_exploration" ? "exploration" : "execution",
    },
  });
};

const openReport = (row) => {
  if (row.reportUrl) window.open(row.reportUrl, "_blank");
};

const applyRouteQuery = () => {
  const queryKeyword = route.query.q;
  const queryFilter = route.query.filter;
  if (typeof queryKeyword === "string") keyword.value = queryKeyword;
  if (
    typeof queryFilter === "string" &&
    ["all", "running", "pending", "failed", "completed"].includes(queryFilter)
  ) {
    activeFilter.value = queryFilter;
  }
};

watch(autoRefresh, startPolling);
watch(
  () => route.query,
  () => {
    applyRouteQuery();
  },
  { immediate: true },
);

const isRunningLike = (status) =>
  ["running", "pending"].includes(normalizeStatus(status));

const isFailedLike = (row) => {
  const status = normalizeStatus(row.status);
  return ["failed", "error", "stopped"].includes(status) || row.issueCount > 0;
};

const isCompletedLike = (row) => {
  const status = normalizeStatus(row.status);
  return (
    ["passed", "success", "completed"].includes(status) && row.issueCount <= 0
  );
};

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

const stageText = (status) => {
  const text = normalizeStatus(status);
  if (text === "running") return "任务执行中";
  if (text === "pending") return "等待执行";
  if (["failed", "error"].includes(text)) return "执行结束，需排查";
  if (["passed", "success", "completed"].includes(text)) return "执行完成";
  return "暂无阶段信息";
};

const statusType = (row) => {
  const text = normalizeStatus(row.status);
  if (["passed", "success", "completed"].includes(text) && row.issueCount <= 0)
    return "success";
  if (["failed", "error", "stopped"].includes(text) || row.issueCount > 0)
    return "danger";
  if (["running", "pending"].includes(text)) return "warning";
  return "info";
};

const formatDate = (value) => {
  if (!value) return "-";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return String(value).slice(0, 19);
  return date.toLocaleString("zh-CN", { hour12: false });
};

const formatDuration = (value) => {
  const seconds = Number(value);
  if (!Number.isFinite(seconds) || seconds <= 0) return "-";
  if (seconds < 60) return `${Math.round(seconds)} 秒`;
  const minutes = Math.floor(seconds / 60);
  const remain = Math.round(seconds % 60);
  return `${minutes}分${remain}秒`;
};

onMounted(() => {
  loadExecutions();
  startPolling();
});

onBeforeUnmount(stopPolling);
</script>

<style scoped lang="scss">
.execution-center {
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
      rgba(96, 165, 250, 0.25),
      transparent 30%
    ),
    linear-gradient(135deg, #111827 0%, #1e3a5f 48%, #1d4ed8 100%);
  box-shadow: 0 20px 50px rgba(15, 23, 42, 0.16);
}

.hero-panel h1 {
  margin: 8px 0 12px;
  font-size: 32px;
}

.hero-panel p {
  max-width: 780px;
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
  grid-template-columns: repeat(5, minmax(0, 1fr));
  gap: 14px;
}

.summary-card,
.filter-panel,
.execution-list-panel,
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
  border-color: #93c5fd;
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

.execution-layout {
  display: grid;
  grid-template-columns: 220px minmax(0, 1fr);
  gap: 18px;
}

.filter-panel,
.execution-list-panel,
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
  background: #eff6ff;
  color: #1d4ed8;
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

.execution-name {
  display: flex;
  align-items: center;
  gap: 8px;
}

.progress-cell {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.progress-cell small {
  color: #64748b;
}

.danger {
  color: #dc2626;
  font-weight: 700;
}

.principle-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 14px;
}

.principle-card {
  padding: 16px;
  border-radius: 16px;
  background: #f8fbff;
  border: 1px solid #dbeafe;
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
  .summary-grid,
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
  .execution-layout,
  .principle-grid {
    grid-template-columns: 1fr;
  }
}
</style>
