<template>
  <el-dialog
    :model-value="modelValue"
    title="QAFlow 标准执行报告"
    width="980px"
    destroy-on-close
    @opened="renderPerformanceChart"
    @closed="disposePerformanceChart"
    @update:model-value="emit('update:modelValue', $event)"
  >
    <div v-loading="loading" class="standard-report-dialog">
      <template v-if="summary">
        <section
          class="quality-decision-strip"
          :class="`decision-${qualityDecision.level}`"
        >
          <div class="decision-main">
            <span>质量决策</span>
            <strong>{{ qualityDecision.title }}</strong>
            <p>{{ qualityDecision.description }}</p>
          </div>
          <div class="decision-next">
            <span>建议下一步</span>
            <strong>{{ qualityDecision.nextAction }}</strong>
          </div>
          <div class="decision-metrics">
            <div
              v-for="item in qualityDecision.metrics"
              :key="item.label"
              class="decision-metric"
            >
              <span>{{ item.label }}</span>
              <strong>{{ item.value }}</strong>
            </div>
          </div>
        </section>

        <el-descriptions :column="2" border>
          <el-descriptions-item label="项目">{{
            summary.project_name || "-"
          }}</el-descriptions-item>
          <el-descriptions-item label="用例">{{
            summary.case_name || "-"
          }}</el-descriptions-item>
          <el-descriptions-item label="APP">{{
            summary.app_name || "-"
          }}</el-descriptions-item>
          <el-descriptions-item label="包名">{{
            summary.package_name || "-"
          }}</el-descriptions-item>
          <el-descriptions-item label="设备">{{
            summary.device_name || "-"
          }}</el-descriptions-item>
          <el-descriptions-item label="执行人">{{
            summary.executor || "-"
          }}</el-descriptions-item>
          <el-descriptions-item label="开始时间">{{
            summary.started_at || "-"
          }}</el-descriptions-item>
          <el-descriptions-item label="结束时间">{{
            summary.finished_at || "-"
          }}</el-descriptions-item>
        </el-descriptions>

        <div
          v-if="summary.diagnosis?.type"
          class="detail-section diagnosis-section"
        >
          <div class="section-title">
            <h4>失败诊断</h4>
            <el-tag
              :type="getSeverityTagType(summary.diagnosis.severity)"
              effect="plain"
            >
              {{ getSeverityText(summary.diagnosis.severity) }}
            </el-tag>
          </div>
          <el-descriptions :column="2" border size="small">
            <el-descriptions-item label="问题类型">{{
              summary.diagnosis.type
            }}</el-descriptions-item>
            <el-descriptions-item label="责任域">{{
              summary.diagnosis.owner || "-"
            }}</el-descriptions-item>
            <el-descriptions-item label="疑似失败步骤" :span="2">
              <template v-if="summary.diagnosis.probable_failed_step">
                第 {{ summary.diagnosis.probable_failed_step.index }} 步：
                {{ summary.diagnosis.probable_failed_step.name }}
                <el-tag size="small" effect="plain">{{
                  summary.diagnosis.probable_failed_step.type_text
                }}</el-tag>
              </template>
              <template v-else>-</template>
            </el-descriptions-item>
            <el-descriptions-item label="排查建议" :span="2">
              {{ summary.diagnosis.suggestion || "-" }}
            </el-descriptions-item>
          </el-descriptions>
          <div
            v-if="summary.diagnosis.actions?.length"
            class="diagnosis-actions"
          >
            <div
              v-for="(action, index) in summary.diagnosis.actions"
              :key="action"
              class="diagnosis-action"
            >
              <span>{{ index + 1 }}</span>
              {{ action }}
            </div>
          </div>
        </div>

        <div class="detail-section attachment-section">
          <div class="section-title">
            <h4>日志与排障附件</h4>
            <div class="section-tags">
              <el-tag
                :type="summary.artifacts?.available ? 'success' : 'info'"
                effect="plain"
              >
                {{ summary.artifacts?.available ? "有排障附件" : "暂无附件" }}
              </el-tag>
              <el-tag
                :type="summary.logcat?.available ? 'success' : 'info'"
                effect="plain"
              >
                {{
                  summary.logcat?.available ? "已采集 logcat" : "暂无 logcat"
                }}
              </el-tag>
            </div>
          </div>
          <div class="attachment-grid">
            <div class="attachment-card">
              <div>
                <strong>排障附件 ZIP</strong>
                <p>
                  包含 Allure 原始结果、执行附件、截图/XML/日志类文件和
                  manifest，适合提交缺陷或交给开发排查。
                </p>
                <span class="attachment-meta">
                  附件 {{ summary.artifacts?.counts?.total || 0 }} 个； 截图
                  {{ summary.artifacts?.counts?.screenshots || 0 }} 个； XML
                  {{ summary.artifacts?.counts?.xml || 0 }} 个
                </span>
              </div>
              <el-button
                type="primary"
                plain
                :disabled="!summary.artifacts?.available"
                @click="downloadEvidence"
              >
                导出排障附件
              </el-button>
            </div>
            <div class="attachment-card">
              <div>
                <strong>Android logcat</strong>
                <p>用于排查崩溃、ANR、闪退、白屏、系统弹窗等问题。</p>
                <span class="attachment-meta">
                  {{
                    summary.logcat?.available
                      ? `包含 ${summary.logcat.file_count || 0} 个日志文件`
                      : "当前执行记录没有采集到 logcat 文件"
                  }}
                </span>
              </div>
              <el-button
                type="primary"
                plain
                :disabled="!summary.logcat?.available"
                @click="downloadLogcat"
              >
                导出 logcat
              </el-button>
            </div>
          </div>
        </div>

        <div v-if="summary.step_outline?.items?.length" class="detail-section">
          <div class="section-title">
            <h4>步骤概览</h4>
            <el-tag
              v-if="summary.step_outline.source === 'allure'"
              type="success"
              effect="plain"
              >Allure 精确步骤</el-tag
            >
            <el-tag
              v-else-if="summary.step_outline.note"
              type="warning"
              effect="plain"
              >推断步骤</el-tag
            >
          </div>
          <el-alert
            v-if="summary.step_outline.note"
            :title="summary.step_outline.note"
            type="info"
            :closable="false"
            show-icon
            class="step-note"
          />
          <el-table
            :data="summary.step_outline.items"
            size="small"
            border
            max-height="300"
          >
            <el-table-column prop="index" label="#" width="60" />
            <el-table-column
              prop="name"
              label="步骤名称"
              min-width="220"
              show-overflow-tooltip
            />
            <el-table-column prop="type_text" label="动作" width="120" />
            <el-table-column label="耗时" width="100">
              <template #default="{ row }">
                {{
                  row.duration_ms !== null && row.duration_ms !== undefined
                    ? `${row.duration_ms}ms`
                    : "-"
                }}
              </template>
            </el-table-column>
            <el-table-column label="状态" width="110">
              <template #default="{ row }">
                <el-tag :type="getStepStatusTagType(row.status)" size="small">
                  {{ row.status_text }}
                </el-tag>
              </template>
            </el-table-column>
          </el-table>
        </div>

        <div
          v-if="visualEvidenceGroups.length"
          class="detail-section evidence-section"
        >
          <div class="section-title">
            <h4>关键截图证据</h4>
            <el-tag type="info" effect="plain">
              展示 {{ visualEvidenceGroups.length }} 组 / 共
              {{ summary.visual_evidence?.total || 0 }} 张
            </el-tag>
          </div>
          <el-alert
            v-if="summary.visual_evidence?.has_more"
            title="当前仅展示前 6 个关键步骤截图，完整截图可通过“导出排障附件”获取。"
            type="info"
            :closable="false"
            show-icon
            class="step-note"
          />
          <div class="evidence-grid">
            <div
              v-for="group in visualEvidenceGroups"
              :key="`${group.step_index}-${group.step_name}`"
              class="evidence-card"
            >
              <div class="evidence-card__title">
                <strong>{{
                  group.step_index ? `步骤 ${group.step_index}` : "执行截图"
                }}</strong>
                <span>{{ group.step_name }}</span>
              </div>
              <div class="evidence-images">
                <div
                  v-for="item in group.items"
                  :key="item.url"
                  class="evidence-image-item"
                >
                  <div class="evidence-image-label">
                    {{ getEvidencePhaseText(item.phase) }}
                  </div>
                  <el-image
                    class="evidence-image"
                    :src="item.url"
                    fit="cover"
                    :preview-src-list="allEvidenceImageUrls"
                    :initial-index="getEvidenceImageIndex(item.url)"
                    preview-teleported
                  />
                </div>
              </div>
            </div>
          </div>
        </div>

        <div v-if="summary.performance?.enabled" class="detail-section">
          <div class="section-title">
            <h4>性能趋势与分析</h4>
            <el-tag
              v-if="summary.performance.sample_count"
              type="info"
              effect="plain"
            >
              {{ summary.performance.sample_count }} 个采样点
            </el-tag>
          </div>
          <el-space wrap>
            <el-tag
              v-for="item in summary.performance.items || []"
              :key="item.label"
              type="info"
            >
              {{ item.label }}：{{ item.value }}{{ item.unit }}
            </el-tag>
            <el-tag
              v-for="warning in summary.performance.warnings || []"
              :key="warning"
              type="warning"
            >
              {{ warning }}
            </el-tag>
          </el-space>
          <div
            v-if="summary.performance.series?.length"
            ref="performanceChartRef"
            class="performance-chart"
          ></div>
          <el-empty v-else description="暂无性能趋势采样" :image-size="80" />
          <div class="performance-analysis">
            <el-alert
              v-for="item in summary.performance.analysis || []"
              :key="item"
              :title="item"
              :type="
                summary.performance.warnings?.length ? 'warning' : 'success'
              "
              show-icon
              :closable="false"
            />
          </div>
        </div>

        <div v-if="summary.failure?.message" class="detail-section">
          <h4>错误信息</h4>
          <el-alert
            :title="summary.failure.message"
            type="error"
            show-icon
            :closable="false"
          />
        </div>
      </template>

      <el-empty v-else-if="!loading" description="暂无报告摘要" />
    </div>

    <template #footer>
      <el-button
        :disabled="!summary?.artifacts?.available"
        @click="downloadEvidence"
        >导出排障附件</el-button
      >
      <el-button :disabled="!summary?.logcat?.available" @click="downloadLogcat"
        >导出 logcat</el-button
      >
      <el-button :disabled="!summary?.wecom_markdown" @click="copyWecomMarkdown"
        >复制企微摘要</el-button
      >
      <el-button
        v-if="execution?.report_path"
        type="success"
        @click="emit('open-allure', execution)"
        >打开 Allure</el-button
      >
      <el-button @click="emit('update:modelValue', false)">关闭</el-button>
    </template>
  </el-dialog>
