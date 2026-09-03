<template>
  <div class="recording-studio">
    <section class="hero-card">
      <div>
        <p class="eyebrow">APP 自动化</p>
        <h1>脚本录制器</h1>
        <p class="subtitle">
          直接操作手机，平台通过 UI 状态变化生成可编辑的 Action
          Atom，后续可拼装为稳定测试用例。
        </p>
      </div>
      <el-tag
        v-if="sessionId"
        size="large"
        :type="isRecording ? 'danger' : 'warning'"
      >
        {{ isRecording ? "观察录制中" : "已暂停" }}
      </el-tag>
    </section>

    <div class="studio-grid">
      <el-card class="screen-card" shadow="never">
        <template #header>
          <div class="toolbar">
            <el-select
              v-model="selectedDeviceId"
              placeholder="选择设备"
              class="toolbar-select"
              :disabled="!!sessionId"
            >
              <el-option
                v-for="device in devices"
                :key="device.id"
                :label="device.name || device.device_id"
                :value="device.id"
                :disabled="device.status === 'offline'"
              />
            </el-select>

            <el-select
              v-model="selectedProjectId"
              placeholder="选择项目"
              class="toolbar-select"
              :disabled="!!sessionId"
            >
              <el-option
                v-for="project in projects"
                :key="project.id"
                :label="project.name"
                :value="project.id"
              />
            </el-select>

            <el-button
              v-if="!sessionId"
              type="primary"
              :icon="VideoCamera"
              :loading="loading"
              :disabled="!selectedDeviceId || !selectedProjectId"
              @click="startRecording"
            >
              开始录制
            </el-button>

            <template v-else>
              <el-button
                :type="isRecording ? 'warning' : 'success'"
                :icon="isRecording ? VideoPause : VideoPlay"
                @click="togglePause"
              >
                {{ isRecording ? "暂停" : "继续" }}
              </el-button>
              <el-button
                :icon="Refresh"
                :loading="refreshing"
                @click="refreshScreenshot"
              >
                刷新画面
              </el-button>
              <el-switch
                v-model="livePreviewEnabled"
                inline-prompt
                active-text="实时"
                inactive-text="手动"
                @change="handleLivePreviewToggle"
              />
              <el-select
                v-model="livePreviewIntervalMs"
                size="small"
                class="live-rate-select"
                :disabled="!livePreviewEnabled"
              >
                <el-option label="0.8s" :value="800" />
                <el-option label="1.2s" :value="1200" />
                <el-option label="2s" :value="2000" />
              </el-select>
              <el-button type="danger" :icon="Close" @click="stopRecording">
                结束
              </el-button>
            </template>
          </div>
        </template>

        <div class="recorder-tip">
          <strong>推荐方式：</strong>开始后直接在手机上操作。平台会轮询 UI
          树并记录最小操作单元；如果漏了一步，可在预览画面点击进行手动补录。
        </div>

        <div v-if="pendingInput" class="pending-input-card">
          <div class="pending-input-copy">
            <strong>检测到输入框：</strong>
            <span>{{ pendingInputLabel }}</span>
            <small
              >输入内容无法从系统键盘稳定读取，请确认刚才输入的文本。</small
            >
          </div>
          <div class="pending-input-actions">
            <el-input
              v-model="pendingInputText"
              clearable
              placeholder="填写刚才在手机里输入的文本"
              @keyup.enter="confirmPendingInput"
            />
            <el-button
              type="primary"
              :disabled="!pendingInputText.trim()"
              @click="confirmPendingInput"
            >
              确认输入
            </el-button>
          </div>
        </div>

        <div v-if="pendingDraft" class="pending-input-card">
          <div class="pending-input-copy">
            <strong>待确认步骤：</strong>
            <span>{{ pendingDraftLabel }}</span>
            <small
              >预览区产生的操作不会自动入库，确认后才加入右侧 Action
              Atoms。</small
            >
          </div>
          <div class="pending-input-actions">
            <el-input
              v-if="pendingDraft.type === 'input'"
              v-model="pendingDraft.text"
              clearable
              placeholder="输入文本"
              @keyup.enter="confirmPendingDraft"
            />
            <el-button type="primary" @click="confirmPendingDraft">
              确认加入
            </el-button>
            <el-button @click="discardPendingDraft"> 丢弃 </el-button>
          </div>
        </div>

        <div class="screen-shell" v-loading="loading">
          <div v-if="!screenshotData" class="empty-screen">
            <el-icon :size="68"><Monitor /></el-icon>
            <p>选择设备和项目后开始录制</p>
          </div>

          <div v-else class="device-frame">
            <canvas
              ref="screenCanvas"
              @mousedown="handleMouseDown"
              @mouseup="handleMouseUp"
            />
          </div>
        </div>

        <div v-if="sessionId" class="status-strip">
          <el-text>时长 {{ formatDuration(recordingDuration) }}</el-text>
          <el-divider direction="vertical" />
          <el-text>原子 {{ interactions.length }}</el-text>
          <el-divider direction="vertical" />
          <el-text :type="isRecording ? 'success' : 'warning'">
            {{ observeStatusText }}
          </el-text>
          <el-divider direction="vertical" />
          <el-text :type="livePreviewError ? 'danger' : 'info'">
            {{ livePreviewStatusText }}
          </el-text>
          <el-button
            size="small"
            link
            type="primary"
            @click="recordManualInput"
          >
            补录输入
          </el-button>
          <el-button size="small" link type="primary" @click="recordManualWait">
            补录等待
          </el-button>
        </div>
      </el-card>

      <el-card class="atoms-card" shadow="never">
        <template #header>
          <div class="panel-header">
            <div>
              <h2>Action Atoms</h2>
              <span>每一条都是后续可复用、可拼装的最小脚本单元</span>
            </div>
            <el-button
              v-if="interactions.length"
              size="small"
              :icon="Delete"
              :disabled="isRecording"
              @click="clearHistory"
            >
              清空
            </el-button>
          </div>
        </template>

        <div v-if="interactions.length" class="atom-list">
          <article
            v-for="(atom, index) in interactions"
            :key="atom.id || `${atom.timestamp}-${index}`"
            class="atom-item"
          >
            <div class="atom-index">{{ index + 1 }}</div>
            <div class="atom-main">
              <div class="atom-topline">
                <el-tag size="small" :type="getAtomTagType(atom.type)">
                  {{ getAtomTypeLabel(atom.type) }}
                </el-tag>
                <span class="atom-source">{{ atom.source || "manual" }}</span>
                <span v-if="atom.confidence" class="atom-confidence">
                  {{ Math.round(Number(atom.confidence) * 100) }}%
                </span>
              </div>

              <el-input
                v-model="atom.name"
                class="atom-name-input"
                size="small"
                placeholder="步骤名称"
                :disabled="isRecording"
                @change="markDirty"
              />

              <el-input
                v-if="atom.type === 'input'"
                v-model="getAtomInput(atom).value"
                class="atom-input-value"
                size="small"
                placeholder="输入文本"
                :disabled="isRecording"
                @change="onInputAtomChanged(atom)"
              />

              <div class="atom-meta">
                {{ formatAtom(atom) }}
              </div>
            </div>

            <el-button
              link
              type="danger"
              :icon="Delete"
              :disabled="isRecording"
              @click="removeInteraction(index)"
            />
          </article>
        </div>

        <el-empty
          v-else
          description="暂无录制步骤。开始录制后直接操作手机，或点击左侧预览补录。"
        />
      </el-card>
    </div>

    <el-dialog v-model="saveDialogVisible" title="保存为测试用例" width="520px">
      <el-form :model="saveForm" label-width="96px">
        <el-form-item label="用例名称" required>
          <el-input v-model="saveForm.name" placeholder="请输入用例名称" />
        </el-form-item>
        <el-form-item label="描述">
          <el-input
            v-model="saveForm.description"
            type="textarea"
            :rows="3"
            placeholder="可选，建议说明录制场景和关键前置条件"
          />
        </el-form-item>
        <el-form-item label="自动等待">
          <el-switch
            v-model="saveForm.auto_insert_wait"
            active-text="按操作间隔插入等待"
            inactive-text="不插入"
          />
        </el-form-item>
      </el-form>

      <template #footer>
        <el-button @click="saveDialogVisible = false">取消</el-button>
        <el-button
          type="primary"
          :loading="loading"
          :disabled="!saveForm.name || !interactions.length"
          @click="saveTestCase"
        >
          保存用例
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { computed, nextTick, onMounted, onUnmounted, ref } from "vue";
import { useRouter } from "vue-router";
import { ElMessage, ElMessageBox } from "element-plus";
import {
  Close,
  Delete,
  Monitor,
  Refresh,
  VideoCamera,
  VideoPause,
  VideoPlay,
} from "@element-plus/icons-vue";
import axios from "axios";

