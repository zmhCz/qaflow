<template>
  <div class="asset-center">
    <section class="hero-panel">
      <div>
        <span class="eyebrow">Test Asset Center</span>
        <h1>测试资产中心</h1>
        <p>
          先用视图层把手工用例、AI 生成、API、Web UI、APP 和 AI
          探索草稿收敛到一个入口， 后续再逐步统一底层 TestAsset 模型。
        </p>
      </div>
      <div class="hero-actions">
        <el-button
          type="primary"
          @click="navigate('/ai-generation/requirement-analysis')"
          >从需求生成用例</el-button
        >
        <el-button plain @click="navigate('/app-automation/exploration')"
          >AI 探索转草稿</el-button
        >
      </div>
    </section>

    <section class="summary-grid">
      <article
        v-for="item in assetSources"
        :key="item.key"
        class="summary-card"
        @click="selectSource(item.key)"
      >
        <div class="summary-top">
          <span class="source-dot" :class="item.tone" />
          <el-tag :type="item.statusType" effect="light">{{
            item.status
          }}</el-tag>
        </div>
        <strong>{{ item.count }}</strong>
        <h3>{{ item.title }}</h3>
        <p>{{ item.description }}</p>
      </article>
    </section>

    <section class="asset-layout">
      <aside class="source-panel">
        <div class="section-title">资产来源</div>
        <button
          v-for="item in sourceFilters"
          :key="item.key"
          class="source-filter"
          :class="{ active: activeSource === item.key }"
          @click="selectSource(item.key)"
        >
          <span>{{ item.title }}</span>
          <em>{{ item.count }}</em>
        </button>
      </aside>

      <main class="asset-list-panel">
        <div class="list-toolbar">
          <div>
            <h2>统一资产视图</h2>
            <p>当前是聚合展示，不改变原模块数据结构。</p>
          </div>
          <div class="toolbar-actions">
            <el-input
              v-model="keyword"
              clearable
              placeholder="搜索名称 / 项目 / 状态"
              style="width: 240px"
            />
            <el-button :loading="loading" @click="loadAssets">刷新</el-button>
          </div>
        </div>

        <el-alert
          v-if="loadErrors.length"
          class="load-alert"
          type="warning"
          show-icon
          :closable="false"
          title="部分资产来源加载失败"
        >
          <template #default>
            {{ loadErrors.join("；") }}
          </template>
        </el-alert>

        <el-table
          v-loading="loading"
          :data="filteredAssets"
          border
          class="asset-table"
          empty-text="暂无资产数据"
        >
          <el-table-column
            label="资产名称"
            min-width="240"
            show-overflow-tooltip
          >
            <template #default="{ row }">
              <div class="asset-name">
                <span>{{ row.name || "未命名资产" }}</span>
                <el-tag size="small" :type="row.tagType" effect="plain">{{
                  row.typeName
                }}</el-tag>
              </div>
            </template>
          </el-table-column>
          <el-table-column label="来源" width="140">
            <template #default="{ row }">{{ row.sourceName }}</template>
          </el-table-column>
          <el-table-column
            label="项目/范围"
            min-width="160"
            show-overflow-tooltip
          >
            <template #default="{ row }">{{ row.project || "-" }}</template>
          </el-table-column>
          <el-table-column label="状态" width="120">
            <template #default="{ row }">
              <el-tag size="small" :type="statusType(row.status)">{{
                statusText(row.status)
              }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column label="最近更新" width="170">
            <template #default="{ row }">{{
              formatDate(row.updatedAt)
            }}</template>
          </el-table-column>
          <el-table-column label="操作" width="210" fixed="right">
            <template #default="{ row }">
              <el-button link type="primary" @click="navigate(row.route)"
                >去维护</el-button
              >
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
      <div class="section-title">当前落地原则</div>
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
const activeSource = ref("all");
const assets = ref([]);
const loadErrors = ref([]);

const sourceMeta = {
  manual: {
    title: "手工用例",
    description: "正式沉淀的测试用例资产。",
    route: "/ai-generation/testcases",
    tagType: "success",
    tone: "tone-green",
    status: "正式资产",
    statusType: "success",
  },
  ai_generated: {
    title: "AI 生成草稿",
    description: "需求分析后生成的用例草稿和采纳记录。",
    route: "/ai-generation/generated-testcases",
    tagType: "primary",
    tone: "tone-blue",
    status: "待确认",
    statusType: "primary",
  },
  api: {
    title: "API 资产",
    description: "接口请求、集合和自动化套件。",
    route: "/api-testing/automation",
    tagType: "warning",
    tone: "tone-orange",
    status: "自动化",
    statusType: "warning",
  },
  web_ui: {
    title: "Web UI 用例",
    description: "Web UI 自动化用例和脚本资产。",
    route: "/ui-automation/test-cases",
    tagType: "info",
    tone: "tone-cyan",
    status: "自动化",
    statusType: "info",
  },
  app_ui: {
    title: "APP 用例",
    description: "APP 场景编排后沉淀的自动化用例。",
    route: "/app-automation/test-cases",
    tagType: "danger",
    tone: "tone-red",
    status: "自动化",
    statusType: "danger",
  },
  exploration: {
    title: "AI 探索草稿",
    description: "探索任务、AI 分析和可转用例草稿。",
    route: "/app-automation/exploration",
    tagType: "primary",
    tone: "tone-purple",
    status: "探索中",
    statusType: "primary",
  },
};

