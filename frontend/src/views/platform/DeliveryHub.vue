<template>
  <div class="delivery-hub">
    <section class="hero-panel">
      <div>
        <span class="eyebrow">Delivery Hub</span>
        <h1>通知与交付出口</h1>
        <p>
          把执行报告、AI 探索报告、日志、证据和后续企微通知收敛到一个出口。
          第一版先组织可复制的交付材料，后续再接机器人和缺陷系统。
        </p>
      </div>
      <div class="hero-actions">
        <el-button
          type="primary"
          @click="navigate('/platform/quality-dashboard')"
          >查看质量看板</el-button
        >
        <el-button plain :loading="loading" @click="loadDeliverables"
          >刷新材料</el-button
        >
      </div>
    </section>

    <section class="channel-grid">
      <article v-for="item in channels" :key="item.title" class="channel-card">
        <el-tag :type="item.type" effect="light">{{ item.status }}</el-tag>
        <h2>{{ item.title }}</h2>
        <p>{{ item.desc }}</p>
        <el-button link type="primary" @click="navigate(item.route)">{{
          item.action
        }}</el-button>
      </article>
    </section>

    <section class="delivery-layout">
      <main class="panel">
        <div class="list-toolbar">
          <div>
            <div class="section-title">近期可交付材料</div>
            <p>
              用于复制给开发、领导或后续企微机器人。当前先生成摘要，链接仍回到平台内。
            </p>
          </div>
          <el-input
            v-model="keyword"
            clearable
            placeholder="搜索任务 / 来源 / 结论"
            style="width: 260px"
          />
        </div>

        <el-alert
          v-if="loadErrors.length"
          class="load-alert"
          type="warning"
          show-icon
          :closable="false"
          title="部分交付材料加载失败"
        >
          <template #default>{{ loadErrors.join("；") }}</template>
        </el-alert>

        <el-table
          v-loading="loading"
          :data="filteredDeliverables"
          border
          empty-text="暂无可交付材料"
        >
          <el-table-column
            label="材料对象"
            min-width="260"
            show-overflow-tooltip
          >
            <template #default="{ row }">
              <div class="deliverable-name">
                <span>{{ row.name }}</span>
                <el-tag size="small" :type="row.tagType" effect="plain">{{
                  row.sourceName
                }}</el-tag>
              </div>
            </template>
          </el-table-column>
          <el-table-column label="结论" width="120">
            <template #default="{ row }">
              <el-tag :type="row.statusType" size="small">{{
                row.statusText
              }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column
            label="交付建议"
            min-width="220"
            show-overflow-tooltip
          >
            <template #default="{ row }">{{ row.suggestion }}</template>
          </el-table-column>
          <el-table-column label="最近时间" width="170">
            <template #default="{ row }">{{
              formatDate(row.updatedAt)
            }}</template>
          </el-table-column>
          <el-table-column label="操作" width="220" fixed="right">
            <template #default="{ row }">
              <el-button link type="primary" @click="copySummary(row)"
                >复制摘要</el-button
              >
              <el-button link type="primary" @click="navigate(row.route)"
                >打开来源</el-button
              >
            </template>
          </el-table-column>
        </el-table>
      </main>

      <aside class="panel template-panel">
        <div class="section-title">推荐通知模板</div>
        <div v-for="item in templates" :key="item.title" class="template-card">
          <strong>{{ item.title }}</strong>
          <p>{{ item.desc }}</p>
          <pre>{{ item.template }}</pre>
        </div>
      </aside>
    </section>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from "vue";
import { useRouter } from "vue-router";
import { ElMessage } from "element-plus";
import api from "@/utils/api";

const router = useRouter();
const loading = ref(false);
const keyword = ref("");
const loadErrors = ref([]);
const deliverables = ref([]);

const channels = [
  {
    title: "企微机器人",
    status: "下一步接入",
    type: "warning",
    desc: "承接执行完成、失败、AI 探索报告通知。",
    action: "先看通知配置",
    route: "/configuration/scheduled-task",
  },
  {
    title: "报告分享",
    status: "已具备入口",
    type: "success",
    desc: "统一从执行、证据、质量看板进入报告材料。",
    action: "查看证据中心",
    route: "/platform/evidence",
  },
  {
    title: "缺陷提交材料",
    status: "待增强",
    type: "info",
    desc: "先复制摘要，后续再转缺陷草稿并附带日志。",
    action: "查看质量待办",
    route: "/platform/backlog",
  },
  {
    title: "领导汇报",
    status: "轻量可用",
    type: "primary",
    desc: "基于质量看板生成趋势和结论材料。",
    action: "查看质量看板",
    route: "/platform/quality-dashboard",
  },
];