const router = useRouter();

const devices = ref([]);
const projects = ref([]);
const selectedDeviceId = ref(null);
const selectedProjectId = ref(null);

const sessionId = ref(null);
const isRecording = ref(false);
const loading = ref(false);
const refreshing = ref(false);
const observing = ref(false);
const dirty = ref(false);
const livePreviewEnabled = ref(true);
const livePreviewIntervalMs = ref(1200);
const livePreviewRefreshing = ref(false);
const livePreviewLastAt = ref("");
const livePreviewError = ref("");

const screenshotData = ref("");
const screenWidth = ref(0);
const screenHeight = ref(0);
const renderedPageState = ref(null);
const interactions = ref([]);
const recordingDuration = ref(0);
const pendingInput = ref(null);
const pendingInputText = ref("");
const pendingDraft = ref(null);

const screenCanvas = ref(null);
const isMouseDown = ref(false);
const mouseDownPos = ref({ x: 0, y: 0 });

const saveDialogVisible = ref(false);
const saveForm = ref({
  name: "",
  description: "",
  auto_insert_wait: true,
});

let observeLoopToken = 0;
let observeTick = 0;
let durationTimer = null;
let livePreviewTimer = null;
let livePreviewLoopToken = 0;

const observeStatusText = computed(() => {
  if (!isRecording.value) return "已暂停观察";
  if (pendingInput.value) return "等待确认输入文本";
  if (observing.value) return "正在观察手机 UI";
  return "等待下一次状态变化";
});

const livePreviewStatusText = computed(() => {
  if (!livePreviewEnabled.value) return "画面手动刷新";
  if (livePreviewError.value) return `画面同步异常：${livePreviewError.value}`;
  if (livePreviewRefreshing.value) return "正在同步手机画面";
  if (livePreviewLastAt.value)
    return `画面已同步 ${new Date(livePreviewLastAt.value).toLocaleTimeString()}`;
  return "画面实时同步中";
});

const pendingInputLabel = computed(() => {
  const item = pendingInput.value || {};
  return item.label || item.resource_id || item.class_name || "输入框";
});

const pendingDraftLabel = computed(() => {
  const draft = pendingDraft.value;
  if (!draft) return "";
  if (draft.type === "tap")
    return `点击 ${draft.label || `(${draft.x}, ${draft.y})`}`;
  if (draft.type === "swipe")
    return `滑动 (${draft.x1}, ${draft.y1}) -> (${draft.x2}, ${draft.y2})`;
  if (draft.type === "input") return `输入 ${draft.label || ""}`;
  return draft.type;
});

