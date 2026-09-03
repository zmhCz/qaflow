<template>
  <div class="app-automation-dashboard">
    <section class="hero-card">
      <div>
        <p class="eyebrow">APP 自动化中心</p>
        <h2>10 分钟跑通第一条 APP 自动化</h2>
        <p class="hero-desc">
          先不用理解所有功能名，按下面闭环完成：选项目、连设备、录元素、编排用例、执行、看报告。
          平台后续能力都围绕这条链路继续沉淀。
        </p>
      </div>
      <div class="hero-actions">
        <el-button
          type="primary"
          @click="$router.push('/app-automation/devices')"
          >检查设备</el-button
        >
        <el-button
          plain
          @click="$router.push('/app-automation/semantic-elements')"
          >维护语义库</el-button
        >
      </div>
    </section>

    <el-alert
      title="技术负责人建议：先追求一条稳定闭环，再扩展覆盖面。"
      type="info"
      :closable="false"
      class="starter-alert"
    >
      <template #default>
        新用户最容易卡在“下一步该做什么”。因此首页只保留闭环路径和关键状态，复杂能力放到二级页面。
      </template>
    </el-alert>

    <el-card shadow="never" class="starter-card">
      <template #header>
        <div class="card-header">
          <span>第一条自动化闭环</span>
          <el-button text type="primary" @click="loadStatistics"
            >刷新状态</el-button
          >
        </div>
      </template>
      <div class="starter-grid">
        <div
          v-for="step in starterSteps"
          :key="step.index"
          class="starter-step"
        >
          <div class="starter-step__index">{{ step.index }}</div>
          <div class="starter-step__body">
            <div class="starter-step__title">{{ step.title }}</div>
            <div class="starter-step__desc">{{ step.desc }}</div>
            <el-button link type="primary" @click="$router.push(step.path)">{{
              step.action
            }}</el-button>
          </div>
        </div>
      </div>
    </el-card>

    <div class="stats-section">
      <el-row :gutter="16">
        <el-col :xs="24" :sm="12" :lg="6">
          <el-card shadow="hover" class="stat-card">
            <div class="stat-content">
              <div class="stat-icon bg-blue">
                <el-icon><Cellphone /></el-icon>
              </div>
              <div class="stat-info">
                <div class="stat-value">{{ statistics.devices.total }}</div>
                <div class="stat-label">设备总数</div>
              </div>
            </div>
          </el-card>
        </el-col>
        <el-col :xs="24" :sm="12" :lg="6">
          <el-card shadow="hover" class="stat-card">
            <div class="stat-content">
              <div class="stat-icon bg-green">
                <el-icon><CircleCheck /></el-icon>
              </div>
              <div class="stat-info">
                <div class="stat-value">{{ statistics.devices.online }}</div>
                <div class="stat-label">在线设备</div>
              </div>
            </div>
          </el-card>
        </el-col>
        <el-col :xs="24" :sm="12" :lg="6">
          <el-card shadow="hover" class="stat-card">
            <div class="stat-content">
              <div class="stat-icon bg-orange">
                <el-icon><Lock /></el-icon>
              </div>
              <div class="stat-info">
                <div class="stat-value">{{ statistics.devices.locked }}</div>
                <div class="stat-label">已锁定设备</div>
              </div>
            </div>
          </el-card>
        </el-col>
        <el-col :xs="24" :sm="12" :lg="6">
          <el-card shadow="hover" class="stat-card">
            <div class="stat-content">
              <div class="stat-icon bg-purple">
                <el-icon><Document /></el-icon>
              </div>
              <div class="stat-info">
                <div class="stat-value">{{ statistics.test_cases.total }}</div>
                <div class="stat-label">测试用例</div>
              </div>
            </div>
          </el-card>
        </el-col>
      </el-row>
    </div>

    <el-row :gutter="16" class="content-section">
      <el-col :xs="24" :lg="12">
        <el-card class="stat-chart" shadow="never">
          <template #header>
            <div class="card-header">
              <span>执行概览</span>
            </div>
          </template>
          <div class="chart-container">
            <div class="stat-item">
              <div class="stat-label">总执行次数</div>
              <div class="stat-value large">
                {{ statistics.executions.total }}
              </div>
            </div>
            <div class="stat-item">
              <div class="stat-label">成功次数</div>
              <div class="stat-value success">
                {{ statistics.executions.success }}
              </div>
            </div>
            <div class="stat-item">
              <div class="stat-label">失败次数</div>
              <div class="stat-value danger">
                {{ statistics.executions.failed }}
              </div>
            </div>
            <div class="stat-item">
              <div class="stat-label">通过率</div>
              <div
                class="stat-value"
                :class="getPassRateClass(statistics.executions.pass_rate)"
              >
                {{ statistics.executions.pass_rate }}%
              </div>
            </div>
          </div>
        </el-card>
      </el-col>

      <el-col :xs="24" :lg="12">
        <el-card class="recent-executions" shadow="never">
          <template #header>
            <div class="card-header">
              <span>最近执行</span>
              <el-button
                type="primary"
                size="small"
                @click="$router.push('/app-automation/executions')"
              >
                查看全部
              </el-button>
            </div>
          </template>
          <div v-if="loading" class="loading-container">
            <el-empty description="加载中..." />
          </div>
          <div
            v-else-if="statistics.recent_executions.length === 0"
            class="empty-container"
          >
            <el-empty description="暂无执行记录" />
          </div>
          <div v-else class="executions-list">
            <div
              v-for="execution in statistics.recent_executions"
              :key="execution.id"
              class="execution-item"
            >
              <div class="execution-info">
                <div class="execution-name">
                  {{ execution.case_name || "未命名用例" }}
                </div>
                <div class="execution-meta">
                  <el-tag :type="getStatusType(execution.status)" size="small">
                    {{ getStatusText(execution.status) }}
                  </el-tag>
                  <span>设备：{{ execution.device_name || "-" }}</span>
                  <span>{{ formatTime(execution.created_at) }}</span>
                </div>
              </div>
              <div class="execution-actions">
                <el-button
                  type="primary"
                  size="small"
                  text
                  @click="viewExecution(execution)"
                >
                  标准报告
                </el-button>
                <el-button
                  v-if="execution.report_path"
                  type="success"
                  size="small"
                  text
                  @click="viewAllureReport(execution)"
                >
                  Allure
                </el-button>
              </div>
            </div>
          </div>
        </el-card>
      </el-col>
    </el-row>

    <el-card shadow="never" class="quick-actions-section">
      <template #header>
        <div class="card-header">
          <span>常用入口</span>
        </div>
      </template>
      <div class="actions-grid">
        <div
          v-for="item in quickActions"
          :key="item.path"
          class="action-item"
          @click="$router.push(item.path)"
        >
          <div class="action-icon" :class="item.color">
            <el-icon><component :is="item.icon" /></el-icon>
          </div>
          <div class="action-label">{{ item.label }}</div>
          <div class="action-desc">{{ item.desc }}</div>
        </div>
      </div>
    </el-card>

    <StandardExecutionReportDialog
      v-model="reportDialogVisible"
      :summary="currentReportSummary"
      :execution="currentReportExecution"
      :loading="reportSummaryLoading"
      @open-allure="viewAllureReport"
    />
  </div>
