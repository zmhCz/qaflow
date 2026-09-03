<template>
  <div class="page-capture-workbench">
    <el-card class="control-card" shadow="hover">
      <template #header>
        <div class="section-header">
          <div>
            <div class="section-title">交互录制台</div>
            <div class="section-subtitle">
              你在手机上实际操作
              APP，这里负责记录点击前后页面、点击位置和命中控件，并直接沉淀成可编排的测试步骤。
            </div>
          </div>
          <el-space wrap>
            <el-button @click="loadBaseData">刷新基础数据</el-button>
            <el-button
              type="danger"
              plain
              :disabled="snapshotHistory.length === 0"
              @click="clearHistory"
            >
              清空本次采集
            </el-button>
          </el-space>
        </div>
      </template>

      <el-row :gutter="16">
        <el-col :xl="7" :lg="8" :md="12" :sm="24">
          <el-form label-width="88px" size="default">
            <el-form-item label="项目">
              <el-select
                v-model="selectedProjectId"
                filterable
                clearable
                placeholder="选择元素归属项目"
                style="width: 100%"
              >
                <el-option
                  v-for="project in projectList"
                  :key="project.id"
                  :label="project.name"
                  :value="project.id"
                />
              </el-select>
            </el-form-item>
            <el-form-item label="设备">
              <el-select
                v-model="selectedDeviceId"
                filterable
                placeholder="选择在线设备"
                style="width: 100%"
              >
                <el-option
                  v-for="device in onlineDevices"
                  :key="device.id"
                  :label="deviceLabel(device)"
                  :value="device.id"
                >
                  <div class="device-option">
                    <span>{{ device.device_id }}</span>
                    <el-tag
                      size="small"
                      :type="getDeviceStatusType(device.status)"
                    >
                      {{ getDeviceStatusText(device.status) }}
                    </el-tag>
                  </div>
                </el-option>
              </el-select>
            </el-form-item>
          </el-form>
          <div v-if="recordingStatusText" class="capture-hint">
            {{ recordingStatusText }}
          </div>
        </el-col>

        <el-col :xl="10" :lg="8" :md="12" :sm="24">
          <div class="capture-actions">
            <el-button
              type="primary"
              :loading="capturing"
              :disabled="!selectedDeviceId"
              @click="captureCurrentPage"
            >
              抓当前页
            </el-button>
            <el-button
              type="success"
              plain
              :disabled="!selectedDeviceId || recording"
              :loading="waitingForTouch"
              @click="startInteractionRecording"
            >
              记录手动交互
            </el-button>
            <el-button
              v-if="recording || waitingForTouch"
              type="warning"
              plain
              @click="stopInteractionRecording"
            >
              停止记录
            </el-button>
            <el-button :disabled="!currentSnapshot" @click="copyCurrentUiXml">
              复制 UI 树
            </el-button>
            <el-button
              :disabled="!currentSnapshot"
              @click="copyCurrentCandidates"
            >
              复制候选 JSON
            </el-button>
          </div>
          <div class="capture-hint">
            推荐节奏：先抓一张当前页作为基线，再开启“记录手动交互”；你每点一步，左侧会生成一步，右侧可以补动作名、改步骤类型，最后直接导入测试用例。
          </div>
        </el-col>

        <el-col :xl="7" :lg="8" :md="24" :sm="24">
          <div class="summary-grid">
            <div class="summary-item">
              <div class="summary-label">本次采集页数</div>
              <div class="summary-value">{{ snapshotHistory.length }}</div>
            </div>
            <div class="summary-item">
              <div class="summary-label">当前候选元素</div>
              <div class="summary-value">
                {{ currentSnapshot?.candidate_count || 0 }}
              </div>
            </div>
            <div class="summary-item">
              <div class="summary-label">当前点击热区</div>
              <div class="summary-value">
                {{ currentSnapshot?.hotzone_count || 0 }}
              </div>
            </div>
          </div>
        </el-col>
      </el-row>
    </el-card>

    <el-row :gutter="16" class="workspace-row">
      <el-col :xl="5" :lg="6" :md="24" :sm="24">
        <el-card class="history-card" shadow="hover">
          <template #header>
            <div class="section-header compact">
              <span class="section-title small">交互记录</span>
              <el-tag size="small" type="success">{{
                recordedInteractions.length
              }}</el-tag>
            </div>
          </template>

          <div
            v-if="recordedInteractions.length === 0"
            class="empty-panel empty-panel--compact"
          >
            <el-empty
              description="开始记录后，这里会按你的实际操作顺序生成步骤。"
            />
          </div>

          <div v-else class="history-list history-list--compact">
            <button
              v-for="item in recordedInteractions"
              :key="item.id"
              class="history-item"
              :class="{ active: activeInteractionId === item.id }"
              @click="selectInteraction(item)"
            >
              <div class="history-item__title">
                <span
                  >#{{ item.index }}
                  {{ item.actionName || item.candidateName }}</span
                >
                <span>{{ item.tapPoint.x }}, {{ item.tapPoint.y }}</span>
              </div>
              <div class="history-item__meta">
                {{ describeRecordedInteraction(item) }}
              </div>
              <div class="history-item__time">
                {{ formatDateTime(item.createdAt) }}
              </div>
            </button>
          </div>
        </el-card>

        <el-card class="history-card" shadow="hover">
          <template #header>
            <div class="section-header compact">
              <span class="section-title small">采集历史</span>
              <el-tag size="small" type="info">{{
                snapshotHistory.length
              }}</el-tag>
            </div>
          </template>

          <div v-if="snapshotHistory.length === 0" class="empty-panel">
            <el-empty description="还没有采集历史页面。" />
          </div>

          <div v-else class="history-list">
            <button
              v-for="snapshot in snapshotHistory"
              :key="snapshot.id"
              class="history-item"
              :class="{ active: currentSnapshot?.id === snapshot.id }"
              @click="selectSnapshot(snapshot)"
            >
              <div class="history-item__title">
                <span>{{ snapshot.title }}</span>
                <span>{{ snapshot.candidate_count }} 项</span>
              </div>
              <div class="history-item__meta">
                {{ snapshot.activity || snapshot.package_name || "未知页面" }}
              </div>
              <div class="history-item__time">
                {{ formatDateTime(snapshot.createdAt) }}
              </div>
            </button>
          </div>
        </el-card>
      </el-col>

      <el-col :xl="10" :lg="10" :md="24" :sm="24">
        <el-card class="preview-card" shadow="hover">
          <template #header>
            <div class="section-header compact">
              <div>
                <span class="section-title small">页面预览</span>
                <div v-if="currentSnapshot" class="meta-line">
                  <el-tag size="small">{{
                    currentSnapshot.package_name || "未识别包名"
                  }}</el-tag>
                  <el-tag size="small" type="success">{{
                    currentSnapshot.activity || "未识别 Activity"
                  }}</el-tag>
                  <el-tag size="small" type="warning"
                    >节点 {{ currentSnapshot.node_count }}</el-tag
                  >
                </div>
              </div>
              <el-switch
                v-model="showAllBoxes"
                inline-prompt
                active-text="全部候选"
                inactive-text="仅高亮"
                :disabled="!currentSnapshot"
              />
            </div>
          </template>

          <div v-if="!currentSnapshot" class="empty-panel">
            <el-empty description="请先选择左侧页面，或先抓一张当前页。">
              <el-button
                type="primary"
                plain
                :disabled="!selectedDeviceId"
                :loading="livePreviewLoading"
                @click="refreshLivePreview({ silent: false })"
              >
                先看实时截图
              </el-button>
            </el-empty>
          </div>

          <div v-else class="preview-stage">
            <div class="preview-toolbar">
              <div class="preview-toolbar__text">
                当前定位：{{ currentFocusSummary }}
                <el-tag
                  v-if="currentSnapshot.is_live_preview"
                  size="small"
                  type="info"
                  effect="plain"
                  >仅实时截图</el-tag
                >
                <el-tag
                  v-else-if="livePreviewEnabled"
                  size="small"
                  type="warning"
                  effect="plain"
                  >候选框来自最近一次抓页</el-tag
                >
              </div>
              <div
                v-if="currentInteractionTapPoint"
                class="preview-toolbar__tap"
              >
                点击点：{{ currentInteractionTapPoint.x }},
                {{ currentInteractionTapPoint.y }}
              </div>
              <div v-if="highlightedCandidate" class="preview-toolbar__hint">
                绿色框是全部候选，蓝框是悬停项，红框是当前选中项；可以直接拖动红框，或拖四角微调大小。
              </div>
            </div>
            <div class="live-preview-bar">
              <div class="live-preview-bar__main">
                <el-switch
                  v-model="livePreviewEnabled"
                  inline-prompt
                  active-text="实时预览"
                  inactive-text="手动刷新"
                  :disabled="!selectedDeviceId"
                />
                <el-select
                  v-model="livePreviewIntervalMs"
                  size="small"
                  class="live-preview-bar__rate"
                  :disabled="!livePreviewEnabled"
                >
                  <el-option label="0.8 秒" :value="800" />
                  <el-option label="1.2 秒" :value="1200" />
                  <el-option label="2 秒" :value="2000" />
                </el-select>
                <el-button
                  size="small"
                  :loading="livePreviewLoading"
                  :disabled="!selectedDeviceId"
                  @click="refreshLivePreview({ silent: false })"
                >
                  刷新截图
                </el-button>
              </div>
              <div
                class="live-preview-bar__status"
                :class="{ error: livePreviewError }"
              >
                <template v-if="livePreviewLoading"
                  >正在同步手机画面...</template
                >
                <template v-else-if="livePreviewError">{{
                  livePreviewError
                }}</template>
                <template v-else-if="livePreviewLastAt"
                  >已同步 {{ formatDateTime(livePreviewLastAt) }}</template
                >
                <template v-else>实时预览只刷新截图，不重新识别控件。</template>
              </div>
            </div>
            <div class="image-shell">
              <div ref="imageWrapperRef" class="image-wrapper">
                <img
                  ref="previewImageRef"
                  :src="currentSnapshot.content"
                  class="preview-image"
                  @load="handlePreviewImageLoad"
                />
                <div
                  v-if="currentInteractionTapPoint"
                  class="tap-point-marker"
                  :style="tapPointStyle(currentInteractionTapPoint)"
                >
                  <span class="tap-point-marker__dot" />
                  <span class="tap-point-marker__label"
                    >{{ currentInteractionTapPoint.x }},
                    {{ currentInteractionTapPoint.y }}</span
                  >
                </div>
                <div
                  v-for="candidate in overlayCandidates"
                  :key="candidate.id"
                  class="candidate-box"
                  :class="{
                    active: highlightedCandidate?.id === candidate.id,
                    hovered: hoveredCandidate?.id === candidate.id,
                    selected: selectedCandidateIds.includes(candidate.id),
                  }"
                  :style="candidateBoxStyle(candidate)"
                  @click.stop="focusCandidate(candidate)"
                  @mousedown.stop="startMove(candidate, $event)"
                >
                  <span class="candidate-box__index">
                    {{ getCandidateIndex(candidate.id) }}
                  </span>
                  <span
                    v-if="
                      highlightedCandidate?.id === candidate.id ||
                      hoveredCandidate?.id === candidate.id
                    "
                    class="candidate-box__label"
                  >
                    {{ getCandidateIndex(candidate.id) }}.
                    {{ candidate.display_name }}
                  </span>
                  <template v-if="highlightedCandidate?.id === candidate.id">
                    <span
                      v-for="handle in resizeHandles"
                      :key="handle"
                      class="candidate-box__handle"
                      :class="`candidate-box__handle--${handle}`"
                      @mousedown.stop="startResize(candidate, handle, $event)"
                    />
                  </template>
                </div>
              </div>
            </div>
          </div>
        </el-card>
      </el-col>

      <el-col :xl="9" :lg="8" :md="24" :sm="24">
        <el-card
          v-if="activeInteraction"
          class="candidate-card recorder-card"
          shadow="hover"
        >
          <template #header>
            <div class="section-header compact">
              <div>
                <span class="section-title small">步骤详情</span>
                <div class="section-subtitle compact">
                  先把这一步在业务上叫什么、属于点击还是输入、是用控件定位还是坐标定位，整理清楚后再导入场景。
                </div>
              </div>
              <el-tag :type="activeInteraction.confidenceType" size="small">
                {{ activeInteraction.confidenceLabel }}
              </el-tag>
            </div>
          </template>

          <div class="recorder-detail">
            <div class="recorder-detail__field">
              <div class="recorder-detail__label">动作名称</div>
              <el-input
                :model-value="activeInteraction.actionName"
                placeholder="例如：切换密码登录 / 点击登录按钮 / 进入社区详情"
                @update:model-value="
                  updateInteractionActionName(activeInteraction.id, $event)
                "
              />
            </div>

            <div class="recorder-detail__field">
              <div class="recorder-detail__label">步骤类型</div>
              <el-radio-group
                :model-value="activeInteraction.actionType"
                size="small"
                @update:model-value="
                  updateInteractionField(
                    activeInteraction.id,
                    'actionType',
                    $event,
                  )
                "
              >
                <el-radio-button
                  v-for="option in interactionActionOptions"
                  :key="option.value"
                  :label="option.value"
                >
                  {{ option.label }}
                </el-radio-button>
              </el-radio-group>
            </div>

            <div class="recorder-detail__field">
              <div class="recorder-detail__label">定位策略</div>
              <el-radio-group
                :model-value="activeInteraction.locatorStrategy"
                size="small"
                @update:model-value="
                  updateInteractionField(
                    activeInteraction.id,
                    'locatorStrategy',
                    $event,
                  )
                "
              >
                <el-radio-button
                  v-for="option in getLocatorStrategyOptions(activeInteraction)"
                  :key="option.value"
                  :label="option.value"
                >
                  {{ option.label }}
                </el-radio-button>
              </el-radio-group>
            </div>

            <div class="recorder-detail__grid">
              <div class="recorder-detail__item">
                <div class="recorder-detail__label">点击前页面</div>
                <div class="recorder-detail__value">
                  {{ activeInteraction.sourceActivityName }}
                </div>
              </div>
              <div class="recorder-detail__item">
                <div class="recorder-detail__label">点击后页面</div>
                <div class="recorder-detail__value">
                  {{ activeInteraction.resultActivityName }}
                </div>
              </div>
              <div class="recorder-detail__item">
                <div class="recorder-detail__label">点击坐标</div>
                <div class="recorder-detail__value">
                  {{ activeInteraction.tapPoint.x }},
                  {{ activeInteraction.tapPoint.y }}
                </div>
              </div>
              <div class="recorder-detail__item">
                <div class="recorder-detail__label">页面变化</div>
                <div class="recorder-detail__value">
                  {{ activeInteraction.transitionSummary }}
                </div>
              </div>
            </div>

            <div class="recorder-detail__field">
              <div class="recorder-detail__label">命中控件</div>
              <div class="recorder-detail__summary">
                <div class="recorder-detail__title">
                  {{ activeInteraction.candidateName }}
                </div>
                <div class="recorder-detail__desc">
                  {{ activeInteraction.matchedLocatorSummary }}
                </div>
              </div>
            </div>

            <div
              v-if="activeInteraction.actionType === 'input'"
              class="recorder-detail__field"
            >
              <div class="recorder-detail__label">输入内容</div>
              <el-input
                :model-value="activeInteraction.inputValue"
                placeholder="直接填文本，或填 {{local.phone}} 这类变量表达式"
                @update:model-value="
                  updateInteractionField(
                    activeInteraction.id,
                    'inputValue',
                    $event,
                  )
                "
              />
              <el-checkbox
                class="recorder-detail__checkbox"
                :model-value="activeInteraction.sendEnter"
                @update:model-value="
                  updateInteractionField(
                    activeInteraction.id,
                    'sendEnter',
                    $event,
                  )
                "
              >
                输入后发送回车
              </el-checkbox>
            </div>

            <div
              v-if="activeInteraction.actionType === 'assert'"
              class="recorder-detail__grid recorder-detail__grid--editing"
            >
              <div class="recorder-detail__item">
                <div class="recorder-detail__label">断言类型</div>
                <el-select
                  :model-value="activeInteraction.assertKind"
                  @update:model-value="
                    updateInteractionField(
                      activeInteraction.id,
                      'assertKind',
                      $event,
                    )
                  "
                >
                  <el-option
                    v-for="option in assertKindOptions"
                    :key="option.value"
                    :label="option.label"
                    :value="option.value"
                  />
                </el-select>
              </div>
              <div
                v-if="activeInteraction.assertKind !== 'exists'"
                class="recorder-detail__item recorder-detail__item--wide"
              >
                <div class="recorder-detail__label">期望值</div>
                <el-input
                  :model-value="activeInteraction.assertExpected"
                  placeholder="例如：登录成功 / 首页"
                  @update:model-value="
                    updateInteractionField(
                      activeInteraction.id,
                      'assertExpected',
                      $event,
                    )
                  "
                />
              </div>
            </div>

            <div
              v-if="activeInteraction.actionType === 'wait'"
              class="recorder-detail__field"
            >
              <div class="recorder-detail__label">等待秒数</div>
              <el-input-number
                :model-value="activeInteraction.waitSeconds"
                :min="1"
                :max="60"
                controls-position="right"
                @update:model-value="
                  updateInteractionField(
                    activeInteraction.id,
                    'waitSeconds',
                    $event,
                  )
                "
              />
            </div>

            <div class="recorder-detail__actions">
              <el-button
                size="small"
                @click="showInteractionSnapshot(activeInteraction, 'before')"
              >
                查看点击前
              </el-button>
              <el-button
                size="small"
                @click="showInteractionSnapshot(activeInteraction, 'after')"
              >
                查看点击后
              </el-button>
              <el-button
                type="success"
                plain
                size="small"
                :disabled="!selectedDeviceId || !highlightedCandidate"
                :loading="validatingSelector"
                @click="validateHighlightedCandidate"
              >
                验证当前定位
              </el-button>
              <el-button
                type="primary"
                size="small"
                :disabled="!selectedProjectId || !highlightedCandidate"
                :loading="importingSingleId === highlightedCandidate?.id"
                @click="importActiveInteractionCandidate"
              >
                导入当前命中控件
              </el-button>
              <el-button
                type="danger"
                plain
                size="small"
                @click="removeInteraction(activeInteraction.id)"
              >
                删除这一步
              </el-button>
            </div>
            <div
              v-if="selectorValidationResult"
              class="validation-result"
              :class="{
                'validation-result--success': selectorValidationResult.matched,
                'validation-result--warning': !selectorValidationResult.matched,
              }"
            >
              <div class="validation-result__title">
                {{
                  selectorValidationResult.matched
                    ? "实时验证通过"
                    : "实时验证未命中"
                }}
              </div>
              <div class="validation-result__desc">
                {{ selectorValidationResult.summary }}
              </div>
            </div>
          </div>
        </el-card>

        <el-card class="candidate-card recorder-card" shadow="hover">
          <template #header>
            <div class="section-header compact">
              <div>
                <span class="section-title small">场景草稿</span>
                <div class="section-subtitle compact">
                  把刚才录到的步骤直接写进测试用例，后续再去编排器里补细节。
                </div>
              </div>
              <el-tag size="small" type="info"
                >{{ recordedStepDrafts.length }} 步</el-tag
              >
            </div>
          </template>

          <div class="scene-export">
            <el-form label-width="72px">
              <el-form-item label="目标项目">
                <div class="scene-export__plain">
                  {{ selectedProjectName || "请先选择项目" }}
                </div>
              </el-form-item>
              <el-form-item label="已有用例">
                <el-select
                  v-model="selectedCaseId"
                  filterable
                  clearable
                  placeholder="选择一个用例并写入步骤"
                  style="width: 100%"
                  :loading="loadingCases"
                >
                  <el-option
                    v-for="item in testCaseList"
                    :key="item.id"
                    :label="item.name"
                    :value="item.id"
                  />
                </el-select>
              </el-form-item>
              <el-form-item label="写入方式">
                <el-radio-group v-model="exportMode" size="small">
                  <el-radio-button label="replace">覆盖步骤</el-radio-button>
                  <el-radio-button label="append">追加步骤</el-radio-button>
                </el-radio-group>
              </el-form-item>
              <el-form-item label="新用例名">
                <el-input
                  v-model="draftCaseName"
                  placeholder="例如：社区APP-账号密码登录"
                />
              </el-form-item>
              <el-form-item label="说明">
                <el-input
                  v-model="draftCaseDescription"
                  type="textarea"
                  :rows="3"
                  placeholder="例如：来自交互录制台的登录流程草稿，可继续补输入值、断言和异常分支"
                />
              </el-form-item>
            </el-form>

            <div class="scene-export__summary">
              导出顺序会按你在手机上的实际操作顺序排列。输入类步骤支持直接填写文本，也支持手工改成变量表达式。
            </div>

            <div
              v-if="recordedStepDrafts.length === 0"
              class="empty-panel empty-panel--compact"
            >
              <el-empty
                description="先录几步交互，这里就会生成待导入的场景草稿。"
              />
            </div>

            <div v-else class="scene-export__steps">
              <div
                v-for="(step, index) in recordedStepDrafts"
                :key="step.id"
                class="scene-export__step"
              >
                <div class="scene-export__step-head">
                  <span>{{ index + 1 }}. {{ step.name }}</span>
                  <el-tag size="small">{{ stepTypeLabel(step.type) }}</el-tag>
                </div>
                <div class="scene-export__step-desc">
                  {{ describeUiFlowStep(step) }}
                </div>
              </div>
            </div>

            <div class="scene-export__actions">
              <el-button @click="openSceneBuilder(selectedCaseId)"
                >打开编排器</el-button
              >
              <el-button
                type="success"
                :loading="exportingCase"
                :disabled="!canCreateDraftCase"
                @click="createDraftCaseFromRecording"
              >
                新建用例草稿
              </el-button>
              <el-button
                type="primary"
                :loading="exportingCase"
                :disabled="!canSyncToCase"
                @click="syncRecordedInteractionsToCase"
              >
                写入选中用例
              </el-button>
            </div>
          </div>
        </el-card>

        <el-card class="candidate-card" shadow="hover">
          <template #header>
            <div class="section-header compact">
              <div>
                <span class="section-title small">候选元素</span>
                <div class="section-subtitle compact">
                  已按 resource-id、文本、交互性过滤，并叠加源码增强结果。
                </div>
              </div>
              <el-space wrap>
                <el-button
                  type="primary"
                  :disabled="
                    selectedCandidates.length === 0 || !selectedProjectId
                  "
                  :loading="importing"
                  @click="importSelectedCandidates"
                >
                  批量导入
                </el-button>
              </el-space>
            </div>
          </template>

          <div class="candidate-filters">
            <el-input
              v-model="candidateSearch"
              clearable
              placeholder="搜名称 / resource-id / text / hint"
            />
            <el-space wrap>
              <el-switch
                v-model="onlyWithResourceId"
                inline-prompt
                active-text="仅ID"
                inactive-text="全部"
              />
              <el-switch
                v-model="onlyClickable"
                inline-prompt
                active-text="仅可点"
                inactive-text="全部"
              />
              <el-switch
                v-model="onlyHotzones"
                inline-prompt
                active-text="仅热区"
                inactive-text="全候选"
              />
            </el-space>
          </div>

          <div v-if="highlightedCandidate" class="adjust-panel">
            <div class="adjust-panel__header">
              <div>
                <div class="adjust-panel__title">人工微调框</div>
                <div class="adjust-panel__desc">
                  {{ highlightedCandidate.display_name }}
                </div>
              </div>
              <el-button
                size="small"
                @click="resetCandidateBounds(highlightedCandidate)"
              >
                恢复原框
              </el-button>
            </div>

            <div class="adjust-text-grid">
              <el-input
                :model-value="highlightedCandidate.display_name"
                placeholder="编辑中文说明"
                @update:model-value="
                  updateHighlightedTextField('display_name', $event)
                "
              />
              <el-input
                :model-value="highlightedCandidate.display_description"
                placeholder="补充说明，便于后续理解"
                @update:model-value="
                  updateHighlightedTextField('display_description', $event)
                "
              />
            </div>

            <div class="adjust-grid">
              <el-input-number
                :model-value="highlightedCandidate.bounds.x1"
                :min="0"
                controls-position="right"
                @update:model-value="updateHighlightedBoundsField('x1', $event)"
              />
              <el-input-number
                :model-value="highlightedCandidate.bounds.y1"
                :min="0"
                controls-position="right"
                @update:model-value="updateHighlightedBoundsField('y1', $event)"
              />
              <el-input-number
                :model-value="highlightedCandidate.bounds.x2"
                :min="0"
                controls-position="right"
                @update:model-value="updateHighlightedBoundsField('x2', $event)"
              />
              <el-input-number
                :model-value="highlightedCandidate.bounds.y2"
                :min="0"
                controls-position="right"
                @update:model-value="updateHighlightedBoundsField('y2', $event)"
              />
            </div>

            <div class="adjust-meta">
              <span>宽 {{ highlightedCandidate.bounds.width }}</span>
              <span>高 {{ highlightedCandidate.bounds.height }}</span>
              <span>{{ formatBounds(highlightedCandidate.bounds) }}</span>
            </div>
          </div>

          <div v-if="!currentSnapshot" class="empty-panel">
            <el-empty description="采集完成后，这里会列出候选元素。" />
          </div>

          <el-table
            v-else
            :data="filteredCandidates"
            height="620"
            border
            @selection-change="handleCandidateSelectionChange"
            @row-click="focusCandidate"
            @row-mouse-enter="hoverCandidate"
            @row-mouse-leave="clearHoveredCandidate"
          >
            <el-table-column label="#" width="56" align="center">
              <template #default="{ row }">
                <span class="candidate-order">{{
                  getCandidateIndex(row.id)
                }}</span>
              </template>
            </el-table-column>
            <el-table-column type="selection" width="48" />
            <el-table-column label="中文说明" min-width="170">
              <template #default="{ row }">
                <div class="candidate-main">
                  <div class="candidate-main__title">
                    {{ row.display_name }}
                  </div>
                  <div class="candidate-main__desc">
                    {{ row.display_description }}
                  </div>
                </div>
              </template>
            </el-table-column>
            <el-table-column label="定位信息" min-width="200">
              <template #default="{ row }">
                <div class="locator-block">
                  <div>{{ row.resource_id || "-" }}</div>
                  <div v-if="row.text">text: {{ row.text }}</div>
                  <div v-else-if="row.hint">hint: {{ row.hint }}</div>
                  <div v-else-if="row.content_desc">
                    desc: {{ row.content_desc }}
                  </div>
                </div>
              </template>
            </el-table-column>
            <el-table-column label="源码增强" min-width="190">
              <template #default="{ row }">
                <div class="source-block">
                  <div class="source-block__title">
                    {{ row.interaction_role_label || "普通候选" }}
                  </div>
                  <div class="source-block__desc">
                    {{ row.source_summary || "未命中源码增强信息" }}
                  </div>
                </div>
              </template>
            </el-table-column>
            <el-table-column label="控件" min-width="120">
              <template #default="{ row }">
                <div class="class-text">{{ row.class_name || "-" }}</div>
              </template>
            </el-table-column>
            <el-table-column label="状态" width="88" align="center">
              <template #default="{ row }">
                <el-tag
                  :type="row.is_hotzone ? 'success' : 'info'"
                  size="small"
                >
                  {{ row.is_hotzone ? "热区" : "静态" }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column label="操作" width="88" fixed="right">
              <template #default="{ row }">
                <el-button
                  type="primary"
                  size="small"
                  text
                  :loading="importingSingleId === row.id"
                  :disabled="!selectedProjectId"
                  @click.stop="importOneCandidate(row)"
                >
                  导入
                </el-button>
              </template>
            </el-table-column>
          </el-table>
        </el-card>
      </el-col>
    </el-row>
  </div>
</template>

<script setup>
import { computed, onMounted, onUnmounted, ref, watch } from "vue";
import { ElMessage, ElMessageBox } from "element-plus";
import { useRouter } from "vue-router";
import {
  captureDeviceScreenshot,
  captureDevicePageState,
  createAppElement,
  createTestCase,
  getAppElementList,
  getAppProjects,
  getDeviceList,
  getTestCaseDetail,
  getTestCaseList,
  recordDeviceNextInteraction,
  updateAppElement,
  updateTestCase,
  validateDeviceSelector,
} from "@/api/app-automation";
import {
  formatDateTime,
  getDeviceStatusText,
  getDeviceStatusType,
} from "@/utils/app-automation-helpers";

const selectedProjectId = ref(null);
const selectedDeviceId = ref(null);
const router = useRouter();
const capturing = ref(false);
const recording = ref(false);
const waitingForTouch = ref(false);
const importing = ref(false);
const importingSingleId = ref(null);
const validatingSelector = ref(false);

const projectList = ref([]);
const testCaseList = ref([]);
const devices = ref([]);
const snapshotHistory = ref([]);
const recordedInteractions = ref([]);
const activeInteractionId = ref(null);
const currentSnapshotId = ref(null);
const selectedCandidates = ref([]);
const candidateSearch = ref("");
const onlyWithResourceId = ref(true);
const onlyClickable = ref(false);
const onlyHotzones = ref(false);
const showAllBoxes = ref(true);
const highlightedCandidateId = ref(null);
const hoveredCandidateId = ref(null);
const livePreviewEnabled = ref(false);
const livePreviewLoading = ref(false);
const livePreviewError = ref("");
const livePreviewLastAt = ref("");
const livePreviewIntervalMs = ref(1200);
const livePreviewTimer = ref(null);
const livePreviewInFlight = ref(false);
const previewWidth = ref(1);
const previewHeight = ref(1);
const previewClientWidth = ref(1);
const previewClientHeight = ref(1);
const imageWrapperRef = ref(null);
const selectorValidationResult = ref(null);
const previewImageRef = ref(null);
const resizeHandles = ["nw", "ne", "se", "sw"];
const dragState = ref(null);
const interactionSequence = ref(0);
const loadingCases = ref(false);
const exportingCase = ref(false);
const selectedCaseId = ref(null);
const exportMode = ref("replace");
const draftCaseName = ref("");
const draftCaseDescription = ref("");

const interactionActionOptions = [
  { label: "点击", value: "click" },
  { label: "输入", value: "input" },
  { label: "断言", value: "assert" },
  { label: "等待", value: "wait" },
];

const assertKindOptions = [
  { label: "存在", value: "exists" },
  { label: "文本包含", value: "text" },
];

const onlineDevices = computed(() =>
  devices.value.filter((device) => device.status !== "offline"),
);

const currentSnapshot = computed(() => {
  return (
    snapshotHistory.value.find(
      (snapshot) => snapshot.id === currentSnapshotId.value,
    ) || null
  );
});

const activeInteraction = computed(() => {
  return (
    recordedInteractions.value.find(
      (item) => item.id === activeInteractionId.value,
    ) || null
  );
});

const selectedProjectName = computed(() => {
  return (
    projectList.value.find((item) => item.id === selectedProjectId.value)
      ?.name || ""
  );
});

const selectedTestCase = computed(() => {
  return (
    testCaseList.value.find((item) => item.id === selectedCaseId.value) || null
  );
});

const recordingStatusText = computed(() => {
  if (waitingForTouch.value) {
    return "正在等待你在手机上完成下一次点击，点完后这里会自动记成一步。";
  }
  if (recording.value) {
    return "交互录制运行中，点击停止记录后，会在当前这一轮结束后停下。";
  }
  return "";
});

const filteredCandidates = computed(() => {
  const snapshot = currentSnapshot.value;
  if (!snapshot) {
    return [];
  }

  const keyword = candidateSearch.value.trim().toLowerCase();
  return snapshot.candidates.filter((candidate) => {
    if (onlyWithResourceId.value && !candidate.resource_id) {
      return false;
    }
    if (onlyClickable.value && !candidate.clickable) {
      return false;
    }
    if (onlyHotzones.value && !candidate.is_hotzone) {
      return false;
    }
    if (!keyword) {
      return true;
    }
    const haystack = [
      candidate.display_name,
      candidate.display_description,
      candidate.resource_id,
      candidate.text,
      candidate.hint,
      candidate.content_desc,
      candidate.class_name,
      candidate.source_summary,
      candidate.source_declared_tag,
      candidate.interaction_role_label,
    ]
      .filter(Boolean)
      .join(" ")
      .toLowerCase();
    return haystack.includes(keyword);
  });
});

const selectedCandidateIds = computed(() =>
  selectedCandidates.value.map((item) => item.id),
);

const highlightedCandidate = computed(() => {
  return (
    filteredCandidates.value.find(
      (candidate) => candidate.id === highlightedCandidateId.value,
    ) || null
  );
});

const hoveredCandidate = computed(() => {
  return (
    filteredCandidates.value.find(
      (candidate) => candidate.id === hoveredCandidateId.value,
    ) || null
  );
});

const candidateIndexMap = computed(() => {
  return new Map(
    filteredCandidates.value.map((candidate, index) => [
      candidate.id,
      index + 1,
    ]),
  );
});

const currentFocusSummary = computed(() => {
  const candidate = highlightedCandidate.value || hoveredCandidate.value;
  if (!candidate) {
    return "未选中候选元素";
  }
  return `#${getCandidateIndex(candidate.id)} ${candidate.display_name}`;
});

const currentInteractionTapPoint = computed(() => {
  const interaction = activeInteraction.value;
  const snapshot = currentSnapshot.value;
  if (!interaction || !snapshot) {
    return null;
  }
  if (
    interaction.sourceSnapshotId !== snapshot.id &&
    interaction.resultSnapshotId !== snapshot.id
  ) {
    return null;
  }
  return interaction.tapPoint || null;
});

const recordedStepDrafts = computed(() => {
  return recordedInteractions.value.map((interaction, index) =>
    buildUiFlowStepFromInteraction(interaction, index),
  );
});

const canCreateDraftCase = computed(() => {
  return Boolean(
    selectedProjectId.value &&
    recordedInteractions.value.length > 0 &&
    draftCaseName.value.trim(),
  );
});

const canSyncToCase = computed(() => {
  return Boolean(
    selectedTestCase.value && recordedInteractions.value.length > 0,
  );
});

const overlayCandidates = computed(() => {
  if (!currentSnapshot.value) {
    return [];
  }
  if (showAllBoxes.value) {
    return filteredCandidates.value;
  }
  return highlightedCandidate.value ? [highlightedCandidate.value] : [];
});

onMounted(() => {
  loadBaseData();
  window.addEventListener("mousemove", handleGlobalPointerMove);
  window.addEventListener("mouseup", stopDragAdjust);
});

onUnmounted(() => {
  recording.value = false;
  stopLivePreviewLoop();
  window.removeEventListener("mousemove", handleGlobalPointerMove);
  window.removeEventListener("mouseup", stopDragAdjust);
});

watch(livePreviewEnabled, (enabled) => {
  if (enabled) {
    scheduleLivePreviewRefresh(0);
    return;
  }
  stopLivePreviewLoop();
});

watch(livePreviewIntervalMs, () => {
  if (livePreviewEnabled.value) {
    scheduleLivePreviewRefresh(livePreviewIntervalMs.value);
  }
});

watch(selectedDeviceId, () => {
  livePreviewError.value = "";
  if (livePreviewEnabled.value) {
    scheduleLivePreviewRefresh(0);
  }
});

watch(selectedProjectId, (projectId) => {
  selectedCaseId.value = null;
  testCaseList.value = [];
  if (projectId) {
    loadTestCases(projectId);
  }
});

const loadBaseData = async () => {
  await Promise.all([loadProjects(), loadDevices()]);
};

const loadProjects = async () => {
  try {
    const res = await getAppProjects({ page_size: 100 });
    projectList.value = res.data.results || res.data || [];
    if (!selectedProjectId.value && projectList.value.length === 1) {
      selectedProjectId.value = projectList.value[0].id;
    }
  } catch (error) {
    ElMessage.error(`加载项目失败: ${error.message || "未知错误"}`);
  }
};

const loadTestCases = async (projectId) => {
  loadingCases.value = true;
  try {
    const res = await getTestCaseList({ page_size: 100, project: projectId });
    testCaseList.value = res.data.results || res.data || [];
  } catch (error) {
    ElMessage.error(`加载测试用例失败: ${error.message || "未知错误"}`);
  } finally {
    loadingCases.value = false;
  }
};

const loadDevices = async () => {
  try {
    const res = await getDeviceList({ page_size: 100 });
    devices.value = res.data.results || res.data || [];
    if (!selectedDeviceId.value) {
      const preferred = onlineDevices.value[0];
      if (preferred) {
        selectedDeviceId.value = preferred.id;
      }
    }
  } catch (error) {
    ElMessage.error(`加载设备失败: ${error.message || "未知错误"}`);
  }
};

const deviceLabel = (device) => {
  return `${device.device_id}${device.name ? ` / ${device.name}` : ""}`;
};

const stopLivePreviewLoop = () => {
  if (livePreviewTimer.value) {
    window.clearTimeout(livePreviewTimer.value);
    livePreviewTimer.value = null;
  }
};

const scheduleLivePreviewRefresh = (delay = livePreviewIntervalMs.value) => {
  stopLivePreviewLoop();
  if (!livePreviewEnabled.value || !selectedDeviceId.value) {
    return;
  }
  livePreviewTimer.value = window.setTimeout(
    () => {
      refreshLivePreview({ silent: true });
    },
    Math.max(0, Number(delay || 0)),
  );
};

const refreshLivePreview = async ({ silent = true } = {}) => {
  if (!selectedDeviceId.value) {
    if (!silent) {
      ElMessage.warning("请先选择设备");
    }
    return;
  }
  if (livePreviewInFlight.value || capturing.value) {
    if (livePreviewEnabled.value) {
      scheduleLivePreviewRefresh(livePreviewIntervalMs.value);
    }
    return;
  }

  stopLivePreviewLoop();
  livePreviewInFlight.value = true;
  livePreviewLoading.value = true;
  try {
    const res = await captureDeviceScreenshot(selectedDeviceId.value);
    const payload = res.data?.data;
    if (!res.data?.success || !payload?.content) {
      throw new Error(res.data?.msg || res.data?.message || "截图失败");
    }

    applyLivePreviewPayload(payload);
    livePreviewError.value = "";
    livePreviewLastAt.value = new Date().toISOString();
    if (!silent) {
      ElMessage.success("预览图已刷新");
    }
  } catch (error) {
    livePreviewError.value =
      error?.response?.data?.msg || error?.message || "实时预览刷新失败";
    if (!silent) {
      ElMessage.error(`实时预览刷新失败: ${livePreviewError.value}`);
    }
  } finally {
    livePreviewInFlight.value = false;
    livePreviewLoading.value = false;
    if (livePreviewEnabled.value) {
      scheduleLivePreviewRefresh(livePreviewIntervalMs.value);
    }
  }
};

const applyLivePreviewPayload = (payload) => {
  const snapshot = currentSnapshot.value;
  if (snapshot) {
    snapshot.content = payload.content;
    snapshot.filename = payload.filename || snapshot.filename;
    snapshot.timestamp = payload.timestamp || Math.floor(Date.now() / 1000);
    return;
  }

  const liveSnapshot = appendSnapshot({
    ...payload,
    title: "实时预览",
    package_name: "",
    activity: "",
    node_count: 0,
    candidate_count: 0,
    hotzone_count: 0,
    candidates: [],
    xml: "",
    is_live_preview: true,
  });
  currentSnapshotId.value = liveSnapshot.id;
  selectedCandidates.value = [];
  highlightedCandidateId.value = null;
  hoveredCandidateId.value = null;
};

const captureCurrentPage = async () => {
  if (!selectedDeviceId.value) {
    ElMessage.warning("请先选择设备");
    return;
  }

  capturing.value = true;
  try {
    const res = await captureDevicePageState(selectedDeviceId.value);
    const payload = res.data?.data;
    if (!res.data?.success || !payload) {
      throw new Error(res.data?.message || "采集失败");
    }

    const snapshot = appendSnapshot(payload);
    currentSnapshotId.value = snapshot.id;
    selectedCandidates.value = [];
    highlightedCandidateId.value = snapshot.candidates[0]?.id || null;
    hoveredCandidateId.value = null;
    showAllBoxes.value = true;
    candidateSearch.value = "";
    ElMessage.success(`已抓取当前页，候选元素 ${snapshot.candidate_count} 个`);
  } catch (error) {
    ElMessage.error(`当前页面采集失败: ${error.message || "未知错误"}`);
  } finally {
    capturing.value = false;
  }
};

const startInteractionRecording = async () => {
  if (!selectedDeviceId.value) {
    ElMessage.warning("请先选择设备");
    return;
  }
  if (recording.value) {
    return;
  }

  recording.value = true;
  ElMessage.success("已开始记录，你可以直接在手机上操作 APP。");
  await runInteractionRecordingLoop();
};

const stopInteractionRecording = () => {
  if (!recording.value && !waitingForTouch.value) {
    return;
  }
  recording.value = false;
  ElMessage.info("已请求停止记录，当前这一轮结束后会停下。");
};

const runInteractionRecordingLoop = async () => {
  while (recording.value) {
    waitingForTouch.value = true;
    try {
      const res = await recordDeviceNextInteraction(selectedDeviceId.value, {
        timeout: 40,
        post_capture_delay_ms: 450,
      });
      const payload = res.data?.data;
      if (!res.data?.success || !payload) {
        throw new Error(res.data?.msg || res.data?.message || "记录交互失败");
      }
      recordInteraction(payload);
    } catch (error) {
      const statusCode = error?.response?.status;
      const message =
        error?.response?.data?.msg || error?.message || "未知错误";
      if (statusCode === 408) {
        if (recording.value) {
          ElMessage.warning("这一轮没有等到点击，我会继续等下一轮。");
          continue;
        }
      } else {
        ElMessage.error(`记录交互失败: ${message}`);
      }
      recording.value = false;
    } finally {
      waitingForTouch.value = false;
    }
  }
};

const recordInteraction = (payload) => {
  const beforeSnapshot = appendSnapshot(payload.before);
  const afterSnapshot = appendSnapshot(payload.after);
  const matchedCandidate = matchSnapshotCandidate(
    beforeSnapshot,
    payload.matched_candidate,
  );

  interactionSequence.value += 1;
  const latestRecord = buildInteractionRecord({
    payload,
    beforeSnapshot,
    afterSnapshot,
    matchedCandidate,
    index: interactionSequence.value,
  });

  recordedInteractions.value = [
    ...recordedInteractions.value,
    latestRecord,
  ].slice(-50);

  activeInteractionId.value = latestRecord.id;
  currentSnapshotId.value = beforeSnapshot.id;
  highlightedCandidateId.value =
    matchedCandidate?.id || beforeSnapshot.candidates[0]?.id || null;
  hoveredCandidateId.value = highlightedCandidateId.value;
  showAllBoxes.value = true;
  candidateSearch.value = "";

  if (!draftCaseName.value.trim()) {
    draftCaseName.value = buildSuggestedCaseName();
  }
  if (!draftCaseDescription.value.trim()) {
    draftCaseDescription.value =
      "来自交互录制台的场景草稿，可继续在编排器中补充变量、断言和异常分支。";
  }

  ElMessage.success(`已记录交互：${latestRecord.candidateName}`);
};

const buildInteractionRecord = ({
  payload,
  beforeSnapshot,
  afterSnapshot,
  matchedCandidate,
  index,
}) => {
  const sourceActivityName = humanizeActivityName(
    beforeSnapshot.activity || beforeSnapshot.package_name || "",
  );
  const resultActivityName = humanizeActivityName(
    afterSnapshot.activity || afterSnapshot.package_name || "",
  );
  const confidence = resolveInteractionConfidence(matchedCandidate);
  const tapPoint = payload.touch_point || { x: 0, y: 0 };
  const selectorPayload = buildInlineSelectorPayload(matchedCandidate);
  const candidateName =
    matchedCandidate?.display_name || `点击 ${tapPoint.x},${tapPoint.y}`;
  const transitionSummary =
    sourceActivityName === resultActivityName
      ? "页面停留在当前页"
      : `${sourceActivityName} -> ${resultActivityName}`;

  return {
    id: `interaction-${Date.now()}-${index}`,
    index,
    createdAt: new Date().toISOString(),
    candidateName,
    summary: transitionSummary,
    tapPoint,
    sourceSnapshotId: beforeSnapshot.id,
    resultSnapshotId: afterSnapshot.id,
    candidateId: matchedCandidate?.id || "",
    actionName: candidateName,
    actionType: buildDefaultActionType(matchedCandidate),
    inputValue: "",
    sendEnter: false,
    assertKind: "exists",
    assertExpected: "",
    waitSeconds: 3,
    locatorStrategy: selectorPayload ? "selector" : "pos",
    selectorPayload,
    sourceActivityName,
    resultActivityName,
    transitionSummary,
    matchedLocatorSummary: buildMatchedLocatorSummary(matchedCandidate),
    confidenceLabel: confidence.label,
    confidenceType: confidence.type,
  };
};

const buildDefaultActionType = (candidate) => {
  const signature = [
    candidate?.class_name,
    candidate?.resource_id,
    candidate?.text,
    candidate?.hint,
    candidate?.content_desc,
    candidate?.locator_key,
  ]
    .filter(Boolean)
    .join(" ")
    .toLowerCase();

  if (/edittext|input/.test(signature)) {
    return "input";
  }
  if (
    /(phone|mobile|password|pwd|code|search|keyword|verify)/.test(signature)
  ) {
    return "input";
  }
  return "click";
};

const buildInlineSelectorPayload = (candidate) => {
  if (!candidate) {
    return null;
  }
  const selector = {
    resource_id: cleanText(candidate.resource_id),
    text: cleanText(candidate.text),
    content_desc: cleanText(candidate.content_desc),
    hint: cleanText(candidate.hint),
    class: cleanText(candidate.class_name),
    package: cleanText(candidate.package_name),
    bounds: cleanText(candidate.raw_bounds),
    clickable: candidate.clickable,
    focusable: candidate.focusable,
    enabled: candidate.enabled,
  };
  Object.keys(selector).forEach((key) => {
    if (
      selector[key] === "" ||
      selector[key] === null ||
      selector[key] === undefined
    ) {
      delete selector[key];
    }
  });
  return Object.keys(selector).length ? selector : null;
};

const resolveInteractionConfidence = (candidate) => {
  if (!candidate) {
    return { label: "需人工确认", type: "danger" };
  }
  if (candidate.resource_id && candidate.source_confidence === "high") {
    return { label: "可稳定定位", type: "success" };
  }
  if (candidate.resource_id || candidate.source_confidence === "medium") {
    return { label: "基本可用", type: "warning" };
  }
  return { label: "需人工确认", type: "danger" };
};

const buildMatchedLocatorSummary = (candidate) => {
  if (!candidate) {
    return "没有明确命中控件，请结合点击位置和前后页面人工确认。";
  }
  return [
    candidate.resource_id,
    candidate.text ? `text=${candidate.text}` : "",
    candidate.content_desc ? `desc=${candidate.content_desc}` : "",
    candidate.hint ? `hint=${candidate.hint}` : "",
    candidate.source_summary || "",
  ]
    .filter(Boolean)
    .join(" | ");
};

const getLocatorStrategyOptions = (interaction) => {
  const options = [];
  if (interaction?.selectorPayload) {
    options.push({ label: "命中控件", value: "selector" });
  }
  options.push({ label: "点击坐标", value: "pos" });
  return options;
};

const appendSnapshot = (payload) => {
  const snapshot = buildSnapshot(payload);
  snapshotHistory.value = [snapshot, ...snapshotHistory.value].slice(0, 40);
  return snapshot;
};

const buildSnapshot = (payload) => {
  const createdAt = new Date(
    payload.timestamp ? payload.timestamp * 1000 : Date.now(),
  ).toISOString();
  const title = buildSnapshotTitle(payload);
  const candidates = (payload.candidates || []).map((candidate, index) =>
    normalizeCandidate(candidate, index, payload),
  );
  return {
    ...payload,
    id: `${payload.device_id || "device"}-${payload.timestamp || Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
    title,
    createdAt,
    candidates,
  };
};

const matchSnapshotCandidate = (snapshot, target) => {
  if (!snapshot || !target) {
    return null;
  }
  return (
    snapshot.candidates.find(
      (candidate) =>
        candidate.resource_id === target.resource_id &&
        candidate.raw_bounds === target.raw_bounds &&
        candidate.class_name === target.class_name,
    ) ||
    snapshot.candidates.find(
      (candidate) =>
        candidate.resource_id === target.resource_id &&
        candidate.text === target.text &&
        candidate.class_name === target.class_name,
    ) ||
    null
  );
};

const buildSnapshotTitle = (payload) => {
  if (payload.title) {
    return payload.title;
  }
  const activityKey = activityShortName(payload.activity);
  if (activityKey) {
    return activityKey;
  }
  return payload.package_name || "未命名页面";
};

const normalizeCandidate = (candidate, index, payload) => {
  const bounds = normalizeBoundsObject(candidate.bounds || {});
  const locatorKey = buildLocatorKey(candidate, index);
  const displayName = pickDisplayName(candidate, locatorKey);
  return {
    ...candidate,
    id: `${payload.timestamp || Date.now()}-${index}-${locatorKey}`,
    bounds,
    original_bounds: { ...bounds },
    locator_key: locatorKey,
    display_name: displayName,
    display_description:
      candidate.description ||
      [candidate.class_name, candidate.raw_bounds].filter(Boolean).join(" | "),
  };
};

const pickDisplayName = (candidate, locatorKey) => {
  return (
    cleanText(candidate.name) ||
    cleanText(candidate.text) ||
    cleanText(candidate.hint) ||
    cleanText(candidate.content_desc) ||
    humanizeLocatorKey(locatorKey) ||
    "未命名元素"
  );
};

const cleanText = (value) => String(value || "").trim();

const buildLocatorKey = (candidate, index = 0) => {
  const resourceTail = cleanText(candidate.resource_id).split("/").pop() || "";
  const textSource = cleanText(
    candidate.text ||
      candidate.hint ||
      candidate.content_desc ||
      candidate.name,
  );
  const preferred = resourceTail || textSource || `node_${index + 1}`;
  const normalized = preferred
    .replace(/[:/]/g, "_")
    .replace(/([a-z0-9])([A-Z])/g, "$1_$2")
    .replace(/[^a-zA-Z0-9_\u4e00-\u9fa5]+/g, "_")
    .replace(/^_+|_+$/g, "")
    .replace(/_+/g, "_")
    .toLowerCase();
  return normalized || `node_${index + 1}`;
};

const humanizeLocatorKey = (locatorKey) => {
  const text = String(locatorKey || "");
  if (!text) {
    return "";
  }
  const tokenMap = {
    btn: "按钮",
    login: "登录",
    phone: "手机号",
    mobile: "手机号",
    password: "密码",
    pwd: "密码",
    verify: "验证码",
    code: "验证码",
    agree: "协议",
    checkbox: "勾选框",
    input: "输入框",
    edit: "输入框",
    community: "社区",
    create: "创建",
    confirm: "确认",
    cancel: "取消",
    mine: "我的",
    home: "首页",
  };
  const tokens = text.split("_").filter(Boolean);
  const translated = tokens
    .map((token) => tokenMap[token] || "")
    .filter(Boolean);
  return translated.join("") || text;
};

const selectSnapshot = (snapshot) => {
  activeInteractionId.value = "";
  currentSnapshotId.value = snapshot.id;
  selectedCandidates.value = [];
  highlightedCandidateId.value = snapshot.candidates[0]?.id || null;
  hoveredCandidateId.value = null;
  candidateSearch.value = "";
};

const selectInteraction = (item) => {
  activeInteractionId.value = item.id;
  const snapshot = snapshotHistory.value.find(
    (entry) => entry.id === item.sourceSnapshotId,
  );
  if (!snapshot) {
    return;
  }
  currentSnapshotId.value = snapshot.id;
  selectedCandidates.value = [];
  highlightedCandidateId.value =
    item.candidateId || snapshot.candidates[0]?.id || null;
  hoveredCandidateId.value = highlightedCandidateId.value;
  candidateSearch.value = "";
  showAllBoxes.value = true;
};

const showInteractionSnapshot = (item, side = "before") => {
  const snapshotId =
    side === "after" ? item.resultSnapshotId : item.sourceSnapshotId;
  const snapshot = snapshotHistory.value.find(
    (entry) => entry.id === snapshotId,
  );
  if (!snapshot) {
    return;
  }
  activeInteractionId.value = item.id;
  currentSnapshotId.value = snapshot.id;
  selectedCandidates.value = [];
  highlightedCandidateId.value =
    item.candidateId || snapshot.candidates[0]?.id || null;
  hoveredCandidateId.value = highlightedCandidateId.value;
  candidateSearch.value = "";
  showAllBoxes.value = true;
};

const updateInteractionActionName = (interactionId, value) => {
  const target = recordedInteractions.value.find(
    (item) => item.id === interactionId,
  );
  if (!target) {
    return;
  }
  target.actionName = String(value || "").trim();
};

const updateInteractionField = (interactionId, field, value) => {
  const target = recordedInteractions.value.find(
    (item) => item.id === interactionId,
  );
  if (!target) {
    return;
  }
  target[field] = value;
  if (field === "actionType" && value !== "input") {
    target.sendEnter = false;
  }
  if (field === "actionType" && value !== "assert") {
    target.assertKind = "exists";
    target.assertExpected = "";
  }
  if (field === "actionType" && value !== "wait") {
    target.waitSeconds = 3;
  }
};

const removeInteraction = async (interactionId) => {
  const target = recordedInteractions.value.find(
    (item) => item.id === interactionId,
  );
  if (!target) {
    return;
  }
  try {
    await ElMessageBox.confirm(
      `确认删除步骤“${target.actionName || target.candidateName}”吗？`,
      "删除步骤",
      {
        type: "warning",
      },
    );
    recordedInteractions.value = recordedInteractions.value.filter(
      (item) => item.id !== interactionId,
    );
    if (activeInteractionId.value === interactionId) {
      activeInteractionId.value =
        recordedInteractions.value[recordedInteractions.value.length - 1]?.id ||
        null;
    }
    ElMessage.success("该步骤已删除");
  } catch {
    // 用户取消时保持当前状态即可
  }
};

const stepTypeLabel = (type) => {
  return (
    interactionActionOptions.find((item) => item.value === type)?.label || type
  );
};

const buildInteractionSelector = (interaction) => {
  if (
    interaction.locatorStrategy === "selector" &&
    interaction.selectorPayload
  ) {
    return {
      selector_type: "selector",
      selector: { ...interaction.selectorPayload },
    };
  }
  return {
    selector_type: "pos",
    selector: `${Number(interaction.tapPoint?.x || 0)},${Number(interaction.tapPoint?.y || 0)}`,
  };
};

const buildUiFlowStepFromInteraction = (interaction, index) => {
  const selectorConfig = buildInteractionSelector(interaction);
  const baseStep = {
    id: buildRecordedStepId(interaction, index),
    kind: "base",
    type: interaction.actionType || "click",
    name: truncateName(
      interaction.actionName || interaction.candidateName || `步骤${index + 1}`,
    ),
    config: {
      ...selectorConfig,
      timeout: 5,
    },
  };

  if (baseStep.type === "input") {
    baseStep.config.value = String(interaction.inputValue || "");
    baseStep.config.send_enter = Boolean(interaction.sendEnter);
    return baseStep;
  }

  if (baseStep.type === "assert") {
    baseStep.config.assert_type = interaction.assertKind || "exists";
    if (baseStep.config.assert_type !== "exists") {
      baseStep.config.expected = String(interaction.assertExpected || "");
      baseStep.config.match_mode = "contains";
    }
    return baseStep;
  }

  if (baseStep.type === "wait") {
    baseStep.config.timeout = Number(interaction.waitSeconds || 3);
    return baseStep;
  }

  return baseStep;
};

const buildRecordedStepId = (interaction, index) => {
  const normalized = String(interaction.id || index + 1).replace(
    /[^a-zA-Z0-9_]+/g,
    "_",
  );
  return `recorded_${index + 1}_${normalized.slice(-24)}`;
};

const describeRecordedInteraction = (interaction) => {
  return `${stepTypeLabel(interaction.actionType)} · ${interaction.transitionSummary}`;
};

const describeUiFlowStep = (step) => {
  const config = step.config || {};
  if (step.type === "input") {
    return `${describeStepSelector(config)}，输入：${config.value || "(待补充)"}`.trim();
  }
  if (step.type === "assert") {
    if (config.assert_type === "exists") {
      return `${describeStepSelector(config)}，断言控件存在`;
    }
    return `${describeStepSelector(config)}，断言包含：${config.expected || "(待补充)"}`;
  }
  if (step.type === "wait") {
    return config.selector
      ? `${describeStepSelector(config)}，最长等待 ${config.timeout}s`
      : `固定等待 ${config.timeout}s`;
  }
  return describeStepSelector(config);
};

const describeStepSelector = (config = {}) => {
  if (config.selector_type === "selector") {
    const selector = config.selector || {};
    return (
      [
        selector.resource_id,
        selector.text ? `text=${selector.text}` : "",
        selector.content_desc ? `desc=${selector.content_desc}` : "",
        selector.hint ? `hint=${selector.hint}` : "",
      ]
        .filter(Boolean)
        .join(" | ") || "命中控件"
    );
  }
  if (config.selector_type === "pos") {
    return `坐标 ${config.selector}`;
  }
  return "待补定位";
};

const buildSuggestedCaseName = () => {
  if (!recordedInteractions.value.length) {
    return "";
  }
  const firstStep = recordedInteractions.value[0];
  const lastStep =
    recordedInteractions.value[recordedInteractions.value.length - 1];
  if (
    firstStep?.actionName &&
    lastStep?.actionName &&
    firstStep.id !== lastStep.id
  ) {
    return truncateName(`${firstStep.actionName} 到 ${lastStep.actionName}`);
  }
  return truncateName(firstStep?.actionName || "录制场景草稿");
};

const buildRecordedCasePayload = (baseData = {}) => {
  const existingSteps = Array.isArray(baseData.ui_flow) ? baseData.ui_flow : [];
  const nextSteps =
    exportMode.value === "append"
      ? [...existingSteps, ...recordedStepDrafts.value]
      : recordedStepDrafts.value;

  return {
    project: baseData.project || selectedProjectId.value,
    name: baseData.name || draftCaseName.value.trim(),
    description:
      draftCaseDescription.value.trim() || baseData.description || "",
    app_package: baseData.app_package ?? null,
    ui_flow: nextSteps,
    variables: Array.isArray(baseData.variables) ? baseData.variables : [],
    timeout: Number(baseData.timeout || 300),
    retry_count: Number(baseData.retry_count || 0),
  };
};

const createDraftCaseFromRecording = async () => {
  if (!canCreateDraftCase.value) {
    ElMessage.warning("请先选择项目，并给新用例起个名字");
    return;
  }
  exportingCase.value = true;
  try {
    const payload = buildRecordedCasePayload();
    const response = await createTestCase(payload);
    const created = response.data || response;
    await loadTestCases(selectedProjectId.value);
    selectedCaseId.value = created.id || null;
    ElMessage.success("录制步骤已生成新的测试用例草稿");
  } catch (error) {
    ElMessage.error(`创建用例草稿失败: ${error.message || "未知错误"}`);
  } finally {
    exportingCase.value = false;
  }
};

const syncRecordedInteractionsToCase = async () => {
  if (!selectedCaseId.value) {
    ElMessage.warning("请先选择一个已有用例");
    return;
  }
  exportingCase.value = true;
  try {
    const response = await getTestCaseDetail(selectedCaseId.value);
    const detail = response.data || response || {};
    const payload = buildRecordedCasePayload(detail);
    await updateTestCase(selectedCaseId.value, payload);
    await loadTestCases(selectedProjectId.value);
    ElMessage.success(
      exportMode.value === "append"
        ? "录制步骤已追加到用例"
        : "录制步骤已覆盖写入用例",
    );
  } catch (error) {
    ElMessage.error(`写入测试用例失败: ${error.message || "未知错误"}`);
  } finally {
    exportingCase.value = false;
  }
};

const openSceneBuilder = (caseId) => {
  if (caseId) {
    router.push({
      path: "/app-automation/scene-builder",
      query: { case_id: caseId },
    });
    return;
  }
  router.push("/app-automation/scene-builder");
};

const importActiveInteractionCandidate = async () => {
  if (!highlightedCandidate.value) {
    ElMessage.warning("当前没有命中的控件可导入");
    return;
  }
  await importOneCandidate(highlightedCandidate.value, {
    actionNameOverride: activeInteraction.value?.actionName || "",
  });
};

const validateHighlightedCandidate = async () => {
  if (!selectedDeviceId.value) {
    ElMessage.warning("请先选择设备");
    return;
  }
  if (!highlightedCandidate.value) {
    ElMessage.warning("请先选中一个候选元素");
    return;
  }

  const selector = buildInlineSelectorPayload(highlightedCandidate.value);
  if (!selector) {
    ElMessage.warning("当前候选元素缺少可验证的定位字段");
    return;
  }

  validatingSelector.value = true;
  selectorValidationResult.value = null;
  try {
    const response = await validateDeviceSelector(selectedDeviceId.value, {
      selector,
    });
    const data = response?.data?.data || response?.data || {};
    const pageState = data.page_state || null;
    const matchedCandidate = data.matched_candidate || null;
    let liveSnapshot = null;

    if (pageState) {
      liveSnapshot = appendSnapshot(pageState);
      currentSnapshotId.value = liveSnapshot.id;
    }

    const matched = Boolean(data.matched);
    let liveCandidate = null;
    if (matched && liveSnapshot && matchedCandidate) {
      liveCandidate =
        matchSnapshotCandidate(liveSnapshot, matchedCandidate) ||
        liveSnapshot.candidates.find(
          (candidate) =>
            candidate.raw_bounds === matchedCandidate.raw_bounds &&
            candidate.resource_id === matchedCandidate.resource_id,
        ) ||
        null;
      if (liveCandidate) {
        highlightedCandidateId.value = liveCandidate.id;
        hoveredCandidateId.value = liveCandidate.id;
      }
    }

    selectorValidationResult.value = {
      matched,
      score: Number(data.score || 0),
      summary: matched
        ? `实时命中：${liveCandidate?.display_name || matchedCandidate?.name || "候选元素"}`
        : "实时页面没有稳定命中该定位，请先微调边框或更换元素后再导入。",
    };

    if (matched) {
      ElMessage.success(selectorValidationResult.value.summary);
    } else {
      ElMessage.warning(selectorValidationResult.value.summary);
    }
  } catch (error) {
    const message = error?.response?.data?.msg || error?.message || "未知错误";
    ElMessage.error(`定位验证失败: ${message}`);
  } finally {
    validatingSelector.value = false;
  }
};

const handleCandidateSelectionChange = (rows) => {
  selectedCandidates.value = rows;
};

const focusCandidate = (candidate) => {
  highlightedCandidateId.value = candidate.id;
  hoveredCandidateId.value = candidate.id;
};

const hoverCandidate = (candidate) => {
  hoveredCandidateId.value = candidate.id;
};

const clearHoveredCandidate = () => {
  hoveredCandidateId.value = null;
};

const getCandidateIndex = (candidateId) => {
  return candidateIndexMap.value.get(candidateId) || "-";
};

const updateHighlightedBoundsField = (field, value) => {
  if (!highlightedCandidate.value) {
    return;
  }
  const nextBounds = {
    ...highlightedCandidate.value.bounds,
    [field]: Number(value || 0),
  };
  applyBoundsToCandidate(highlightedCandidate.value, nextBounds);
};

const updateHighlightedTextField = (field, value) => {
  if (!highlightedCandidate.value) {
    return;
  }
  highlightedCandidate.value[field] = String(value || "").trim();
};

const resetCandidateBounds = (candidate) => {
  if (!candidate?.original_bounds) {
    return;
  }
  applyBoundsToCandidate(candidate, { ...candidate.original_bounds });
};

const applyBoundsToCandidate = (candidate, nextBounds) => {
  const normalized = normalizeBoundsObject(nextBounds, {
    maxWidth: previewWidth.value,
    maxHeight: previewHeight.value,
  });
  candidate.bounds = normalized;
  candidate.raw_bounds = formatBounds(normalized);
};

const candidateBoxStyle = (candidate) => {
  const snapshot = currentSnapshot.value;
  if (!snapshot) {
    return {};
  }
  const width = previewWidth.value || 1;
  const height = previewHeight.value || 1;
  const bounds = candidate.bounds || {};
  const x1 = Number(bounds.x1 || 0);
  const y1 = Number(bounds.y1 || 0);
  const boxWidth = Number(bounds.width || 0);
  const boxHeight = Number(bounds.height || 0);
  return {
    left: `${(x1 / width) * 100}%`,
    top: `${(y1 / height) * 100}%`,
    width: `${(boxWidth / width) * 100}%`,
    height: `${(boxHeight / height) * 100}%`,
  };
};

const tapPointStyle = (point) => {
  if (!point) {
    return {};
  }
  const width = previewWidth.value || 1;
  const height = previewHeight.value || 1;
  return {
    left: `${(Number(point.x || 0) / width) * 100}%`,
    top: `${(Number(point.y || 0) / height) * 100}%`,
  };
};

const handlePreviewImageLoad = (event) => {
  previewWidth.value = event.target.naturalWidth || 1;
  previewHeight.value = event.target.naturalHeight || 1;
  previewClientWidth.value =
    event.target.clientWidth || event.target.naturalWidth || 1;
  previewClientHeight.value =
    event.target.clientHeight || event.target.naturalHeight || 1;
};

const startMove = (candidate, event) => {
  if (highlightedCandidate.value?.id !== candidate.id) {
    focusCandidate(candidate);
    return;
  }
  const point = pointerToNatural(event);
  if (!point) {
    return;
  }
  dragState.value = {
    mode: "move",
    handle: "",
    candidateId: candidate.id,
    startX: point.x,
    startY: point.y,
    originalBounds: { ...candidate.bounds },
  };
};

const startResize = (candidate, handle, event) => {
  const point = pointerToNatural(event);
  if (!point) {
    return;
  }
  dragState.value = {
    mode: "resize",
    handle,
    candidateId: candidate.id,
    startX: point.x,
    startY: point.y,
    originalBounds: { ...candidate.bounds },
  };
};

const handleGlobalPointerMove = (event) => {
  if (!dragState.value || !currentSnapshot.value) {
    return;
  }
  const point = pointerToNatural(event);
  if (!point) {
    return;
  }
  const candidate = currentSnapshot.value.candidates.find(
    (item) => item.id === dragState.value.candidateId,
  );
  if (!candidate) {
    return;
  }

  const dx = point.x - dragState.value.startX;
  const dy = point.y - dragState.value.startY;
  const original = dragState.value.originalBounds;
  let nextBounds = { ...original };

  if (dragState.value.mode === "move") {
    const width = original.width;
    const height = original.height;
    nextBounds = {
      x1: original.x1 + dx,
      y1: original.y1 + dy,
      x2: original.x1 + dx + width,
      y2: original.y1 + dy + height,
    };
  } else {
    if (dragState.value.handle.includes("n")) {
      nextBounds.y1 = original.y1 + dy;
    }
    if (dragState.value.handle.includes("s")) {
      nextBounds.y2 = original.y2 + dy;
    }
    if (dragState.value.handle.includes("w")) {
      nextBounds.x1 = original.x1 + dx;
    }
    if (dragState.value.handle.includes("e")) {
      nextBounds.x2 = original.x2 + dx;
    }
  }

  applyBoundsToCandidate(candidate, nextBounds);
};

const stopDragAdjust = () => {
  dragState.value = null;
};

const pointerToNatural = (event) => {
  const image = previewImageRef.value;
  if (!image) {
    return null;
  }
  const rect = image.getBoundingClientRect();
  if (!rect.width || !rect.height) {
    return null;
  }
  const offsetX = Math.max(0, Math.min(event.clientX - rect.left, rect.width));
  const offsetY = Math.max(0, Math.min(event.clientY - rect.top, rect.height));
  return {
    x: Math.round((offsetX / rect.width) * previewWidth.value),
    y: Math.round((offsetY / rect.height) * previewHeight.value),
  };
};

const copyCurrentUiXml = async () => {
  if (!currentSnapshot.value?.ui_xml) {
    ElMessage.warning("当前没有 UI 树可复制");
    return;
  }
  await copyText(currentSnapshot.value.ui_xml, "UI 树已复制");
};

const copyCurrentCandidates = async () => {
  if (!currentSnapshot.value?.candidates?.length) {
    ElMessage.warning("当前没有候选元素可复制");
    return;
  }
  await copyText(
    JSON.stringify(currentSnapshot.value.candidates, null, 2),
    "候选元素 JSON 已复制",
  );
};

const copyText = async (text, successMessage) => {
  try {
    await navigator.clipboard.writeText(text);
    ElMessage.success(successMessage);
  } catch (error) {
    ElMessage.error(`复制失败: ${error.message || "浏览器未授权"}`);
  }
};

const importSelectedCandidates = async () => {
  await importCandidates(selectedCandidates.value);
};

const importOneCandidate = async (candidate, options = {}) => {
  importingSingleId.value = candidate.id;
  try {
    const result = await importCandidates([candidate], {
      ...options,
      silentSuccess: true,
    });
    if (!result) {
      return;
    }
    if (result.updatedCount > 0) {
      ElMessage.success(`元素已存在，已更新 ${candidate.display_name}`);
    } else if (result.successCount > 0) {
      ElMessage.success(`已导入 ${candidate.display_name}`);
    } else {
      ElMessage.error(
        result.failed[0] || `导入 ${candidate.display_name} 失败`,
      );
    }
  } finally {
    importingSingleId.value = null;
  }
};

const importCandidates = async (candidates, options = {}) => {
  if (!selectedProjectId.value) {
    ElMessage.warning("请先选择项目");
    return;
  }
  if (!currentSnapshot.value) {
    ElMessage.warning("请先采集页面");
    return;
  }
  if (!candidates.length) {
    ElMessage.warning("请先勾选候选元素");
    return;
  }

  importing.value = true;
  let createdCount = 0;
  let updatedCount = 0;
  const failed = [];
  try {
    for (const candidate of candidates) {
      const payload = buildElementPayload(
        candidate,
        currentSnapshot.value,
        options,
      );
      try {
        await createAppElement(payload);
        createdCount += 1;
      } catch (error) {
        if (isDuplicateNameError(error)) {
          const existingElement = await findExistingElementByName(payload.name);
          if (existingElement) {
            await updateAppElement(
              existingElement.id,
              buildElementUpdatePayload(existingElement, payload),
            );
            updatedCount += 1;
            continue;
          }
        }
        const reason = extractApiErrorMessage(error);
        failed.push(`${candidate.display_name}: ${reason}`);
      }
    }

    const successCount = createdCount + updatedCount;
    if (!options.silentSuccess) {
      if (successCount > 0 && failed.length === 0) {
        if (updatedCount > 0 && createdCount === 0) {
          ElMessage.success(`成功更新 ${updatedCount} 个已有元素`);
        } else if (updatedCount > 0) {
          ElMessage.success(
            `成功导入 ${createdCount} 个，更新 ${updatedCount} 个元素`,
          );
        } else {
          ElMessage.success(`成功导入 ${createdCount} 个元素`);
        }
      } else if (successCount > 0) {
        const successLabel =
          updatedCount > 0
            ? `成功 ${createdCount} 个，更新 ${updatedCount} 个`
            : `成功 ${createdCount} 个`;
        ElMessage.warning(`${successLabel}，失败 ${failed.length} 个`);
      } else {
        ElMessage.error(failed[0] || "导入失败");
      }
    }
    return { successCount, createdCount, updatedCount, failed };
  } finally {
    importing.value = false;
  }
};

const buildElementPayload = (candidate, snapshot, options = {}) => {
  const activityKey = activityShortName(snapshot.activity) || "captured_page";
  const locatorKey = candidate.locator_key || buildLocatorKey(candidate);
  const actionName = String(options.actionNameOverride || "").trim();
  const manualNote = String(candidate.display_description || "").trim();
  return {
    name: truncateName(`${activityKey}.${locatorKey}`),
    element_type: "selector",
    project: selectedProjectId.value,
    tags: ["页面采集", activityKey],
    config: {
      package: candidate.package_name || snapshot.package_name || "",
      activity: snapshot.activity || "",
      resource_id: candidate.resource_id || "",
      text: candidate.text || "",
      content_desc: candidate.content_desc || "",
      hint: candidate.hint || "",
      class: candidate.class_name || "",
      locator_key: locatorKey,
      source_file: `page_capture/${activityKey}.yaml`,
      bounds: candidate.raw_bounds || formatBounds(candidate.bounds),
      clickable: !!candidate.clickable,
      focusable: false,
      enabled: true,
      description: actionName || candidate.display_name || "",
      manual_note: manualNote,
    },
  };
};

const extractApiErrorMessage = (error) => {
  const data = error?.response?.data;
  if (!data) {
    return error?.message || "未知错误";
  }

  const directMessage = [data.message, data.detail, data.msg, data.error]
    .map((item) => String(item || "").trim())
    .find(Boolean);
  if (directMessage) {
    return directMessage;
  }

  const fieldMessages = Object.entries(data)
    .filter(
      ([key]) =>
        !["message", "detail", "msg", "error", "non_field_errors"].includes(
          key,
        ),
    )
    .flatMap(([key, value]) =>
      normalizeApiErrorValues(value).map((item) => `${key}: ${item}`),
    );
  if (fieldMessages.length) {
    return fieldMessages.join("；");
  }

  const nonFieldMessages = normalizeApiErrorValues(data.non_field_errors);
  if (nonFieldMessages.length) {
    return nonFieldMessages.join("；");
  }

  return error?.message || "未知错误";
};

const normalizeApiErrorValues = (value) => {
  if (Array.isArray(value)) {
    return value.flatMap((item) => normalizeApiErrorValues(item));
  }
  if (value && typeof value === "object") {
    return Object.values(value).flatMap((item) =>
      normalizeApiErrorValues(item),
    );
  }
  const text = String(value || "").trim();
  return text ? [text] : [];
};

const isDuplicateNameError = (error) => {
  const messages = [
    ...normalizeApiErrorValues(error?.response?.data?.name),
    ...normalizeApiErrorValues(error?.response?.data?.non_field_errors),
    extractApiErrorMessage(error),
  ].map((item) => item.toLowerCase());

  return messages.some(
    (message) =>
      (message.includes("name") &&
        (message.includes("already exists") || message.includes("unique"))) ||
      message.includes("已存在") ||
      message.includes("唯一"),
  );
};

const findExistingElementByName = async (name) => {
  const response = await getAppElementList({
    project: selectedProjectId.value,
    search: name,
    page_size: 20,
  });
  const payload = response?.data || response || {};
  const results = Array.isArray(payload) ? payload : payload.results || [];
  return results.find((item) => item.name === name) || null;
};

const buildElementUpdatePayload = (existing, payload) => {
  const existingTags = Array.isArray(existing?.tags) ? existing.tags : [];
  const nextTags = Array.from(
    new Set([...existingTags, ...(payload.tags || [])]),
  );
  return {
    name: payload.name,
    element_type: payload.element_type,
    project: existing?.project?.id || existing?.project || payload.project,
    tags: nextTags,
    config: {
      ...(existing?.config || {}),
      ...(payload.config || {}),
    },
    is_active: existing?.is_active ?? true,
  };
};

const truncateName = (value) => String(value || "").slice(0, 200);

const formatBounds = (bounds = {}) => {
  const { x1 = 0, y1 = 0, x2 = 0, y2 = 0 } = bounds;
  return `[${x1},${y1}][${x2},${y2}]`;
};

const normalizeBoundsObject = (bounds = {}, limits = {}) => {
  const maxWidth =
    limits.maxWidth || previewWidth.value || Number.MAX_SAFE_INTEGER;
  const maxHeight =
    limits.maxHeight || previewHeight.value || Number.MAX_SAFE_INTEGER;
  const minSize = 12;

  let x1 = Number(bounds.x1 ?? 0);
  let y1 = Number(bounds.y1 ?? 0);
  let x2 = Number(bounds.x2 ?? x1 + Number(bounds.width || minSize));
  let y2 = Number(bounds.y2 ?? y1 + Number(bounds.height || minSize));

  if (x2 < x1) {
    [x1, x2] = [x2, x1];
  }
  if (y2 < y1) {
    [y1, y2] = [y2, y1];
  }

  x1 = Math.max(0, Math.min(x1, maxWidth));
  y1 = Math.max(0, Math.min(y1, maxHeight));
  x2 = Math.max(x1 + minSize, Math.min(x2, maxWidth));
  y2 = Math.max(y1 + minSize, Math.min(y2, maxHeight));

  return {
    x1: Math.round(x1),
    y1: Math.round(y1),
    x2: Math.round(x2),
    y2: Math.round(y2),
    width: Math.round(x2 - x1),
    height: Math.round(y2 - y1),
  };
};

const activityShortName = (activity) => {
  const clean = cleanText(activity);
  if (!clean) {
    return "";
  }
  return clean
    .split(".")
    .pop()
    .replace(/Activity$/i, "")
    .replace(/([a-z0-9])([A-Z])/g, "$1_$2")
    .replace(/[^a-zA-Z0-9_]+/g, "_")
    .replace(/^_+|_+$/g, "")
    .toLowerCase();
};

const humanizeActivityName = (activity) => {
  const shortName = activityShortName(activity);
  if (!shortName) {
    return "未知页面";
  }
  return shortName
    .split("_")
    .filter(Boolean)
    .map((token) => token.charAt(0).toUpperCase() + token.slice(1))
    .join(" ");
};

const clearHistory = () => {
  recording.value = false;
  waitingForTouch.value = false;
  snapshotHistory.value = [];
  recordedInteractions.value = [];
  activeInteractionId.value = "";
  interactionSequence.value = 0;
  currentSnapshotId.value = null;
  selectedCandidates.value = [];
  highlightedCandidateId.value = null;
  hoveredCandidateId.value = null;
  candidateSearch.value = "";
  showAllBoxes.value = true;
  draftCaseName.value = "";
  draftCaseDescription.value = "";
};
</script>

<style scoped lang="scss">
.page-capture-workbench {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.workspace-row {
  margin-bottom: 8px;
}

.control-card,
.history-card,
.preview-card,
.candidate-card {
  border-radius: 16px;
}

.history-card + .history-card {
  margin-top: 16px;
}

.recorder-card {
  margin-bottom: 16px;
}

.section-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.section-header.compact {
  align-items: flex-start;
}

.section-title {
  font-size: 18px;
  font-weight: 600;
  color: #1f2937;
}

.section-title.small {
  font-size: 16px;
}

.section-subtitle {
  margin-top: 4px;
  color: #6b7280;
  font-size: 13px;
}

.section-subtitle.compact {
  margin-top: 2px;
}

.capture-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 8px;
}

.capture-hint {
  color: #6b7280;
  font-size: 13px;
  line-height: 1.6;
}

.summary-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 10px;
}

.summary-item {
  padding: 12px;
  background: linear-gradient(135deg, #f8fafc, #eef2ff);
  border: 1px solid #e5e7eb;
  border-radius: 12px;
}

.summary-label {
  color: #6b7280;
  font-size: 12px;
}

.summary-value {
  margin-top: 6px;
  color: #111827;
  font-size: 24px;
  font-weight: 700;
}

.empty-panel {
  min-height: 260px;
  display: flex;
  align-items: center;
  justify-content: center;
}

.empty-panel--compact {
  min-height: 180px;
}

.history-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
  max-height: 700px;
  overflow-y: auto;
}

.history-list--compact {
  max-height: 320px;
}

.history-item {
  width: 100%;
  padding: 12px;
  border: 1px solid #e5e7eb;
  border-radius: 12px;
  background: #fff;
  text-align: left;
  cursor: pointer;
  transition: all 0.2s ease;
}

.history-item:hover,
.history-item.active {
  border-color: #409eff;
  box-shadow: 0 8px 18px rgba(64, 158, 255, 0.12);
}

.history-item__title {
  display: flex;
  justify-content: space-between;
  gap: 8px;
  color: #111827;
  font-weight: 600;
}

.history-item__meta,
.history-item__time {
  margin-top: 6px;
  color: #6b7280;
  font-size: 12px;
  word-break: break-all;
}

.meta-line {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-top: 6px;
}

.preview-stage {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.preview-toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
}

.preview-toolbar__text {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 6px;
  color: #374151;
  font-size: 13px;
}

.preview-toolbar__tap {
  padding: 4px 10px;
  border-radius: 999px;
  background: rgba(249, 115, 22, 0.12);
  color: #c2410c;
  font-size: 12px;
  font-weight: 600;
}

.preview-toolbar__hint {
  color: #6b7280;
  font-size: 12px;
}

.live-preview-bar {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  padding: 10px 12px;
  border: 1px solid #dbeafe;
  border-radius: 12px;
  background: linear-gradient(135deg, #eff6ff, #f8fafc);
}

.live-preview-bar__main {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
}

.live-preview-bar__rate {
  width: 96px;
}

.live-preview-bar__status {
  color: #64748b;
  font-size: 12px;
}

.live-preview-bar__status.error {
  color: #dc2626;
}

.image-shell {
  border: 1px solid #e5e7eb;
  border-radius: 14px;
  background: #f8fafc;
  padding: 12px;
  overflow: auto;
}

.image-wrapper {
  position: relative;
  display: inline-block;
  max-width: 100%;
}

.preview-image {
  display: block;
  max-width: 100%;
  border-radius: 10px;
}

.tap-point-marker {
  position: absolute;
  z-index: 3;
  transform: translate(-50%, -50%);
  pointer-events: none;
}

.tap-point-marker__dot {
  display: block;
  width: 18px;
  height: 18px;
  border: 3px solid #fff;
  border-radius: 50%;
  background: #f97316;
  box-shadow: 0 0 0 6px rgba(249, 115, 22, 0.24);
}

.tap-point-marker__label {
  display: inline-block;
  margin-top: 8px;
  margin-left: 12px;
  padding: 3px 8px;
  border-radius: 999px;
  background: rgba(15, 23, 42, 0.88);
  color: #fff;
  font-size: 12px;
  white-space: nowrap;
}

.candidate-box {
  position: absolute;
  border: 2px solid rgba(52, 211, 153, 0.92);
  background: rgba(52, 211, 153, 0.12);
  box-sizing: border-box;
  cursor: pointer;
}

.candidate-box.selected {
  border-color: rgba(251, 191, 36, 0.96);
  background: rgba(251, 191, 36, 0.16);
}

.candidate-box.hovered {
  border-color: rgba(59, 130, 246, 0.96);
  background: rgba(59, 130, 246, 0.14);
  z-index: 1;
}

.candidate-box.active {
  border-color: rgba(239, 68, 68, 0.96);
  background: rgba(239, 68, 68, 0.18);
  cursor: move;
  z-index: 2;
}

.candidate-box__index {
  position: absolute;
  left: -1px;
  top: -1px;
  min-width: 18px;
  height: 18px;
  padding: 0 4px;
  border-radius: 0 0 8px 0;
  background: rgba(15, 23, 42, 0.82);
  color: #fff;
  font-size: 11px;
  line-height: 18px;
  text-align: center;
}

.candidate-box__label {
  position: absolute;
  left: 0;
  top: -24px;
  padding: 3px 8px;
  border-radius: 8px;
  background: #ef4444;
  color: #fff;
  font-size: 12px;
  white-space: nowrap;
}

.candidate-box__handle {
  position: absolute;
  width: 10px;
  height: 10px;
  border: 1px solid #fff;
  border-radius: 50%;
  background: #ef4444;
}

.candidate-box__handle--nw {
  top: -6px;
  left: -6px;
  cursor: nwse-resize;
}

.candidate-box__handle--ne {
  top: -6px;
  right: -6px;
  cursor: nesw-resize;
}

.candidate-box__handle--se {
  right: -6px;
  bottom: -6px;
  cursor: nwse-resize;
}

.candidate-box__handle--sw {
  left: -6px;
  bottom: -6px;
  cursor: nesw-resize;
}

.candidate-filters {
  display: flex;
  flex-direction: column;
  gap: 10px;
  margin-bottom: 12px;
}

.recorder-detail {
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.recorder-detail__field,
.recorder-detail__item {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.recorder-detail__grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
}

.recorder-detail__grid--editing {
  margin-top: -2px;
}

.recorder-detail__label {
  color: #6b7280;
  font-size: 12px;
}

.recorder-detail__value,
.recorder-detail__title {
  color: #111827;
  font-size: 13px;
  font-weight: 600;
}

.recorder-detail__desc {
  color: #4b5563;
  font-size: 12px;
  line-height: 1.6;
  word-break: break-all;
}

.recorder-detail__summary {
  padding: 12px;
  border: 1px solid #e5e7eb;
  border-radius: 12px;
  background: #f8fafc;
}

.recorder-detail__item--wide {
  grid-column: 1 / -1;
}

.recorder-detail__actions {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.validation-result {
  margin-top: 12px;
  padding: 10px 12px;
  border-radius: 10px;
  border: 1px solid #dbeafe;
  background: #eff6ff;
}

.validation-result--success {
  border-color: #bbf7d0;
  background: #f0fdf4;
}

.validation-result--warning {
  border-color: #fde68a;
  background: #fffbeb;
}

.validation-result__title {
  font-size: 13px;
  font-weight: 600;
  color: #111827;
}

.validation-result__desc {
  margin-top: 4px;
  font-size: 12px;
  line-height: 1.6;
  color: #4b5563;
}

.recorder-detail__checkbox {
  margin-top: 6px;
}

.scene-export {
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.scene-export__plain {
  width: 100%;
  min-height: 32px;
  display: flex;
  align-items: center;
  color: #111827;
}

.scene-export__summary {
  color: #6b7280;
  font-size: 13px;
  line-height: 1.7;
}

.scene-export__steps {
  display: flex;
  flex-direction: column;
  gap: 10px;
  max-height: 320px;
  overflow: auto;
  padding-right: 4px;
}

.scene-export__step {
  padding: 12px;
  border: 1px solid #e5e7eb;
  border-radius: 12px;
  background: #f8fafc;
}

.scene-export__step-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  color: #111827;
  font-weight: 600;
}

.scene-export__step-desc {
  margin-top: 6px;
  color: #6b7280;
  font-size: 13px;
  line-height: 1.6;
  word-break: break-word;
}

.scene-export__actions {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.adjust-panel {
  display: flex;
  flex-direction: column;
  gap: 10px;
  margin-bottom: 12px;
  padding: 12px;
  border: 1px solid #e5e7eb;
  border-radius: 12px;
  background: #fafcff;
}

.adjust-panel__header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 10px;
}

.adjust-panel__title {
  color: #111827;
  font-size: 14px;
  font-weight: 600;
}

.adjust-panel__desc {
  margin-top: 4px;
  color: #6b7280;
  font-size: 12px;
}

.adjust-text-grid {
  display: grid;
  grid-template-columns: 1fr;
  gap: 8px;
}

.adjust-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 8px;
}

.adjust-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  color: #6b7280;
  font-size: 12px;
}

.candidate-order {
  color: #111827;
  font-size: 12px;
  font-weight: 700;
}

.candidate-main__title {
  color: #111827;
  font-weight: 600;
}

.source-block__title {
  color: #111827;
  font-size: 12px;
  font-weight: 600;
  line-height: 1.5;
}

.source-block__desc,
.candidate-main__desc,
.locator-block,
.class-text {
  color: #6b7280;
  font-size: 12px;
  line-height: 1.5;
  word-break: break-all;
}

.device-option {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 8px;
}

@media (max-width: 992px) {
  .summary-grid {
    grid-template-columns: 1fr;
  }

  .recorder-detail__grid {
    grid-template-columns: 1fr;
  }
}
</style>