const loadDevices = async () => {
  try {
    const res = await axios.get("/api/app-automation/devices/");
    devices.value =
      res.data.results || res.data.data?.results || res.data || [];
  } catch {
    ElMessage.error("获取设备列表失败");
  }
};

const loadProjects = async () => {
  try {
    const res = await axios.get("/api/app-automation/projects/");
    projects.value =
      res.data.results || res.data.data?.results || res.data || [];
  } catch {
    ElMessage.error("获取项目列表失败");
  }
};

const startRecording = async () => {
  if (!selectedDeviceId.value || !selectedProjectId.value) {
    ElMessage.warning("请先选择设备和项目");
    return;
  }

  loading.value = true;
  try {
    const res = await axios.post("/api/app-automation/recording/sessions/", {
      device_id: selectedDeviceId.value,
      project_id: selectedProjectId.value,
      enable_stream_capture: false,
    });

    if (!res.data?.success) {
      throw new Error(res.data?.msg || "启动录制失败");
    }

    const data = res.data.data || {};
    sessionId.value = data.session_id;
    screenshotData.value = data.screenshot || "";
    screenWidth.value = data.screen_width || 0;
    screenHeight.value = data.screen_height || 0;
    renderedPageState.value = data.page_state || null;
    interactions.value = normalizeInteractions(data.interactions || []);
    updatePendingInput(data.pending_input);
    recordingDuration.value = 0;
    dirty.value = false;
    isRecording.value = true;

    await nextTick();
    drawScreenshot();
    startDurationTimer();
    startObserveLoop(false);
    startLivePreviewLoop(0);
    livePreviewError.value = "";
    ElMessage.success("录制已开始，请直接在手机上操作");
  } catch (error) {
    livePreviewError.value =
      error.response?.data?.msg || error.message || "截图失败";
    if (true) {
      ElMessage.error(
        `启动录制失败：${error.response?.data?.msg || error.message}`,
      );
    }
  } finally {
    loading.value = false;
  }
};

const togglePause = async () => {
  if (!isRecording.value && dirty.value) {
    try {
      await syncInteractions();
    } catch (error) {
      ElMessage.error(error.message);
      return;
    }
  }

  isRecording.value = !isRecording.value;
  if (isRecording.value) {
    startDurationTimer();
    startObserveLoop(true);
    startLivePreviewLoop(0);
  } else {
    stopDurationTimer();
    stopObserveLoop();
    stopLivePreviewLoop();
  }
};

const stopRecording = async () => {
  stopObserveLoop();
  stopLivePreviewLoop();
  stopDurationTimer();
  isRecording.value = false;

  if (!interactions.value.length) {
    const confirmed = await ElMessageBox.confirm(
      "还没有录制到任何操作，确定结束并取消本次录制吗？",
      "提示",
      { type: "warning" },
    ).catch(() => false);
    if (confirmed) {
      await cancelRecording();
    } else {
      isRecording.value = true;
      startDurationTimer();
      startObserveLoop(false);
      startLivePreviewLoop(0);
    }
    return;
  }

  saveForm.value.name = `录制用例 ${new Date().toLocaleString()}`;
  saveDialogVisible.value = true;
};

const cancelRecording = async () => {
  if (!sessionId.value) return;
  try {
    await axios.delete(
      `/api/app-automation/recording/sessions/${sessionId.value}/`,
    );
  } catch (error) {
    console.error("取消录制失败", error);
  }
  resetRecording();
};

const saveTestCase = async () => {
  if (!saveForm.value.name) {
    ElMessage.warning("请输入用例名称");
    return;
  }
  if (!interactions.value.length) {
    ElMessage.warning("没有可保存的操作步骤");
    return;
  }

  loading.value = true;
  try {
    const payload = {
      name: saveForm.value.name,
      description: saveForm.value.description,
      auto_insert_wait: saveForm.value.auto_insert_wait,
      interactions: exportInteractions(),
    };
    const res = await axios.post(
      `/api/app-automation/recording/sessions/${sessionId.value}/finalize/`,
      payload,
    );

    if (!res.data?.success) {
      throw new Error(res.data?.msg || "保存失败");
    }

    ElMessage.success("测试用例已保存");
    saveDialogVisible.value = false;
    resetRecording();
    router.push("/app-automation/test-cases");
  } catch (error) {
    ElMessage.error(`保存失败：${error.response?.data?.msg || error.message}`);
  } finally {
    loading.value = false;
  }
};

const resetRecording = () => {
  stopObserveLoop();
  stopLivePreviewLoop();
  stopDurationTimer();
  sessionId.value = null;
  isRecording.value = false;
  observing.value = false;
  screenshotData.value = "";
  screenWidth.value = 0;
  screenHeight.value = 0;
  renderedPageState.value = null;
  interactions.value = [];
  recordingDuration.value = 0;
  pendingInput.value = null;
  pendingInputText.value = "";
  pendingDraft.value = null;
  livePreviewRefreshing.value = false;
  livePreviewLastAt.value = "";
  livePreviewError.value = "";
  dirty.value = false;
  saveForm.value = { name: "", description: "", auto_insert_wait: true };
};

const startObserveLoop = (reset = false) => {
  if (!sessionId.value || !isRecording.value) return;
  stopObserveLoop();
  observeLoopToken += 1;
  observeTick = 0;
  void runObserveLoop(observeLoopToken, reset);
};

const stopObserveLoop = () => {
  observeLoopToken += 1;
  observing.value = false;
};