</template>

<script setup>
import { computed, nextTick, onBeforeUnmount, ref, watch } from "vue";
import { ElMessage } from "element-plus";
import * as echarts from "echarts";

const props = defineProps({
  modelValue: {
    type: Boolean,
    default: false,
  },
  summary: {
    type: Object,
    default: null,
  },
  execution: {
    type: Object,
    default: null,
  },
  loading: {
    type: Boolean,
    default: false,
  },
});

const emit = defineEmits(["update:modelValue", "open-allure"]);

const performanceChartRef = ref(null);
let performanceChart = null;

const visualEvidenceGroups = computed(
  () => props.summary?.visual_evidence?.groups || [],
);
const allEvidenceImageUrls = computed(() => {
  return visualEvidenceGroups.value.flatMap((group) =>
    (group.items || []).map((item) => item.url).filter(Boolean),
  );
});
const evidenceImageIndexMap = computed(() => {
  return allEvidenceImageUrls.value.reduce((indexMap, url, index) => {
    if (!indexMap.has(url)) indexMap.set(url, index);
    return indexMap;
  }, new Map());
});

const qualityDecision = computed(() => {
  const summary = props.summary || {};
  const execution = props.execution || {};
  const level = summary.conclusion?.level || "";
  const result = String(execution.result || summary.result || "").toLowerCase();
  const status = String(execution.status || summary.status || "").toLowerCase();
  const failedSteps = Number(
    summary.steps?.failed || execution.failed_steps || 0,
  );
  const totalSteps = Number(summary.steps?.total || execution.total_steps || 0);
  const passRate = Number(summary.steps?.pass_rate || 0);
  const hasArtifacts = Boolean(summary.artifacts?.available);
  const hasLogcat = Boolean(summary.logcat?.available);
  const failureType = summary.failure?.type || summary.diagnosis?.type || "";

  let decisionLevel = "info";
  let title = summary.conclusion?.text || "暂无结论";
  let description =
    summary.conclusion?.suggestion ||
    "当前报告信息不足，建议结合执行步骤和附件判断。";
  let nextAction = "查看步骤与附件";

  if (["running", "pending"].includes(status)) {
    title = "执行未完成";
    description = "任务仍在执行或等待中，暂不建议作为质量结论依据。";
    nextAction = "等待执行完成";
  } else if (
    ["failed", "error"].includes(result) ||
    ["failed", "error"].includes(status) ||
    failedSteps > 0 ||
    level === "danger"
  ) {
    decisionLevel = "danger";
    title = "不建议发布";
    description = failureType
      ? `本次执行存在失败步骤，初步归因为「${failureType}」。`
      : "本次执行存在失败或异常，需要先完成排查。";
    nextAction = "先定位失败原因";
  } else if (passRate > 0 && passRate < 100) {
    decisionLevel = "warning";
    title = "暂缓结论";
    description = `当前通过率 ${passRate}%，仍存在未完全通过的步骤。`;
    nextAction = "复核失败/跳过步骤";
  } else if (!hasArtifacts && !hasLogcat) {
    decisionLevel = "warning";
    title = "可参考，但证据不足";
    description = "执行结果通过，但缺少排障附件和 logcat，后续追溯能力不足。";
    nextAction = "补充证据后沉淀";
  } else {
    decisionLevel = "success";
    title = "本轮执行通过";
    description = "当前执行未发现失败步骤，可作为本轮自动化通过参考。";
    nextAction = "沉淀为回归依据";
  }

  return {
    level: decisionLevel,
    title,
    description,
    nextAction,
    metrics: [
      { label: "通过率", value: `${passRate || 0}%` },
      {
        label: "执行项",
        value: `通过 ${summary.steps?.passed || 0} / 失败 ${failedSteps} / 共 ${totalSteps}`,
      },
      { label: "耗时", value: summary.duration_text || "-" },
      {
        label: "证据",
        value: hasLogcat ? "logcat" : hasArtifacts ? "附件" : "不足",
      },
    ],
  };
});

