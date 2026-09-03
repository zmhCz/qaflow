<template>
  <div class="exploration-page">
    <div class="hero-card">
      <div>
        <p class="eyebrow">APP 自动化 / 受控探索</p>
        <h2>AI 探索测试</h2>
        <p class="hero-desc">
          通过受控规则探索自动覆盖 APP
          页面路径，内置高风险动作护栏，并沉淀截图、页面结构、日志和可转化的用例草稿。
        </p>
      </div>
      <div class="hero-actions">
        <el-button :icon="Refresh" :loading="loading" @click="loadTasks"
          >刷新</el-button
        >
        <el-button type="primary" :icon="Plus" @click="openCreateDialog"
          >新建探索任务</el-button
        >
      </div>
    </div>

    <el-card class="filter-card" shadow="never">
      <el-form :inline="true" :model="query" class="filter-form">
        <el-form-item label="项目">
          <el-select
            v-model="query.project"
            clearable
            filterable
            placeholder="全部项目"
            style="width: 180px"
            @change="loadTasks"
          >
            <el-option
              v-for="item in projects"
              :key="item.id"
              :label="item.name"
              :value="item.id"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="状态">
          <el-select
            v-model="query.status"
            clearable
            placeholder="全部状态"
            style="width: 150px"
            @change="loadTasks"
          >
            <el-option label="等待中" value="pending" />
            <el-option label="执行中" value="running" />
            <el-option label="已完成" value="completed" />
            <el-option label="执行异常" value="error" />
            <el-option label="已停止" value="stopped" />
          </el-select>
        </el-form-item>
        <el-form-item label="搜索">
          <el-input
            v-model="query.search"
            clearable
            placeholder="任务名 / 目标 / 包名 / 设备"
            style="width: 260px"
            @keyup.enter="loadTasks"
            @clear="loadTasks"
          />
        </el-form-item>
        <el-form-item>
          <el-button type="primary" plain @click="loadTasks">筛选</el-button>
        </el-form-item>
      </el-form>
    </el-card>

    <el-table
      v-loading="loading"
      :data="tasks"
      class="task-table"
      empty-text="暂无探索任务"
    >
      <el-table-column
        prop="name"
        label="任务名称"
        min-width="220"
        show-overflow-tooltip
      >
        <template #default="{ row }">
          <div class="task-name-cell">
            <span>{{ row.name }}</span>
            <el-tag
              v-if="row.source_task"
              size="small"
              type="success"
              effect="plain"
            >
              {{ sourceTypeText(row.source_type) }}
            </el-tag>
          </div>
        </template>
      </el-table-column>
      <el-table-column prop="project_name" label="项目" width="140">
        <template #default="{ row }">{{ row.project_name || "-" }}</template>
      </el-table-column>
      <el-table-column
        prop="package_name"
        label="包名"
        min-width="210"
        show-overflow-tooltip
      >
        <template #default="{ row }">{{ row.package_name || "-" }}</template>
      </el-table-column>
      <el-table-column
        prop="device_name"
        label="设备"
        min-width="150"
        show-overflow-tooltip
      >
        <template #default="{ row }">{{ row.device_name || "-" }}</template>
      </el-table-column>
      <el-table-column label="状态" width="110">
        <template #default="{ row }">
          <el-tooltip
            v-if="row.execution_health?.is_stale"
            :content="
              row.execution_health.suggestion || row.execution_health.message
            "
            placement="top"
          >
            <el-tag
              :type="
                row.execution_health.level === 'danger' ? 'danger' : 'warning'
              "
            >
              {{ statusText(row.status) }}异常
            </el-tag>
          </el-tooltip>
          <el-tag v-else :type="statusTag(row.status)">{{
            statusText(row.status)
          }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="进度" width="150">
        <template #default="{ row }">
          <el-progress
            :percentage="Number(row.progress || 0)"
            :stroke-width="8"
          />
          <div v-if="row.execution_health?.is_stale" class="task-stage stale">
            {{ row.execution_health.message }}
          </div>
          <div
            v-if="row.summary?.current_stage || row.status === 'running'"
            class="task-stage"
          >
            {{ row.summary?.current_stage || "执行中，正在同步状态" }}
          </div>
        </template>
      </el-table-column>
      <el-table-column label="探索结果" width="170">
        <template #default="{ row }">
          <span
            >{{ row.total_steps || 0 }} 步 / {{ row.explored_pages || 0 }} 页 /
            {{ row.issue_count || 0 }} 问题</span
          >
        </template>
      </el-table-column>
      <el-table-column label="更新时间" width="170">
        <template #default="{ row }">{{ formatTime(row.updated_at) }}</template>
      </el-table-column>
      <el-table-column label="操作" width="320" fixed="right">
        <template #default="{ row }">
          <el-button link type="primary" @click="openReport(row)"
            >报告</el-button
          >
          <el-button
            v-if="row.status !== 'running'"
            link
            type="primary"
            @click="openEditDialog(row)"
            >编辑</el-button
          >
          <el-button
            v-if="row.status !== 'running'"
            link
            type="success"
            :loading="isTaskStarting(row.id)"
            :disabled="isTaskStarting(row.id)"
            @click="runTask(row)"
          >
            {{
              row.status === "completed"
                ? "重新执行"
                : row.status === "error"
                  ? "重试"
                  : "开始"
            }}
          </el-button>
          <el-button
            v-if="canRunConsistency(row)"
            link
            type="warning"
            :loading="isConsistencyStarting(row.id)"
            :disabled="isTaskStarting(row.id) || isConsistencyStarting(row.id)"
            @click="runConsistency(row)"
          >
            跑三次一致性
          </el-button>
          <el-button
            v-if="row.status === 'running' || row.status === 'pending'"
            link
            type="warning"
            @click="stopTask(row)"
            >停止</el-button
          >
          <el-button
            v-if="canCheckTaskDevice(row)"
            link
            type="warning"
            :loading="isDeviceHealthChecking(row)"
            @click="checkTaskDevice(row)"
          >
            检查设备
          </el-button>
          <el-button
            link
            type="danger"
            :disabled="row.status === 'running'"
            @click="deleteTask(row)"
            >删除</el-button
          >
        </template>
      </el-table-column>
    </el-table>

    <el-pagination
      v-show="total > 0"
      v-model:current-page="page"
      v-model:page-size="pageSize"
      :total="total"
      :page-sizes="[10, 20, 50]"
      layout="total, sizes, prev, pager, next, jumper"
      class="pager"
      @size-change="loadTasks"
      @current-change="loadTasks"
    />

    <el-dialog
      v-model="createVisible"
      :title="dialogTitle"
      width="680px"
      :close-on-click-modal="false"
    >
      <el-form ref="formRef" :model="form" :rules="rules" label-width="110px">
        <el-form-item label="任务名称" prop="name">
          <el-input v-model="form.name" placeholder="例如：首页冒烟探索" />
        </el-form-item>
        <el-form-item label="项目" prop="project">
          <el-select
            v-model="form.project"
            clearable
            filterable
            placeholder="选择项目"
            style="width: 100%"
          >
            <el-option
              v-for="item in projects"
              :key="item.id"
              :label="item.name"
              :value="item.id"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="应用包名" prop="app_package">
          <el-select
            v-model="form.app_package"
            clearable
            filterable
            placeholder="选择被测应用"
            style="width: 100%"
          >
            <el-option
              v-for="item in packages"
              :key="item.id"
              :label="`${item.name} (${item.package_name})`"
              :value="item.id"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="执行设备" prop="device">
          <el-select
            v-model="form.device"
            clearable
            filterable
            placeholder="选择已连接设备"
            style="width: 100%"
          >
            <el-option
              v-for="item in devices"
              :key="item.id"
              :label="item.name || item.device_id"
              :value="item.id"
            >
              <span>{{ item.name || item.device_id }}</span>
              <span class="option-meta">{{ item.status }}</span>
            </el-option>
          </el-select>
        </el-form-item>
        <el-form-item label="探索策略">
          <el-select
            v-model="form.strategy"
            placeholder="选择探索策略"
            style="width: 100%"
          >
            <el-option
              label="目标巡检：按清单受控点击（推荐）"
              value="target_inspection"
            />
            <el-option label="基础探索：通用控件遍历" value="rule_mvp" />
            <el-option label="冒烟探索：优先主入口和核心按钮" value="smoke" />
            <el-option
              label="稳定性探索：多入口遍历和异常发现"
              value="stability"
            />
            <el-option label="表单探索：优先输入框和提交按钮" value="form" />
            <el-option label="列表探索：优先列表项和滑动" value="list" />
          </el-select>
        </el-form-item>
        <el-form-item :label="isTargetInspectionMode ? '巡检说明' : '探索目标'">
          <el-input
            v-model="form.objective"
            type="textarea"
            :rows="3"
            :placeholder="
              isTargetInspectionMode
                ? '说明本轮巡检范围，例如：社区首页一级入口巡检，不进入搜索'
                : '告诉执行人员这次想覆盖什么，例如：探索登录后的首页主导航和社区入口'
            "
          />
        </el-form-item>
        <el-form-item
          :label="isTargetInspectionMode ? '目标清单' : '入口关键词'"
        >
          <el-select
            v-model="form.entry_keywords"
            multiple
            filterable
            allow-create
            default-first-option
            :placeholder="
              isTargetInspectionMode
                ? '例如：首页、价格、活动、公告；支持直接粘贴多行'
                : '例如：我的、社区、创建；支持直接粘贴多行或逗号分隔'
            "
            style="width: 100%"
            @paste.capture="handleEntryKeywordsPaste"
          >
            <el-option
              v-for="item in defaultEntryKeywords"
              :key="item"
              :label="item"
              :value="item"
            />
          </el-select>
          <div class="form-tip">
            {{
              isTargetInspectionMode
                ? "目标巡检会严格按清单逐项查找并点击；找不到就记录未找到，不会点击无关控件。支持批量粘贴，按换行、逗号、顿号、分号或空格自动拆分。"
                : "入口关键词是候选入口，命中任意一个就开始正式探索，不会继续在二级页查找其它一级入口；多步路径请配置到“起始导航”。支持批量粘贴，按换行、逗号、顿号、分号或空格自动拆分。"
            }}
          </div>
        </el-form-item>
        <el-form-item label="起始说明">
          <el-input
            v-model="form.start_note"
            placeholder="例如：请先手动停留在首页；未登录场景停留在登录页"
          />
        </el-form-item>
        <el-form-item label="起始导航">
          <div class="start-actions-editor">
            <div
              v-for="(action, index) in form.start_actions"
              :key="index"
              class="start-action-row"
            >
              <el-select
                v-model="action.type"
                placeholder="动作"
                class="start-action-type"
              >
                <el-option label="点击文字" value="tap_text" />
                <el-option label="点击 resource-id" value="tap_resource_id" />
                <el-option label="点击坐标" value="tap_pos" />
                <el-option label="等待" value="wait" />
                <el-option label="滑动" value="swipe" />
                <el-option label="返回" value="back" />
              </el-select>
              <el-input
                v-if="['tap_text', 'tap_resource_id'].includes(action.type)"
                v-model="action.value"
                :placeholder="
                  action.type === 'tap_text'
                    ? '例如：我的 / 消息 / 创建'
                    : '例如：btnCreate 或 com.xx:id/btnCreate'
                "
                class="start-action-value"
              />
              <template v-else-if="action.type === 'tap_pos'">
                <el-input-number
                  v-model="action.x"
                  :min="0"
                  placeholder="x"
                  class="start-action-number"
                />
                <el-input-number
                  v-model="action.y"
                  :min="0"
                  placeholder="y"
                  class="start-action-number"
                />
              </template>
              <el-input-number
                v-else-if="action.type === 'wait'"
                v-model="action.seconds"
                :min="0.2"
                :step="0.5"
                class="start-action-number"
              />
              <el-select
                v-else-if="action.type === 'swipe'"
                v-model="action.direction"
                class="start-action-value"
              >
                <el-option label="向上滑" value="up" />
                <el-option label="向下滑" value="down" />
                <el-option label="向左滑" value="left" />
                <el-option label="向右滑" value="right" />
              </el-select>
              <span v-else class="form-tip">执行系统返回</span>
              <el-button link type="danger" @click="removeStartAction(index)"
                >删除</el-button
              >
            </div>
            <div class="start-action-toolbar">
              <el-button plain type="primary" @click="addStartAction"
                >添加起始导航步骤</el-button
              >
              <el-button
                plain
                type="success"
                :loading="startShotLoading"
                :disabled="!form.device"
                @click="openStartPointPicker"
              >
                从截图选点
              </el-button>
            </div>
            <div class="form-tip">
              探索开始前会自动启动 APP，再按这里的步骤进入目标页面；不配置则从
              APP 启动后的当前页开始。
            </div>
            <div
              v-if="startActionSafetySummary.total"
              class="start-action-safety"
              :class="startActionSafetySummary.level"
            >
              <div class="safety-title">
                <strong>起始导航安全检查</strong>
                <el-tag
                  :type="startActionSafetySummary.tagType"
                  effect="plain"
                  >{{ startActionSafetySummary.label }}</el-tag
                >
              </div>
              <div class="safety-metrics">
                <span>{{ startActionSafetySummary.total }} 个动作</span>
                <span>{{ startActionSafetySummary.low }} 个低风险</span>
                <span>{{ startActionSafetySummary.caution }} 个需确认</span>
                <span>{{ startActionSafetySummary.forbidden }} 个禁止</span>
              </div>
              <div
                v-if="startActionSafetySummary.messages.length"
                class="safety-messages"
              >
                <div
                  v-for="message in startActionSafetySummary.messages"
                  :key="message"
                >
                  {{ message }}
                </div>
              </div>
            </div>
          </div>
        </el-form-item>
        <el-row :gutter="12">
          <el-col :span="12">
            <el-form-item label="最大步数" prop="max_steps">
              <el-input-number
                v-model="form.max_steps"
                :min="1"
                :max="200"
                style="width: 100%"
              />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="最大时长" prop="max_duration">
              <el-input-number
                v-model="form.max_duration"
                :min="10"
                :max="7200"
                style="width: 100%"
              >
                <template #suffix>秒</template>
              </el-input-number>
            </el-form-item>
          </el-col>
        </el-row>
        <el-form-item label="黑名单">
          <el-select
            v-model="form.blacklist_keywords"
            multiple
            filterable
            allow-create
            default-first-option
            placeholder="输入后回车，可防止高危操作"
            style="width: 100%"
          >
            <el-option
              v-for="item in defaultBlacklist"
              :key="item"
              :label="item"
              :value="item"
            />
          </el-select>
          <div class="form-tip">
            建议保留删除、支付、注销、解散等高风险词，探索器命中这些文案会跳过。
          </div>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="createVisible = false">取消</el-button>
        <el-button
          v-if="!editingId"
          plain
          type="success"
          :loading="saveAndRunLoading"
          :disabled="saving || startActionSafetySummary.forbidden > 0"
          @click="submitTask(true)"
        >
          保存并执行
        </el-button>
        <el-button
          type="primary"
          :loading="saving"
          :disabled="
            saveAndRunLoading || startActionSafetySummary.forbidden > 0
          "
          @click="submitTask(false)"
        >
          保存
        </el-button>
      </template>
    </el-dialog>

    <el-dialog
      v-model="startPointPickerVisible"
      title="从截图选择点击位置"
      width="420px"
      append-to-body
    >
      <div class="start-point-picker">
        <div class="form-tip">
          点击截图中的目标位置，系统会按真机截图尺寸换算坐标，并自动添加为一条起始导航点击步骤。
        </div>
        <div class="start-point-shot-wrap">
          <img
            v-if="startPointScreenshot"
            ref="startPointImageRef"
            :src="startPointScreenshot"
            class="start-point-shot"
            alt="device screenshot"
            @click="pickStartPoint"
          />
          <el-empty v-else description="暂无截图" />
        </div>
      </div>
      <template #footer>
        <el-button @click="startPointPickerVisible = false">取消</el-button>
      </template>
    </el-dialog>

    <el-drawer
      v-model="reportVisible"
      size="72%"
      title="探索报告"
      destroy-on-close
    >
      <div v-if="currentTask" class="report">
        <el-card
          v-show="reportActiveTab === 'overview'"
          shadow="never"
          class="report-card report-workbench-card"
        >
          <template #header>
            <div class="section-title">
              <span>报告处理台</span>
              <el-tag :type="reportWorkbenchLevel.type" effect="plain">{{
                reportWorkbenchLevel.label
              }}</el-tag>
            </div>
          </template>
          <div class="report-workbench-main">
            <div class="report-workbench-summary">
              <span class="decision-kicker">质量决策</span>
              <strong>{{ qualityDecision.title }}</strong>
              <p>{{ qualityDecision.description }}</p>
              <div class="report-next-line">
                <span>建议下一步</span>
                <strong>{{ qualityDecision.nextAction }}</strong>
              </div>
              <div class="report-workbench-metrics">
                <div
                  v-for="metric in qualityDecision.metrics.slice(0, 3)"
                  :key="metric.label"
                  class="report-metric-chip"
                >
                  <span>{{ metric.label }}</span>
                  <strong>{{ metric.value }}</strong>
                </div>
              </div>
              <div
                v-if="qualityDecision.reasons.length"
                class="decision-reason-row compact"
              >
                <el-tag
                  v-for="item in qualityDecision.reasons.slice(0, 3)"
                  :key="item"
                  :type="qualityDecision.tagType"
                  effect="plain"
                >
                  {{ item }}
                </el-tag>
              </div>
            </div>
            <div class="report-workbench-actions">
              <el-button
                v-for="action in postRunGuide.primaryActions"
                :key="action.key"
                :type="action.type || 'primary'"
                :plain="action.plain !== false"
                @click="handlePostRunAction(action.key)"
              >
                {{ action.label }}
              </el-button>
              <el-dropdown trigger="click" @command="handleReportMoreAction">
                <el-button plain>
                  更多操作
                  <el-icon class="el-icon--right"><ArrowDown /></el-icon>
                </el-button>
                <template #dropdown>
                  <el-dropdown-menu>
                    <el-dropdown-item
                      v-for="action in reportMoreActions"
                      :key="action.key"
                      :command="action.key"
                      :disabled="action.disabled"
                    >
                      {{ action.label }}
                    </el-dropdown-item>
                  </el-dropdown-menu>
                </template>
              </el-dropdown>
            </div>
          </div>
          <div class="report-quick-toggle">
            <span
              >默认只展示结论、问题和证据入口；需要定位细节时再展开高级详情。</span
            >
            <el-button
              size="small"
              text
              type="primary"
              @click="showReportDetails = !showReportDetails"
            >
              {{ showReportDetails ? "收起高级详情" : "展开高级详情" }}
            </el-button>
          </div>
          <div v-if="showReportDetails" class="report-details-fold">
            <div class="report-workflow-strip compact">
              <div
                v-for="(step, index) in postRunGuide.steps"
                :key="step.title"
                class="report-workflow-step"
                :class="{ active: step.active }"
              >
                <span class="workflow-index">{{ index + 1 }}</span>
                <div>
                  <strong>{{ step.title }}</strong>
                  <p>{{ step.desc }}</p>
                </div>
              </div>
            </div>
            <el-collapse class="report-roadmap-collapse">
              <el-collapse-item title="平台沉淀进度（高级）" name="roadmap">
                <div class="roadmap-progress-board">
                  <div
                    v-for="stage in roadmapStageGroups"
                    :key="stage.key"
                    class="roadmap-stage-card"
                    :class="`stage-${stage.level}`"
                  >
                    <div class="roadmap-stage-head">
                      <div>
                        <strong>{{ stage.title }}</strong>
                        <span>{{ stage.description }}</span>
                      </div>
                      <el-progress
                        type="circle"
                        :percentage="stage.progress"
                        :width="52"
                        :stroke-width="6"
                        :status="
                          stage.level === 'success' ? 'success' : undefined
                        "
                      />
                    </div>
                    <div class="roadmap-stage-list">
                      <div
                        v-for="item in stage.items"
                        :key="item.key"
                        class="roadmap-stage-item"
                        :class="`item-${item.status}`"
                      >
                        <el-tag
                          :type="roadmapStatusTagType(item.status)"
                          effect="plain"
                          size="small"
                        >
                          {{ roadmapStatusText(item.status) }}
                        </el-tag>
                        <div>
                          <strong>{{ item.title }}</strong>
                          <span>{{ item.desc }}</span>
                        </div>
                        <el-button
                          v-if="item.action"
                          text
                          type="primary"
                          size="small"
                          @click="handlePostRunAction(item.action)"
                        >
                          去处理
                        </el-button>
                      </div>
                    </div>
                  </div>
                </div>
              </el-collapse-item>
            </el-collapse>
          </div>
          <div class="report-evidence-shortcuts">
            <div>
              <strong>关键证据入口</strong>
              <span
                >需要排查时优先看截图定位和日志；对外同步只复制任务简报。</span
              >
            </div>
            <div class="report-evidence-actions">
              <el-button
                size="small"
                plain
                type="primary"
                @click="handlePostRunAction('evidence')"
                >截图证据</el-button
              >
              <el-button
                size="small"
                plain
                :disabled="!currentTask.logcat?.available"
                @click="handlePostRunAction('logs')"
                >日志附件</el-button
              >
              <el-button size="small" plain @click="copyTaskBrief"
                >复制简报</el-button
              >
            </div>
          </div>
          <div
            v-if="aiNextRoundReadiness.visible && showReportDetails"
            class="next-round-ready-card"
          >
            <div>
              <span class="decision-kicker">下一轮受控巡检</span>
              <strong>{{ aiNextRoundReadiness.title }}</strong>
              <p>{{ aiNextRoundReadiness.description }}</p>
              <div class="next-round-ready-meta">
                <el-tag effect="plain" type="success"
                  >候选目标 {{ aiNextRoundCandidateTargets.length }}</el-tag
                >
                <el-tag effect="plain" type="info"
                  >起始导航
                  {{
                    aiPlanStartActions.length ||
                    aiActionsToStartActions().length
                  }}</el-tag
                >
                <el-tag
                  v-if="aiNextRoundReadiness.blocker"
                  effect="plain"
                  type="warning"
                >
                  {{ aiNextRoundReadiness.blocker }}
                </el-tag>
              </div>
            </div>
            <div class="next-round-ready-actions">
              <el-button plain type="primary" @click="handlePostRunAction('ai')"
                >查看 AI 计划</el-button
              >
              <el-button
                type="success"
                :disabled="!aiNextRoundReadiness.ready"
                @click="handlePostRunAction('next_round')"
              >
                生成下一轮巡检草稿
              </el-button>
            </div>
          </div>
          <el-alert
            v-if="taskExecutionHealth.is_stale"
            class="execution-health-alert"
            :type="taskExecutionHealth.level === 'danger' ? 'error' : 'warning'"
            :title="taskExecutionHealth.message"
            :description="taskExecutionHealth.suggestion"
            show-icon
            :closable="false"
          />
          <div
            v-if="targetAcceptanceSummary.available && showReportDetails"
            class="target-acceptance-panel"
            :class="`acceptance-${targetAcceptanceSummary.level}`"
          >
            <div class="target-acceptance-head">
              <div>
                <strong>{{ targetAcceptanceSummary.title }}</strong>
                <span>{{ targetAcceptanceSummary.description }}</span>
              </div>
              <el-tag :type="targetAcceptanceSummary.tagType" effect="plain">
                {{ targetAcceptanceSummary.badge }}
              </el-tag>
            </div>
            <div class="target-acceptance-list">
              <div
                v-for="item in targetAcceptanceVisibleItems"
                :key="item.key"
                class="target-acceptance-item"
                :class="{ failed: !item.passed }"
              >
                <el-tag
                  :type="item.passed ? 'success' : 'warning'"
                  effect="plain"
                >
                  {{ item.passed ? "通过" : "未达标" }}
                </el-tag>
                <div>
                  <strong>{{ item.label }}</strong>
                  <span>{{ item.actual }} / {{ item.expected }}</span>
                  <p v-if="!item.passed">{{ item.suggestion }}</p>
                </div>
              </div>
            </div>
            <div
              v-if="targetAcceptanceIssueCards.length"
              class="target-acceptance-guidance"
            >
              <div
                v-for="card in targetAcceptanceIssueCards"
                :key="card.key"
                class="target-acceptance-guide-card"
              >
                <div class="acceptance-guide-head">
                  <div>
                    <el-tag :type="card.tagType" effect="dark">{{
                      card.badge
                    }}</el-tag>
                    <strong>{{ card.title }}</strong>
                  </div>
                  <el-button
                    text
                    type="primary"
                    @click="handlePostRunAction(card.action)"
                  >
                    {{ card.actionLabel }}
                  </el-button>
                </div>
                <p>{{ card.reason }}</p>
                <div
                  v-if="card.detailRows.length"
                  class="acceptance-guide-details"
                >
                  <span v-for="row in card.detailRows" :key="row.label">
                    {{ row.label }}：{{ row.value }}
                  </span>
                </div>
                <div
                  v-if="card.targets.length"
                  class="acceptance-guide-targets"
                >
                  <span class="muted">优先复核：</span>
                  <el-tag
                    v-for="target in card.targets"
                    :key="target.key"
                    effect="plain"
                    :type="target.tagType"
                    @click="
                      target.stepIndex
                        ? focusReviewEvidence(target.stepIndex)
                        : handlePostRunAction('evidence')
                    "
                  >
                    {{ target.label }}
                  </el-tag>
                </div>
              </div>
            </div>
            <div
              v-if="targetAcceptanceSummary.action"
              class="target-acceptance-actions"
            >
              <span>{{ targetAcceptanceSummary.nextAction }}</span>
              <el-button
                text
                type="primary"
                @click="handlePostRunAction(targetAcceptanceSummary.action)"
              >
                去处理
              </el-button>
            </div>
          </div>
          <div
            v-if="reportAttributionItems.length && showReportDetails"
            class="report-attribution-panel"
          >
            <div class="report-attribution-head">
              <div>
                <strong>问题归因速览</strong>
                <span>先判断该找谁处理，避免把环境/定位误判成 APP 缺陷</span>
              </div>
              <el-tag effect="plain" type="info"
                >{{ reportAttributionItems.length }} 类</el-tag
              >
            </div>
            <div class="report-attribution-grid">
              <div
                v-for="item in reportAttributionItems"
                :key="item.key"
                class="report-attribution-item"
              >
                <el-tag :type="item.tagType" effect="dark">{{
                  item.label
                }}</el-tag>
                <div>
                  <strong>{{ item.count }} 项 · {{ item.owner }}</strong>
                  <span>{{ item.nextAction }}</span>
                  <small>{{ item.examples.join("、") }}</small>
                </div>
              </div>
            </div>
          </div>
          <div class="report-review-board">
            <div class="report-review-header">
              <strong>优先处理清单</strong>
              <span>{{
                reportPriorityItems.length
                  ? "按影响排序，只处理这些关键项"
                  : "当前没有阻塞项，可以直接看证据或进入下一轮"
              }}</span>
            </div>
            <div v-if="reportPriorityItems.length" class="report-priority-list">
              <div
                v-for="item in visibleReportPriorityItems"
                :key="item.key"
                class="report-priority-item"
                :class="`priority-${item.level}`"
              >
                <el-tag :type="item.tagType" effect="dark">{{
                  item.badge
                }}</el-tag>
                <div class="priority-main">
                  <el-tag
                    v-if="item.attribution"
                    :type="item.attribution.tagType"
                    effect="plain"
                    size="small"
                  >
                    {{ item.attribution.label }}
                  </el-tag>
                  <el-tag
                    v-if="item.reviewLabel"
                    :type="item.reviewTagType"
                    effect="plain"
                    size="small"
                  >
                    {{ item.reviewLabel }}
                  </el-tag>
                  <strong>{{ item.title }}</strong>
                  <p class="priority-copy">{{ item.description }}</p>
                  <div
                    v-if="showReportDetails && item.detailRows?.length"
                    class="priority-evidence-grid priority-evidence-preview"
                  >
                    <div
                      v-for="row in item.detailRows.slice(0, 3)"
                      :key="`preview-${item.key}-${row.label}`"
                      class="priority-evidence-row"
                    >
                      <span>{{ row.label }}</span>
                      <strong>{{ row.value }}</strong>
                    </div>
                  </div>
                  <div
                    v-if="
                      isPriorityExpanded(item.key) &&
                      item.detailRows?.length > 3
                    "
                    class="priority-evidence-grid"
                  >
                    <div
                      v-for="row in item.detailRows.slice(3)"
                      :key="row.label"
                      class="priority-evidence-row"
                    >
                      <span>{{ row.label }}</span>
                      <strong>{{ row.value }}</strong>
                    </div>
                  </div>
                  <div v-if="showReportDetails" class="priority-help">
                    <span>建议：{{ item.suggestion }}</span>
                  </div>
                </div>
                <div class="priority-actions">
                  <el-button
                    v-if="item.detailRows?.length > 3"
                    text
                    type="info"
                    @click="togglePriorityEvidence(item.key)"
                  >
                    {{ isPriorityExpanded(item.key) ? "收起更多" : "展开更多" }}
                  </el-button>
                  <el-button
                    v-if="item.action"
                    text
                    type="primary"
                    @click="handlePriorityItemAction(item)"
                  >
                    {{ item.actionLabel }}
                  </el-button>
                  <el-dropdown
                    v-if="item.reviewType"
                    trigger="click"
                    @command="
                      (resolution) => reviewPriorityItem(item, resolution)
                    "
                  >
                    <el-button text type="success" size="small">
                      快速归档<el-icon class="el-icon--right"
                        ><ArrowDown
                      /></el-icon>
                    </el-button>
                    <template #dropdown>
                      <el-dropdown-menu>
                        <el-dropdown-item command="normal_behavior"
                          >正常业务行为</el-dropdown-item
                        >
                        <el-dropdown-item command="rule_exception"
                          >状态切换例外</el-dropdown-item
                        >
                        <el-dropdown-item command="needs_assertion"
                          >需补状态断言</el-dropdown-item
                        >
                        <el-dropdown-item command="valid_issue"
                          >有效问题</el-dropdown-item
                        >
                        <el-dropdown-item command="ignore"
                          >暂不处理</el-dropdown-item
                        >
                      </el-dropdown-menu>
                    </template>
                  </el-dropdown>
                </div>
              </div>
              <div
                v-if="hiddenPriorityItemCount > 0"
                class="priority-list-more"
              >
                <span
                  >还有 {{ hiddenPriorityItemCount }} 项低优先级内容已收起</span
                >
                <el-button
                  size="small"
                  text
                  type="primary"
                  @click="showAllPriorityItems = true"
                >
                  查看全部
                </el-button>
              </div>
              <div
                v-else-if="
                  showAllPriorityItems && reportPriorityItems.length > 3
                "
                class="priority-list-more"
              >
                <span>已显示全部 {{ reportPriorityItems.length }} 项</span>
                <el-button
                  size="small"
                  text
                  type="primary"
                  @click="showAllPriorityItems = false"
                >
                  收起列表
                </el-button>
              </div>
            </div>
            <div v-else class="report-clear-state">
              <strong>本轮暂无必须复核项</strong>
              <span
                >如果这轮目标覆盖符合预期，可以查看页面证据做抽查，或生成 AI
                分析准备下一轮探索。</span
              >
            </div>
          </div>
        </el-card>

        <div class="report-tabbar">
          <el-radio-group v-model="reportActiveTab">
            <el-radio-button label="overview">处理台</el-radio-button>
            <el-radio-button label="steps">步骤轨迹</el-radio-button>
            <el-radio-button label="evidence">页面证据</el-radio-button>
            <el-radio-button label="risk">风险</el-radio-button>
            <el-radio-button label="ai">AI 分析</el-radio-button>
            <el-radio-button label="logs">日志</el-radio-button>
          </el-radio-group>
          <span class="tabbar-tip">{{ reportTabTip }}</span>
        </div>

        <el-card
          v-if="targetInspectionResults.length"
          v-show="reportActiveTab === 'overview' && showReportDetails"
          shadow="never"
          class="report-card target-inspection-card"
        >
          <template #header>
            <div class="section-title">
              <span>目标巡检矩阵</span>
              <el-tag
                :type="
                  targetInspectionSummary.issueCount ? 'warning' : 'success'
                "
                effect="plain"
              >
                {{ targetInspectionSummary.covered }}/{{
                  targetInspectionSummary.total
                }}
                已覆盖
              </el-tag>
            </div>
          </template>
          <div class="target-inspection-summary">
            <div class="target-inspection-metric">
              <span>覆盖率</span>
              <strong>{{ targetInspectionSummary.coverageRate }}%</strong>
            </div>
            <div class="target-inspection-metric">
              <span>有效命中</span>
              <strong>{{ targetInspectionSummary.effective }}</strong>
            </div>
            <div class="target-inspection-metric">
              <span>待确认</span>
              <strong>{{ targetInspectionSummary.unconfirmed }}</strong>
            </div>
            <div class="target-inspection-metric">
              <span>未找到</span>
              <strong>{{ targetInspectionSummary.notFound }}</strong>
            </div>
            <div class="target-inspection-metric">
              <span>已复核归档</span>
              <strong>{{ targetInspectionSummary.suppressed }}</strong>
            </div>
          </div>
          <div class="target-inspection-list">
            <div
              v-for="item in targetInspectionResults"
              :key="`${item.id || item.target_name}-${item.status}`"
              class="target-inspection-item"
              :class="`target-${item.status || 'unknown'}`"
            >
              <div class="target-inspection-main">
                <strong>{{ item.target_name || "-" }}</strong>
                <div class="target-inspection-actions">
                  <span>{{ targetInspectionStatusText(item.status) }}</span>
                  <el-button
                    v-if="item.step_index"
                    text
                    type="primary"
                    size="small"
                    @click="focusReviewEvidence(item.step_index)"
                  >
                    看截图定位
                  </el-button>
                  <el-tag
                    v-if="item.effective_review?.resolution"
                    :type="
                      targetReviewTagType(item.effective_review.resolution)
                    "
                    effect="plain"
                  >
                    {{ targetReviewText(item.effective_review.resolution) }}
                  </el-tag>
                  <el-dropdown
                    trigger="click"
                    @command="
                      (resolution) => reviewTargetResult(item, resolution)
                    "
                  >
                    <el-button
                      text
                      type="primary"
                      size="small"
                      :loading="
                        reviewingTargetKey.startsWith(
                          `${item.id || item.target_name}-`,
                        )
                      "
                    >
                      复核
                    </el-button>
                    <template #dropdown>
                      <el-dropdown-menu>
                        <el-dropdown-item command="normal_behavior"
                          >归档为正常行为</el-dropdown-item
                        >
                        <el-dropdown-item command="valid_issue"
                          >确认有效问题</el-dropdown-item
                        >
                        <el-dropdown-item command="element_needs_update"
                          >元素需维护</el-dropdown-item
                        >
                        <el-dropdown-item command="wrong_start_page"
                          >起始页不对</el-dropdown-item
                        >
                        <el-dropdown-item command="rule_exception"
                          >规则例外</el-dropdown-item
                        >
                        <el-dropdown-item command="target_should_remove"
                          >建议移出目标</el-dropdown-item
                        >
                      </el-dropdown-menu>
                    </template>
                  </el-dropdown>
                </div>
              </div>
              <div class="target-inspection-meta">
                <el-tag
                  :type="targetInspectionStatusTag(item.status)"
                  effect="plain"
                >
                  {{ item.changed ? "有变化" : "无明显变化" }}
                </el-tag>
                <span v-if="item.match_reason"
                  >命中依据：{{ item.match_reason }}</span
                >
                <span v-if="item.state_change_label"
                  >状态变化：{{ item.state_change_label }}</span
                >
                <span v-else-if="item.state_diagnostics_label"
                  >变化依据：{{ item.state_diagnostics_label }}</span
                >
                <span v-if="item.recovery_status"
                  >恢复：{{
                    targetRecoveryStatusText(item.recovery_status)
                  }}</span
                >
                <span v-if="item.bounds">bounds {{ item.bounds }}</span>
                <span v-if="item.x !== null && item.y !== null"
                  >({{ item.x }}, {{ item.y }})</span
                >
              </div>
              <p v-if="item.error_message">{{ item.error_message }}</p>
            </div>
          </div>
        </el-card>

        <el-card
          v-if="targetStabilityRows.length"
          v-show="reportActiveTab === 'overview' && showReportDetails"
          shadow="never"
          class="report-card target-stability-card"
        >
          <template #header>
            <div class="section-title">
              <span>目标稳定性</span>
              <el-tag
                :type="targetStabilitySummary.unstable ? 'warning' : 'success'"
                effect="plain"
              >
                {{ targetStabilitySummary.stable }}/{{
                  targetStabilitySummary.total
                }}
                稳定
              </el-tag>
            </div>
          </template>
          <div class="target-stability-summary">
            <div>
              <strong>{{ targetStabilitySummary.consistencyRate }}%</strong>
              <span>最近 {{ targetStabilitySummary.runCount }} 次一致性</span>
            </div>
            <div v-if="targetBatchDiffItems.length" class="target-batch-diff">
              <el-tag type="warning" effect="plain">本次较上次有变化</el-tag>
              <span
                v-for="item in targetBatchDiffItems.slice(0, 5)"
                :key="item.target"
              >
                {{ item.target }}：{{
                  targetInspectionStatusText(item.previous)
                }}
                -> {{ targetInspectionStatusText(item.current) }}
              </span>
            </div>
            <div v-else class="target-batch-diff">
              <el-tag type="success" effect="plain">本次与上次一致</el-tag>
            </div>
          </div>
          <div class="target-stability-table">
            <div class="target-stability-row header">
              <span>目标</span>
              <span>最近状态</span>
              <span>结论</span>
            </div>
            <div
              v-for="row in targetStabilityRows"
              :key="row.target"
              class="target-stability-row"
              :class="{ unstable: !row.stable }"
            >
              <strong>{{ row.target }}</strong>
              <div class="target-stability-runs">
                <el-tag
                  v-for="item in row.runs"
                  :key="`${row.target}-${item.run_id}`"
                  :type="targetInspectionStatusTag(item.status)"
                  effect="plain"
                >
                  #{{ item.run_id }}
                  {{ targetInspectionStatusText(item.status) }}
                </el-tag>
              </div>
              <span>{{ row.stable ? "结果一致" : "需复核" }}</span>
            </div>
          </div>
        </el-card>

        <el-card
          v-if="explorationRunHistory.length"
          v-show="reportActiveTab === 'overview' && showReportDetails"
          shadow="never"
          class="report-card run-history-card"
        >
          <template #header>
            <div class="section-title">
              <span>执行批次历史</span>
              <el-tag type="info" effect="plain"
                >最近 {{ explorationRunHistory.length }} 次</el-tag
              >
            </div>
          </template>
          <div class="run-history-list">
            <div
              v-for="(run, index) in explorationRunHistory"
              :key="run.id || index"
              class="run-history-item"
              :class="{ latest: index === 0 }"
            >
              <div class="run-history-main">
                <strong>#{{ run.id || "-" }}</strong>
                <el-tag :type="statusTag(run.status)" effect="plain">
                  {{ statusText(run.status) }}
                </el-tag>
                <el-tag
                  :type="
                    run.result === 'passed'
                      ? 'success'
                      : run.result === 'failed'
                        ? 'danger'
                        : 'warning'
                  "
                  effect="plain"
                >
                  {{ run.result || "无结果" }}
                </el-tag>
              </div>
              <div class="run-history-meta">
                <span>{{ run.strategy || currentTask.strategy || "-" }}</span>
                <span>{{ run.total_steps || 0 }} 步</span>
                <span>{{ run.issue_count || 0 }} 问题</span>
                <span
                  >覆盖率 {{ run.summary?.target_coverage_rate ?? "-" }}%</span
                >
                <span>{{ formatDuration(run.duration) }}</span>
                <span>{{ formatTime(run.created_at) }}</span>
              </div>
            </div>
          </div>
        </el-card>

        <el-card
          v-if="iteration.has_source"
          v-show="reportActiveTab === 'overview' && showReportDetails"
          shadow="never"
          class="report-card iteration-card"
        >
          <template #header>
            <div class="section-title">
              <span>探索迭代关系</span>
              <el-tag type="success" effect="plain">{{
                sourceTypeText(iteration.source_type)
              }}</el-tag>
            </div>
          </template>
          <div class="iteration-source">
            <span class="muted">来源任务：</span>
            <el-button
              link
              type="primary"
              @click="openSourceReport(iteration.source_task?.id)"
            >
              #{{ iteration.source_task?.id }}
              {{ iteration.source_task?.name || "-" }}
            </el-button>
          </div>
          <div
            v-if="iterationChainSummary.total_attempts"
            class="iteration-chain-summary"
          >
            <el-tag type="primary" effect="plain">
              第
              {{ iterationChainSummary.current_round || iterationChain.length }}
              轮
            </el-tag>
            <el-tag type="success" effect="plain">
              有效 {{ iterationChainSummary.effective_attempts || 0 }} 轮
            </el-tag>
            <el-tag
              :type="
                iterationChainSummary.ineffective_attempts ? 'warning' : 'info'
              "
              effect="plain"
            >
              跑空 {{ iterationChainSummary.ineffective_attempts || 0 }} 轮
            </el-tag>
            <el-tag
              v-if="iterationChainSummary.pending_attempts"
              type="info"
              effect="plain"
            >
              待执行 {{ iterationChainSummary.pending_attempts }} 轮
            </el-tag>
            <el-tag
              v-if="iterationChainSummary.error_attempts"
              type="danger"
              effect="plain"
            >
              异常 {{ iterationChainSummary.error_attempts }} 轮
            </el-tag>
            <el-tag
              v-if="iterationChainSummary.issue_attempts"
              type="danger"
              effect="plain"
            >
              发现问题 {{ iterationChainSummary.issue_attempts }} 轮
            </el-tag>
            <span
              v-if="iterationChainSummary.latest_effective_task"
              class="muted"
            >
              最新有效：#{{ iterationChainSummary.latest_effective_task.id }}
              {{ iterationChainSummary.latest_effective_task.name }}
            </span>
          </div>
          <div v-if="iterationChain.length > 1" class="iteration-chain">
            <div class="chain-title">探索链路时间线</div>
            <div
              v-for="node in iterationChain"
              :key="node.id"
              class="chain-node"
              :class="{ current: node.is_current }"
            >
              <span class="chain-node-index">{{ node.round }}</span>
              <div class="chain-node-main">
                <strong>#{{ node.id }} {{ node.name || "-" }}</strong>
                <small>
                  {{ sourceTypeText(node.source_type) }} ·
                  {{ statusText(node.status) }} ·
                  {{ formatTime(node.created_at) }}
                </small>
              </div>
              <div class="chain-node-metrics">
                <el-tag :type="iterationChainNodeType(node)" effect="plain">
                  {{ iterationChainNodeLabel(node) }}
                </el-tag>
                <span>{{ node.metrics?.total_steps || 0 }} 步</span>
                <span>{{ node.metrics?.explored_pages || 0 }} 页</span>
                <span>{{ node.metrics?.issue_count || 0 }} 问题</span>
              </div>
            </div>
          </div>
          <div
            v-if="iteration.source_summary?.targets?.length"
            class="keyword-row"
          >
            <span class="muted">AI 建议目标：</span>
            <el-tag
              v-for="item in iteration.source_summary.targets"
              :key="item"
              type="info"
              effect="plain"
            >
              {{ item }}
            </el-tag>
          </div>
          <div
            v-if="iterationAcceptedActions.length"
            class="iteration-action-audit"
          >
            <div class="audit-header">
              <strong>本轮采纳动作</strong>
              <span class="muted">
                采纳 {{ iterationAcceptedActions.length }} 条，未采纳
                {{ iterationRejectedActionCount }} 条
              </span>
            </div>
            <div
              v-for="(item, index) in iterationAcceptedActions"
              :key="`${item.action_type}-${item.target}-${index}`"
              class="audit-action-item"
            >
              <span>{{ actionProposalText(item) }}</span>
              <el-tag :type="actionRiskTagType(item.risk)" effect="plain">
                {{ actionRiskText(item.risk) }}
              </el-tag>
              <el-tag type="info" effect="plain">
                {{ actionLayerText(classifyAIActionProposal(item)) }}
              </el-tag>
            </div>
          </div>
          <el-alert
            v-if="iterationEffectAssessment.title"
            :type="iterationEffectAssessment.type"
            :title="iterationEffectAssessment.title"
            :description="iterationEffectAssessment.description"
            show-icon
            class="iteration-effect-alert"
          />
          <div
            v-if="iterationNextSuggestion.title"
            class="iteration-next-suggestion"
          >
            <div>
              <strong>{{ iterationNextSuggestion.title }}</strong>
              <p>{{ iterationNextSuggestion.description }}</p>
            </div>
            <el-tag :type="iterationNextSuggestion.type" effect="dark">
              {{ iterationNextSuggestion.action }}
            </el-tag>
          </div>
          <div v-if="canCreateAdjustedIterationDraft" class="iteration-remedy">
            <el-button
              plain
              type="warning"
              @click="createAdjustedIterationDraft"
            >
              生成修正探索草稿
            </el-button>
            <span class="muted"
              >会移除本轮疑似无效的起始动作，保留探索目标和入口关键词。</span
            >
          </div>
          <div class="iteration-grid">
            <div
              v-for="item in iterationMetricCards"
              :key="item.key"
              class="iteration-metric"
            >
              <span>{{ item.label }}</span>
              <strong>{{ item.current }}</strong>
              <small :class="item.diffClass">{{ item.diffText }}</small>
            </div>
          </div>
        </el-card>

        <div
          v-if="conversionSummary.total_steps"
          v-show="reportActiveTab === 'overview' && showReportDetails"
          class="conversion-summary"
        >
          <div class="conversion-main">
            <strong>转用例质量预估</strong>
            <span
              >高可信 {{ conversionSummary.high_confidence_steps || 0 }} /
              {{ conversionSummary.total_steps || 0 }} 步</span
            >
            <el-tag
              :type="
                conversionSummary.needs_review_count ? 'warning' : 'success'
              "
              effect="plain"
              :class="{ 'clickable-tag': conversionSummary.needs_review_count }"
              @click="
                conversionSummary.needs_review_count &&
                showConversionReview('all')
              "
            >
              {{
                conversionSummary.needs_review_count
                  ? `${conversionSummary.needs_review_count} 步需复核`
                  : "可直接沉淀"
              }}
            </el-tag>
          </div>
          <div class="conversion-tags">
            <el-tag effect="plain"
              >可用率 {{ conversionSummary.ready_rate || 0 }}%</el-tag
            >
            <el-tag
              v-if="conversionSummary.coordinate_only_count"
              type="warning"
              effect="plain"
              class="clickable-tag"
              @click="showConversionReview('coordinate')"
            >
              坐标兜底 {{ conversionSummary.coordinate_only_count }}
            </el-tag>
            <el-tag
              v-if="conversionSummary.no_change_tap_count"
              type="info"
              effect="plain"
              class="clickable-tag"
              @click="showConversionReview('no_change')"
            >
              点击无变化 {{ conversionSummary.no_change_tap_count }}
            </el-tag>
            <el-tag
              v-if="conversionSummary.issue_step_count"
              type="danger"
              effect="plain"
              class="clickable-tag"
              @click="showConversionReview('issue')"
            >
              问题步骤 {{ conversionSummary.issue_step_count }}
            </el-tag>
            <el-tag
              v-if="conversionSummary.forbidden_risk_step_count"
              type="danger"
              effect="plain"
              class="clickable-tag"
              @click="showConversionReview('risk')"
            >
              已过滤风险步骤 {{ conversionSummary.forbidden_risk_step_count }}
            </el-tag>
          </div>
          <div
            v-if="conversionNeedsReview.length"
            class="conversion-review-toggle"
          >
            <el-button text type="warning" @click="toggleConversionReview">
              {{
                expandedConversionReview ? "收起需复核步骤" : "查看需复核步骤"
              }}
            </el-button>
            <span
              >点击上方标签可按原因筛选，建议转成用例前优先确认这些步骤。</span
            >
          </div>
          <div
            v-if="expandedConversionReview && conversionNeedsReview.length"
            class="conversion-review-list"
          >
            <div class="conversion-review-filter">
              <el-tag
                v-for="option in conversionReviewFilterOptions"
                :key="option.value"
                :type="
                  activeConversionReviewFilter === option.value
                    ? option.type
                    : 'info'
                "
                :effect="
                  activeConversionReviewFilter === option.value
                    ? 'dark'
                    : 'plain'
                "
                class="clickable-tag"
                @click="showConversionReview(option.value)"
              >
                {{ option.label }} {{ option.count }}
              </el-tag>
            </div>
            <div
              v-for="item in filteredConversionNeedsReview"
              :key="`${item.step_index}-${item.reason}`"
              class="conversion-review-item"
            >
              <div class="conversion-review-main">
                <strong>第 {{ item.step_index || "-" }} 步</strong>
                <span>{{ conversionReviewTitle(item) }}</span>
                <el-tag :type="stabilityTagType(item.stability)" effect="plain">
                  {{ stabilityText(item.stability) }}
                </el-tag>
                <el-button
                  text
                  type="primary"
                  size="small"
                  @click="focusReviewEvidence(item.step_index)"
                >
                  看截图定位
                </el-button>
              </div>
              <div class="conversion-review-reason">
                {{ conversionReviewPlainReason(item) }}
              </div>
              <div class="conversion-review-next">
                {{ conversionReviewNextAction(item) }}
              </div>
            </div>
            <el-empty
              v-if="!filteredConversionNeedsReview.length"
              description="当前筛选下暂无需复核步骤"
            />
          </div>
        </div>

        <el-alert
          v-if="currentTask.error_message"
          v-show="reportActiveTab === 'overview'"
          type="error"
          :title="currentTask.error_message"
          show-icon
          class="report-alert"
        />

        <el-card
          v-show="reportActiveTab === 'logs'"
          shadow="never"
          class="report-card attachment-section"
        >
          <template #header>
            <div class="section-title">
              <span>日志与排查附件</span>
              <el-tag
                :type="currentTask.logcat?.available ? 'success' : 'info'"
                effect="plain"
              >
                {{
                  currentTask.logcat?.available
                    ? "已采集 logcat"
                    : "暂无 logcat"
                }}
              </el-tag>
            </div>
          </template>
          <div class="attachment-card">
            <div>
              <strong>Android logcat</strong>
              <p>
                用于排查探索过程中的崩溃、ANR、闪退、白屏、系统弹窗等问题，提缺陷时可以直接发给开发。
              </p>
              <span class="attachment-meta">
                {{
                  currentTask.logcat?.available
                    ? `包含 ${currentTask.logcat.file_count || 0} 个日志文件`
                    : "当前探索任务没有采集到日志文件，建议重新执行一次探索任务"
                }}
              </span>
            </div>
            <el-button
              type="primary"
              plain
              :disabled="!currentTask.logcat?.available"
              @click="downloadExplorationLogcat"
            >
              导出日志 ZIP
            </el-button>
          </div>
        </el-card>

        <el-card
          id="exploration-issue-review-card"
          v-show="reportActiveTab === 'overview' && showReportDetails"
          shadow="never"
          class="report-card compact-card"
        >
          <template #header>
            <div class="section-title">
              <span>问题复核</span>
              <el-tag
                :type="issueList.length ? 'warning' : 'success'"
                effect="plain"
              >
                {{
                  issueList.length
                    ? `${pendingIssueCount} 个待处理 / ${issueList.length} 个总计`
                    : "暂无疑似问题"
                }}
              </el-tag>
            </div>
          </template>
          <el-empty
            v-if="!issueList.length"
            description="本次探索暂未发现疑似问题"
          />
          <el-timeline v-else>
            <el-timeline-item
              v-for="issue in issueList"
              :key="`${issue.step_index}-${issue.issue_type}`"
              type="warning"
            >
              <div
                class="issue-review-item"
                :class="{ archived: isIssueArchived(issue) }"
              >
                <div class="issue-line">
                  <span
                    >第 {{ issue.step_index }} 步：{{
                      issue.issue_message || issueTypeText(issue.issue_type)
                    }}</span
                  >
                  <el-tag
                    v-if="issueReviewResolution(issue)"
                    :type="issueReviewTagType(issue)"
                    effect="plain"
                    size="small"
                  >
                    {{ issueReviewLabel(issue) }}
                  </el-tag>
                </div>
                <div class="issue-evidence-grid">
                  <div
                    v-for="row in issueQuickEvidenceRows(issue)"
                    :key="`${issue.step_index}-${row.label}`"
                    class="issue-evidence-row"
                  >
                    <span>{{ row.label }}</span>
                    <strong>{{ row.value }}</strong>
                  </div>
                </div>
                <div class="issue-actions">
                  <el-button
                    v-if="issue.step_index"
                    text
                    type="primary"
                    size="small"
                    @click="focusReviewEvidence(issue.step_index)"
                  >
                    看截图定位
                  </el-button>
                  <el-button
                    text
                    type="danger"
                    size="small"
                    @click="copyDefectDraft(issue)"
                  >
                    复制该问题证据
                  </el-button>
                  <el-button
                    text
                    type="primary"
                    size="small"
                    :loading="
                      reviewingIssueKey === `${issue.step_index}-valid_issue`
                    "
                    @click="reviewIssue(issue, 'valid_issue')"
                  >
                    确认为有效问题
                  </el-button>
                  <el-dropdown
                    trigger="click"
                    @command="(resolution) => reviewIssue(issue, resolution)"
                  >
                    <el-button
                      text
                      type="success"
                      size="small"
                      :loading="
                        reviewingIssueKey.startsWith(`${issue.step_index}-`) &&
                        reviewingIssueKey !== `${issue.step_index}-valid_issue`
                      "
                    >
                      归档为<el-icon class="el-icon--right"
                        ><ArrowDown
                      /></el-icon>
                    </el-button>
                    <template #dropdown>
                      <el-dropdown-menu>
                        <el-dropdown-item command="normal_behavior"
                          >正常业务行为</el-dropdown-item
                        >
                        <el-dropdown-item command="rule_exception"
                          >状态切换例外</el-dropdown-item
                        >
                        <el-dropdown-item command="needs_assertion"
                          >需补状态断言</el-dropdown-item
                        >
                        <el-dropdown-item command="ignore"
                          >暂不处理</el-dropdown-item
                        >
                      </el-dropdown-menu>
                    </template>
                  </el-dropdown>
                </div>
              </div>
            </el-timeline-item>
          </el-timeline>
        </el-card>

        <el-card
          v-if="aiAnalysisInProgress"
          v-show="reportActiveTab === 'ai'"
          shadow="never"
          class="report-card ai-progress-card"
        >
          <div class="ai-progress-header">
            <div>
              <strong>AI 正在分析本次探索报告</strong>
              <p>{{ aiAnalysisProgressMessage }}</p>
            </div>
            <el-tag type="warning" effect="plain">{{
              aiAnalysisProgressStage
            }}</el-tag>
          </div>
          <el-steps
            :active="aiAnalysisStepActive"
            finish-status="success"
            process-status="process"
            simple
          >
            <el-step title="提交任务" />
            <el-step title="整理报告" />
            <el-step title="请求模型" />
            <el-step title="解析结果" />
          </el-steps>
          <p class="muted">
            这是一个耗时操作，你可以先查看步骤轨迹、页面证据或日志；分析完成后页面会自动刷新。
          </p>
        </el-card>

        <el-card
          v-if="aiAnalysisFailed"
          v-show="reportActiveTab === 'ai'"
          shadow="never"
          class="report-card ai-progress-card failed"
        >
          <el-alert
            type="error"
            show-icon
            title="AI 分析失败"
            :description="aiAnalysisErrorMessage"
          />
          <el-button
            class="ai-retry-button"
            type="success"
            plain
            :loading="aiAnalyzing"
            @click="runAIAnalysis"
          >
            重新分析
          </el-button>
        </el-card>

        <el-card
          v-if="aiAnalysis.status && !aiAnalysisInProgress"
          v-show="reportActiveTab === 'ai'"
          shadow="never"
          class="report-card ai-analysis-card"
        >
          <template #header>
            <div class="section-title">
              <span>AI 分析建议</span>
              <el-tag
                :type="aiRiskTagType(aiAnalysis.risk_level)"
                effect="plain"
              >
                {{ aiRiskText(aiAnalysis.risk_level) }}
              </el-tag>
            </div>
          </template>
          <el-alert
            :type="aiRiskTagType(aiAnalysis.risk_level)"
            :title="aiAnalysis.conclusion || 'AI 暂无明确结论'"
            show-icon
            class="report-alert"
          />
          <div v-if="aiInspectionPlanVisible" class="ai-plan-board">
            <div class="ai-plan-head">
              <div>
                <span class="decision-kicker">AI L1 受控巡检计划</span>
                <strong>{{
                  aiInspectionPlan.summary || "AI 已生成下一轮目标巡检计划"
                }}</strong>
                <p>
                  AI
                  只生成计划，不会直接控制手机；保存前请确认目标、入口和风险项。
                </p>
              </div>
              <el-tag type="success" effect="dark">target_inspection</el-tag>
            </div>
            <div class="ai-plan-metrics">
              <div>
                <span>推荐目标</span>
                <strong
                  >{{ selectedAIPlanTargets.length }}/{{
                    aiPlanTargets.length
                  }}</strong
                >
              </div>
              <div>
                <span>起始导航</span>
                <strong>{{ aiPlanStartActions.length }}</strong>
              </div>
              <div>
                <span>风险控制</span>
                <strong>{{ aiPlanRiskControls.length }}</strong>
              </div>
              <div>
                <span>语义建议</span>
                <strong>{{ aiSemanticSuggestions.length }}</strong>
              </div>
            </div>
            <div v-if="aiPlanCoverageGaps.length" class="ai-plan-section">
              <strong>覆盖缺口</strong>
              <div class="keyword-row">
                <el-tag
                  v-for="item in aiPlanCoverageGaps"
                  :key="item"
                  type="warning"
                  effect="plain"
                >
                  {{ item }}
                </el-tag>
              </div>
            </div>
            <div v-if="aiPlanTargets.length" class="ai-plan-section">
              <div class="ai-plan-section-head">
                <strong>下一轮目标</strong>
                <div>
                  <el-button
                    size="small"
                    text
                    type="primary"
                    @click="acceptRecommendedAIPlanTargets"
                    >采纳推荐</el-button
                  >
                  <el-button size="small" text @click="clearAIPlanTargets"
                    >清空</el-button
                  >
                </div>
              </div>
              <div class="ai-plan-target-list">
                <div
                  v-for="(item, index) in aiPlanTargets"
                  :key="aiPlanTargetKey(item, index)"
                  class="ai-plan-target-item"
                  :class="{
                    selected: isAIPlanTargetSelected(item, index),
                    disabled: item.risk === 'high',
                  }"
                >
                  <el-checkbox
                    :model-value="isAIPlanTargetSelected(item, index)"
                    :disabled="item.risk === 'high'"
                    @change="
                      (checked) => toggleAIPlanTarget(item, index, checked)
                    "
                  />
                  <div>
                    <strong>{{ item.target_name }}</strong>
                    <p>{{ item.reason || "建议纳入下一轮目标巡检。" }}</p>
                    <div class="proposal-tags">
                      <el-tag
                        :type="planPriorityTagType(item.priority)"
                        effect="plain"
                        >{{ item.priority || "P1" }}</el-tag
                      >
                      <el-tag type="info" effect="plain">{{
                        item.semantic_role || "控件"
                      }}</el-tag>
                      <el-tag
                        v-if="item.page_name"
                        type="info"
                        effect="plain"
                        >{{ item.page_name }}</el-tag
                      >
                      <el-tag
                        :type="actionRiskTagType(item.risk)"
                        effect="plain"
                        >{{ actionRiskText(item.risk) }}</el-tag
                      >
                    </div>
                  </div>
                </div>
              </div>
            </div>
            <div
              v-if="aiPlanRiskControls.length || aiSemanticSuggestions.length"
              class="ai-plan-two-col"
            >
              <div
                v-if="aiPlanRiskControls.length"
                class="ai-plan-section compact"
              >
                <strong>风险控制</strong>
                <div
                  v-for="item in aiPlanRiskControls"
                  :key="item"
                  class="ai-analysis-item"
                >
                  {{ item }}
                </div>
              </div>
              <div
                v-if="aiSemanticSuggestions.length"
                class="ai-plan-section compact"
              >
                <strong>语义库建议</strong>
                <div
                  v-for="item in aiSemanticSuggestions"
                  :key="`${item.page_name}-${item.target_name}`"
                  class="ai-analysis-item"
                >
                  {{ item.page_name ? `${item.page_name} / ` : ""
                  }}{{ item.target_name }}：{{ item.suggestion }}
                </div>
              </div>
            </div>
          </div>
          <div class="ai-analysis-grid">
            <div class="ai-analysis-block">
              <strong>疑似缺陷</strong>
              <el-empty
                v-if="!(aiAnalysis.defect_candidates || []).length"
                description="暂无"
              />
              <div
                v-for="(item, index) in aiAnalysis.defect_candidates || []"
                :key="aiItemKey(item, index, 'defect')"
                class="ai-analysis-item traceable"
              >
                <div class="ai-item-main">
                  <strong>{{ aiItemTitle(item) }}</strong>
                  <p>{{ aiItemReason(item) }}</p>
                  <div v-if="aiItemEvidence(item)" class="ai-item-evidence">
                    <el-tag size="small" effect="plain"
                      >第 {{ aiItemStepIndex(item) }} 步</el-tag
                    >
                    <span>{{ aiItemEvidenceSummary(item) }}</span>
                  </div>
                </div>
                <el-button
                  v-if="aiItemStepIndex(item)"
                  size="small"
                  text
                  type="primary"
                  @click="focusAIEvidence(item)"
                >
                  看截图定位
                </el-button>
              </div>
            </div>
            <div class="ai-analysis-block">
              <strong>可能误报</strong>
              <el-empty
                v-if="!(aiAnalysis.false_positive_candidates || []).length"
                description="暂无"
              />
              <div
                v-for="(item, index) in aiAnalysis.false_positive_candidates ||
                []"
                :key="aiItemKey(item, index, 'false-positive')"
                class="ai-analysis-item traceable"
              >
                <div class="ai-item-main">
                  <strong>{{ aiItemTitle(item) }}</strong>
                  <p>{{ aiItemReason(item) }}</p>
                  <div v-if="aiItemEvidence(item)" class="ai-item-evidence">
                    <el-tag size="small" effect="plain"
                      >第 {{ aiItemStepIndex(item) }} 步</el-tag
                    >
                    <span>{{ aiItemEvidenceSummary(item) }}</span>
                  </div>
                </div>
                <el-button
                  v-if="aiItemStepIndex(item)"
                  size="small"
                  text
                  type="primary"
                  @click="focusAIEvidence(item)"
                >
                  看截图定位
                </el-button>
              </div>
            </div>
            <div class="ai-analysis-block">
              <strong>可能原因</strong>
              <div
                v-for="item in aiAnalysis.root_cause_hypotheses || []"
                :key="item"
                class="ai-analysis-item"
              >
                {{ displayAIItem(item) }}
              </div>
            </div>
            <div class="ai-analysis-block">
              <strong>下一轮探索目标</strong>
              <div
                v-for="item in aiAnalysis.next_exploration_targets || []"
                :key="item"
                class="ai-analysis-item"
              >
                {{ displayAIItem(item) }}
              </div>
            </div>
            <div
              v-if="
                aiNextRoundDraft.targets?.length ||
                aiNextRoundDraft.start_actions?.length
              "
              class="ai-analysis-block"
            >
              <strong>下一轮草稿预览</strong>
              <div class="ai-analysis-item">
                <span>入口关键词：</span>
                {{
                  (aiNextRoundDraft.entry_keywords || []).join("、") || "暂无"
                }}
              </div>
              <div class="ai-analysis-item">
                <span>预填导航：</span>
                {{
                  (aiNextRoundDraft.start_actions || [])
                    .map((item) => item.value || item.target)
                    .filter(Boolean)
                    .join("、") || "暂无"
                }}
              </div>
              <div class="ai-analysis-item">
                <span>探索策略：</span>
                {{ aiNextRoundDraft.strategy || "target_inspection" }}，{{
                  aiNextRoundDraft.max_steps || 30
                }}
                步
              </div>
            </div>
            <div class="ai-analysis-block">
              <strong>人工复核点</strong>
              <div
                v-for="(item, index) in aiAnalysis.manual_review_points || []"
                :key="aiItemKey(item, index, 'review')"
                class="ai-analysis-item traceable"
              >
                <div class="ai-item-main">
                  <strong>{{ aiItemTitle(item) }}</strong>
                  <p>{{ aiItemReason(item) }}</p>
                  <div v-if="aiItemEvidence(item)" class="ai-item-evidence">
                    <el-tag size="small" effect="plain"
                      >第 {{ aiItemStepIndex(item) }} 步</el-tag
                    >
                    <span>{{ aiItemEvidenceSummary(item) }}</span>
                  </div>
                </div>
                <el-button
                  v-if="aiItemStepIndex(item)"
                  size="small"
                  text
                  type="primary"
                  @click="focusAIEvidence(item)"
                >
                  看截图定位
                </el-button>
              </div>
            </div>
          </div>
          <div v-if="aiActionProposals.length" class="ai-action-proposals">
            <div class="proposal-header">
              <div>
                <strong>AI 建议动作</strong>
                <span class="muted">
                  只用于生成草稿，不会自动执行；已采纳
                  {{ selectedAIActionProposals.length }} 条，其中可预填起始导航
                  {{ aiActionsToStartActions().length }} 条。
                </span>
              </div>
              <div class="proposal-header-actions">
                <el-button
                  size="small"
                  text
                  type="primary"
                  @click="acceptRecommendedAIActionProposals"
                >
                  采纳推荐
                </el-button>
                <el-button size="small" text @click="clearAIActionProposals">
                  清空
                </el-button>
              </div>
            </div>
            <div
              v-for="(item, index) in aiActionProposals"
              :key="`${item.action_type}-${item.target}-${index}`"
              class="ai-action-item"
              :class="{
                selected: isAIActionProposalSelected(item, index),
                disabled: item.risk === 'high',
              }"
            >
              <el-checkbox
                :model-value="isAIActionProposalSelected(item, index)"
                :disabled="item.risk === 'high'"
                @change="
                  (checked) => toggleAIActionProposal(item, index, checked)
                "
              />
              <div>
                <strong>{{ actionProposalText(item) }}</strong>
                <p>{{ item.reason || "建议人工确认后再采纳到下一轮探索。" }}</p>
              </div>
              <div class="proposal-tags">
                <el-tag :type="actionRiskTagType(item.risk)" effect="plain">{{
                  actionRiskText(item.risk)
                }}</el-tag>
                <el-tag effect="plain" type="info">{{
                  actionLayerText(classifyAIActionProposal(item))
                }}</el-tag>
                <el-tag
                  v-if="item.layer_reason"
                  effect="plain"
                  type="warning"
                  >{{ item.layer_reason }}</el-tag
                >
                <el-tag v-if="item.confidence" effect="plain"
                  >可信度 {{ Math.round(item.confidence * 100) }}%</el-tag
                >
              </div>
            </div>
          </div>
          <div class="ai-analysis-actions">
            <el-button
              plain
              type="success"
              :disabled="!aiNextRoundReadiness.ready"
              @click="createTaskDraftFromAIAnalysis"
            >
              生成下一轮探索草稿
            </el-button>
            <span class="muted">只预填新任务，不会自动执行。</span>
          </div>
          <p class="muted">
            模型：{{ aiAnalysis.model_name || "-" }}；角色：{{
              aiAnalysis.model_role || "-"
            }}； 提示词：{{ aiPromptDisplayName }}
          </p>
          <div v-if="aiAnalysis.audit" class="ai-audit-panel">
            <el-button
              text
              type="primary"
              @click="expandedAIAudit = !expandedAIAudit"
            >
              {{ expandedAIAudit ? "收起 AI 分析依据" : "查看 AI 分析依据" }}
            </el-button>
            <div v-if="expandedAIAudit" class="ai-audit-content">
              <div class="ai-audit-grid">
                <div>
                  <span>分析时间</span>
                  <strong>{{
                    formatTime(aiAnalysis.audit.analyzed_at)
                  }}</strong>
                </div>
                <div>
                  <span>送入步骤</span>
                  <strong
                    >{{
                      aiAnalysis.audit.input_summary?.step_count_sent || 0
                    }}
                    步</strong
                  >
                </div>
                <div>
                  <span>探索轮次</span>
                  <strong
                    >第
                    {{ aiAnalysis.audit.iteration_summary?.current_round || 1 }}
                    轮</strong
                  >
                </div>
                <div>
                  <span>问题依据</span>
                  <strong
                    >{{
                      aiAnalysis.audit.input_summary?.rule_issue_count_sent || 0
                    }}
                    条</strong
                  >
                </div>
                <div>
                  <span>可追溯项</span>
                  <strong
                    >{{
                      aiAnalysis.evidence_summary?.traceable_item_count || 0
                    }}
                    条</strong
                  >
                </div>
              </div>
              <div class="ai-audit-safety">
                <el-tag effect="plain" type="success">AI 不直接控制手机</el-tag>
                <el-tag effect="plain" type="success"
                  >不允许坐标点击建议</el-tag
                >
                <el-tag effect="plain" type="warning"
                  >高风险动作需人工复核</el-tag
                >
                <el-tag effect="plain"
                  >允许动作：{{
                    (aiAnalysis.audit.safety?.action_allowlist || []).join(
                      " / ",
                    )
                  }}</el-tag
                >
              </div>
              <p class="muted">
                输入摘要：总步数
                {{ aiAnalysis.audit.input_summary?.total_steps || 0 }}， 页面
                {{ aiAnalysis.audit.input_summary?.explored_pages || 0 }}，
                目标覆盖
                {{
                  aiAnalysis.audit.input_summary?.target_coverage_rate || 0
                }}%， 有效迭代
                {{
                  aiAnalysis.audit.iteration_summary?.effective_attempts || 0
                }}
                轮， 跑空
                {{
                  aiAnalysis.audit.iteration_summary?.ineffective_attempts || 0
                }}
                轮。
              </p>
            </div>
          </div>
        </el-card>
        <el-card
          v-if="
            !aiAnalysis.status && !aiAnalysisInProgress && !aiAnalysisFailed
          "
          v-show="reportActiveTab === 'ai'"
          shadow="never"
          class="report-card"
        >
          <el-empty description="当前报告还没有 AI 分析结果">
            <el-button
              type="success"
              :loading="aiAnalyzing"
              :disabled="
                !currentTask ||
                currentTask.status === 'running' ||
                aiAnalysisInProgress
              "
              @click="runAIAnalysis"
            >
              立即分析报告
            </el-button>
          </el-empty>
        </el-card>

        <el-card
          v-show="reportActiveTab === 'overview' && showReportDetails"
          shadow="never"
          class="report-card"
        >
          <template #header>
            <div class="section-title">覆盖与风险概览</div>
          </template>
          <div class="coverage-grid">
            <div class="coverage-card">
              <span class="coverage-label">目标覆盖率</span>
              <strong>{{ targetCoverage.rate || 0 }}%</strong>
              <small
                >{{ targetCoverage.covered || 0 }} /
                {{ targetCoverage.total || 0 }} 个关键词</small
              >
            </div>
            <div class="coverage-card">
              <span class="coverage-label">页面覆盖</span>
              <strong>{{ pageCoverage.page_count || 0 }}</strong>
              <small
                >问题页面 {{ pageCoverage.issue_page_count || 0 }} 个</small
              >
            </div>
            <div class="coverage-card">
              <span class="coverage-label">点击控件</span>
              <strong>{{ pageCoverage.clicked_control_count || 0 }}</strong>
              <small
                >重复页面 {{ pageCoverage.repeated_page_count || 0 }} 个</small
              >
            </div>
            <div class="coverage-card warning">
              <span class="coverage-label">风险跳过</span>
              <strong>{{ skippedRisks.length }}</strong>
              <small>禁止点击控件已拦截</small>
            </div>
          </div>
          <div v-if="targetCoveredKeywords.length" class="keyword-row">
            <span class="muted">已命中目标：</span>
            <el-tag
              v-for="item in targetCoveredKeywords"
              :key="item"
              type="success"
              effect="plain"
            >
              {{ item }}
            </el-tag>
          </div>
          <div v-if="targetUncoveredKeywords.length" class="keyword-row">
            <span class="muted">未覆盖目标：</span>
            <el-tag
              v-for="item in targetUncoveredKeywords"
              :key="item"
              type="warning"
              effect="plain"
            >
              {{ item }}
            </el-tag>
          </div>
          <div
            v-if="targetFilteredKeywords.length"
            class="keyword-row keyword-row-muted"
          >
            <span class="muted">已过滤噪声词：</span>
            <el-tag
              v-for="item in targetFilteredKeywordPreview"
              :key="item"
              type="info"
              effect="plain"
            >
              {{ item }}
            </el-tag>
            <el-tooltip
              v-if="
                targetFilteredKeywords.length >
                targetFilteredKeywordPreview.length
              "
              placement="top"
              :content="
                targetFilteredKeywords
                  .slice(targetFilteredKeywordPreview.length)
                  .join('、')
              "
            >
              <el-tag type="info" effect="plain"
                >+{{
                  targetFilteredKeywords.length -
                  targetFilteredKeywordPreview.length
                }}</el-tag
              >
            </el-tooltip>
          </div>
          <div v-if="issueTypeList.length" class="issue-type-list">
            <span class="muted">问题分类：</span>
            <el-tag
              v-for="item in issueTypeList"
              :key="item.type"
              type="danger"
              effect="plain"
            >
              {{ issueTypeText(item.type) }} × {{ item.count }}
            </el-tag>
          </div>
        </el-card>

        <el-card
          v-if="skippedRisks.length"
          v-show="reportActiveTab === 'risk'"
          shadow="never"
          class="report-card"
        >
          <template #header>
            <div class="section-title">风险跳过明细</div>
          </template>
          <el-table :data="skippedRisks" border size="small">
            <el-table-column label="风险语义" width="150">
              <template #default="{ row }">
                <el-tag type="danger" effect="plain">{{
                  row.group || row.keyword || "-"
                }}</el-tag>
              </template>
            </el-table-column>
            <el-table-column label="命中词" width="110">
              <template #default="{ row }">{{ row.keyword || "-" }}</template>
            </el-table-column>
            <el-table-column label="控件" min-width="220" show-overflow-tooltip>
              <template #default="{ row }">
                {{
                  displayText(
                    row.text ||
                      row.content_desc ||
                      friendlyResourceName(row.resource_id),
                    "未知控件",
                  )
                }}
              </template>
            </el-table-column>
            <el-table-column label="原因" min-width="180" show-overflow-tooltip>
              <template #default="{ row }">{{
                row.reason || "命中风险策略"
              }}</template>
            </el-table-column>
            <el-table-column
              label="Activity"
              min-width="180"
              show-overflow-tooltip
            >
              <template #default="{ row }">{{ row.activity || "-" }}</template>
            </el-table-column>
          </el-table>
        </el-card>
        <el-card
          v-if="!skippedRisks.length"
          v-show="reportActiveTab === 'risk'"
          shadow="never"
          class="report-card"
        >
          <el-empty description="本次探索暂无风险跳过记录" />
        </el-card>

        <el-card
          v-if="pageMapAssetVisible"
          v-show="reportActiveTab === 'evidence'"
          shadow="never"
          class="report-card page-map-assets-card"
        >
          <template #header>
            <div class="section-title">
              <span>页面资产沉淀</span>
              <el-tag
                :type="
                  pageMapAssetStats.status === 'failed' ? 'danger' : 'success'
                "
                effect="plain"
              >
                {{
                  pageMapAssetStats.status === "failed" ? "沉淀失败" : "已沉淀"
                }}
              </el-tag>
            </div>
          </template>
          <div class="page-map-assets-grid">
            <div class="page-map-asset-item">
              <strong>{{
                pageMapAssetNodes.length ||
                pageMapAssetStats.page_nodes_total ||
                0
              }}</strong>
              <span>页面节点</span>
            </div>
            <div class="page-map-asset-item">
              <strong>{{ pageMapAssetElementCount }}</strong>
              <span>控件快照</span>
            </div>
            <div class="page-map-asset-item">
              <strong>{{
                pageMapAssetTransitions.length ||
                pageMapAssetStats.transitions_created ||
                0
              }}</strong>
              <span>跳转关系</span>
            </div>
          </div>
          <div class="muted">
            页面地图已作为后续 AI 规划、语义元素候选和 UI
            改版影响分析的数据底座。
          </div>
        </el-card>

        <el-card
          v-if="pageMap.length"
          v-show="reportActiveTab === 'evidence'"
          shadow="never"
          class="report-card"
        >
          <template #header>
            <div class="section-title">轻量页面地图</div>
          </template>
          <div class="page-map-grid">
            <div
              v-for="(page, index) in pageMap"
              :key="page.signature || index"
              :id="evidencePageDomId(page, index)"
              class="page-map-card"
              :class="{
                danger: visiblePageIssues(page).length,
                highlighted: isEvidencePageHighlighted(page, index),
              }"
            >
              <div
                v-if="mediaUrl(page.screenshot)"
                class="page-map-shot-wrap"
                :style="pageShotStyle(page)"
                @click="openEvidencePreview(page, index)"
              >
                <el-image
                  :src="mediaUrl(page.screenshot)"
                  fit="fill"
                  class="page-map-shot"
                />
                <div class="page-map-overlay-layer">
                  <div
                    v-for="control in pageOverlayControls(page)"
                    :key="`${control.step_index}-${control.action}-${control.bounds || control.x || ''}-${control.y || ''}`"
                    class="page-click-overlay"
                    :class="{
                      highlighted:
                        Number(control.step_index) ===
                        Number(highlightedEvidenceStepIndex),
                      point:
                        !parseControlBounds(control) &&
                        !isSwipeControl(control),
                      swipe: isSwipeControl(control),
                    }"
                    :style="controlOverlayStyle(control, page)"
                    :title="controlOverlayTitle(control)"
                  >
                    <span>{{ control.step_index }}</span>
                  </div>
                </div>
              </div>
              <div v-else class="page-map-shot placeholder">无截图</div>
              <div class="page-map-body">
                <div class="page-map-title">
                  <span>{{ pageDisplayTitle(page, index) }}</span>
                  <el-tag
                    :type="
                      visiblePageIssues(page).length ? 'danger' : 'success'
                    "
                    effect="plain"
                    :class="{ clickable: visiblePageIssues(page).length }"
                    @click="togglePageIssues(page, index)"
                  >
                    {{
                      visiblePageIssues(page).length
                        ? `${visiblePageIssues(page).length} 个问题`
                        : "无问题"
                    }}
                  </el-tag>
                </div>
                <div class="page-map-meta">
                  <span>首次第 {{ page.first_step || "-" }} 步</span>
                  <span>停留 {{ page.step_count || 0 }} 次</span>
                  <span
                    >点击 {{ (page.clicked_controls || []).length }} 个</span
                  >
                  <span
                    >跳过风险 {{ (page.skipped_risks || []).length }} 个</span
                  >
                </div>
                <div class="page-map-activity">
                  {{ page.activity || page.package || "未获取到 Activity" }}
                </div>
                <div
                  v-if="(page.clicked_controls || []).length"
                  class="page-map-controls"
                >
                  <el-tag
                    v-for="control in (page.clicked_controls || []).slice(0, 4)"
                    :key="`${control.step_index}-${control.action}`"
                    effect="plain"
                    :type="
                      Number(control.step_index) ===
                      Number(highlightedEvidenceStepIndex)
                        ? 'warning'
                        : 'info'
                    "
                    :class="{
                      'highlighted-control':
                        Number(control.step_index) ===
                        Number(highlightedEvidenceStepIndex),
                    }"
                  >
                    {{
                      displayText(
                        control.text ||
                          friendlyResourceName(control.resource_id) ||
                          control.action,
                        "未知控件",
                      )
                    }}
                  </el-tag>
                </div>
                <div
                  v-if="isPageIssuesExpanded(page, index)"
                  class="page-map-issues"
                >
                  <div
                    v-for="issue in visiblePageIssues(page)"
                    :key="`${issue.step_index}-${issue.issue_type}`"
                    class="page-map-issue"
                  >
                    <div class="page-map-issue-head">
                      <div>
                        <el-tag size="small" type="danger" effect="dark"
                          >#{{ issue.step_index || "-" }}</el-tag
                        >
                        <strong>{{ issueTypeText(issue.issue_type) }}</strong>
                      </div>
                      <el-button
                        v-if="issue.step_index"
                        text
                        type="primary"
                        size="small"
                        @click="openPageIssueEvidence(page, index, issue)"
                      >
                        看大图定位
                      </el-button>
                    </div>
                    <p>
                      {{
                        issue.issue_message ||
                        "需要结合截图和日志确认是否为真实问题。"
                      }}
                    </p>
                    <div class="page-map-issue-evidence">
                      <div
                        v-for="row in issueQuickEvidenceRows(issue).slice(0, 3)"
                        :key="`${issue.step_index}-${row.label}`"
                      >
                        <span>{{ row.label }}</span>
                        <strong>{{ row.value }}</strong>
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </el-card>
        <el-card
          v-if="!pageMap.length && !entryNavigation.length"
          v-show="reportActiveTab === 'evidence'"
          shadow="never"
          class="report-card"
        >
          <el-empty description="当前报告暂无页面地图或入口导航证据" />
        </el-card>

        <el-card
          v-if="entryNavigation.length"
          v-show="reportActiveTab === 'evidence'"
          shadow="never"
          class="report-card"
        >
          <template #header>
            <div class="section-title">自动入口导航</div>
          </template>
          <div class="entry-nav-list">
            <div
              v-for="item in entryNavigation"
              :key="`${item.keyword}-${item.attempt || item.status}`"
              class="entry-nav-item"
              :class="{ failed: item.status !== 'matched' }"
            >
              <div>
                <strong>{{ item.keyword }}</strong>
                <span class="muted">
                  {{
                    item.status === "matched"
                      ? `命中坐标 (${item.x}, ${item.y})`
                      : "未命中"
                  }}
                </span>
              </div>
              <el-tag
                :type="item.status === 'matched' ? 'success' : 'warning'"
                effect="plain"
              >
                {{ item.status === "matched" ? "已进入" : "需检查" }}
              </el-tag>
            </div>
          </div>
        </el-card>

        <el-card
          id="exploration-step-table-card"
          v-show="reportActiveTab === 'steps'"
          shadow="never"
          class="report-card"
        >
          <template #header>
            <div class="section-title">复现路径</div>
          </template>
          <el-timeline v-if="(insights.reproduction_path || []).length">
            <el-timeline-item
              v-for="item in insights.reproduction_path"
              :key="item.step_index"
              :type="item.changed ? 'success' : 'info'"
            >
              第 {{ item.step_index }} 步：{{ displayPathAction(item) }}
              <span class="muted">
                {{ displayText(item.target || item.activity || "") }}</span
              >
            </el-timeline-item>
          </el-timeline>
          <el-empty v-else description="暂无可复用路径" />
        </el-card>

        <el-card
          v-show="reportActiveTab === 'steps'"
          shadow="never"
          class="report-card"
        >
          <template #header>
            <div class="section-title">步骤轨迹</div>
          </template>
          <el-table
            ref="stepTableRef"
            :data="currentTask.steps || []"
            row-key="step_index"
            border
            class="step-table"
            :row-class-name="stepRowClassName"
          >
            <el-table-column type="expand" width="46">
              <template #default="{ row }">
                <div class="step-detail-panel">
                  <div class="detail-grid">
                    <div>
                      <span class="detail-label">技术定位</span>
                      <div class="detail-value">
                        {{ technicalStepTarget(row) }}
                      </div>
                    </div>
                    <div>
                      <span class="detail-label">Activity</span>
                      <div class="detail-value">
                        {{ row.after_activity || row.before_activity || "-" }}
                      </div>
                    </div>
                    <div>
                      <span class="detail-label">原始动作</span>
                      <div class="detail-value">
                        {{ row.action_label || row.action_type || "-" }}
                      </div>
                    </div>
                    <div>
                      <span class="detail-label">截图说明</span>
                      <div class="detail-value">
                        点击看大图，可按步骤顺序切换标注截图。
                      </div>
                    </div>
                  </div>
                  <div v-if="hasDecisionInfo(row)" class="decision-panel">
                    <div class="decision-header">
                      <span class="detail-label">决策依据</span>
                      <el-tag
                        v-if="stepScoreText(row) !== '-'"
                        type="info"
                        effect="plain"
                      >
                        候选分 {{ stepScoreText(row) }}
                      </el-tag>
                    </div>
                    <div
                      v-if="stepObjectiveHits(row).length"
                      class="decision-row"
                    >
                      <span class="decision-label">目标命中</span>
                      <el-tag
                        v-for="item in stepObjectiveHits(row)"
                        :key="item"
                        type="success"
                        effect="plain"
                      >
                        {{ item }}
                      </el-tag>
                    </div>
                    <div v-if="stepRiskText(row)" class="decision-row">
                      <span class="decision-label">风险判断</span>
                      <el-tag :type="stepRiskTagType(row)" effect="plain">{{
                        stepRiskText(row)
                      }}</el-tag>
                    </div>
                    <div
                      v-if="stepDecisionReasons(row).length"
                      class="decision-reasons"
                    >
                      <el-tag
                        v-for="reason in stepDecisionReasons(row)"
                        :key="reason"
                        effect="plain"
                      >
                        {{ reason }}
                      </el-tag>
                    </div>
                  </div>
                  <div class="step-evidence-panel">
                    <div class="step-evidence-head">
                      <strong>本步复核要点</strong>
                      <el-button
                        v-if="canOpenStepEvidence(row)"
                        text
                        type="primary"
                        size="small"
                        @click="openStepEvidence(row)"
                      >
                        看截图定位
                      </el-button>
                    </div>
                    <div class="step-evidence-grid">
                      <div
                        v-for="item in stepQuickEvidenceRows(row)"
                        :key="`${row.step_index}-${item.label}`"
                        class="step-evidence-row"
                      >
                        <span>{{ item.label }}</span>
                        <strong>{{ item.value }}</strong>
                      </div>
                    </div>
                  </div>
                </div>
              </template>
            </el-table-column>
            <el-table-column prop="step_index" label="#" width="60" />
            <el-table-column label="操作说明" min-width="260">
              <template #default="{ row }">
                <div class="step-primary">{{ displayStepAction(row) }}</div>
                <div class="step-secondary">{{ displayStepTarget(row) }}</div>
              </template>
            </el-table-column>
            <el-table-column label="页面变化" width="100">
              <template #default="{ row }">
                <el-tag :type="row.changed ? 'success' : 'info'">{{
                  row.changed ? "有变化" : "无变化"
                }}</el-tag>
              </template>
            </el-table-column>
            <el-table-column label="疑似问题" min-width="220">
              <template #default="{ row }">
                <div v-if="stepReviewSignal(row)" class="step-issue-cell">
                  <el-tag
                    :type="stepReviewSignal(row).tagType"
                    effect="plain"
                    size="small"
                  >
                    {{ stepReviewSignal(row).label }}
                  </el-tag>
                  <span>{{ stepReviewSignal(row).message }}</span>
                  <el-button
                    v-if="canOpenStepEvidence(row)"
                    text
                    type="primary"
                    size="small"
                    @click="openStepEvidence(row)"
                  >
                    看定位
                  </el-button>
                </div>
                <span v-else>-</span>
              </template>
            </el-table-column>
            <el-table-column label="标注截图" width="130">
              <template #default="{ row }">
                <el-image
                  v-if="row.annotated_screenshot_url || row.screenshot_url"
                  :src="row.annotated_screenshot_url || row.screenshot_url"
                  :preview-src-list="screenshotPreviewList(row)"
                  :initial-index="screenshotPreviewInitialIndex(row)"
                  fit="cover"
                  class="step-shot annotated-shot"
                  preview-teleported
                />
                <span v-else>-</span>
              </template>
            </el-table-column>
          </el-table>
        </el-card>
      </div>
    </el-drawer>

    <el-dialog
      v-model="evidencePreviewVisible"
      :title="evidencePreviewTitle"
      width="860px"
      append-to-body
      class="evidence-preview-dialog"
    >
      <div v-if="evidencePreviewPage" class="evidence-preview-layout">
        <div
          class="evidence-preview-shot-wrap"
          :style="pageShotStyle(evidencePreviewPage)"
        >
          <el-image
            :src="mediaUrl(evidencePreviewPage.screenshot)"
            fit="fill"
            class="evidence-preview-shot"
          />
          <div class="page-map-overlay-layer">
            <div
              v-for="control in pageOverlayControls(evidencePreviewPage, 80)"
              :key="`preview-${control.step_index}-${control.action}-${control.bounds || control.x || ''}-${control.y || ''}`"
              class="page-click-overlay"
              :class="{
                highlighted:
                  Number(control.step_index) ===
                  Number(highlightedEvidenceStepIndex),
                point: !parseControlBounds(control) && !isSwipeControl(control),
                swipe: isSwipeControl(control),
              }"
              :style="controlOverlayStyle(control, evidencePreviewPage)"
              :title="controlOverlayTitle(control)"
            >
              <span>{{ control.step_index }}</span>
            </div>
          </div>
        </div>
        <div class="evidence-preview-side">
          <div class="evidence-preview-side-title">当前关注步骤</div>
          <div class="evidence-preview-focus-card">
            <div class="evidence-focus-header">
              <el-tag
                v-if="evidencePreviewFocusStepIndex"
                type="warning"
                effect="dark"
              >
                #{{ evidencePreviewFocusStepIndex }}
              </el-tag>
              <strong>{{ evidencePreviewFocusTitle }}</strong>
            </div>
            <div class="evidence-focus-row">
              <span>操作</span>
              <strong>{{ evidencePreviewFocusAction }}</strong>
            </div>
            <div class="evidence-focus-row">
              <span>位置</span>
              <strong>{{ evidencePreviewFocusPosition }}</strong>
            </div>
            <div class="evidence-focus-row">
              <span>预期</span>
              <strong>{{ evidencePreviewFocusExpected }}</strong>
            </div>
            <div class="evidence-focus-row issue">
              <span>实际</span>
              <strong>{{ evidencePreviewFocusActual }}</strong>
            </div>
            <p>{{ evidencePreviewFocusAdvice }}</p>
          </div>
          <div class="evidence-preview-side-title secondary">本页其他操作</div>
          <div
            v-if="evidencePreviewControls.length"
            class="evidence-preview-control-list"
          >
            <div
              v-for="control in evidencePreviewControls"
              :key="`preview-list-${control.step_index}-${control.action}`"
              class="evidence-preview-control"
              :class="{
                highlighted:
                  Number(control.step_index) ===
                  Number(highlightedEvidenceStepIndex),
              }"
              @click="selectEvidencePreviewStep(control.step_index)"
            >
              <el-tag
                size="small"
                :type="isSwipeControl(control) ? 'warning' : 'primary'"
                effect="dark"
              >
                #{{ control.step_index || "-" }}
              </el-tag>
              <span>{{ controlOverlayTitle(control) }}</span>
            </div>
          </div>
          <el-empty
            v-else
            description="当前截图没有可绘制点击框，但右侧已展示本步预期和实际结果"
            :image-size="80"
          />
        </div>
      </div>
    </el-dialog>

    <el-dialog
      v-model="deviceHealthVisible"
      title="设备健康检查"
      width="640px"
      append-to-body
    >
      <div v-if="deviceHealthResult" class="device-health-panel">
        <div class="device-health-summary">
          <div>
            <strong>{{
              deviceHealthResult.device_name ||
              deviceHealthResult.device_id ||
              "执行设备"
            }}</strong>
            <span>{{
              deviceHealthResult.checked_at
                ? formatTime(deviceHealthResult.checked_at)
                : "刚刚检查"
            }}</span>
          </div>
          <el-tag
            :type="deviceHealthTag(deviceHealthResult.verdict)"
            effect="dark"
          >
            {{ deviceHealthResult.verdict_text || "需处理" }} ·
            {{ deviceHealthResult.score || 0 }} 分
          </el-tag>
        </div>
        <div class="device-health-checks">
          <div
            v-for="item in deviceHealthResult.checks || []"
            :key="item.key"
            class="device-health-check"
            :class="{ failed: !item.passed }"
          >
            <el-tag :type="item.passed ? 'success' : 'danger'" effect="plain">
              {{ item.passed ? "通过" : "失败" }}
            </el-tag>
            <div>
              <strong>{{ item.name }}</strong>
              <span>{{ item.message || "-" }}</span>
              <p v-if="!item.passed && item.suggestion">
                {{ item.suggestion }}
              </p>
            </div>
          </div>
        </div>
        <div
          v-if="deviceHealthResult.suggestions?.length"
          class="device-health-suggestions"
        >
          <strong>处理建议</strong>
          <p
            v-for="(item, index) in deviceHealthResult.suggestions"
            :key="index"
          >
            {{ item }}
          </p>
        </div>
      </div>
      <el-empty v-else description="暂无检查结果" />
      <template #footer>
        <el-button @click="deviceHealthVisible = false">关闭</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import {
  computed,
  nextTick,
  onMounted,
  onUnmounted,
  reactive,
  ref,
  watch,
} from "vue";
import { useRouter } from "vue-router";
import { ElMessage, ElMessageBox } from "element-plus";
import { ArrowDown, Plus, Refresh } from "@element-plus/icons-vue";
import { buildAINextRoundReadiness } from "./readiness.mjs";
import {
  analyzeExplorationWithAI,
  convertExplorationToCase,
  createExplorationTask,
  deleteExplorationTask,
  captureDeviceScreenshot,
  getDeviceList,
  getExplorationReport,
  getExplorationTasks,
  getAppProjects,
  getPackageList,
  healthCheckDevice,
  reviewExplorationIssue,
  reviewExplorationTarget,
  runExplorationConsistency,
  runExplorationTask,
  stopExplorationTask,
  updateExplorationTask,
} from "@/api/app-automation";

const defaultBlacklist = [
  "退出",
  "退出登录",
  "离开",
  "删除",
  "支付",
  "购买",
  "充值",
  "提现",
  "注销",
  "解散",
  "清空",
  "解绑",
  "发布",
  "授权",
];
const defaultEntryKeywords = [
  "首页",
  "消息",
  "社区",
  "创建",
  "我的",
  "设置",
  "搜索",
  "列表",
];
const stableStartTargets = new Set([
  "首页",
  "消息",
  "社区",
  "我的",
  "发现",
  "搜索",
  "设置",
  "登录",
  "注册",
  "通知",
  "会话",
  "聊天",
  "联系人",
  "好友",
  "返回首页",
]);
const entryKeywordCandidates = [
  "首页",
  "消息",
  "私信",
  "聊天",
  "会话",
  "好友设置",
  "聊天设置",
  "消息列表",
  "好友",
  "社区",
  "创建",
  "我的",
  "设置",
  "搜索",
  "列表",
  "通知",
  "联系人",
  "登录",
  "注册",
  "返回主导航",
];
const processKeywordMarkers = [
  "观察",
  "确认",
  "复核",
  "包括",
  "是否",
  "文案",
  "目标",
  "路径",
  "修正",
  "建议",
  "检查",
  "进入",
  "再进入",
  "点击",
  "打开",
  "查看",
  "验证",
  "测试",
  "人工复现",
  "至第",
  "第",
  "步骤",
  "网络请求",
  "权限提示",
  "Toast",
  "toast",
];
const dynamicTargetMarkers = [
  "条目",
  "列表项",
  "第一个",
  "第二个",
  "某个",
  "任意",
  "指定",
  "目标数据",
  "消息条目",
  "用户条目",
  "商品",
  "订单",
  "卡片",
  "item",
];
const router = useRouter();

const loading = ref(false);
const saving = ref(false);
const converting = ref(false);
const aiAnalyzing = ref(false);
const startingTaskIds = ref([]);
const consistencyStartingTaskIds = ref([]);
const tasks = ref([]);
const total = ref(0);
const page = ref(1);
const pageSize = ref(10);
const projects = ref([]);
const packages = ref([]);
const devices = ref([]);
const createVisible = ref(false);
const reportVisible = ref(false);
const currentTask = ref(null);
const reportActiveTab = ref("overview");
const showReportDetails = ref(false);
const formRef = ref(null);
const expandedPageIssues = ref({});
const expandedPriorityItems = ref({});
const showAllPriorityItems = ref(false);
const expandedConversionReview = ref(false);
const activeConversionReviewFilter = ref("all");
const expandedAIAudit = ref(false);
const highlightedStepIndex = ref(null);
const highlightedEvidenceStepIndex = ref(null);
const evidencePreviewVisible = ref(false);
const evidencePreviewPage = ref(null);
const evidencePreviewIndex = ref(-1);
const reviewingIssueKey = ref("");
const reviewingTargetKey = ref("");
const deviceHealthVisible = ref(false);
const deviceHealthResult = ref(null);
const deviceHealthCheckingIds = ref([]);
const stepTableRef = ref(null);
const selectedAIActionKeys = ref([]);
const selectedAIPlanTargetKeys = ref([]);
const startPointPickerVisible = ref(false);
const startShotLoading = ref(false);
const startPointScreenshot = ref("");
const startPointImageRef = ref(null);
const editingId = ref(null);
const saveAndRunLoading = ref(false);
const isAutoRefreshing = ref(false);
let refreshTimer = null;
const dialogTitle = computed(() =>
  editingId.value ? "编辑探索任务" : "新建探索任务",
);
const isTargetInspectionMode = computed(
  () => form.strategy === "target_inspection",
);

const query = reactive({
  project: "",
  status: "",
  search: "",
});

const form = reactive({
  name: "",
  project: null,
  app_package: null,
  device: null,
  strategy: "target_inspection",
  objective: "",
  entry_keywords: [],
  start_note: "",
  start_actions: [],
  max_steps: 20,
  max_duration: 300,
  blacklist_keywords: [...defaultBlacklist],
  source_task: null,
  source_type: "",
  source_summary: {},
});

const rules = {
  name: [{ required: true, message: "请输入任务名称", trigger: "blur" }],
  app_package: [
    { required: true, message: "请选择应用包名", trigger: "change" },
  ],
  device: [{ required: true, message: "请选择执行设备", trigger: "change" }],
  max_steps: [{ required: true, message: "请设置最大步数", trigger: "change" }],
  max_duration: [
    { required: true, message: "请设置最大时长", trigger: "change" },
  ],
};

const insights = computed(() => currentTask.value?.insights || {});
const issueList = computed(
  () => insights.value?.issues || currentTask.value?.summary?.issues || [],
);
const issueReviewMap = computed(() => {
  const reviews =
    insights.value?.issue_reviews ||
    currentTask.value?.summary?.issue_reviews ||
    {};
  return reviews && typeof reviews === "object" && !Array.isArray(reviews)
    ? reviews
    : {};
});
const archivedIssueResolutions = new Set([
  "normal_behavior",
  "rule_exception",
  "needs_assertion",
  "ignore",
  "false_positive",
]);
const issueReviewResolution = (issue = {}) => {
  return issueReviewMap.value?.[String(issue.step_index)]?.resolution || "";
};
const isIssueArchived = (issue = {}) =>
  archivedIssueResolutions.has(issueReviewResolution(issue));
const actionableIssueList = computed(() =>
  issueList.value.filter((issue) => !isIssueArchived(issue)),
);
const validIssueReviewCount = computed(
  () =>
    Object.values(issueReviewMap.value).filter(
      (item) => item?.resolution === "valid_issue",
    ).length,
);
const ignoredIssueCount = computed(() => {
  const ignored = Array.isArray(insights.value?.ignored_issues)
    ? insights.value.ignored_issues
    : [];
  const reviewedFalsePositive = Object.values(issueReviewMap.value).filter(
    (item) => archivedIssueResolutions.has(item?.resolution),
  ).length;
  return Math.max(ignored.length, reviewedFalsePositive);
});
const pendingIssueCount = computed(() => actionableIssueList.value.length);
const ignoredIssueStepSet = computed(() => {
  const items = Array.isArray(insights.value?.ignored_issues)
    ? insights.value.ignored_issues
    : [];
  return new Set(
    items.map((item) => Number(item.step_index)).filter(Number.isFinite),
  );
});
const entryNavigation = computed(
  () =>
    insights.value?.entry_navigation ||
    currentTask.value?.summary?.entry_navigation ||
    [],
);
const targetCoverage = computed(() => insights.value?.target_coverage || {});
const targetCoveredKeywords = computed(() =>
  Array.isArray(targetCoverage.value?.covered_keywords)
    ? targetCoverage.value.covered_keywords
    : [],
);
const targetUncoveredKeywords = computed(() =>
  Array.isArray(targetCoverage.value?.uncovered_keywords)
    ? targetCoverage.value.uncovered_keywords
    : [],
);
const targetFilteredKeywords = computed(() =>
  Array.isArray(targetCoverage.value?.invalid_keywords_filtered)
    ? targetCoverage.value.invalid_keywords_filtered
    : [],
);
const targetFilteredKeywordPreview = computed(() =>
  targetFilteredKeywords.value.slice(0, 8),
);
const formatTargetStateChanges = (changes = []) => {
  const fieldNames = {
    checked: "选中态",
    selected: "选中态",
    enabled: "可用态",
    text: "文案",
    content_desc: "描述",
  };
  return changes
    .slice(0, 3)
    .map((item) => {
      const field = fieldNames[item.field] || item.field || "状态";
      const before = item.before === "" ? "空" : item.before;
      const after = item.after === "" ? "空" : item.after;
      return `${field} ${before} -> ${after}`;
    })
    .join("；");
};
const formatStateDiagnostics = (diagnostics = {}) => {
  const labels = {
    activity_changed: "页面跳转",
    semantic_page_changed: "页面结构变化",
    target_state_changed: "控件状态变化",
    dialog_opened: "弹窗出现",
    dialog_closed: "弹窗关闭",
    list_content_changed: "列表内容变化",
  };
  const reasons = Array.isArray(diagnostics?.reasons)
    ? diagnostics.reasons
    : [];
  return reasons
    .map((reason) => labels[reason] || reason)
    .filter(Boolean)
    .slice(0, 3)
    .join("、");
};
const normalizeTargetInspectionResult = (item = {}, index = 0) => ({
  ...item,
  target_name: item.target_name || item.target || "-",
  step_index: Number.isFinite(Number(item.step_index))
    ? Number(item.step_index)
    : index + 1,
  bounds: item.bounds || "",
  x: Number.isFinite(Number(item.x)) ? Number(item.x) : null,
  y: Number.isFinite(Number(item.y)) ? Number(item.y) : null,
  match_reason: Array.isArray(item.evidence?.match_reasons)
    ? item.evidence.match_reasons.join("、")
    : Array.isArray(item.match_reasons)
      ? item.match_reasons.join("、")
      : "",
  state_changes: Array.isArray(item.evidence?.state_change?.changes)
    ? item.evidence.state_change.changes
    : Array.isArray(item.state_change?.changes)
      ? item.state_change.changes
      : [],
  state_change_label: formatTargetStateChanges(
    Array.isArray(item.evidence?.state_change?.changes)
      ? item.evidence.state_change.changes
      : Array.isArray(item.state_change?.changes)
        ? item.state_change.changes
        : [],
  ),
  state_diagnostics:
    item.evidence?.state_diagnostics || item.state_diagnostics || {},
  state_diagnostics_label: formatStateDiagnostics(
    item.evidence?.state_diagnostics || item.state_diagnostics || {},
  ),
  recovery_status: item.evidence?.recovery?.status || "",
  error_message: item.error_message || item.issue_message || "",
});
const targetInspectionResults = computed(() => {
  const directResults = Array.isArray(currentTask.value?.target_results)
    ? currentTask.value.target_results
    : [];
  if (directResults.length)
    return directResults.map(normalizeTargetInspectionResult);
  const summaryResults = currentTask.value?.summary?.target_results;
  return Array.isArray(summaryResults)
    ? summaryResults.map(normalizeTargetInspectionResult)
    : [];
});
const explorationRunHistory = computed(() => {
  const history = Array.isArray(currentTask.value?.run_history)
    ? currentTask.value.run_history
    : [];
  if (history.length) return history;
  return currentTask.value?.latest_run ? [currentTask.value.latest_run] : [];
});
const targetRunHistory = computed(() => {
  const history = Array.isArray(currentTask.value?.target_run_history)
    ? currentTask.value.target_run_history
    : [];
  return history
    .map((item) => ({
      run: item.run || {},
      target_results: Array.isArray(item.target_results)
        ? item.target_results.map(normalizeTargetInspectionResult)
        : [],
    }))
    .filter((item) => item.run?.id && item.target_results.length);
});
const backendTargetConsistency = computed(() => {
  const value =
    currentTask.value?.target_consistency ||
    currentTask.value?.summary?.target_consistency ||
    {};
  return value && typeof value === "object" ? value : {};
});
const targetAcceptanceItems = computed(() =>
  Array.isArray(backendTargetConsistency.value?.acceptance_items)
    ? backendTargetConsistency.value.acceptance_items
    : [],
);
const failedTargetAcceptanceItems = computed(() =>
  targetAcceptanceItems.value.filter((item) => !item.passed),
);
const targetAcceptanceVisibleItems = computed(() => {
  if (failedTargetAcceptanceItems.value.length) {
    return failedTargetAcceptanceItems.value.slice(0, 4);
  }
  return targetAcceptanceItems.value.slice(0, 4);
});
const recoverySuccessStatuses = new Set([
  "not_needed",
  "not_needed_same_activity",
  "recovered",
  "recovered_by_targets",
  "recovered_by_relaunch",
  "recovered_by_relaunch_targets",
]);
const targetAcceptanceGuideConfig = {
  run_count: {
    badge: "样本不足",
    tagType: "warning",
    reason:
      "当前执行次数还不够，不能判断这个任务是否稳定。请让手机停在同一个起始页，再连续跑三次。",
    action: "consistency",
    actionLabel: "跑三次一致性",
  },
  recognition_rate: {
    badge: "目标命中",
    tagType: "warning",
    reason:
      "有目标在部分轮次没有被识别到，优先检查截图里目标是否存在，以及目标名称/语义元素是否足够准确。",
    action: "evidence",
    actionLabel: "看截图证据",
  },
  anchor_recovery_rate: {
    badge: "锚点恢复",
    tagType: "warning",
    reason:
      "点击后页面偏航或返回失败，说明执行器没有稳定回到起始业务区域。优先补返回策略或降低这类入口优先级。",
    action: "steps",
    actionLabel: "看执行步骤",
  },
  evidence_completeness_rate: {
    badge: "证据缺失",
    tagType: "warning",
    reason:
      "部分目标缺少点击前后截图、命中范围或坐标，报告无法支撑复核。优先检查截图保存和目标结果入库链路。",
    action: "evidence",
    actionLabel: "看页面证据",
  },
  consistency_rate: {
    badge: "结果波动",
    tagType: "warning",
    reason:
      "同一个目标三次结果不一致，可能是页面数据波动、设备状态不同，或定位规则不稳定。先对比三次截图。",
    action: "evidence",
    actionLabel: "对比证据",
  },
  off_list_action_count: {
    badge: "越界动作",
    tagType: "danger",
    reason:
      "目标巡检不应该点击目标清单之外的控件。出现这类指标时，要优先回退执行器逻辑，不要继续扩 AI 分析。",
    action: "steps",
    actionLabel: "看异常步骤",
  },
  risk_auto_action_count: {
    badge: "高风险动作",
    tagType: "danger",
    reason:
      "删除、退出、支付等高风险动作不允许自动执行。出现这类指标时，要先检查风险护栏是否失效。",
    action: "risk",
    actionLabel: "看风险记录",
  },
};
const targetAcceptanceAffectedTargets = (key) => {
  const backend = backendTargetConsistency.value || {};
  const runCount = Number(
    backend.run_count || targetStabilitySummary.value.runCount || 0,
  );
  if (!targetStabilityRows.value.length) return [];

  const rows = targetStabilityRows.value.filter((row) => {
    if (key === "recognition_rate")
      return Number(row.recognizedInRuns || 0) < runCount;
    if (key === "evidence_completeness_rate")
      return Number(row.evidenceCompleteInRuns || 0) < runCount;
    if (key === "consistency_rate") return !row.stable;
    if (key === "anchor_recovery_rate") {
      return row.runs.some(
        (run) =>
          run.recovery_status &&
          !recoverySuccessStatuses.has(run.recovery_status),
      );
    }
    return false;
  });

  return rows.slice(0, 6).map((row) => {
    const step = row.runs.find((item) =>
      Number.isFinite(Number(item.step_index)),
    )?.step_index;
    return {
      key: `${key}-${row.target}`,
      label: step ? `${row.target}（第 ${step} 步）` : row.target,
      stepIndex: step,
      tagType: row.stable ? "info" : "warning",
    };
  });
};
const targetAcceptanceGuardrailRows = (key) => {
  const backend = backendTargetConsistency.value || {};
  const source =
    key === "off_list_action_count"
      ? backend.off_list_actions
      : backend.risk_auto_actions;
  return Array.isArray(source)
    ? source.slice(0, 4).map((item, index) => ({
        label: `异常 ${index + 1}`,
        value:
          [
            item.step_index ? `第 ${item.step_index} 步` : "",
            item.action_type || item.source || "",
            item.target || item.target_name || "",
          ]
            .filter(Boolean)
            .join(" / ") || "未记录具体步骤",
      }))
    : [];
};
const targetAcceptanceIssueCards = computed(() =>
  failedTargetAcceptanceItems.value.map((item) => {
    const config = targetAcceptanceGuideConfig[item.key] || {
      badge: "未达标",
      tagType: "warning",
      reason: item.suggestion || "该指标未达标，需要结合报告证据人工复核。",
      action: "evidence",
      actionLabel: "看证据",
    };
    const guardrailRows = [
      "off_list_action_count",
      "risk_auto_action_count",
    ].includes(item.key)
      ? targetAcceptanceGuardrailRows(item.key)
      : [];
    return {
      key: item.key,
      title: `${item.label}未达标`,
      badge: config.badge,
      tagType: config.tagType,
      reason: config.reason,
      action: config.action,
      actionLabel: config.actionLabel,
      targets: targetAcceptanceAffectedTargets(item.key),
      detailRows: [
        { label: "当前", value: item.actual },
        { label: "预期", value: item.expected },
        ...guardrailRows,
      ],
    };
  }),
);
const targetAcceptanceSummary = computed(() => {
  const consistency = backendTargetConsistency.value || {};
  const available = Boolean(
    consistency.available && targetAcceptanceItems.value.length,
  );
  const failedCount = failedTargetAcceptanceItems.value.length;
  const total = targetAcceptanceItems.value.length;
  if (!available) {
    return {
      available: false,
      level: "info",
      tagType: "info",
      title: "暂无巡检验收数据",
      description: "连续执行目标巡检后会生成稳定性验收项。",
      badge: "待执行",
      nextAction: "先跑目标巡检",
      action: "",
    };
  }
  if (failedCount) {
    const hasTargetQualityGap = failedTargetAcceptanceItems.value.some((item) =>
      [
        "recognition_rate",
        "evidence_completeness_rate",
        "consistency_rate",
      ].includes(item.key),
    );
    const hasGuardrailGap = failedTargetAcceptanceItems.value.some((item) =>
      ["off_list_action_count", "risk_auto_action_count"].includes(item.key),
    );
    return {
      available,
      level: hasGuardrailGap ? "danger" : "warning",
      tagType: hasGuardrailGap ? "danger" : "warning",
      title: "巡检验收未通过",
      description: `有 ${failedCount}/${total} 个指标未达标，先处理这些指标，再把本轮结果作为稳定基线。`,
      badge: `${failedCount} 项未达标`,
      nextAction: hasTargetQualityGap
        ? "优先看页面证据和目标命中范围"
        : "优先检查执行器护栏",
      action: hasTargetQualityGap ? "evidence" : "steps",
    };
  }
  return {
    available,
    level: "success",
    tagType: "success",
    title: "巡检验收通过",
    description: `最近 ${consistency.run_count || 0} 次执行的核心指标已达标，可以作为稳定基线继续观察。`,
    badge: `${total}/${total} 通过`,
    nextAction: "继续沉淀页面地图或生成下一轮目标",
    action: "page_map",
  };
});
const targetStabilityRows = computed(() => {
  const backendRows = Array.isArray(backendTargetConsistency.value?.rows)
    ? backendTargetConsistency.value.rows
    : [];
  if (backendRows.length) {
    return backendRows.map((row) => ({
      target: row.target_name || row.target || "-",
      runs: Array.isArray(row.statuses) ? row.statuses : [],
      stable: Boolean(row.consistent),
      recognizedInRuns: Number(row.recognized_in_runs || 0),
      evidenceCompleteInRuns: Number(row.evidence_complete_in_runs || 0),
      recommendation: row.recommendation || "",
    }));
  }
  const runs = targetRunHistory.value.slice(0, 3);
  if (!runs.length) return [];
  const targetNames = [];
  runs.forEach((runItem) => {
    runItem.target_results.forEach((result) => {
      if (result.target_name && !targetNames.includes(result.target_name)) {
        targetNames.push(result.target_name);
      }
    });
  });
  return targetNames.map((target) => {
    const statuses = runs.map((runItem) => {
      const result = runItem.target_results.find(
        (item) => item.target_name === target,
      );
      return {
        run_id: runItem.run.id,
        status: result?.status || "not_found",
      };
    });
    const stable =
      statuses.length >= 2
        ? statuses.every((item) => item.status === "found_effective")
        : statuses[0]?.status === "found_effective";
    return {
      target,
      runs: statuses,
      stable,
    };
  });
});
const targetStabilitySummary = computed(() => {
  const backend = backendTargetConsistency.value || {};
  if (backend.available) {
    const total = Number(backend.target_count || 0);
    const stable = Number(backend.consistent_target_count || 0);
    return {
      total,
      stable,
      unstable: Number(
        backend.inconsistent_target_count ?? Math.max(total - stable, 0),
      ),
      runCount: Number(backend.run_count || 0),
      consistencyRate: Number(backend.consistency_rate || 0),
      passed: Boolean(backend.passed),
      failedThresholds: Array.isArray(backend.failed_thresholds)
        ? backend.failed_thresholds
        : [],
    };
  }
  const rows = targetStabilityRows.value;
  const stable = rows.filter((item) => item.stable).length;
  const total = rows.length;
  const runCount = Math.min(targetRunHistory.value.length, 3);
  return {
    total,
    stable,
    unstable: Math.max(total - stable, 0),
    runCount,
    consistencyRate: total ? Math.round((stable / total) * 10000) / 100 : 0,
  };
});
const targetBatchDiffItems = computed(() => {
  const [current, previous] = targetRunHistory.value;
  if (!current || !previous) return [];
  const targetNames = Array.from(
    new Set(
      [
        ...current.target_results.map((item) => item.target_name),
        ...previous.target_results.map((item) => item.target_name),
      ].filter(Boolean),
    ),
  );
  return targetNames
    .map((target) => {
      const currentStatus =
        current.target_results.find((item) => item.target_name === target)
          ?.status || "not_found";
      const previousStatus =
        previous.target_results.find((item) => item.target_name === target)
          ?.status || "not_found";
      return { target, current: currentStatus, previous: previousStatus };
    })
    .filter((item) => item.current !== item.previous);
});
const targetInspectionSummary = computed(() => {
  const results = targetInspectionResults.value;
  const total = results.length;
  const effective = results.filter(
    (item) => item.status === "found_effective",
  ).length;
  const unconfirmed = results.filter(
    (item) => item.status === "found_unconfirmed",
  ).length;
  const notFound = results.filter((item) => item.status === "not_found").length;
  const issueCount = results.filter(
    (item) =>
      !item.is_review_suppressed &&
      !["found_effective", "found_unconfirmed"].includes(item.status),
  ).length;
  const reviewed = results.filter(
    (item) => item.effective_review?.resolution,
  ).length;
  const suppressed = results.filter((item) => item.is_review_suppressed).length;
  const covered = effective + unconfirmed;
  return {
    total,
    covered,
    effective,
    unconfirmed,
    notFound,
    issueCount,
    reviewed,
    suppressed,
    coverageRate: total ? Math.round((covered / total) * 10000) / 100 : 0,
  };
});
const pageCoverage = computed(() => insights.value?.page_coverage || {});
const skippedRisks = computed(
  () =>
    insights.value?.skipped_risks ||
    currentTask.value?.summary?.skipped_risks ||
    [],
);
const pageMap = computed(
  () => insights.value?.page_map || currentTask.value?.summary?.page_map || [],
);
const conversionSummary = computed(
  () => insights.value?.conversion_summary || {},
);
const conversionNeedsReview = computed(
  () => conversionSummary.value?.needs_review || [],
);
const filteredConversionNeedsReview = computed(() => {
  if (activeConversionReviewFilter.value === "all")
    return conversionNeedsReview.value;
  return conversionNeedsReview.value.filter(
    (item) =>
      conversionReviewReasonType(item) === activeConversionReviewFilter.value,
  );
});
const startActionSafetySummary = computed(() => {
  const actions = normalizeStartActions(form.start_actions);
  const customKeywords = Array.isArray(form.blacklist_keywords)
    ? form.blacklist_keywords
    : [];
  const summary = {
    total: actions.length,
    low: 0,
    caution: 0,
    forbidden: 0,
    messages: [],
    level: "safe",
    label: "低风险",
    tagType: "success",
  };

  actions.forEach((action, index) => {
    const risk = assessStartActionRisk(action, customKeywords);
    if (risk.level === "forbidden") {
      summary.forbidden += 1;
      summary.messages.push(
        `第 ${index + 1} 个动作命中禁止风险：${risk.reason}`,
      );
    } else if (risk.level === "caution") {
      summary.caution += 1;
      summary.messages.push(`第 ${index + 1} 个动作需确认：${risk.reason}`);
    } else {
      summary.low += 1;
    }
  });

  if (summary.forbidden > 0) {
    summary.level = "danger";
    summary.label = "存在禁止动作";
    summary.tagType = "danger";
  } else if (summary.caution > 0) {
    summary.level = "warning";
    summary.label = "需人工确认";
    summary.tagType = "warning";
  }
  return summary;
});
const conversionReviewFilterOptions = computed(() => {
  const countByType = (type) =>
    conversionNeedsReview.value.filter(
      (item) => conversionReviewReasonType(item) === type,
    ).length;
  return [
    {
      value: "all",
      label: "全部复核",
      count: conversionNeedsReview.value.length,
      type: "warning",
    },
    {
      value: "coordinate",
      label: "坐标兜底",
      count: countByType("coordinate"),
      type: "warning",
    },
    {
      value: "no_change",
      label: "点击无变化",
      count: countByType("no_change"),
      type: "info",
    },
    {
      value: "issue",
      label: "问题步骤",
      count: countByType("issue"),
      type: "danger",
    },
    {
      value: "risk",
      label: "风险步骤",
      count: countByType("risk"),
      type: "danger",
    },
    {
      value: "other",
      label: "其他",
      count: countByType("other"),
      type: "info",
    },
  ].filter((item) => item.value === "all" || item.count > 0);
});
const aiAnalysis = computed(
  () =>
    insights.value?.ai_analysis ||
    currentTask.value?.summary?.ai_analysis ||
    {},
);
const aiNextRoundDraft = computed(
  () => aiAnalysis.value?.next_round_draft || {},
);
const aiInspectionPlan = computed(
  () =>
    aiAnalysis.value?.inspection_plan ||
    aiNextRoundDraft.value?.inspection_plan ||
    {},
);
const aiAnalysisStatus = computed(
  () => currentTask.value?.summary?.ai_analysis_status || "",
);
const aiAnalysisInProgress = computed(() =>
  ["queued", "running"].includes(aiAnalysisStatus.value),
);
const aiAnalysisFailed = computed(
  () => aiAnalysisStatus.value === "failed" && !aiAnalysis.value?.status,
);
const aiPromptDisplayName = computed(() => {
  const auditPrompt = aiAnalysis.value?.audit?.prompt || {};
  return (
    aiAnalysis.value?.prompt_config_name ||
    auditPrompt.name ||
    aiAnalysis.value?.prompt_type ||
    "内置默认提示词"
  );
});
const aiAnalysisProgressStage = computed(
  () => currentTask.value?.summary?.ai_analysis_stage || "等待分析",
);
const aiAnalysisProgressMessage = computed(
  () =>
    currentTask.value?.summary?.ai_analysis_message || "AI 分析任务正在处理中",
);
const aiAnalysisErrorMessage = computed(
  () =>
    currentTask.value?.summary?.ai_analysis_error ||
    currentTask.value?.summary?.ai_analysis_message ||
    "AI 分析失败，请检查模型配置后重试",
);
const aiPlanTargets = computed(() => {
  const targets = Array.isArray(aiInspectionPlan.value?.recommended_targets)
    ? aiInspectionPlan.value.recommended_targets
    : [];
  return targets
    .map((item, index) => ({
      target_name: displayText(
        item.target_name || item.target || item.name,
        "",
      ),
      page_name: displayText(item.page_name || item.page, ""),
      semantic_role: displayText(item.semantic_role || item.role, "控件"),
      priority: ["P0", "P1", "P2"].includes(
        String(item.priority || "").toUpperCase(),
      )
        ? String(item.priority).toUpperCase()
        : "P1",
      reason: displayText(item.reason || item.candidate_reason, ""),
      risk: ["low", "medium", "high"].includes(item.risk)
        ? item.risk
        : "medium",
      source: item.source || "llm",
      index,
    }))
    .filter((item) => item.target_name);
});
const aiPlanStartActions = computed(() =>
  Array.isArray(aiInspectionPlan.value?.start_actions)
    ? normalizeAIActionProposals(aiInspectionPlan.value.start_actions)
    : [],
);
const aiPlanCoverageGaps = computed(() =>
  Array.isArray(aiInspectionPlan.value?.coverage_gaps)
    ? aiInspectionPlan.value.coverage_gaps
        .map((item) => displayText(item, ""))
        .filter(Boolean)
        .slice(0, 8)
    : [],
);
const aiPlanRiskControls = computed(() =>
  Array.isArray(aiInspectionPlan.value?.risk_controls)
    ? aiInspectionPlan.value.risk_controls
        .map((item) => displayText(item, ""))
        .filter(Boolean)
        .slice(0, 8)
    : [],
);
const aiSemanticSuggestions = computed(() =>
  Array.isArray(aiAnalysis.value?.semantic_suggestions)
    ? aiAnalysis.value.semantic_suggestions
        .map((item) => ({
          page_name: displayText(item.page_name || item.page, ""),
          target_name: displayText(
            item.target_name || item.target || item.name,
            "",
          ),
          semantic_role: displayText(item.semantic_role || item.role, "控件"),
          suggestion: displayText(
            item.suggestion || item.advice,
            "建议人工确认语义命名和控件角色。",
          ),
          reason: displayText(item.reason, ""),
        }))
        .filter((item) => item.target_name)
        .slice(0, 8)
    : [],
);
const aiInspectionPlanVisible = computed(() =>
  Boolean(
    aiInspectionPlan.value?.schema_version ||
    aiPlanTargets.value.length ||
    aiPlanCoverageGaps.value.length ||
    aiPlanRiskControls.value.length ||
    aiSemanticSuggestions.value.length,
  ),
);
const pageMapAssets = computed(() => currentTask.value?.page_map_assets || {});
const pageMapAssetStats = computed(
  () =>
    pageMapAssets.value?.stats ||
    currentTask.value?.summary?.page_map_persistence ||
    {},
);
const pageMapAssetNodes = computed(() =>
  Array.isArray(pageMapAssets.value?.nodes) ? pageMapAssets.value.nodes : [],
);
const pageMapAssetTransitions = computed(() =>
  Array.isArray(pageMapAssets.value?.transitions)
    ? pageMapAssets.value.transitions
    : [],
);
const pageMapAssetElementCount = computed(() => {
  const fromNodes = pageMapAssetNodes.value.reduce(
    (sum, node) => sum + Number(node.element_count || 0),
    0,
  );
  return (
    fromNodes ||
    Number(pageMapAssetStats.value.page_elements_created || 0) +
      Number(pageMapAssetStats.value.page_elements_updated || 0)
  );
});
const pageMapAssetVisible = computed(() => {
  return Boolean(
    pageMapAssetNodes.value.length ||
    pageMapAssetTransitions.value.length ||
    pageMapAssetStats.value.page_nodes_total ||
    pageMapAssetStats.value.status === "failed",
  );
});
const explorationGuard = computed(() => {
  const summary = currentTask.value?.summary || {};
  return {
    stopReason: summary.exploration_stop_reason || "",
    emptyPageEscapes: Number(summary.empty_page_escape_count || 0),
    unresponsiveTargets: Number(summary.unresponsive_target_count || 0),
    stagnantActions: Number(summary.stagnant_action_count || 0),
    lowValueActions: Number(summary.low_value_action_count || 0),
    repeatedPages: Number(summary.repeated_semantic_hit_count || 0),
    semanticPages: Number(summary.explored_semantic_pages || 0),
  };
});
const taskExecutionHealth = computed(() => {
  const value = currentTask.value?.execution_health || {};
  return value && typeof value === "object" ? value : {};
});
const qualityDecision = computed(() => {
  const task = currentTask.value || {};
  const status = String(task.status || "").toLowerCase();
  const result = String(task.result || "").toLowerCase();
  const coverageRate = Number(targetCoverage.value?.rate || 0);
  const coverageTotal = Number(targetCoverage.value?.total || 0);
  const needsReviewCount = Number(
    conversionSummary.value?.needs_review_count || 0,
  );
  const issueCount = actionableIssueList.value.length;
  const validCount = validIssueReviewCount.value;
  const skippedRiskCount = skippedRisks.value.length;
  const pageCount = Number(
    task.explored_pages || pageCoverage.value?.page_count || 0,
  );
  const stepCount = Number(
    task.total_steps || conversionSummary.value?.total_steps || 0,
  );
  const hasLogcat = Boolean(task.logcat?.available);
  const hasAIAnalysis = Boolean(
    aiAnalysis.value?.status || aiAnalysis.value?.conclusion,
  );
  const guard = explorationGuard.value;
  const hasGuardStop = Boolean(guard.stopReason);
  const hasAcceptanceFailed =
    targetAcceptanceSummary.value.available &&
    failedTargetAcceptanceItems.value.length > 0;
  const acceptanceFailedCount = failedTargetAcceptanceItems.value.length;
  const reasons = [];

  let level = "info";
  let tagType = "info";
  let title = "等待更多信息";
  let description = "当前报告信息还不足以形成稳定质量判断。";
  let nextAction = "继续补充执行证据";

  if (taskExecutionHealth.value.is_stale) {
    level = taskExecutionHealth.value.level === "danger" ? "danger" : "warning";
    tagType = level;
    title = "执行状态疑似卡住";
    description =
      taskExecutionHealth.value.message ||
      "任务状态长时间未更新，当前结果不能作为质量判断依据。";
    nextAction = taskExecutionHealth.value.suggestion || "先检查设备和后台服务";
    reasons.push("执行状态异常");
  } else if (["pending"].includes(status)) {
    title = "暂不判定";
    description = "任务尚未执行，不能作为质量判断依据。";
    nextAction = "先执行探索任务";
    reasons.push("任务未执行");
  } else if (["running"].includes(status)) {
    title = "执行中，暂不判定";
    description = "任务仍在执行中，建议等待报告、截图和日志生成后再判断。";
    nextAction = "等待执行完成";
    reasons.push("执行中");
  } else if (
    ["error", "failed"].includes(status) ||
    ["error", "failed"].includes(result) ||
    task.error_message
  ) {
    level = "danger";
    tagType = "danger";
    title = "不建议发布";
    description = "本次探索执行异常或任务失败，当前结果不能作为通过依据。";
    nextAction = "先查看失败原因并重试";
    reasons.push("执行异常");
  } else if (validCount > 0) {
    level = "danger";
    tagType = "danger";
    title = "不建议发布";
    description = `已有 ${validCount} 个问题被人工确认为有效问题，需要先完成缺陷处理。`;
    nextAction = "提交或跟进缺陷";
    reasons.push("存在有效问题");
  } else if (issueCount > 0) {
    level = "warning";
    tagType = "warning";
    title = "暂缓结论，先复核";
    description = `本次仍有 ${issueCount} 个疑似问题，需要结合截图、日志和复现路径确认真实性。`;
    nextAction = "复核疑似问题";
    reasons.push("存在待复核问题");
  } else if (needsReviewCount > 0) {
    level = "warning";
    tagType = "warning";
    title = "可参考，但需补复核";
    description = `探索未发现明确问题，但仍有 ${needsReviewCount} 个步骤建议人工确认后再沉淀资产。`;
    nextAction = "复核步骤后转用例";
    reasons.push("存在需复核步骤");
  } else if (hasAcceptanceFailed) {
    level =
      targetAcceptanceSummary.value.level === "danger" ? "danger" : "warning";
    tagType = targetAcceptanceSummary.value.tagType;
    title = "暂缓结论，先修巡检指标";
    description = `目标巡检还有 ${acceptanceFailedCount} 个验收指标未达标，本轮结果还不能作为稳定基线。`;
    nextAction = targetAcceptanceSummary.value.nextAction;
    reasons.push("巡检验收未过");
  } else if (hasGuardStop) {
    level = "warning";
    tagType = "warning";
    title = "本轮已自动止损";
    description = `探索器判断继续执行价值不高，已提前结束：${guard.stopReason}`;
    nextAction = "调整入口或目标后再跑一轮";
    reasons.push("触发探索止损");
  } else if (coverageTotal > 0 && coverageRate < 60) {
    level = "warning";
    tagType = "warning";
    title = "覆盖不足，建议继续探索";
    description = `当前目标覆盖率 ${coverageRate}%，还不足以支撑完整质量结论。`;
    nextAction = "补充入口或继续下一轮";
    reasons.push("目标覆盖偏低");
  } else {
    level = "success";
    tagType = "success";
    title = "本轮未发现阻塞问题";
    description = "当前探索未发现待复核疑似问题，可作为本轮探索通过参考。";
    nextAction = "沉淀路径或继续扩展覆盖";
    reasons.push("暂无阻塞问题");
  }

  if (ignoredIssueCount.value > 0)
    reasons.push(`已归档误报 ${ignoredIssueCount.value} 个`);
  if (skippedRiskCount > 0) reasons.push(`跳过风险控件 ${skippedRiskCount} 个`);
  if (guard.emptyPageEscapes > 0)
    reasons.push(`空页返回 ${guard.emptyPageEscapes} 次`);
  if (guard.unresponsiveTargets > 0)
    reasons.push(`无响应控件 ${guard.unresponsiveTargets} 个`);
  if (
    targetAcceptanceSummary.value.available &&
    !failedTargetAcceptanceItems.value.length
  )
    reasons.push("巡检验收通过");
  if (!hasLogcat) reasons.push("缺少 logcat");
  if (!hasAIAnalysis) reasons.push("未生成 AI 分析");

  return {
    level,
    tagType,
    title,
    description,
    nextAction,
    reasons,
    metrics: [
      {
        label: "问题状态",
        value: validCount
          ? `${validCount} 有效`
          : issueCount
            ? `${issueCount} 待复核`
            : "无待复核",
        desc: ignoredIssueCount.value
          ? `已归档 ${ignoredIssueCount.value} 个误报`
          : "按人工复核状态统计",
      },
      {
        label: "目标覆盖",
        value: `${coverageRate}%`,
        desc: coverageTotal
          ? `${targetCoverage.value?.covered || 0}/${coverageTotal} 个关键词`
          : "未配置目标关键词",
      },
      {
        label: "执行证据",
        value: `${stepCount} 步 / ${pageCount} 页`,
        desc: `${Math.round(task.duration || 0)} 秒 · ${hasLogcat ? "logcat 已采集" : "缺少 logcat 附件"}`,
      },
      {
        label: "探索效率",
        value: hasGuardStop
          ? "已止损"
          : `${guard.semanticPages || pageCount} 个语义页`,
        desc: hasGuardStop
          ? guard.stopReason
          : `低价值 ${guard.lowValueActions} / 重复 ${guard.repeatedPages}`,
      },
      {
        label: "AI 分析",
        value: hasAIAnalysis ? "已生成" : "未生成",
        desc: aiAnalysisStatus.value || "可按需触发分析",
      },
    ],
  };
});

const postRunGuide = computed(() => {
  const task = currentTask.value || {};
  const status = String(task.status || "").toLowerCase();
  const hasFailed = ["error", "failed"].includes(status) || task.error_message;
  const hasIssues = actionableIssueList.value.length > 0;
  const hasTargets = targetInspectionResults.value.length > 0;
  const hasTargetGaps =
    targetInspectionSummary.value.notFound > 0 ||
    targetInspectionSummary.value.unconfirmed > 0;
  const hasPageAssets = pageMapAssetVisible.value || pageMap.value.length > 0;
  const hasAI = Boolean(
    aiAnalysis.value?.status || aiAnalysis.value?.conclusion,
  );
  const hasAcceptanceFailed =
    targetAcceptanceSummary.value.available &&
    failedTargetAcceptanceItems.value.length > 0;
  const consistencyRunCount = Number(
    backendTargetConsistency.value?.run_count || 0,
  );
  const needsConsistencyBaseline =
    task.strategy === "target_inspection" &&
    hasTargets &&
    consistencyRunCount < 3;
  const isExecutionStale = Boolean(task.execution_health?.is_stale);

  let title = "先按这条链路收敛本轮结果";
  let description =
    "跑完探索后，不要先看所有明细；先判断有没有失败/疑似问题，再沉淀页面地图和下一轮目标。";
  let badge = "处理建议";
  let tagType = "info";
  const primaryActions = [];

  if (isExecutionStale) {
    title = "先处理执行卡住";
    description =
      task.execution_health?.message ||
      "任务状态长时间没有更新，先排查设备、ADB 或后台执行服务。";
    badge = "疑似卡住";
    tagType = task.execution_health?.level === "danger" ? "danger" : "warning";
    primaryActions.push({ key: "refresh", label: "刷新状态", type: "primary" });
    primaryActions.push({
      key: "device_health",
      label: "检查设备",
      type: "warning",
    });
    primaryActions.push({ key: "logs", label: "查看日志", type: "warning" });
    primaryActions.push({
      key: "stop_current",
      label: "停止任务",
      type: "danger",
    });
  } else if (status === "running" || status === "pending") {
    title = "先等任务执行完成";
    description =
      "任务还没有完整报告，现在只需要观察执行状态；完成后再处理证据、问题和页面地图。";
    badge = status === "running" ? "执行中" : "等待中";
    primaryActions.push({ key: "refresh", label: "刷新状态", type: "primary" });
    primaryActions.push({
      key: "device_health",
      label: "检查设备",
      type: "warning",
    });
  } else if (hasFailed) {
    title = "本轮先当作执行异常处理";
    description =
      "这类结果不要急着分析业务问题，优先看失败原因和 logcat，确认是设备/脚本/服务问题后再重跑。";
    badge = "先排障";
    tagType = "danger";
    primaryActions.push({
      key: "device_health",
      label: "检查设备",
      type: "warning",
    });
    primaryActions.push({ key: "logs", label: "查看日志", type: "danger" });
    primaryActions.push({ key: "steps", label: "看失败步骤", type: "warning" });
  } else if (hasIssues) {
    title = "先复核疑似问题";
    description =
      "只有复核后才能决定是缺陷、误报还是规则例外；不要直接把疑似问题当业务缺陷提交。";
    badge = `${actionableIssueList.value.length} 个待复核`;
    tagType = "warning";
    primaryActions.push({ key: "issues", label: "复核问题", type: "warning" });
    primaryActions.push({
      key: "evidence",
      label: "看页面证据",
      type: "primary",
    });
    primaryActions.push({ key: "logs", label: "导出日志", type: "info" });
  } else if (hasAcceptanceFailed) {
    title = "先处理巡检验收项";
    description =
      "验收指标未过时，不建议继续扩 AI 分析；先看失败项对应的证据、步骤或护栏统计。";
    badge = `${failedTargetAcceptanceItems.value.length} 项未达标`;
    tagType = targetAcceptanceSummary.value.tagType;
    primaryActions.push({
      key: targetAcceptanceSummary.value.action || "evidence",
      label: "处理未达标项",
      type: tagType,
    });
    primaryActions.push({
      key: "evidence",
      label: "看页面证据",
      type: "primary",
    });
  } else if (hasTargets && hasTargetGaps) {
    title = "目标巡检还没收敛";
    description =
      "存在未找到或待确认目标，下一步应该回到页面地图补控件语义、合并重复页，或者调整目标清单后重跑。";
    badge = "补语义库";
    tagType = "warning";
    primaryActions.push({
      key: "page_map",
      label: "去页面地图治理",
      type: "warning",
    });
    primaryActions.push({
      key: "evidence",
      label: "看截图定位",
      type: "primary",
    });
  } else if (needsConsistencyBaseline) {
    title = "本轮可以做稳定性验证";
    description = `目标巡检已跑通，但稳定性基线还不够；当前已有 ${consistencyRunCount}/3 次结果，建议连续跑三次一致性。`;
    badge = "待建基线";
    tagType = "warning";
    primaryActions.push({
      key: "consistency",
      label: "跑三次一致性",
      type: "warning",
      plain: false,
    });
    primaryActions.push({
      key: "evidence",
      label: "抽查截图证据",
      type: "primary",
    });
  } else if (!hasAI) {
    title = "本轮结果可进入分析";
    description =
      "没有明显阻塞项，可以触发 AI 分析，让它总结覆盖缺口、下一轮目标和语义元素建议。";
    badge = "可分析";
    tagType = "success";
    primaryActions.push({
      key: "ai",
      label: "生成 AI 分析",
      type: "success",
      plain: false,
    });
    primaryActions.push({
      key: "page_map",
      label: "看页面地图",
      type: "primary",
    });
  } else {
    title = aiNextRoundReadiness.value.ready
      ? "可以进入下一轮受控巡检"
      : "本轮可以沉淀资产";
    description = aiNextRoundReadiness.value.ready
      ? "报告、证据和 AI 分析都已经具备；建议先生成下一轮巡检草稿，人工确认后再执行。"
      : "报告、证据和 AI 分析都已经具备，可以考虑转用例草稿，或基于页面地图扩下一轮目标巡检。";
    badge = "可沉淀";
    tagType = "success";
    if (aiNextRoundReadiness.value.ready) {
      primaryActions.push({
        key: "next_round",
        label: "生成下一轮巡检草稿",
        type: "success",
        plain: false,
      });
    }
    primaryActions.push({
      key: "convert",
      label: "转用例草稿",
      type: "success",
      plain: Boolean(aiNextRoundReadiness.value.ready),
    });
    primaryActions.push({
      key: "page_map",
      label: "扩展页面地图",
      type: "primary",
    });
  }

  const steps = [
    {
      title: "先判定本轮是否有效",
      desc: hasFailed
        ? "当前执行异常，优先排障后重跑。"
        : "执行已完成，可以进入结果处理。",
      active: hasFailed,
    },
    {
      title: "复核问题和证据",
      desc: hasIssues
        ? `还有 ${actionableIssueList.value.length} 个疑似问题需要处理。`
        : "暂无待复核疑似问题。",
      active: hasIssues,
    },
    {
      title: "治理页面地图/语义库",
      desc: hasPageAssets
        ? "本轮已有页面资产，可去页面地图合并重复页、补控件命名。"
        : "本轮页面资产较少，建议先确认执行入口和设备状态。",
      active: hasTargets ? hasTargetGaps : hasPageAssets,
    },
    {
      title: "决定下一轮动作",
      desc: needsConsistencyBaseline
        ? `还差 ${Math.max(3 - consistencyRunCount, 0)} 次一致性基线。`
        : hasAI
          ? "已有 AI 分析，可转用例或创建下一轮巡检。"
          : "结果基本可用后再触发 AI 分析。",
      active: !hasFailed && !hasIssues && !hasTargetGaps,
    },
  ];

  return { title, description, badge, tagType, primaryActions, steps };
});

const roadmapStatusText = (status) =>
  ({
    done: "已完成",
    active: "推进中",
    blocked: "待处理",
    todo: "待开始",
  })[status] || "待确认";

const roadmapStatusTagType = (status) =>
  ({
    done: "success",
    active: "primary",
    blocked: "warning",
    todo: "info",
  })[status] || "info";

const roadmapStageProgress = (items = []) => {
  if (!items.length) return 0;
  const score = items.reduce((sum, item) => {
    if (item.status === "done") return sum + 1;
    if (item.status === "active") return sum + 0.55;
    if (item.status === "blocked") return sum + 0.25;
    return sum;
  }, 0);
  return Math.round((score / items.length) * 100);
};

const roadmapStageLevel = (items = []) => {
  if (items.some((item) => item.status === "blocked")) return "warning";
  if (items.every((item) => item.status === "done")) return "success";
  if (items.some((item) => item.status === "active")) return "active";
  return "info";
};

const roadmapStageGroups = computed(() => {
  const task = currentTask.value || {};
  const status = String(task.status || "").toLowerCase();
  const finished = ["completed", "stopped"].includes(status);
  const stepCount = Number(
    task.total_steps || conversionSummary.value?.total_steps || 0,
  );
  const pageCount = Number(
    task.explored_pages || pageCoverage.value?.page_count || 0,
  );
  const hasEvidence = stepCount > 0 && pageCount > 0;
  const hasActionableIssues = actionableIssueList.value.length > 0;
  const hasAcceptance = Boolean(targetAcceptanceSummary.value.available);
  const acceptancePassed =
    hasAcceptance && !failedTargetAcceptanceItems.value.length;
  const hasPageAssets = pageMapAssetVisible.value || pageMap.value.length > 0;
  const hasSemanticCandidates = Number(pageMapAssetElementCount.value || 0) > 0;
  const hasAIPlan = Boolean(
    (aiNextRoundDraft.value?.targets || []).length ||
    (aiAnalysis.value?.next_exploration_targets || []).length,
  );
  const hasCaseDraftSource =
    Number(conversionSummary.value?.high_confidence_steps || 0) > 0;

  const shortItems = [
    {
      key: "baseline",
      title: "目标巡检稳定基线",
      desc: acceptancePassed
        ? "最近执行的识别率、一致性、证据完整性和护栏指标已达标。"
        : hasAcceptance
          ? `${failedTargetAcceptanceItems.value.length} 个验收指标未达标，先看证据和失败项。`
          : "需要同一目标巡检任务连续执行三次，形成稳定性基线。",
      status: acceptancePassed ? "done" : hasAcceptance ? "blocked" : "todo",
      action: acceptancePassed ? "" : "evidence",
    },
    {
      key: "review",
      title: "问题复核闭环",
      desc: hasActionableIssues
        ? `还有 ${actionableIssueList.value.length} 个疑似问题待复核。`
        : finished
          ? "疑似问题已处理或本轮暂无待复核项。"
          : "任务完成后再复核疑似问题。",
      status: hasActionableIssues ? "blocked" : finished ? "done" : "todo",
      action: hasActionableIssues ? "issues" : "",
    },
    {
      key: "evidence",
      title: "证据链可读",
      desc: hasEvidence
        ? "步骤、页面、截图证据已生成，可按步骤打开定位。"
        : "还缺少可阅读的步骤/页面证据。",
      status: hasEvidence ? "done" : finished ? "blocked" : "todo",
      action: hasEvidence ? "evidence" : "steps",
    },
    {
      key: "diagnosis",
      title: "失败可诊断",
      desc: task.logcat?.available
        ? `已采集 ${task.logcat.file_count || 0} 个 logcat 附件。`
        : "建议执行时采集 logcat，崩溃或卡住时可直接交给开发排查。",
      status: task.logcat?.available ? "done" : finished ? "active" : "todo",
      action: "logs",
    },
  ];

  const midItems = [
    {
      key: "page_map",
      title: "页面地图资产",
      desc: hasPageAssets
        ? `已沉淀 ${pageMapAssetNodes.value.length || pageMapAssetStats.value.page_nodes_total || pageMap.value.length || 0} 个页面节点。`
        : "需要通过目标巡检沉淀页面节点、控件和跳转关系。",
      status: hasPageAssets ? "done" : finished ? "blocked" : "todo",
      action: "page_map",
    },
    {
      key: "semantic_candidates",
      title: "语义候选沉淀",
      desc: hasSemanticCandidates
        ? `已有 ${pageMapAssetElementCount.value} 个控件候选可治理。`
        : "下一步从页面地图批量治理语义候选，人工只确认业务名称和角色。",
      status: hasSemanticCandidates
        ? "active"
        : hasPageAssets
          ? "active"
          : "todo",
      action: "page_map",
    },
    {
      key: "ai_plan",
      title: "AI 下一轮计划",
      desc: hasAIPlan
        ? "AI 已给出下一轮目标或草稿，保存前仍需人工确认。"
        : "报告稳定后触发 AI 分析，生成下一轮受控巡检目标。",
      status: hasAIPlan
        ? "done"
        : finished && !hasActionableIssues
          ? "active"
          : "todo",
      action: hasAIPlan ? "ai" : "ai",
    },
    {
      key: "case_draft",
      title: "稳定路径转用例",
      desc: hasCaseDraftSource
        ? `已有 ${conversionSummary.value.high_confidence_steps || 0} 个高可信步骤可转草稿。`
        : "等稳定路径足够可信后，再转自动化用例草稿。",
      status: hasCaseDraftSource ? "active" : "todo",
      action: hasCaseDraftSource ? "convert" : "",
    },
  ];

  return [
    {
      key: "short",
      title: "短期目标：稳定可用",
      description: "先保证执行可重复、结果可信、失败可解释。",
      items: shortItems,
      progress: roadmapStageProgress(shortItems),
      level: roadmapStageLevel(shortItems),
    },
    {
      key: "middle",
      title: "中期目标：资产闭环",
      description: "把巡检结果沉淀为页面地图、语义候选和下一轮计划。",
      items: midItems,
      progress: roadmapStageProgress(midItems),
      level: roadmapStageLevel(midItems),
    },
  ];
});

const reportPriorityItems = computed(() => {
  const items = [];
  failedTargetAcceptanceItems.value.slice(0, 3).forEach((item) => {
    items.push({
      key: `acceptance-${item.key}`,
      level: ["off_list_action_count", "risk_auto_action_count"].includes(
        item.key,
      )
        ? "high"
        : "medium",
      tagType: ["off_list_action_count", "risk_auto_action_count"].includes(
        item.key,
      )
        ? "danger"
        : "warning",
      badge: "巡检验收",
      title: `${item.label}未达标`,
      description: `当前 ${item.actual}，预期 ${item.expected}。`,
      suggestion:
        item.suggestion ||
        "建议先查看页面证据和执行步骤，再调整目标清单或定位规则。",
      detailRows: [
        { label: "点了哪里", value: "这是巡检汇总指标，不对应单一步骤。" },
        { label: "预期", value: item.expected },
        { label: "实际", value: item.actual },
        {
          label: "处理",
          value:
            item.suggestion || "先进入对应证据或步骤，定位是哪类指标未达标。",
        },
      ],
      action: ["off_list_action_count", "risk_auto_action_count"].includes(
        item.key,
      )
        ? "steps"
        : "evidence",
      actionLabel: ["off_list_action_count", "risk_auto_action_count"].includes(
        item.key,
      )
        ? "看步骤"
        : "看证据",
    });
  });

  actionableIssueList.value.slice(0, 3).forEach((issue) => {
    const attribution = issueAttribution(issue);
    const resolution = issueReviewResolution(issue);
    items.push({
      key: `issue-${issue.step_index}-${issue.issue_type}`,
      level: "high",
      tagType: "danger",
      badge: "疑似问题",
      attribution,
      reviewType: "issue",
      issue,
      reviewLabel: resolution ? targetReviewText(resolution) : "",
      reviewTagType: resolution ? targetReviewTagType(resolution) : "info",
      title: `第 ${issue.step_index || "-"} 步：${issueTypeText(issue.issue_type)}`,
      description: displayText(
        issue.issue_message,
        "需要结合截图和日志确认是否为真实缺陷。",
      ),
      suggestion:
        "点“看证据”确认截图点击位置、实际页面和日志；确认后再归档或提交缺陷。",
      detailRows: buildPriorityEvidenceRows(issue.step_index, {
        actual: displayText(
          issue.issue_message,
          "需要结合截图和日志确认是否为真实缺陷。",
        ),
        advice:
          "确认高亮区域是否是预期控件；如果业务正常就归档为正常行为/规则例外，否则提交缺陷。",
      }),
      action: "evidence",
      actionLabel: "看截图定位",
      stepIndex: issue.step_index,
    });
  });

  targetInspectionResults.value
    .filter(
      (item) =>
        !item.is_review_suppressed &&
        [
          "not_found",
          "found_unconfirmed",
          "anchor_recovery_failed",
          "error",
        ].includes(item.status),
    )
    .slice(0, 3)
    .forEach((item) => {
      const attribution = targetAttribution(item);
      items.push({
        key: `target-${item.step_index}-${item.target_name}-${item.status}`,
        level: item.status === "found_unconfirmed" ? "medium" : "high",
        tagType: item.status === "found_unconfirmed" ? "warning" : "danger",
        badge: "目标巡检",
        attribution,
        title:
          item.status === "not_found"
            ? `没找到目标：${item.target_name || "-"}`
            : `${item.target_name || "-"}：${targetInspectionStatusText(item.status)}`,
        description:
          item.error_message ||
          "建议查看页面证据，确认目标是否在当前页面、是否需要补语义或调整起始入口。",
        suggestion:
          item.status === "not_found"
            ? "如果截图上有这个入口，就补语义或改目标名；如果本页没有，就调整巡检起点或入口清单。"
            : "确认点击后业务状态是否符合预期；正常状态变化可归档为规则例外。",
        detailRows: buildPriorityEvidenceRows(item.step_index, {
          expected:
            item.status === "not_found"
              ? `在当前页面或有限滑动范围内找到「${item.target_name || "目标控件"}」。`
              : `点击「${item.target_name || "目标控件"}」后业务状态可确认。`,
          actual: item.error_message || targetInspectionStatusText(item.status),
          advice:
            item.status === "not_found"
              ? "如果截图中能看到目标，补语义或改目标名；如果看不到，调整起始页/入口清单。"
              : "如果是开关、Tab、选中态变化，建议归档为正常行为或补状态断言。",
        }),
        action: "evidence",
        actionLabel: "看截图定位",
        stepIndex: item.step_index,
      });
    });

  conversionNeedsReview.value.slice(0, 3).forEach((item) => {
    items.push({
      key: `conversion-${item.step_index}-${item.reason}`,
      level: "medium",
      tagType: "warning",
      badge: "转用例",
      title: conversionReviewTitle(item),
      description: conversionReviewPlainReason(item),
      suggestion: conversionReviewNextAction(item).replace(/^建议：/, ""),
      detailRows: buildPriorityEvidenceRows(item.step_index, {
        actual: conversionReviewPlainReason(item),
        advice: conversionReviewNextAction(item).replace(/^建议：/, ""),
      }),
      action: "conversion",
      actionLabel: "展开复核",
      filter: conversionReviewReasonType(item),
      stepIndex: item.step_index,
    });
  });

  return items.slice(0, 6);
});

const visibleReportPriorityItems = computed(() => {
  return showAllPriorityItems.value
    ? reportPriorityItems.value
    : reportPriorityItems.value.slice(0, 2);
});

const hiddenPriorityItemCount = computed(() => {
  if (showAllPriorityItems.value) return 0;
  return Math.max(
    reportPriorityItems.value.length - visibleReportPriorityItems.value.length,
    0,
  );
});

const reportWorkbenchLevel = computed(() => {
  if (reportPriorityItems.value.some((item) => item.level === "high")) {
    return {
      type: "danger",
      label: `${reportPriorityItems.value.length} 项待处理`,
    };
  }
  if (reportPriorityItems.value.length) {
    return {
      type: "warning",
      label: `${reportPriorityItems.value.length} 项需确认`,
    };
  }
  return { type: "success", label: "暂无阻塞项" };
});

const reportMoreActions = computed(() => {
  const currentActionKeys = new Set(
    (postRunGuide.value?.primaryActions || []).map((item) => item.key),
  );
  const actionItems = [
    {
      key: "toggle_details",
      label: showReportDetails.value ? "收起高级详情" : "展开高级详情",
      disabled: false,
    },
    {
      key: "export",
      label: "导出报告摘要",
      disabled: !currentTask.value,
    },
    {
      key: "copy",
      label: "复制报告摘要",
      disabled: !currentTask.value,
    },
    {
      key: "copy_defect",
      label: "复制缺陷证据包",
      disabled: !canCopyDefectDraft.value,
    },
    {
      key: "copy_brief",
      label: "复制任务简报",
      disabled: !currentTask.value,
    },
    {
      key: "convert",
      label: "转为用例草稿",
      disabled:
        !insights.value?.can_convert_to_case ||
        currentTask.value?.status === "running",
    },
    {
      key: "ai",
      label: aiAnalysisButtonText.value,
      disabled:
        !currentTask.value ||
        currentTask.value?.status === "running" ||
        aiAnalysisInProgress.value,
    },
  ];
  return actionItems.filter((item) => !currentActionKeys.has(item.key));
});

function handleReportMoreAction(action) {
  if (action === "toggle_details") {
    showReportDetails.value = !showReportDetails.value;
    return;
  }
  if (action === "export") {
    exportExplorationSummary();
    return;
  }
  if (action === "copy") {
    copyExplorationSummary();
    return;
  }
  if (action === "copy_defect") {
    copyDefectDraft();
    return;
  }
  if (action === "copy_brief") {
    copyTaskBrief();
    return;
  }
  handlePostRunAction(action);
}

function handlePriorityItemAction(item) {
  if (item.action === "evidence" && item.stepIndex) {
    focusReviewEvidence(item.stepIndex);
    return;
  }
  if (item.action === "conversion") {
    showReportDetails.value = true;
    showConversionReview(item.filter || "all");
    reportActiveTab.value = "overview";
    return;
  }
  if (item.action === "steps") {
    reportActiveTab.value = "steps";
    return;
  }
  if (item.action === "logs") {
    reportActiveTab.value = "logs";
  }
}

function reviewPriorityItem(item, resolution) {
  if (item.reviewType === "issue" && item.issue) {
    reviewIssue(item.issue, resolution);
    return;
  }
  if (item.reviewType === "target" && item.targetResult) {
    reviewTargetResult(item.targetResult, resolution);
  }
}

const isPriorityExpanded = (key) => Boolean(expandedPriorityItems.value?.[key]);

const togglePriorityEvidence = (key) => {
  if (!key) return;
  expandedPriorityItems.value = {
    ...expandedPriorityItems.value,
    [key]: !expandedPriorityItems.value?.[key],
  };
};

const focusIssueReviewPanel = async () => {
  reportActiveTab.value = "overview";
  showReportDetails.value = true;
  await nextTick();
  document
    .getElementById("exploration-issue-review-card")
    ?.scrollIntoView({ behavior: "smooth", block: "start" });
};

function handlePostRunAction(action) {
  if (action === "refresh") {
    loadTasks();
    return;
  }
  if (action === "issues") {
    focusIssueReviewPanel();
    return;
  }
  if (action === "steps") {
    reportActiveTab.value = "steps";
    return;
  }
  if (action === "evidence") {
    reportActiveTab.value = "evidence";
    return;
  }
  if (action === "logs") {
    reportActiveTab.value = "logs";
    return;
  }
  if (action === "risk") {
    reportActiveTab.value = "risk";
    return;
  }
  if (action === "device_health") {
    checkTaskDevice(currentTask.value);
    return;
  }
  if (action === "consistency") {
    if (currentTask.value) {
      runConsistency(currentTask.value);
    }
    return;
  }
  if (action === "next_round") {
    if (!aiNextRoundReadiness.value.ready) {
      ElMessage.warning(
        aiNextRoundReadiness.value.blocker || "当前还不能生成下一轮巡检草稿",
      );
      return;
    }
    createTaskDraftFromAIAnalysis();
    return;
  }
  if (action === "stop_current") {
    if (currentTask.value?.id) {
      stopTask(currentTask.value);
    }
    return;
  }
  if (action === "page_map") {
    router.push("/app-automation/page-map");
    return;
  }
  if (action === "ai") {
    reportActiveTab.value = "ai";
    if (!aiAnalysisInProgress.value && !aiAnalysis.value?.status) {
      runAIAnalysis();
    }
    return;
  }
  if (action === "convert") {
    convertToCaseDraft();
  }
}
const aiAnalysisStepActive = computed(() => {
  const stage = aiAnalysisProgressStage.value;
  if (
    stage.includes("解析") ||
    stage.includes("保存") ||
    stage.includes("完成")
  )
    return 3;
  if (stage.includes("模型") || stage.includes("请求")) return 2;
  if (stage.includes("报告") || stage.includes("上下文")) return 1;
  return 0;
});
const aiAnalysisButtonText = computed(() => {
  if (aiAnalysisInProgress.value) return "AI 分析中...";
  if (aiAnalysis.value?.status) return "重新分析报告";
  if (aiAnalysisFailed.value) return "重新分析报告";
  return "AI 分析报告";
});
const reportTabTip = computed(
  () =>
    ({
      overview: "默认只看结论、待处理清单和关键证据入口",
      steps: `查看 ${currentTask.value?.steps?.length || 0} 条详细步骤和截图`,
      evidence: "查看页面地图、入口导航和截图证据",
      risk: skippedRisks.value.length
        ? `本次跳过 ${skippedRisks.value.length} 个风险控件`
        : "本次暂无风险跳过记录",
      ai: aiAnalysis.value?.status
        ? "查看 AI 分析、建议动作和分析依据"
        : "当前报告还没有 AI 分析结果",
      logs: currentTask.value?.logcat?.available
        ? "可导出 logcat ZIP 给开发排查"
        : "当前报告暂无 logcat 附件",
    })[reportActiveTab.value] || "",
);
const evidencePreviewTitle = computed(() => {
  if (!evidencePreviewPage.value) return "页面证据大图";
  return `${pageDisplayTitle(evidencePreviewPage.value, evidencePreviewIndex.value)} - 页面证据大图`;
});
const aiPlanTargetKey = (item, index) =>
  `${index}|${item?.page_name || ""}|${item?.target_name || ""}`;
const selectedAIPlanTargets = computed(() => {
  return aiPlanTargets.value.filter((item, index) =>
    selectedAIPlanTargetKeys.value.includes(aiPlanTargetKey(item, index)),
  );
});
const aiNextRoundCandidateTargets = computed(() => {
  const selectedTargets = selectedAIPlanTargets.value
    .map((item) => item.target_name)
    .filter(Boolean);
  if (selectedTargets.length) return selectedTargets;
  const draftTargets = Array.isArray(aiNextRoundDraft.value?.targets)
    ? aiNextRoundDraft.value.targets
        .map((item) => displayText(item, ""))
        .filter(Boolean)
    : [];
  if (draftTargets.length) return draftTargets;
  return Array.isArray(aiAnalysis.value?.next_exploration_targets)
    ? aiAnalysis.value.next_exploration_targets
        .map((item) => displayAIItem(item))
        .filter(Boolean)
    : [];
});
const aiNextRoundReadiness = computed(() => {
  const hasAnalysis = Boolean(
    aiAnalysis.value?.status || aiAnalysis.value?.conclusion,
  );
  const targetCount = aiNextRoundCandidateTargets.value.length;
  const acceptanceFailedCount = failedTargetAcceptanceItems.value.length;
  const pendingIssueCount = actionableIssueList.value.length;
  return buildAINextRoundReadiness({
    hasAnalysis,
    targetCount,
    acceptanceFailedCount,
    pendingIssueCount,
  });
});
const aiActionProposals = computed(() =>
  normalizeAIActionProposals(aiAnalysis.value?.action_proposals),
);
const selectedAIActionProposals = computed(() => {
  return aiActionProposals.value.filter((item, index) =>
    selectedAIActionKeys.value.includes(actionProposalKey(item, index)),
  );
});
const iteration = computed(() => currentTask.value?.iteration || {});
const iterationChain = computed(() =>
  Array.isArray(iteration.value?.chain) ? iteration.value.chain : [],
);
const iterationChainSummary = computed(
  () => iteration.value?.chain_summary || {},
);
const iterationSourceSummary = computed(
  () => iteration.value?.source_summary || {},
);
const iterationAcceptedActions = computed(() => {
  const selected = iterationSourceSummary.value.selected_action_proposals;
  const legacy = iterationSourceSummary.value.action_proposals;
  return normalizeAIActionProposals(
    Array.isArray(selected) ? selected : legacy,
  );
});
const iterationRejectedActionCount = computed(() => {
  const explicitCount = Number(
    iterationSourceSummary.value.rejected_action_count,
  );
  if (Number.isFinite(explicitCount) && explicitCount >= 0)
    return explicitCount;
  const allCount = normalizeAIActionProposals(
    iterationSourceSummary.value.action_proposals,
  ).length;
  return Math.max(allCount - iterationAcceptedActions.value.length, 0);
});
const iterationEffectAssessment = computed(() => {
  if (!iteration.value?.has_source) return {};
  const current = iteration.value?.current_metrics || {};
  const diff = iteration.value?.diff || {};
  const steps = Number(current.total_steps || 0);
  const pages = Number(current.explored_pages || 0);
  const issues = Number(current.issue_count || 0);
  const coverage = Number(current.target_coverage_rate || 0);
  const acceptedCount = iterationAcceptedActions.value.length;
  const status = String(currentTask.value?.status || "").toLowerCase();

  if (status === "pending") {
    return {
      type: "info",
      title: "本轮尚未执行",
      description:
        "这是已生成的探索任务草稿，还没有开始执行。请执行完成后再判断是否跑空或有效。",
    };
  }

  if (["error", "failed"].includes(status)) {
    const failedTarget = extractFailedStartActionTarget(currentTask.value);
    return {
      type: "error",
      title: "本轮执行异常",
      description: failedTarget
        ? `起始导航未找到目标「${failedTarget}」，建议生成修正草稿并移除该动作，或把它改为条件兜底动作。`
        : displayText(
            currentTask.value?.error_message,
            "本轮执行异常，建议优先查看失败原因后再重试。",
          ),
    };
  }

  if (steps <= 0 && pages <= 0) {
    return {
      type: "warning",
      title: "本轮探索未形成有效路径",
      description: acceptedCount
        ? "已采纳 AI 动作，但执行后没有产生有效步骤或页面覆盖。建议检查起始导航是否命中、设备是否停留在正确页面，或减少动作后重新尝试。"
        : "本轮没有采纳 AI 动作，也没有形成有效探索路径。建议补充入口关键词或手动配置起始导航。",
    };
  }

  if (issues > 0) {
    return {
      type: "warning",
      title: "本轮发现疑似问题，建议人工复核",
      description: `本轮发现 ${issues} 个疑似问题。请结合截图、Activity 和 logcat 判断是否为真实缺陷，再决定是否沉淀用例。`,
    };
  }

  if (
    Number(diff.explored_pages || 0) > 0 ||
    Number(diff.target_coverage_rate || 0) > 0 ||
    coverage >= 50
  ) {
    return {
      type: "success",
      title: "本轮探索有增量",
      description:
        "相较上一轮，本轮在页面覆盖或目标覆盖上有提升，可以继续沿这个方向扩展探索目标。",
    };
  }

  return {
    type: "info",
    title: "本轮探索增量有限",
    description:
      "本轮完成了探索，但相较上一轮覆盖提升不明显。建议调整入口关键词、减少无效动作，或换一个更具体的探索目标。",
  };
});
const iterationNextSuggestion = computed(() => {
  if (!iteration.value?.has_source) return {};
  const current = iteration.value?.current_metrics || {};
  const summary = iterationChainSummary.value || {};
  const steps = Number(current.total_steps || 0);
  const pages = Number(current.explored_pages || 0);
  const issues = Number(current.issue_count || 0);
  const ineffectiveAttempts = Number(summary.ineffective_attempts || 0);
  const status = String(currentTask.value?.status || "").toLowerCase();

  if (status === "pending") {
    return {
      type: "info",
      action: "先执行",
      title: "等待执行后再评估",
      description:
        "当前任务只是 AI 生成的下一轮草稿，尚不能判定为跑空。建议先执行，完成后再根据覆盖增量决定是否修正。",
    };
  }

  if (["error", "failed"].includes(status)) {
    const failedTarget = extractFailedStartActionTarget(currentTask.value);
    return {
      type: "warning",
      action: "修正重试",
      title: failedTarget
        ? `移除失败动作「${failedTarget}」`
        : "先修正失败原因",
      description: failedTarget
        ? `本轮起始导航未找到「${failedTarget}」，修正草稿会移除该动作，只保留稳定入口。`
        : "本轮执行异常，建议基于失败原因生成修正草稿后再重试。",
    };
  }

  if (issues > 0) {
    return {
      type: "danger",
      action: "先复核缺陷",
      title: "建议先确认问题真实性",
      description:
        "本轮已经发现疑似问题，优先查看截图、logcat 和复现路径；确认后再决定是否沉淀用例或提交缺陷。",
    };
  }

  if (steps <= 0 && pages <= 0 && ineffectiveAttempts >= 2) {
    return {
      type: "warning",
      action: "停止当前链路",
      title: "建议换入口重新探索",
      description:
        "这条链路已经出现多轮跑空，继续沿用当前入口收益较低。建议回到目标页面、调整入口关键词或重新定义探索目标。",
    };
  }

  if (steps <= 0 && pages <= 0) {
    return {
      type: "warning",
      action: "修正重试",
      title: "建议先生成修正草稿",
      description:
        "本轮没有形成有效路径，适合移除滑动、等待、返回等不稳定起始动作，只保留安全的文字点击后再跑一轮。",
    };
  }

  if (steps >= 5 || pages >= 2) {
    return {
      type: "success",
      action: "可沉淀/继续扩展",
      title: "本轮已有可复用探索路径",
      description:
        "建议先判断路径是否覆盖核心业务。如果是稳定高价值路径，可以转成用例草稿；如果还没覆盖目标，可继续生成下一轮探索。",
    };
  }

  return {
    type: "info",
    action: "继续观察",
    title: "本轮有少量增量",
    description:
      "可以继续探索，但建议收窄目标或补充入口关键词，避免产生过多低价值路径。",
  };
});
const canCreateAdjustedIterationDraft = computed(() => {
  if (!iteration.value?.has_source || !currentTask.value?.id) return false;
  const current = iteration.value?.current_metrics || {};
  const status = String(currentTask.value?.status || "").toLowerCase();
  if (status === "pending" || status === "running") return false;
  return (
    Number(current.total_steps || 0) <= 0 &&
    Number(current.explored_pages || 0) <= 0
  );
});
const iterationMetricCards = computed(() => {
  const current = iteration.value?.current_metrics || {};
  const source = iteration.value?.source_metrics || {};
  const diff = iteration.value?.diff || {};
  return [
    {
      key: "total_steps",
      label: "探索步数",
      current: current.total_steps || 0,
      diffText: formatMetricDiff(diff.total_steps, source.total_steps, "步"),
      diffClass: metricDiffClass(diff.total_steps),
    },
    {
      key: "explored_pages",
      label: "页面数",
      current: current.explored_pages || 0,
      diffText: formatMetricDiff(
        diff.explored_pages,
        source.explored_pages,
        "页",
      ),
      diffClass: metricDiffClass(diff.explored_pages),
    },
    {
      key: "issue_count",
      label: "疑似问题",
      current: current.issue_count || 0,
      diffText: formatMetricDiff(diff.issue_count, source.issue_count, "个"),
      diffClass: metricDiffClass(diff.issue_count, true),
    },
    {
      key: "target_coverage_rate",
      label: "目标覆盖率",
      current: `${current.target_coverage_rate || 0}%`,
      diffText: formatMetricDiff(
        diff.target_coverage_rate,
        source.target_coverage_rate,
        "%",
      ),
      diffClass: metricDiffClass(diff.target_coverage_rate),
    },
  ];
});
const canCopyDefectDraft = computed(() =>
  Boolean(
    currentTask.value?.error_message ||
    actionableIssueList.value.length ||
    ["failed", "error"].includes(
      String(currentTask.value?.status || "").toLowerCase(),
    ) ||
    ["failed", "error"].includes(
      String(currentTask.value?.result || "").toLowerCase(),
    ),
  ),
);
const issueTypeList = computed(() => {
  const counts =
    insights.value?.issue_type_counts ||
    currentTask.value?.summary?.issue_type_counts ||
    {};
  return Object.entries(counts).map(([type, count]) => ({ type, count }));
});

const attributionProfiles = {
  app_bug: {
    label: "APP稳定性",
    owner: "APP开发",
    tagType: "danger",
    severity: 5,
    nextAction: "优先导出日志和截图，按稳定性问题提交开发排查",
  },
  environment: {
    label: "环境/设备",
    owner: "设备或执行环境",
    tagType: "warning",
    severity: 4,
    nextAction: "先检查设备、ADB、网络和后台执行服务，再决定是否重跑",
  },
  locator: {
    label: "元素定位",
    owner: "语义库/页面地图",
    tagType: "warning",
    severity: 3,
    nextAction: "查看截图命中范围，补语义元素或调整目标名称",
  },
  state_assertion: {
    label: "状态断言",
    owner: "断言/规则",
    tagType: "info",
    severity: 2,
    nextAction: "确认是否为开关、Tab、选中态等正常状态变化",
  },
  safety: {
    label: "风险护栏",
    owner: "测试策略",
    tagType: "danger",
    severity: 4,
    nextAction: "确认是否应继续禁止，或从目标清单移除高风险入口",
  },
  data_config: {
    label: "配置/数据",
    owner: "用例配置",
    tagType: "info",
    severity: 2,
    nextAction: "检查目标清单、入口关键词、变量和测试数据是否正确",
  },
  unknown: {
    label: "待判断",
    owner: "人工复核",
    tagType: "info",
    severity: 1,
    nextAction: "结合截图、步骤和日志先做人工复核",
  },
};

const issueAttribution = (issue = {}) => {
  const type = String(issue.issue_type || "").toLowerCase();
  const message =
    `${issue.issue_message || ""} ${issue.error_message || ""}`.toLowerCase();
  let key = "unknown";
  if (
    ["crash", "anr", "blank_or_black_screen", "app_exit"].includes(type) ||
    /crash|anr|fatal|崩溃|无响应|白屏|黑屏|闪退/.test(message)
  ) {
    key = "app_bug";
  } else if (
    ["ui_dump_failed", "system_dialog", "network_error"].includes(type) ||
    /adb|device|offline|unauthorized|timeout|超时|设备|连接|网络|截图失败|ui树/.test(
      message,
    )
  ) {
    key = "environment";
  } else if (
    ["target_not_found"].includes(type) ||
    /not found|selector|resource|bounds|定位|找不到|未找到/.test(message)
  ) {
    key = "locator";
  } else if (
    ["no_response", "target_state_unconfirmed"].includes(type) ||
    /no response|无变化|无响应|状态|断言|未确认/.test(message)
  ) {
    key = "state_assertion";
  } else if (/变量|数据|配置|入口|目标清单/.test(message)) {
    key = "data_config";
  }
  return { key, ...attributionProfiles[key] };
};

const targetAttribution = (item = {}) => {
  const status = String(item.status || "").toLowerCase();
  const message =
    `${item.error_message || ""} ${item.match_reason || ""}`.toLowerCase();
  let key = "unknown";
  if (status === "risk_skipped") key = "safety";
  else if (status === "not_found") key = "locator";
  else if (status === "found_unconfirmed") key = "state_assertion";
  else if (
    ["anchor_recovery_failed", "error"].includes(status) ||
    /adb|device|offline|timeout|恢复失败|执行异常|连接/.test(message)
  )
    key = "environment";
  else if (/配置|入口|目标清单/.test(message)) key = "data_config";
  return { key, ...attributionProfiles[key] };
};

const taskFailureAttribution = (task = currentTask.value || {}) => {
  if (task.execution_health?.is_stale)
    return { key: "environment", ...attributionProfiles.environment };
  const status = String(task.status || "").toLowerCase();
  const result = String(task.result || "").toLowerCase();
  const message = String(task.error_message || "").toLowerCase();
  if (
    !["error", "failed"].includes(status) &&
    !["error", "failed"].includes(result) &&
    !message
  )
    return null;
  if (/crash|anr|fatal|崩溃|闪退|无响应/.test(message))
    return { key: "app_bug", ...attributionProfiles.app_bug };
  if (
    /adb|device|offline|unauthorized|timeout|超时|设备|连接|截图|uiautomator/.test(
      message,
    )
  )
    return { key: "environment", ...attributionProfiles.environment };
  if (/selector|resource|bounds|element|定位|找不到|未找到/.test(message))
    return { key: "locator", ...attributionProfiles.locator };
  if (/assert|断言|预期/.test(message))
    return { key: "state_assertion", ...attributionProfiles.state_assertion };
  return { key: "unknown", ...attributionProfiles.unknown };
};

const reportAttributionItems = computed(() => {
  const bucket = new Map();
  const add = (profile, example) => {
    if (!profile?.key) return;
    if (!bucket.has(profile.key)) {
      bucket.set(profile.key, {
        ...profile,
        count: 0,
        examples: [],
      });
    }
    const item = bucket.get(profile.key);
    item.count += 1;
    const readableExample = displayText(example, "");
    if (
      readableExample &&
      item.examples.length < 3 &&
      !item.examples.includes(readableExample)
    ) {
      item.examples.push(readableExample);
    }
  };

  add(
    taskFailureAttribution(),
    currentTask.value?.error_message ||
      currentTask.value?.execution_health?.message ||
      "任务执行状态",
  );
  actionableIssueList.value.forEach((issue) => {
    add(
      issueAttribution(issue),
      `第 ${issue.step_index || "-"} 步 ${issueTypeText(issue.issue_type)}`,
    );
  });
  targetInspectionResults.value
    .filter(
      (item) =>
        !item.is_review_suppressed &&
        [
          "not_found",
          "found_unconfirmed",
          "risk_skipped",
          "anchor_recovery_failed",
          "error",
        ].includes(item.status),
    )
    .forEach((item) => {
      add(
        targetAttribution(item),
        `${item.target_name || "目标"}：${targetInspectionStatusText(item.status)}`,
      );
    });

  return Array.from(bucket.values())
    .sort((a, b) => b.severity - a.severity || b.count - a.count)
    .slice(0, 4);
});
const unreadableTextPattern = /[\u25a0-\u25a1\ufffd\ue000-\uf8ff]/g;

const displayText = (value, fallback = "-") => {
  const text = String(value || "")
    .replace(unreadableTextPattern, "")
    .replace(/[\u0000-\u0008\u000b\u000c\u000e-\u001f]/g, "")
    .replace(/\s+/g, " ")
    .trim();
  if (!text) return fallback;
  const readable = [...text].some((char) =>
    /[\p{L}\p{N}\u4e00-\u9fff]/u.test(char),
  );
  return readable ? text : fallback;
};

const resourceTail = (value) => {
  const text = String(value || "");
  return text.split("/").pop() || text;
};

const controlNameMap = {
  btnServerList: "服务器列表按钮",
  createNewLayout: "创建入口",
  btnCreateServer: "创建社区按钮",
  btnLogin: "登录按钮",
  btn_login: "登录按钮",
  btnLogout: "退出登录按钮",
  ivBack: "返回按钮",
  ifvBack: "返回按钮",
  ll_search_layout: "搜索区域",
  drawerLayout: "侧边栏区域",
  content: "页面内容区",
};

const friendlyResourceName = (value) => {
  const tail = displayText(resourceTail(value), "");
  if (!tail) return "";
  if (controlNameMap[tail]) return controlNameMap[tail];
  if (/btn/i.test(tail)) return `${tail.replace(/^btn[_-]?/i, "")} 按钮`;
  if (/edit|input|et/i.test(tail)) return `${tail} 输入框`;
  if (/list/i.test(tail)) return `${tail} 列表`;
  if (/layout|container/i.test(tail)) return `${tail} 区域`;
  return tail;
};

const displayStepTarget = (row) => {
  return (
    displayText(row.display_target, "") ||
    displayText(row.target_text, "") ||
    friendlyResourceName(row.target_resource_id) ||
    displayText(row.target_class, "") ||
    "-"
  );
};

const displayStepAction = (row) => {
  const displayAction = displayText(row.display_action, "");
  if (displayAction) return displayAction;
  const action = displayText(row.action_label, "");
  const target = displayStepTarget(row);
  if (row.action_type === "tap" && target !== "-") return `点击 ${target}`;
  if (row.action_type === "swipe") return "滑动页面";
  if (row.action_type === "back") return "返回上一页";
  if (row.action_type === "wait") return "等待页面稳定";
  return action || `探索步骤 ${row.step_index || ""}`;
};

const displayPathAction = (item) => {
  const action = displayText(item.action, "");
  if (action) return action;
  const target = displayText(item.target, "");
  if (item.action_type === "tap" && target) return `点击 ${target}`;
  if (item.action_type === "swipe") return "滑动页面";
  return `探索步骤 ${item.step_index || ""}`;
};

const technicalStepTarget = (row) => {
  if (row.technical_target) return row.technical_target;
  const parts = [];
  if (row.target_resource_id)
    parts.push(`resource-id: ${row.target_resource_id}`);
  if (row.target_text) parts.push(`text: ${row.target_text}`);
  if (row.target_class) parts.push(`class: ${row.target_class}`);
  if (row.bounds) parts.push(`bounds: ${row.bounds}`);
  if (
    row.x !== null &&
    row.x !== undefined &&
    row.y !== null &&
    row.y !== undefined
  )
    parts.push(`坐标: (${row.x}, ${row.y})`);
  return parts.join("；") || "-";
};

const stepByIndex = (stepIndex) => {
  const index = Number(stepIndex);
  if (!Number.isFinite(index)) return null;
  return (
    (currentTask.value?.steps || []).find(
      (item) => Number(item.step_index) === index,
    ) || null
  );
};

const issueByStepIndex = (stepIndex) => {
  const index = Number(stepIndex);
  if (!Number.isFinite(index)) return null;
  return (
    issueList.value.find((item) => Number(item.step_index) === index) || null
  );
};

const targetResultByStepIndex = (stepIndex) => {
  const index = Number(stepIndex);
  if (!Number.isFinite(index)) return null;
  return (
    targetInspectionResults.value.find(
      (item) => Number(item.step_index) === index,
    ) || null
  );
};

const buildPriorityEvidenceRows = (stepIndex, fallback = {}) => {
  const index = Number(stepIndex);
  const step = stepByIndex(index);
  const issue = issueByStepIndex(index);
  const targetResult = targetResultByStepIndex(index);
  const control =
    stepEvidenceOverlayControl(step) || targetResultOverlayControl(index);
  const target =
    targetResult?.target_name ||
    displayStepTarget(step || {}) ||
    fallback.target ||
    "目标控件";
  const rows = [
    {
      label: "点了哪里",
      value: control
        ? evidenceControlPositionText(control)
        : fallback.position ||
          "暂未拿到可绘制点击范围，建议先看截图确认目标位置。",
    },
    {
      label: "预期",
      value:
        fallback.expected ||
        (targetResult?.status === "not_found"
          ? `在当前页面或有限滑动范围内找到「${target}」。`
          : "点击后出现跳转、弹窗、选中态变化，或业务状态可被确认。"),
    },
    {
      label: "实际",
      value:
        fallback.actual ||
        issue?.issue_message ||
        targetResult?.error_message ||
        (step?.changed ? "检测到页面有变化。" : "未检测到明确变化。"),
    },
    {
      label: "处理",
      value:
        fallback.advice ||
        "打开截图证据确认高亮范围，再决定归档、补语义或提交缺陷。",
    },
  ];
  return rows.filter((item) => displayText(item.value, ""));
};

const issueQuickEvidenceRows = (issue = {}) => {
  return buildPriorityEvidenceRows(issue.step_index, {
    actual: displayText(
      issue.issue_message,
      "需要结合截图和日志确认是否为真实缺陷。",
    ),
    advice:
      "先看截图高亮位置，再判断是有效缺陷、正常业务行为，还是需要补状态断言。",
  }).slice(0, 4);
};

const stepReviewSignal = (row = {}) => {
  const issue = issueByStepIndex(row.step_index);
  const targetResult = targetResultByStepIndex(row.step_index);
  if (issue) {
    const resolution = issueReviewResolution(issue);
    return {
      label: resolution
        ? targetReviewText(resolution)
        : issueTypeText(issue.issue_type),
      tagType: resolution
        ? targetReviewTagType(resolution)
        : isIssueArchived(issue)
          ? "success"
          : "warning",
      message: displayText(
        issue.issue_message,
        "需要结合截图和日志确认是否为真实问题。",
      ),
    };
  }
  if (
    targetResult &&
    !targetResult.is_review_suppressed &&
    [
      "not_found",
      "found_unconfirmed",
      "risk_skipped",
      "anchor_recovery_failed",
      "error",
    ].includes(targetResult.status)
  ) {
    return {
      label: targetInspectionStatusText(targetResult.status),
      tagType: targetInspectionStatusTag(targetResult.status),
      message: displayText(
        targetResult.error_message,
        targetResult.status === "found_unconfirmed"
          ? "点击后状态待人工确认。"
          : "目标巡检结果需要复核。",
      ),
    };
  }
  if (row.action_type === "tap" && row.changed === false) {
    return {
      label: "状态待确认",
      tagType: "info",
      message:
        "点击后未检测到明显页面变化，可能是正常状态切换，也可能是点击无效。",
    };
  }
  return null;
};

const stepQuickEvidenceRows = (row = {}) => {
  const signal = stepReviewSignal(row);
  return buildPriorityEvidenceRows(row.step_index, {
    actual:
      signal?.message ||
      (row.changed ? "检测到页面有变化。" : "未检测到明确变化。"),
    advice: signal
      ? "先看截图定位，再判断本步是有效问题、正常行为、需补断言，还是需要维护语义元素。"
      : "如果要沉淀为用例，建议确认截图高亮位置、动作目标和页面变化是否一致。",
  }).slice(0, 4);
};

const conversionReviewTarget = (item = {}) => {
  const step = stepByIndex(item.step_index);
  return (
    displayText(item.target, "") ||
    displayStepTarget(step || {}) ||
    displayText(item.action, "") ||
    "该步骤"
  );
};

const conversionReviewTitle = (item = {}) => {
  const target = conversionReviewTarget(item);
  if (conversionReviewReasonType(item) === "issue")
    return `疑似问题：${target}`;
  if (conversionReviewReasonType(item) === "no_change")
    return `点击后状态待确认：${target}`;
  if (conversionReviewReasonType(item) === "coordinate")
    return `定位不够稳：${target}`;
  if (conversionReviewReasonType(item) === "risk") return `风险步骤：${target}`;
  return displayText(item.action || item.target, "待确认步骤");
};

const conversionReviewPlainReason = (item = {}) => {
  const target = conversionReviewTarget(item);
  const reason = displayText(item.reason, "");
  const reasonType = conversionReviewReasonType(item);
  if (reason.includes("target_not_found") || reasonType === "issue") {
    return `没有在当前页面或有限滑动范围内找到「${target}」。这不等于业务缺陷，优先确认目标是否在本页、命名是否准确、是否需要先返回/切换入口。`;
  }
  if (reasonType === "no_change") {
    return `系统执行了点击，但没有检测到明显页面变化。需要结合截图判断：是正常的开关/选中状态变化，还是点击没有生效。`;
  }
  if (reasonType === "coordinate") {
    return `该步骤依赖坐标或语义信息不足，换设备或 UI 改版后稳定性偏低。建议补充语义元素或调整目标名称。`;
  }
  if (reasonType === "risk") {
    return `该步骤命中风险规则，系统已阻止或降级处理。需要人工确认是否允许自动化继续执行。`;
  }
  return reason || "建议人工结合截图确认该步骤是否应保留。";
};

const conversionReviewNextAction = (item = {}) => {
  const reasonType = conversionReviewReasonType(item);
  if (reasonType === "issue")
    return "建议：点“看截图定位”看当时页面，如果目标确实不存在，就回页面地图补入口/补语义；如果目标在别的页面，就调整巡检起点。";
  if (reasonType === "no_change")
    return "建议：如果这是开关、Tab、选中态变化，可归档为正常行为或补状态断言；如果完全没反应，再作为问题处理。";
  if (reasonType === "coordinate")
    return "建议：优先把该控件入语义库，减少坐标兜底。";
  if (reasonType === "risk")
    return "建议：确认该动作是否允许自动化执行，不允许就保留黑名单。";
  return "建议：先看截图定位，再决定保留、归档或补语义。";
};

const mediaUrl = (path) => {
  if (!path) return "";
  const value = String(path);
  if (/^https?:\/\//.test(value) || value.startsWith("/media/")) return value;
  return `/media/${value.replace(/^media\//, "").replace(/^\/+/, "")}`;
};

const pageDisplayTitle = (page, index) => {
  if (page?.synthetic_step_evidence)
    return `步骤 ${page.first_step || "-"}：截图证据`;
  const title = displayText(page.title, "");
  if (title && title !== "未知页面") return `页面 ${index + 1}：${title}`;
  const activity = displayText(page.activity, "");
  if (activity) return `页面 ${index + 1}：${activity.split(".").pop()}`;
  return `页面 ${index + 1}：未知页面`;
};

const pageIssueKey = (page, index) =>
  page.signature || `${index}-${page.first_step || ""}`;

const visiblePageIssues = (page) => {
  const issues = Array.isArray(page?.issues) ? page.issues : [];
  return issues.filter((issue) => {
    if (ignoredIssueStepSet.value.has(Number(issue?.step_index))) return false;
    if (isIssueArchived(issue)) return false;
    const type = String(issue?.issue_type || "");
    const message = displayText(issue?.issue_message, "");
    // Older exploration reports wrote placeholder crash markers into page_map
    // without log details. Hide those stale markers so the report only flags
    // actionable crash evidence.
    if (type === "crash" && !message) return false;
    return Boolean(type || message);
  });
};

const stepRaw = (row) => row?.raw || {};

const stepDecisionReasons = (row) => {
  const reasons = stepRaw(row).score_reasons;
  if (!Array.isArray(reasons)) return [];
  return reasons.map((item) => displayText(item, "")).filter(Boolean);
};

const stepObjectiveHits = (row) => {
  const hits = stepRaw(row).objective_hits;
  if (!Array.isArray(hits)) return [];
  return hits.map((item) => displayText(item, "")).filter(Boolean);
};

const stepRisk = (row) => stepRaw(row).risk || {};

const stepRiskText = (row) => {
  const risk = stepRisk(row);
  const level = displayText(risk.level, "");
  const keyword = displayText(risk.keyword, "");
  const reason = displayText(risk.reason, "");
  if (!level && !keyword && !reason) return "";
  if (keyword && reason) return `${reason}：${keyword}`;
  return reason || keyword || level;
};

const stepRiskTagType = (row) => {
  const level = String(stepRisk(row).level || "");
  if (level === "forbidden") return "danger";
  if (level === "caution") return "warning";
  return "info";
};

const stepScoreText = (row) => {
  const score = stepRaw(row).candidate_score;
  const value = Number(score);
  return Number.isFinite(value) ? value.toFixed(1) : "-";
};

const hasDecisionInfo = (row) => {
  return (
    stepScoreText(row) !== "-" ||
    stepDecisionReasons(row).length > 0 ||
    stepObjectiveHits(row).length > 0 ||
    Boolean(stepRiskText(row))
  );
};

const stabilityText = (level) =>
  ({
    high: "高可信",
    medium: "需确认",
    low: "低稳定",
  })[level] || "需确认";

const stabilityTagType = (level) => {
  if (level === "high") return "success";
  if (level === "low") return "danger";
  return "warning";
};

const conversionReviewReasonType = (item) => {
  const reason = String(item?.reason || "").toLowerCase();
  const risk = item?.risk || {};
  if (risk.level === "forbidden" || reason.includes("风险")) return "risk";
  if (
    reason.includes("target_not_found") ||
    reason.includes("疑似问题") ||
    reason.includes("问题")
  )
    return "issue";
  if (reason.includes("坐标") || reason.includes("缺少语义"))
    return "coordinate";
  if (
    reason.includes("target_state_unconfirmed") ||
    reason.includes("无明显变化") ||
    reason.includes("无变化")
  )
    return "no_change";
  return "other";
};

const showConversionReview = (filter = "all") => {
  activeConversionReviewFilter.value = filter;
  expandedConversionReview.value = true;
};

const toggleConversionReview = () => {
  if (!expandedConversionReview.value) {
    showConversionReview(activeConversionReviewFilter.value || "all");
  } else {
    expandedConversionReview.value = false;
  }
};

const aiRiskText = (level) =>
  ({
    low: "低风险",
    medium: "中风险",
    high: "高风险",
  })[level] || "待确认";

const aiRiskTagType = (level) => {
  if (level === "high") return "error";
  if (level === "medium") return "warning";
  if (level === "low") return "success";
  return "info";
};

const cleanAIKeywordText = (value) => {
  return String(value || "")
    .trim()
    .replace(/^[在再去到从往]+/, "")
    .replace(/(页面|页|模块|区域|入口)$/, "")
    .replace(/[“”"'`（）()[\]【】<>《》]/g, "")
    .replace(/^[\s,，。；;、：:!?！？]+|[\s,，。；;、：:!?！？]+$/g, "");
};

const isNoiseAIKeyword = (value) => {
  const text = cleanAIKeywordText(value);
  if (/^\d+$/.test(text)) return true;
  if (text.length < 2 || text.length > 8) return true;
  return processKeywordMarkers.some((marker) => text.includes(marker));
};

const isDynamicAITarget = (target) => {
  const text = String(target || "").toLowerCase();
  return dynamicTargetMarkers.some((marker) =>
    text.includes(marker.toLowerCase()),
  );
};

const isStableStartTarget = (target) => {
  const text = cleanAIKeywordText(target);
  if (stableStartTargets.has(text)) return true;
  if (isDynamicAITarget(text) || isNoiseAIKeyword(text)) return false;
  return entryKeywordCandidates.includes(text) && text.length <= 6;
};

const normalizeAIActionProposals = (items) => {
  if (!Array.isArray(items)) return [];
  const allowedTypes = new Set(["tap_text", "swipe", "wait", "back"]);
  const blockedKeywords = new Set(defaultBlacklist);
  return items
    .filter((item) => item && allowedTypes.has(item.action_type || item.type))
    .map((item) => {
      const actionType = item.action_type || item.type;
      const target = cleanAIKeywordText(
        displayText(item.target || item.value, ""),
      );
      const risk = ["low", "medium", "high"].includes(item.risk)
        ? item.risk
        : "medium";
      const hasBlockedTarget =
        target &&
        [...blockedKeywords].some((keyword) => target.includes(keyword));
      const layer = item.layer || item.action_layer || "";
      return {
        action_type: actionType,
        target,
        direction: ["up", "down", "left", "right"].includes(item.direction)
          ? item.direction
          : "up",
        seconds: Number(item.seconds || 1),
        reason: displayText(item.reason, ""),
        risk: hasBlockedTarget ? "high" : risk,
        confidence: Math.min(Math.max(Number(item.confidence || 0), 0), 1),
        layer,
        layer_reason: displayText(
          item.layer_reason || item.rejection_reason,
          "",
        ),
        can_start_navigation: Boolean(item.can_start_navigation),
      };
    })
    .filter((item) => item.action_type !== "tap_text" || item.target)
    .slice(0, 8);
};

const CONDITIONAL_ACTION_KEYWORDS = [
  "取消",
  "关闭",
  "我知道了",
  "稍后",
  "暂不",
  "以后再说",
  "允许",
  "拒绝",
  "确定",
  "确认",
];

const actionHasKeyword = (item, keywords) => {
  const target = String(item?.target || item?.value || "").trim();
  const reason = String(item?.reason || "").trim();
  return keywords.some(
    (keyword) => target.includes(keyword) || reason.includes(keyword),
  );
};

const normalizeRiskText = (value) =>
  String(value || "")
    .trim()
    .toLowerCase()
    .replace(/\s+/g, "");

const assessStartActionRisk = (action, customKeywords = []) => {
  const values = [
    action?.value,
    action?.target,
    action?.text,
    action?.resource_id,
  ]
    .map(normalizeRiskText)
    .filter(Boolean);
  const joined = values.join(" ");
  if (!joined) {
    if (["tap_pos"].includes(action?.type)) {
      return {
        level: "caution",
        reason: "坐标点击缺少语义，建议仅在人工确认截图位置后使用",
      };
    }
    return { level: "low", reason: "低风险动作" };
  }

  const customHit = customKeywords
    .map((item) => String(item || "").trim())
    .filter(Boolean)
    .find((keyword) => joined.includes(normalizeRiskText(keyword)));
  if (customHit) {
    return { level: "forbidden", reason: `命中黑名单「${customHit}」` };
  }

  const forbiddenHit = defaultBlacklist.find((keyword) =>
    joined.includes(normalizeRiskText(keyword)),
  );
  if (forbiddenHit) {
    return { level: "forbidden", reason: `命中禁止风险词「${forbiddenHit}」` };
  }

  const cautionKeywords = [
    "提交",
    "发布",
    "保存",
    "确认",
    "确定",
    "继续",
    "授权",
    "允许",
    "同意",
    "完成",
  ];
  const cautionHit = cautionKeywords.find((keyword) =>
    joined.includes(normalizeRiskText(keyword)),
  );
  if (cautionHit) {
    return { level: "caution", reason: `命中需确认动作「${cautionHit}」` };
  }

  return { level: "low", reason: "低风险动作" };
};

const classifyAIActionProposal = (item) => {
  if (!item || item.risk === "high") return "blocked";
  if (item.layer === "blocked") return "blocked";
  if (item.layer === "conditional_fallback") return "conditional_fallback";
  if (item.layer === "exploration_preference") return "exploration_preference";
  if (item.layer === "start_navigation" && isStableStartTarget(item.target))
    return "start_navigation";
  if (item.action_type !== "tap_text") return "exploration_preference";
  if (actionHasKeyword(item, CONDITIONAL_ACTION_KEYWORDS))
    return "conditional_fallback";
  if (isDynamicAITarget(item.target)) return "exploration_preference";
  return item.risk === "low" && isStableStartTarget(item.target)
    ? "start_navigation"
    : "exploration_preference";
};

const actionLayerText = (layer) =>
  ({
    start_navigation: "起始导航",
    conditional_fallback: "条件兜底",
    exploration_preference: "探索偏好",
    blocked: "禁止动作",
  })[layer] || "探索偏好";

const aiActionGroups = (actions = selectedAIActionProposals.value) => {
  const groups = {
    start_navigation: [],
    conditional_fallback: [],
    exploration_preference: [],
    blocked: [],
  };
  actions.forEach((item) => {
    groups[classifyAIActionProposal(item)].push(item);
  });
  return groups;
};

const actionProposalText = (item) => {
  if (item.action_type === "tap_text") return `点击文字：${item.target}`;
  if (item.action_type === "swipe")
    return `滑动：${directionText(item.direction)}`;
  if (item.action_type === "wait") return `等待：${item.seconds || 1} 秒`;
  if (item.action_type === "back") return "返回上一页";
  return "未知动作";
};

const actionRiskText = (risk) =>
  ({
    low: "低风险",
    medium: "需确认",
    high: "高风险",
  })[risk] || "需确认";

const actionRiskTagType = (risk) => {
  if (risk === "low") return "success";
  if (risk === "high") return "danger";
  return "warning";
};

const planPriorityTagType = (priority) => {
  if (priority === "P0") return "danger";
  if (priority === "P1") return "warning";
  return "info";
};

const recommendedAIPlanTargetKeys = () => {
  return aiPlanTargets.value
    .map((item, index) => ({ item, key: aiPlanTargetKey(item, index) }))
    .filter(({ item }) => item.risk !== "high")
    .map(({ key }) => key);
};

const syncAcceptedAIPlanTargetKeys = () => {
  selectedAIPlanTargetKeys.value = recommendedAIPlanTargetKeys();
};

const acceptRecommendedAIPlanTargets = () => {
  syncAcceptedAIPlanTargetKeys();
  ElMessage.success("已采纳可执行巡检目标");
};

const clearAIPlanTargets = () => {
  selectedAIPlanTargetKeys.value = [];
};

const isAIPlanTargetSelected = (item, index) => {
  return selectedAIPlanTargetKeys.value.includes(aiPlanTargetKey(item, index));
};

const toggleAIPlanTarget = (item, index, checked) => {
  if (item.risk === "high") return;
  const key = aiPlanTargetKey(item, index);
  if (checked) {
    if (!selectedAIPlanTargetKeys.value.includes(key)) {
      selectedAIPlanTargetKeys.value = [...selectedAIPlanTargetKeys.value, key];
    }
    return;
  }
  selectedAIPlanTargetKeys.value = selectedAIPlanTargetKeys.value.filter(
    (itemKey) => itemKey !== key,
  );
};

const actionProposalKey = (item, index) => {
  return [
    index,
    item.action_type || "",
    item.target || "",
    item.direction || "",
    item.seconds || "",
  ].join("|");
};

const recommendedAIActionKeys = () => {
  return aiActionProposals.value
    .map((item, index) => ({ item, key: actionProposalKey(item, index) }))
    .filter(({ item }) => item.risk !== "high")
    .map(({ key }) => key);
};

const syncAcceptedAIActionKeys = () => {
  selectedAIActionKeys.value = recommendedAIActionKeys();
};

const acceptRecommendedAIActionProposals = () => {
  syncAcceptedAIActionKeys();
  ElMessage.success("已采纳低/中风险建议动作");
};

const clearAIActionProposals = () => {
  selectedAIActionKeys.value = [];
};

const parseBulkEntryKeywords = (value) => {
  return String(value || "")
    .split(/[\s,，、;；|/]+/)
    .map((item) => cleanAIKeywordText(item))
    .filter((item) => item && !isNoiseAIKeyword(item));
};

const mergeEntryKeywords = (keywords) => {
  const existing = Array.isArray(form.entry_keywords)
    ? form.entry_keywords
    : [];
  return Array.from(
    new Set([
      ...existing.map((item) => cleanAIKeywordText(item)).filter(Boolean),
      ...keywords,
    ]),
  ).slice(0, 30);
};

const handleEntryKeywordsPaste = (event) => {
  const rawText = event.clipboardData?.getData("text") || "";
  if (!rawText.trim()) return;
  const looksBulkInput = /[\s,，、;；|/]/.test(rawText);
  const keywords = parseBulkEntryKeywords(rawText);
  if (!looksBulkInput && keywords.length <= 1) return;
  event.preventDefault();
  if (!keywords.length) {
    ElMessage.warning("未识别到有效入口关键词");
    return;
  }
  const beforeCount = Array.isArray(form.entry_keywords)
    ? form.entry_keywords.length
    : 0;
  form.entry_keywords = mergeEntryKeywords(keywords);
  const addedCount = Math.max(form.entry_keywords.length - beforeCount, 0);
  ElMessage.success(
    addedCount
      ? `已批量添加 ${addedCount} 个入口关键词`
      : "入口关键词已存在，已自动去重",
  );
};

const isAIActionProposalSelected = (item, index) => {
  return selectedAIActionKeys.value.includes(actionProposalKey(item, index));
};

const toggleAIActionProposal = (item, index, checked) => {
  if (item.risk === "high") return;
  const key = actionProposalKey(item, index);
  if (checked) {
    if (!selectedAIActionKeys.value.includes(key)) {
      selectedAIActionKeys.value = [...selectedAIActionKeys.value, key];
    }
    return;
  }
  selectedAIActionKeys.value = selectedAIActionKeys.value.filter(
    (itemKey) => itemKey !== key,
  );
};

const directionText = (direction) =>
  ({
    up: "向上",
    down: "向下",
    left: "向左",
    right: "向右",
  })[direction] || "向上";

const aiActionsToStartActions = () => {
  return aiActionGroups().start_navigation.map((item) => {
    return { ...defaultStartAction(), type: "tap_text", value: item.target };
  });
};

const extractFailedStartActionTarget = (task = currentTask.value) => {
  const message = String(task?.error_message || "");
  const match = message.match(/未找到起始导航目标[:：]\s*([^，。；;\n\r]+)/);
  return match?.[1]?.trim() || "";
};

const removeFailedTargetActions = (actions, failedTarget) => {
  if (!failedTarget) return actions;
  return actions.filter(
    (item) => String(item?.target || item?.value || "").trim() !== failedTarget,
  );
};

watch(
  aiPlanTargets,
  () => {
    syncAcceptedAIPlanTargetKeys();
  },
  { immediate: true },
);

watch(
  aiActionProposals,
  () => {
    syncAcceptedAIActionKeys();
  },
  { immediate: true },
);

watch(aiAnalysisStatus, (status, previousStatus) => {
  if (!reportVisible.value || status === previousStatus) return;
  if (
    previousStatus &&
    ["queued", "running"].includes(previousStatus) &&
    status === "completed"
  ) {
    ElMessage.success("AI 分析已完成");
  }
  if (
    previousStatus &&
    ["queued", "running"].includes(previousStatus) &&
    status === "failed"
  ) {
    ElMessage.error(aiAnalysisErrorMessage.value);
  }
  updatePolling();
});

const sourceTypeText = (type) =>
  ({
    ai_next_round: "AI 建议生成",
    ai_adjusted_retry: "AI 修正重试",
    manual_derived: "人工衍生",
    copied: "复制生成",
  })[type] || "衍生任务";

const iterationChainNodeType = (node) => {
  const state = String(node?.iteration_state || "").toLowerCase();
  if (state === "pending") return "info";
  if (state === "error") return "danger";
  if (state === "stopped") return "info";
  if (state === "empty_run") return "warning";
  if (node?.is_current) return "primary";
  const status = String(node?.status || "").toLowerCase();
  if (["pending", "running"].includes(status)) return "info";
  if (["error", "failed", "stopped"].includes(status)) return "danger";
  if (Number(node?.metrics?.issue_count || 0) > 0) return "warning";
  return node?.effective ? "success" : "info";
};

const iterationChainNodeLabel = (node) => {
  const state = String(node?.iteration_state || "").toLowerCase();
  if (state === "pending") return "待执行";
  if (state === "error") return "执行异常";
  if (state === "stopped") return "已停止";
  if (state === "empty_run") return "跑空";
  if (state === "effective") return "有效";
  const status = String(node?.status || "").toLowerCase();
  if (status === "pending") return "待执行";
  if (status === "running") return "执行中";
  if (["error", "failed"].includes(status)) return "执行异常";
  if (status === "stopped") return "已停止";
  return node?.effective ? "有效" : "跑空";
};

const formatMetricDiff = (diffValue, sourceValue, unit = "") => {
  const value = Number(diffValue || 0);
  const source = Number(sourceValue || 0);
  const prefix = value > 0 ? "+" : "";
  return `上一轮 ${source}${unit}，本轮 ${prefix}${value}${unit}`;
};

const metricDiffClass = (diffValue, warnWhenPositive = false) => {
  const value = Number(diffValue || 0);
  if (value === 0) return "metric-diff-neutral";
  if (warnWhenPositive && value > 0) return "metric-diff-warning";
  return value > 0 ? "metric-diff-positive" : "metric-diff-muted";
};

const displayAIItem = (item) => {
  if (!item) return "-";
  if (typeof item === "string") return item;
  return displayText(
    item.title || item.reason || item.text || JSON.stringify(item),
    "-",
  );
};

const aiItemKey = (item, index, prefix = "ai") => {
  if (!item || typeof item === "string")
    return `${prefix}-${index}-${item || ""}`;
  return `${prefix}-${item.step_index || "no-step"}-${item.title || item.reason || index}`;
};

const aiItemTitle = (item) => {
  if (!item || typeof item === "string") return displayAIItem(item);
  return displayText(item.title || item.text || item.reason, "AI 分析项");
};

const aiItemReason = (item) => {
  if (!item || typeof item === "string") return "";
  return displayText(
    item.reason ||
      item.evidence ||
      item.review_suggestion ||
      item.suggested_archive_type,
    "",
  );
};

const aiItemEvidence = (item) => {
  if (!item || typeof item !== "object") return null;
  return item.evidence && typeof item.evidence === "object"
    ? item.evidence
    : null;
};

const aiItemStepIndex = (item) => {
  if (!item || typeof item !== "object") return null;
  const explicit = Number(item.step_index);
  if (Number.isFinite(explicit) && explicit > 0) return explicit;
  const evidenceStep = Number(aiItemEvidence(item)?.step_index);
  return Number.isFinite(evidenceStep) && evidenceStep > 0
    ? evidenceStep
    : null;
};

const aiItemEvidenceSummary = (item) => {
  const evidence = aiItemEvidence(item);
  if (!evidence) return "暂无结构化证据";
  const parts = [
    displayText(evidence.action, ""),
    displayText(evidence.target, ""),
    evidence.changed === true
      ? "页面有变化"
      : evidence.changed === false
        ? "页面无明显变化"
        : "",
    displayText(evidence.issue_message || evidence.issue_type, ""),
    displayText(evidence.activity, ""),
  ].filter(Boolean);
  return parts.slice(0, 4).join(" · ") || "已关联步骤证据";
};

const focusAIEvidence = (item) => {
  const stepIndex = aiItemStepIndex(item);
  if (!stepIndex) {
    ElMessage.info("该 AI 分析项暂未关联到具体步骤");
    return;
  }
  focusReviewEvidence(stepIndex);
};

const aiTargetTexts = () => {
  return (aiAnalysis.value?.next_exploration_targets || [])
    .map((item) => displayAIItem(item))
    .map((item) => displayText(item, ""))
    .filter(Boolean);
};

const autoExplorationTargetTexts = () => {
  return aiTargetTexts().filter(
    (item) => !processKeywordMarkers.some((marker) => item.includes(marker)),
  );
};

const deriveEntryKeywordsFromTargets = (targets) => {
  const modelKeywords = Array.isArray(
    aiAnalysis.value?.entry_keyword_candidates,
  )
    ? aiAnalysis.value.entry_keyword_candidates
    : [];
  const text = targets.join(" ");
  const keywords = new Set();
  const addKeyword = (value) => {
    const keyword = cleanAIKeywordText(value);
    if (!keyword || isNoiseAIKeyword(keyword)) return;
    keywords.add(keyword);
  };

  modelKeywords.forEach(addKeyword);
  entryKeywordCandidates.forEach((keyword) => {
    if (text.includes(keyword)) keywords.add(keyword);
  });
  targets.forEach((target) => {
    const cleaned = String(target || "")
      .replace(/[，。；;,.、/|｜：:!?！？]/g, " ")
      .split(/\s+/)
      .map(cleanAIKeywordText)
      .filter((item) => item && !isNoiseAIKeyword(item));
    cleaned.slice(0, 2).forEach(addKeyword);
  });
  return Array.from(keywords).slice(0, 8);
};

const baseExplorationTaskName = (task) => {
  const firstChainName = iteration.value?.chain?.[0]?.name;
  const rawName = firstChainName || task?.name || "";
  return (
    String(rawName)
      .replace(/^\[AI-\d+\]\s*/, "")
      .replace(/^AI建议探索\s*-\s*/g, "")
      .replace(/^修正探索\s*-\s*/g, "")
      .replace(/\s*-\s*AI 第 \d+ 轮$/g, "")
      .trim() || "探索任务"
  );
};

const nextExplorationRound = () => {
  const currentRound = Number(
    iteration.value?.chain_summary?.current_round ||
      iteration.value?.chain?.length ||
      1,
  );
  return Math.max(currentRound + 1, 2);
};

const stepRowClassName = ({ row }) => {
  return Number(row?.step_index) === Number(highlightedStepIndex.value)
    ? "review-step-highlight"
    : "";
};

const focusReviewStep = async (stepIndex) => {
  const index = Number(stepIndex);
  if (!Number.isFinite(index)) return;
  reportActiveTab.value = "steps";
  highlightedStepIndex.value = index;
  expandedConversionReview.value = true;
  await nextTick();

  const row = (currentTask.value?.steps || []).find(
    (item) => Number(item.step_index) === index,
  );
  if (row && stepTableRef.value?.toggleRowExpansion) {
    stepTableRef.value.toggleRowExpansion(row, true);
  }

  document
    .getElementById("exploration-step-table-card")
    ?.scrollIntoView({ behavior: "smooth", block: "start" });

  window.setTimeout(() => {
    if (Number(highlightedStepIndex.value) === index) {
      highlightedStepIndex.value = null;
    }
  }, 4500);
};

const pageContainsStep = (page, stepIndex) => {
  const index = Number(stepIndex);
  if (!Number.isFinite(index)) return false;
  if (pageHasExactStep(page, index)) return true;
  const firstStep = Number(page?.first_step || 0);
  const stepCount = Number(page?.step_count || 0);
  return (
    firstStep > 0 &&
    stepCount > 0 &&
    index >= firstStep &&
    index < firstStep + stepCount
  );
};

const pageHasExactStep = (page, stepIndex) => {
  const index = Number(stepIndex);
  if (!Number.isFinite(index)) return false;
  const controls = Array.isArray(page?.clicked_controls)
    ? page.clicked_controls
    : [];
  if (controls.some((control) => Number(control.step_index) === index))
    return true;
  const issues = Array.isArray(page?.issues) ? page.issues : [];
  return issues.some((issue) => Number(issue.step_index) === index);
};

const evidencePageDomId = (page, index) => {
  const key = String(pageIssueKey(page, index) || index).replace(
    /[^a-zA-Z0-9_-]/g,
    "-",
  );
  return `exploration-page-evidence-${key}`;
};

const findEvidencePageIndexByStep = (stepIndex) => {
  const exactIndex = pageMap.value.findIndex((page) =>
    pageHasExactStep(page, stepIndex),
  );
  if (exactIndex >= 0) return exactIndex;
  return pageMap.value.findIndex((page) => pageContainsStep(page, stepIndex));
};

const isEvidencePageHighlighted = (page, index) => {
  if (!highlightedEvidenceStepIndex.value) return false;
  return (
    Number(index) ===
    findEvidencePageIndexByStep(highlightedEvidenceStepIndex.value)
  );
};

const parseControlBounds = (control) => {
  const match = String(control?.bounds || "").match(
    /\[(\d+),(\d+)\]\[(\d+),(\d+)\]/,
  );
  if (!match) return null;
  const [, x1, y1, x2, y2] = match.map(Number);
  if (![x1, y1, x2, y2].every(Number.isFinite)) return null;
  if (x2 <= x1 || y2 <= y1) return null;
  return { x1, y1, x2, y2 };
};

const pageScreenSize = (page) => {
  const rawSize = page?.screen_size;
  if (Array.isArray(rawSize) && rawSize.length >= 2) {
    const width = Number(rawSize[0]);
    const height = Number(rawSize[1]);
    if (width > 0 && height > 0) return { width, height };
  }
  if (rawSize && typeof rawSize === "object") {
    const width = Number(rawSize.width);
    const height = Number(rawSize.height);
    if (width > 0 && height > 0) return { width, height };
  }

  const boundsList = (page?.clicked_controls || [])
    .map(parseControlBounds)
    .filter(Boolean);
  const maxX = Math.max(0, ...boundsList.map((item) => item.x2));
  const maxY = Math.max(0, ...boundsList.map((item) => item.y2));
  return {
    width: maxX > 0 ? Math.max(maxX, 1080) : 1080,
    height: maxY > 0 ? Math.max(maxY, 2400) : 2400,
  };
};

const pageShotStyle = (page) => {
  const { width, height } = pageScreenSize(page);
  return {
    aspectRatio: `${width} / ${height}`,
  };
};

const stepEvidenceScreenshot = (step) => {
  return (
    step?.annotated_screenshot_url ||
    step?.screenshot_url ||
    step?.after_screenshot_url ||
    step?.before_screenshot_url ||
    ""
  );
};

const stepEvidenceOverlayControl = (step) => {
  if (!step) return null;
  return {
    step_index: step.step_index,
    action: displayStepAction(step),
    text: displayStepTarget(step),
    resource_id: step.target_resource_id || step.resource_id || "",
    class_name: step.target_class || step.class_name || "",
    bounds: step.bounds || step.target_bounds || "",
    x: step.x ?? step.tap_x ?? step.target_x,
    y: step.y ?? step.tap_y ?? step.target_y,
    raw: {
      ...(step.raw || {}),
      start: step.start || step.swipe_start || step.raw?.start,
      end: step.end || step.swipe_end || step.raw?.end,
      source: "step_fallback_overlay",
    },
  };
};

const buildStepEvidencePage = (step) => {
  const screenshot = stepEvidenceScreenshot(step);
  if (!screenshot) return null;
  const control = stepEvidenceOverlayControl(step);
  return {
    title: `步骤 ${step.step_index || "-"} 证据`,
    activity: step.after_activity || step.before_activity || "",
    package:
      currentTask.value?.package_name ||
      currentTask.value?.app_package_name ||
      "",
    screenshot,
    first_step: step.step_index,
    step_count: 1,
    screen_size: step.screen_size || step.raw?.screen_size || null,
    clicked_controls: control ? [control] : [],
    issues: issueByStepIndex(step.step_index)
      ? [issueByStepIndex(step.step_index)]
      : [],
    synthetic_step_evidence: true,
  };
};

const isSwipeControl = (control) =>
  String(control?.action || "")
    .toLowerCase()
    .includes("swipe") || Boolean(control?.raw?.start && control?.raw?.end);

const targetResultOverlayControl = (stepIndex) => {
  const result = targetResultByStepIndex(stepIndex);
  if (!result) return null;
  if (
    !parseControlBounds(result) &&
    !(Number.isFinite(Number(result.x)) && Number.isFinite(Number(result.y)))
  ) {
    return null;
  }
  return {
    step_index: result.step_index,
    action: `点击 ${result.target_name || "目标控件"}`,
    text: result.target_name || "",
    resource_id:
      result.target_resource_id || result.evidence?.candidate_resource_id || "",
    class_name: result.target_class || result.evidence?.candidate_class || "",
    bounds: result.bounds || "",
    x: result.x,
    y: result.y,
    raw: {
      ...(result.evidence || {}),
      source: "target_result_overlay",
      target_status: result.status,
    },
  };
};

const pageOverlayControls = (page, limit = 16) => {
  const controls = Array.isArray(page?.clicked_controls)
    ? page.clicked_controls
    : [];
  const drawable = controls.filter((control) => {
    if (parseControlBounds(control)) return true;
    return (
      Number.isFinite(Number(control?.x)) && Number.isFinite(Number(control?.y))
    );
  });
  const highlightedIndex = Number(highlightedEvidenceStepIndex.value);
  const fallbackHighlighted = Number.isFinite(highlightedIndex)
    ? targetResultOverlayControl(highlightedIndex)
    : null;
  const merged =
    fallbackHighlighted &&
    !drawable.some((control) => Number(control.step_index) === highlightedIndex)
      ? [...drawable, fallbackHighlighted]
      : drawable;
  const highlighted = merged.find(
    (control) => Number(control.step_index) === highlightedIndex,
  );
  const limited = merged.slice(0, limit);
  if (
    highlighted &&
    !limited.some(
      (control) =>
        Number(control.step_index) === Number(highlighted.step_index),
    )
  ) {
    return [...limited.slice(0, Math.max(limit - 1, 0)), highlighted];
  }
  return limited;
};

const evidencePreviewControls = computed(() => {
  return evidencePreviewPage.value
    ? pageOverlayControls(evidencePreviewPage.value, 80)
    : [];
});

const evidencePreviewFocusStepIndex = computed(() => {
  const highlighted = Number(highlightedEvidenceStepIndex.value);
  if (Number.isFinite(highlighted) && highlighted > 0) return highlighted;
  const firstIssue = visiblePageIssues(evidencePreviewPage.value || {})[0];
  if (firstIssue?.step_index) return Number(firstIssue.step_index);
  const firstControl = evidencePreviewControls.value[0];
  return firstControl?.step_index ? Number(firstControl.step_index) : null;
});

const evidencePreviewFocusedControl = computed(() => {
  const index = Number(evidencePreviewFocusStepIndex.value);
  if (!Number.isFinite(index)) return null;
  return (
    evidencePreviewControls.value.find(
      (control) => Number(control.step_index) === index,
    ) || null
  );
});

const evidencePreviewFocusedStep = computed(() =>
  stepByIndex(evidencePreviewFocusStepIndex.value),
);
const evidencePreviewFocusedIssue = computed(() =>
  issueByStepIndex(evidencePreviewFocusStepIndex.value),
);
const evidencePreviewFocusedTargetResult = computed(() =>
  targetResultByStepIndex(evidencePreviewFocusStepIndex.value),
);

const evidencePreviewFocusTitle = computed(() => {
  const issue = evidencePreviewFocusedIssue.value;
  const targetResult = evidencePreviewFocusedTargetResult.value;
  if (issue?.issue_type) return issueTypeText(issue.issue_type);
  if (targetResult?.status)
    return targetInspectionStatusText(targetResult.status);
  return "查看本步操作证据";
});

const evidencePreviewFocusAction = computed(() => {
  const step = evidencePreviewFocusedStep.value;
  if (step) return displayStepAction(step);
  const targetResult = evidencePreviewFocusedTargetResult.value;
  if (targetResult?.target_name)
    return `查找并点击「${targetResult.target_name}」`;
  const control = evidencePreviewFocusedControl.value;
  return control ? controlOverlayTitle(control) : "本步没有实际点击动作";
});

const evidenceControlPositionText = (control) => {
  if (!control)
    return "无点击框：通常表示目标未找到、等待页面稳定或本步没有实际点击。";
  const bounds = parseControlBounds(control);
  if (isSwipeControl(control)) return "截图中的箭头方向表示滑动方向。";
  if (bounds) return `截图中高亮框为点击区域，bounds ${control.bounds}`;
  if (
    control.x !== null &&
    control.x !== undefined &&
    control.y !== null &&
    control.y !== undefined
  ) {
    return `截图中高亮点为点击坐标：(${control.x}, ${control.y})`;
  }
  return "该步骤暂无可绘制点击范围。";
};

const evidencePreviewFocusPosition = computed(() =>
  evidenceControlPositionText(evidencePreviewFocusedControl.value),
);

const evidencePreviewFocusExpected = computed(() => {
  const targetResult = evidencePreviewFocusedTargetResult.value;
  const step = evidencePreviewFocusedStep.value;
  const target = targetResult?.target_name || displayStepTarget(step || {});
  if (targetResult?.status === "not_found")
    return `预期在当前页面或有限滑动范围内找到「${target}」并点击。`;
  if (step?.action_type === "tap")
    return "预期点击后出现页面跳转、弹窗、选中态变化，或业务状态能被确认。";
  if (step?.action_type === "swipe")
    return "预期页面列表按箭头方向滚动，并出现新的内容或目标控件。";
  if (step?.action_type === "wait")
    return "预期页面加载完成，目标控件进入可识别状态。";
  return "预期本步能推进探索流程，或形成可解释的页面状态变化。";
});

const evidencePreviewFocusActual = computed(() => {
  const issue = evidencePreviewFocusedIssue.value;
  const targetResult = evidencePreviewFocusedTargetResult.value;
  const step = evidencePreviewFocusedStep.value;
  return displayText(
    issue?.issue_message || targetResult?.error_message || step?.issue_message,
    step?.changed ? "检测到页面有变化" : "未检测到明确变化",
  );
});

const evidencePreviewFocusAdvice = computed(() => {
  const issue = evidencePreviewFocusedIssue.value;
  const targetResult = evidencePreviewFocusedTargetResult.value;
  if (
    issue?.issue_type === "target_not_found" ||
    targetResult?.status === "not_found"
  ) {
    return "复核重点：先看截图上是否真的存在目标控件。存在就补语义库/改目标名；不存在就调整起始页、返回策略或巡检目标清单。";
  }
  if (
    issue?.issue_type === "target_state_unconfirmed" ||
    targetResult?.status === "found_unconfirmed"
  ) {
    return "复核重点：确认这是正常状态变化还是点击无效。开关、Tab、选中态建议补断言或归档为规则例外。";
  }
  if (!evidencePreviewFocusedControl.value) {
    return "当前没有可绘制点击框，请结合左侧截图和步骤说明判断是否需要补元素、补入口或降低该步骤可信度。";
  }
  return "复核重点：确认高亮区域是否就是你预期点击的位置，以及点击后的业务结果是否合理。";
});

const openEvidencePreview = (page, index, stepIndex = null) => {
  if (!mediaUrl(page?.screenshot)) return;
  if (stepIndex !== null && stepIndex !== undefined) {
    highlightedEvidenceStepIndex.value = Number(stepIndex);
  }
  evidencePreviewPage.value = page;
  evidencePreviewIndex.value = index;
  evidencePreviewVisible.value = true;
};

const openPageIssueEvidence = (page, pageIndex, issue = {}) => {
  const stepIndex = Number(issue.step_index);
  openEvidencePreview(
    page,
    pageIndex,
    Number.isFinite(stepIndex) && stepIndex > 0 ? stepIndex : null,
  );
};

const canOpenStepEvidence = (row = {}) => {
  const stepIndex = Number(row.step_index);
  if (!Number.isFinite(stepIndex) || stepIndex <= 0) return false;
  if (findEvidencePageIndexByStep(stepIndex) >= 0) return true;
  const step = stepByIndex(stepIndex) || row;
  return Boolean(buildStepEvidencePage(step));
};

const openStepEvidence = (row = {}) => {
  const stepIndex = Number(row.step_index);
  if (!Number.isFinite(stepIndex) || stepIndex <= 0) return;
  highlightedEvidenceStepIndex.value = stepIndex;

  const pageIndex = findEvidencePageIndexByStep(stepIndex);
  if (pageIndex >= 0) {
    openEvidencePreview(pageMap.value[pageIndex], pageIndex, stepIndex);
    return;
  }

  const fallbackPage = buildStepEvidencePage(stepByIndex(stepIndex) || row);
  if (fallbackPage) {
    openEvidencePreview(fallbackPage, 0, stepIndex);
  }
};

const selectEvidencePreviewStep = (stepIndex) => {
  const index = Number(stepIndex);
  if (Number.isFinite(index) && index > 0) {
    highlightedEvidenceStepIndex.value = index;
  }
};

const controlOverlayStyle = (control, page) => {
  const { width, height } = pageScreenSize(page);
  const bounds = parseControlBounds(control);
  const toPercent = (value, total) =>
    `${Math.max(0, Math.min(100, (Number(value) / total) * 100))}%`;

  const start = control?.raw?.start;
  const end = control?.raw?.end;
  if (
    Array.isArray(start) &&
    Array.isArray(end) &&
    start.length >= 2 &&
    end.length >= 2
  ) {
    const sx = Number(start[0]);
    const sy = Number(start[1]);
    const ex = Number(end[0]);
    const ey = Number(end[1]);
    if ([sx, sy, ex, ey].every(Number.isFinite)) {
      const distance = Math.hypot(ex - sx, ey - sy);
      const angle = (Math.atan2(ey - sy, ex - sx) * 180) / Math.PI;
      return {
        left: toPercent(sx, width),
        top: toPercent(sy, height),
        width: `${Math.max(6, (distance / width) * 100)}%`,
        transform: `rotate(${angle}deg)`,
        transformOrigin: "0 50%",
      };
    }
  }

  if (bounds) {
    return {
      left: toPercent(bounds.x1, width),
      top: toPercent(bounds.y1, height),
      width: toPercent(bounds.x2 - bounds.x1, width),
      height: toPercent(bounds.y2 - bounds.y1, height),
    };
  }

  const x = Number(control?.x);
  const y = Number(control?.y);
  if (Number.isFinite(x) && Number.isFinite(y)) {
    return {
      left: toPercent(x, width),
      top: toPercent(y, height),
    };
  }

  return {};
};

const controlOverlayTitle = (control) => {
  const label = displayText(
    control?.text ||
      friendlyResourceName(control?.resource_id) ||
      control?.action,
    "未知控件",
  );
  return `第 ${control?.step_index || "-"} 步：${label}`;
};

const targetInspectionStatusText = (status) =>
  ({
    found_effective: "已命中并生效",
    found_unconfirmed: "已命中待确认",
    not_found: "未找到",
    risk_skipped: "风险跳过",
    anchor_recovery_failed: "锚点恢复失败",
    error: "执行异常",
    pending: "待执行",
  })[status] ||
  status ||
  "未知";

const targetInspectionStatusTag = (status) =>
  ({
    found_effective: "success",
    found_unconfirmed: "warning",
    not_found: "info",
    risk_skipped: "danger",
    anchor_recovery_failed: "danger",
    error: "danger",
    pending: "info",
  })[status] || "info";

const targetReviewText = (resolution) =>
  ({
    valid_issue: "有效问题",
    normal_behavior: "正常行为",
    element_needs_update: "元素需维护",
    target_should_remove: "建议移除",
    wrong_start_page: "起始页不对",
    rule_exception: "规则例外",
    needs_assertion: "需补状态断言",
    ignore: "暂不处理",
    false_positive: "误报",
  })[resolution] ||
  resolution ||
  "未复核";

const targetReviewTagType = (resolution) =>
  ({
    valid_issue: "danger",
    normal_behavior: "success",
    element_needs_update: "warning",
    target_should_remove: "info",
    wrong_start_page: "warning",
    rule_exception: "success",
    needs_assertion: "warning",
    ignore: "info",
    false_positive: "success",
  })[resolution] || "info";

const issueReviewLabel = (issue = {}) => {
  const resolution = issueReviewResolution(issue);
  return resolution ? targetReviewText(resolution) : "";
};

const issueReviewTagType = (issue = {}) => {
  const resolution = issueReviewResolution(issue);
  return resolution ? targetReviewTagType(resolution) : "info";
};

const targetReviewDefaultNote = (resolution) =>
  ({
    valid_issue: "人工复核为有效问题，保留在目标巡检报告中。",
    normal_behavior: "人工复核为正常业务行为；后续同类目标自动归档。",
    element_needs_update: "人工复核为元素定位需维护，建议补充或更新语义元素。",
    target_should_remove:
      "人工复核为低价值或不适合巡检目标，建议从目标清单移除。",
    wrong_start_page: "人工复核为起始页面不正确，建议调整起始导航后重跑。",
    rule_exception: "人工复核为规则例外；后续同类目标自动归档。",
  })[resolution] || "人工复核";

const targetRecoveryStatusText = (status) =>
  ({
    not_needed: "无需恢复",
    not_needed_same_activity: "仍在目标页",
    recovered: "返回键恢复",
    recovered_by_targets: "返回到目标页",
    recovered_by_relaunch: "重启后恢复",
    recovered_by_relaunch_targets: "重启后回到目标页",
    failed: "恢复失败",
  })[status] ||
  status ||
  "-";

const focusReviewEvidence = async (stepIndex) => {
  const index = Number(stepIndex);
  if (!Number.isFinite(index)) return;
  highlightedEvidenceStepIndex.value = index;
  reportActiveTab.value = "evidence";
  await nextTick();

  const pageIndex = findEvidencePageIndexByStep(index);
  if (pageIndex >= 0) {
    const page = pageMap.value[pageIndex];
    if (visiblePageIssues(page).length) {
      expandedPageIssues.value = {
        ...expandedPageIssues.value,
        [pageIssueKey(page, pageIndex)]: true,
      };
    }
    document
      .getElementById(evidencePageDomId(page, pageIndex))
      ?.scrollIntoView({ behavior: "smooth", block: "center" });
    openEvidencePreview(page, pageIndex, index);
  } else {
    const step = stepByIndex(index);
    const fallbackPage = buildStepEvidencePage(step);
    if (fallbackPage) {
      openEvidencePreview(fallbackPage, 0, index);
      ElMessage.info("页面地图中未找到对应页，已打开该步骤截图证据");
    } else {
      ElMessage.info("页面证据中暂未找到对应步骤，且该步骤没有可预览截图");
    }
  }

  window.setTimeout(() => {
    if (
      !evidencePreviewVisible.value &&
      Number(highlightedEvidenceStepIndex.value) === index
    ) {
      highlightedEvidenceStepIndex.value = null;
    }
  }, 6000);
};

const isPageIssuesExpanded = (page, index) => {
  if (!visiblePageIssues(page).length) return false;
  return Boolean(expandedPageIssues.value[pageIssueKey(page, index)]);
};

const togglePageIssues = (page, index) => {
  if (!visiblePageIssues(page).length) return;
  const key = pageIssueKey(page, index);
  expandedPageIssues.value = {
    ...expandedPageIssues.value,
    [key]: !expandedPageIssues.value[key],
  };
};

const issueTypeText = (type) =>
  ({
    app_exit: "离开应用",
    no_response: "无响应",
    ui_dump_failed: "UI树失败",
    crash: "崩溃",
    anr: "ANR",
    network_error: "网络异常",
    system_dialog: "系统弹窗",
    blank_or_black_screen: "白屏/黑屏",
    target_not_found: "目标未找到",
    target_state_unconfirmed: "点击后状态待确认",
    anchor_recovery_failed: "锚点恢复失败",
  })[type] ||
  type ||
  "未知问题";

const stepPreviewImageUrl = (row) => {
  return (
    row?.annotated_screenshot_url ||
    row?.screenshot_url ||
    row?.after_screenshot_url ||
    ""
  );
};

const screenshotPreviewItems = () => {
  const seen = new Set();
  return (currentTask.value?.steps || [])
    .map((step) => ({
      stepIndex: Number(step.step_index),
      url: stepPreviewImageUrl(step),
    }))
    .filter((item) => {
      if (!item.url || seen.has(item.url)) return false;
      seen.add(item.url);
      return true;
    });
};

const screenshotPreviewList = (row) => {
  const items = screenshotPreviewItems();
  const currentUrl = stepPreviewImageUrl(row);
  if (currentUrl && !items.some((item) => item.url === currentUrl)) {
    items.unshift({ stepIndex: Number(row?.step_index), url: currentUrl });
  }
  return items.map((item) => item.url);
};

const screenshotPreviewInitialIndex = (row) => {
  const currentUrl = stepPreviewImageUrl(row);
  if (!currentUrl) return 0;
  const index = screenshotPreviewList(row).findIndex(
    (url) => url === currentUrl,
  );
  return index >= 0 ? index : 0;
};

const defaultStartAction = () => ({
  type: "tap_text",
  value: "",
  x: 0,
  y: 0,
  seconds: 1,
  direction: "up",
});

const normalizeStartActions = (actions) => {
  if (!Array.isArray(actions)) return [];
  return actions
    .filter((item) => item && item.type)
    .map((item) => ({
      ...defaultStartAction(),
      ...item,
    }));
};

const addStartAction = () => {
  form.start_actions.push(defaultStartAction());
};

const removeStartAction = (index) => {
  form.start_actions.splice(index, 1);
};

const normalizeScreenshotContent = (content) => {
  if (!content) return "";
  if (String(content).startsWith("data:image")) return content;
  return `data:image/png;base64,${content}`;
};

const openStartPointPicker = async () => {
  if (!form.device) {
    ElMessage.warning("请先选择执行设备");
    return;
  }
  startShotLoading.value = true;
  try {
    const res = await captureDeviceScreenshot(form.device);
    const data = res.data?.data || res.data || {};
    startPointScreenshot.value = normalizeScreenshotContent(
      data.content || data.screenshot || data.image || "",
    );
    if (!startPointScreenshot.value) {
      ElMessage.warning("未获取到设备截图");
      return;
    }
    startPointPickerVisible.value = true;
  } catch (error) {
    console.error("获取设备截图失败:", error);
    ElMessage.error(error?.response?.data?.detail || "获取设备截图失败");
  } finally {
    startShotLoading.value = false;
  }
};

const pickStartPoint = (event) => {
  const image = startPointImageRef.value;
  if (!image?.naturalWidth || !image?.naturalHeight) {
    ElMessage.warning("截图尚未加载完成，请稍后再点");
    return;
  }
  const rect = image.getBoundingClientRect();
  const localX = event.clientX - rect.left;
  const localY = event.clientY - rect.top;
  const realX = Math.round((localX * image.naturalWidth) / rect.width);
  const realY = Math.round((localY * image.naturalHeight) / rect.height);
  form.start_actions.push({
    ...defaultStartAction(),
    type: "tap_pos",
    x: Math.max(0, realX),
    y: Math.max(0, realY),
  });
  startPointPickerVisible.value = false;
  ElMessage.success(`已添加点击坐标：(${realX}, ${realY})`);
};

const unwrapList = (res) => {
  const data = res.data;
  const payload = data?.data || data;
  return {
    results: payload?.results || payload || [],
    count: payload?.count || (Array.isArray(payload) ? payload.length : 0),
  };
};

const loadOptions = async () => {
  const [projectRes, packageRes, deviceRes] = await Promise.all([
    getAppProjects({ page_size: 100 }),
    getPackageList({ page_size: 100 }),
    getDeviceList({ page_size: 100 }),
  ]);
  projects.value = unwrapList(projectRes).results;
  packages.value = unwrapList(packageRes).results;
  devices.value = unwrapList(deviceRes).results;
};

const hasActiveTask = computed(() =>
  tasks.value.some((item) => ["pending", "running"].includes(item.status)),
);
const hasActiveAIAnalysis = computed(
  () =>
    reportVisible.value && currentTask.value?.id && aiAnalysisInProgress.value,
);

const isTaskStarting = (taskId) => startingTaskIds.value.includes(taskId);
const isConsistencyStarting = (taskId) =>
  consistencyStartingTaskIds.value.includes(taskId);

const canRunConsistency = (task = {}) => {
  const status = String(task.status || "").toLowerCase();
  return (
    task.strategy === "target_inspection" &&
    !["pending", "running"].includes(status)
  );
};

const markTaskStarting = (taskId, starting) => {
  if (!taskId) return;
  if (starting) {
    if (!startingTaskIds.value.includes(taskId)) {
      startingTaskIds.value = [...startingTaskIds.value, taskId];
    }
  } else {
    startingTaskIds.value = startingTaskIds.value.filter((id) => id !== taskId);
  }
};

const markConsistencyStarting = (taskId, starting) => {
  if (!taskId) return;
  if (starting) {
    if (!consistencyStartingTaskIds.value.includes(taskId)) {
      consistencyStartingTaskIds.value = [
        ...consistencyStartingTaskIds.value,
        taskId,
      ];
    }
  } else {
    consistencyStartingTaskIds.value = consistencyStartingTaskIds.value.filter(
      (id) => id !== taskId,
    );
  }
};

const getTaskDeviceId = (task) => {
  const device = task?.device;
  if (device && typeof device === "object")
    return device.id || device.pk || device.device_id;
  return device;
};

const canCheckTaskDevice = (task) => {
  if (!getTaskDeviceId(task)) return false;
  const status = String(task?.status || "").toLowerCase();
  return (
    task?.execution_health?.is_stale ||
    ["pending", "running", "error", "failed"].includes(status)
  );
};

const isDeviceHealthChecking = (taskOrId) => {
  const deviceId =
    typeof taskOrId === "object" ? getTaskDeviceId(taskOrId) : taskOrId;
  return (
    Boolean(deviceId) &&
    deviceHealthCheckingIds.value.includes(String(deviceId))
  );
};

const markDeviceHealthChecking = (deviceId, checking) => {
  if (!deviceId) return;
  const key = String(deviceId);
  if (checking) {
    if (!deviceHealthCheckingIds.value.includes(key)) {
      deviceHealthCheckingIds.value = [...deviceHealthCheckingIds.value, key];
    }
  } else {
    deviceHealthCheckingIds.value = deviceHealthCheckingIds.value.filter(
      (id) => id !== key,
    );
  }
};

const deviceHealthTag = (verdict) => {
  if (verdict === "executable") return "success";
  if (verdict === "needs_attention") return "warning";
  return "danger";
};

const checkTaskDevice = async (task) => {
  const deviceId = getTaskDeviceId(task);
  if (!deviceId) {
    ElMessage.warning("当前任务未绑定执行设备，无法检查");
    return;
  }
  markDeviceHealthChecking(deviceId, true);
  deviceHealthResult.value = null;
  try {
    const res = await healthCheckDevice(deviceId);
    deviceHealthResult.value = res.data?.data || null;
    deviceHealthVisible.value = true;
  } catch (error) {
    console.error("设备健康检查失败:", error);
    ElMessage.error(formatApiError(error, "设备健康检查失败"));
  } finally {
    markDeviceHealthChecking(deviceId, false);
  }
};

const syncCurrentReport = async () => {
  if (!reportVisible.value || !currentTask.value?.id) return;
  const latest = tasks.value.find((item) => item.id === currentTask.value.id);
  if (
    hasActiveAIAnalysis.value ||
    (latest && !["pending", "running"].includes(latest.status))
  ) {
    const res = await getExplorationReport(currentTask.value.id);
    currentTask.value = res.data?.data || res.data;
  } else if (latest) {
    currentTask.value = { ...currentTask.value, ...latest };
  }
};

const reloadCurrentReport = async () => {
  if (!currentTask.value?.id) return;
  const res = await getExplorationReport(currentTask.value.id);
  currentTask.value = res.data?.data || res.data;
};

const reviewIssue = async (issue, resolution) => {
  if (!currentTask.value?.id || !issue?.step_index) return;
  const key = `${issue.step_index}-${resolution}`;
  const noteMap = {
    valid_issue: "人工复核为有效问题，保留在报告中用于后续缺陷确认。",
    normal_behavior: "人工复核为正常业务行为；后续同类控件命中后可自动归档。",
    rule_exception:
      "人工复核为状态切换类控件：点击后允许页面无跳转，只要开关/选中状态变化即视为正常。",
    needs_assertion: "人工复核为需补充状态断言，不再作为页面无变化问题。",
    ignore: "人工复核后暂不处理。",
  };
  reviewingIssueKey.value = key;
  try {
    await reviewExplorationIssue(currentTask.value.id, {
      step_index: issue.step_index,
      resolution,
      note: noteMap[resolution] || "",
    });
    await reloadCurrentReport();
    ElMessage.success(
      resolution === "valid_issue" ? "已标记为有效问题" : "已归档并更新报告",
    );
  } catch (error) {
    console.error("保存问题复核失败:", error);
    ElMessage.error(error?.response?.data?.message || "保存问题复核失败");
  } finally {
    reviewingIssueKey.value = "";
  }
};

const reviewTargetResult = async (item, resolution) => {
  if (!currentTask.value?.id || !item) return;
  const key = `${item.id || item.target_name}-${resolution}`;
  reviewingTargetKey.value = key;
  try {
    await reviewExplorationTarget(currentTask.value.id, {
      target_result_id: item.id,
      target_name: item.target_name,
      step_index: item.step_index,
      resolution,
      note: targetReviewDefaultNote(resolution),
    });
    await reloadCurrentReport();
    ElMessage.success(
      `${item.target_name || "目标"} 已标记为${targetReviewText(resolution)}`,
    );
  } catch (error) {
    console.error("保存目标复核失败:", error);
    ElMessage.error(error?.response?.data?.message || "保存目标复核失败");
  } finally {
    reviewingTargetKey.value = "";
  }
};

const updatePolling = () => {
  if ((hasActiveTask.value || hasActiveAIAnalysis.value) && !refreshTimer) {
    refreshTimer = setInterval(() => {
      loadTasks({ silent: true });
    }, 2000);
  } else if (
    !hasActiveTask.value &&
    !hasActiveAIAnalysis.value &&
    refreshTimer
  ) {
    clearInterval(refreshTimer);
    refreshTimer = null;
  }
};

const loadTasks = async (options = {}) => {
  const silent = Boolean(options.silent);
  if (silent) {
    isAutoRefreshing.value = true;
  } else {
    loading.value = true;
  }
  try {
    const params = {
      page: page.value,
      page_size: pageSize.value,
      search: query.search || undefined,
      status: query.status || undefined,
      project: query.project || undefined,
    };
    const res = await getExplorationTasks(params);
    const payload = unwrapList(res);
    tasks.value = payload.results;
    total.value = payload.count;
    await syncCurrentReport();
    updatePolling();
  } catch (error) {
    console.error("加载探索任务失败:", error);
    if (!silent) {
      ElMessage.error("加载探索任务失败");
    }
  } finally {
    loading.value = false;
    isAutoRefreshing.value = false;
  }
};

const openCreateDialog = () => {
  editingId.value = null;
  applyCreateFormDefaults();
  createVisible.value = true;
};

const consumePageMapInspectionDraft = () => {
  const raw = window.localStorage.getItem("qaflow_page_map_inspection_draft");
  if (!raw) return false;
  window.localStorage.removeItem("qaflow_page_map_inspection_draft");
  try {
    const draft = JSON.parse(raw);
    const targets = Array.isArray(draft.entry_keywords)
      ? draft.entry_keywords
          .map((item) => String(item || "").trim())
          .filter(Boolean)
      : [];
    if (!targets.length) return false;
    editingId.value = null;
    applyCreateFormDefaults({
      name: draft.name || "页面地图目标巡检",
      project: draft.project || null,
      app_package: draft.app_package || null,
      strategy: "target_inspection",
      objective:
        draft.objective || "基于页面地图生成的目标巡检草稿，请确认后执行。",
      entry_keywords: targets,
      start_note: draft.start_note || "",
      max_steps: draft.max_steps || Math.max(targets.length * 3, 20),
      max_duration: draft.max_duration || 300,
      source_type: "page_map_target_draft",
      source_summary: {
        ...(draft.source_summary || {}),
        target_list: targets,
        target_inspection_enabled: true,
      },
    });
    createVisible.value = true;
    ElMessage.success("已带入页面地图巡检草稿，请确认设备和目标清单后保存");
    return true;
  } catch (error) {
    console.warn("页面地图巡检草稿解析失败:", error);
    return false;
  }
};

const applyCreateFormDefaults = (overrides = {}) => {
  Object.assign(form, {
    name: "",
    project: null,
    app_package: null,
    device: null,
    strategy: "target_inspection",
    objective: "",
    entry_keywords: [],
    start_note: "",
    start_actions: [],
    max_steps: 20,
    max_duration: 300,
    blacklist_keywords: [...defaultBlacklist],
    source_task: null,
    source_type: "",
    source_summary: {},
    ...overrides,
  });
};

const openEditDialog = (row) => {
  if (row.status === "running") return;
  editingId.value = row.id;
  Object.assign(form, {
    name: row.name || "",
    project: row.project || null,
    app_package: row.app_package || null,
    device: row.device || null,
    strategy: row.strategy || "rule_mvp",
    objective: row.objective || "",
    entry_keywords: Array.isArray(row.entry_keywords)
      ? [...row.entry_keywords]
      : [],
    start_note: row.start_note || "",
    start_actions: normalizeStartActions(row.start_actions),
    max_steps: row.max_steps || 20,
    max_duration: row.max_duration || 300,
    blacklist_keywords:
      Array.isArray(row.blacklist_keywords) && row.blacklist_keywords.length
        ? [...row.blacklist_keywords]
        : [...defaultBlacklist],
    source_task: row.source_task || null,
    source_type: row.source_type || "",
    source_summary: row.source_summary || {},
  });
  createVisible.value = true;
};

const createTaskDraftFromAIAnalysis = () => {
  const task = currentTask.value;
  const draft = aiNextRoundDraft.value || {};
  const selectedPlanTargets = selectedAIPlanTargets.value
    .map((item) => item.target_name)
    .filter(Boolean);
  const draftTargets = Array.isArray(draft.targets)
    ? draft.targets.map((item) => displayText(item, "")).filter(Boolean)
    : [];
  const targets = selectedPlanTargets.length
    ? selectedPlanTargets
    : draftTargets.length
      ? draftTargets
      : aiTargetTexts();
  if (!task || !targets.length) {
    ElMessage.info("AI 暂无下一轮探索目标");
    return;
  }
  const autoTargets = autoExplorationTargetTexts();
  const proposedStartActions =
    Array.isArray(draft.start_actions) && draft.start_actions.length
      ? normalizeStartActions(draft.start_actions)
      : aiActionsToStartActions();
  const actionGroups = aiActionGroups();
  const draftEntryKeywords = Array.isArray(draft.entry_keywords)
    ? draft.entry_keywords
        .map(cleanAIKeywordText)
        .filter((item) => item && !isNoiseAIKeyword(item))
    : [];
  const entryKeywords = draftEntryKeywords.length
    ? draftEntryKeywords
    : deriveEntryKeywordsFromTargets(
        autoTargets.length ? autoTargets : targets,
      );
  const rejectedActionCount = Math.max(
    aiActionProposals.value.length - selectedAIActionProposals.value.length,
    0,
  );
  const baseName = baseExplorationTaskName(task);
  const round = nextExplorationRound();
  editingId.value = null;
  Object.assign(form, {
    name: `${baseName} - AI 第 ${round} 轮`,
    project: task.project || null,
    app_package: task.app_package || null,
    device: task.device || null,
    strategy: draft.strategy || "target_inspection",
    objective: [
      "基于上一轮 AI 分析，下一轮建议重点探索：",
      ...targets.map((item, index) => `${index + 1}. ${item}`),
    ].join("\n"),
    entry_keywords: entryKeywords,
    start_note: proposedStartActions.length
      ? `由 AI 分析建议生成，已按人工勾选预填 ${proposedStartActions.length} 条起始导航动作；请保存前再次确认。`
      : "由 AI 分析建议生成，请保存前人工确认目标、入口关键词和风险黑名单。",
    start_actions: proposedStartActions,
    max_steps: Math.max(
      Number(task.max_steps || 20),
      Number(draft.max_steps || 30),
    ),
    max_duration: Math.max(
      Number(task.max_duration || 300),
      Number(draft.max_duration || 300),
    ),
    blacklist_keywords:
      Array.isArray(task.blacklist_keywords) && task.blacklist_keywords.length
        ? [...task.blacklist_keywords]
        : [...defaultBlacklist],
    source_task: task.id,
    source_type: "ai_next_round",
    source_summary: {
      analysis_model: aiAnalysis.value?.model_name || "",
      risk_level: aiAnalysis.value?.risk_level || "",
      conclusion: aiAnalysis.value?.conclusion || "",
      targets,
      auto_targets: autoTargets,
      entry_keywords: entryKeywords,
      entry_keyword_candidates:
        aiAnalysis.value?.entry_keyword_candidates || [],
      inspection_plan: aiInspectionPlan.value || {},
      selected_inspection_targets: selectedAIPlanTargets.value,
      semantic_suggestions: aiSemanticSuggestions.value,
      next_round_draft: draft,
      exploration_preferences: draft.exploration_preferences || [],
      confirmation_required_actions: draft.confirmation_required_actions || [],
      blocked_actions: draft.blocked_actions || [],
      action_proposals: aiActionProposals.value,
      selected_action_proposals: selectedAIActionProposals.value,
      admitted_start_actions: proposedStartActions,
      action_layers: {
        start_navigation: actionGroups.start_navigation,
        conditional_fallback: actionGroups.conditional_fallback,
        exploration_preference: actionGroups.exploration_preference,
        blocked: actionGroups.blocked,
      },
      rejected_action_count: rejectedActionCount,
    },
  });
  reportVisible.value = false;
  createVisible.value = true;
  ElMessage.success("已生成下一轮探索任务草稿，请确认后保存");
};

const createAdjustedIterationDraft = () => {
  const task = currentTask.value;
  if (!task) return;

  const sourceSummary = iterationSourceSummary.value || {};
  const targets =
    Array.isArray(sourceSummary.targets) && sourceSummary.targets.length
      ? sourceSummary.targets
          .map((item) => displayText(item, ""))
          .filter(Boolean)
      : aiTargetTexts();
  const autoTargets =
    Array.isArray(sourceSummary.auto_targets) &&
    sourceSummary.auto_targets.length
      ? sourceSummary.auto_targets
          .map((item) => displayText(item, ""))
          .filter(Boolean)
      : targets.filter(
          (item) =>
            !processKeywordMarkers.some((marker) => item.includes(marker)),
        );
  const acceptedActions = iterationAcceptedActions.value;
  const failedTarget = extractFailedStartActionTarget(task);
  const retainedActions = removeFailedTargetActions(
    acceptedActions,
    failedTarget,
  );
  const saferStartActions = retainedActions
    .filter((item) => classifyAIActionProposal(item) === "start_navigation")
    .map((item) => ({
      ...defaultStartAction(),
      type: "tap_text",
      value: item.target,
    }));
  const entryKeywords = Array.from(
    new Set(
      [
        ...(Array.isArray(task.entry_keywords) ? task.entry_keywords : []),
        ...deriveEntryKeywordsFromTargets(
          autoTargets.length ? autoTargets : targets,
        ),
      ]
        .map(cleanAIKeywordText)
        .filter((item) => item && !isNoiseAIKeyword(item)),
    ),
  ).slice(0, 10);
  const baseName = baseExplorationTaskName(task);
  const round = nextExplorationRound();

  editingId.value = null;
  Object.assign(form, {
    name: `${baseName} - 修正重试第 ${round} 轮`,
    project: task.project || null,
    app_package: task.app_package || null,
    device: task.device || null,
    strategy: task.strategy || "stability",
    objective: [
      "基于上一轮无效探索修正：",
      "1. 本轮未形成有效路径，先移除可能带偏页面的滑动/等待/返回动作。",
      "2. 保留探索目标和入口关键词，优先让平台重新寻找可点击入口。",
      ...targets.map((item, index) => `${index + 3}. ${item}`),
    ].join("\n"),
    entry_keywords: entryKeywords,
    start_note: saferStartActions.length
      ? `由无效迭代自动修正，仅保留 ${saferStartActions.length} 条点击文字起始动作；请保存前确认是否命中当前页面。`
      : "由无效迭代自动修正，已清空起始导航；请依赖入口关键词重新进入目标区域，必要时手动补充点击文字动作。",
    start_actions: saferStartActions,
    max_steps: Math.max(Number(task.max_steps || 20), 30),
    max_duration: Math.max(Number(task.max_duration || 300), 300),
    blacklist_keywords:
      Array.isArray(task.blacklist_keywords) && task.blacklist_keywords.length
        ? [...task.blacklist_keywords]
        : [...defaultBlacklist],
    source_task: task.id,
    source_type: "ai_adjusted_retry",
    source_summary: {
      based_on_source_task:
        iteration.value?.source_task?.id || task.source_task || null,
      reason: "previous_iteration_no_effective_path",
      failed_start_action_target: failedTarget,
      targets,
      auto_targets: autoTargets,
      entry_keywords: entryKeywords,
      previous_selected_action_proposals: acceptedActions,
      removed_action_proposals: acceptedActions.filter(
        (item) => !retainedActions.includes(item),
      ),
      retained_start_actions: saferStartActions,
      removed_action_count: Math.max(
        acceptedActions.length - saferStartActions.length,
        0,
      ),
    },
  });
  reportVisible.value = false;
  createVisible.value = true;
  ElMessage.success("已生成修正探索草稿，请确认后保存");
};

const formatApiError = (error, fallback = "操作失败") => {
  const data = error?.response?.data;
  if (!data) return error?.message || fallback;
  if (typeof data === "string") return data;
  if (typeof data.detail === "string") return data.detail;
  if (typeof data.message === "string") return data.message;
  const parts = [];
  Object.entries(data).forEach(([key, value]) => {
    if (Array.isArray(value)) {
      parts.push(`${key}: ${value.join("；")}`);
    } else if (value && typeof value === "object") {
      parts.push(`${key}: ${JSON.stringify(value)}`);
    } else if (value) {
      parts.push(`${key}: ${value}`);
    }
  });
  return parts.join("；") || fallback;
};

const submitTask = (runAfterSave = false) => {
  formRef.value?.validate(async (valid) => {
    if (!valid) return;
    if (runAfterSave && editingId.value) {
      ElMessage.warning("编辑已有任务时请先保存，再手动执行");
      return;
    }
    if (startActionSafetySummary.value.forbidden > 0) {
      ElMessage.error(
        startActionSafetySummary.value.messages[0] ||
          "起始导航存在禁止动作，请删除后再保存",
      );
      return;
    }
    saving.value = true;
    saveAndRunLoading.value = Boolean(runAfterSave);
    try {
      const payload = {
        ...form,
        source_summary: {
          ...(form.source_summary || {}),
          ...(form.strategy === "target_inspection"
            ? {
                target_list: Array.isArray(form.entry_keywords)
                  ? [...form.entry_keywords]
                  : [],
                target_inspection_enabled: true,
              }
            : {}),
          ...(runAfterSave
            ? {
                human_confirmed_run: true,
                human_confirmed_at: new Date().toISOString(),
                run_mode: "save_and_run",
              }
            : {}),
        },
        start_actions: normalizeStartActions(form.start_actions).filter(
          (action) => {
            if (["tap_text", "tap_resource_id"].includes(action.type))
              return String(action.value || "").trim();
            if (action.type === "tap_pos")
              return Number(action.x) > 0 && Number(action.y) > 0;
            return true;
          },
        ),
      };
      if (editingId.value) {
        await updateExplorationTask(editingId.value, payload);
        ElMessage.success("探索任务已更新");
      } else {
        const res = await createExplorationTask(payload);
        const createdTask = res.data?.data || res.data || {};
        if (runAfterSave && createdTask.id) {
          await runExplorationTask(createdTask.id);
          ElMessage.success("探索任务已创建并启动");
        } else {
          ElMessage.success("探索任务已创建");
        }
      }
      createVisible.value = false;
      editingId.value = null;
      await loadTasks({ silent: Boolean(runAfterSave) });
      if (runAfterSave) updatePolling();
    } catch (error) {
      console.error("创建探索任务失败:", error);
      ElMessage.error(formatApiError(error, "创建探索任务失败"));
    } finally {
      saving.value = false;
      saveAndRunLoading.value = false;
    }
  });
};

const runTask = async (row) => {
  markTaskStarting(row.id, true);
  tasks.value = tasks.value.map((item) =>
    item.id === row.id
      ? {
          ...item,
          status: "pending",
          progress: Math.max(Number(item.progress || 0), 1),
          summary: {
            ...(item.summary || {}),
            current_stage: "任务已提交，正在连接设备",
          },
        }
      : item,
  );
  updatePolling();
  try {
    await runExplorationTask(row.id);
    ElMessage.success("任务已启动，正在连接设备并启动 APP");
    await loadTasks({ silent: true });
  } catch (error) {
    console.error("启动探索任务失败:", error);
    ElMessage.error(error?.response?.data?.message || "启动探索任务失败");
  } finally {
    markTaskStarting(row.id, false);
  }
};

const runConsistency = async (row) => {
  try {
    await ElMessageBox.confirm(
      "平台会连续执行同一个目标巡检任务 3 次。执行前请确认手机停留在同一个起始页面，过程中不要手动操作手机。",
      "三次一致性验证",
      { type: "warning" },
    );
  } catch (error) {
    return;
  }

  markConsistencyStarting(row.id, true);
  tasks.value = tasks.value.map((item) =>
    item.id === row.id
      ? {
          ...item,
          status: "pending",
          progress: 1,
          summary: {
            ...(item.summary || {}),
            current_stage: "三次一致性验证已提交，准备连续执行 3 轮",
            consistency_batch_total: 3,
            consistency_batch_index: 0,
          },
        }
      : item,
  );
  updatePolling();
  try {
    await runExplorationConsistency(row.id, { run_count: 3 });
    ElMessage.success("三次一致性验证已启动，请保持手机在同一页面并等待完成");
    await loadTasks({ silent: true });
  } catch (error) {
    console.error("启动三次一致性验证失败:", error);
    ElMessage.error(error?.response?.data?.message || "启动三次一致性验证失败");
  } finally {
    markConsistencyStarting(row.id, false);
  }
};

const stopTask = async (row) => {
  try {
    await stopExplorationTask(row.id);
    ElMessage.success("已停止探索任务");
    loadTasks();
  } catch (error) {
    console.error("停止探索任务失败:", error);
    ElMessage.error(error?.response?.data?.message || "停止探索任务失败");
  }
};

const deleteTask = (row) => {
  ElMessageBox.confirm(`确认删除探索任务「${row.name}」吗？`, "删除确认", {
    type: "warning",
  })
    .then(async () => {
      await deleteExplorationTask(row.id);
      ElMessage.success("删除成功");
      loadTasks();
    })
    .catch(() => {});
};

const openReport = async (row) => {
  try {
    reportActiveTab.value = "overview";
    activeConversionReviewFilter.value = "all";
    expandedPageIssues.value = {};
    expandedPriorityItems.value = {};
    showAllPriorityItems.value = false;
    expandedConversionReview.value = false;
    expandedAIAudit.value = false;
    showReportDetails.value = false;
    highlightedStepIndex.value = null;
    const res = await getExplorationReport(row.id);
    currentTask.value = res.data?.data || res.data;
    reportVisible.value = true;
  } catch (error) {
    console.error("加载探索报告失败:", error);
    ElMessage.error("加载探索报告失败");
  }
};

const openSourceReport = async (taskId) => {
  if (!taskId) return;
  try {
    reportActiveTab.value = "overview";
    activeConversionReviewFilter.value = "all";
    expandedPageIssues.value = {};
    expandedPriorityItems.value = {};
    showAllPriorityItems.value = false;
    expandedConversionReview.value = false;
    expandedAIAudit.value = false;
    showReportDetails.value = false;
    highlightedStepIndex.value = null;
    const res = await getExplorationReport(taskId);
    currentTask.value = res.data?.data || res.data;
    reportVisible.value = true;
    ElMessage.success("已打开来源探索报告");
  } catch (error) {
    console.error("加载来源报告失败:", error);
    ElMessage.error(error.response?.data?.message || "加载来源报告失败");
  }
};

const downloadExplorationLogcat = () => {
  const url =
    currentTask.value?.logcat?.download_url ||
    (currentTask.value?.id
      ? `/api/app-automation/exploration-tasks/${currentTask.value.id}/download-logcat/`
      : "");
  if (!url || !currentTask.value?.logcat?.available) {
    ElMessage.warning("该探索任务暂无可导出的 logcat");
    return;
  }
  window.open(url, "_blank");
};

const safeMarkdownText = (value, fallback = "-") => {
  const text = String(value ?? "")
    .replace(/\r\n/g, "\n")
    .trim();
  return text || fallback;
};

const sanitizeFilename = (value) => {
  return (
    String(value || "report")
      .replace(/[\\/:*?"<>|]/g, "-")
      .replace(/\s+/g, "-")
      .replace(/-+/g, "-")
      .replace(/^-|-$/g, "")
      .slice(0, 80) || "report"
  );
};

const markdownList = (items, formatter, emptyText = "- 无") => {
  if (!Array.isArray(items) || !items.length) return emptyText;
  return items.map(formatter).join("\n");
};

const absoluteAppUrl = (path) => {
  const value = String(path || "").trim();
  if (!value) return "";
  if (/^https?:\/\//i.test(value)) return value;
  const normalized = value.startsWith("/") ? value : `/${value}`;
  return window.location?.origin
    ? `${window.location.origin}${normalized}`
    : normalized;
};

const evidenceScreenshotLinks = (step = {}) => {
  const items = [
    { label: "标注截图", url: step.annotated_screenshot_url },
    {
      label: "操作后截图",
      url: step.after_screenshot_url || step.screenshot_url,
    },
    { label: "操作前截图", url: step.before_screenshot_url },
  ];
  const seen = new Set();
  return items
    .map((item) => ({ ...item, url: absoluteAppUrl(mediaUrl(item.url)) }))
    .filter((item) => {
      if (!item.url || seen.has(item.url)) return false;
      seen.add(item.url);
      return true;
    });
};

const issueEvidenceRows = (issue = {}) => {
  const stepIndex = Number(issue.step_index);
  const step = stepByIndex(stepIndex) || {};
  const targetResult = targetResultByStepIndex(stepIndex);
  const control =
    stepEvidenceOverlayControl(step) || targetResultOverlayControl(stepIndex);
  const review = issueReviewMap.value?.[String(issue.step_index)] || {};
  const screenshots = evidenceScreenshotLinks(step);
  const rows = [
    `- 关联步骤：第 ${issue.step_index || "-"} 步`,
    `- 操作：${safeMarkdownText(displayStepAction(step), "未知操作")}`,
    `- 目标：${safeMarkdownText(targetResult?.target_name || displayStepTarget(step), "未知目标")}`,
    `- 点击/滑动位置：${safeMarkdownText(evidenceControlPositionText(control), "暂无可绘制位置")}`,
    `- 预期：${safeMarkdownText(buildPriorityEvidenceRows(stepIndex, {})[1]?.value, "页面应出现可解释的业务状态变化")}`,
    `- 实际：${safeMarkdownText(issue.issue_message || targetResult?.error_message || step.issue_message, step.changed ? "检测到页面变化" : "未检测到明确变化")}`,
    `- Activity：${safeMarkdownText(step.after_activity || step.before_activity || targetResult?.activity, "暂无")}`,
    `- 技术定位：${safeMarkdownText(technicalStepTarget(step), "暂无")}`,
    review.resolution
      ? `- 人工复核：${safeMarkdownText(targetReviewText(review.resolution))}；说明：${safeMarkdownText(review.note)}`
      : "- 人工复核：未复核",
    screenshots.length
      ? `- 截图链接：${screenshots.map((item) => `[${item.label}](${item.url})`).join("、")}`
      : "- 截图链接：暂无截图附件",
  ];
  return rows.join("\n");
};

const buildDefectEvidencePackage = (issues = []) => {
  const issueItems =
    Array.isArray(issues) && issues.length
      ? issues
      : actionableIssueList.value.slice(0, 3);
  if (!issueItems.length) return "- 暂无结构化问题证据。";
  return issueItems
    .slice(0, 5)
    .map((issue, index) =>
      [`### 证据 ${index + 1}`, issueEvidenceRows(issue)].join("\n"),
    )
    .join("\n\n");
};

const buildExplorationSummaryMarkdown = () => {
  const task = currentTask.value || {};
  const summary = conversionSummary.value || {};
  const guard = explorationGuard.value;
  const lines = [
    `# QAFlow AI 探索报告 - ${safeMarkdownText(task.name, `任务 ${task.id || ""}`)}`,
    "",
    "## 质量决策",
    `- 结论：${safeMarkdownText(qualityDecision.value.title)}`,
    `- 建议下一步：${safeMarkdownText(qualityDecision.value.nextAction)}`,
    `- 判断说明：${safeMarkdownText(qualityDecision.value.description)}`,
    `- 主要依据：${qualityDecision.value.reasons.join("、") || "无"}`,
    "",
    "## 目标巡检验收",
    targetAcceptanceSummary.value.available
      ? `- 验收结论：${safeMarkdownText(targetAcceptanceSummary.value.title)}`
      : "- 验收结论：暂无目标巡检验收数据",
    targetAcceptanceSummary.value.available
      ? `- 验收说明：${safeMarkdownText(targetAcceptanceSummary.value.description)}`
      : "- 验收说明：连续执行目标巡检后会生成稳定性验收项。",
    targetAcceptanceSummary.value.available
      ? `- 建议下一步：${safeMarkdownText(targetAcceptanceSummary.value.nextAction)}`
      : "- 建议下一步：先执行目标巡检任务。",
    "",
    "### 验收项",
    markdownList(
      targetAcceptanceItems.value,
      (item) =>
        `- ${item.passed ? "通过" : "未达标"}｜${safeMarkdownText(item.label)}：${safeMarkdownText(item.actual)} / ${safeMarkdownText(item.expected)}${item.passed ? "" : `；建议：${safeMarkdownText(item.suggestion)}`}`,
    ),
    "",
    "## 基本信息",
    `- 任务状态：${safeMarkdownText(task.status)}`,
    `- 探索结果：${safeMarkdownText(task.result)}`,
    `- 探索步数：${task.total_steps || 0}`,
    `- 页面数：${task.explored_pages || 0}`,
    `- 疑似问题：${task.issue_count || 0}`,
    `- 耗时：${Math.round(task.duration || 0)} 秒`,
    `- 应用包名：${safeMarkdownText(task.package_name || task.app_package_name)}`,
    `- 执行设备：${safeMarkdownText(task.device_name)}`,
    "",
    "## 问题归因",
    markdownList(
      reportAttributionItems.value,
      (item) =>
        `- ${safeMarkdownText(item.label)}：${item.count} 项；负责人：${safeMarkdownText(item.owner)}；建议：${safeMarkdownText(item.nextAction)}；示例：${item.examples.join("、") || "无"}`,
    ),
    "",
    "## 探索效率",
    `- 自动止损：${guard.stopReason ? `是，${guard.stopReason}` : "否"}`,
    `- 语义页面数：${guard.semanticPages || 0}`,
    `- 空页返回：${guard.emptyPageEscapes}`,
    `- 无响应控件：${guard.unresponsiveTargets}`,
    `- 低价值动作：${guard.lowValueActions}`,
    `- 重复页面命中：${guard.repeatedPages}`,
    "",
    "## 探索结论",
    safeMarkdownText(insights.value?.conclusion, "暂无探索结论"),
    "",
    "## 转用例质量预估",
    `- 高可信步骤：${summary.high_confidence_steps || 0} / ${summary.total_steps || 0}`,
    `- 可用率：${summary.ready_rate || 0}%`,
    `- 需复核步骤：${summary.needs_review_count || 0}`,
    `- 坐标兜底步骤：${summary.coordinate_only_count || 0}`,
    `- 点击无变化步骤：${summary.no_change_tap_count || 0}`,
    `- 问题步骤：${summary.issue_step_count || 0}`,
    "",
    "## 需复核步骤",
    markdownList(
      conversionNeedsReview.value,
      (item) =>
        `- 第 ${item.step_index || "-"} 步：${safeMarkdownText(item.action || item.target, "待确认步骤")}；原因：${safeMarkdownText(item.reason, "建议人工确认")}`,
    ),
    "",
    "## 疑似问题",
    markdownList(
      actionableIssueList.value,
      (item) =>
        `- 第 ${item.step_index || "-"} 步：${safeMarkdownText(item.issue_message || issueTypeText(item.issue_type), "疑似问题")}`,
    ),
    "",
    "## 关键问题证据包",
    buildDefectEvidencePackage(actionableIssueList.value.slice(0, 3)),
    "",
    "## 覆盖与风险",
    `- 目标覆盖率：${targetCoverage.value?.rate || 0}%`,
    `- 已覆盖目标：${targetCoveredKeywords.value.join("、") || "无"}`,
    `- 未覆盖目标：${targetUncoveredKeywords.value.join("、") || "无"}`,
    `- 已过滤噪声词：${targetFilteredKeywords.value.join("、") || "无"}`,
    `- 风险跳过：${skippedRisks.value.length}`,
    "",
    "## 风险跳过明细",
    markdownList(
      skippedRisks.value,
      (item) =>
        `- ${safeMarkdownText(item.keyword, "风险词")}：${safeMarkdownText(item.target || item.text || item.resource_id, "未知控件")}；原因：${safeMarkdownText(item.reason, "命中风险策略")}`,
    ),
    "",
    "## 复现路径",
    markdownList(
      (insights.value?.reproduction_path || []).slice(0, 50),
      (item) =>
        `- 第 ${item.step_index || "-"} 步：${safeMarkdownText(displayPathAction(item), "探索步骤")} ${safeMarkdownText(item.target || item.activity, "")}`,
    ),
    "",
    "## 日志附件",
    task.logcat?.available
      ? `- 已采集 logcat，包含 ${task.logcat.file_count || 0} 个日志文件，可在平台内导出 ZIP。`
      : "- 暂无 logcat 附件。",
    "",
    "> 本摘要由 QAFlow 自动生成，适合用于问题沟通、周报记录或探索结果归档。",
  ];
  return lines.join("\n");
};

const exportExplorationSummary = () => {
  if (!currentTask.value) return;
  const markdown = buildExplorationSummaryMarkdown();
  const blob = new Blob([markdown], { type: "text/markdown;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = `qaflow探索报告-${sanitizeFilename(currentTask.value.name || currentTask.value.id)}.md`;
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  URL.revokeObjectURL(url);
  ElMessage.success("报告摘要已导出");
};

const writeClipboardFallback = (text) => {
  const textarea = document.createElement("textarea");
  textarea.value = text;
  textarea.setAttribute("readonly", "readonly");
  textarea.style.position = "fixed";
  textarea.style.left = "-9999px";
  textarea.style.top = "-9999px";
  document.body.appendChild(textarea);
  textarea.select();
  const copied = document.execCommand("copy");
  document.body.removeChild(textarea);
  return copied;
};

const copyExplorationSummary = async () => {
  if (!currentTask.value) return;
  const markdown = buildExplorationSummaryMarkdown();
  try {
    if (navigator.clipboard?.writeText) {
      await navigator.clipboard.writeText(markdown);
    } else if (!writeClipboardFallback(markdown)) {
      throw new Error("clipboard fallback failed");
    }
    ElMessage.success("报告摘要已复制");
  } catch (error) {
    console.error("复制报告摘要失败:", error);
    ElMessage.error("复制失败，请改用导出报告摘要");
  }
};

const buildTaskBriefMarkdown = () => {
  const task = currentTask.value || {};
  const issueCount =
    actionableIssueList.value.length || Number(task.issue_count || 0);
  const reviewCount = conversionSummary.value?.needs_review_count || 0;
  const conclusion =
    qualityDecision.value?.title ||
    insights.value?.conclusion ||
    task.result ||
    task.status ||
    "暂无结论";
  const nextAction =
    qualityDecision.value?.nextAction ||
    postRunGuide.value?.title ||
    "打开报告处理台查看";
  const logcatText = task.logcat?.available
    ? `logcat 已采集 ${task.logcat.file_count || 0} 个文件`
    : "暂无 logcat";
  return [
    "QAFlow AI探索任务简报",
    `任务：${safeMarkdownText(task.name, `任务 ${task.id || ""}`)}`,
    `结论：${safeMarkdownText(conclusion)}`,
    `待复核：${issueCount} 个疑似问题，${reviewCount} 个步骤需确认`,
    `证据：${logcatText}`,
    `下一步：${safeMarkdownText(nextAction)}`,
  ].join("\n");
};

const copyTaskBrief = async () => {
  if (!currentTask.value) return;
  const markdown = buildTaskBriefMarkdown();
  try {
    if (navigator.clipboard?.writeText) {
      await navigator.clipboard.writeText(markdown);
    } else if (!writeClipboardFallback(markdown)) {
      throw new Error("clipboard fallback failed");
    }
    ElMessage.success("任务简报已复制");
  } catch (error) {
    console.error("复制任务简报失败:", error);
    ElMessage.error("复制失败，请改用导出报告摘要");
  }
};

const buildDefectDraftMarkdown = (targetIssue = null) => {
  const task = currentTask.value || {};
  const selectedIssue = targetIssue || issueList.value[0] || {};
  const defectTitle =
    selectedIssue.issue_message ||
    task.error_message ||
    insights.value?.conclusion ||
    "AI 探索测试发现疑似问题";
  const issueItems = targetIssue ? [targetIssue] : actionableIssueList.value;
  const issueSection = issueItems.length
    ? markdownList(
        issueItems,
        (item) =>
          `- 第 ${item.step_index || "-"} 步：${safeMarkdownText(item.issue_message || issueTypeText(item.issue_type), "疑似问题")}；归因：${safeMarkdownText(issueAttribution(item).label)}`,
      )
    : `- ${safeMarkdownText(task.error_message || insights.value?.conclusion, "任务执行异常，需人工确认")}`;
  const evidencePackage = buildDefectEvidencePackage(issueItems);
  const defectAttribution = targetIssue
    ? issueAttribution(targetIssue)
    : reportAttributionItems.value[0] ||
      taskFailureAttribution(task) ||
      attributionProfiles.unknown;
  const reproductionPath = insights.value?.reproduction_path || [];
  const selectedStepIndex = Number(selectedIssue.step_index);
  const relatedPath =
    targetIssue && Number.isFinite(selectedStepIndex)
      ? reproductionPath
          .filter((item) => Number(item.step_index) <= selectedStepIndex)
          .slice(-10)
      : reproductionPath.slice(0, 20);
  const reproduction = markdownList(
    relatedPath,
    (item) =>
      `- 第 ${item.step_index || "-"} 步：${safeMarkdownText(displayPathAction(item), "探索步骤")} ${safeMarkdownText(item.target || item.activity, "")}`,
  );

  return [
    `# 缺陷草稿：${safeMarkdownText(defectTitle)}`,
    "",
    "## 环境信息",
    `- 平台任务：${safeMarkdownText(task.name, `任务 ${task.id || ""}`)}`,
    `- 应用包名：${safeMarkdownText(task.package_name || task.app_package_name)}`,
    `- 执行设备：${safeMarkdownText(task.device_name)}`,
    `- 初步归因：${safeMarkdownText(defectAttribution.label)}（${safeMarkdownText(defectAttribution.owner)}）`,
    `- 建议处理：${safeMarkdownText(defectAttribution.nextAction)}`,
    `- 探索策略：${safeMarkdownText(task.summary?.strategy || task.strategy || "rule_mvp")}`,
    `- 执行耗时：${Math.round(task.duration || 0)} 秒`,
    "",
    "## 问题现象",
    issueSection,
    "",
    "## 复现路径",
    reproduction,
    "",
    "## 期望结果",
    "- APP 页面响应正常，不出现崩溃、ANR、白屏、异常跳转或关键功能不可用。",
    "",
    "## 实际结果",
    `- ${safeMarkdownText(defectTitle)}`,
    "",
    "## 证据定位",
    evidencePackage,
    "",
    "## 附件与日志",
    task.logcat?.available
      ? `- 已采集 logcat，包含 ${task.logcat.file_count || 0} 个日志文件：[下载 logcat ZIP](${absoluteAppUrl(task.logcat.download_url || `/api/app-automation/exploration-tasks/${task.id}/download-logcat/`)})。`
      : "- 当前报告暂无 logcat 附件，建议重新执行并开启日志采集后补充。",
    "- 报告内包含操作前/后截图和标注截图，可辅助定位发生问题的步骤。",
    "",
    "## 初步判断",
    `- 探索结论：${safeMarkdownText(insights.value?.conclusion, "暂无")}`,
    `- 问题数量：${targetIssue ? 1 : actionableIssueList.value.length || task.issue_count || 0}`,
    `- 需复核步骤：${conversionSummary.value?.needs_review_count || 0}`,
    "",
    "> 该缺陷草稿由 QAFlow AI 探索报告生成，提交前建议人工确认复现路径和截图。",
  ].join("\n");
};

const copyDefectDraft = async (targetIssue = null) => {
  if (!targetIssue && !canCopyDefectDraft.value) {
    ElMessage.info("当前报告暂无可生成缺陷草稿的问题");
    return;
  }
  const markdown = buildDefectDraftMarkdown(targetIssue);
  try {
    if (navigator.clipboard?.writeText) {
      await navigator.clipboard.writeText(markdown);
    } else if (!writeClipboardFallback(markdown)) {
      throw new Error("clipboard fallback failed");
    }
    ElMessage.success("缺陷证据包已复制");
  } catch (error) {
    console.error("复制缺陷草稿失败:", error);
    ElMessage.error("复制失败，请改用导出报告摘要");
  }
};

const getAIAnalysisErrorMessage = (error) => {
  const data = error?.response?.data || {};
  const rawMessage = String(data.message || error?.message || "");
  const rawDetail = String(data.detail || "");
  const lowerText = `${rawMessage} ${rawDetail}`.toLowerCase();

  if (
    data.error_type === "model_auth_error" ||
    lowerText.includes("401") ||
    lowerText.includes("invalid token") ||
    lowerText.includes("unauthorized") ||
    lowerText.includes("api key") ||
    lowerText.includes("api_key")
  ) {
    return (
      data.message ||
      "AI 模型认证失败，请到配置中心的 AI 探索模型配置中检查 API Key 是否有效。"
    );
  }
  if (
    data.error_type === "model_rate_limited" ||
    lowerText.includes("429") ||
    lowerText.includes("rate limit")
  ) {
    return data.message || "AI 模型请求过于频繁或额度不足，请稍后重试。";
  }
  if (data.error_type === "model_timeout" || lowerText.includes("timeout")) {
    return data.message || "AI 模型响应超时，请稍后重试。";
  }
  return data.message || error?.userMessage || "AI 分析失败，请检查模型配置";
};

const runAIAnalysis = async () => {
  if (!currentTask.value?.id) return;
  aiAnalyzing.value = true;
  try {
    const res = await analyzeExplorationWithAI(currentTask.value.id, {
      force: true,
    });
    const payload = res.data?.data || res.data;
    const isSubmitted = ["queued", "running"].includes(payload?.status);
    currentTask.value = {
      ...currentTask.value,
      summary: {
        ...(currentTask.value.summary || {}),
        ai_analysis_status: payload?.status || "queued",
        ai_analysis_stage: payload?.stage || "等待分析",
        ai_analysis_message:
          payload?.message || "AI 分析任务已提交，正在排队处理",
        ai_analysis_error: "",
      },
    };
    reportActiveTab.value = "ai";
    updatePolling();
    ElMessage.success(
      isSubmitted ? "AI 分析任务已提交，完成后会自动刷新" : "AI 分析完成",
    );
  } catch (error) {
    console.error("AI 分析失败:", error);
    ElMessage({
      type: "error",
      message: getAIAnalysisErrorMessage(error),
      duration: 6000,
      showClose: true,
    });
  } finally {
    aiAnalyzing.value = false;
  }
};

const convertToCaseDraft = async () => {
  if (!currentTask.value?.id) return;
  converting.value = true;
  try {
    const res = await convertExplorationToCase(currentTask.value.id, {
      name: `探索草稿 - ${currentTask.value.name || ""}`.trim(),
    });
    const testCase = res.data?.data?.test_case;
    ElMessage.success("已生成用例草稿");
    if (testCase?.id) {
      ElMessageBox.confirm(
        "用例草稿已创建，是否打开用例编排继续维护？",
        "生成成功",
        {
          type: "success",
          confirmButtonText: "打开编排",
          cancelButtonText: "先留在报告",
        },
      )
        .then(() => {
          router.push({
            path: "/app-automation/scene-builder",
            query: { case_id: testCase.id },
          });
        })
        .catch(() => {});
    }
  } catch (error) {
    console.error("转换用例草稿失败:", error);
    ElMessage.error(error?.response?.data?.message || "转换用例草稿失败");
  } finally {
    converting.value = false;
  }
};

const statusText = (status) =>
  ({
    pending: "等待中",
    running: "执行中",
    completed: "已完成",
    error: "异常",
    stopped: "已停止",
  })[status] ||
  status ||
  "-";

const statusTag = (status) =>
  ({
    pending: "info",
    running: "warning",
    completed: "success",
    error: "danger",
    stopped: "info",
  })[status] || "info";

const formatTime = (value) => {
  if (!value) return "-";
  return new Date(value).toLocaleString();
};

const formatDuration = (value) => {
  const seconds = Number(value || 0);
  if (!Number.isFinite(seconds) || seconds <= 0) return "-";
  if (seconds < 60) return `${Math.round(seconds)} 秒`;
  const minutes = Math.floor(seconds / 60);
  const rest = Math.round(seconds % 60);
  return rest ? `${minutes} 分 ${rest} 秒` : `${minutes} 分`;
};

onMounted(async () => {
  await loadOptions();
  await loadTasks();
  consumePageMapInspectionDraft();
});

onUnmounted(() => {
  if (refreshTimer) {
    clearInterval(refreshTimer);
    refreshTimer = null;
  }
});
</script>

<style scoped>
.exploration-page {
  padding: 20px;
}

.hero-card {
  display: flex;
  justify-content: space-between;
  gap: 20px;
  padding: 24px;
  border-radius: 18px;
  color: #17324d;
  background:
    radial-gradient(
      circle at top right,
      rgba(46, 125, 50, 0.18),
      transparent 34%
    ),
    linear-gradient(135deg, #f5fbf6 0%, #eef7ff 100%);
  border: 1px solid #dceee0;
}

.eyebrow {
  margin: 0 0 8px;
  font-size: 13px;
  color: #4f7d5d;
  letter-spacing: 0.08em;
}

.hero-card h2 {
  margin: 0;
  font-size: 28px;
}

.hero-desc {
  max-width: 760px;
  margin: 10px 0 0;
  line-height: 1.7;
  color: #4c5f70;
}

.hero-actions {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  white-space: nowrap;
}

.filter-card {
  margin-top: 16px;
}

.filter-form {
  margin-bottom: -18px;
}

.task-table {
  margin-top: 16px;
}

.pager {
  margin-top: 16px;
  justify-content: flex-end;
}

.option-meta {
  float: right;
  color: #909399;
  font-size: 12px;
}

.form-tip,
.muted {
  color: #6b7280;
  font-size: 13px;
  line-height: 1.6;
}

.start-action-toolbar {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 8px;
}

.start-action-safety {
  margin-top: 10px;
  padding: 10px 12px;
  border-radius: 10px;
  border: 1px solid #bbf7d0;
  background: #f0fdf4;
}

.start-action-safety.warning {
  border-color: #fde68a;
  background: #fffbeb;
}

.start-action-safety.danger {
  border-color: #fecaca;
  background: #fef2f2;
}

.safety-title,
.safety-metrics {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
}

.safety-title {
  justify-content: space-between;
}

.safety-metrics,
.safety-messages {
  margin-top: 6px;
  color: #64748b;
  font-size: 12px;
}

.safety-messages {
  display: grid;
  gap: 3px;
}

.start-point-picker {
  display: grid;
  gap: 12px;
}

.start-point-shot-wrap {
  display: flex;
  justify-content: center;
  padding: 12px;
  border-radius: 14px;
  background: #f8fafc;
  border: 1px dashed #cbd5e1;
}

.start-point-shot {
  width: min(100%, 320px);
  max-height: 640px;
  object-fit: contain;
  cursor: crosshair;
  border-radius: 12px;
  box-shadow: 0 12px 28px rgba(15, 23, 42, 0.18);
}

.decision-summary-card {
  margin-bottom: 16px;
  border: 1px solid #e5edf6;
  background:
    radial-gradient(
      circle at top right,
      rgba(14, 165, 233, 0.12),
      transparent 32%
    ),
    linear-gradient(180deg, #ffffff 0%, #f8fbff 100%);
}

.decision-summary-main {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 240px;
  gap: 16px;
  align-items: stretch;
}

.decision-verdict,
.decision-next-action {
  padding: 18px;
  border-radius: 18px;
  border: 1px solid #e8eef5;
  background: rgba(255, 255, 255, 0.82);
}

.decision-kicker,
.decision-next-action span,
.decision-evidence-item span {
  color: #64748b;
  font-size: 13px;
}

.decision-verdict strong,
.decision-next-action strong {
  display: block;
  margin-top: 8px;
  color: #0f172a;
  font-size: 22px;
}

.decision-verdict p {
  margin: 10px 0 0;
  color: #475569;
  line-height: 1.7;
}

.decision-success {
  border-color: #bbf7d0;
  background: #f0fdf4;
}

.decision-warning {
  border-color: #fde68a;
  background: #fffbeb;
}

.decision-danger {
  border-color: #fecaca;
  background: #fef2f2;
}

.decision-info {
  border-color: #bfdbfe;
  background: #eff6ff;
}

.decision-evidence-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 12px;
  margin-top: 14px;
}

.decision-evidence-item {
  padding: 14px;
  border-radius: 16px;
  background: #fff;
  border: 1px solid #e8eef5;
}

.decision-evidence-item strong {
  display: block;
  margin-top: 6px;
  color: #0f172a;
  font-size: 18px;
}

.decision-evidence-item small {
  display: block;
  margin-top: 6px;
  color: #64748b;
  line-height: 1.45;
}

.decision-reason-row {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 14px;
}

.report-actions {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 12px;
  margin-bottom: 16px;
}

.report-tabbar {
  position: sticky;
  top: 0;
  z-index: 6;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin: 0 0 14px;
  padding: 10px 12px;
  border-radius: 14px;
  background: rgba(255, 255, 255, 0.94);
  border: 1px solid #e2e8f0;
  box-shadow: 0 10px 28px rgba(15, 23, 42, 0.06);
  backdrop-filter: blur(8px);
}

.tabbar-tip {
  color: #64748b;
  font-size: 13px;
  line-height: 1.4;
}

.target-inspection-card {
  border-color: #dbeafe;
  background: #f8fbff;
}

.target-inspection-summary {
  display: grid;
  grid-template-columns: repeat(5, minmax(0, 1fr));
  gap: 10px;
  margin-bottom: 12px;
}

.target-inspection-metric {
  padding: 12px;
  border: 1px solid #e2e8f0;
  border-radius: 10px;
  background: #fff;
}

.target-inspection-metric span {
  display: block;
  color: #64748b;
  font-size: 12px;
}

.target-inspection-metric strong {
  display: block;
  margin-top: 4px;
  color: #0f172a;
  font-size: 20px;
}

.target-inspection-list {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 10px;
}

.target-inspection-item {
  padding: 12px;
  border: 1px solid #e2e8f0;
  border-left: 4px solid #94a3b8;
  border-radius: 10px;
  background: #fff;
}

.target-inspection-item.target-found_effective {
  border-left-color: #22c55e;
}

.target-inspection-item.target-found_unconfirmed {
  border-left-color: #f59e0b;
}

.target-inspection-item.target-risk_skipped,
.target-inspection-item.target-anchor_recovery_failed,
.target-inspection-item.target-error {
  border-left-color: #ef4444;
}

.target-inspection-main,
.target-inspection-meta {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
}

.target-inspection-main {
  justify-content: space-between;
}

.target-inspection-main strong {
  color: #0f172a;
}

.target-inspection-main span,
.target-inspection-meta {
  color: #64748b;
  font-size: 12px;
}

.target-inspection-actions {
  display: flex;
  align-items: center;
  gap: 6px;
}

.target-inspection-item p {
  margin: 8px 0 0;
  color: #92400e;
  font-size: 12px;
  line-height: 1.5;
}

.target-stability-card {
  border-color: #dcfce7;
  background: #fbfefb;
}

.target-stability-summary {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 12px;
  padding: 12px;
  border: 1px solid #dcfce7;
  border-radius: 10px;
  background: #fff;
}

.target-stability-summary strong {
  display: block;
  color: #166534;
  font-size: 22px;
}

.target-stability-summary span {
  color: #64748b;
  font-size: 12px;
}

.target-batch-diff {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  flex-wrap: wrap;
  gap: 8px;
}

.target-stability-table {
  display: grid;
  gap: 8px;
}

.target-stability-row {
  display: grid;
  grid-template-columns: 180px minmax(0, 1fr) 80px;
  gap: 10px;
  align-items: center;
  padding: 10px 12px;
  border: 1px solid #e2e8f0;
  border-radius: 10px;
  background: #fff;
}

.target-stability-row.header {
  color: #64748b;
  font-size: 12px;
  background: #f8fafc;
}

.target-stability-row.unstable {
  border-color: #fde68a;
  background: #fffbeb;
}

.target-stability-row strong {
  color: #0f172a;
}

.target-stability-row > span:last-child {
  color: #475569;
  font-size: 12px;
}

.target-stability-runs {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 6px;
}

.run-history-card {
  border-color: #e2e8f0;
}

.run-history-list {
  display: grid;
  gap: 10px;
}

.run-history-item {
  display: grid;
  grid-template-columns: 180px minmax(0, 1fr);
  gap: 12px;
  align-items: center;
  padding: 12px;
  border: 1px solid #e2e8f0;
  border-radius: 10px;
  background: #fff;
}

.run-history-item.latest {
  border-color: #bfdbfe;
  background: #eff6ff;
}

.run-history-main,
.run-history-meta {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
}

.run-history-main strong {
  color: #0f172a;
}

.run-history-meta {
  color: #64748b;
  font-size: 12px;
}

.conversion-summary {
  display: grid;
  gap: 10px;
  margin: -4px 0 16px;
  padding: 12px 14px;
  border: 1px solid #fed7aa;
  border-radius: 12px;
  background: linear-gradient(135deg, #fff7ed, #ffffff);
}

.conversion-main,
.conversion-tags {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 10px;
}

.conversion-main strong {
  color: #9a3412;
}

.clickable-tag {
  cursor: pointer;
  user-select: none;
}

.clickable-tag:hover {
  filter: brightness(0.98);
  transform: translateY(-1px);
}

.conversion-main span {
  color: #475569;
  font-size: 13px;
}

.conversion-review-toggle {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
  padding-top: 2px;
  color: #64748b;
  font-size: 12px;
}

.conversion-review-list {
  display: grid;
  gap: 8px;
  padding-top: 4px;
}

.conversion-review-filter {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
  padding: 8px 10px;
  border-radius: 10px;
  background: #fff7ed;
  border: 1px dashed #fdba74;
}

.conversion-review-item {
  padding: 10px 12px;
  border: 1px solid #fde68a;
  border-radius: 10px;
  background: #fffbeb;
}

.conversion-review-main {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
  color: #1f2937;
}

.conversion-review-reason {
  margin-top: 6px;
  color: #92400e;
  font-size: 12px;
  line-height: 1.5;
}

.report-alert,
.report-card {
  margin-bottom: 16px;
}

.report-workbench-card {
  border-color: #c7d2fe;
  background:
    radial-gradient(
      circle at top right,
      rgba(59, 130, 246, 0.12),
      transparent 34%
    ),
    linear-gradient(135deg, #f8fbff 0%, #ffffff 72%);
}

.report-workbench-main {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 18px;
  align-items: start;
}

.report-workbench-summary strong {
  display: block;
  color: #0f172a;
  font-size: 18px;
  margin-bottom: 6px;
}

.report-workbench-summary p {
  margin: 0;
  color: #475569;
  line-height: 1.7;
}

.report-next-line {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  margin-top: 12px;
  padding: 8px 10px;
  border-radius: 999px;
  color: #1d4ed8;
  background: #eff6ff;
  border: 1px solid #bfdbfe;
}

.report-next-line span {
  color: #64748b;
  font-size: 12px;
}

.report-next-line strong {
  display: inline;
  margin: 0;
  color: #1d4ed8;
  font-size: 13px;
}

.decision-reason-row.compact {
  margin-top: 10px;
}

.report-workbench-metrics {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 8px;
  margin-top: 12px;
  max-width: 620px;
}

.report-metric-chip {
  padding: 10px 12px;
  border: 1px solid #dbeafe;
  border-radius: 12px;
  background: rgba(255, 255, 255, 0.76);
}

.report-metric-chip span,
.priority-help {
  color: #64748b;
  font-size: 12px;
  line-height: 1.5;
}

.report-metric-chip strong {
  display: block;
  margin: 4px 0 0;
  color: #0f172a;
  font-size: 16px;
}

.report-workbench-actions {
  display: flex;
  justify-content: flex-end;
  flex-wrap: wrap;
  gap: 8px;
  max-width: 360px;
}

.report-workflow-strip {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 10px;
  margin-top: 16px;
}

.report-details-fold {
  display: grid;
  gap: 10px;
  margin-top: 12px;
}

.report-workflow-strip.compact {
  grid-template-columns: repeat(4, minmax(0, 1fr));
  margin-top: 0;
}

.report-workflow-step {
  display: grid;
  grid-template-columns: auto minmax(0, 1fr);
  gap: 10px;
  align-items: flex-start;
  padding: 12px;
  border-radius: 14px;
  border: 1px solid #e2e8f0;
  background: rgba(255, 255, 255, 0.78);
}

.report-workflow-step.active {
  border-color: #93c5fd;
  background: #eff6ff;
  box-shadow: 0 10px 24px rgba(37, 99, 235, 0.08);
}

.workflow-index {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 24px;
  height: 24px;
  border-radius: 999px;
  color: #1d4ed8;
  font-weight: 700;
  background: #dbeafe;
}

.report-workflow-step strong {
  display: block;
  color: #0f172a;
  font-size: 13px;
}

.report-workflow-step p {
  margin: 4px 0 0;
  color: #64748b;
  font-size: 12px;
  line-height: 1.45;
}

.report-roadmap-collapse {
  border: 1px solid #e2e8f0;
  border-radius: 14px;
  overflow: hidden;
  background: rgba(255, 255, 255, 0.82);
}

.report-roadmap-collapse :deep(.el-collapse-item__header) {
  padding: 0 14px;
  color: #334155;
  font-weight: 700;
  background: #f8fafc;
}

.report-roadmap-collapse :deep(.el-collapse-item__content) {
  padding: 0 14px 14px;
}

.roadmap-progress-board {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
  margin-top: 14px;
}

.roadmap-stage-card {
  padding: 14px;
  border-radius: 16px;
  border: 1px solid #e2e8f0;
  background: #fff;
}

.roadmap-stage-card.stage-success {
  border-color: #bbf7d0;
  background: linear-gradient(135deg, #f0fdf4 0%, #ffffff 72%);
}

.roadmap-stage-card.stage-warning {
  border-color: #fed7aa;
  background: linear-gradient(135deg, #fff7ed 0%, #ffffff 72%);
}

.roadmap-stage-card.stage-active {
  border-color: #bfdbfe;
  background: linear-gradient(135deg, #eff6ff 0%, #ffffff 72%);
}

.roadmap-stage-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 12px;
}

.roadmap-stage-head strong {
  display: block;
  color: #0f172a;
  font-size: 15px;
}

.roadmap-stage-head span {
  display: block;
  margin-top: 4px;
  color: #64748b;
  font-size: 12px;
  line-height: 1.45;
}

.roadmap-stage-list {
  display: grid;
  gap: 8px;
}

.roadmap-stage-item {
  display: grid;
  grid-template-columns: auto minmax(0, 1fr) auto;
  align-items: center;
  gap: 8px;
  padding: 9px 10px;
  border-radius: 12px;
  border: 1px solid #e2e8f0;
  background: rgba(255, 255, 255, 0.76);
}

.roadmap-stage-item.item-blocked {
  border-color: #fed7aa;
  background: #fffbeb;
}

.roadmap-stage-item.item-done {
  border-color: #dcfce7;
  background: #f7fee7;
}

.roadmap-stage-item strong,
.roadmap-stage-item span {
  display: block;
}

.roadmap-stage-item strong {
  color: #1f2937;
  font-size: 12px;
}

.roadmap-stage-item span {
  margin-top: 2px;
  color: #64748b;
  font-size: 12px;
  line-height: 1.45;
}

.report-quick-toggle {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-top: 12px;
  padding: 10px 12px;
  border-radius: 12px;
  color: #64748b;
  font-size: 12px;
  background: rgba(248, 250, 252, 0.9);
  border: 1px dashed #cbd5e1;
}

.report-evidence-shortcuts {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-top: 10px;
  padding: 10px 12px;
  border-radius: 12px;
  background: rgba(255, 255, 255, 0.78);
  border: 1px solid #e2e8f0;
}

.report-evidence-shortcuts strong {
  display: block;
  color: #0f172a;
  font-size: 13px;
}

.report-evidence-shortcuts span {
  display: block;
  margin-top: 3px;
  color: #64748b;
  font-size: 12px;
}

.report-evidence-actions {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  flex-wrap: wrap;
  gap: 8px;
}

.next-round-ready-card {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  margin-top: 12px;
  padding: 14px;
  border-radius: 16px;
  border: 1px solid #bbf7d0;
  background:
    radial-gradient(
      circle at top right,
      rgba(34, 197, 94, 0.14),
      transparent 32%
    ),
    #f0fdf4;
}

.next-round-ready-card strong {
  display: block;
  margin-top: 4px;
  color: #14532d;
  font-size: 15px;
}

.next-round-ready-card p {
  margin: 6px 0 0;
  color: #475569;
  line-height: 1.55;
}

.next-round-ready-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-top: 10px;
}

.next-round-ready-actions {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  flex-wrap: wrap;
  gap: 8px;
  min-width: 260px;
}

.execution-health-alert {
  margin-top: 16px;
}

.device-health-panel {
  display: grid;
  gap: 14px;
}

.device-health-summary {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 14px;
  border-radius: 14px;
  background: linear-gradient(135deg, #eff6ff 0%, #ffffff 100%);
  border: 1px solid #bfdbfe;
}

.device-health-summary strong,
.device-health-summary span {
  display: block;
}

.device-health-summary strong {
  color: #0f172a;
  font-size: 16px;
}

.device-health-summary span {
  margin-top: 4px;
  color: #64748b;
  font-size: 12px;
}

.device-health-checks {
  display: grid;
  gap: 10px;
}

.device-health-check {
  display: grid;
  grid-template-columns: auto minmax(0, 1fr);
  gap: 10px;
  padding: 12px;
  border-radius: 12px;
  background: #f8fafc;
  border: 1px solid #e2e8f0;
}

.device-health-check.failed {
  background: #fff7ed;
  border-color: #fed7aa;
}

.device-health-check strong,
.device-health-check span,
.device-health-check p {
  display: block;
}

.device-health-check strong {
  color: #0f172a;
}

.device-health-check span {
  margin-top: 3px;
  color: #475569;
  line-height: 1.5;
}

.device-health-check p {
  margin: 6px 0 0;
  color: #b45309;
  font-size: 13px;
  line-height: 1.5;
}

.device-health-suggestions {
  padding: 12px;
  border-radius: 12px;
  background: #fffbeb;
  border: 1px solid #fde68a;
}

.device-health-suggestions strong {
  display: block;
  margin-bottom: 6px;
  color: #92400e;
}

.device-health-suggestions p {
  margin: 4px 0 0;
  color: #92400e;
  font-size: 13px;
  line-height: 1.5;
}

.target-acceptance-panel {
  margin-top: 16px;
  padding: 14px;
  border-radius: 16px;
  border: 1px solid #dbeafe;
  background: #f8fbff;
}

.target-acceptance-panel.acceptance-success {
  border-color: #bbf7d0;
  background: #f0fdf4;
}

.target-acceptance-panel.acceptance-warning {
  border-color: #fde68a;
  background: #fffbeb;
}

.target-acceptance-panel.acceptance-danger {
  border-color: #fecaca;
  background: #fef2f2;
}

.target-acceptance-guidance {
  display: grid;
  gap: 10px;
  margin-top: 12px;
}

.target-acceptance-guide-card {
  padding: 12px;
  border-radius: 12px;
  border: 1px solid rgba(251, 191, 36, 0.42);
  background: rgba(255, 255, 255, 0.78);
}

.acceptance-guide-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.acceptance-guide-head > div {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
}

.acceptance-guide-head strong {
  color: #0f172a;
  font-size: 13px;
}

.target-acceptance-guide-card p {
  margin: 8px 0 0;
  color: #475569;
  font-size: 13px;
  line-height: 1.55;
}

.acceptance-guide-details {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 8px;
}

.acceptance-guide-details span {
  padding: 5px 8px;
  border-radius: 999px;
  color: #475569;
  font-size: 12px;
  background: rgba(255, 255, 255, 0.82);
  border: 1px solid rgba(203, 213, 225, 0.72);
}

.acceptance-guide-targets {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 6px;
  margin-top: 10px;
}

.acceptance-guide-targets .el-tag {
  cursor: pointer;
}

.report-attribution-panel {
  margin-top: 16px;
  padding: 14px;
  border-radius: 16px;
  border: 1px solid #e2e8f0;
  background: #ffffff;
}

.report-attribution-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 10px;
}

.report-attribution-head strong,
.report-attribution-head span {
  display: block;
}

.report-attribution-head strong {
  color: #0f172a;
}

.report-attribution-head span {
  margin-top: 3px;
  color: #64748b;
  font-size: 12px;
}

.report-attribution-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 10px;
}

.report-attribution-item {
  display: grid;
  grid-template-columns: auto minmax(0, 1fr);
  gap: 10px;
  align-items: start;
  padding: 10px;
  border-radius: 12px;
  background: #f8fafc;
  border: 1px solid #e2e8f0;
}

.report-attribution-item strong,
.report-attribution-item span,
.report-attribution-item small {
  display: block;
}

.report-attribution-item strong {
  color: #0f172a;
  font-size: 13px;
}

.report-attribution-item span {
  margin-top: 3px;
  color: #475569;
  font-size: 12px;
  line-height: 1.45;
}

.report-attribution-item small {
  margin-top: 4px;
  color: #94a3b8;
  font-size: 12px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.target-acceptance-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 10px;
}

.target-acceptance-head strong {
  display: block;
  color: #0f172a;
}

.target-acceptance-head span {
  display: block;
  margin-top: 4px;
  color: #64748b;
  font-size: 12px;
  line-height: 1.5;
}

.target-acceptance-list {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 8px;
}

.target-acceptance-item {
  display: grid;
  grid-template-columns: auto minmax(0, 1fr);
  gap: 10px;
  align-items: flex-start;
  padding: 10px 12px;
  border-radius: 12px;
  border: 1px solid #e2e8f0;
  background: rgba(255, 255, 255, 0.86);
}

.target-acceptance-item.failed {
  border-color: #fed7aa;
  background: #fffaf3;
}

.target-acceptance-item strong {
  display: block;
  color: #0f172a;
}

.target-acceptance-item span,
.target-acceptance-item p,
.target-acceptance-actions {
  color: #64748b;
  font-size: 12px;
  line-height: 1.5;
}

.target-acceptance-item p {
  margin: 4px 0 0;
}

.target-acceptance-actions {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  margin-top: 10px;
}

.report-review-board {
  margin-top: 16px;
  padding: 14px;
  border-radius: 16px;
  border: 1px solid #e2e8f0;
  background: rgba(255, 255, 255, 0.82);
}

.report-review-header {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 10px;
}

.report-review-header strong {
  color: #0f172a;
}

.report-review-header span {
  color: #64748b;
  font-size: 12px;
}

.report-priority-list {
  display: grid;
  gap: 8px;
}

.report-priority-item {
  display: grid;
  grid-template-columns: auto minmax(0, 1fr) auto;
  gap: 10px;
  align-items: center;
  padding: 10px 12px;
  border-radius: 12px;
  border: 1px solid #e5e7eb;
  background: #fff;
}

.report-priority-item.priority-high {
  border-color: #fecaca;
  background: #fff7f7;
}

.report-priority-item.priority-medium {
  border-color: #fde68a;
  background: #fffbeb;
}

.report-priority-item strong {
  display: block;
  color: #0f172a;
  margin-bottom: 2px;
}

.priority-main {
  min-width: 0;
}

.priority-actions {
  display: flex;
  align-items: flex-end;
  flex-direction: column;
  gap: 4px;
}

.priority-actions .el-button + .el-button {
  margin-left: 0;
}

.priority-list-more {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  padding: 8px 10px;
  color: #64748b;
  font-size: 12px;
}

.report-priority-item p,
.priority-copy {
  margin: 0;
  color: #64748b;
  font-size: 12px;
  line-height: 1.55;
}

.priority-evidence-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 6px;
  margin-top: 8px;
}

.priority-evidence-preview {
  grid-template-columns: repeat(3, minmax(0, 1fr));
  margin-top: 10px;
}

.priority-evidence-row {
  padding: 8px 10px;
  border-radius: 10px;
  border: 1px solid rgba(203, 213, 225, 0.75);
  background: rgba(255, 255, 255, 0.72);
}

.priority-evidence-row span {
  display: block;
  margin-bottom: 3px;
  color: #64748b;
  font-size: 11px;
}

.priority-evidence-row strong {
  margin: 0;
  color: #334155;
  font-size: 12px;
  line-height: 1.45;
  font-weight: 600;
}

.priority-help {
  margin-top: 6px;
  padding-top: 6px;
  border-top: 1px dashed rgba(148, 163, 184, 0.45);
}

.priority-help span {
  color: #334155;
}

.report-clear-state {
  display: grid;
  gap: 4px;
  padding: 14px;
  border: 1px dashed #bbf7d0;
  border-radius: 12px;
  color: #166534;
  background: #f0fdf4;
}

.report-clear-state span {
  color: #64748b;
  font-size: 13px;
}

.report-detail-switch {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 12px;
  color: #64748b;
  font-size: 12px;
}

.post-run-guide-card {
  border-color: #bfdbfe;
  background: linear-gradient(135deg, #eff6ff 0%, #ffffff 68%);
}

.post-run-guide-main {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 14px;
}

.post-run-guide-summary strong {
  display: block;
  color: #0f172a;
  font-size: 17px;
  margin-bottom: 6px;
}

.post-run-guide-summary p {
  margin: 0;
  color: #475569;
  line-height: 1.6;
}

.post-run-guide-actions {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  flex-wrap: wrap;
  gap: 8px;
  min-width: 260px;
}

.post-run-step-list {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 10px;
}

.post-run-step {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  padding: 12px;
  border-radius: 12px;
  border: 1px solid #e2e8f0;
  background: rgba(255, 255, 255, 0.82);
}

.post-run-step.active {
  border-color: #60a5fa;
  box-shadow: 0 10px 24px rgba(37, 99, 235, 0.1);
}

.post-run-step-index {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  flex: 0 0 24px;
  height: 24px;
  border-radius: 999px;
  background: #2563eb;
  color: #fff;
  font-size: 12px;
  font-weight: 700;
}

.post-run-step strong {
  display: block;
  color: #0f172a;
  font-size: 13px;
  margin-bottom: 4px;
}

.post-run-step p {
  margin: 0;
  color: #64748b;
  font-size: 12px;
  line-height: 1.5;
}

.attachment-section {
  background: #f8fafc;
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

.issue-line {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.issue-review-item {
  display: grid;
  gap: 10px;
  padding: 12px;
  border-radius: 14px;
  border: 1px solid #fde68a;
  background: #fffbeb;
}

.issue-review-item.archived {
  border-color: #bbf7d0;
  background: #f0fdf4;
}

.issue-evidence-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 8px;
}

.issue-evidence-row {
  padding: 9px 10px;
  border-radius: 10px;
  border: 1px solid rgba(251, 191, 36, 0.42);
  background: rgba(255, 255, 255, 0.74);
}

.issue-evidence-row span,
.issue-evidence-row strong {
  display: block;
}

.issue-evidence-row span {
  margin-bottom: 4px;
  color: #92400e;
  font-size: 11px;
}

.issue-evidence-row strong {
  color: #334155;
  font-size: 12px;
  line-height: 1.5;
  font-weight: 600;
}

.issue-actions {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  justify-content: flex-end;
  gap: 4px;
}

.issue-line > span:first-child {
  color: #92400e;
  line-height: 1.6;
}

.ai-analysis-card {
  border-color: #bbf7d0;
}

.ai-progress-card {
  border-color: #fed7aa;
  background: linear-gradient(135deg, #fff7ed 0%, #ffffff 60%);
}

.ai-progress-card.failed {
  border-color: #fecaca;
  background: #fff7f7;
}

.ai-progress-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 14px;
  margin-bottom: 14px;
}

.ai-progress-header strong {
  display: block;
  color: #0f172a;
  font-size: 16px;
  margin-bottom: 4px;
}

.ai-progress-header p {
  margin: 0;
  color: #64748b;
}

.ai-retry-button {
  margin-top: 12px;
}

.ai-plan-board {
  display: grid;
  gap: 14px;
  margin: 14px 0;
  padding: 16px;
  border-radius: 18px;
  border: 1px solid #bfdbfe;
  background: linear-gradient(135deg, #eff6ff 0%, #ffffff 72%);
}

.ai-plan-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 14px;
}

.ai-plan-head strong {
  display: block;
  margin-top: 4px;
  color: #0f172a;
  font-size: 17px;
}

.ai-plan-head p {
  margin: 6px 0 0;
  color: #64748b;
  line-height: 1.55;
}

.ai-plan-metrics {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 10px;
}

.ai-plan-metrics > div,
.ai-plan-section {
  padding: 12px;
  border-radius: 14px;
  border: 1px solid #dbeafe;
  background: rgba(255, 255, 255, 0.78);
}

.ai-plan-metrics span,
.ai-plan-metrics strong {
  display: block;
}

.ai-plan-metrics span {
  color: #64748b;
  font-size: 12px;
}

.ai-plan-metrics strong {
  margin-top: 4px;
  color: #1d4ed8;
  font-size: 20px;
}

.ai-plan-section > strong,
.ai-plan-section-head > strong {
  color: #1e3a8a;
}

.ai-plan-section-head,
.ai-plan-two-col {
  display: flex;
  justify-content: space-between;
  gap: 12px;
}

.ai-plan-two-col > .ai-plan-section {
  flex: 1;
  min-width: 0;
}

.ai-plan-target-list {
  display: grid;
  gap: 8px;
  margin-top: 10px;
}

.ai-plan-target-item {
  display: flex;
  align-items: flex-start;
  gap: 12px;
  padding: 12px;
  border-radius: 12px;
  border: 1px solid #e2e8f0;
  background: #fff;
}

.ai-plan-target-item.selected {
  border-color: #60a5fa;
  background: #eff6ff;
}

.ai-plan-target-item.disabled {
  opacity: 0.68;
}

.ai-plan-target-item > div:nth-child(2) {
  flex: 1;
  min-width: 0;
}

.ai-plan-target-item strong,
.ai-plan-target-item p {
  display: block;
}

.ai-plan-target-item strong {
  color: #0f172a;
}

.ai-plan-target-item p {
  margin: 4px 0 8px;
  color: #475569;
  font-size: 13px;
  line-height: 1.55;
}

.ai-analysis-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
}

.ai-analysis-block {
  padding: 12px;
  border: 1px solid #dcfce7;
  border-radius: 12px;
  background: #f7fee7;
}

.ai-analysis-block strong {
  display: block;
  margin-bottom: 8px;
  color: #166534;
}

.ai-analysis-item {
  margin-top: 6px;
  color: #365314;
  font-size: 13px;
  line-height: 1.6;
}

.ai-analysis-item.traceable {
  display: flex;
  justify-content: space-between;
  gap: 10px;
  padding: 10px;
  border: 1px solid rgba(34, 197, 94, 0.18);
  border-radius: 10px;
  background: rgba(255, 255, 255, 0.72);
}

.ai-item-main {
  min-width: 0;
  flex: 1;
}

.ai-item-main strong {
  margin-bottom: 4px;
}

.ai-item-main p {
  margin: 0;
  color: #4b5563;
}

.ai-item-evidence {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
  margin-top: 8px;
  color: #64748b;
  font-size: 12px;
}

.ai-analysis-actions {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 10px;
  margin-top: 12px;
}

.ai-audit-panel {
  margin-top: 10px;
  padding-top: 8px;
  border-top: 1px dashed #bbf7d0;
}

.ai-audit-content {
  margin-top: 8px;
  padding: 12px;
  border-radius: 12px;
  background: #f8fafc;
  border: 1px solid #e2e8f0;
}

.ai-audit-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
  gap: 10px;
}

.ai-audit-grid div {
  padding: 10px;
  border-radius: 10px;
  background: #ffffff;
  border: 1px solid #e5e7eb;
}

.ai-audit-grid span,
.ai-audit-grid strong {
  display: block;
}

.ai-audit-grid span {
  color: #64748b;
  font-size: 12px;
}

.ai-audit-grid strong {
  margin-top: 4px;
  color: #0f172a;
  font-size: 14px;
}

.ai-audit-safety {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 10px;
}

.coverage-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 12px;
}

.coverage-card {
  display: grid;
  gap: 6px;
  padding: 14px;
  border-radius: 14px;
  background: #f8fafc;
  border: 1px solid #e5e7eb;
}

.coverage-card.warning {
  background: #fff7ed;
  border-color: #fed7aa;
}

.coverage-card strong {
  color: #0f172a;
  font-size: 24px;
}

.coverage-card small,
.coverage-label {
  color: #64748b;
}

.keyword-row,
.issue-type-list {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 14px;
}

.keyword-row-muted {
  opacity: 0.78;
}

.page-map-assets-card {
  border-color: #bbf7d0;
  background:
    radial-gradient(
      circle at top right,
      rgba(34, 197, 94, 0.12),
      transparent 34%
    ),
    linear-gradient(180deg, #ffffff 0%, #f8fffb 100%);
}

.page-map-assets-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 12px;
  margin-bottom: 10px;
}

.page-map-asset-item {
  padding: 14px;
  border-radius: 14px;
  border: 1px solid #dcfce7;
  background: rgba(255, 255, 255, 0.82);
}

.page-map-asset-item strong {
  display: block;
  color: #166534;
  font-size: 24px;
  line-height: 1.2;
}

.page-map-asset-item span {
  color: #64748b;
  font-size: 13px;
}

.page-map-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 14px;
}

.page-map-card {
  display: grid;
  grid-template-columns: 96px minmax(0, 1fr);
  gap: 14px;
  padding: 14px;
  border-radius: 16px;
  background: #f8fafc;
  border: 1px solid #e5e7eb;
}

.page-map-card.danger {
  background: #fff7f7;
  border-color: #fecaca;
}

.page-map-card.highlighted {
  background: #fffbeb;
  border-color: #f59e0b;
  box-shadow:
    0 0 0 3px rgba(245, 158, 11, 0.18),
    0 16px 34px rgba(146, 64, 14, 0.12);
}

.highlighted-control {
  font-weight: 700;
  box-shadow: 0 0 0 2px rgba(245, 158, 11, 0.22);
}

.page-map-shot-wrap {
  position: relative;
  width: 96px;
  min-height: 132px;
  overflow: hidden;
  border-radius: 12px;
  border: 1px solid #e5e7eb;
  background: #fff;
  cursor: zoom-in;
  transition:
    transform 0.16s ease,
    box-shadow 0.16s ease;
}

.page-map-shot-wrap:hover {
  transform: translateY(-1px);
  box-shadow: 0 10px 22px rgba(15, 23, 42, 0.16);
}

.page-map-shot {
  display: block;
  width: 100%;
  height: 100%;
  background: #fff;
}

.page-map-shot.placeholder {
  width: 96px;
  min-height: 132px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 12px;
  border: 1px solid #e5e7eb;
  color: #94a3b8;
  font-size: 12px;
}

.page-map-overlay-layer {
  position: absolute;
  inset: 0;
  pointer-events: none;
}

.page-click-overlay {
  position: absolute;
  min-width: 10px;
  min-height: 10px;
  border: 2px solid rgba(37, 99, 235, 0.92);
  border-radius: 5px;
  background: rgba(37, 99, 235, 0.16);
  box-shadow: 0 0 0 2px rgba(37, 99, 235, 0.12);
}

.page-click-overlay span {
  position: absolute;
  left: -7px;
  top: -9px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 16px;
  height: 16px;
  padding: 0 4px;
  border-radius: 999px;
  color: #fff;
  background: #2563eb;
  font-size: 10px;
  font-weight: 800;
  line-height: 1;
  box-shadow: 0 4px 10px rgba(15, 23, 42, 0.22);
}

.page-click-overlay.highlighted {
  z-index: 3;
  border-color: #f59e0b;
  background: rgba(245, 158, 11, 0.22);
  box-shadow:
    0 0 0 3px rgba(245, 158, 11, 0.24),
    0 0 18px rgba(245, 158, 11, 0.42);
}

.page-click-overlay.highlighted span {
  background: #f59e0b;
}

.page-click-overlay.point {
  width: 16px;
  height: 16px;
  min-width: 16px;
  min-height: 16px;
  border-radius: 999px;
  transform: translate(-50%, -50%);
}

.page-click-overlay.swipe {
  min-width: 24px;
  min-height: 0;
  height: 0 !important;
  border: 0;
  border-top: 3px solid rgba(37, 99, 235, 0.92);
  border-radius: 0;
  background: transparent;
  box-shadow: none;
}

.page-click-overlay.swipe::after {
  content: "";
  position: absolute;
  right: -1px;
  top: -6px;
  width: 0;
  height: 0;
  border-top: 5px solid transparent;
  border-bottom: 5px solid transparent;
  border-left: 8px solid rgba(37, 99, 235, 0.92);
}

.page-click-overlay.swipe.highlighted {
  border-top-color: #f59e0b;
}

.page-click-overlay.swipe.highlighted::after {
  border-left-color: #f59e0b;
}

.evidence-preview-layout {
  display: grid;
  grid-template-columns: minmax(280px, 420px) minmax(220px, 1fr);
  gap: 18px;
  align-items: start;
}

.evidence-preview-shot-wrap {
  position: relative;
  width: min(100%, 420px);
  max-height: 72vh;
  overflow: hidden;
  border-radius: 18px;
  border: 1px solid #dbe3ef;
  background: #0f172a;
  box-shadow: 0 18px 46px rgba(15, 23, 42, 0.18);
}

.evidence-preview-shot {
  display: block;
  width: 100%;
  height: 100%;
  background: #fff;
}

.evidence-preview-shot-wrap .page-click-overlay {
  border-width: 3px;
  border-radius: 8px;
}

.evidence-preview-shot-wrap .page-click-overlay span {
  left: -10px;
  top: -12px;
  min-width: 22px;
  height: 22px;
  font-size: 12px;
}

.evidence-preview-shot-wrap .page-click-overlay.point {
  width: 22px;
  height: 22px;
  min-width: 22px;
  min-height: 22px;
}

.evidence-preview-shot-wrap .page-click-overlay.swipe {
  border-top-width: 4px;
}

.evidence-preview-side {
  display: grid;
  gap: 12px;
  min-width: 0;
}

.evidence-preview-side-title {
  color: #0f172a;
  font-size: 15px;
  font-weight: 800;
}

.evidence-preview-side-title.secondary {
  margin-top: 6px;
  color: #475569;
  font-size: 13px;
}

.evidence-preview-focus-card {
  display: grid;
  gap: 10px;
  padding: 14px;
  border-radius: 16px;
  background: linear-gradient(180deg, #fffbeb 0%, #fff7ed 100%);
  border: 1px solid #fbbf24;
  box-shadow: 0 10px 24px rgba(146, 64, 14, 0.1);
}

.evidence-focus-header {
  display: flex;
  align-items: center;
  gap: 8px;
  color: #92400e;
}

.evidence-focus-row {
  display: grid;
  grid-template-columns: 44px minmax(0, 1fr);
  gap: 10px;
  align-items: start;
  color: #334155;
  font-size: 13px;
  line-height: 1.55;
}

.evidence-focus-row span {
  color: #64748b;
}

.evidence-focus-row strong {
  font-weight: 700;
  word-break: break-word;
}

.evidence-focus-row.issue strong {
  color: #b45309;
}

.evidence-preview-focus-card p {
  margin: 0;
  padding-top: 8px;
  color: #7c2d12;
  border-top: 1px dashed #fdba74;
  font-size: 12px;
  line-height: 1.6;
}

.evidence-preview-control-list {
  display: grid;
  gap: 8px;
  max-height: 70vh;
  overflow: auto;
  padding-right: 4px;
}

.evidence-preview-control {
  display: grid;
  grid-template-columns: auto minmax(0, 1fr);
  gap: 8px;
  align-items: start;
  padding: 9px 10px;
  border-radius: 12px;
  color: #334155;
  background: #f8fafc;
  border: 1px solid #e5e7eb;
  font-size: 12px;
  line-height: 1.5;
  cursor: pointer;
  transition:
    border-color 0.18s ease,
    box-shadow 0.18s ease,
    transform 0.18s ease;
}

.evidence-preview-control:hover {
  border-color: #93c5fd;
  box-shadow: 0 8px 18px rgba(37, 99, 235, 0.08);
  transform: translateY(-1px);
}

.evidence-preview-control.highlighted {
  color: #92400e;
  background: #fffbeb;
  border-color: #f59e0b;
}

.conversion-review-next {
  margin-top: 6px;
  color: #64748b;
  font-size: 12px;
  line-height: 1.55;
}

.page-map-body {
  min-width: 0;
}

.page-map-title {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  color: #0f172a;
  font-weight: 700;
}

.page-map-title .clickable {
  cursor: pointer;
}

.page-map-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 8px 12px;
  margin-top: 8px;
  color: #475569;
  font-size: 12px;
}

.page-map-activity {
  margin-top: 8px;
  color: #64748b;
  font-size: 12px;
  word-break: break-all;
}

.page-map-controls {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-top: 10px;
}

.page-map-issues {
  display: grid;
  gap: 6px;
  margin-top: 10px;
}

.page-map-issue {
  padding: 8px 10px;
  border-radius: 10px;
  color: #991b1b;
  background: #fff1f2;
  border: 1px solid #fecdd3;
  font-size: 12px;
  line-height: 1.5;
}

.page-map-issue-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}

.page-map-issue-head > div {
  display: flex;
  align-items: center;
  gap: 6px;
  min-width: 0;
}

.page-map-issue-head strong {
  color: #7f1d1d;
  font-size: 13px;
}

.page-map-issue p {
  margin: 6px 0 0;
  color: #991b1b;
}

.page-map-issue-evidence {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 6px;
  margin-top: 8px;
}

.page-map-issue-evidence div {
  padding: 7px 8px;
  border-radius: 8px;
  border: 1px solid rgba(254, 205, 211, 0.9);
  background: rgba(255, 255, 255, 0.72);
}

.page-map-issue-evidence span,
.page-map-issue-evidence strong {
  display: block;
}

.page-map-issue-evidence span {
  margin-bottom: 3px;
  color: #9f1239;
  font-size: 11px;
}

.page-map-issue-evidence strong {
  color: #334155;
  font-size: 12px;
  line-height: 1.45;
  font-weight: 600;
}

.entry-nav-list {
  display: grid;
  gap: 10px;
}

.entry-nav-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 12px 14px;
  border-radius: 12px;
  background: #f8fafc;
  border: 1px solid #e5e7eb;
}

.entry-nav-item.failed {
  background: #fff7ed;
  border-color: #fed7aa;
}

.section-title {
  font-weight: 700;
}

.step-table :deep(.el-table__expanded-cell) {
  background: #f8fafc;
}

.step-table :deep(.review-step-highlight td) {
  background: #fff7ed !important;
  transition: background 0.2s ease;
}

.step-table :deep(.review-step-highlight .step-primary) {
  color: #c2410c;
}

.step-detail-panel {
  padding: 12px 18px;
}

.detail-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px 24px;
}

.detail-label {
  display: block;
  margin-bottom: 4px;
  color: #64748b;
  font-size: 12px;
}

.detail-value {
  color: #1f2937;
  font-size: 13px;
  line-height: 1.6;
  word-break: break-all;
}

.decision-panel {
  margin-top: 14px;
  padding: 12px;
  border: 1px solid #dbeafe;
  border-radius: 10px;
  background: #eff6ff;
}

.decision-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  margin-bottom: 8px;
}

.decision-row {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 8px;
}

.decision-label {
  color: #475569;
  font-size: 12px;
  font-weight: 700;
}

.decision-reasons {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 10px;
}

.step-evidence-panel {
  margin-top: 14px;
  padding: 12px;
  border: 1px solid #fed7aa;
  border-radius: 12px;
  background: linear-gradient(135deg, #fff7ed 0%, #ffffff 76%);
}

.step-evidence-head,
.step-issue-cell {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
}

.step-evidence-head {
  justify-content: space-between;
  margin-bottom: 10px;
}

.step-evidence-head strong {
  color: #9a3412;
}

.step-evidence-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 8px;
}

.step-evidence-row {
  padding: 9px 10px;
  border-radius: 10px;
  border: 1px solid rgba(251, 146, 60, 0.36);
  background: rgba(255, 255, 255, 0.78);
}

.step-evidence-row span,
.step-evidence-row strong {
  display: block;
}

.step-evidence-row span {
  margin-bottom: 4px;
  color: #9a3412;
  font-size: 11px;
}

.step-evidence-row strong {
  color: #334155;
  font-size: 12px;
  line-height: 1.5;
}

.step-issue-cell {
  color: #475569;
  font-size: 12px;
  line-height: 1.5;
}

.step-primary {
  color: #111827;
  font-weight: 700;
}

.step-secondary {
  margin-top: 4px;
  color: #6b7280;
  font-size: 12px;
}

.step-shot {
  width: 48px;
  height: 72px;
  border-radius: 8px;
  border: 1px solid #e5e7eb;
}

.annotated-shot {
  width: 64px;
  height: 96px;
  box-shadow: 0 8px 18px rgba(15, 23, 42, 0.12);
}

.task-name-cell {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
}

.task-name-cell > span:first-child {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.task-stage {
  margin-top: 4px;
  color: #64748b;
  font-size: 12px;
  line-height: 1.3;
}

.task-stage.stale {
  color: #b45309;
  font-weight: 600;
}

.iteration-card {
  border-color: #bbf7d0;
  background: linear-gradient(135deg, #f0fdf4 0%, #ffffff 72%);
}

.ai-action-proposals {
  margin-top: 16px;
  padding: 14px;
  border-radius: 14px;
  background: #f8fafc;
  border: 1px solid #dbeafe;
}

.proposal-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 10px;
}

.proposal-header > div:first-child {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
}

.proposal-header-actions {
  display: flex;
  gap: 8px;
  flex-shrink: 0;
}

.ai-action-item {
  display: flex;
  align-items: flex-start;
  gap: 14px;
  padding: 12px;
  border-radius: 12px;
  background: #ffffff;
  border: 1px solid #e5e7eb;
}

.ai-action-item.selected {
  border-color: #93c5fd;
  background: #eff6ff;
}

.ai-action-item.disabled {
  opacity: 0.72;
}

.ai-action-item > div:nth-child(2) {
  flex: 1;
  min-width: 0;
}

.ai-action-item + .ai-action-item {
  margin-top: 8px;
}

.ai-action-item p {
  margin: 6px 0 0;
  color: #64748b;
  font-size: 12px;
  line-height: 1.5;
}

.proposal-tags {
  display: flex;
  justify-content: flex-end;
  flex-wrap: wrap;
  gap: 6px;
  min-width: 120px;
}

.iteration-source {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 6px;
  margin-bottom: 12px;
}

.iteration-chain-summary {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 12px;
}

.iteration-chain {
  margin: 12px 0;
  padding: 12px;
  border-radius: 14px;
  background: rgba(255, 255, 255, 0.72);
  border: 1px solid #dcfce7;
}

.chain-title {
  margin-bottom: 10px;
  color: #14532d;
  font-size: 13px;
  font-weight: 700;
}

.chain-node {
  display: grid;
  grid-template-columns: auto minmax(0, 1fr) auto;
  align-items: center;
  gap: 10px;
  padding: 10px;
  border-radius: 12px;
  background: #f8fafc;
  border: 1px solid #e5e7eb;
}

.chain-node + .chain-node {
  margin-top: 8px;
}

.chain-node.current {
  background: #eff6ff;
  border-color: #93c5fd;
}

.chain-node-index {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 28px;
  border-radius: 999px;
  color: #ffffff;
  background: #16a34a;
  font-weight: 700;
}

.chain-node.current .chain-node-index {
  background: #2563eb;
}

.chain-node-main {
  min-width: 0;
}

.chain-node-main strong,
.chain-node-main small {
  display: block;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.chain-node-main strong {
  color: #0f172a;
}

.chain-node-main small {
  margin-top: 4px;
  color: #64748b;
  font-size: 12px;
}

.chain-node-metrics {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  justify-content: flex-end;
  gap: 8px;
  color: #475569;
  font-size: 12px;
}

.iteration-action-audit {
  margin-top: 12px;
  padding: 12px;
  border-radius: 12px;
  background: #ffffff;
  border: 1px solid #dcfce7;
}

.audit-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  margin-bottom: 10px;
}

.audit-action-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  padding: 8px 10px;
  border-radius: 10px;
  background: #f8fafc;
  color: #334155;
  font-size: 13px;
}

.audit-action-item + .audit-action-item {
  margin-top: 6px;
}

.iteration-effect-alert {
  margin-top: 12px;
}

.iteration-next-suggestion {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 14px;
  margin-top: 12px;
  padding: 12px 14px;
  border-radius: 14px;
  background: #f8fafc;
  border: 1px solid #dbeafe;
}

.iteration-next-suggestion strong {
  color: #0f172a;
}

.iteration-next-suggestion p {
  margin: 4px 0 0;
  color: #64748b;
  font-size: 13px;
  line-height: 1.5;
}

.iteration-remedy {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 10px;
  margin-top: 10px;
  padding: 10px 12px;
  border-radius: 12px;
  background: #fffbeb;
  border: 1px solid #fde68a;
}

.iteration-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 12px;
  margin-top: 14px;
}

.iteration-metric {
  padding: 12px;
  border-radius: 12px;
  background: #ffffff;
  border: 1px solid #dcfce7;
}

.iteration-metric span,
.iteration-metric small {
  display: block;
  color: #64748b;
  font-size: 12px;
}

.iteration-metric strong {
  display: block;
  margin: 6px 0 4px;
  color: #14532d;
  font-size: 22px;
}

.metric-diff-positive {
  color: #16a34a !important;
}

.metric-diff-warning {
  color: #d97706 !important;
}

.metric-diff-muted,
.metric-diff-neutral {
  color: #64748b !important;
}

@media (max-width: 900px) {
  .hero-card {
    flex-direction: column;
  }

  .decision-summary-main,
  .decision-evidence-grid {
    grid-template-columns: 1fr;
  }

  .report-workbench-main,
  .report-workbench-metrics,
  .report-workflow-strip,
  .roadmap-progress-board,
  .priority-evidence-grid,
  .priority-evidence-preview,
  .issue-evidence-grid,
  .page-map-issue-evidence,
  .report-attribution-grid,
  .report-priority-item {
    grid-template-columns: 1fr;
  }

  .roadmap-stage-item {
    grid-template-columns: 1fr;
  }

  .report-workbench-actions {
    justify-content: flex-start;
    max-width: none;
  }

  .priority-actions {
    align-items: flex-start;
    flex-direction: row;
    flex-wrap: wrap;
  }

  .report-tabbar {
    align-items: flex-start;
    flex-direction: column;
  }

  .report-evidence-shortcuts {
    align-items: flex-start;
    flex-direction: column;
  }

  .report-evidence-actions {
    justify-content: flex-start;
  }

  .coverage-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .ai-plan-head,
  .ai-plan-section-head,
  .ai-plan-two-col {
    align-items: flex-start;
    flex-direction: column;
  }

  .ai-plan-metrics,
  .ai-analysis-grid,
  .ai-audit-grid {
    grid-template-columns: 1fr;
  }

  .page-map-assets-grid {
    grid-template-columns: 1fr;
  }

  .page-map-grid {
    grid-template-columns: 1fr;
  }

  .detail-grid {
    grid-template-columns: 1fr;
  }

  .chain-node {
    grid-template-columns: auto minmax(0, 1fr);
  }

  .chain-node-metrics {
    grid-column: 1 / -1;
    justify-content: flex-start;
  }

  .iteration-next-suggestion {
    align-items: flex-start;
    flex-direction: column;
  }

  .attachment-card {
    align-items: stretch;
    flex-direction: column;
  }

  .iteration-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}
</style>