const handleLivePreviewToggle = (enabled) => {
  if (enabled && sessionId.value && isRecording.value) {
    startLivePreviewLoop(0);
    return;
  }
  stopLivePreviewLoop();
};

const startLivePreviewLoop = (delay = livePreviewIntervalMs.value) => {
  stopLivePreviewLoop();
  if (!livePreviewEnabled.value || !sessionId.value || !isRecording.value)
    return;

  livePreviewLoopToken += 1;
  const token = livePreviewLoopToken;
  const waitMs = Math.max(0, Number(delay || 0));
  livePreviewTimer = window.setTimeout(async () => {
    if (
      token !== livePreviewLoopToken ||
      !sessionId.value ||
      !isRecording.value ||
      !livePreviewEnabled.value
    ) {
      return;
    }
    await refreshScreenshot({ silent: true, fromLivePreview: true });
    if (
      token === livePreviewLoopToken &&
      sessionId.value &&
      isRecording.value &&
      livePreviewEnabled.value
    ) {
      startLivePreviewLoop(livePreviewIntervalMs.value);
    }
  }, waitMs);
};

const stopLivePreviewLoop = () => {
  livePreviewLoopToken += 1;
  if (livePreviewTimer) {
    window.clearTimeout(livePreviewTimer);
    livePreviewTimer = null;
  }
  livePreviewRefreshing.value = false;
};

const runObserveLoop = async (token, reset = false) => {
  let errorCount = 0;

  while (token === observeLoopToken && sessionId.value && isRecording.value) {
    observing.value = true;
    observeTick += 1;

    try {
      const res = await axios.post(
        `/api/app-automation/recording/sessions/${sessionId.value}/observe/`,
        {
          reset,
          include_screenshot:
            !livePreviewEnabled.value && observeTick % 4 === 0,
        },
      );
      reset = false;
      errorCount = 0;

      if (token !== observeLoopToken) break;

      const data = res.data?.data || {};
      if (Object.prototype.hasOwnProperty.call(data, "pending_input")) {
        updatePendingInput(data.pending_input);
      }
      if (Array.isArray(data.interactions) && !dirty.value) {
        interactions.value = normalizeInteractions(data.interactions);
      } else if (data.recorded && !dirty.value) {
        interactions.value.push(normalizeInteraction(data.recorded));
      }

      const nextScreenshot = data.page_state?.content;
      if (nextScreenshot) {
        screenshotData.value = nextScreenshot;
        renderedPageState.value = data.page_state || renderedPageState.value;
        await nextTick();
        drawScreenshot();
      }
    } catch (error) {
      if (token !== observeLoopToken) break;
      errorCount += 1;
      if (errorCount >= 3) {
        ElMessage.error(
          `观察录制异常，已暂停：${error.response?.data?.msg || error.message}`,
        );
        isRecording.value = false;
        stopDurationTimer();
        break;
      }
    } finally {
      observing.value = false;
    }

    await delay(850);
  }
};

const refreshScreenshot = async ({
  silent = false,
  fromLivePreview = false,
} = {}) => {
  if (!sessionId.value) return;
  if (refreshing.value || livePreviewRefreshing.value) return;
  if (fromLivePreview) {
    livePreviewRefreshing.value = true;
  } else {
    refreshing.value = true;
  }
  try {
    const res = await axios.post(
      `/api/app-automation/recording/sessions/${sessionId.value}/screenshot/`,
      { with_candidates: false },
    );
    if (res.data?.success) {
      screenshotData.value = res.data.data.content || "";
      if (Array.isArray(res.data.data.candidates)) {
        renderedPageState.value = res.data.data;
      }
      await nextTick();
      drawScreenshot();
      livePreviewLastAt.value = new Date().toISOString();
      livePreviewError.value = "";
    }
  } catch (error) {
    livePreviewError.value =
      error.response?.data?.msg || error.message || "截图失败";
    if (!silent) {
      ElMessage.error(
        `刷新画面失败：${error.response?.data?.msg || error.message}`,
      );
    }
  } finally {
    if (fromLivePreview) {
      livePreviewRefreshing.value = false;
    } else {
      refreshing.value = false;
    }
  }
};

const syncInteractions = async () => {
  if (!sessionId.value || !dirty.value) return;
  const res = await axios.put(
    `/api/app-automation/recording/sessions/${sessionId.value}/interactions/`,
    { interactions: exportInteractions() },
  );
  if (!res.data?.success) {
    throw new Error(res.data?.msg || "同步步骤失败");
  }
  interactions.value = normalizeInteractions(
    res.data.data.interactions || interactions.value,
  );
  dirty.value = false;
};

const startDurationTimer = () => {
  stopDurationTimer();
  durationTimer = setInterval(() => {
    recordingDuration.value += 1;
  }, 1000);
};

const stopDurationTimer = () => {
  if (durationTimer) {
    clearInterval(durationTimer);
    durationTimer = null;
  }
};

const handleMouseDown = (event) => {
  if (!sessionId.value || !screenCanvas.value) return;
  mouseDownPos.value = canvasPointToDevicePoint(event);
  isMouseDown.value = true;
};

const handleMouseUp = async (event) => {
  if (!isMouseDown.value || !sessionId.value) return;
  isMouseDown.value = false;

  const upPoint = canvasPointToDevicePoint(event);
  const downPoint = mouseDownPos.value;
  const distance = Math.hypot(upPoint.x - downPoint.x, upPoint.y - downPoint.y);

  if (distance < 12) {
    stageTapDraft(upPoint.x, upPoint.y);
    return;
  }

  stageSwipeDraft(downPoint.x, downPoint.y, upPoint.x, upPoint.y);
};