const principles = [
  { title: "先统一视图", desc: "当前只做聚合展示和入口收拢，不迁移底层表。" },
  {
    title: "保留来源关系",
    desc: "每条资产都要知道来自 AI、手工、API、Web UI、APP 还是探索。",
  },
  {
    title: "服务后续模型",
    desc: "等心智稳定后，再逐步抽象 TestAsset / ExecutionJob / Evidence。",
  },
  {
    title: "避免资产孤岛",
    desc: "新增能力必须回答资产沉淀、执行调度和证据回流到哪里。",
  },
];

const assetSources = computed(() =>
  Object.entries(sourceMeta).map(([key, meta]) => ({
    key,
    ...meta,
    count: assets.value.filter((item) => item.source === key).length,
  })),
);

const sourceFilters = computed(() => [
  { key: "all", title: "全部资产", count: assets.value.length },
  ...assetSources.value.map((item) => ({
    key: item.key,
    title: item.title,
    count: item.count,
  })),
]);

const filteredAssets = computed(() => {
  const text = keyword.value.trim().toLowerCase();
  return assets.value.filter((item) => {
    if (activeSource.value !== "all" && item.source !== activeSource.value)
      return false;
    if (!text) return true;
    return [
      item.name,
      item.project,
      item.status,
      item.sourceName,
      item.typeName,
    ].some((value) =>
      String(value || "")
        .toLowerCase()
        .includes(text),
    );
  });
});

const normalizeList = (response) => {
  const data = response?.data;
  if (Array.isArray(data)) return data;
  if (Array.isArray(data?.results)) return data.results;
  if (Array.isArray(data?.data)) return data.data;
  return [];
};

const pickName = (item, fallback) =>
  item.name ||
  item.title ||
  item.case_name ||
  item.test_case_name ||
  item.task_name ||
  item.requirement_title ||
  fallback;

const pickProject = (item) =>
  item.project_name ||
  item.project?.name ||
  item.project ||
  item.app_name ||
  item.package_name ||
  item.module ||
  "";

const pickDate = (item) =>
  item.updated_at ||
  item.update_time ||
  item.modified_at ||
  item.created_at ||
  item.create_time ||
  item.finished_at ||
  "";

const toAsset = (source, item, index) => {
  const meta = sourceMeta[source];
  return {
    id: `${source}-${item.id || item.task_id || index}`,
    rawId: item.id || item.task_id,
    source,
    sourceName: meta.title,
    typeName: meta.title,
    tagType: meta.tagType,
    route: meta.route,
    name: pickName(
      item,
      `${meta.title} #${item.id || item.task_id || index + 1}`,
    ),
    project: pickProject(item),
    status:
      item.status || item.state || item.result || item.review_status || "",
    updatedAt: pickDate(item),
  };
};

const requestSource = async (
  source,
  url,
  params = { page: 1, page_size: 8 },
) => {
  const response = await api.get(url, { params });
  return normalizeList(response)
    .slice(0, 8)
    .map((item, index) => toAsset(source, item, index));
};

const loadAssets = async () => {
  loading.value = true;
  loadErrors.value = [];

  const sources = [
    ["manual", "/testcases/"],
    ["ai_generated", "/requirement-analysis/testcase-generation/"],
    ["api", "/api-testing/test-suites/"],
    ["web_ui", "/ui-automation/test-cases/"],
    ["app_ui", "/app-automation/test-cases/"],
    ["exploration", "/app-automation/exploration-tasks/"],
  ];

  const results = await Promise.allSettled(
    sources.map(([source, url]) => requestSource(source, url)),
  );
  const nextAssets = [];
  results.forEach((result, index) => {
    const [source] = sources[index];
    if (result.status === "fulfilled") {
      nextAssets.push(...result.value);
      return;
    }
    loadErrors.value.push(
      `${sourceMeta[source].title}：${result.reason?.userMessage || result.reason?.message || "加载失败"}`,
    );
  });

  assets.value = nextAssets.sort(
    (a, b) => new Date(b.updatedAt || 0) - new Date(a.updatedAt || 0),
  );
  loading.value = false;
};

const selectSource = (source) => {
  activeSource.value = source;
};

const navigate = (path) => {
  router.push(path);
};