</template>

<script setup>
import { ref, onMounted, onUnmounted } from "vue";
import { ElMessage } from "element-plus";
import {
  getDashboardStatistics,
  getExecutionReportSummary,
} from "@/api/app-automation";
import {
  getExecutionStatusType,
  getExecutionStatusText,
  formatRelativeTime,
} from "@/utils/app-automation-helpers";
import StandardExecutionReportDialog from "../reports/components/StandardExecutionReportDialog.vue";
import {
  Aim,
  Cellphone,
  CircleCheck,
  Connection,
  Document,
  Lock,
  Picture,
} from "@element-plus/icons-vue";

const loading = ref(false);
const reportDialogVisible = ref(false);
const reportSummaryLoading = ref(false);
const currentReportSummary = ref(null);
const currentReportExecution = ref(null);

const statistics = ref({
  devices: { total: 0, online: 0, locked: 0, available: 0 },
  test_cases: { total: 0 },
  executions: { total: 0, success: 0, failed: 0, pass_rate: 0 },
  recent_executions: [],
});

const starterSteps = [
  {
    index: 1,
    title: "确认项目和包名",
    desc: "先把本次 APP、版本和测试范围挂到明确项目下，避免元素和用例后续混在一起。",
    path: "/app-automation/projects",
    action: "去项目管理",
  },
  {
    index: 2,
    title: "连接并检查设备",
    desc: "刷新设备列表，确认真机在线、可截图、可获取 UI 树，再开始维护元素。",
    path: "/app-automation/devices",
    action: "去设备管理",
  },
  {
    index: 3,
    title: "录入语义元素",
    desc: "通过截图框选核心控件，按页面、业务对象、控件角色生成规范名称。",
    path: "/app-automation/semantic-elements",
    action: "去语义库",
  },
  {
    index: 4,
    title: "编排第一条用例",
    desc: "建议先选登录、退出或首页断言这类最小闭环，跑通后再扩展复杂场景。",
    path: "/app-automation/scene-builder",
    action: "去用例编排",
  },
  {
    index: 5,
    title: "执行并观察结果",
    desc: "优先用单条用例验证设备、元素、变量和断言是否稳定。",
    path: "/app-automation/test-cases",
    action: "去测试用例",
  },
  {
    index: 6,
    title: "查看标准报告",
    desc: "失败时先看失败步骤、截图、logcat 和归因建议，再决定修脚本还是提缺陷。",
    path: "/app-automation/reports",
    action: "去报告列表",
  },
];