const getCandidateLabel = (candidate) => {
  if (!candidate) return "";
  return (
    candidate.text ||
    candidate.content_desc ||
    candidate.hint ||
    candidate.name ||
    candidate.resource_id ||
    ""
  );
};

const stageTapDraft = (x, y) => {
  const elementData = findPreviewCandidateByPoint(x, y);
  pendingDraft.value = {
    type: "tap",
    x,
    y,
    auto_locate: true,
    element_data: elementData,
    label: getCandidateLabel(elementData),
  };
  ElMessage.info("已生成待确认点击步骤");
};

const stageSwipeDraft = (x1, y1, x2, y2) => {
  pendingDraft.value = {
    type: "swipe",
    x1,
    y1,
    x2,
    y2,
    duration: 0.3,
  };
  ElMessage.info("已生成待确认滑动步骤");
};

const confirmPendingDraft = async () => {
  if (!pendingDraft.value) return;
  const draft = { ...pendingDraft.value };
  const elementData = draft.element_data;
  delete draft.label;
  delete draft.element_data;
  if (elementData) draft.element_data = elementData;
  try {
    const res = await axios.post(
      `/api/app-automation/recording/sessions/${sessionId.value}/interactions/`,
      draft,
    );
    applyRecordedResponse(res);
    pendingDraft.value = null;
    ElMessage.success("步骤已加入");
  } catch (error) {
    ElMessage.error(
      `确认步骤失败：${error.response?.data?.msg || error.message}`,
    );
  }
};

const discardPendingDraft = () => {
  pendingDraft.value = null;
};

const recordManualTap = async (x, y) => {
  try {
    const elementData = findPreviewCandidateByPoint(x, y);
    const res = await axios.post(
      `/api/app-automation/recording/sessions/${sessionId.value}/interactions/`,
      { type: "tap", x, y, auto_locate: true, element_data: elementData },
    );
    applyRecordedResponse(res);
    ElMessage.success("已补录点击");
  } catch (error) {
    ElMessage.error(
      `补录点击失败：${error.response?.data?.msg || error.message}`,
    );
  }
};

const recordManualSwipe = async (x1, y1, x2, y2) => {
  try {
    const res = await axios.post(
      `/api/app-automation/recording/sessions/${sessionId.value}/interactions/`,
      { type: "swipe", x1, y1, x2, y2, duration: 0.3 },
    );
    applyRecordedResponse(res);
    ElMessage.success("已补录滑动");
  } catch (error) {
    ElMessage.error(
      `补录滑动失败：${error.response?.data?.msg || error.message}`,
    );
  }
};

const updatePendingInput = (nextPendingInput) => {
  if (!nextPendingInput) {
    pendingInput.value = null;
    pendingInputText.value = "";
    return;
  }

  const previousKey = pendingInput.value?.key;
  pendingInput.value = nextPendingInput;
  if (previousKey !== nextPendingInput.key) {
    pendingInputText.value = "";
  }
};

const buildPendingInputPayload = (text) => {
  const payload = { type: "input", text };
  if (!pendingInput.value) return payload;

  const { x, y, element_data: elementData } = pendingInput.value;
  if (Number.isFinite(Number(x))) payload.x = Number(x);
  if (Number.isFinite(Number(y))) payload.y = Number(y);
  if (elementData) payload.element_data = elementData;
  return payload;
};

const confirmPendingInput = async () => {
  if (!sessionId.value || !pendingInput.value) return;
  const text = pendingInputText.value.trim();
  if (!text) {
    ElMessage.warning("请输入刚才在手机里输入的文本");
    return;
  }

  try {
    const res = await axios.post(
      `/api/app-automation/recording/sessions/${sessionId.value}/interactions/`,
      buildPendingInputPayload(text),
    );
    applyRecordedResponse(res);
    ElMessage.success("已记录输入步骤");
  } catch (error) {
    ElMessage.error(
      `记录输入失败：${error.response?.data?.msg || error.message}`,
    );
  }
};

const recordManualInput = async () => {
  if (!sessionId.value) return;
  try {
    const { value } = await ElMessageBox.prompt(
      pendingInput.value
        ? `请输入刚才在「${pendingInputLabel.value}」中输入的文本。`
        : "请输入刚才在手机中输入的文本。若需要绑定具体输入框，建议先在左侧预览点击输入框，再补录输入。",
      "补录输入",
      {
        confirmButtonText: "记录",
        cancelButtonText: "取消",
        inputPlaceholder: "输入文本",
        inputValue: pendingInputText.value,
      },
    );
    const text = String(value || "").trim();
    if (!text) return;
    const res = await axios.post(
      `/api/app-automation/recording/sessions/${sessionId.value}/interactions/`,
      buildPendingInputPayload(text),
    );
    applyRecordedResponse(res);
    ElMessage.success("已补录输入");
  } catch {
    // user canceled
  }
};

const recordManualWait = async () => {
  if (!sessionId.value) return;
  try {
    const { value } = await ElMessageBox.prompt("等待秒数", "补录等待", {
      confirmButtonText: "记录",
      cancelButtonText: "取消",
      inputValue: "1",
    });
    const duration = Number(value);
    if (!Number.isFinite(duration) || duration <= 0) {
      ElMessage.warning("请输入有效等待秒数");
      return;
    }
    const res = await axios.post(
      `/api/app-automation/recording/sessions/${sessionId.value}/interactions/`,
      { type: "wait", duration },
    );
    applyRecordedResponse(res);
    ElMessage.success("已补录等待");
  } catch {
    // user canceled
  }
};

