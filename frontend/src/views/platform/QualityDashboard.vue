<template>
  <div class="quality-dashboard">
    <section class="hero-panel">
      <div>
        <span class="eyebrow">Quality Dashboard</span>
        <h1>质量看板</h1>
        <p>
          轻量汇总 APP 自动化和 AI 探索的执行结果、失败率、疑似问题和耗时趋势。
          第一版只做最近任务的趋势视图，先服务汇报和复盘。
        </p>
      </div>
      <div class="hero-actions">
        <el-button type="primary" @click="navigate('/platform/backlog')"
          >查看质量待办</el-button
        >
        <el-button plain :loading="loading" @click="loadDashboard"
          >刷新数据</el-button
        >
      </div>
    </section>

    <section class="kpi-grid">
      <article v-for="item in kpis" :key="item.label" class="kpi-card">
        <span>{{ item.label }}</span>
        <strong>{{ item.value }}</strong>
        <p>{{ item.desc }}</p>
      </article>
    </section>

    <el-alert
      v-if="loadErrors.length"
      class="load-alert"
      type="warning"
      show-icon
      :closable="false"
      title="部分看板数据加载失败"
    >
      <template #default>{{ loadErrors.join("；") }}</template>
    </el-alert>

    <section class="dashboard-grid">
      <article class="panel trend-panel">
        <div class="section-title">近期待办与问题趋势</div>
        <div class="trend-list">
          <div v-for="item in trendRows" :key="item.date" class="trend-row">
            <span class="trend-date">{{ item.date }}</span>
            <div class="trend-bars">
              <span
                class="bar app"
                :style="{
                  width: `${barWidth(item.appFailures, maxTrendValue)}%`,
                }"
              />
              <span
                class="bar ai"
                :style="{ width: `${barWidth(item.aiIssues, maxTrendValue)}%` }"
              />
            </div>
            <small
              >失败 {{ item.appFailures }} / 疑似 {{ item.aiIssues }}</small
            >
          </div>
        </div>
        <div class="legend">
          <span><i class="legend-dot app" />APP 失败</span>
          <span><i class="legend-dot ai" />AI 疑似问题</span>
        </div>
      </article>

      <article class="panel">
        <div class="section-title">质量分布</div>
        <div class="distribution-list">
          <div
            v-for="item in distribution"
            :key="item.label"
            class="distribution-item"
          >
            <div>
              <strong>{{ item.label }}</strong>
              <span>{{ item.desc }}</span>
            </div>
            <el-tag :type="item.type">{{ item.value }}</el-tag>
          </div>
        </div>
      </article>
    </section>

    <section class="panel">
      <div class="list-toolbar">
        <div>
          <div class="section-title">近期风险样本</div>
          <p>优先展示失败、异常、疑似问题和等待/执行中的任务。</p>
        </div>
        <el-input
          v-model="keyword"
          clearable
          placeholder="搜索名称 / 来源 / 状态"
          style="width: 260px"
        />
      </div>
      <el-table
        v-loading="loading"
        :data="filteredRisks"
        border
        empty-text="暂无风险样本"
      >
        <el-table-column label="对象" min-width="260" show-overflow-tooltip>
          <template #default="{ row }">
            <div class="risk-name">
              <span>{{ row.name }}</span>
              <el-tag size="small" :type="row.tagType" effect="plain">{{
                row.sourceName
              }}</el-tag>
            </div>
          </template>
        </el-table-column>
        <el-table-column label="状态" width="120">
          <template #default="{ row }">
            <el-tag :type="row.statusType" size="small">{{
              row.statusText
            }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="失败/问题" width="110">
          <template #default="{ row }">{{ row.issueCount }}</template>
        </el-table-column>
        <el-table-column label="最近时间" width="170">
          <template #default="{ row }">{{
            formatDate(row.updatedAt)
          }}</template>
        </el-table-column>
        <el-table-column label="操作" width="180" fixed="right">
          <template #default="{ row }">
            <el-button link type="primary" @click="goBacklog(row)"
              >待办</el-button
            >
            <el-button link type="primary" @click="navigate(row.route)"
              >来源</el-button
            >
          </template>
        </el-table-column>
      </el-table>
    </section>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from "vue";
import { useRouter } from "vue-router";
import api from "@/utils/api";

const router = useRouter();
const loading = ref(false);
const keyword = ref("");
const loadErrors = ref([]);
const appExecutions = ref([]);
const explorationTasks = ref([]);

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

const loadDashboard = async () => {
  loading.value = true;
  loadErrors.value = [];
  const requests = [
    api.get("/app-automation/executions/", {
      params: { page: 1, page_size: 80 },
    }),
    api.get("/app-automation/exploration-tasks/", {
      params: { page: 1, page_size: 80 },
    }),
  ];
  const results = await Promise.allSettled(requests);
  if (results[0].status === "fulfilled") {
    appExecutions.value = normalizeList(results[0].value);
  } else {
    loadErrors.value.push(
      `APP 执行：${results[0].reason?.userMessage || results[0].reason?.message || "加载失败"}`,
    );
  }
  if (results[1].status === "fulfilled") {
    explorationTasks.value = normalizeList(results[1].value);
  } else {
    loadErrors.value.push(
      `AI 探索：${results[1].reason?.userMessage || results[1].reason?.message || "加载失败"}`,
    );
  }
  loading.value = false;
};