const templates = [
  {
    title: "失败通知",
    desc: "适合发给开发排查。",
    template:
      "【QAFlow 自动化失败】\n对象：{name}\n结论：{status}\n建议：请查看报告、截图和 logcat 进行归因。",
  },
  {
    title: "AI 探索复核",
    desc: "适合发给测试或产品确认。",
    template:
      "【QAFlow AI 探索待复核】\n对象：{name}\n疑似问题：{issueCount}\n建议：确认有效问题、误报或转回归用例。",
  },
  {
    title: "质量日报摘要",
    desc: "适合给负责人同步进展。",
    template:
      "【QAFlow 质量摘要】\n今日执行：{total}\n失败/疑似：{issueCount}\n待处理：请查看质量待办中心。",
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

const loadDeliverables = async () => {
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
    next.push(...normalizeList(results[0].value).map(toExecutionDeliverable));
  } else {
    loadErrors.value.push(
      `APP 执行：${results[0].reason?.userMessage || results[0].reason?.message || "加载失败"}`,
    );
  }
  if (results[1].status === "fulfilled") {
    next.push(...normalizeList(results[1].value).map(toExplorationDeliverable));
  } else {
    loadErrors.value.push(
      `AI 探索：${results[1].reason?.userMessage || results[1].reason?.message || "加载失败"}`,
    );
  }

  deliverables.value = next.sort(
    (a, b) => new Date(b.updatedAt || 0) - new Date(a.updatedAt || 0),
  );
  loading.value = false;
};

const toExecutionDeliverable = (item, index) => {
  const status = normalizeStatus(item.result || item.status);
  const failedSteps = Number(item.failed_steps || 0);
  const failed =
    ["failed", "error", "stopped"].includes(status) || failedSteps > 0;
  return {
    id: `execution-${item.id || index}`,
    sourceName: "APP 执行",
    tagType: "primary",
    name:
      item.case_name ||
      item.test_case_name ||
      item.name ||
      `APP 执行 #${item.id || index + 1}`,
    statusText: statusLabel(status),
    statusType: failed ? "danger" : statusType(status),
    issueCount: failedSteps,
    suggestion: failed
      ? "建议提交开发排查，附报告、截图和 logcat"
      : "可作为本轮通过记录归档",
    updatedAt: pickDate(item),
    route: "/app-automation/executions",
  };
};

const toExplorationDeliverable = (item, index) => {
  const status = normalizeStatus(item.result || item.status);
  const issueCount = Number(item.issue_count || 0);
  return {
    id: `exploration-${item.id || index}`,
    sourceName: "AI 探索",
    tagType: "success",
    name: item.name || item.objective || `AI 探索 #${item.id || index + 1}`,
    statusText: statusLabel(status),
    statusType: issueCount > 0 ? "warning" : statusType(status),
    issueCount,
    suggestion:
      issueCount > 0 ? "建议人工复核后决定转缺陷或转用例" : "可归档为探索记录",
    updatedAt: pickDate(item),
    route: "/app-automation/exploration",
  };
};

const filteredDeliverables = computed(() => {
  const text = keyword.value.trim().toLowerCase();
  if (!text) return deliverables.value;
  return deliverables.value.filter((item) =>
    [item.name, item.sourceName, item.statusText, item.suggestion].some(
      (value) =>
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

const statusType = (status) => {
  if (["failed", "error", "stopped"].includes(status)) return "danger";
  if (["running", "pending"].includes(status)) return "warning";
  if (["passed", "success", "completed"].includes(status)) return "success";
  return "info";
};

const copySummary = async (row) => {
  const text = [
    `【QAFlow 交付摘要】`,
    `对象：${row.name}`,
    `来源：${row.sourceName}`,
    `结论：${row.statusText}`,
    `失败/疑似问题：${row.issueCount}`,
    `建议：${row.suggestion}`,
    `入口：${window.location.origin}${row.route}`,
  ].join("\n");
  try {
    await navigator.clipboard.writeText(text);
    ElMessage.success("交付摘要已复制");
  } catch {
    ElMessage.warning("复制失败，请手动复制页面内容");
  }
};

const formatDate = (value) => {
  if (!value) return "-";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return String(value).slice(0, 19);
  return date.toLocaleString("zh-CN", { hour12: false });
};

const navigate = (path) => router.push(path);

onMounted(loadDeliverables);
</script>

<style scoped lang="scss">
.delivery-hub {
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
      rgba(129, 140, 248, 0.25),
      transparent 30%
    ),
    linear-gradient(135deg, #111827 0%, #312e81 48%, #4338ca 100%);
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
.list-toolbar {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
}

.channel-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 14px;
}

.channel-card,
.panel {
  border-radius: 20px;
  background: #fff;
  border: 1px solid #e8eef5;
  box-shadow: 0 10px 30px rgba(17, 42, 70, 0.06);
}

.channel-card {
  padding: 18px;
}

.channel-card h2 {
  margin: 14px 0 8px;
  color: #172033;
  font-size: 18px;
}

.channel-card p {
  margin: 0 0 12px;
  color: #64748b;
  line-height: 1.6;
}

.delivery-layout {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 340px;
  gap: 18px;
}

.panel {
  padding: 18px;
}

.section-title {
  margin-bottom: 8px;
  color: #172033;
  font-size: 18px;
  font-weight: 700;
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

.load-alert {
  margin-bottom: 14px;
}

.deliverable-name {
  display: flex;
  align-items: center;
  gap: 8px;
}

.template-panel {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.template-card {
  padding: 14px;
  border-radius: 16px;
  background: #f8fbff;
  border: 1px solid #e8eef5;
}

.template-card strong {
  color: #172033;
}

.template-card p {
  margin: 6px 0;
  color: #64748b;
  line-height: 1.5;
}

.template-card pre {
  margin: 8px 0 0;
  padding: 10px;
  white-space: pre-wrap;
  border-radius: 12px;
  background: #eef2ff;
  color: #312e81;
  font-family: inherit;
  line-height: 1.5;
}

@media (max-width: 1180px) {
  .channel-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .delivery-layout {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 760px) {
  .hero-panel,
  .channel-grid {
    grid-template-columns: 1fr;
  }

  .hero-panel,
  .list-toolbar {
    flex-direction: column;
    align-items: stretch;
  }
}
</style>
