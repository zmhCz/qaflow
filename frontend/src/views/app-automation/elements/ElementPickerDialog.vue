<template>
  <el-dialog
    v-model="visible"
    title="可视化元素拾取器"
    width="90%"
    :close-on-click-modal="false"
    @close="handleClose"
  >
    <div class="element-picker-container" v-loading="loading">
      <!-- 左侧：设备截图 + 元素边框叠加 -->
      <div class="picker-left">
        <div class="device-screen-wrapper">
          <div v-if="!screenshotData" class="empty-state">
            <el-empty description="请先选择设备并获取截图" />
          </div>

          <div v-else class="device-screen" ref="screenContainer">
            <!-- 截图 -->
            <img
              ref="screenshot"
              :src="screenshotData"
              class="screenshot-image"
              @load="onImageLoad"
            />

            <!-- SVG 元素边框叠加层 -->
            <svg
              v-if="elements.length > 0"
              class="element-overlay"
              :width="imageWidth"
              :height="imageHeight"
              @click="handleScreenClick"
            >
              <!-- 绘制所有元素的边框 -->
              <g
                v-for="elem in elements"
                :key="elem.resource_id + elem.bounds.x1 + elem.bounds.y1"
              >
                <rect
                  :x="elem.bounds.x1"
                  :y="elem.bounds.y1"
                  :width="elem.bounds.width"
                  :height="elem.bounds.height"
                  :class="[
                    'element-rect',
                    { selected: isSelected(elem), interactive: elem.clickable },
                  ]"
                  @click.stop="selectElement(elem)"
                />
                <!-- 悬浮时显示元素名称 -->
                <title>{{ elem.name }}</title>
              </g>
            </svg>
          </div>
        </div>

        <!-- 操作工具栏 -->
        <div class="toolbar">
          <el-space>
            <el-select
              v-model="selectedDeviceId"
              placeholder="选择设备"
              style="width: 200px"
              @change="onDeviceChange"
            >
              <el-option
                v-for="device in devices"
                :key="device.device_id"
                :label="device.name || device.device_id"
                :value="device.device_id"
                :disabled="device.status === 'offline'"
              >
                <span>{{ device.name || device.device_id }}</span>
                <el-tag
                  v-if="device.status === 'offline'"
                  type="danger"
                  size="small"
                  style="margin-left: 8px"
                  >离线</el-tag
                >
              </el-option>
            </el-select>

            <el-button
              type="primary"
              :icon="Refresh"
              @click="refreshScreenshot"
              :disabled="!selectedDeviceId"
            >
              刷新截图
            </el-button>

            <el-button :icon="View" @click="toggleElementBorders">
              {{ showBorders ? "隐藏边框" : "显示边框" }}
            </el-button>
          </el-space>
        </div>
      </div>

      <!-- 右侧：元素详情 + Locator 推荐 -->
      <div class="picker-right">
        <div v-if="!selectedElement" class="empty-hint">
          <el-icon :size="48" color="#909399"><Search /></el-icon>
          <p>点击截图上的元素以选中</p>
        </div>

        <div v-else class="element-details">
          <!-- 元素基本信息 -->
          <el-descriptions title="元素信息" :column="1" border>
            <el-descriptions-item label="显示名称">
              {{ selectedElement.name }}
            </el-descriptions-item>
            <el-descriptions-item label="Resource ID">
              <el-text v-if="selectedElement.resource_id" type="primary">
                {{ selectedElement.resource_id }}
              </el-text>
              <el-text v-else type="info">无</el-text>
            </el-descriptions-item>
            <el-descriptions-item label="Text">
              {{ selectedElement.text || "-" }}
            </el-descriptions-item>
            <el-descriptions-item label="Content Desc">
              {{ selectedElement.content_desc || "-" }}
            </el-descriptions-item>
            <el-descriptions-item label="Class">
              {{ selectedElement.class_name }}
            </el-descriptions-item>
            <el-descriptions-item label="Bounds">
              {{ selectedElement.raw_bounds }}
            </el-descriptions-item>
            <el-descriptions-item label="可交互">
              <el-tag
                v-if="selectedElement.clickable"
                type="success"
                size="small"
                >可点击</el-tag
              >
              <el-tag
                v-if="selectedElement.focusable"
                type="success"
                size="small"
                >可聚焦</el-tag
              >
              <el-tag
                v-if="selectedElement.scrollable"
                type="success"
                size="small"
                >可滚动</el-tag
              >
              <span
                v-if="
                  !selectedElement.clickable &&
                  !selectedElement.focusable &&
                  !selectedElement.scrollable
                "
                >-</span
              >
            </el-descriptions-item>
          </el-descriptions>

          <!-- Locator 策略推荐 -->
          <div class="locator-strategies" v-if="locatorStrategies.length > 0">
            <h3>定位策略推荐</h3>
            <el-radio-group v-model="selectedLocatorType" class="strategy-list">
              <div
                v-for="strategy in locatorStrategies"
                :key="strategy.type"
                class="strategy-item"
              >
                <el-radio :label="strategy.type" border>
                  <div class="strategy-content">
                    <div class="strategy-header">
                      <span class="strategy-type">{{ strategy.type }}</span>
                      <el-progress
                        :percentage="Math.round(strategy.confidence * 100)"
                        :color="getConfidenceColor(strategy.confidence)"
                        :stroke-width="6"
                        style="width: 100px; margin-left: 12px"
                      />
                    </div>
                    <div class="strategy-value">{{ strategy.value }}</div>
                    <div class="strategy-reason">{{ strategy.reason }}</div>
                  </div>
                </el-radio>
              </div>
            </el-radio-group>
          </div>

          <!-- 保存表单 -->
          <el-form
            :model="elementForm"
            label-width="100px"
            style="margin-top: 20px"
          >
            <el-form-item label="元素名称" required>
              <el-input
                v-model="elementForm.name"
                placeholder="请输入元素名称"
              />
            </el-form-item>
            <el-form-item label="描述">
              <el-input
                v-model="elementForm.description"
                type="textarea"
                :rows="2"
                placeholder="选填"
              />
            </el-form-item>
            <el-form-item label="所属项目" required>
              <el-select
                v-model="elementForm.project_id"
                placeholder="请选择项目"
                style="width: 100%"
              >
                <el-option
                  v-for="project in projects"
                  :key="project.id"
                  :label="project.name"
                  :value="project.id"
                />
              </el-select>
            </el-form-item>
          </el-form>
        </div>
      </div>
    </div>

    <template #footer>
      <el-button @click="handleClose">取消</el-button>
      <el-button
        type="primary"
        @click="saveElement"
        :disabled="
          !selectedElement || !elementForm.name || !elementForm.project_id
        "
      >
        保存元素
      </el-button>
    </template>
  </el-dialog>
