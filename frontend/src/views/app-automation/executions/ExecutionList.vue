<template>
  <div class="execution-list">
    <!-- 工具栏 -->
    <el-card class="toolbar" shadow="never">
      <el-row :gutter="20">
        <el-col :span="4">
          <el-select
            v-model="projectFilter"
            placeholder="全部项目"
            clearable
            filterable
            @change="loadExecutions"
          >
            <el-option
              v-for="p in projectList"
              :key="p.id"
              :label="p.name"
              :value="p.id"
            />
          </el-select>
        </el-col>
        <el-col :span="8">
          <el-input
            v-model="searchQuery"
            placeholder="搜索用例名称、设备"
            clearable
            @clear="loadExecutions"
            @keyup.enter="loadExecutions"
          >
            <template #prefix>
              <el-icon><Search /></el-icon>
            </template>
          </el-input>
        </el-col>
        <el-col :span="12" class="text-right">
          <el-select
            v-model="statusFilter"
            placeholder="状态筛选"
            clearable
            style="width: 150px; margin-right: 10px"
            @change="loadExecutions"
          >
            <el-option label="全部" value="" />
            <el-option label="等待中" value="pending" />
            <el-option label="执行中" value="running" />
            <el-option label="已完成" value="completed" />
            <el-option label="执行异常" value="error" />
            <el-option label="已停止" value="stopped" />
          </el-select>
          <el-button @click="loadExecutions">
            <el-icon><Refresh /></el-icon>
            刷新
          </el-button>
        </el-col>
      </el-row>
    </el-card>

    <!-- 执行记录列表 -->
    <el-card class="table-card" shadow="never">
      <el-table
        v-loading="loading"
        :data="executions"
        stripe
        style="width: 100%"
      >
        <el-table-column prop="case_name" label="测试用例" min-width="180" />
        <el-table-column prop="device_name" label="设备" width="150" />
        <el-table-column label="状态" width="100">
          <template #default="{ row }">
            <el-tag
              :type="getDisplayStatus(row.status, row.result).type"
              size="small"
            >
              {{ getDisplayStatus(row.status, row.result).text }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="进度" width="150">
          <template #default="{ row }">
            <el-progress
              :percentage="row.progress || 0"
              :status="
                row.status === 'error'
                  ? 'exception'
                  : row.result === 'failed'
                    ? 'exception'
                    : row.result === 'passed'
                      ? 'success'
                      : undefined
              "
            />
          </template>
        </el-table-column>
        <el-table-column label="步骤统计" width="180">
          <template #default="{ row }">
            <div class="step-stats">
              <span class="stat-item success"
                >通过: {{ row.passed_steps || 0 }}</span
              >
              <span class="stat-item danger"
                >失败: {{ row.failed_steps || 0 }}</span
              >
              <span class="stat-item">总数: {{ row.total_steps || 0 }}</span>
            </div>
          </template>
        </el-table-column>
        <el-table-column label="耗时" width="100">
          <template #default="{ row }">
            {{ formatDuration(row.duration) }}
          </template>
        </el-table-column>
        <el-table-column prop="user_name" label="执行人" width="100" />
        <el-table-column label="开始时间" width="160">
          <template #default="{ row }">
            {{ formatDateTime(row.started_at) }}
          </template>
        </el-table-column>
        <el-table-column label="结束时间" width="160">
          <template #default="{ row }">
            {{ row.finished_at ? formatDateTime(row.finished_at) : "-" }}
          </template>
        </el-table-column>
        <el-table-column label="操作" width="220" fixed="right">
          <template #default="{ row }">
            <el-button
              v-if="row.status === 'running'"
              type="warning"
              size="small"
              text
              @click="stopExecution(row)"
            >
              停止
            </el-button>
            <el-button
              type="primary"
              size="small"
              text
              @click="viewReport(row)"
            >
              标准报告
            </el-button>
            <el-button
              v-if="row.report_path"
              type="success"
              size="small"
              text
              @click="viewAllureReport(row)"
            >
              Allure
            </el-button>
            <el-button
              v-if="hasPerformance(row)"
              type="success"
              size="small"
              text
              @click="viewPerformance(row)"
            >
              性能
            </el-button>
            <el-button
              v-if="row.error_message"
              type="danger"
              size="small"
              text
              @click="viewError(row)"
            >
              查看错误
            </el-button>
          </template>
        </el-table-column>
      </el-table>

      <!-- 分页 -->
      <div class="pagination">
        <el-pagination
          v-model:current-page="currentPage"
          v-model:page-size="pageSize"
          :total="total"
          :page-sizes="[10, 20, 50, 100]"
          layout="total, sizes, prev, pager, next, jumper"
          @size-change="loadExecutions"
          @current-change="loadExecutions"
        />
      </div>
    </el-card>

    <!-- 错误信息对话框 -->
    <el-dialog v-model="errorDialogVisible" title="错误信息" width="600px">
      <div class="error-content">
        <pre>{{ currentError }}</pre>
      </div>
      <template #footer>
        <el-button type="primary" @click="errorDialogVisible = false">
          关闭
        </el-button>
      </template>
    </el-dialog>

    <el-dialog
      v-model="performanceDialogVisible"
      title="手机性能指标"
      width="760px"
    >
      <div
        v-if="currentPerformance && currentPerformance.enabled"
        class="performance-content"
      >
        <el-descriptions :column="2" border size="small">
          <el-descriptions-item label="设备">{{
            currentPerformance.device_id || "-"
          }}</el-descriptions-item>
          <el-descriptions-item label="包名">{{
            currentPerformance.package_name || "-"
          }}</el-descriptions-item>
          <el-descriptions-item label="采样次数">{{
            currentPerformance.sample_count || 0
          }}</el-descriptions-item>
          <el-descriptions-item label="采样间隔"
            >{{
              currentPerformance.sample_interval || "-"
            }}s</el-descriptions-item
          >
          <el-descriptions-item label="CPU 平均/峰值">
            {{ formatPerfStat(currentPerformance.cpu, "%") }}
          </el-descriptions-item>
          <el-descriptions-item label="内存 PSS 平均/峰值">
            {{ formatPerfStat(currentPerformance.memory_pss_mb, "MB") }}
          </el-descriptions-item>
          <el-descriptions-item label="电池温度峰值">
            {{
              formatPerfValue(
                currentPerformance.battery_temperature_c?.max,
                "℃",
              )
            }}
          </el-descriptions-item>
          <el-descriptions-item label="电量">
            {{ formatPerfStat(currentPerformance.battery_level, "%") }}
          </el-descriptions-item>
        </el-descriptions>

        <div
          v-if="currentPerformance.errors && currentPerformance.errors.length"
          class="performance-errors"
        >
          采样提示：{{ currentPerformance.errors.join("；") }}
        </div>

        <el-table
          v-if="performanceSamplesPreview.length"
          :data="performanceSamplesPreview"
          size="small"
          max-height="260"
          class="performance-samples"
        >
          <el-table-column prop="timestamp" label="时间" min-width="180" />
          <el-table-column label="CPU">
            <template #default="{ row }">{{
              formatPerfValue(row.cpu_percent, "%")
            }}</template>
          </el-table-column>
          <el-table-column label="内存">
            <template #default="{ row }">{{
              formatPerfValue(row.memory_pss_mb, "MB")
            }}</template>
          </el-table-column>
          <el-table-column label="温度">
            <template #default="{ row }">{{
              formatPerfValue(row.battery_temperature_c, "℃")
            }}</template>
          </el-table-column>
          <el-table-column label="电量">
            <template #default="{ row }">{{
              formatPerfValue(row.battery_level, "%")
            }}</template>
          </el-table-column>
        </el-table>
      </div>
      <el-empty v-else description="暂无性能数据" />
      <template #footer>
        <el-button type="primary" @click="performanceDialogVisible = false">
          关闭
        </el-button>
      </template>
    </el-dialog>

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
import { ElMessage, ElMessageBox } from "element-plus";
import {
  getExecutionList,
  stopExecution as apiStopExecution,
  getAppProjects,
  getExecutionReportSummary,
} from "@/api/app-automation";
import { Search, Refresh } from "@element-plus/icons-vue";
import StandardExecutionReportDialog from "../reports/components/StandardExecutionReportDialog.vue";
import {
  getDisplayStatus,
  formatDateTime,
} from "@/utils/app-automation-helpers";

