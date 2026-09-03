<template>
  <div class="semantic-workbench">
    <section class="semantic-hero">
      <div>
        <p class="eyebrow">Semantic Library V2</p>
        <h1>语义元素工作台</h1>
        <p class="subtitle">
          先把元素库维护稳定：直接显示真机截图，框选控件区域，填写业务名称后入库。旧元素先保留，新元素统一打
          semantic_v2 标签。
        </p>
      </div>
      <el-space wrap>
        <el-button @click="loadBaseData">刷新基础数据</el-button>
        <el-button
          type="primary"
          :loading="capturing"
          :disabled="!selectedDeviceId"
          @click="captureScreen"
        >
          刷新截图
        </el-button>
      </el-space>
    </section>

    <div class="workbench-grid">
      <el-card class="screen-card" shadow="never">
        <template #header>
          <div class="card-header">
            <div>
              <strong>设备截图</strong>
              <span>按住鼠标拖拽框选一个按钮、输入框或可点击区域</span>
            </div>
            <el-tag v-if="selectionBoundsText" type="success">{{
              selectionBoundsText
            }}</el-tag>
            <el-tag v-else type="info">未框选</el-tag>
          </div>
        </template>

        <div class="toolbar-form">
          <el-select
            v-model="selectedProjectId"
            placeholder="选择项目"
            clearable
            filterable
          >
            <el-option
              v-for="project in projects"
              :key="project.id"
              :label="project.name"
              :value="project.id"
            />
          </el-select>
          <el-select
            v-model="selectedDeviceId"
            placeholder="选择在线设备"
            filterable
          >
            <el-option
              v-for="device in onlineDevices"
              :key="device.id"
              :label="deviceLabel(device)"
              :value="device.id"
            />
          </el-select>
        </div>

        <div v-if="!screenshot" class="empty-shot">
          <el-empty
            description="选择设备后点击“刷新截图”，这里会直接显示手机当前画面。"
          />
        </div>

        <div
          v-else
          ref="imageWrapRef"
          class="shot-wrap"
          @mousedown="startSelection"
          @mousemove="moveSelection"
          @mouseup="finishSelection"
          @mouseleave="finishSelection"
        >
          <img
            ref="imageRef"
            :src="screenshot"
            class="device-shot"
            draggable="false"
            @load="handleImageLoad"
          />
          <div
            v-if="selectionStyle"
            class="selection-box"
            :style="selectionStyle"
          >
            <span>{{ form.businessName || "待命名元素" }}</span>
          </div>
        </div>
      </el-card>

      <el-card class="editor-card" shadow="never">
        <template #header>
          <div class="card-header">
            <div>
              <strong>入库信息</strong>
              <span>建议先点击验证，再保存到语义库</span>
            </div>
            <el-tag :type="preSaveVerified ? 'success' : 'warning'">
              {{ preSaveVerified ? "点击已确认" : "待点击验证" }}
            </el-tag>
          </div>
        </template>

        <el-form label-width="96px" class="semantic-form">
          <el-form-item label="业务对象" required>
            <el-autocomplete
              v-model="form.businessName"
              :fetch-suggestions="querySemanticObjectSuggestions"
              placeholder="从字典选择，如：退出登录 / 社区名称"
              clearable
              style="width: 100%"
            />
          </el-form-item>
          <el-form-item label="页面名称" required>
            <el-select
              v-model="form.pageName"
              placeholder="从字典选择页面"
              filterable
              allow-create
              clearable
              default-first-option
              style="width: 100%"
            >
              <el-option
                v-for="item in semanticPageOptions"
                :key="item"
                :label="item"
                :value="item"
              />
            </el-select>
          </el-form-item>
          <el-form-item label="元素角色">
            <el-select v-model="form.role" style="width: 100%">
              <el-option
                v-for="item in semanticRoleOptions"
                :key="item"
                :label="item"
                :value="item"
              />
            </el-select>
          </el-form-item>
          <el-form-item label="备注">
            <el-input
              v-model="form.note"
              type="textarea"
              :rows="4"
              placeholder="可写业务解释、前置条件、为什么这样框选等"
            />
          </el-form-item>

          <div class="meta-panel">
            <div>
              <span>截图尺寸</span>
              <strong
                >{{ imageNaturalSize.width }} x
                {{ imageNaturalSize.height }}</strong
              >
            </div>
            <div>
              <span>框选区域</span>
              <strong>{{ selectionBoundsText || "-" }}</strong>
            </div>
            <div>
              <span>保存标签</span>
              <strong
                >semantic_v2 / 人工框选 /
                {{ preSaveVerified ? "已验证" : "待验证" }}</strong
              >
            </div>
          </div>

          <el-alert
            :type="preSaveVerified ? 'success' : 'info'"
            show-icon
            :closable="false"
            :title="
              preSaveVerified
                ? '已完成点击验证：保存后元素会直接标为已验证。'
                : '推荐流程：框选区域后先点击验证，确认业务跳转符合预期，再保存入库。'
            "
          />

          <div class="form-actions">
            <el-button @click="clearSelection">清除框选</el-button>
            <el-button
              type="success"
              plain
              :loading="preSaveClickTesting"
              :disabled="!canClickTestSelection"
              @click="clickTestCurrentSelection"
            >
              点击验证
            </el-button>
            <el-button
              type="primary"
              :loading="saving"
              :disabled="!canSave"
              @click="saveSemanticElement"
            >
              保存到语义库
            </el-button>
          </div>
        </el-form>
      </el-card>
    </div>

    <el-card class="library-card" shadow="never">
      <template #header>
        <div class="card-header">
          <div>
            <strong>semantic_v2 新元素</strong>
            <span>这里仅展示新工作台沉淀的元素，旧元素库不会被删除</span>
          </div>
          <div class="header-actions">
            <el-button
              size="small"
              type="success"
              :loading="syncingVerified"
              @click="syncVerifiedFromHistory"
            >
              同步历史通过
            </el-button>
            <el-button size="small" @click="loadSemanticElements"
              >刷新列表</el-button
            >
          </div>
        </div>
      </template>

      <el-table :data="semanticElements" v-loading="elementsLoading" border>
        <el-table-column label="业务名称" min-width="180">
          <template #default="{ row }">
            <div class="element-title">
              {{ row.config?.description || row.name }}
            </div>
            <div class="element-sub">{{ row.name }}</div>
          </template>
        </el-table-column>
        <el-table-column label="页面" min-width="130">
          <template #default="{ row }">{{
            row.config?.page_name || "-"
          }}</template>
        </el-table-column>
        <el-table-column label="角色" width="100">
          <template #default="{ row }">
            <el-tag size="small">{{
              row.config?.interaction_role || "-"
            }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="定位兜底" min-width="190">
          <template #default="{ row }">{{
            row.config?.bounds || "-"
          }}</template>
        </el-table-column>
        <el-table-column label="状态" width="100">
          <template #default="{ row }">
            <el-tag
              size="small"
              :type="getSemanticStatusType(row.config?.semantic_status)"
            >
              {{ row.config?.semantic_status || "待验证" }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="标签" min-width="210">
          <template #default="{ row }">
            <el-tag
              v-for="tag in row.tags || []"
              :key="tag"
              size="small"
              class="tag-item"
              >{{ tag }}</el-tag
            >
          </template>
        </el-table-column>
        <el-table-column label="操作" width="110" fixed="right">
          <template #default="{ row }">
            <div class="row-actions">
              <el-dropdown
                trigger="click"
                @command="(command) => handleElementAction(command, row)"
              >
                <el-button size="small" plain>
                  更多<el-icon class="el-icon--right"><ArrowDown /></el-icon>
                </el-button>
                <template #dropdown>
                  <el-dropdown-menu>
                    <el-dropdown-item
                      command="recheck"
                      :disabled="validatingElementId === row.id"
                    >
                      定位复验
                    </el-dropdown-item>
                    <el-dropdown-item command="mark_verified"
                      >标为已验证</el-dropdown-item
                    >
                    <el-dropdown-item command="mark_needs_update"
                      >标为需调整</el-dropdown-item
                    >
                    <el-dropdown-item command="mark_pending"
                      >重置为待验证</el-dropdown-item
                    >
                  </el-dropdown-menu>
                </template>
              </el-dropdown>
            </div>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <el-dialog
      v-model="validationDialogVisible"
      title="元素定位验证结果"
      width="820px"
    >
      <div v-if="validationResult" class="validation-result">
        <el-alert
          :type="validationResult.matched ? 'success' : 'warning'"
          :title="
            validationResult.matched
              ? '验证通过：当前页面可命中该语义元素'
              : '验证未通过：当前页面未命中该语义元素'
          "
          :description="validationResult.reason"
          show-icon
          :closable="false"
        />
        <div class="validation-grid">
          <div>
            <span>验证策略</span>
            <strong>{{ validationResult.strategy || "-" }}</strong>
          </div>
          <div>
            <span>匹配分数</span>
            <strong>{{ validationResult.score }}</strong>
          </div>
          <div>
            <span>当前页面</span>
            <strong>{{ validationResult.page_activity || "-" }}</strong>
          </div>
          <div>
            <span>候选数量</span>
            <strong>{{
              validationResult.page_state?.candidate_count || 0
            }}</strong>
          </div>
        </div>

        <div
          v-if="validationResult.page_state?.content"
          class="validation-shot-wrap"
        >
          <div class="validation-shot-stage">
            <img
              :src="validationResult.page_state.content"
              class="validation-shot"
            />
            <div
              v-if="validationTargetStyle"
              class="validation-target-box"
              :style="validationTargetStyle"
            >
              <span>验证区域</span>
              <i
                v-if="validationTapStyle"
                class="tap-point"
                :style="validationTapStyle"
              />
            </div>
          </div>
        </div>

        <el-alert
          v-if="
            ['page_map_bounds', 'page_map_bounds_fallback'].includes(
              validationResult.strategy,
            )
          "
          class="validation-note"
          type="info"
          show-icon
          :closable="false"
          title="页面地图元素会优先使用入库时的框选区域作为验证和点击区域；下方实时 UI 节点只是辅助命中证据，区域可能更小。"
        />

        <el-descriptions :column="1" border size="small">
          <el-descriptions-item label="验证/点击区域 bounds">
            {{ validationResult.target_raw_bounds || "-" }}
          </el-descriptions-item>
          <el-descriptions-item label="点击中心点">
            {{
              validationResult.tap_point
                ? `${validationResult.tap_point.x}, ${validationResult.tap_point.y}`
                : "-"
            }}
          </el-descriptions-item>
        </el-descriptions>

        <el-descriptions
          v-if="validationResult.matched_candidate"
          :column="1"
          border
          size="small"
        >
          <el-descriptions-item label="命中 resource-id">
            {{ validationResult.matched_candidate.resource_id || "-" }}
          </el-descriptions-item>
          <el-descriptions-item label="命中文案">
            {{
              validationResult.matched_candidate.text ||
              validationResult.matched_candidate.content_desc ||
              "-"
            }}
          </el-descriptions-item>
          <el-descriptions-item label="实时 UI 节点 bounds">
            {{
              validationResult.matched_candidate.raw_bounds ||
              validationResult.matched_candidate.bounds ||
              "-"
            }}
          </el-descriptions-item>
          <el-descriptions-item label="命中 class">
            {{
              validationResult.matched_candidate.class_name ||
              validationResult.matched_candidate.class ||
              "-"
            }}
          </el-descriptions-item>
        </el-descriptions>
      </div>
      <template #footer>
        <el-button
          v-if="validationResult?.matched"
          type="primary"
          plain
          :loading="clickTesting"
          @click="clickTestSemanticElement"
        >
          点击试验
        </el-button>
        <el-button @click="validationDialogVisible = false">关闭</el-button>
      </template>
    </el-dialog>

    <el-dialog
      v-model="clickTestDialogVisible"
      title="点击试验结果"
      width="860px"
    >
      <div v-if="clickTestResult" class="click-test-result">
        <el-alert
          type="info"
          :title="clickTestResult.reason || '已点击目标区域'"
          description="请对照点击后截图或真机页面，确认是否进入了预期业务流程。后续可以把这里沉淀成断言规则。"
          show-icon
          :closable="false"
        />
        <div class="click-test-meta">
          <span
            >点击坐标：{{ clickTestResult.tap_point?.x }},
            {{ clickTestResult.tap_point?.y }}</span
          >
          <span>点击区域：{{ clickTestResult.target_raw_bounds || "-" }}</span>
        </div>
        <div class="click-shot-grid">
          <div>
            <strong>点击前</strong>
            <div class="validation-shot-wrap small">
              <img
                :src="clickTestResult.before?.content"
                class="validation-shot"
              />
            </div>
          </div>
          <div>
            <strong>点击后</strong>
            <div class="validation-shot-wrap small">
              <img
                :src="clickTestResult.after?.content"
                class="validation-shot"
              />
            </div>
          </div>
        </div>
      </div>
      <template #footer>
        <el-button type="success" @click="markClickTestVerified"
          >符合预期，确认</el-button
        >
        <el-button @click="clickTestDialogVisible = false">关闭</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { computed, onMounted, ref, watch } from "vue";
import { ElMessage } from "element-plus";
import { ArrowDown } from "@element-plus/icons-vue";
import {
  captureDeviceScreenshot,
  clickTestAppElement,
  clickTestSelection,
  createAppElement,
  getAppElementList,
  getAppProjects,
  getDeviceList,
  getSemanticDictionaryOptions,
  syncVerifiedSemanticElements,
  updateAppElementSemanticStatus,
  validateAppElement,
  uploadAppElementImage,
} from "@/api/app-automation";
import {
  semanticObjectOptions as defaultSemanticObjectOptions,
  semanticPageOptions as defaultSemanticPageOptions,
  semanticRoleOptions as defaultSemanticRoleOptions,
} from "@/config/semanticNaming";

const projects = ref([]);
const devices = ref([]);
const selectedProjectId = ref(null);
const selectedDeviceId = ref(null);
const screenshot = ref("");
const screenshotMeta = ref({});
const capturing = ref(false);
const saving = ref(false);
const elementsLoading = ref(false);
const syncingVerified = ref(false);
const semanticElements = ref([]);
const validatingElementId = ref(null);
const validationDialogVisible = ref(false);
const validationResult = ref(null);
const validationElement = ref(null);
const clickTesting = ref(false);
const clickTestDialogVisible = ref(false);
const clickTestResult = ref(null);
const preSaveClickTesting = ref(false);
const preSaveVerified = ref(false);
const semanticPageOptions = ref([...defaultSemanticPageOptions]);
const semanticObjectOptions = ref([...defaultSemanticObjectOptions]);
const semanticRoleOptions = ref([...defaultSemanticRoleOptions]);

const imageRef = ref(null);
const imageWrapRef = ref(null);
const imageNaturalSize = ref({ width: 0, height: 0 });
const drawing = ref(false);
const dragStart = ref(null);
const selection = ref(null);

const form = ref({
  businessName: "",
  pageName: "",
  role: "按钮",
  note: "",
});

const onlineDevices = computed(() =>
  devices.value.filter((device) => device.status !== "offline"),
);

const selectionBounds = computed(() => {
  if (!selection.value || !imageRef.value) return null;
  const image = imageRef.value;
  const scaleX = (image.naturalWidth || 1) / (image.clientWidth || 1);
  const scaleY = (image.naturalHeight || 1) / (image.clientHeight || 1);
  const x1 = Math.round(
    Math.min(selection.value.x1, selection.value.x2) * scaleX,
  );
  const y1 = Math.round(
    Math.min(selection.value.y1, selection.value.y2) * scaleY,
  );
  const x2 = Math.round(
    Math.max(selection.value.x1, selection.value.x2) * scaleX,
  );
  const y2 = Math.round(
    Math.max(selection.value.y1, selection.value.y2) * scaleY,
  );
  const width = Math.max(0, x2 - x1);
  const height = Math.max(0, y2 - y1);
  if (width < 8 || height < 8) return null;
  return { x1, y1, x2, y2, width, height };
});

const selectionBoundsText = computed(() => {
  const bounds = selectionBounds.value;
  if (!bounds) return "";
  return `[${bounds.x1},${bounds.y1}][${bounds.x2},${bounds.y2}]`;
});

const selectionStyle = computed(() => {
  if (!selection.value) return null;
  const x1 = Math.min(selection.value.x1, selection.value.x2);
  const y1 = Math.min(selection.value.y1, selection.value.y2);
  const width = Math.abs(selection.value.x2 - selection.value.x1);
  const height = Math.abs(selection.value.y2 - selection.value.y1);
  return {
    left: `${x1}px`,
    top: `${y1}px`,
    width: `${width}px`,
    height: `${height}px`,
  };
});

const resetPreSaveVerification = () => {
  preSaveVerified.value = false;
  if (clickTestResult.value?.mode === "pre_save_selection") {
    clickTestResult.value = null;
  }
};

const canSave = computed(
  () =>
    Boolean(selectedProjectId.value) &&
    Boolean(screenshot.value) &&
    Boolean(selectionBounds.value) &&
    Boolean(form.value.businessName.trim()) &&
    Boolean(form.value.pageName.trim()),
);

const canClickTestSelection = computed(
  () =>
    Boolean(selectedDeviceId.value) &&
    Boolean(screenshot.value) &&
    Boolean(selectionBounds.value),
);

const buildOverlayStyle = (bounds, imageInfo) => {
  if (!bounds || !imageInfo?.image_width || !imageInfo?.image_height)
    return null;
  const imageWidth = Number(imageInfo.image_width);
  const imageHeight = Number(imageInfo.image_height);
  if (!imageWidth || !imageHeight) return null;

  const x1 = Number(bounds.x1 || 0);
  const y1 = Number(bounds.y1 || 0);
  const x2 = Number(bounds.x2 || 0);
  const y2 = Number(bounds.y2 || 0);
  return {
    left: `${Math.max(0, Math.min(100, (x1 / imageWidth) * 100))}%`,
    top: `${Math.max(0, Math.min(100, (y1 / imageHeight) * 100))}%`,
    width: `${Math.max(0.2, ((x2 - x1) / imageWidth) * 100)}%`,
    height: `${Math.max(0.2, ((y2 - y1) / imageHeight) * 100)}%`,
  };
};

const validationTargetStyle = computed(() =>
  buildOverlayStyle(
    validationResult.value?.target_bounds,
    validationResult.value?.page_state,
  ),
);

const validationTapStyle = computed(() => {
  const point = validationResult.value?.tap_point;
  const bounds = validationResult.value?.target_bounds;
  if (!point || !bounds) return null;
  const width = Math.max(1, Number(bounds.x2 || 0) - Number(bounds.x1 || 0));
  const height = Math.max(1, Number(bounds.y2 || 0) - Number(bounds.y1 || 0));
  return {
    left: `${((Number(point.x || 0) - Number(bounds.x1 || 0)) / width) * 100}%`,
    top: `${((Number(point.y || 0) - Number(bounds.y1 || 0)) / height) * 100}%`,
  };
});

const deviceLabel = (device) => {
  const name = device.name || device.device_id;
  const model = device.model || device.android_version || "";
  return model ? `${name} / ${model}` : name;
};

const normalizeDictionaryValues = (items = [], fallback = []) => {
  const values = items
    .map((item) => item.value || item.label || item)
    .filter(Boolean);
  return values.length ? values : [...fallback];
};

const querySemanticObjectSuggestions = (queryString, callback) => {
  const keyword = String(queryString || "").trim();
  const candidates = semanticObjectOptions.value
    .filter((item) => !keyword || item.includes(keyword))
    .map((item) => ({ value: item }));

  callback(candidates);
};

const loadSemanticDictionaries = async () => {
  try {
    const params = selectedProjectId.value
      ? { project: selectedProjectId.value }
      : {};
    const { data } = await getSemanticDictionaryOptions(params);
    const options = data.data || {};
    semanticPageOptions.value = normalizeDictionaryValues(
      options.page,
      defaultSemanticPageOptions,
    );
    semanticObjectOptions.value = normalizeDictionaryValues(
      options.object,
      defaultSemanticObjectOptions,
    );
    semanticRoleOptions.value = normalizeDictionaryValues(
      options.role,
      defaultSemanticRoleOptions,
    );

    if (!semanticRoleOptions.value.includes(form.value.role)) {
      form.value.role = semanticRoleOptions.value[0] || "按钮";
    }
  } catch (error) {
    console.warn("语义字典加载失败，已使用前端默认字典:", error);
  }
};

const loadBaseData = async () => {
  const [projectRes, deviceRes] = await Promise.all([
    getAppProjects({ page_size: 100 }),
    getDeviceList({ page_size: 100 }),
  ]);
  projects.value = projectRes.data.results || projectRes.data || [];
  devices.value = deviceRes.data.results || deviceRes.data || [];
  if (!selectedProjectId.value && projects.value.length) {
    selectedProjectId.value = projects.value[0].id;
  }
  if (!selectedDeviceId.value && onlineDevices.value.length) {
    selectedDeviceId.value = onlineDevices.value[0].id;
  }
  await loadSemanticDictionaries();
};

const loadSemanticElements = async () => {
  elementsLoading.value = true;
  try {
    const res = await getAppElementList({
      page_size: 50,
      element_type: "selector",
      search: "semantic_v2",
    });
    semanticElements.value = res.data.results || [];
  } catch (error) {
    ElMessage.error(
      `语义元素加载失败: ${error.response?.data?.msg || error.message}`,
    );
  } finally {
    elementsLoading.value = false;
  }
};

const getSemanticStatusType = (status) => {
  if (status === "已验证") return "success";
  if (status === "需调整") return "danger";
  return "warning";
};

const markSemanticStatus = async (row, status) => {
  if (!row?.id) return;
  try {
    await updateAppElementSemanticStatus(row.id, { status });
    ElMessage.success(`已标记为${status}`);
    await loadSemanticElements();
  } catch (error) {
    ElMessage.error(
      `状态更新失败: ${error.response?.data?.msg || error.message}`,
    );
  }
};

const handleElementAction = async (command, row) => {
  if (command === "recheck") {
    await validateSemanticElement(row);
    return;
  }

  const statusMap = {
    mark_verified: "已验证",
    mark_needs_update: "需调整",
    mark_pending: "待验证",
  };
  const status = statusMap[command];
  if (status) {
    await markSemanticStatus(row, status);
  }
};

const validateSemanticElement = async (row) => {
  if (!row?.id) return;
  if (!selectedDeviceId.value) {
    ElMessage.warning("请先在顶部选择一台在线设备");
    return;
  }

  validatingElementId.value = row.id;
  validationElement.value = row;
  clickTestResult.value = null;
  try {
    const res = await validateAppElement(row.id, {
      device: selectedDeviceId.value,
    });
    validationResult.value = res.data?.data || null;
    validationDialogVisible.value = true;
    if (validationResult.value?.matched) {
      ElMessage.success("元素定位验证通过");
    } else {
      ElMessage.warning("元素定位验证未命中，已标记为需调整");
    }
    await loadSemanticElements();
  } catch (error) {
    ElMessage.error(
      `定位验证失败: ${error.response?.data?.msg || error.message}`,
    );
  } finally {
    validatingElementId.value = null;
  }
};

const clickTestSemanticElement = async () => {
  const element = validationElement.value || validationResult.value?.element;
  if (!element?.id) {
    ElMessage.warning("请先完成一次定位验证");
    return;
  }
  if (!selectedDeviceId.value) {
    ElMessage.warning("请先选择一台在线设备");
    return;
  }

  clickTesting.value = true;
  try {
    const res = await clickTestAppElement(element.id, {
      device: selectedDeviceId.value,
      delay_ms: 500,
    });
    clickTestResult.value = res.data?.data || null;
    clickTestDialogVisible.value = true;
    ElMessage.success("点击试验已完成，请确认业务结果");
  } catch (error) {
    ElMessage.error(
      `点击试验失败: ${error.response?.data?.msg || error.message}`,
    );
  } finally {
    clickTesting.value = false;
  }
};

const clickTestCurrentSelection = async () => {
  if (!canClickTestSelection.value) {
    ElMessage.warning("请先选择设备并框选一个元素区域");
    return;
  }

  preSaveClickTesting.value = true;
  preSaveVerified.value = false;
  try {
    const res = await clickTestSelection({
      device: selectedDeviceId.value,
      bounds: selectionBounds.value,
      screenshot: {
        natural_width: imageNaturalSize.value.width,
        natural_height: imageNaturalSize.value.height,
        device_id: screenshotMeta.value.device_id || "",
        filename: screenshotMeta.value.filename || "",
        timestamp: screenshotMeta.value.timestamp || null,
      },
      delay_ms: 500,
    });
    clickTestResult.value = {
      ...(res.data?.data || {}),
      mode: "pre_save_selection",
    };
    clickTestDialogVisible.value = true;
    ElMessage.success("点击验证已完成，请确认业务结果");
  } catch (error) {
    ElMessage.error(
      `点击验证失败: ${error.response?.data?.msg || error.message}`,
    );
  } finally {
    preSaveClickTesting.value = false;
  }
};

const markClickTestVerified = async () => {
  if (clickTestResult.value?.mode === "pre_save_selection") {
    preSaveVerified.value = true;
    clickTestDialogVisible.value = false;
    ElMessage.success("已确认点击结果，保存后将标为已验证");
    return;
  }

  const element = validationElement.value || clickTestResult.value?.element;
  if (!element?.id) return;
  await markSemanticStatus(element, "已验证");
  clickTestDialogVisible.value = false;
};

const syncVerifiedFromHistory = async () => {
  syncingVerified.value = true;
  try {
    const res = await syncVerifiedSemanticElements({
      project: selectedProjectId.value,
      execution_limit: 300,
    });
    const data = res.data?.data || {};
    ElMessage.success(`同步完成，更新 ${data.updated_count || 0} 个元素`);
    await loadSemanticElements();
  } catch (error) {
    ElMessage.error(`同步失败: ${error.response?.data?.msg || error.message}`);
  } finally {
    syncingVerified.value = false;
  }
};

const captureScreen = async () => {
  if (!selectedDeviceId.value) {
    ElMessage.warning("请先选择设备");
    return;
  }
  capturing.value = true;
  try {
    const res = await captureDeviceScreenshot(selectedDeviceId.value);
    const data = res.data?.data || {};
    screenshot.value = data.content || "";
    screenshotMeta.value = data;
    clearSelection();
    if (!screenshot.value) {
      throw new Error("截图数据为空");
    }
    ElMessage.success("截图已刷新");
  } catch (error) {
    ElMessage.error(`截图失败: ${error.response?.data?.msg || error.message}`);
  } finally {
    capturing.value = false;
  }
};

const handleImageLoad = () => {
  imageNaturalSize.value = {
    width: imageRef.value?.naturalWidth || 0,
    height: imageRef.value?.naturalHeight || 0,
  };
};

const getLocalPoint = (event) => {
  if (!imageWrapRef.value || !imageRef.value) return null;
  const rect = imageWrapRef.value.getBoundingClientRect();
  const x = Math.max(
    0,
    Math.min(
      event.clientX - rect.left + imageWrapRef.value.scrollLeft,
      imageRef.value.clientWidth,
    ),
  );
  const y = Math.max(
    0,
    Math.min(
      event.clientY - rect.top + imageWrapRef.value.scrollTop,
      imageRef.value.clientHeight,
    ),
  );
  return { x, y };
};

const startSelection = (event) => {
  if (event.button !== 0 || !screenshot.value) return;
  const point = getLocalPoint(event);
  if (!point) return;
  drawing.value = true;
  dragStart.value = point;
  selection.value = { x1: point.x, y1: point.y, x2: point.x, y2: point.y };
  resetPreSaveVerification();
  event.preventDefault();
};

const moveSelection = (event) => {
  if (!drawing.value || !dragStart.value) return;
  const point = getLocalPoint(event);
  if (!point) return;
  selection.value = {
    x1: dragStart.value.x,
    y1: dragStart.value.y,
    x2: point.x,
    y2: point.y,
  };
  event.preventDefault();
};

const finishSelection = (event) => {
  if (!drawing.value) return;
  const point = getLocalPoint(event) || dragStart.value;
  selection.value = {
    x1: dragStart.value.x,
    y1: dragStart.value.y,
    x2: point.x,
    y2: point.y,
  };
  drawing.value = false;
  dragStart.value = null;
  if (!selectionBounds.value) {
    selection.value = null;
  }
  resetPreSaveVerification();
};

const clearSelection = () => {
  drawing.value = false;
  dragStart.value = null;
  selection.value = null;
  resetPreSaveVerification();
};

const slugify = (value) => {
  const text = String(value || "").trim();
  const ascii = text
    .replace(/([a-z0-9])([A-Z])/g, "$1_$2")
    .replace(/[^a-zA-Z0-9_\u4e00-\u9fa5]+/g, "_")
    .replace(/^_+|_+$/g, "")
    .toLowerCase();
  return ascii || `element_${Date.now()}`;
};

const cropSelectionBlob = async () => {
  const bounds = selectionBounds.value;
  const image = imageRef.value;
  if (!bounds || !image) return null;
  const canvas = document.createElement("canvas");
  canvas.width = bounds.width;
  canvas.height = bounds.height;
  const ctx = canvas.getContext("2d");
  if (!ctx) return null;
  ctx.drawImage(
    image,
    bounds.x1,
    bounds.y1,
    bounds.width,
    bounds.height,
    0,
    0,
    bounds.width,
    bounds.height,
  );
  return new Promise((resolve) => canvas.toBlob(resolve, "image/png"));
};

const uploadSelectionPreview = async (technicalName) => {
  try {
    const blob = await cropSelectionBlob();
    if (!blob) return {};
    const file = new File([blob], `${technicalName}.png`, {
      type: "image/png",
    });
    const res = await uploadAppElementImage(file, "semantic_v2");
    if (res.data?.success) {
      return {
        preview_image_path: res.data.data?.image_path || "",
        preview_file_hash: res.data.data?.file_hash || "",
      };
    }
  } catch (error) {
    // 预览图失败不阻塞元素入库。
    return {
      preview_upload_error: error.response?.data?.msg || error.message,
    };
  }
  return {};
};

const saveSemanticElement = async () => {
  if (!canSave.value) {
    ElMessage.warning("请选择项目、截图框选区域，并选择页面名称和业务对象");
    return;
  }
  saving.value = true;
  try {
    const bounds = selectionBounds.value;
    const baseKey = slugify(
      `${form.value.pageName}_${form.value.businessName}`,
    );
    const technicalName = `semantic_v2.${baseKey}.${Date.now()}`;
    const previewConfig = await uploadSelectionPreview(
      technicalName.replace(/\./g, "_"),
    );
    const semanticStatus = preSaveVerified.value ? "已验证" : "待验证";
    const statusTag = semanticStatus;
    const payload = {
      project: selectedProjectId.value,
      name: technicalName,
      element_type: "selector",
      tags: ["semantic_v2", "人工框选", statusTag, form.value.role],
      config: {
        strategy: "manual_bounds",
        ai_managed: false,
        semantic_version: "v2",
        semantic_status: semanticStatus,
        semantic_status_source: preSaveVerified.value
          ? "pre_save_click_test"
          : "manual_entry",
        description: form.value.businessName.trim(),
        page_name: form.value.pageName.trim(),
        semantic_page: form.value.pageName.trim(),
        semantic_object: form.value.businessName.trim(),
        semantic_role: form.value.role,
        manual_note:
          form.value.note.trim() || "通过语义元素工作台截图框选生成。",
        interaction_role: form.value.role,
        locator_key: baseKey,
        resource_id: "",
        class: "manual.bounds",
        text: form.value.businessName.trim(),
        content_desc: "",
        hint: "",
        bounds: selectionBoundsText.value,
        bounds_rect: bounds,
        screenshot: {
          device_id: screenshotMeta.value.device_id || "",
          filename: screenshotMeta.value.filename || "",
          timestamp: screenshotMeta.value.timestamp || null,
          natural_width: imageNaturalSize.value.width,
          natural_height: imageNaturalSize.value.height,
        },
        pre_save_click_validation: preSaveVerified.value
          ? {
              verified: true,
              target_bounds: clickTestResult.value?.target_bounds || null,
              target_raw_bounds: clickTestResult.value?.target_raw_bounds || "",
              tap_point: clickTestResult.value?.tap_point || null,
              validated_device:
                clickTestResult.value?.validated_device ||
                selectedDeviceId.value,
              validated_at: clickTestResult.value?.validated_at || null,
            }
          : null,
        ...previewConfig,
      },
    };
    await createAppElement(payload);
    ElMessage.success(
      preSaveVerified.value
        ? "已保存并标为已验证"
        : "已保存到 semantic_v2 语义库，状态为待验证",
    );
    form.value.businessName = "";
    form.value.note = "";
    clearSelection();
    preSaveVerified.value = false;
    clickTestResult.value = null;
    await loadSemanticElements();
  } catch (error) {
    ElMessage.error(
      `保存失败: ${error.response?.data?.msg || JSON.stringify(error.response?.data || {}) || error.message}`,
    );
  } finally {
    saving.value = false;
  }
};

onMounted(async () => {
  await loadBaseData();
  await loadSemanticElements();
});

watch(selectedProjectId, () => {
  loadSemanticDictionaries();
});
</script>

<style lang="scss" scoped>
.semantic-workbench {
  min-height: calc(100vh - 92px);
  padding: 20px;
  background:
    radial-gradient(circle at 12% 8%, rgba(34, 197, 94, 0.12), transparent 28%),
    linear-gradient(135deg, #f8fafc 0%, #eef6ff 100%);
}

.semantic-hero {
  display: flex;
  justify-content: space-between;
  gap: 16px;
  align-items: flex-start;
  padding: 22px 24px;
  margin-bottom: 16px;
  border: 1px solid rgba(148, 163, 184, 0.24);
  border-radius: 18px;
  background: rgba(255, 255, 255, 0.9);
  box-shadow: 0 18px 48px rgba(15, 23, 42, 0.08);
}

.eyebrow {
  margin: 0 0 6px;
  color: #0f766e;
  font-size: 12px;
  font-weight: 800;
  letter-spacing: 0.12em;
  text-transform: uppercase;
}

h1 {
  margin: 0;
  color: #0f172a;
  font-size: 28px;
}

.subtitle {
  max-width: 760px;
  margin: 8px 0 0;
  color: #64748b;
  line-height: 1.7;
}

.workbench-grid {
  display: grid;
  grid-template-columns: minmax(0, 1.45fr) 420px;
  gap: 16px;
  align-items: start;
}

.screen-card,
.editor-card,
.library-card {
  border-radius: 16px;
  border: 1px solid rgba(148, 163, 184, 0.24);
}

.library-card {
  margin-top: 16px;
}

.card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;

  strong {
    display: block;
    color: #0f172a;
    font-size: 16px;
  }

  span {
    display: block;
    margin-top: 4px;
    color: #64748b;
    font-size: 12px;
  }
}

.header-actions {
  display: flex;
  gap: 8px;
  align-items: center;
  flex-shrink: 0;
}

.toolbar-form {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px;
  margin-bottom: 14px;
}

.empty-shot {
  min-height: 520px;
  display: flex;
  align-items: center;
  justify-content: center;
  border: 1px dashed #cbd5e1;
  border-radius: 14px;
  background: #f8fafc;
}

.shot-wrap {
  position: relative;
  max-height: 680px;
  overflow: auto;
  border-radius: 18px;
  background: #020617;
  cursor: crosshair;
  user-select: none;
}

.device-shot {
  display: block;
  width: 100%;
  height: auto;
  pointer-events: none;
}

.selection-box {
  position: absolute;
  box-sizing: border-box;
  border: 3px solid #f97316;
  background: rgba(249, 115, 22, 0.16);
  box-shadow: 0 0 0 2px rgba(255, 255, 255, 0.9);
  pointer-events: none;

  span {
    position: absolute;
    left: 0;
    top: -32px;
    max-width: 240px;
    padding: 5px 10px;
    border-radius: 999px;
    color: #fff;
    background: rgba(15, 23, 42, 0.92);
    font-size: 12px;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }
}

.semantic-form {
  :deep(.el-alert) {
    margin-top: 14px;
  }
}

.meta-panel {
  display: grid;
  gap: 10px;
  padding: 14px;
  border-radius: 14px;
  background: #f8fafc;
  border: 1px solid #e2e8f0;

  div {
    display: flex;
    justify-content: space-between;
    gap: 12px;
  }

  span {
    color: #64748b;
  }

  strong {
    color: #0f172a;
    font-family: Consolas, Monaco, monospace;
    font-size: 12px;
    text-align: right;
  }
}

.form-actions {
  display: flex;
  justify-content: flex-end;
  gap: 10px;
  margin-top: 16px;
}

.element-title {
  color: #0f172a;
  font-weight: 700;
}

.element-sub {
  margin-top: 4px;
  color: #64748b;
  font-family: Consolas, Monaco, monospace;
  font-size: 12px;
}

.tag-item {
  margin-right: 6px;
}

.row-actions {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  white-space: nowrap;
}

.validation-result {
  display: grid;
  gap: 14px;
}

.validation-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 10px;

  div {
    padding: 12px;
    border-radius: 10px;
    background: #f8fafc;
    border: 1px solid #e2e8f0;
  }

  span {
    display: block;
    margin-bottom: 6px;
    color: #64748b;
    font-size: 12px;
  }

  strong {
    color: #0f172a;
    word-break: break-all;
  }
}