const applyRecordedResponse = (res) => {
  if (!res.data?.success) {
    throw new Error(res.data?.msg || "记录失败");
  }
  if (
    Object.prototype.hasOwnProperty.call(res.data.data || {}, "pending_input")
  ) {
    updatePendingInput(res.data.data.pending_input);
  }
  const list = res.data.data?.interactions;
  if (Array.isArray(list)) {
    interactions.value = normalizeInteractions(list);
  } else if (res.data.data?.interaction) {
    interactions.value.push(normalizeInteraction(res.data.data.interaction));
  }
  dirty.value = false;
};

const clearHistory = async () => {
  const confirmed = await ElMessageBox.confirm(
    "确定清空当前录制步骤吗？该操作会同步清空后端录制会话。",
    "提示",
    { type: "warning" },
  ).catch(() => false);
  if (!confirmed) return;

  try {
    await axios.delete(
      `/api/app-automation/recording/sessions/${sessionId.value}/interactions/`,
    );
    interactions.value = [];
    dirty.value = false;
  } catch (error) {
    ElMessage.error(`清空失败：${error.response?.data?.msg || error.message}`);
  }
};

const removeInteraction = async (index) => {
  interactions.value.splice(index, 1);
  dirty.value = true;
  if (!isRecording.value) {
    await syncInteractions().catch((error) => {
      ElMessage.error(error.message);
    });
  }
};

const markDirty = () => {
  dirty.value = true;
};

const onInputAtomChanged = (atom) => {
  const value = getAtomInput(atom).value || "";
  atom.text = value;
  atom.input.raw_value = value;
  markDirty();
};

const getAtomInput = (atom) => {
  if (!atom.input || typeof atom.input !== "object") {
    atom.input = { value: atom.text || "", raw_value: atom.text || "" };
  }
  return atom.input;
};

const normalizeInteractions = (items) => items.map(normalizeInteraction);

const normalizeInteraction = (item) => {
  const atom = { ...item };
  atom.id =
    atom.id || `local_${Date.now()}_${Math.random().toString(16).slice(2)}`;
  atom.name = atom.name || getDefaultAtomName(atom);
  if (atom.type === "input") {
    atom.input = {
      value: atom.input?.value ?? atom.text ?? "",
      raw_value: atom.input?.raw_value ?? atom.text ?? "",
    };
    atom.text = atom.input.value;
  }
  return atom;
};

const exportInteractions = () =>
  interactions.value.map((item) => {
    const atom = { ...item };
    if (atom.type === "input") {
      atom.input = {
        value: atom.input?.value ?? atom.text ?? "",
        raw_value: atom.input?.raw_value ?? atom.text ?? "",
      };
      atom.text = atom.input.value;
    }
    return atom;
  });

const drawScreenshot = () => {
  if (!screenCanvas.value || !screenshotData.value) return;

  const canvas = screenCanvas.value;
  const ctx = canvas.getContext("2d");
  const img = new Image();

  img.onload = () => {
    screenWidth.value = img.naturalWidth || img.width;
    screenHeight.value = img.naturalHeight || img.height;
    canvas.width = screenWidth.value;
    canvas.height = screenHeight.value;
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    ctx.drawImage(img, 0, 0, canvas.width, canvas.height);
  };

  img.src = screenshotData.value;
};

const canvasPointToDevicePoint = (event) => {
  const rect = screenCanvas.value.getBoundingClientRect();
  const scaleX = screenWidth.value / rect.width;
  const scaleY = screenHeight.value / rect.height;
  return {
    x: Math.round((event.clientX - rect.left) * scaleX),
    y: Math.round((event.clientY - rect.top) * scaleY),
  };
};

const findPreviewCandidateByPoint = (x, y) => {
  const candidates = renderedPageState.value?.candidates || [];
  const matched = [];
  const nearest = [];

  candidates.forEach((candidate) => {
    const bounds = candidate.bounds || {};
    const x1 = Number(bounds.x1 || 0);
    const y1 = Number(bounds.y1 || 0);
    const x2 = Number(bounds.x2 || 0);
    const y2 = Number(bounds.y2 || 0);
    const distance = Math.max(x1 - x, 0, x - x2) + Math.max(y1 - y, 0, y - y2);
    const item = {
      candidate,
      distance,
      score: scorePreviewCandidate(candidate, x, y, distance),
    };
    if (x >= x1 && x <= x2 && y >= y1 && y <= y2) {
      matched.push(item);
    } else {
      nearest.push(item);
    }
  });

  const exactText = matched
    .filter(
      ({ candidate }) =>
        hasVisibleText(candidate) && !isWeakPreviewCandidate(candidate),
    )
    .sort((a, b) => b.score - a.score);
  if (exactText.length) return exactText[0].candidate;

  const nearbyText = nearest
    .filter(
      ({ candidate, distance }) =>
        distance <= 96 &&
        hasVisibleText(candidate) &&
        !isWeakPreviewCandidate(candidate),
    )
    .sort((a, b) => b.score - a.score);
  if (nearbyText.length) return nearbyText[0].candidate;

  const exactResource = matched
    .filter(
      ({ candidate }) =>
        candidate.resource_id && !isWeakPreviewCandidate(candidate),
    )
    .sort((a, b) => b.score - a.score);
  if (exactResource.length) return exactResource[0].candidate;

  matched.sort((a, b) => b.score - a.score);
  return matched[0]?.candidate || null;
};