const quickActions = [
  {
    label: "设备管理",
    desc: "在线状态、锁定、健康检查",
    path: "/app-automation/devices",
    icon: Cellphone,
    color: "bg-blue",
  },
  {
    label: "语义元素库",
    desc: "维护可复用控件",
    path: "/app-automation/semantic-elements",
    icon: Picture,
    color: "bg-green",
  },
  {
    label: "页面采集台",
    desc: "从截图和 UI 树沉淀页面资产",
    path: "/app-automation/page-capture",
    icon: Connection,
    color: "bg-teal",
  },
  {
    label: "用例编排",
    desc: "拼装可执行业务流程",
    path: "/app-automation/scene-builder",
    icon: Document,
    color: "bg-purple",
  },
  {
    label: "执行记录",
    desc: "查看运行状态和失败记录",
    path: "/app-automation/executions",
    icon: Aim,
    color: "bg-orange",
  },
];

const loadStatistics = async () => {
  loading.value = true;
  try {
    const res = await getDashboardStatistics();
    if (res.data.success) {
      statistics.value = {
        ...statistics.value,
        ...res.data.data,
        recent_executions: res.data.data?.recent_executions || [],
      };
    }
  } catch (error) {
    ElMessage.error(
      error?.userMessage || "加载统计数据失败，请确认后端服务是否正常",
    );
  } finally {
    loading.value = false;
  }
};

const getStatusType = getExecutionStatusType;
const getStatusText = getExecutionStatusText;
const formatTime = formatRelativeTime;

const getPassRateClass = (rate) => {
  if (rate >= 90) return "success";
  if (rate >= 70) return "warning";
  return "danger";
};

const viewExecution = async (execution) => {
  if (!execution?.id) {
    ElMessage.warning("执行记录 ID 无效");
    return;
  }
  currentReportExecution.value = execution;
  currentReportSummary.value = null;
  reportDialogVisible.value = true;
  reportSummaryLoading.value = true;
  try {
    const res = await getExecutionReportSummary(execution.id);
    currentReportSummary.value = res.data?.data || null;
  } catch (error) {
    ElMessage.error(error?.userMessage || "标准报告加载失败");
  } finally {
    reportSummaryLoading.value = false;
  }
};

const viewAllureReport = (execution) => {
  if (!execution?.report_path) {
    ElMessage.info("当前执行暂无 Allure 报告");
    return;
  }
  window.open(
    `/api/app-automation/executions/${execution.id}/report/`,
    "_blank",
  );
};

let refreshTimer = null;

onMounted(() => {
  loadStatistics();
  refreshTimer = setInterval(loadStatistics, 30000);
});

onUnmounted(() => {
  if (refreshTimer) {
    clearInterval(refreshTimer);
    refreshTimer = null;
  }
});
</script>

<style scoped lang="scss">
.app-automation-dashboard {
  padding: 20px;
  background: #f6f8fb;
}

.hero-card {
  display: flex;
  justify-content: space-between;
  gap: 20px;
  padding: 26px;
  margin-bottom: 16px;
  border-radius: 22px;
  color: #17324d;
  background:
    radial-gradient(
      circle at top right,
      rgba(64, 158, 255, 0.2),
      transparent 34%
    ),
    linear-gradient(135deg, #f7fbff 0%, #edf7f2 100%);
  border: 1px solid #dfeaf5;
}

.eyebrow {
  margin: 0 0 8px;
  font-size: 13px;
  color: #3f7d6b;
  letter-spacing: 0.08em;
}

.hero-card h2 {
  margin: 0;
  font-size: 28px;
}

.hero-desc {
  max-width: 780px;
  margin: 10px 0 0;
  line-height: 1.7;
  color: #4b6072;
}

.hero-actions {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  white-space: nowrap;
}

.starter-alert,
.starter-card,
.stats-section,
.content-section {
  margin-bottom: 16px;
}

.starter-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 14px;
}