function getSeverityTagType(severity) {
  if (severity === "critical") return "danger";
  if (severity === "high") return "danger";
  if (severity === "medium") return "warning";
  return "info";
}

function getSeverityText(severity) {
  if (severity === "critical") return "严重";
  if (severity === "high") return "高";
  if (severity === "medium") return "中";
  if (severity === "low") return "低";
  return "提示";
}

function getStepStatusTagType(status) {
  if (status === "passed") return "success";
  if (status === "failed") return "danger";
  if (status === "unknown") return "warning";
  return "info";
}

function getEvidencePhaseText(phase) {
  if (phase === "before") return "操作前";
  if (phase === "after") return "操作后";
  if (phase === "error") return "失败现场";
  return "截图";
}

function getEvidenceImageIndex(url) {
  return evidenceImageIndexMap.value.get(url) || 0;
}

async function copyWecomMarkdown() {
  const text = props.summary?.wecom_markdown;
  if (!text) return ElMessage.warning("暂无可复制的企微摘要");
  try {
    await navigator.clipboard.writeText(text);
    ElMessage.success("企微摘要已复制");
  } catch {
    ElMessage.error("复制失败，请检查浏览器剪贴板权限");
  }
}

function downloadByUrl(url, emptyMessage) {
  if (!url) {
    ElMessage.warning(emptyMessage);
    return;
  }
  window.open(url, "_blank");
}