const loading = ref(false);
const executions = ref([]);
const searchQuery = ref("");
const statusFilter = ref("");
const projectFilter = ref(null);
const projectList = ref([]);
const currentPage = ref(1);
const pageSize = ref(20);
const total = ref(0);

const errorDialogVisible = ref(false);
const currentError = ref("");
const performanceDialogVisible = ref(false);
const currentPerformance = ref({});
const performanceSamplesPreview = ref([]);
const reportDialogVisible = ref(false);
const reportSummaryLoading = ref(false);
const currentReportSummary = ref(null);
const currentReportExecution = ref(null);

let refreshTimer = null;

const loadExecutions = async () => {
  loading.value = true;
  try {
    const params = {
      page: currentPage.value,
      page_size: pageSize.value,
      search: searchQuery.value,
      status: statusFilter.value,
    };
    if (projectFilter.value) params.project = projectFilter.value;
    const res = await getExecutionList(params);
    executions.value = res.data.results || [];
    total.value = res.data.count || 0;
  } catch (error) {
    ElMessage.error("加载执行记录失败: " + (error.message || "未知错误"));
  } finally {
    loading.value = false;
  }
};

const stopExecution = async (execution) => {
  try {
    await ElMessageBox.confirm("确定要停止该执行吗？", "确认停止", {
      confirmButtonText: "确定",
      cancelButtonText: "取消",
      type: "warning",
    });

    const res = await apiStopExecution(execution.id);
    if (res.data.success) {
      ElMessage.success("已停止执行");
      loadExecutions();
    }
  } catch (error) {
    if (error !== "cancel") {
      ElMessage.error("停止失败: " + (error.message || "未知错误"));
    }
  }
};

