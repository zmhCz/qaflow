<template>
  <div class="element-management">
    <el-card>
      <!-- 顶部操作栏 -->
      <template #header>
        <div class="header-actions">
          <el-space wrap>
            <!-- 项目筛选 -->
            <el-select
              v-model="projectFilter"
              placeholder="全部项目"
              clearable
              filterable
              style="width: 160px"
              @change="handleSearch"
            >
              <el-option
                v-for="p in projectList"
                :key="p.id"
                :label="p.name"
                :value="p.id"
              />
            </el-select>

            <!-- 类型切换 -->
            <el-radio-group v-model="typeFilter" @change="loadElements">
              <el-radio-button value="">全部</el-radio-button>
              <el-radio-button value="image">图片</el-radio-button>
              <el-radio-button value="pos">坐标</el-radio-button>
              <el-radio-button value="region">区域</el-radio-button>
              <el-radio-button value="selector">定位</el-radio-button>
            </el-radio-group>

            <!-- 搜索 -->
            <el-input
              v-model="searchQuery"
              placeholder="搜索名称/中文说明/补充说明/resource-id"
              style="width: 250px"
              clearable
              @clear="handleSearch"
              @keyup.enter="handleSearch"
            >
              <template #prefix>
                <el-icon><Search /></el-icon>
              </template>
              <template #suffix>
                <el-button
                  v-if="searchQuery"
                  type="primary"
                  link
                  :icon="Search"
                  @click="handleSearch"
                  style="padding: 0"
                />
              </template>
            </el-input>
          </el-space>

          <!-- 操作按钮 -->
          <el-space>
            <el-button
              type="primary"
              @click="router.push('/app-automation/semantic-elements')"
            >
              语义库工作台
            </el-button>
            <el-button plain @click="showSourceSemanticDialog">
              源码候选辅助
            </el-button>
            <el-button @click="router.push('/app-automation/page-capture')">
              页面采集台
            </el-button>
            <el-button type="warning" @click="showPickerDialog">
              <el-icon><View /></el-icon>
              可视化拾取
            </el-button>
            <el-button type="success" @click="showCaptureDialog">
              <el-icon><Camera /></el-icon>
              从设备创建
            </el-button>
            <el-button type="primary" @click="showCreateDialog">
              <el-icon><Plus /></el-icon>
              手动创建
            </el-button>
          </el-space>
        </div>
      </template>

      <!-- 元素列表 -->
      <el-table
        :data="elements"
        border
        v-loading="loading"
        @selection-change="handleSelectionChange"
      >
        <el-table-column type="selection" width="55" />

        <el-table-column prop="name" label="元素名称" width="200" fixed="left">
          <template #default="{ row }">
            <el-link type="primary" @click="handleView(row)">
              {{ row.name }}
            </el-link>
          </template>
        </el-table-column>

        <el-table-column label="中文说明" min-width="220" show-overflow-tooltip>
          <template #default="{ row }">
            <div class="element-text-main">{{ getDisplayName(row) }}</div>
          </template>
        </el-table-column>

        <el-table-column label="补充说明" min-width="260" show-overflow-tooltip>
          <template #default="{ row }">
            <div class="element-text-sub">{{ getManualNote(row) }}</div>
          </template>
        </el-table-column>

        <el-table-column prop="element_type" label="类型" width="100">
          <template #default="{ row }">
            <el-tag :type="getTypeColor(row.element_type)">
              {{ getTypeName(row.element_type) }}
            </el-tag>
          </template>
        </el-table-column>

        <el-table-column label="图片分类" width="120">
          <template #default="{ row }">
            <el-tag
              v-if="row.element_type === 'image' && row.config?.image_category"
              type="info"
              size="small"
            >
              {{ row.config.image_category }}
            </el-tag>
            <span v-else style="color: #909399">-</span>
          </template>
        </el-table-column>

        <el-table-column prop="tags" label="标签" width="200">
          <template #default="{ row }">
            <el-tag
              v-for="tag in row.tags"
              :key="tag"
              size="small"
              style="margin-right: 5px"
            >
              {{ tag }}
            </el-tag>
          </template>
        </el-table-column>

        <!-- 预览 -->
        <el-table-column label="预览" width="200" align="center">
          <template #default="{ row }">
            <!-- 图片类型 -->
            <div v-if="row.element_type === 'image'" class="preview-image">
              <el-image
                :src="getImageUrl(row)"
                fit="contain"
                style="width: 150px; height: 80px; cursor: pointer"
                :preview-src-list="[getImageUrl(row)]"
                preview-teleported
              />
            </div>

            <!-- 坐标类型 -->
            <div v-else-if="row.element_type === 'pos'" class="preview-pos">
              <el-space :size="4">
                <el-tag type="primary" size="small"
                  >X: {{ row.config?.x }}</el-tag
                >
                <el-tag type="primary" size="small"
                  >Y: {{ row.config?.y }}</el-tag
                >
              </el-space>
            </div>

            <!-- 区域类型 -->
            <div
              v-else-if="row.element_type === 'region'"
              class="preview-region"
            >
              <el-space direction="vertical" :size="4">
                <el-space :size="4">
                  <el-tag type="success" size="small"
                    >X1: {{ row.config?.x1 }}</el-tag
                  >
                  <el-tag type="success" size="small"
                    >Y1: {{ row.config?.y1 }}</el-tag
                  >
                </el-space>
                <el-space :size="4">
                  <el-tag type="warning" size="small"
                    >X2: {{ row.config?.x2 }}</el-tag
                  >
                  <el-tag type="warning" size="small"
                    >Y2: {{ row.config?.y2 }}</el-tag
                  >
                </el-space>
              </el-space>
            </div>

            <div
              v-else-if="row.element_type === 'selector'"
              class="preview-selector"
            >
              <el-space direction="vertical" :size="4" alignment="start">
                <el-tag
                  v-if="row.config?.resource_id"
                  type="primary"
                  size="small"
                >
                  id: {{ row.config.resource_id }}
                </el-tag>
                <el-tag v-if="row.config?.text" type="success" size="small">
                  text: {{ row.config.text }}
                </el-tag>
                <el-tag
                  v-if="row.config?.content_desc"
                  type="warning"
                  size="small"
                >
                  desc: {{ row.config.content_desc }}
                </el-tag>
                <el-tag v-if="row.config?.class" type="info" size="small">
                  class: {{ row.config.class }}
                </el-tag>
              </el-space>
            </div>
          </template>
        </el-table-column>

        <el-table-column
          prop="usage_count"
          label="使用次数"
          width="100"
          sortable
        />

        <el-table-column prop="created_at" label="创建时间" width="180">
          <template #default="{ row }">
            {{ formatDateTime(row.created_at) }}
          </template>
        </el-table-column>

        <el-table-column label="操作" width="280" fixed="right">
          <template #default="{ row }">
            <el-button size="small" type="primary" @click="handleEdit(row)">
              编辑
            </el-button>
            <el-button size="small" @click="handleDuplicate(row)">
              复制
            </el-button>
            <el-button size="small" type="danger" @click="handleDelete(row)">
              删除
            </el-button>
          </template>
        </el-table-column>
      </el-table>

      <!-- 批量操作栏 -->
      <div v-if="selectedElements.length > 0" class="batch-actions">
        <el-space>
          <span>已选择 {{ selectedElements.length }} 项</span>
          <el-button type="danger" size="small" @click="handleBatchDelete">
            批量删除
          </el-button>
        </el-space>
      </div>

      <!-- 分页 -->
      <el-pagination
        v-model:current-page="currentPage"
        v-model:page-size="pageSize"
        :total="total"
        :page-sizes="[10, 20, 50, 100]"
        layout="total, sizes, prev, pager, next, jumper"
        @current-change="loadElements"
        @size-change="loadElements"
        style="margin-top: 20px; justify-content: flex-end"
      />
    </el-card>

    <!-- 从设备截图创建对话框 -->
    <CaptureElementDialog
      v-model="captureDialogVisible"
      :project-list="projectList"
      @success="handleCreateSuccess"
    />

    <!-- 手动创建/编辑对话框 -->
    <ManualElementDialog
      v-model="dialogVisible"
      :edit-data="editElement"
      :project-list="projectList"
      @success="handleCreateSuccess"
    />

    <!-- 查看详情对话框 -->
    <el-dialog v-model="detailDialogVisible" title="元素详情" width="800px">
      <el-descriptions :column="2" border v-if="viewingElement">
        <el-descriptions-item label="元素名称">{{
          viewingElement.name
        }}</el-descriptions-item>
        <el-descriptions-item label="元素类型">
          <el-tag :type="getTypeColor(viewingElement.element_type)">
            {{ getTypeName(viewingElement.element_type) }}
          </el-tag>
        </el-descriptions-item>
        <el-descriptions-item label="中文说明">{{
          getDisplayName(viewingElement)
        }}</el-descriptions-item>
        <el-descriptions-item label="补充说明">{{
          getManualNote(viewingElement)
        }}</el-descriptions-item>
        <el-descriptions-item label="标签" :span="2">
          <el-tag
            v-for="tag in viewingElement.tags"
            :key="tag"
            size="small"
            style="margin-right: 5px"
          >
            {{ tag }}
          </el-tag>
        </el-descriptions-item>
        <el-descriptions-item label="配置信息" :span="2">
          <pre
            style="
              margin: 0;
              padding: 10px;
              background: #f5f7fa;
              border-radius: 4px;
            "
            >{{ JSON.stringify(viewingElement.config, null, 2) }}</pre
          >
        </el-descriptions-item>
        <el-descriptions-item label="使用次数">{{
          viewingElement.usage_count || 0
        }}</el-descriptions-item>
        <el-descriptions-item label="创建时间">{{
          formatDateTime(viewingElement.created_at)
        }}</el-descriptions-item>
      </el-descriptions>
    </el-dialog>

    <!-- 可视化元素拾取器 -->
    <ElementPickerDialog
      v-model="pickerDialogVisible"
      :projects="projectList"
      @saved="handlePickerSaved"
    />

    <el-dialog
      v-model="sourceSemanticDialogVisible"
      title="AI 语义元素生成"
      width="1080px"
      destroy-on-close
    >
      <div class="source-semantic-toolbar">
        <el-select
          v-model="sourceProjectId"
          placeholder="绑定项目（可选）"
          clearable
          filterable
          style="width: 220px"
        >
          <el-option
            v-for="p in projectList"
            :key="p.id"
            :label="p.name"
            :value="p.id"
          />
        </el-select>
        <el-select
          v-model="sourcePreviewDeviceId"
          placeholder="选择设备截图框选"
          clearable
          filterable
          style="width: 210px"
        >
          <el-option
            v-for="device in deviceList"
            :key="device.id"
            :label="device.name || device.device_id"
            :value="device.id"
            :disabled="device.status === 'offline'"
          />
        </el-select>
        <el-input
          v-model="sourceKeyword"
          placeholder="搜索 resource-id / 业务词 / 文件名"
          clearable
          style="width: 280px"
          @keyup.enter="loadSourceSemanticCandidates"
        />
        <el-select
          v-model="sourceRole"
          placeholder="角色"
          clearable
          style="width: 150px"
        >
          <el-option label="输入框" value="input" />
          <el-option label="按钮" value="button" />
          <el-option label="勾选框" value="checkbox" />
          <el-option label="开关" value="switch" />
          <el-option label="入口" value="entry" />
          <el-option label="可点击" value="clickable" />
        </el-select>
        <el-button
          :loading="sourceSemanticLoading"
          @click="loadSourceSemanticCandidates"
        >
          扫描源码
        </el-button>
        <el-button
          :loading="sourcePreviewLoading"
          :disabled="!sourcePreviewDeviceId"
          @click="captureSourcePreview"
        >
          抓图框选
        </el-button>
        <el-button
          :loading="sourceSemanticImporting"
          :disabled="!sourcePreviewImportCandidate"
          @click="importSourcePreviewSelection"
        >
          导入框选控件
        </el-button>
        <el-button
          type="primary"
          :loading="sourceSemanticImporting"
          :disabled="sourceSemanticSelection.length === 0"
          @click="importSelectedSourceSemantics"
        >
          导入选中 {{ sourceSemanticSelection.length }}
        </el-button>
      </div>

      <el-alert
        v-if="sourceSemanticRoot"
        type="info"
        :closable="false"
        show-icon
        class="source-semantic-alert"
      >
        <template #title>
          源码路径：{{ sourceSemanticRoot }}。这些元素由平台从 APP
          源码推断，首次用于核心用例前建议人工确认业务含义。
        </template>
      </el-alert>

      <div class="source-semantic-layout">
        <el-table
          ref="sourceSemanticTableRef"
          :data="sourceSemanticCandidates"
          border
          height="520"
          v-loading="sourceSemanticLoading"
          highlight-current-row
          @current-change="handleSourceCandidateCurrentChange"
          @selection-change="sourceSemanticSelection = $event"
        >
          <el-table-column type="selection" width="48" />
          <el-table-column label="语义名称" min-width="190">
            <template #default="{ row }">
              <div class="element-text-main">{{ row.display_name }}</div>
              <div class="element-text-sub">{{ row.name }}</div>
            </template>
          </el-table-column>
          <el-table-column label="角色" width="110">
            <template #default="{ row }">
              <el-tag size="small" :type="getSourceRoleTag(row.role)">{{
                row.role_label || row.role
              }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column label="置信度" width="90">
            <template #default="{ row }">
              <el-tag
                size="small"
                :type="
                  row.confidence === 'high'
                    ? 'success'
                    : row.confidence === 'medium'
                      ? 'warning'
                      : 'info'
                "
              >
                {{ row.confidence }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column
            prop="resource_id"
            label="resource-id"
            min-width="190"
            show-overflow-tooltip
          />
          <el-table-column
            prop="source_layout_file"
            label="布局文件"
            min-width="230"
            show-overflow-tooltip
          />
          <el-table-column
            prop="source_summary"
            label="源码依据"
            min-width="220"
            show-overflow-tooltip
          />
        </el-table>
        <div class="source-preview-panel">
          <div class="source-preview-title">
            <span>当前设备截图框选</span>
            <el-tag
              v-if="sourcePreviewMatchedCandidate"
              type="success"
              size="small"
              >已命中</el-tag
            >
            <el-tag
              v-else-if="sourceCurrentCandidate && sourcePreviewImage"
              type="warning"
              size="small"
              >当前页未命中</el-tag
            >
          </div>
          <div v-if="!sourcePreviewImage" class="source-preview-empty">
            选择设备后点击“抓图框选”，再点左侧候选查看真实位置。
          </div>
          <div
            v-else
            class="source-preview-image-wrap"
            @mousedown="startSourcePreviewManualBox"
            @mousemove="moveSourcePreviewManualBox"
            @mouseup="finishSourcePreviewManualBox"
            @mouseleave="finishSourcePreviewManualBox"
          >
            <img
              ref="sourcePreviewImageRef"
              :src="sourcePreviewImage"
              class="source-preview-image"
              @load="handleSourcePreviewImageLoad"
            />
            <button
              v-for="candidate in sourcePreviewOverlayCandidates"
              :key="getRuntimeCandidateKey(candidate)"
              type="button"
              :class="[
                'source-preview-hotzone',
                {
                  'is-active': isSourcePreviewCandidateActive(candidate),
                  'is-matched': isSourcePreviewCandidateMatched(candidate),
                },
              ]"
              :style="getSourcePreviewCandidateStyle(candidate)"
              :title="describeRuntimeCandidate(candidate)"
              @mousedown.stop
              @click.stop="selectSourcePreviewCandidate(candidate)"
            />
            <div
              v-if="sourcePreviewBoxStyle"
              class="source-preview-box"
              :style="sourcePreviewBoxStyle"
            >
              <span>{{ sourcePreviewBoxLabel }}</span>
            </div>
          </div>
          <div class="source-preview-meta">
            <div>候选：{{ sourceCurrentCandidate?.display_name || "-" }}</div>
            <div>
              resource-id：{{ sourceCurrentCandidate?.resource_id || "-" }}
            </div>
            <div>
              框选控件：{{
                describeRuntimeCandidate(sourcePreviewImportCandidate) || "-"
              }}
            </div>
            <div v-if="sourcePreviewManualCandidate">
              手动区域：{{ sourcePreviewManualCandidate.raw_bounds }}
              <el-button
                link
                type="primary"
                size="small"
                @click="clearSourcePreviewManualBox"
                >清除</el-button
              >
            </div>
            <div>
              布局：{{ sourceCurrentCandidate?.source_layout_file || "-" }}
            </div>
          </div>
        </div>
      </div>
    </el-dialog>
  </div>
</template>

<script setup>
import { computed, ref, onMounted } from "vue";
import { useRouter } from "vue-router";
import { ElMessage, ElMessageBox } from "element-plus";
import {
  getAppElementList,
  createAppElement,
  deleteAppElement as apiDeleteAppElement,
  getAppProjects,
  getDeviceList,
  captureDeviceScreenshot,
  captureDevicePageState,
  getSourceSemanticCandidates,
  importSourceSemantics,
} from "@/api/app-automation";
import { Search, Plus, Camera, View } from "@element-plus/icons-vue";
import { formatDateTime } from "@/utils/app-automation-helpers";
import CaptureElementDialog from "./components/CaptureElementDialog.vue";
import ManualElementDialog from "./components/ManualElementDialog.vue";
import ElementPickerDialog from "./ElementPickerDialog.vue";

const router = useRouter();

// 状态
const loading = ref(false);
const elements = ref([]);
const selectedElements = ref([]);

// 筛选条件
const searchQuery = ref("");
const typeFilter = ref("");
const projectFilter = ref(null);
const projectList = ref([]);
const currentPage = ref(1);
const pageSize = ref(20);
const total = ref(0);

// 对话框
const dialogVisible = ref(false);
const captureDialogVisible = ref(false);
const pickerDialogVisible = ref(false);
const detailDialogVisible = ref(false);
const sourceSemanticDialogVisible = ref(false);
const editElement = ref(null);
const viewingElement = ref(null);
const sourceSemanticLoading = ref(false);
const sourceSemanticImporting = ref(false);
const sourceSemanticCandidates = ref([]);
const sourceSemanticSelection = ref([]);
const sourceSemanticRoot = ref("");
const sourceSemanticTableRef = ref(null);
const sourceKeyword = ref("");
const sourceRole = ref("");
const sourceProjectId = ref(null);
const deviceList = ref([]);
const sourcePreviewDeviceId = ref(null);
const sourcePreviewLoading = ref(false);
const sourcePreviewImage = ref("");
const sourcePreviewCandidates = ref([]);
const sourceCurrentCandidate = ref(null);
const sourcePreviewMatchedCandidate = ref(null);
const sourcePreviewSelectedRuntimeCandidate = ref(null);
const sourcePreviewManualCandidate = ref(null);
const sourcePreviewDrawing = ref(false);
const sourcePreviewDrawStart = ref(null);
const sourcePreviewPageInfo = ref({});
const sourcePreviewNaturalWidth = ref(1);
const sourcePreviewNaturalHeight = ref(1);
const sourcePreviewImageRef = ref(null);

const loadElements = async () => {
  loading.value = true;
  try {
    const params = {
      page: currentPage.value,
      page_size: pageSize.value,
      element_type: typeFilter.value,
    };
    if (projectFilter.value) params.project = projectFilter.value;

    // 只有搜索关键词不为空时才添加 search 参数
    if (searchQuery.value && searchQuery.value.trim()) {
      params.search = searchQuery.value.trim();
    }

    const res = await getAppElementList(params);
    elements.value = res.data.results || [];
    total.value = res.data.count || 0;
  } catch (error) {
    ElMessage.error("加载元素列表失败: " + (error.message || "未知错误"));
  } finally {
    loading.value = false;
  }
};

// 搜索处理
const handleSearch = () => {
  currentPage.value = 1; // 搜索时重置到第一页
  loadElements();
};

// 对话框操作
const showCreateDialog = () => {
  editElement.value = null;
  dialogVisible.value = true;
};

const showCaptureDialog = () => {
  captureDialogVisible.value = true;
};

const showPickerDialog = () => {
  pickerDialogVisible.value = true;
};

const handlePickerSaved = (element) => {
  ElMessage.success("元素已保存");
  loadElements();
};

const showSourceSemanticDialog = async () => {
  sourceSemanticDialogVisible.value = true;
  if (sourceProjectId.value === null && projectFilter.value) {
    sourceProjectId.value = projectFilter.value;
  }
  await loadDeviceListForSourcePreview();
  await loadSourceSemanticCandidates();
};

const loadDeviceListForSourcePreview = async () => {
  try {
    const res = await getDeviceList({ page_size: 100 });
    deviceList.value = res.data.results || res.data || [];
    if (!sourcePreviewDeviceId.value) {
      const onlineDevice = deviceList.value.find(
        (device) => device.status !== "offline",
      );
      sourcePreviewDeviceId.value = onlineDevice?.id || null;
    }
  } catch (error) {
    ElMessage.warning(
      `设备列表加载失败: ${error.response?.data?.msg || error.message}`,
    );
  }
};

const captureSourcePreview = async () => {
  if (!sourcePreviewDeviceId.value) {
    ElMessage.warning("请先选择设备");
    return;
  }

  sourcePreviewLoading.value = true;
  try {
    const res = await captureDevicePageState(sourcePreviewDeviceId.value);
    const data = res.data?.data || {};
    sourcePreviewImage.value = data.content || "";
    sourcePreviewCandidates.value = data.candidates || [];
    sourcePreviewPageInfo.value = {
      package_name: data.package_name || "",
      activity: data.activity || "",
      timestamp: data.timestamp || null,
      filename: data.filename || "",
    };
    sourcePreviewSelectedRuntimeCandidate.value = null;
    sourcePreviewManualCandidate.value = null;
    updateSourcePreviewMatch();
    if (!sourcePreviewImage.value) {
      ElMessage.warning("当前页面没有返回截图");
    }
  } catch (error) {
    try {
      const res = await captureDeviceScreenshot(sourcePreviewDeviceId.value);
      const data = res.data?.data || {};
      sourcePreviewImage.value = data.content || "";
      sourcePreviewCandidates.value = [];
      sourcePreviewPageInfo.value = {
        package_name: "",
        activity: "",
        timestamp: data.timestamp || null,
        filename: data.filename || "",
      };
      sourcePreviewSelectedRuntimeCandidate.value = null;
      sourcePreviewManualCandidate.value = null;
      updateSourcePreviewMatch();
      ElMessage.warning(
        "已显示设备截图，但当前 UI 树抓取失败，暂时无法自动框选。",
      );
    } catch (fallbackError) {
      ElMessage.error(
        `抓图失败: ${fallbackError.response?.data?.msg || error.response?.data?.msg || fallbackError.message || error.message}`,
      );
    }
  } finally {
    sourcePreviewLoading.value = false;
  }
};

const handleSourceCandidateCurrentChange = (row) => {
  sourceCurrentCandidate.value = row || null;
  updateSourcePreviewMatch();
};

const handleSourcePreviewImageLoad = (event) => {
  sourcePreviewNaturalWidth.value = event.target.naturalWidth || 1;
  sourcePreviewNaturalHeight.value = event.target.naturalHeight || 1;
};

const resourceTail = (value) => {
  const text = String(value || "").trim();
  return text.split("/").pop().split(":").pop();
};

const cleanPreviewText = (value) => String(value || "").trim();

const normalizePreviewText = (value) => cleanPreviewText(value).toLowerCase();

const runtimeRole = (candidate = {}) =>
  normalizePreviewText(candidate.interaction_role || candidate.role);

const sourceRoleValue = (candidate = {}) =>
  normalizePreviewText(candidate.role || candidate.interaction_role);

const hasUsableBounds = (candidate = {}) => {
  const bounds = candidate.bounds || {};
  return Number(bounds.width || 0) > 0 && Number(bounds.height || 0) > 0;
};

const getRuntimeCandidateKey = (candidate = {}) =>
  [
    candidate.resource_id || "",
    candidate.raw_bounds || "",
    candidate.text || "",
    candidate.content_desc || "",
    candidate.hint || "",
  ].join("|");

const isSameRuntimeCandidate = (left, right) => {
  if (!left || !right) return false;
  return getRuntimeCandidateKey(left) === getRuntimeCandidateKey(right);
};

const describeRuntimeCandidate = (candidate = null) => {
  if (!candidate) return "";
  return [
    cleanPreviewText(
      candidate.text ||
        candidate.content_desc ||
        candidate.hint ||
        candidate.name,
    ),
    cleanPreviewText(candidate.resource_id),
    cleanPreviewText(candidate.class_name || candidate.class),
  ]
    .filter(Boolean)
    .slice(0, 2)
    .join(" / ");
};

const formatPreviewBounds = (bounds = {}) =>
  `[${Number(bounds.x1 || 0)},${Number(bounds.y1 || 0)}][${Number(bounds.x2 || 0)},${Number(bounds.y2 || 0)}]`;

const getPreviewImageMetrics = () => {
  const image = sourcePreviewImageRef.value;
  const wrap = image?.parentElement;
  if (!image || !wrap) return null;
  return {
    image,
    wrap,
    renderedWidth: image.clientWidth || 1,
    renderedHeight: image.clientHeight || 1,
    naturalWidth: sourcePreviewNaturalWidth.value || image.naturalWidth || 1,
    naturalHeight: sourcePreviewNaturalHeight.value || image.naturalHeight || 1,
  };
};

const getPreviewNaturalPoint = (event) => {
  const metrics = getPreviewImageMetrics();
  if (!metrics) return null;
  const rect = metrics.wrap.getBoundingClientRect();
  const displayX = event.clientX - rect.left + metrics.wrap.scrollLeft;
  const displayY = event.clientY - rect.top + metrics.wrap.scrollTop;
  const clampedX = Math.max(0, Math.min(metrics.renderedWidth, displayX));
  const clampedY = Math.max(0, Math.min(metrics.renderedHeight, displayY));
  return {
    x: Math.round((clampedX / metrics.renderedWidth) * metrics.naturalWidth),
    y: Math.round((clampedY / metrics.renderedHeight) * metrics.naturalHeight),
  };
};

const createManualCandidateFromPoints = (start, end, temporary = false) => {
  if (!start || !end) return null;
  const x1 = Math.max(0, Math.min(start.x, end.x));
  const y1 = Math.max(0, Math.min(start.y, end.y));
  const x2 = Math.min(
    sourcePreviewNaturalWidth.value || 1,
    Math.max(start.x, end.x),
  );
  const y2 = Math.min(
    sourcePreviewNaturalHeight.value || 1,
    Math.max(start.y, end.y),
  );
  const width = Math.max(0, x2 - x1);
  const height = Math.max(0, y2 - y1);
  const bounds = { x1, y1, x2, y2, width, height };
  const label =
    sourceCurrentCandidate.value?.display_name || `手动框选_${x1}_${y1}`;
  return {
    name: label,
    description: temporary ? "正在框选" : "手动截图框选区域",
    package_name: sourcePreviewPageInfo.value.package_name || "",
    class_name: "manual.bounds",
    resource_id: "",
    text: label,
    content_desc: "",
    hint: "",
    clickable: true,
    focusable: false,
    checkable: false,
    scrollable: false,
    interaction_role:
      sourceRoleValue(sourceCurrentCandidate.value) || "clickable",
    interaction_role_label: "手动框选",
    bounds,
    raw_bounds: formatPreviewBounds(bounds),
    manual_box: true,
  };
};

const startSourcePreviewManualBox = (event) => {
  if (event.button !== 0 || !sourcePreviewImage.value) return;
  const point = getPreviewNaturalPoint(event);
  if (!point) return;
  sourcePreviewDrawing.value = true;
  sourcePreviewDrawStart.value = point;
  sourcePreviewSelectedRuntimeCandidate.value = null;
  sourcePreviewManualCandidate.value = createManualCandidateFromPoints(
    point,
    point,
    true,
  );
};

const moveSourcePreviewManualBox = (event) => {
  if (!sourcePreviewDrawing.value || !sourcePreviewDrawStart.value) return;
  const point = getPreviewNaturalPoint(event);
  if (!point) return;
  sourcePreviewManualCandidate.value = createManualCandidateFromPoints(
    sourcePreviewDrawStart.value,
    point,
    true,
  );
};

const finishSourcePreviewManualBox = (event) => {
  if (!sourcePreviewDrawing.value) return;
  const point = getPreviewNaturalPoint(event) || sourcePreviewDrawStart.value;
  const candidate = createManualCandidateFromPoints(
    sourcePreviewDrawStart.value,
    point,
  );
  sourcePreviewDrawing.value = false;
  sourcePreviewDrawStart.value = null;
  if (!candidate || candidate.bounds.width < 8 || candidate.bounds.height < 8) {
    sourcePreviewManualCandidate.value = null;
    return;
  }
  sourcePreviewManualCandidate.value = candidate;
  sourcePreviewSelectedRuntimeCandidate.value = null;
};

const clearSourcePreviewManualBox = () => {
  sourcePreviewManualCandidate.value = null;
  sourcePreviewDrawing.value = false;
  sourcePreviewDrawStart.value = null;
};

const roleCompatible = (sourceCandidate = {}, runtimeCandidate = {}) => {
  const source = sourceRoleValue(sourceCandidate);
  const runtime = runtimeRole(runtimeCandidate);
  if (!source || !runtime || runtime === "unknown") return true;
  if (source === runtime) return true;
  if (
    source === "button" &&
    ["clickable", "entry", "tab", "option"].includes(runtime)
  )
    return true;
  if (source === "entry" && ["clickable", "button", "option"].includes(runtime))
    return true;
  if (source === "input" && ["focusable", "search"].includes(runtime))
    return true;
  return false;
};

const previewTextMatches = (left, right) => {
  const a = normalizePreviewText(left);
  const b = normalizePreviewText(right);
  if (!a || !b) return 0;
  if (a === b) return 35;
  if (a.length >= 2 && b.includes(a)) return 22;
  if (b.length >= 2 && a.includes(b)) return 18;
  return 0;
};

const scoreSourceRuntimeMatch = (
  sourceCandidate = {},
  runtimeCandidate = {},
) => {
  if (!sourceCandidate || !runtimeCandidate) return 0;
  let score = 0;
  const sourceResource = cleanPreviewText(sourceCandidate.resource_id);
  const runtimeResource = cleanPreviewText(runtimeCandidate.resource_id);
  if (sourceResource && runtimeResource) {
    if (sourceResource === runtimeResource) {
      score += 110;
    } else if (resourceTail(sourceResource) === resourceTail(runtimeResource)) {
      score += 90;
    }
  }

  const sourceTexts = [
    sourceCandidate.text,
    sourceCandidate.hint,
    sourceCandidate.content_desc,
    sourceCandidate.display_name,
  ];
  const runtimeTexts = [
    runtimeCandidate.text,
    runtimeCandidate.hint,
    runtimeCandidate.content_desc,
    runtimeCandidate.name,
  ];
  let textScore = 0;
  sourceTexts.forEach((sourceText) => {
    runtimeTexts.forEach((runtimeText) => {
      textScore = Math.max(
        textScore,
        previewTextMatches(sourceText, runtimeText),
      );
    });
  });
  score += textScore;

  const sourceClass = normalizePreviewText(sourceCandidate.class);
  const runtimeClass = normalizePreviewText(
    runtimeCandidate.class_name || runtimeCandidate.class,
  );
  if (
    sourceClass &&
    runtimeClass &&
    (runtimeClass.endsWith(sourceClass) || sourceClass.endsWith(runtimeClass))
  ) {
    score += 12;
  }
  if (roleCompatible(sourceCandidate, runtimeCandidate)) {
    score += 8;
  }
  if (
    runtimeCandidate.clickable ||
    runtimeCandidate.focusable ||
    runtimeCandidate.checkable
  ) {
    score += 4;
  }
  return score;
};

const findBestRuntimeMatch = (sourceCandidate) => {
  if (!sourceCandidate || !sourcePreviewCandidates.value.length) return null;
  const scored = sourcePreviewCandidates.value
    .filter(hasUsableBounds)
    .map((candidate) => ({
      candidate,
      score: scoreSourceRuntimeMatch(sourceCandidate, candidate),
    }))
    .filter((item) => item.score >= 45)
    .sort((a, b) => b.score - a.score);
  return scored[0]?.candidate || null;
};

const findBestSourceCandidateForRuntime = (runtimeCandidate) => {
  if (!runtimeCandidate || !sourceSemanticCandidates.value.length) return null;
  const scored = sourceSemanticCandidates.value
    .map((candidate) => ({
      candidate,
      score: scoreSourceRuntimeMatch(candidate, runtimeCandidate),
    }))
    .filter((item) => item.score >= 45)
    .sort((a, b) => b.score - a.score);
  return scored[0]?.candidate || null;
};

const updateSourcePreviewMatch = () => {
  sourcePreviewMatchedCandidate.value = findBestRuntimeMatch(
    sourceCurrentCandidate.value,
  );
};

const sourcePreviewBoxStyle = computed(() => {
  const matched = sourcePreviewImportCandidate.value;
  const bounds = matched?.bounds || {};
  const width = sourcePreviewNaturalWidth.value || 1;
  const height = sourcePreviewNaturalHeight.value || 1;
  const x1 = Number(bounds.x1 || 0);
  const y1 = Number(bounds.y1 || 0);
  const boxWidth = Number(
    bounds.width || Math.max(0, Number(bounds.x2 || 0) - x1),
  );
  const boxHeight = Number(
    bounds.height || Math.max(0, Number(bounds.y2 || 0) - y1),
  );
  if (!matched || !boxWidth || !boxHeight) {
    return null;
  }
  return {
    left: `${(x1 / width) * 100}%`,
    top: `${(y1 / height) * 100}%`,
    width: `${(boxWidth / width) * 100}%`,
    height: `${(boxHeight / height) * 100}%`,
  };
});

const sourcePreviewOverlayCandidates = computed(() =>
  sourcePreviewCandidates.value.filter(hasUsableBounds).slice(0, 180),
);

const sourcePreviewBoxLabel = computed(
  () =>
    describeRuntimeCandidate(sourcePreviewImportCandidate.value) ||
    sourceCurrentCandidate.value?.display_name ||
    sourceCurrentCandidate.value?.resource_id ||
    "已框选控件",
);

const sourcePreviewImportCandidate = computed(
  () =>
    sourcePreviewManualCandidate.value ||
    sourcePreviewSelectedRuntimeCandidate.value ||
    sourcePreviewMatchedCandidate.value,
);

const getSourcePreviewCandidateStyle = (candidate) => {
  const bounds = candidate?.bounds || {};
  const width = sourcePreviewNaturalWidth.value || 1;
  const height = sourcePreviewNaturalHeight.value || 1;
  const x1 = Number(bounds.x1 || 0);
  const y1 = Number(bounds.y1 || 0);
  const boxWidth = Number(
    bounds.width || Math.max(0, Number(bounds.x2 || 0) - x1),
  );
  const boxHeight = Number(
    bounds.height || Math.max(0, Number(bounds.y2 || 0) - y1),
  );
  return {
    left: `${(x1 / width) * 100}%`,
    top: `${(y1 / height) * 100}%`,
    width: `${(boxWidth / width) * 100}%`,
    height: `${(boxHeight / height) * 100}%`,
  };
};

const isSourcePreviewCandidateActive = (candidate) =>
  isSameRuntimeCandidate(
    candidate,
    sourcePreviewSelectedRuntimeCandidate.value,
  );

const isSourcePreviewCandidateMatched = (candidate) =>
  isSameRuntimeCandidate(candidate, sourcePreviewMatchedCandidate.value);

const selectSourcePreviewCandidate = (candidate) => {
  sourcePreviewSelectedRuntimeCandidate.value = candidate;
  sourcePreviewManualCandidate.value = null;
  const matchedSource = findBestSourceCandidateForRuntime(candidate);
  if (matchedSource) {
    sourceCurrentCandidate.value = matchedSource;
    sourcePreviewMatchedCandidate.value = candidate;
    sourceSemanticTableRef.value?.setCurrentRow?.(matchedSource);
    ElMessage.success("已根据截图框选匹配到源码语义候选");
  } else {
    sourcePreviewMatchedCandidate.value = candidate;
    ElMessage.warning(
      "该框选控件暂未匹配到源码候选，可直接导入为运行时语义元素",
    );
  }
};

const loadSourceSemanticCandidates = async () => {
  sourceSemanticLoading.value = true;
  try {
    const res = await getSourceSemanticCandidates({
      keyword: sourceKeyword.value,
      role: sourceRole.value,
      limit: 300,
    });
    const data = res.data?.data || {};
    sourceSemanticRoot.value = data.source_root || "";
    sourceSemanticCandidates.value = data.candidates || [];
    sourceSemanticSelection.value = [];
    sourceCurrentCandidate.value = sourceSemanticCandidates.value[0] || null;
    updateSourcePreviewMatch();
    if (!data.available) {
      ElMessage.warning("未找到 APP 源码路径，无法生成源码语义候选");
    }
  } catch (error) {
    ElMessage.error(
      `源码语义候选加载失败: ${error.response?.data?.msg || error.message}`,
    );
  } finally {
    sourceSemanticLoading.value = false;
  }
};

const semanticKeyFromRuntimeCandidate = (candidate = {}) => {
  const resource = resourceTail(candidate.resource_id);
  const label = cleanPreviewText(
    candidate.text ||
      candidate.content_desc ||
      candidate.hint ||
      candidate.name,
  );
  const classTail = cleanPreviewText(candidate.class_name || "node")
    .split(".")
    .pop();
  const bounds = candidate.bounds || {};
  const raw =
    resource || label || `${classTail}_${bounds.x1 || 0}_${bounds.y1 || 0}`;
  return (
    raw
      .replace(/([a-z0-9])([A-Z])/g, "$1_$2")
      .replace(/[^a-zA-Z0-9_\u4e00-\u9fa5]+/g, "_")
      .replace(/^_+|_+$/g, "")
      .toLowerCase() || "runtime_element"
  );
};

const roleFromRuntimeCandidate = (candidate = {}) => {
  const role = runtimeRole(candidate);
  if (role && role !== "unknown") return role;
  if (candidate.checkable) return "checkbox";
  if (candidate.focusable) return "input";
  if (candidate.clickable) return "button";
  if (candidate.scrollable) return "scrollable";
  return "clickable";
};

const buildRuntimeSemanticCandidate = (candidate = {}) => {
  const locatorKey = semanticKeyFromRuntimeCandidate(candidate);
  const displayName = cleanPreviewText(
    candidate.text ||
      candidate.content_desc ||
      candidate.hint ||
      candidate.name ||
      locatorKey,
  );
  const role = roleFromRuntimeCandidate(candidate);
  return {
    key: locatorKey,
    locator_key: locatorKey,
    name: `semantic.${locatorKey}`,
    display_name: displayName,
    description: displayName,
    manual_note: "通过设备截图框选生成，建议补充业务含义后用于核心用例。",
    role,
    role_label: candidate.interaction_role_label || role,
    confidence: candidate.resource_id ? "high" : "medium",
    resource_id: candidate.resource_id || "",
    class: candidate.class_name || candidate.class || "",
    text: candidate.text || "",
    hint: candidate.hint || "",
    content_desc: candidate.content_desc || "",
    bounds: candidate.raw_bounds || "",
    raw_bounds: candidate.raw_bounds || "",
    runtime_match: {
      ...candidate,
      page: sourcePreviewPageInfo.value,
      captured_at: Date.now(),
    },
    source_summary: "device screenshot box selection",
    source_refs: [],
    source_click_refs: [],
    source_movement_refs: [],
  };
};

const buildCandidateWithRuntimeMatch = (
  sourceCandidate = {},
  runtimeCandidate = null,
) => {
  const matched = runtimeCandidate || findBestRuntimeMatch(sourceCandidate);
  if (!matched) return { ...sourceCandidate };
  return {
    ...sourceCandidate,
    resource_id: matched.resource_id || sourceCandidate.resource_id || "",
    class: matched.class_name || sourceCandidate.class || "",
    text: matched.text || sourceCandidate.text || "",
    hint: matched.hint || sourceCandidate.hint || "",
    content_desc: matched.content_desc || sourceCandidate.content_desc || "",
    bounds: matched.raw_bounds || sourceCandidate.bounds || "",
    raw_bounds: matched.raw_bounds || sourceCandidate.raw_bounds || "",
    runtime_match: {
      ...matched,
      page: sourcePreviewPageInfo.value,
      captured_at: Date.now(),
    },
  };
};

const importSelectedSourceSemantics = async () => {
  if (!sourceSemanticSelection.value.length) {
    ElMessage.warning("请先选择要导入的语义元素");
    return;
  }

  sourceSemanticImporting.value = true;
  try {
    const res = await importSourceSemantics({
      project: sourceProjectId.value,
      candidates: sourceSemanticSelection.value.map((candidate) =>
        buildCandidateWithRuntimeMatch(candidate),
      ),
    });
    const data = res.data?.data || {};
    ElMessage.success(
      res.data?.msg ||
        `导入完成，新增 ${data.created?.length || 0} 个，更新 ${data.updated?.length || 0} 个`,
    );
    sourceSemanticDialogVisible.value = false;
    sourceSemanticSelection.value = [];
    typeFilter.value = "selector";
    await loadElements();
  } catch (error) {
    ElMessage.error(`导入失败: ${error.response?.data?.msg || error.message}`);
  } finally {
    sourceSemanticImporting.value = false;
  }
};

const importSourcePreviewSelection = async () => {
  const runtimeCandidate = sourcePreviewImportCandidate.value;
  if (!runtimeCandidate) {
    ElMessage.warning("请先在截图上框选一个控件");
    return;
  }

  const matchedSource = findBestSourceCandidateForRuntime(runtimeCandidate);
  const candidate = matchedSource
    ? buildCandidateWithRuntimeMatch(matchedSource, runtimeCandidate)
    : buildRuntimeSemanticCandidate(runtimeCandidate);

  sourceSemanticImporting.value = true;
  try {
    const res = await importSourceSemantics({
      project: sourceProjectId.value,
      candidates: [candidate],
    });
    const data = res.data?.data || {};
    ElMessage.success(
      res.data?.msg ||
        `导入完成，新增 ${data.created?.length || 0} 个，更新 ${data.updated?.length || 0} 个`,
    );
    typeFilter.value = "selector";
    await loadElements();
  } catch (error) {
    ElMessage.error(
      `导入框选控件失败: ${error.response?.data?.msg || error.message}`,
    );
  } finally {
    sourceSemanticImporting.value = false;
  }
};

const handleView = (element) => {
  viewingElement.value = element;
  detailDialogVisible.value = true;
};

const handleEdit = (element) => {
  editElement.value = element;
  dialogVisible.value = true;
};

// 智能生成唯一的副本名称
const findAvailableName = (baseName) => {
  // 先尝试 "原名_副本"
  const firstCandidate = `${baseName}_副本`;
  if (!elements.value.some((el) => el.name === firstCandidate)) {
    return firstCandidate;
  }

  // 查找 "原名_副本(n)" 中的最大 n
  const pattern = new RegExp(
    `^${baseName.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}_副本\\((\\d+)\\)$`,
  );
  let maxNum = 1;

  elements.value.forEach((el) => {
    const match = el.name.match(pattern);
    if (match) {
      const num = parseInt(match[1]);
      if (num > maxNum) {
        maxNum = num;
      }
    }
  });

  return `${baseName}_副本(${maxNum + 1})`;
};

const handleDuplicate = async (element) => {
  try {
    // 智能生成唯一名称
    const newName = findAvailableName(element.name);

    // 复制配置，移除 file_hash（避免重复检测）
    const newConfig = { ...element.config };
    delete newConfig.file_hash; // 允许多个元素共享同一图片

    // 复制元素数据
    const duplicateData = {
      ...element,
      name: newName,
      id: undefined,
      created_at: undefined,
      updated_at: undefined,
      created_by: undefined,
      created_by_id: undefined,
      last_used_at: undefined,
      usage_count: 0,
      config: newConfig, // 使用清理后的配置
    };

    await createAppElement(duplicateData);
    ElMessage.success(`已复制为 "${newName}"`);
    loadElements();
  } catch (error) {
    console.error("复制失败:", error);
    const errorMsg =
      error.response?.data?.config?.[0] ||
      error.response?.data?.name?.[0] ||
      error.response?.data?.message ||
      "复制失败";
    ElMessage.error(errorMsg);
  }
};

const handleCreateSuccess = () => {
  loadElements();
};

const handleSelectionChange = (selection) => {
  selectedElements.value = selection;
};

const handleBatchDelete = async () => {
  try {
    await ElMessageBox.confirm(
      `确定要删除选中的 ${selectedElements.value.length} 个元素吗？`,
      "批量删除确认",
      {
        confirmButtonText: "确定",
        cancelButtonText: "取消",
        type: "warning",
      },
    );

    for (const element of selectedElements.value) {
      await apiDeleteAppElement(element.id);
    }

    ElMessage.success("批量删除成功");
    selectedElements.value = [];
    loadElements();
  } catch (error) {
    if (error !== "cancel") {
      console.error("批量删除失败:", error);
      ElMessage.error("批量删除失败");
    }
  }
};

const handleDelete = async (element) => {
  try {
    await ElMessageBox.confirm(
      `确定要删除元素 "${element.name}" 吗？`,
      "删除确认",
      {
        confirmButtonText: "确定",
        cancelButtonText: "取消",
        type: "warning",
      },
    );

    await apiDeleteAppElement(element.id);
    ElMessage.success("删除成功");
    loadElements();
  } catch (error) {
    if (error !== "cancel") {
      console.error("删除失败:", error);
      ElMessage.error("删除失败");
    }
  }
};

// 获取图片URL
const getImageUrl = (element) => {
  if (!element?.id) return "";
  // 使用 updated_at 作为版本号，确保图片更新后能刷新
  const timestamp = element.updated_at
    ? new Date(element.updated_at).getTime()
    : Date.now();
  return `/api/app-automation/elements/${element.id}/preview/?t=${timestamp}`;
};

const getTypeColor = (type) => {
  const colorMap = {
    image: "primary",
    pos: "success",
    region: "warning",
    selector: "info",
  };
  return colorMap[type] || "info";
};

const getTypeName = (type) => {
  const nameMap = {
    image: "图片",
    pos: "坐标",
    region: "区域",
    selector: "定位",
  };
  return nameMap[type] || type;
};

const getDisplayName = (element) => {
  return (
    element?.display_name ||
    element?.config?.description ||
    element?.name ||
    "-"
  );
};

const getManualNote = (element) => {
  return (
    element?.manual_note ||
    element?.config?.manual_note ||
    element?.display_description ||
    "-"
  );
};

// formatDateTime 已从 app-automation-helpers 导入

const getSourceRoleTag = (role) => {
  const roleMap = {
    input: "success",
    button: "primary",
    checkbox: "warning",
    switch: "warning",
    entry: "info",
    clickable: "primary",
  };
  return roleMap[role] || "info";
};

onMounted(() => {
  getAppProjects({ page_size: 100 })
    .then((res) => {
      projectList.value = res.data.results || res.data || [];
    })
    .catch(() => {});
  loadElements();
});
</script>

<style scoped lang="scss">
.element-management {
  padding: 20px;

  .header-actions {
    display: flex;
    justify-content: space-between;
    align-items: center;
    flex-wrap: wrap;
    gap: 10px;
  }

  .preview-image {
    padding: 5px;

    :deep(.el-image) {
      border: 1px solid #e4e7ed;
      border-radius: 4px;
      overflow: hidden;

      &:hover {
        border-color: #409eff;
      }
    }
  }

  .preview-pos,
  .preview-region {
    display: flex;
    justify-content: center;
  }

  .element-text-main {
    color: #111827;
    font-weight: 600;
    line-height: 1.5;
    word-break: break-all;
  }

  .element-text-sub {
    color: #6b7280;
    line-height: 1.5;
    word-break: break-all;
  }

  .source-semantic-toolbar {
    display: flex;
    flex-wrap: wrap;
    gap: 10px;
    align-items: center;
    margin-bottom: 12px;
  }

  .source-semantic-alert {
    margin-bottom: 12px;
  }

  .source-semantic-layout {
    display: grid;
    grid-template-columns: minmax(0, 1.15fr) 380px;
    gap: 12px;
    align-items: stretch;
  }

  .source-preview-panel {
    min-height: 520px;
    padding: 12px;
    border: 1px solid #e5e7eb;
    border-radius: 10px;
    background: #f8fafc;
  }

  .source-preview-title {
    display: flex;
    align-items: center;
    justify-content: space-between;
    margin-bottom: 10px;
    color: #111827;
    font-weight: 600;
  }

  .source-preview-empty {
    display: flex;
    min-height: 320px;
    align-items: center;
    justify-content: center;
    padding: 24px;
    border: 1px dashed #cbd5e1;
    border-radius: 10px;
    color: #64748b;
    text-align: center;
    line-height: 1.6;
    background: #fff;
  }

  .source-preview-image-wrap {
    position: relative;
    max-height: 420px;
    overflow: auto;
    border-radius: 10px;
    background: #111827;
    cursor: crosshair;
    user-select: none;
  }

  .source-preview-image {
    display: block;
    width: 100%;
    height: auto;
    pointer-events: none;
    user-select: none;
  }

  .source-preview-hotzone {
    position: absolute;
    z-index: 1;
    box-sizing: border-box;
    padding: 0;
    border: 1px solid rgba(59, 130, 246, 0.55);
    border-radius: 2px;
    background: rgba(59, 130, 246, 0.08);
    cursor: crosshair;
  }

  .source-preview-hotzone:hover {
    border-color: #f97316;
    background: rgba(249, 115, 22, 0.16);
  }

  .source-preview-hotzone.is-matched {
    border-color: rgba(34, 197, 94, 0.9);
    background: rgba(34, 197, 94, 0.14);
  }

  .source-preview-hotzone.is-active {
    z-index: 3;
    border: 3px solid #ef4444;
    background: rgba(239, 68, 68, 0.16);
    box-shadow: 0 0 0 2px rgba(255, 255, 255, 0.9);
  }

  .source-preview-box {
    position: absolute;
    z-index: 4;
    box-sizing: border-box;
    border: 3px solid #ef4444;
    background: rgba(239, 68, 68, 0.12);
    box-shadow: 0 0 0 2px rgba(255, 255, 255, 0.86);
    pointer-events: none;
  }

  .source-preview-box span {
    position: absolute;
    left: 0;
    top: -30px;
    max-width: 240px;
    padding: 4px 8px;
    border-radius: 999px;
    color: #fff;
    background: rgba(15, 23, 42, 0.9);
    font-size: 12px;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }

  .source-preview-meta {
    display: grid;
    gap: 6px;
    margin-top: 10px;
    color: #475569;
    font-size: 12px;
    word-break: break-all;
  }

  .batch-actions {
    margin-top: 15px;
    padding: 10px;
    background: #ecf5ff;
    border: 1px solid #b3d8ff;
    border-radius: 4px;
    display: flex;
    align-items: center;
    justify-content: space-between;

    span {
      color: #409eff;
      font-weight: 500;
    }
  }

  :deep(.el-table) {
    .el-link {
      font-weight: 500;
    }
  }

  :deep(.el-pagination) {
    display: flex;
  }

  :deep(pre) {
    font-family: "Courier New", Courier, monospace;
    font-size: 13px;
    line-height: 1.5;
  }
}
</style>