</template>

<script setup>
import { ref, computed, watch } from "vue";
import { ElMessage } from "element-plus";
import { Refresh, View, Search } from "@element-plus/icons-vue";
import axios from "axios";

const props = defineProps({
  modelValue: {
    type: Boolean,
    default: false,
  },
  projects: {
    type: Array,
    default: () => [],
  },
});

const emit = defineEmits(["update:modelValue", "saved"]);

// 响应式状态
const visible = computed({
  get: () => props.modelValue,
  set: (val) => emit("update:modelValue", val),
});

const loading = ref(false);
const devices = ref([]);
const selectedDeviceId = ref("");
const screenshotData = ref("");
const elements = ref([]);
const selectedElement = ref(null);
const locatorStrategies = ref([]);
const selectedLocatorType = ref("");
const showBorders = ref(true);
const imageWidth = ref(0);
const imageHeight = ref(0);

const elementForm = ref({
  name: "",
  description: "",
  project_id: null,
});

// 获取设备列表
const loadDevices = async () => {
  try {
    const res = await axios.get("/api/app-automation/devices/");
    devices.value = res.data.results || res.data;
  } catch (error) {
    ElMessage.error("获取设备列表失败");
  }
};

// 刷新截图和 UI 层级
const refreshScreenshot = async () => {
  if (!selectedDeviceId.value) {
    ElMessage.warning("请先选择设备");
    return;
  }

  loading.value = true;
  try {
    const res = await axios.post(
      `/api/app-automation/devices/${getDeviceId()}/page-state/`,
    );

    if (res.data.success) {
      const data = res.data.data;
      screenshotData.value = data.content;
      elements.value = data.candidates || [];

      ElMessage.success(`截图获取成功，识别到 ${elements.value.length} 个元素`);
    } else {
      ElMessage.error(res.data.msg || "截图获取失败");
    }
  } catch (error) {
    ElMessage.error(
      "截图获取失败：" + (error.response?.data?.msg || error.message),
    );
  } finally {
    loading.value = false;
  }
};

// 获取当前设备的数据库 ID（用于 API 调用）
const getDeviceId = () => {
  const device = devices.value.find(
    (d) => d.device_id === selectedDeviceId.value,
  );
  return device?.id;
};

// 选中元素
const selectElement = async (element) => {
  selectedElement.value = element;

  // 调用后端分析接口获取 locator 推荐
  try {
    const res = await axios.post(
      "/api/app-automation/elements/analyze-for-picker/",
      {
        element_data: element,
      },
    );

    if (res.data.success) {
      locatorStrategies.value = res.data.data.strategies || [];

      // 默认选中最佳策略
      if (locatorStrategies.value.length > 0) {
        selectedLocatorType.value = locatorStrategies.value[0].type;
      }

      // 自动填充元素名称
      elementForm.value.name = res.data.data.display_name || element.name || "";
    }
  } catch (error) {
    console.error("分析元素失败", error);
    // 不影响选中操作，只是没有推荐
  }
};