const appFailedCount = computed(
  () =>
    appExecutions.value.filter((item) => {
      const status = normalizeStatus(item.result || item.status);
      return (
        ["failed", "error", "stopped"].includes(status) ||
        Number(item.failed_steps || 0) > 0
      );
    }).length,
);

const appPassedCount = computed(
  () =>
    appExecutions.value.filter((item) => {
      const status = normalizeStatus(item.result || item.status);
      return (
        ["passed", "success", "completed"].includes(status) &&
        Number(item.failed_steps || 0) <= 0
      );
    }).length,
);

const aiIssueCount = computed(() =>
  explorationTasks.value.reduce(
    (sum, item) => sum + Number(item.issue_count || 0),
    0,
  ),
);
const runningCount = computed(
  () =>
    [...appExecutions.value, ...explorationTasks.value].filter((item) =>
      ["running", "pending"].includes(
        normalizeStatus(item.result || item.status),
      ),
    ).length,
);

const kpis = computed(() => {
  const appTotal = appExecutions.value.length;
  const passRate = appTotal
    ? Math.round((appPassedCount.value / appTotal) * 100)
    : 0;
  return [
    { label: "APP 执行总数", value: appTotal, desc: "最近执行记录样本" },
    {
      label: "APP 通过率",
      value: `${passRate}%`,
      desc: `${appPassedCount.value} 通过 / ${appFailedCount.value} 失败`,
    },
    {
      label: "AI 疑似问题",
      value: aiIssueCount.value,
      desc: "探索任务累计疑似问题",
    },
    {
      label: "等待/执行中",
      value: runningCount.value,
      desc: "需要继续关注的任务",
    },
  ];
});

const trendRows = computed(() => {
  const bucket = new Map();
  const ensure = (date) => {
    if (!bucket.has(date))
      bucket.set(date, { date, appFailures: 0, aiIssues: 0 });
    return bucket.get(date);
  };
  appExecutions.value.forEach((item) => {
    const date = formatDay(pickDate(item));
    if (!date) return;
    const failed =
      ["failed", "error", "stopped"].includes(
        normalizeStatus(item.result || item.status),
      ) || Number(item.failed_steps || 0) > 0;
    if (failed) ensure(date).appFailures += 1;
  });
  explorationTasks.value.forEach((item) => {
    const date = formatDay(pickDate(item));
    if (!date) return;
    ensure(date).aiIssues += Number(item.issue_count || 0);
  });
  return Array.from(bucket.values())
    .sort((a, b) => a.date.localeCompare(b.date))
    .slice(-7);
});

const maxTrendValue = computed(() =>
  Math.max(
    1,
    ...trendRows.value.flatMap((item) => [item.appFailures, item.aiIssues]),
  ),
);

const distribution = computed(() => [
  {
    label: "执行失败",
    desc: "需要进入报告和证据排查",
    value: appFailedCount.value,
    type: appFailedCount.value ? "danger" : "success",
  },
  {
    label: "探索疑似问题",
    desc: "需要人工复核有效性",
    value: aiIssueCount.value,
    type: aiIssueCount.value ? "warning" : "success",
  },
  {
    label: "运行中/等待中",
    desc: "需要确认是否卡住",
    value: runningCount.value,
    type: runningCount.value ? "warning" : "info",
  },
  {
    label: "执行通过",
    desc: "可作为稳定样本参考",
    value: appPassedCount.value,
    type: "success",
  },
]);

const riskRows = computed(() => {
  const appRows = appExecutions.value
    .map((item, index) => {
      const status = normalizeStatus(item.result || item.status);
      const issueCount = Number(item.failed_steps || 0);
      const risky =
        ["failed", "error", "stopped", "running", "pending"].includes(status) ||
        issueCount > 0;
      if (!risky) return null;
      return {
        id: `app-${item.id || index}`,
        source: "app_execution",
        sourceName: "APP 执行",
        tagType: "primary",
        name:
          item.case_name ||
          item.test_case_name ||
          item.name ||
          `APP 执行 #${item.id || index + 1}`,
        statusText: statusLabel(status),
        statusType: statusType(status, issueCount),
        issueCount,
        updatedAt: pickDate(item),
        route: "/app-automation/executions",
      };
    })
    .filter(Boolean);

  const aiRows = explorationTasks.value
    .map((item, index) => {
      const status = normalizeStatus(item.result || item.status);
      const issueCount = Number(item.issue_count || 0);
      const risky =
        ["running", "pending", "failed", "error"].includes(status) ||
        issueCount > 0;
      if (!risky) return null;
      return {
        id: `ai-${item.id || index}`,
        source: "ai_exploration",
        sourceName: "AI 探索",
        tagType: "success",
        name: item.name || item.objective || `AI 探索 #${item.id || index + 1}`,
        statusText: statusLabel(status),
        statusType: issueCount > 0 ? "warning" : statusType(status, issueCount),
        issueCount,
        updatedAt: pickDate(item),
        route: "/app-automation/exploration",
      };
    })
    .filter(Boolean);

  return [...appRows, ...aiRows]
    .sort((a, b) => new Date(b.updatedAt || 0) - new Date(a.updatedAt || 0))
    .slice(0, 12);
});