function downloadLogcat() {
  downloadByUrl(
    props.summary?.logcat?.download_url ||
      (props.execution?.id
        ? `/api/app-automation/executions/${props.execution.id}/download-logcat/`
        : ""),
    "该执行记录暂无可导出的 logcat",
  );
}

function downloadEvidence() {
  downloadByUrl(
    props.summary?.artifacts?.download_url ||
      (props.execution?.id
        ? `/api/app-automation/executions/${props.execution.id}/download-evidence/`
        : ""),
    "该执行记录暂无可导出的排障附件",
  );
}

async function renderPerformanceChart() {
  const series = props.summary?.performance?.series || [];
  if (!props.modelValue) return;
  if (!series.length) {
    disposePerformanceChart();
    return;
  }
  await nextTick();
  if (!performanceChartRef.value) return;

  disposePerformanceChart();
  performanceChart = echarts.init(performanceChartRef.value);
  performanceChart.setOption({
    tooltip: { trigger: "axis" },
    legend: { top: 0, data: ["CPU %", "内存 MB", "温度 ℃"] },
    grid: { left: 48, right: 28, top: 44, bottom: 36 },
    xAxis: {
      type: "category",
      boundaryGap: false,
      data: series.map((item) => item.label),
    },
    yAxis: [
      { type: "value", name: "CPU/温度", min: 0 },
      { type: "value", name: "内存", min: 0 },
    ],
    series: [
      {
        name: "CPU %",
        type: "line",
        smooth: true,
        showSymbol: false,
        data: series.map((item) => item.cpu ?? null),
        itemStyle: { color: "#f59e0b" },
        areaStyle: { opacity: 0.08 },
      },
      {
        name: "内存 MB",
        type: "line",
        smooth: true,
        showSymbol: false,
        yAxisIndex: 1,
        data: series.map((item) => item.memory ?? null),
        itemStyle: { color: "#2563eb" },
        areaStyle: { opacity: 0.06 },
      },
      {
        name: "温度 ℃",
        type: "line",
        smooth: true,
        showSymbol: false,
        data: series.map((item) => item.temperature ?? null),
        itemStyle: { color: "#ef4444" },
      },
    ],
  });
  setTimeout(() => performanceChart?.resize(), 120);
}