// 判断元素是否被选中
const isSelected = (element) => {
  if (!selectedElement.value) return false;
  return (
    element.resource_id === selectedElement.value.resource_id &&
    element.bounds.x1 === selectedElement.value.bounds.x1 &&
    element.bounds.y1 === selectedElement.value.bounds.y1
  );
};

// 图片加载完成
const onImageLoad = (e) => {
  imageWidth.value = e.target.naturalWidth;
  imageHeight.value = e.target.naturalHeight;
};

// 处理截图点击（用于点击坐标拾取）
const handleScreenClick = (e) => {
  // 这里可以扩展为坐标点击定位
};

// 切换边框显示
const toggleElementBorders = () => {
  showBorders.value = !showBorders.value;
};

// 设备切换
const onDeviceChange = () => {
  screenshotData.value = "";
  elements.value = [];
  selectedElement.value = null;
  refreshScreenshot();
};

// 保存元素
const saveElement = async () => {
  if (!selectedElement.value) {
    ElMessage.warning("请先选择一个元素");
    return;
  }

  if (!elementForm.value.name) {
    ElMessage.warning("请输入元素名称");
    return;
  }

  if (!elementForm.value.project_id) {
    ElMessage.warning("请选择所属项目");
    return;
  }

  loading.value = true;
  try {
    const res = await axios.post(
      "/api/app-automation/elements/create-from-picker/",
      {
        project_id: elementForm.value.project_id,
        name: elementForm.value.name,
        description: elementForm.value.description,
        element_data: selectedElement.value,
        preferred_locator_type: selectedLocatorType.value,
      },
    );

    if (res.data.success) {
      ElMessage.success("元素创建成功");
      emit("saved", res.data.data.element);
      handleClose();
    } else {
      ElMessage.error(res.data.msg || "创建失败");
    }
  } catch (error) {
    ElMessage.error(
      "创建元素失败：" + (error.response?.data?.msg || error.message),
    );
  } finally {
    loading.value = false;
  }
};

// 获取可靠性颜色
const getConfidenceColor = (confidence) => {
  if (confidence >= 0.8) return "#67c23a";
  if (confidence >= 0.6) return "#e6a23c";
  return "#f56c6c";
};

// 关闭对话框
const handleClose = () => {
  visible.value = false;
  selectedElement.value = null;
  locatorStrategies.value = [];
  elementForm.value = { name: "", description: "", project_id: null };
};

// 监听对话框打开
watch(visible, (newVal) => {
  if (newVal) {
    loadDevices();
  }
});
</script>

<style scoped>
.element-picker-container {
  display: flex;
  gap: 20px;
  height: 70vh;
}

.picker-left {
  flex: 1.5;
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.picker-right {
  flex: 1;
  overflow-y: auto;
  padding: 0 8px;
}

.device-screen-wrapper {
  flex: 1;
  border: 1px solid #dcdfe6;
  border-radius: 4px;
  overflow: auto;
  background: #f5f7fa;
  display: flex;
  align-items: center;
  justify-content: center;
}

.device-screen {
  position: relative;
  display: inline-block;
}

.screenshot-image {
  display: block;
  max-width: 100%;
  height: auto;
}

.element-overlay {
  position: absolute;
  top: 0;
  left: 0;
  pointer-events: all;
}

.element-rect {
  fill: rgba(64, 158, 255, 0.1);
  stroke: #409eff;
  stroke-width: 2;
  cursor: pointer;
  transition: all 0.2s;
}

.element-rect:hover {
  fill: rgba(64, 158, 255, 0.2);
  stroke-width: 3;
}

.element-rect.selected {
  fill: rgba(103, 194, 58, 0.2);
  stroke: #67c23a;
  stroke-width: 3;
}

.element-rect.interactive {
  stroke: #e6a23c;
}

.toolbar {
  padding: 12px;
  background: #fff;
  border: 1px solid #dcdfe6;
  border-radius: 4px;
}

.empty-state {
  text-align: center;
  padding: 40px;
  color: #909399;
}

.empty-hint {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  height: 100%;
  color: #909399;
}

.empty-hint p {
  margin-top: 16px;
  font-size: 14px;
}

.element-details {
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.locator-strategies h3 {
  font-size: 16px;
  font-weight: 600;
  margin-bottom: 12px;
  color: #303133;
}

.strategy-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
  width: 100%;
}

.strategy-item {
  width: 100%;
}

.strategy-item :deep(.el-radio) {
  width: 100%;
  height: auto;
  padding: 12px;
}

.strategy-item :deep(.el-radio__label) {
  width: 100%;
  padding-left: 8px;
}

.strategy-content {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.strategy-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.strategy-type {
  font-weight: 600;
  color: #409eff;
  font-size: 14px;
}

.strategy-value {
  font-family: "Courier New", monospace;
  color: #606266;
  font-size: 13px;
  word-break: break-all;
}

.strategy-reason {
  font-size: 12px;
  color: #909399;
}
</style>