const filteredRisks = computed(() => {
  const text = keyword.value.trim().toLowerCase();
  if (!text) return riskRows.value;
  return riskRows.value.filter((item) =>
    [item.name, item.sourceName, item.statusText].some((value) =>
      String(value || "")
        .toLowerCase()
        .includes(text),
    ),
  );
});

const statusLabel = (status) => {
  if (["passed", "success", "completed"].includes(status)) return "通过";
  if (status === "failed") return "失败";
  if (status === "error") return "异常";
  if (status === "running") return "执行中";
  if (status === "pending") return "等待中";
  if (status === "stopped") return "已停止";
  return status || "未标记";
};

const statusType = (status, issueCount) => {
  if (["failed", "error", "stopped"].includes(status) || issueCount > 0)
    return "danger";
  if (["running", "pending"].includes(status)) return "warning";
  if (["passed", "success", "completed"].includes(status)) return "success";
  return "info";
};

const barWidth = (value, max) =>
  Math.max(value > 0 ? 8 : 0, Math.round((value / max) * 100));

const formatDay = (value) => {
  if (!value) return "";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return String(value).slice(0, 10);
  return date.toISOString().slice(0, 10);
};

const formatDate = (value) => {
  if (!value) return "-";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return String(value).slice(0, 19);
  return date.toLocaleString("zh-CN", { hour12: false });
};

const navigate = (path) => router.push(path);

const goBacklog = (row) => {
  router.push({
    path: "/platform/backlog",
    query: {
      q: row.name,
      filter: row.source === "ai_exploration" ? "suspicious" : "failure",
    },
  });
};

onMounted(loadDashboard);
</script>

<style scoped lang="scss">
.quality-dashboard {
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
      rgba(250, 204, 21, 0.24),
      transparent 30%
    ),
    linear-gradient(135deg, #172033 0%, #1e3a5f 48%, #854d0e 100%);
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
.list-toolbar {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
}

.kpi-grid,
.dashboard-grid {
  display: grid;
  gap: 14px;
}

.kpi-grid {
  grid-template-columns: repeat(4, minmax(0, 1fr));
}

.dashboard-grid {
  grid-template-columns: minmax(0, 1.2fr) minmax(320px, 0.8fr);
}

.kpi-card,
.panel {
  border-radius: 20px;
  background: #fff;
  border: 1px solid #e8eef5;
  box-shadow: 0 10px 30px rgba(17, 42, 70, 0.06);
}

.kpi-card {
  padding: 18px;
}

.kpi-card span {
  color: #64748b;
  font-size: 13px;
}

.kpi-card strong {
  display: block;
  margin-top: 10px;
  color: #122033;
  font-size: 30px;
}

.kpi-card p {
  margin: 6px 0 0;
  color: #64748b;
}

.panel {
  padding: 18px;
}

.section-title {
  margin-bottom: 14px;
  color: #172033;
  font-size: 18px;
  font-weight: 700;
}

.load-alert {
  margin-bottom: 14px;
}

.trend-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.trend-row {
  display: grid;
  grid-template-columns: 94px minmax(0, 1fr) 120px;
  gap: 10px;
  align-items: center;
}

.trend-date,
.trend-row small {
  color: #64748b;
}

.trend-bars {
  height: 22px;
  border-radius: 999px;
  background: #f1f5f9;
  overflow: hidden;
  display: flex;
}

.bar.app {
  background: #ef4444;
}
.bar.ai {
  background: #f59e0b;
}

.legend {
  margin-top: 14px;
  display: flex;
  gap: 16px;
  color: #64748b;
}

.legend-dot {
  width: 10px;
  height: 10px;
  display: inline-block;
  border-radius: 50%;
  margin-right: 6px;
}

.legend-dot.app {
  background: #ef4444;
}
.legend-dot.ai {
  background: #f59e0b;
}

.distribution-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.distribution-item {
  padding: 14px;
  border-radius: 16px;
  background: #f8fbff;
  border: 1px solid #e8eef5;
  display: flex;
  justify-content: space-between;
  gap: 12px;
}

.distribution-item strong,
.distribution-item span {
  display: block;
}

.distribution-item span {
  margin-top: 4px;
  color: #64748b;
}

.list-toolbar {
  align-items: flex-start;
  justify-content: space-between;
  margin-bottom: 14px;
}

.list-toolbar p {
  margin: 0;
  color: #64748b;
}

.risk-name {
  display: flex;
  align-items: center;
  gap: 8px;
}

@media (max-width: 1080px) {
  .kpi-grid,
  .dashboard-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

@media (max-width: 760px) {
  .hero-panel,
  .kpi-grid,
  .dashboard-grid,
  .trend-row {
    grid-template-columns: 1fr;
  }

  .hero-panel,
  .list-toolbar {
    flex-direction: column;
    align-items: stretch;
  }
}
</style>