.starter-step {
  display: flex;
  gap: 14px;
  padding: 16px;
  border-radius: 16px;
  background: #fff;
  border: 1px solid #e7edf5;
}

.starter-step__index {
  width: 34px;
  height: 34px;
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 12px;
  color: #fff;
  font-weight: 700;
  background: linear-gradient(135deg, #409eff 0%, #2f54eb 100%);
}

.starter-step__title {
  margin-bottom: 6px;
  color: #1f2937;
  font-weight: 700;
}

.starter-step__desc {
  margin-bottom: 6px;
  color: #64748b;
  font-size: 13px;
  line-height: 1.7;
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-weight: 700;
}

.stat-card {
  cursor: pointer;
  transition:
    transform 0.2s ease,
    box-shadow 0.2s ease;

  &:hover {
    transform: translateY(-3px);
  }
}

.stat-content {
  display: flex;
  align-items: center;
  gap: 15px;
}

.stat-icon,
.action-icon {
  display: flex;
  align-items: center;
  justify-content: center;
  color: white;
}

.stat-icon {
  width: 58px;
  height: 58px;
  border-radius: 16px;
  font-size: 24px;
}

.stat-info {
  flex: 1;
}

.stat-value {
  margin-bottom: 8px;
  color: #1f2937;
  font-size: 28px;
  font-weight: 800;
  line-height: 1;
}

.stat-label {
  color: #64748b;
  font-size: 14px;
}

.bg-blue {
  background: linear-gradient(135deg, #4f8cff 0%, #2f54eb 100%);
}
.bg-green {
  background: linear-gradient(135deg, #33b679 0%, #0f9f6e 100%);
}
.bg-orange {
  background: linear-gradient(135deg, #fa8c16 0%, #f5222d 100%);
}
.bg-purple {
  background: linear-gradient(135deg, #7c3aed 0%, #2563eb 100%);
}
.bg-teal {
  background: linear-gradient(135deg, #13c2c2 0%, #08979c 100%);
}

.chart-container {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 14px;
}

.stat-item {
  padding: 16px;
  text-align: center;
  border-radius: 14px;
  background: #f8fafc;
  border: 1px solid #edf2f7;
}

.stat-value.large {
  color: #409eff;
  font-size: 32px;
}
.stat-value.success {
  color: #67c23a;
}
.stat-value.warning {
  color: #e6a23c;
}
.stat-value.danger {
  color: #f56c6c;
}

.execution-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
  padding: 12px;
  border-bottom: 1px solid #ebeef5;

  &:last-child {
    border-bottom: none;
  }

  &:hover {
    background: #f8fafc;
  }
}

.execution-info {
  min-width: 0;
  flex: 1;
}

.execution-name {
  margin-bottom: 8px;
  color: #1f2937;
  font-size: 14px;
  font-weight: 600;
}

.execution-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  align-items: center;
  color: #64748b;
  font-size: 12px;
}

.execution-actions {
  white-space: nowrap;
}

.actions-grid {
  display: grid;
  grid-template-columns: repeat(5, minmax(0, 1fr));
  gap: 14px;
}

.action-item {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
  min-height: 128px;
  padding: 18px;
  cursor: pointer;
  text-align: center;
  border-radius: 16px;
  background: #f8fafc;
  border: 1px solid #edf2f7;
  transition: all 0.2s ease;

  &:hover {
    transform: translateY(-3px);
    background: #ecf5ff;
    box-shadow: 0 10px 24px rgba(15, 23, 42, 0.08);
  }
}

.action-icon {
  width: 48px;
  height: 48px;
  border-radius: 14px;
  font-size: 22px;
}

.action-label {
  color: #1f2937;
  font-weight: 700;
}

.action-desc {
  color: #64748b;
  font-size: 12px;
  line-height: 1.5;
}

.loading-container,
.empty-container {
  padding: 36px 0;
}

@media (max-width: 1200px) {
  .hero-card {
    flex-direction: column;
  }

  .starter-grid,
  .actions-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

@media (max-width: 640px) {
  .starter-grid,
  .actions-grid,
  .chart-container {
    grid-template-columns: 1fr;
  }
}
</style>
