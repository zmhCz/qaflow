<template>
  <div class="evidence-center">
    <section class="hero-panel">
      <div>
        <span class="eyebrow">Evidence Center</span>
        <h1>测试证据中心</h1>
        <p>
          先聚合 APP 执行报告、AI 探索报告、Allure、logcat 和排障附件入口，
          让失败排查、缺陷提交和质量复盘有一个统一证据视图。
        </p>
      </div>
      <div class="hero-actions">
        <el-button type="primary" @click="navigate('/platform/executions')"
          >查看执行记录</el-button
        >
        <el-button plain @click="navigate('/app-automation/exploration')"
          >查看 AI 探索</el-button
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

    <section class="evidence-layout">
      <aside class="filter-panel">
        <div class="section-title">证据筛选</div>
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

      <main class="evidence-list-panel">
        <div class="list-toolbar">
          <div>
            <h2>统一证据视图</h2>
            <p>当前是视图层聚合，后续再沉淀统一 Evidence 模型。</p>
          </div>
          <div class="toolbar-actions">
            <el-input
              v-model="keyword"
              clearable
              placeholder="搜索任务 / 用例 / 设备 / 状态"
              style="width: 260px"
            />
            <el-button :loading="loading" @click="loadEvidence">刷新</el-button>
          </div>
        </div>

        <el-alert
          v-if="loadErrors.length"
          class="load-alert"
          type="warning"
          show-icon
          :closable="false"
          title="部分证据来源加载失败"
        >
          <template #default>{{ loadErrors.join("；") }}</template>
        </el-alert>

        <el-table
          v-loading="loading"
          :data="filteredEvidence"
          border
          empty-text="暂无证据数据"
        >
          <el-table-column
            label="证据对象"
            min-width="240"
            show-overflow-tooltip
          >
            <template #default="{ row }">
              <div class="evidence-name">
                <span>{{ row.name }}</span>
                <el-tag size="small" :type="row.tagType" effect="plain">{{
                  row.sourceName
                }}</el-tag>
              </div>
            </template>
          </el-table-column>
          <el-table-column label="结论/状态" width="130">
            <template #default="{ row }">
              <el-tag :type="statusType(row)" size="small">{{
                row.statusText
              }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column label="证据完整度" min-width="180">
            <template #default="{ row }">
              <div class="evidence-tags">
                <el-tag
                  v-for="tag in row.evidenceTags"
                  :key="tag.label"
                  :type="tag.type"
                  effect="plain"
                  size="small"
                >
                  {{ tag.label }}
                </el-tag>
              </div>
            </template>
          </el-table-column>
          <el-table-column label="问题/失败" width="110">
            <template #default="{ row }">{{ row.issueCount }}</template>
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
          <el-table-column label="操作" width="190" fixed="right">
            <template #default="{ row }">
              <el-button link type="primary" @click="goExecution(row)"
                >执行</el-button
              >
              <el-button link type="primary" @click="navigate(row.route)"
                >打开来源</el-button
              >
            </template>
          </el-table-column>
        </el-table>
      </main>
    </section>

    <section class="principle-panel">
      <div class="section-title">证据中心第一版边界</div>
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
const evidenceItems = ref([]);
const loadErrors = ref([]);

const principles = [
  {
    title: "先聚合入口",
    desc: "第一版先把报告、日志、截图和附件入口收在一起，不迁移文件存储。",
  },
  {
    title: "先服务排查",
    desc: "优先解决失败后找证据、导出日志、提交缺陷的效率问题。",
  },
  {
    title: "保留来源",
    desc: "证据必须能追溯到执行记录、AI 探索任务和原始报告。",
  },
  {
    title: "后续再建模",
    desc: "稳定后再抽象 Evidence，并挂接 TestAsset / ExecutionJob / 缺陷草稿。",
  },
];

const normalizeList = (response) => {
  const data = response?.data;
  if (Array.isArray(data)) return data;
  if (Array.isArray(data?.results)) return data.results;
  if (Array.isArray(data?.data)) return data.data;
  return [];
};

const toExecutionEvidence = (item, index) => {
  const failedSteps = Number(item.failed_steps || 0);
  const result = String(item.result || item.status || "");
  const hasAllure = Boolean(item.report_path);
  const hasPerformance = Boolean(
    item.performance_enabled || item.performance_summary?.enabled,
  );
  return {
    id: `execution-${item.id || index}`,
    source: "execution",
    sourceName: "APP 执行",
    tagType: "primary",
    name:
      item.case_name ||
      item.test_case_name ||
      item.name ||
      `执行记录 #${item.id || index + 1}`,
    status: result,
    statusText: statusText(result),
    issueCount: failedSteps,
    device: item.device_name || "",
    scope: item.project_name || "",
    updatedAt: item.finished_at || item.started_at || item.updated_at || "",
    route: "/app-automation/executions",
    evidenceTags: [
      {
        label: hasAllure ? "Allure" : "无 Allure",
        type: hasAllure ? "success" : "info",
      },
      {
        label: hasPerformance ? "性能数据" : "无性能数据",
        type: hasPerformance ? "success" : "info",
      },
      {
        label: failedSteps ? "含失败步骤" : "无失败步骤",
        type: failedSteps ? "danger" : "success",
      },
    ],
  };
};

const toExplorationEvidence = (item, index) => {
  const issueCount = Number(item.issue_count || 0);
  const hasLogcat = Boolean(
    item.logcat?.available || item.summary?.logcat?.available,
  );
  const hasAI = Boolean(
    item.summary?.ai_analysis || item.insights?.ai_analysis,
  );
  return {
    id: `exploration-${item.id || index}`,
    source: "exploration",
    sourceName: "AI 探索",
    tagType: "success",
    name: item.name || `探索任务 #${item.id || index + 1}`,
    status: item.result || item.status || "",
    statusText: statusText(item.result || item.status),
    issueCount,
    device: item.device_name || "",
    scope: item.objective || item.package_name || "",
    updatedAt: item.finished_at || item.updated_at || item.created_at || "",
    route: "/app-automation/exploration",
    evidenceTags: [
      {
        label: hasLogcat ? "logcat" : "无 logcat",
        type: hasLogcat ? "success" : "info",
      },
      {
        label: hasAI ? "AI 分析" : "无 AI 分析",
        type: hasAI ? "success" : "warning",
      },
      {
        label: issueCount ? "含疑似问题" : "无疑似问题",
        type: issueCount ? "danger" : "success",
      },
    ],
  };
};

const loadEvidence = async () => {
  loading.value = true;
  loadErrors.value = [];
  const requests = [
    api.get("/app-automation/executions/", {
      params: { page: 1, page_size: 12 },
    }),
    api.get("/app-automation/exploration-tasks/", {
      params: { page: 1, page_size: 12 },
    }),
  ];
  const results = await Promise.allSettled(requests);
  const next = [];
  if (results[0].status === "fulfilled") {
    next.push(...normalizeList(results[0].value).map(toExecutionEvidence));
  } else {
    loadErrors.value.push(
      `APP 执行：${results[0].reason?.userMessage || results[0].reason?.message || "加载失败"}`,
    );
  }
  if (results[1].status === "fulfilled") {
    next.push(...normalizeList(results[1].value).map(toExplorationEvidence));
  } else {
    loadErrors.value.push(
      `AI 探索：${results[1].reason?.userMessage || results[1].reason?.message || "加载失败"}`,
    );
  }
  evidenceItems.value = next.sort(
    (a, b) => new Date(b.updatedAt || 0) - new Date(a.updatedAt || 0),
  );
  loading.value = false;
};

const summaryCards = computed(() => [
  {
    key: "all",
    label: "全部证据",
    value: evidenceItems.value.length,
    desc: "执行与探索证据总量",
  },
  {
    key: "issue",
    label: "含问题证据",
    value: evidenceItems.value.filter((item) => item.issueCount > 0).length,
    desc: "失败步骤或疑似问题",
  },
  {
    key: "execution",
    label: "APP 执行",
    value: evidenceItems.value.filter((item) => item.source === "execution")
      .length,
    desc: "标准报告 / Allure / 附件",
  },
  {
    key: "exploration",
    label: "AI 探索",
    value: evidenceItems.value.filter((item) => item.source === "exploration")
      .length,
    desc: "截图证据 / logcat / AI 分析",
  },
]);

const filterOptions = computed(() =>
  summaryCards.value.map((item) => ({
    key: item.key,
    label: item.label,
    count: item.value,
  })),
);

const filteredEvidence = computed(() => {
  const text = keyword.value.trim().toLowerCase();
  return evidenceItems.value.filter((item) => {
    if (activeFilter.value === "issue" && item.issueCount <= 0) return false;
    if (
      ["execution", "exploration"].includes(activeFilter.value) &&
      item.source !== activeFilter.value
    )
      return false;
    if (!text) return true;
    return [
      item.name,
      item.statusText,
      item.device,
      item.scope,
      item.sourceName,
    ].some((value) =>
      String(value || "")
        .toLowerCase()
        .includes(text),
    );
  });
});

const navigate = (path) => router.push(path);

const goExecution = (row) => {
  router.push({
    path: "/platform/executions",
    query: {
      q: row.name,
      filter: row.issueCount > 0 ? "failed" : "all",
    },
  });
};

const applyRouteQuery = () => {
  const queryKeyword = route.query.q;
  const queryFilter = route.query.filter;
  if (typeof queryKeyword === "string") keyword.value = queryKeyword;
  if (
    typeof queryFilter === "string" &&
    ["all", "issue", "execution", "exploration"].includes(queryFilter)
  ) {
    activeFilter.value = queryFilter;
  }
};

const statusText = (status) => {
  const text = String(status || "").toLowerCase();
  if (["passed", "success", "completed"].includes(text)) return "通过";
  if (["failed", "error"].includes(text)) return "失败";
  if (text === "running") return "执行中";
  if (text === "pending") return "等待中";
  if (text === "stopped") return "已停止";
  return status || "未标记";
};

const statusType = (row) => {
  const text = String(row.status || "").toLowerCase();
  if (["passed", "success", "completed"].includes(text) && row.issueCount <= 0)
    return "success";
  if (["failed", "error"].includes(text) || row.issueCount > 0) return "danger";
  if (["running", "pending"].includes(text)) return "warning";
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

onMounted(loadEvidence);
</script>

<style scoped lang="scss">
.evidence-center {
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
      rgba(251, 191, 36, 0.24),
      transparent 30%
    ),
    linear-gradient(135deg, #172033 0%, #334155 48%, #92400e 100%);
  box-shadow: 0 20px 50px rgba(15, 23, 42, 0.16);
}

.hero-panel h1 {
  margin: 8px 0 12px;
  font-size: 32px;
}

.hero-panel p {
  max-width: 760px;
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
.toolbar-actions,
.evidence-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
}

.summary-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 14px;
}

.summary-card,
.filter-panel,
.evidence-list-panel,
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
  border-color: #f3c56b;
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

.evidence-layout {
  display: grid;
  grid-template-columns: 220px minmax(0, 1fr);
  gap: 18px;
}

.filter-panel,
.evidence-list-panel,
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
  background: #fff7ed;
  color: #b45309;
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

.evidence-name {
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
  background: #fffbeb;
  border: 1px solid #fde68a;
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
  .evidence-layout,
  .principle-grid {
    grid-template-columns: 1fr;
  }
}
</style>