const scorePreviewCandidate = (candidate, x, y, distance = 0) => {
  const bounds = candidate.bounds || {};
  const x1 = Number(bounds.x1 || 0);
  const y1 = Number(bounds.y1 || 0);
  const x2 = Number(bounds.x2 || 0);
  const y2 = Number(bounds.y2 || 0);
  const width = Math.max(1, x2 - x1);
  const height = Math.max(1, y2 - y1);
  const area = width * height;
  const centerDistance =
    Math.abs((x1 + x2) / 2 - x) + Math.abs((y1 + y2) / 2 - y);
  const role = String(candidate.interaction_role || "").toLowerCase();
  const className = String(candidate.class_name || "").toLowerCase();
  const resourceId = String(candidate.resource_id || "").toLowerCase();
  const hasLabel = hasVisibleText(candidate) || Boolean(candidate.name);
  const generic = isWeakPreviewCandidate(candidate);
  const roleScore =
    {
      input: 50,
      button: 45,
      checkbox: 45,
      switch: 45,
      tab: 42,
      option: 40,
      entry: 38,
      clickable: 35,
      focusable: 24,
    }[role] || 0;

  let score = 0;
  score += generic ? -1000 : 0;
  score += roleScore;
  score += hasLabel ? 30 : 0;
  score += candidate.resource_id && !generic ? 12 : 0;
  score += candidate.is_hotzone ? 8 : 0;
  score +=
    className.includes("textview") || className.includes("button") ? 8 : 0;
  score +=
    resourceId.includes("cancel") ||
    resourceId.includes("confirm") ||
    resourceId.includes("logout")
      ? 16
      : 0;
  score += /取消|确认|退出|登出/.test(
    String(candidate.text || candidate.content_desc || candidate.hint || ""),
  )
    ? 18
    : 0;
  score -= Math.min(distance / 2, 80);
  score -= Math.min(centerDistance / 8, 80);
  score -= Math.min(area / 40000, 80);
  return score;
};

const hasVisibleText = (candidate) =>
  Boolean(
    String(candidate?.text || "").trim() ||
    String(candidate?.content_desc || "").trim() ||
    String(candidate?.hint || "").trim(),
  );

const isWeakPreviewCandidate = (candidate) => {
  const role = String(candidate.interaction_role || "").toLowerCase();
  if (
    [
      "input",
      "button",
      "checkbox",
      "switch",
      "tab",
      "option",
      "entry",
    ].includes(role)
  )
    return false;
  const resourceId = String(candidate.resource_id || "").toLowerCase();
  const className = String(candidate.class_name || "").toLowerCase();
  const hasLabel = Boolean(
    candidate.text || candidate.content_desc || candidate.hint,
  );
  if (
    resourceId === "android:id/content" ||
    resourceId.endsWith(":id/content") ||
    resourceId.includes("main_content_container")
  )
    return true;
  if (resourceId.includes("drawerlayout") || className.includes("drawerlayout"))
    return true;
  if (
    !hasLabel &&
    ["framelayout", "linearlayout", "relativelayout", "viewgroup"].some(
      (marker) => className.includes(marker),
    )
  )
    return true;
  return false;
};

const formatAtom = (atom) => {
  if (atom.type === "tap") {
    return getTargetLabel(atom) || `坐标 (${atom.x}, ${atom.y})`;
  }
  if (atom.type === "swipe") {
    return `${atom.x1},${atom.y1} -> ${atom.x2},${atom.y2}`;
  }
  if (atom.type === "input") {
    return `${getTargetLabel(atom) || "输入框"} = "${atom.input?.value || atom.text || ""}"`;
  }
  if (atom.type === "wait") {
    return `${atom.duration || 1} 秒`;
  }
  return atom.name || atom.type || "";
};

const getTargetLabel = (atom) => {
  const target = atom.target || {};
  return (
    target.text ||
    target.hint ||
    target.content_desc ||
    atom.element_name ||
    humanizeResourceId(target.resource_id) ||
    humanizeClassName(target.class) ||
    ""
  );
};

const humanizeResourceId = (resourceId) => {
  let text = String(resourceId || "").trim();
  if (!text) return "";
  if (text.includes("/")) {
    text = text.split("/").pop();
  } else if (text.includes(":")) {
    text = text.split(":").pop();
  }
  if (["content", "drawerLayout", "action_bar_root"].includes(text)) return "";
  text = text.replace(/^(btn|iv|tv|et|ll|rl|fl|rv|cbk|ic|img|view)_?/i, "");
  text = text.replace(/([a-z0-9])([A-Z])/g, "$1 $2");
  text = text.replace(/[_-]+/g, " ");
  return text.trim();
};

const humanizeClassName = (className) => {
  const tail =
    String(className || "")
      .split(".")
      .pop() || "";
  if (
    !tail ||
    ["FrameLayout", "LinearLayout", "RelativeLayout", "ViewGroup"].includes(
      tail,
    )
  )
    return "";
  return tail.replace(/([a-z0-9])([A-Z])/g, "$1 $2");
};

const getDefaultAtomName = (atom) => {
  const label = getTargetLabel(atom);
  if (atom.type === "tap") return `点击 ${label || "坐标"}`;
  if (atom.type === "input") return `输入 ${label || "文本"}`;
  if (atom.type === "swipe") return "滑动";
  if (atom.type === "wait") return "等待";
  return "操作";
};

const getAtomTypeLabel = (type) => {
  const labels = {
    tap: "点击",
    swipe: "滑动",
    input: "输入",
    wait: "等待",
  };
  return labels[type] || type;
};

const getAtomTagType = (type) => {
  const types = {
    tap: "primary",
    swipe: "success",
    input: "warning",
    wait: "info",
  };
  return types[type] || "info";
};

const formatDuration = (seconds) => {
  const mins = Math.floor(seconds / 60);
  const secs = seconds % 60;
  return `${mins}:${String(secs).padStart(2, "0")}`;
};