.validation-shot-wrap {
  max-height: 360px;
  overflow: auto;
  border-radius: 12px;
  background: #020617;
  border: 1px solid #e2e8f0;

  &.small {
    max-height: 280px;
  }
}

.validation-shot-stage {
  position: relative;
  display: inline-block;
  min-width: 100%;
}

.validation-shot {
  display: block;
  width: 100%;
  height: auto;
}

.validation-target-box {
  position: absolute;
  border: 3px solid #f59e0b;
  border-radius: 10px;
  box-shadow:
    0 0 0 2px rgba(255, 255, 255, 0.85),
    0 0 18px rgba(245, 158, 11, 0.55);
  pointer-events: none;

  span {
    position: absolute;
    left: 0;
    top: -28px;
    padding: 3px 8px;
    border-radius: 999px;
    background: #f59e0b;
    color: #fff;
    font-size: 12px;
    white-space: nowrap;
  }
}

.tap-point {
  position: absolute;
  width: 14px;
  height: 14px;
  transform: translate(-50%, -50%);
  border-radius: 50%;
  background: #ef4444;
  border: 2px solid #fff;
  box-shadow: 0 0 0 4px rgba(239, 68, 68, 0.28);
}

.click-test-result {
  display: grid;
  gap: 14px;
}

.click-test-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  color: #475569;
  font-size: 13px;
}

.click-shot-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 14px;

  strong {
    display: block;
    margin-bottom: 8px;
    color: #0f172a;
  }
}

@media (max-width: 1180px) {
  .workbench-grid {
    grid-template-columns: 1fr;
  }

  .semantic-hero {
    flex-direction: column;
  }

  .click-shot-grid {
    grid-template-columns: 1fr;
  }
}
</style>