const goExecution = (row) => {
  router.push({
    path: "/platform/executions",
    query: {
      q: row.name,
      filter: "all",
    },
  });
};

const goEvidence = (row) => {
  router.push({
    path: "/platform/evidence",
    query: {
      q: row.name,
      filter: row.source === "exploration" ? "exploration" : "all",
    },
  });
};

const applyRouteQuery = () => {
  const queryKeyword = route.query.q;
  const querySource = route.query.source;
  if (typeof queryKeyword === "string") keyword.value = queryKeyword;
  if (
    typeof querySource === "string" &&
    sourceFilters.value.some((item) => item.key === querySource)
  ) {
    activeSource.value = querySource;
  }
};

const formatDate = (value) => {
  if (!value) return "-";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return String(value).slice(0, 19);
  return date.toLocaleString("zh-CN", { hour12: false });
};

const statusText = (status) => {
  const map = {
    completed: "已完成",
    pending: "等待中",
    running: "执行中",
    failed: "失败",
    error: "异常",
    success: "成功",
    active: "启用",
    draft: "草稿",
    approved: "已确认",
    rejected: "已驳回",
  };
  return map[status] || status || "未标记";
};

const statusType = (status) => {
  if (["completed", "success", "approved", "active"].includes(status))
    return "success";
  if (["running", "pending", "draft"].includes(status)) return "warning";
  if (["failed", "error", "rejected"].includes(status)) return "danger";
  return "info";
};

watch(
  () => route.query,
  () => {
    applyRouteQuery();
  },
  { immediate: true },
);

onMounted(loadAssets);
</script>

<style scoped lang="scss">
.asset-center {
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
      circle at top left,
      rgba(20, 184, 166, 0.28),
      transparent 30%
    ),
    linear-gradient(135deg, #102033 0%, #17395c 48%, #0f766e 100%);
  box-shadow: 0 20px 50px rgba(15, 23, 42, 0.16);
}

.hero-panel h1 {
  margin: 8px 0 12px;
  font-size: 32px;
}

.hero-panel p {
  max-width: 760px;
  margin: 0;
  color: rgba(248, 251, 255, 0.82);
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

.hero-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
}

.summary-grid {
  display: grid;
  grid-template-columns: repeat(6, minmax(0, 1fr));
  gap: 14px;
}

.summary-card,
.source-panel,
.asset-list-panel,
.principle-panel {
  border-radius: 20px;
  background: #fff;
  border: 1px solid #e8eef5;
  box-shadow: 0 10px 30px rgba(17, 42, 70, 0.06);
}

.summary-card {
  padding: 16px;
  cursor: pointer;
  transition:
    transform 0.2s ease,
    border-color 0.2s ease;
}

.summary-card:hover {
  transform: translateY(-3px);
  border-color: #a7d7cf;
}

.summary-top {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.source-dot {
  width: 12px;
  height: 12px;
  border-radius: 50%;
}

.tone-green {
  background: #10b981;
}
.tone-blue {
  background: #3b82f6;
}
.tone-orange {
  background: #f97316;
}
.tone-cyan {
  background: #06b6d4;
}
.tone-red {
  background: #ef4444;
}
.tone-purple {
  background: #8b5cf6;
}

.summary-card strong {
  display: block;
  margin-top: 16px;
  color: #122033;
  font-size: 30px;
}

.summary-card h3 {
  margin: 8px 0 6px;
  color: #172033;
}

.summary-card p {
  margin: 0;
  color: #64748b;
  line-height: 1.55;
  font-size: 13px;
}

.asset-layout {
  display: grid;
  grid-template-columns: 220px minmax(0, 1fr);
  gap: 18px;
}

.source-panel,
.asset-list-panel,
.principle-panel {
  padding: 18px;
}

.section-title {
  margin-bottom: 14px;
  color: #172033;
  font-size: 18px;
  font-weight: 700;
}

.source-filter {
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
  transition:
    background 0.2s ease,
    color 0.2s ease;
}

.source-filter.active,
.source-filter:hover {
  background: #eef8f6;
  color: #0f766e;
}

.source-filter em {
  font-style: normal;
  font-weight: 700;
}

.list-toolbar {
  display: flex;
  align-items: flex-start;
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

.toolbar-actions {
  display: flex;
  gap: 10px;
}

.load-alert {
  margin-bottom: 14px;
}

.asset-name {
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
  background: #f8fbff;
  border: 1px solid #e8eef5;
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
    grid-template-columns: repeat(3, minmax(0, 1fr));
  }
}

@media (max-width: 960px) {
  .hero-panel,
  .list-toolbar {
    flex-direction: column;
    align-items: stretch;
  }

  .asset-layout,
  .summary-grid,
  .principle-grid {
    grid-template-columns: 1fr;
  }

  .toolbar-actions {
    flex-direction: column;
  }
}
</style>