const viewReport = async (execution) => {
  if (!execution || !execution.id) {
    ElMessage.warning("执行记录ID无效");
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
    ElMessage.error(
      `标准报告加载失败: ${error.response?.data?.msg || error.message}`,
    );
  } finally {
    reportSummaryLoading.value = false;
  }
};

const viewAllureReport = (execution) => {
  if (!execution?.report_path) {
    ElMessage.info("Allure 报告路径不存在");
    return;
  }
  window.open(
    `/api/app-automation/executions/${execution.id}/report/`,
    "_blank",
  );
};

const viewError = (execution) => {
  currentError.value = execution.error_message;
  errorDialogVisible.value = true;
};

const hasPerformance = (execution) => {
  return !!(
    execution &&
    execution.performance_metrics &&
    execution.performance_metrics.enabled
  );
};

const viewPerformance = (execution) => {
  currentPerformance.value = execution.performance_metrics || {};
  performanceSamplesPreview.value = (currentPerformance.value.samples || [])
    .slice(-20)
    .reverse();
  performanceDialogVisible.value = true;
};

const formatPerfValue = (value, unit = "") => {
  if (value === null || value === undefined || value === "") return "-";
  const number = Number(value);
  if (!Number.isFinite(number)) return `${value}${unit}`;
  return `${Math.round(number * 100) / 100}${unit}`;
};

const formatPerfStat = (stat, unit = "") => {
  if (!stat) return "-";
  return `${formatPerfValue(stat.avg, unit)} / ${formatPerfValue(stat.max, unit)}`;
};

// getDisplayStatus 已从 helpers 导入

const formatDuration = (seconds) => {
  if (!seconds) return "-";
  if (seconds < 60) return `${Math.floor(seconds)}秒`;
  const minutes = Math.floor(seconds / 60);
  const secs = Math.floor(seconds % 60);
  return `${minutes}分${secs}秒`;
};

// 自动刷新执行中的记录
const startAutoRefresh = () => {
  refreshTimer = setInterval(() => {
    // 如果有执行中的记录，自动刷新
    const hasRunning = executions.value.some((e) =>
      ["running", "pending"].includes(e.status),
    );
    if (hasRunning) {
      loadExecutions();
    }
  }, 5000); // 每5秒刷新一次
};

const stopAutoRefresh = () => {
  if (refreshTimer) {
    clearInterval(refreshTimer);
    refreshTimer = null;
  }
};

onMounted(() => {
  getAppProjects({ page_size: 100 })
    .then((res) => {
      projectList.value = res.data.results || res.data || [];
    })
    .catch(() => {});
  loadExecutions();
  startAutoRefresh();
});

onUnmounted(() => {
  stopAutoRefresh();
});
</script>

<style scoped lang="scss">
.execution-list {
  padding: 20px;
}

.toolbar {
  margin-bottom: 20px;

  .text-right {
    text-align: right;
  }
}

.table-card {
  .pagination {
    margin-top: 20px;
    display: flex;
    justify-content: flex-end;
  }
}

.step-stats {
  display: flex;
  gap: 8px;
  font-size: 12px;

  .stat-item {
    &.success {
      color: #67c23a;
    }
    &.danger {
      color: #f56c6c;
    }
  }
}

.error-content {
  max-height: 400px;
  overflow-y: auto;

  pre {
    background: #f5f7fa;
    padding: 15px;
    border-radius: 4px;
    font-family: "Courier New", Courier, monospace;
    font-size: 13px;
    line-height: 1.5;
    white-space: pre-wrap;
    word-wrap: break-word;
  }
}

.performance-content {
  .performance-errors {
    margin-top: 12px;
    color: #e6a23c;
    font-size: 12px;
    line-height: 1.6;
  }

  .performance-samples {
    margin-top: 14px;
  }
}
</style>