function disposePerformanceChart() {
  if (performanceChart) {
    performanceChart.dispose();
    performanceChart = null;
  }
}

watch(
  () => [props.modelValue, props.summary],
  () => renderPerformanceChart(),
);

onBeforeUnmount(disposePerformanceChart);
</script>

<style scoped>
.standard-report-dialog {
  min-height: 180px;
}

.quality-decision-strip {
  display: grid;
  grid-template-columns: minmax(0, 1.2fr) 220px minmax(360px, 0.9fr);
  gap: 14px;
  align-items: stretch;
  padding: 16px;
  border-radius: 16px;
  border: 1px solid #dbeafe;
  background: linear-gradient(180deg, #ffffff 0%, #f8fbff 100%);
}

.quality-decision-strip.decision-success {
  border-color: #bbf7d0;
  background: #f0fdf4;
}

.quality-decision-strip.decision-warning {
  border-color: #fde68a;
  background: #fffbeb;
}

.quality-decision-strip.decision-danger {
  border-color: #fecaca;
  background: #fef2f2;
}

.quality-decision-strip.decision-info {
  border-color: #bfdbfe;
  background: #eff6ff;
}

.decision-main,
.decision-next,
.decision-metric {
  padding: 12px;
  border-radius: 12px;
  background: rgba(255, 255, 255, 0.72);
  border: 1px solid rgba(226, 232, 240, 0.9);
}

.decision-main span,
.decision-next span,
.decision-metric span {
  display: block;
  color: #64748b;
  font-size: 12px;
}

.decision-main strong,
.decision-next strong,
.decision-metric strong {
  display: block;
  margin-top: 6px;
  color: #0f172a;
}

.decision-main strong {
  font-size: 22px;
}

.decision-main p {
  margin: 8px 0 0;
  color: #475569;
  line-height: 1.6;
}

.decision-metrics {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 10px;
}

.detail-section {
  margin-top: 24px;
}

.detail-section h4 {
  margin: 0 0 12px;
  color: #303133;
}

.section-title {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.section-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.diagnosis-section {
  padding: 14px;
  border-radius: 12px;
  background: #fff7ed;
  border: 1px solid #fed7aa;
}

.diagnosis-actions {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 10px;
  margin-top: 12px;
}

.diagnosis-action {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  padding: 10px;
  border-radius: 8px;
  background: #fff;
  color: #475569;
  font-size: 13px;
  line-height: 1.6;
}

.diagnosis-action span {
  width: 20px;
  height: 20px;
  flex-shrink: 0;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border-radius: 50%;
  background: #f97316;
  color: #fff;
  font-size: 12px;
  font-weight: 700;
}

.attachment-section {
  padding: 14px;
  border-radius: 12px;
  background: #f8fafc;
  border: 1px solid #e2e8f0;
}

.attachment-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
  margin-top: 12px;
}

.attachment-card {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  padding: 14px;
  border-radius: 10px;
  background: #fff;
  border: 1px solid #e5e7eb;
}

.attachment-card strong {
  color: #0f172a;
}

.attachment-card p {
  margin: 6px 0;
  color: #475569;
  line-height: 1.6;
}

.attachment-meta {
  color: #64748b;
  font-size: 12px;
}

.step-note {
  margin-bottom: 10px;
}

.evidence-section {
  padding: 14px;
  border-radius: 12px;
  background: #f8fafc;
  border: 1px solid #e2e8f0;
}

.evidence-grid {
  display: grid;
  gap: 12px;
}

.evidence-card {
  padding: 12px;
  border-radius: 10px;
  background: #fff;
  border: 1px solid #e5e7eb;
}

.evidence-card__title {
  display: flex;
  gap: 10px;
  align-items: center;
  margin-bottom: 10px;
  color: #0f172a;
}

.evidence-card__title span {
  color: #475569;
}

.evidence-images {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
  gap: 10px;
}

.evidence-image-item {
  overflow: hidden;
  border-radius: 10px;
  border: 1px solid #e5e7eb;
  background: #f8fafc;
}

.evidence-image-label {
  padding: 6px 10px;
  color: #475569;
  font-size: 12px;
  border-bottom: 1px solid #e5e7eb;
}

.evidence-image {
  display: block;
  width: 100%;
  height: 220px;
  background: #020617;
  cursor: zoom-in;
}

.performance-chart {
  width: 100%;
  height: 300px;
  margin-top: 16px;
  border: 1px solid #e5e7eb;
  border-radius: 10px;
}

.performance-analysis {
  display: grid;
  gap: 8px;
  margin-top: 12px;
}

@media (max-width: 960px) {
  .quality-decision-strip,
  .attachment-grid {
    grid-template-columns: 1fr;
  }

  .decision-metrics {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .diagnosis-actions {
    grid-template-columns: 1fr;
  }

  .attachment-card {
    align-items: stretch;
    flex-direction: column;
  }
}
</style>