const delay = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

onMounted(() => {
  loadDevices();
  loadProjects();
});

onUnmounted(() => {
  stopObserveLoop();
  stopLivePreviewLoop();
  stopDurationTimer();
  if (sessionId.value) {
    void cancelRecording();
  }
});
</script>

<style scoped>
.recording-studio {
  min-height: calc(100vh - 120px);
  padding: 4px;
  background:
    radial-gradient(
      circle at 18% 12%,
      rgba(64, 158, 255, 0.16),
      transparent 28%
    ),
    linear-gradient(135deg, #f7fbff 0%, #f6f1e8 100%);
}

.hero-card {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 18px;
  padding: 22px 26px;
  margin-bottom: 16px;
  color: #17324d;
  border: 1px solid rgba(23, 50, 77, 0.08);
  border-radius: 18px;
  background: rgba(255, 255, 255, 0.82);
  box-shadow: 0 18px 48px rgba(23, 50, 77, 0.08);
}

.eyebrow {
  margin: 0 0 6px;
  color: #6c7a89;
  font-size: 12px;
  letter-spacing: 0.18em;
  text-transform: uppercase;
}

.hero-card h1 {
  margin: 0;
  font-size: 28px;
  font-weight: 800;
}

.subtitle {
  max-width: 760px;
  margin: 8px 0 0;
  color: #5f7182;
  line-height: 1.6;
}

.studio-grid {
  display: grid;
  grid-template-columns: minmax(520px, 1.25fr) minmax(420px, 0.95fr);
  gap: 16px;
}

.screen-card,
.atoms-card {
  border: 1px solid rgba(23, 50, 77, 0.08);
  border-radius: 16px;
  overflow: hidden;
}

.toolbar {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 10px;
}

.toolbar-select {
  width: 190px;
}

.live-rate-select {
  width: 92px;
}

.recorder-tip {
  padding: 12px 14px;
  margin-bottom: 12px;
  border: 1px solid #d7e9ff;
  border-radius: 12px;
  color: #3b5874;
  background: #edf6ff;
  line-height: 1.6;
}

.pending-input-card {
  display: grid;
  grid-template-columns: minmax(220px, 1fr) minmax(280px, 1.2fr);
  gap: 12px;
  align-items: center;
  padding: 14px;
  margin-bottom: 12px;
  border: 1px solid #f3c969;
  border-radius: 14px;
  background: linear-gradient(135deg, #fff8e6 0%, #fffdf6 100%);
  box-shadow: 0 10px 28px rgba(199, 136, 15, 0.12);
}

.pending-input-copy {
  display: flex;
  flex-direction: column;
  gap: 4px;
  color: #6b4b0f;
  line-height: 1.45;
}

.pending-input-copy small {
  color: #96722a;
}

.pending-input-actions {
  display: grid;
  grid-template-columns: minmax(160px, 1fr) auto;
  gap: 10px;
}

.screen-shell {
  height: calc(100vh - 340px);
  min-height: 540px;
  display: flex;
  align-items: center;
  justify-content: center;
  border: 1px solid #d8e2ec;
  border-radius: 18px;
  background:
    linear-gradient(45deg, rgba(23, 50, 77, 0.04) 25%, transparent 25%),
    linear-gradient(-45deg, rgba(23, 50, 77, 0.04) 25%, transparent 25%),
    #f8fafc;
  background-size: 20px 20px;
  overflow: hidden;
}

.empty-screen {
  text-align: center;
  color: #8a98a8;
}

.device-frame {
  max-width: 100%;
  max-height: 100%;
  padding: 14px;
  border-radius: 28px;
  background: #1d2733;
  box-shadow: 0 24px 60px rgba(29, 39, 51, 0.28);
}

.device-frame canvas {
  display: block;
  width: auto;
  height: auto;
  max-width: min(100%, 520px);
  max-height: calc(100vh - 390px);
  border-radius: 18px;
  cursor: crosshair;
  background: #000;
}

.status-strip {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
  padding: 12px 4px 0;
}

.panel-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.panel-header h2 {
  margin: 0;
  font-size: 18px;
}

.panel-header span {
  color: #8492a6;
  font-size: 12px;
}

.atom-list {
  max-height: calc(100vh - 300px);
  overflow-y: auto;
  padding-right: 4px;
}

.atom-item {
  display: grid;
  grid-template-columns: 34px 1fr 28px;
  gap: 10px;
  padding: 12px;
  margin-bottom: 10px;
  border: 1px solid #e4ebf2;
  border-radius: 14px;
  background: #fbfdff;
}

.atom-index {
  width: 28px;
  height: 28px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 50%;
  color: #fff;
  background: #17324d;
  font-size: 12px;
  font-weight: 700;
}

.atom-main {
  min-width: 0;
}

.atom-topline {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
}

.atom-source,
.atom-confidence {
  color: #8492a6;
  font-size: 12px;
}

.atom-name-input,
.atom-input-value {
  margin-bottom: 8px;
}

.atom-meta {
  color: #667789;
  font-size: 12px;
  line-height: 1.5;
  word-break: break-word;
}

@media (max-width: 1180px) {
  .studio-grid {
    grid-template-columns: 1fr;
  }

  .screen-shell {
    height: 620px;
  }

  .pending-input-card,
  .pending-input-actions {
    grid-template-columns: 1fr;
  }

  .atom-list {
    max-height: 520px;
  }
}

@media (max-width: 720px) {
  .hero-card {
    align-items: flex-start;
    flex-direction: column;
  }

  .toolbar-select {
    width: 100%;
  }

  .screen-shell {
    min-height: 420px;
    height: 58vh;
  }
}
</style>
