<template>
  <div class="data-factory-container">
    <el-card class="header-card">
      <div class="header-content">
        <h1 class="page-title" @click="goToHome">
          <el-icon class="title-icon"><DataLine /></el-icon>
          {{ $t("dataFactory.title") }}
        </h1>
        <p class="page-subtitle">{{ $t("dataFactory.subtitle") }}</p>
        <div class="header-actions">
          <el-button-group>
            <el-button
              :type="viewMode === 'category' ? 'primary' : ''"
              @click="viewMode = 'category'"
            >
              <el-icon><Menu /></el-icon>
              {{ $t("dataFactory.viewMode.category") }}
            </el-button>
            <el-button
              :type="viewMode === 'scenario' ? 'primary' : ''"
              @click="viewMode = 'scenario'"
            >
              <el-icon><Grid /></el-icon>
              {{ $t("dataFactory.viewMode.scenario") }}
            </el-button>
            <el-button
              :type="viewMode === 'account_pool' ? 'primary' : ''"
              @click="openAccountPool"
            >
              <el-icon><User /></el-icon>
              账号池
            </el-button>
            <el-button
              :type="viewMode === 'business_load' ? 'primary' : ''"
              @click="openBusinessLoad"
            >
              <el-icon><VideoPlay /></el-icon>
              业务压测
            </el-button>
          </el-button-group>
          <el-button type="info" @click="showHistory = true">
            <el-icon><Clock /></el-icon>
            {{ $t("dataFactory.actions.history") }}
          </el-button>
        </div>
      </div>
    </el-card>

    <!-- 工具分类视图 -->
    <div v-if="viewMode === 'category'" class="category-view">
      <div
        v-for="category in filteredCategories()"
        :key="category.category"
        class="category-section"
      >
        <el-card class="category-card">
          <template #header>
            <div class="category-header">
              <el-icon :class="`category-icon ${category.icon}`">
                <component :is="getIcon(category.icon)" />
              </el-icon>
              <span class="category-title">{{
                getCategoryName(category.category)
              }}</span>
              <el-tag size="small">{{
                $t("dataFactory.toolCount", { count: category.tools.length })
              }}</el-tag>
              <el-button
                v-if="currentScenario"
                size="small"
                @click.stop="clearScenario"
                style="margin-left: auto"
              >
                {{ $t("dataFactory.actions.clearFilter") }}
              </el-button>
            </div>
          </template>
          <div class="tools-grid">
            <div
              v-for="tool in category.tools"
              :key="tool.name"
              class="tool-item"
              @click="openTool(tool, category.category)"
            >
              <div class="tool-icon">
                <el-icon
                  ><component :is="getIcon(tool.icon || 'operation')"
                /></el-icon>
              </div>
              <div class="tool-info">
                <h4 class="tool-name">
                  {{ getToolDisplayName(tool.name) || tool.display_name }}
                </h4>
                <p class="tool-desc">
                  {{ getToolDescription(tool.name) || tool.description }}
                </p>
              </div>
              <el-icon class="tool-arrow"><ArrowRight /></el-icon>
            </div>
          </div>
        </el-card>
      </div>
    </div>

    <!-- 使用场景视图 -->
    <div v-else-if="viewMode === 'scenario'" class="scenario-view">
      <el-row :gutter="20">
        <el-col
          :span="8"
          v-for="scenario in scenarios"
          :key="scenario.scenario"
        >
          <el-card class="scenario-card" @click="filterByScenario(scenario)">
            <div class="scenario-content">
              <el-icon class="scenario-icon">
                <component :is="getScenarioIcon(scenario.scenario)" />
              </el-icon>
              <h3 class="scenario-title">
                {{ getScenarioName(scenario.scenario) }}
              </h3>
              <p class="scenario-desc">
                {{ getScenarioDesc(scenario.scenario) }}
              </p>
              <div class="scenario-stats">
                <el-tag size="small">{{
                  $t("dataFactory.toolCount", { count: scenario.tool_count })
                }}</el-tag>
              </div>
            </div>
          </el-card>
        </el-col>
      </el-row>
    </div>

    <!-- 账号池视图 -->
    <div v-else-if="viewMode === 'account_pool'" class="account-pool-view">
      <el-row :gutter="16" class="account-stats">
        <el-col :span="6">
          <el-card shadow="hover">
            <div class="stat-card">
              <span class="stat-label">账号总数</span>
              <strong>{{ accountStats.total || 0 }}</strong>
            </div>
          </el-card>
        </el-col>
        <el-col :span="6">
          <el-card shadow="hover">
            <div class="stat-card">
              <span class="stat-label">可用账号</span>
              <strong class="success">{{ accountStats.available || 0 }}</strong>
            </div>
          </el-card>
        </el-col>
        <el-col :span="6">
          <el-card shadow="hover">
            <div class="stat-card">
              <span class="stat-label">使用中</span>
              <strong class="warning">{{ accountStats.in_use || 0 }}</strong>
            </div>
          </el-card>
        </el-col>
        <el-col :span="6">
          <el-card shadow="hover">
            <div class="stat-card">
              <span class="stat-label">不可用</span>
              <strong class="danger">{{
                (accountStats.disabled || 0) + (accountStats.invalid || 0)
              }}</strong>
            </div>
          </el-card>
        </el-col>
      </el-row>

      <el-card class="account-pool-card">
        <template #header>
          <div class="account-toolbar">
            <div>
              <h3>业务账号池</h3>
              <p>
                维护可复用的业务账号，供进房压测、IM
                刷屏、发布组队等场景分配使用。
              </p>
            </div>
            <div class="account-actions">
              <el-button @click="fetchAccountPool">刷新</el-button>
              <el-button type="success" @click="openAccountAllocateDialog"
                >分配账号</el-button
              >
              <el-button type="primary" @click="openAccountDialog()"
                >添加账号</el-button
              >
              <el-button type="warning" @click="accountImportVisible = true"
                >批量导入</el-button
              >
            </div>
          </div>
        </template>

        <el-form :inline="true" class="account-filters">
          <el-form-item label="环境">
            <el-select
              v-model="accountFilters.environment"
              clearable
              placeholder="选择环境"
              style="width: 140px"
            >
              <el-option
                v-for="item in accountOptions.environments"
                :key="item.value"
                :label="item.label"
                :value="item.value"
              />
            </el-select>
          </el-form-item>
          <el-form-item label="业务域">
            <el-select
              v-model="accountFilters.business_domain"
              clearable
              placeholder="选择业务域"
              style="width: 140px"
            >
              <el-option
                v-for="item in accountOptions.business_domains"
                :key="item.value"
                :label="item.label"
                :value="item.value"
              />
            </el-select>
          </el-form-item>
          <el-form-item label="状态">
            <el-select
              v-model="accountFilters.status"
              clearable
              placeholder="选择状态"
              style="width: 140px"
            >
              <el-option
                v-for="item in accountOptions.statuses"
                :key="item.value"
                :label="item.label"
                :value="item.value"
              />
            </el-select>
          </el-form-item>
          <el-form-item label="关键词">
            <el-input
              v-model="accountFilters.keyword"
              clearable
              placeholder="账号、手机号、备注/标签"
              style="width: 220px"
            />
          </el-form-item>
          <el-form-item>
            <el-button type="primary" @click="handleAccountSearch"
              >查询</el-button
            >
            <el-button @click="resetAccountFilters">重置</el-button>
          </el-form-item>
        </el-form>

        <el-table
          v-loading="accountLoading"
          :data="accountRecords"
          border
          stripe
        >
          <el-table-column
            prop="environment_display"
            label="环境"
            width="100"
          />
          <el-table-column
            prop="business_domain_display"
            label="业务域"
            width="100"
          />
          <el-table-column prop="account_no" label="账号" min-width="150" />
          <el-table-column prop="phone" label="手机号" min-width="130" />
          <el-table-column prop="user_id" label="用户ID" min-width="120" />
          <el-table-column prop="nickname" label="昵称" min-width="120" />
          <el-table-column label="凭据" width="120">
            <template #default="{ row }">
              <el-tag v-if="row.has_password" size="small" type="info"
                >密码</el-tag
              >
              <el-tag v-if="row.has_token" size="small" type="warning"
                >Token</el-tag
              >
              <span v-if="!row.has_password && !row.has_token" class="muted"
                >无</span
              >
            </template>
          </el-table-column>
          <el-table-column label="状态" width="110">
            <template #default="{ row }">
              <el-tag :type="getAccountStatusType(row.status)">
                {{ row.status_display || row.status }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="purpose" label="用途" min-width="140" />
          <el-table-column label="锁定人" width="120">
            <template #default="{ row }">{{
              row.locked_by_name || "-"
            }}</template>
          </el-table-column>
          <el-table-column label="更新时间" width="170">
            <template #default="{ row }">{{
              formatDateTime(row.updated_at)
            }}</template>
          </el-table-column>
          <el-table-column label="操作" width="210" fixed="right">
            <template #default="{ row }">
              <el-button size="small" @click="openAccountDialog(row)"
                >编辑</el-button
              >
              <el-button
                v-if="row.status === 'in_use'"
                size="small"
                type="success"
                @click="releaseAccount(row)"
                >释放</el-button
              >
              <el-button size="small" type="danger" @click="deleteAccount(row)"
                >删除</el-button
              >
            </template>
          </el-table-column>
        </el-table>

        <div class="pagination-container">
          <el-pagination
            v-model:current-page="accountCurrentPage"
            v-model:page-size="accountPageSize"
            :page-sizes="[20, 50, 100, 200]"
            :total="accountTotal"
            layout="total, sizes, prev, pager, next, jumper"
            @size-change="handleAccountSizeChange"
            @current-change="handleAccountPageChange"
          />
        </div>
      </el-card>
    </div>

    <!-- 业务压测任务 -->
    <div v-else-if="viewMode === 'business_load'" class="business-load-view">
      <el-card class="business-load-card">
        <template #header>
          <div class="account-toolbar">
            <div>
              <h3>
                {{
                  businessLoadActiveScenario
                    ? currentBusinessLoadScenarioCard?.label
                    : "业务压测场景"
                }}
              </h3>
              <p>
                {{
                  businessLoadActiveScenario
                    ? currentBusinessLoadScenarioCard?.description ||
                      "查看当前场景下的压测任务，并创建新的场景任务。"
                    : "先选择具体压测场景，再进入场景内页查看任务列表和创建任务。"
                }}
              </p>
            </div>
            <div class="account-actions">
              <el-button
                v-if="businessLoadActiveScenario"
                @click="backBusinessLoadScenarioHome"
                >返回场景</el-button
              >
              <el-button
                v-if="businessLoadActiveScenario"
                @click="fetchBusinessLoadTasks"
                >刷新</el-button
              >
              <el-button
                v-if="businessLoadActiveScenario"
                type="primary"
                @click="
                  openBusinessLoadDialog(null, businessLoadActiveScenario)
                "
              >
                创建任务
              </el-button>
            </div>
          </div>
        </template>

        <el-alert
          title="建议先完成预检查，再执行小流量试跑。发布组队和 IM 场景会产生真实业务流量，请控制账号数和频率。"
          type="info"
          :closable="false"
          show-icon
          class="tool-alert"
        />

        <div v-if="!businessLoadActiveScenario" class="business-scenario-board">
          <div class="section-heading">
            <div>
              <h4>选择压测场景</h4>
              <p>
                这里不再展示任务列表。点击场景后进入内页，只看该场景的任务和创建入口。
              </p>
            </div>
          </div>
          <div class="business-scenario-grid">
            <div
              v-for="scenario in businessLoadScenarioCards"
              :key="scenario.value"
              class="business-scenario-card"
              :class="{ disabled: scenario.disabled }"
              @click="enterBusinessLoadScenario(scenario.value)"
            >
              <div class="scenario-card-top">
                <el-icon><component :is="scenario.icon" /></el-icon>
                <el-tag size="small" :type="scenario.statusType">{{
                  scenario.badge
                }}</el-tag>
              </div>
              <h4>{{ scenario.label }}</h4>
              <p>{{ scenario.description }}</p>
              <div class="scenario-card-footer">
                <span>{{ scenario.fit }}</span>
                <el-button
                  size="small"
                  type="primary"
                  plain
                  :disabled="scenario.disabled"
                  @click.stop="enterBusinessLoadScenario(scenario.value)"
                >
                  进入
                </el-button>
              </div>
            </div>
          </div>
        </div>

        <div v-else class="business-scenario-detail">
          <el-form :inline="true" class="account-filters">
            <el-form-item label="状态">
              <el-select
                v-model="businessLoadFilters.status"
                clearable
                placeholder="选择状态"
                style="width: 140px"
              >
                <el-option
                  v-for="item in businessLoadOptions.statuses"
                  :key="item.value"
                  :label="item.label"
                  :value="item.value"
                />
              </el-select>
            </el-form-item>
            <el-form-item label="关键词">
              <el-input
                v-model="businessLoadFilters.keyword"
                clearable
                placeholder="任务名称、用途"
                style="width: 220px"
              />
            </el-form-item>
            <el-form-item>
              <el-button type="primary" @click="handleBusinessLoadSearch"
                >查询</el-button
              >
              <el-button @click="resetBusinessLoadTaskFilters">重置</el-button>
            </el-form-item>
          </el-form>

          <el-table
            v-loading="businessLoadLoading"
            :data="businessLoadTasks"
            border
            stripe
            @row-dblclick="openBusinessLoadDetail"
          >
            <el-table-column
              prop="name"
              label="任务名称"
              min-width="210"
              show-overflow-tooltip
            />
            <el-table-column label="目标与规模" min-width="280">
              <template #default="{ row }">
                <div class="task-brief">
                  <strong>{{ getBusinessLoadTargetBrief(row) }}</strong>
                  <span>{{ getBusinessLoadScaleBrief(row) }}</span>
                </div>
              </template>
            </el-table-column>
            <el-table-column label="状态" width="110">
              <template #default="{ row }">
                <el-tag :type="getBusinessLoadStatusType(row.status)">
                  {{ getBusinessLoadStatusText(row) }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column label="最近结果" min-width="220">
              <template #default="{ row }">
                <span class="muted">{{
                  row.metrics?.last_trial_run?.message ||
                  row.metrics?.last_precheck?.message ||
                  "暂无执行结果"
                }}</span>
              </template>
            </el-table-column>
            <el-table-column label="更新时间" width="170">
              <template #default="{ row }">{{
                formatDateTime(row.updated_at)
              }}</template>
            </el-table-column>
            <el-table-column label="操作" width="320" fixed="right">
              <template #default="{ row }">
                <el-button
                  size="small"
                  type="primary"
                  plain
                  @click="openBusinessLoadDetail(row)"
                  >详情</el-button
                >
                <el-button size="small" @click="openBusinessLoadDialog(row)"
                  >编辑</el-button
                >
                <el-button size="small" @click="precheckBusinessLoadTask(row)"
                  >预检查</el-button
                >
                <el-button
                  size="small"
                  type="success"
                  :disabled="row.status === 'running'"
                  @click="startBusinessLoadTask(row)"
                >
                  启动任务
                </el-button>
                <el-dropdown
                  trigger="click"
                  @command="
                    (command) => handleBusinessLoadCommand(command, row)
                  "
                >
                  <el-button size="small">更多</el-button>
                  <template #dropdown>
                    <el-dropdown-menu>
                      <el-dropdown-item
                        command="trial"
                        :disabled="row.status === 'running'"
                        >小流量试跑</el-dropdown-item
                      >
                      <el-dropdown-item
                        v-if="['ready', 'running'].includes(row.status)"
                        command="stop"
                        >停止</el-dropdown-item
                      >
                      <el-dropdown-item divided command="delete"
                        >删除</el-dropdown-item
                      >
                    </el-dropdown-menu>
                  </template>
                </el-dropdown>
              </template>
            </el-table-column>
          </el-table>

          <div class="pagination-container">
            <el-pagination
              v-model:current-page="businessLoadCurrentPage"
              v-model:page-size="businessLoadPageSize"
              :page-sizes="[20, 50, 100]"
              :total="businessLoadTotal"
              layout="total, sizes, prev, pager, next, jumper"
              @size-change="handleBusinessLoadSizeChange"
              @current-change="handleBusinessLoadPageChange"
            />
          </div>
        </div>
      </el-card>
    </div>

    <el-drawer
      v-model="businessLoadDetailVisible"
      :title="businessLoadDetailTask?.name || '业务压测详情'"
      size="72%"
      destroy-on-close
    >
      <div v-if="businessLoadDetailTask" class="business-detail-drawer">
        <div class="detail-hero">
          <div>
            <el-tag>{{ businessLoadDetailTask.scenario_type_display }}</el-tag>
            <h3>{{ businessLoadDetailTask.name }}</h3>
            <p>{{ businessLoadDetailTask.purpose || "暂无用途说明" }}</p>
          </div>
          <div class="detail-actions">
            <el-button @click="openBusinessLoadDialog(businessLoadDetailTask)"
              >编辑配置</el-button
            >
            <el-button @click="precheckBusinessLoadTask(businessLoadDetailTask)"
              >预检查</el-button
            >
            <el-button
              type="success"
              :disabled="businessLoadDetailTask.status === 'running'"
              @click="startBusinessLoadTask(businessLoadDetailTask)"
            >
              启动任务
            </el-button>
            <el-dropdown
              trigger="click"
              @command="
                (command) =>
                  handleBusinessLoadCommand(command, businessLoadDetailTask)
              "
            >
              <el-button>更多</el-button>
              <template #dropdown>
                <el-dropdown-menu>
                  <el-dropdown-item
                    command="trial"
                    :disabled="businessLoadDetailTask.status === 'running'"
                    >小流量试跑</el-dropdown-item
                  >
                  <el-dropdown-item
                    v-if="
                      ['ready', 'running'].includes(
                        businessLoadDetailTask.status,
                      )
                    "
                    command="stop"
                    >停止任务</el-dropdown-item
                  >
                  <el-dropdown-item divided command="delete"
                    >删除任务</el-dropdown-item
                  >
                </el-dropdown-menu>
              </template>
            </el-dropdown>
          </div>
        </div>

        <el-descriptions :column="3" border class="detail-descriptions">
          <el-descriptions-item label="状态">
            <el-tag
              :type="getBusinessLoadStatusType(businessLoadDetailTask.status)"
            >
              {{ getBusinessLoadStatusText(businessLoadDetailTask) }}
            </el-tag>
          </el-descriptions-item>
          <el-descriptions-item label="目标">{{
            getBusinessLoadTargetBrief(businessLoadDetailTask)
          }}</el-descriptions-item>
          <el-descriptions-item label="规模">{{
            getBusinessLoadScaleBrief(businessLoadDetailTask)
          }}</el-descriptions-item>
          <el-descriptions-item label="最近结果" :span="3">
            {{
              businessLoadDetailTask.metrics?.last_trial_run?.message ||
              businessLoadDetailTask.metrics?.last_precheck?.message ||
              "暂无执行结果"
            }}
          </el-descriptions-item>
        </el-descriptions>

        <el-tabs class="detail-tabs">
          <el-tab-pane label="执行计划">
            <div class="plan-meta">
              <span
                v-if="
                  businessLoadDetailTask.scenario_type === 'im_message_flood'
                "
                >IM目标：{{
                  getImTargetLabel(businessLoadDetailTask.config)
                }}</span
              >
              <span
                v-if="
                  businessLoadDetailTask.scenario_type === 'im_message_flood'
                "
                >发送间隔：{{
                  businessLoadDetailTask.config?.interval_ms || 1000
                }}ms</span
              >
              <span
                v-if="
                  businessLoadDetailTask.scenario_type !== 'im_message_flood'
                "
                >社区：{{
                  businessLoadDetailTask.config?.server_name || "-"
                }}</span
              >
              <span
                v-if="
                  businessLoadDetailTask.scenario_type !== 'im_message_flood'
                "
                >社区号：{{
                  businessLoadDetailTask.config?.server_no || "-"
                }}</span
              >
              <span
                v-if="
                  businessLoadDetailTask.scenario_type !== 'im_message_flood'
                "
                >serverId：{{
                  businessLoadDetailTask.config?.server_id || "-"
                }}</span
              >
              <span
                >真实流量：{{
                  businessLoadDetailTask.config?.dry_run === false ? "是" : "否"
                }}</span
              >
            </div>
            <el-table
              v-if="
                businessLoadDetailTask.metrics?.last_precheck?.account_room_plan
                  ?.length
              "
              :data="
                businessLoadDetailTask.metrics.last_precheck.account_room_plan
              "
              size="small"
              border
            >
              <el-table-column prop="account_no" label="账号" min-width="130" />
              <el-table-column prop="phone" label="手机号" min-width="130" />
              <el-table-column
                prop="display_order"
                label="房间序号"
                width="90"
              />
              <el-table-column
                prop="channel_name"
                label="语音房"
                min-width="180"
              />
              <el-table-column prop="channel_id" label="房间ID" width="140" />
              <el-table-column
                prop="room_type_label"
                label="房间模式"
                width="150"
              />
              <el-table-column prop="status" label="状态" width="100" />
            </el-table>
            <el-empty
              v-else
              description="暂无执行计划。请先预检查生成账号/房间分配。"
              :image-size="80"
            />
          </el-tab-pane>

          <el-tab-pane
            v-if="
              businessLoadDetailTask.scenario_type === 'team_recruit_publish'
            "
            label="组队房间"
          >
            <el-table
              v-if="getTeamPublishRoomRows(businessLoadDetailTask).length"
              :data="getTeamPublishRoomRows(businessLoadDetailTask)"
              size="small"
              border
            >
              <el-table-column prop="display_order" label="序号" width="70" />
              <el-table-column
                prop="channel_name"
                label="房间名称"
                min-width="180"
              />
              <el-table-column prop="channel_id" label="房间ID" width="140" />
              <el-table-column label="招募状态" width="110">
                <template #default="{ row: room }">
                  <el-tag
                    :type="getTeamRoomRecruitStatusType(room)"
                    size="small"
                  >
                    {{ getTeamRoomRecruitStatus(room) }}
                  </el-tag>
                </template>
              </el-table-column>
              <el-table-column
                prop="heartbeat_rounds"
                label="保活轮次"
                width="100"
              />
              <el-table-column
                prop="last_message"
                label="最近文案"
                min-width="220"
                show-overflow-tooltip
              />
              <el-table-column label="操作" width="260" fixed="right">
                <template #default="{ row: room }">
                  <el-button
                    size="small"
                    type="primary"
                    @click="
                      openTeamRoomRepublishDialog(businessLoadDetailTask, room)
                    "
                    >编辑并发布</el-button
                  >
                  <el-button
                    size="small"
                    type="warning"
                    :loading="teamRoomCancelLoading[room.channel_id]"
                    @click="cancelTeamRoomRecruit(businessLoadDetailTask, room)"
                  >
                    取消招募
                  </el-button>
                </template>
              </el-table-column>
            </el-table>
            <el-empty
              v-else
              description="暂无组队房间数据，请先执行试跑。"
              :image-size="80"
            />
          </el-tab-pane>

          <el-tab-pane label="最近试跑">
            <div
              v-if="businessLoadDetailTask.metrics?.last_trial_run"
              class="trial-result-panel"
            >
              <el-row :gutter="12" class="trial-summary">
                <el-col
                  v-for="stat in getBusinessLoadTrialSummaryStats(
                    businessLoadDetailTask,
                  )"
                  :key="stat.label"
                  :span="stat.span || 6"
                >
                  <div class="trial-stat" :class="stat.type">
                    <span>{{ stat.label }}</span>
                    <strong>{{ stat.value }}</strong>
                  </div>
                </el-col>
              </el-row>

              <el-table
                v-if="
                  businessLoadDetailTask.metrics.last_trial_run.account_results
                    ?.length
                "
                :data="
                  businessLoadDetailTask.metrics.last_trial_run.account_results
                "
                size="small"
                border
                class="trial-table"
              >
                <el-table-column
                  prop="account_no"
                  label="账号"
                  min-width="120"
                />
                <el-table-column prop="phone" label="手机号" min-width="130" />
                <el-table-column
                  v-if="
                    businessLoadDetailTask.scenario_type ===
                    'community_activity_simulation'
                  "
                  prop="activity_role_label"
                  label="用户角色"
                  width="100"
                />
                <el-table-column
                  prop="channel_name"
                  label="目标房间"
                  min-width="180"
                />
                <el-table-column label="执行步骤" min-width="280">
                  <template #default="{ row: accountRow }">
                    <el-tag
                      v-for="step in accountRow.steps"
                      :key="step.key"
                      :type="step.success ? 'success' : 'danger'"
                      size="small"
                      class="capability-tag"
                    >
                      {{ step.label }} {{ step.success ? "通过" : "失败" }}
                    </el-tag>
                  </template>
                </el-table-column>
                <el-table-column
                  prop="elapsed_ms"
                  label="耗时(ms)"
                  width="100"
                />
                <el-table-column label="错误信息" min-width="180">
                  <template #default="{ row: accountRow }">{{
                    accountRow.error || "-"
                  }}</template>
                </el-table-column>
              </el-table>
            </div>
            <el-empty v-else description="暂无试跑结果。" :image-size="80" />
          </el-tab-pane>

          <el-tab-pane label="性能">
            <div
              v-if="businessLoadDetailTask.metrics?.last_trial_run?.performance"
              class="performance-panel"
            >
              <div class="performance-metrics">
                <span
                  >CPU平均：{{
                    businessLoadDetailTask.metrics.last_trial_run.performance
                      ?.summary?.cpu_avg_percent ?? "-"
                  }}%</span
                >
                <span
                  >CPU峰值：{{
                    businessLoadDetailTask.metrics.last_trial_run.performance
                      ?.summary?.cpu_max_percent ?? "-"
                  }}%</span
                >
                <span
                  >内存平均：{{
                    businessLoadDetailTask.metrics.last_trial_run.performance
                      ?.summary?.memory_avg_percent ?? "-"
                  }}%</span
                >
                <span
                  >内存峰值：{{
                    businessLoadDetailTask.metrics.last_trial_run.performance
                      ?.summary?.memory_max_percent ?? "-"
                  }}%</span
                >
                <span
                  >Django进程峰值：{{
                    businessLoadDetailTask.metrics.last_trial_run.performance
                      ?.summary?.process_rss_max_mb ?? "-"
                  }}
                  MB</span
                >
              </div>
              <ul class="performance-analysis">
                <li
                  v-for="item in businessLoadDetailTask.metrics.last_trial_run
                    .performance?.analysis || []"
                  :key="item"
                >
                  {{ item }}
                </li>
              </ul>
            </div>
            <el-empty v-else description="暂无性能数据。" :image-size="80" />
          </el-tab-pane>
        </el-tabs>
      </div>
    </el-drawer>

    <el-dialog
      v-model="accountDialogVisible"
      :title="accountDialogMode === 'create' ? '新增账号' : '编辑账号'"
      width="720px"
      :close-on-click-modal="false"
    >
      <el-form :model="accountForm" label-width="110px" autocomplete="off">
        <el-row :gutter="16">
          <el-col :span="12">
            <el-form-item label="环境" required>
              <el-select
                v-model="accountForm.environment"
                placeholder="请选择环境"
                style="width: 100%"
              >
                <el-option
                  v-for="item in accountOptions.environments"
                  :key="item.value"
                  :label="item.label"
                  :value="item.value"
                />
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="业务域" required>
              <el-select
                v-model="accountForm.business_domain"
                placeholder="请选择业务域"
                style="width: 100%"
              >
                <el-option
                  v-for="item in accountOptions.business_domains"
                  :key="item.value"
                  :label="item.label"
                  :value="item.value"
                />
              </el-select>
            </el-form-item>
          </el-col>
        </el-row>
        <el-row :gutter="16">
          <el-col :span="12">
            <el-form-item label="账号" required>
              <el-input
                v-model="accountForm.account_no"
                placeholder="如 demo_account_001"
                autocomplete="off"
                name="qaflow_business_account_no"
              />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="状态">
              <el-select v-model="accountForm.status" style="width: 100%">
                <el-option
                  v-for="item in accountOptions.statuses"
                  :key="item.value"
                  :label="item.label"
                  :value="item.value"
                />
              </el-select>
            </el-form-item>
          </el-col>
        </el-row>
        <el-row :gutter="16">
          <el-col :span="12">
            <el-form-item label="手机号">
              <el-input
                v-model="accountForm.phone"
                autocomplete="off"
                name="qaflow_business_account_phone"
              />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="用户ID">
              <el-input
                v-model="accountForm.user_id"
                autocomplete="off"
                name="qaflow_business_account_user_id"
              />
            </el-form-item>
          </el-col>
        </el-row>
        <el-row :gutter="16">
          <el-col :span="12">
            <el-form-item label="昵称">
              <el-input
                v-model="accountForm.nickname"
                autocomplete="off"
                name="qaflow_business_account_nickname"
              />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="用途">
              <el-input
                v-model="accountForm.purpose"
                placeholder="如 IM刷屏、进房压测"
                autocomplete="off"
                name="qaflow_business_account_purpose"
              />
            </el-form-item>
          </el-col>
        </el-row>
        <el-form-item label="密码">
          <el-input
            v-model="accountForm.password"
            type="password"
            show-password
            placeholder="编辑时不填则保留原密码"
            autocomplete="new-password"
            name="qaflow_business_account_secret"
          />
        </el-form-item>
        <el-form-item label="Token">
          <el-input
            v-model="accountForm.token"
            type="textarea"
            :rows="2"
            placeholder="可选，SDK/API 场景使用"
            autocomplete="off"
            name="qaflow_business_account_token"
          />
        </el-form-item>
        <el-form-item label="标签">
          <el-input
            v-model="accountForm.tagsText"
            placeholder="逗号分隔，如 im,smoke"
            autocomplete="off"
            name="qaflow_business_account_tags"
          />
        </el-form-item>
        <el-form-item label="备注">
          <el-input v-model="accountForm.remark" type="textarea" :rows="2" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="accountDialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="accountSaving" @click="saveAccount"
          >保存</el-button
        >
      </template>
    </el-dialog>

    <el-dialog
      v-model="accountImportVisible"
      title="批量导入账号"
      width="760px"
      :close-on-click-modal="false"
    >
      <el-alert
        title="支持按手机号段批量导入，也支持多行文本导入业务测试账号。"
        type="info"
        :closable="false"
        show-icon
        class="tool-alert"
      />
      <el-form :model="accountImportForm" label-width="110px">
        <el-row :gutter="16">
          <el-col :span="12">
            <el-form-item label="环境">
              <el-select
                v-model="accountImportForm.environment"
                style="width: 100%"
              >
                <el-option
                  v-for="item in accountOptions.environments"
                  :key="item.value"
                  :label="item.label"
                  :value="item.value"
                />
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="业务域">
              <el-select
                v-model="accountImportForm.business_domain"
                style="width: 100%"
              >
                <el-option
                  v-for="item in accountOptions.business_domains"
                  :key="item.value"
                  :label="item.label"
                  :value="item.value"
                />
              </el-select>
            </el-form-item>
          </el-col>
        </el-row>
        <el-form-item label="用途">
          <el-input v-model="accountImportForm.purpose" />
        </el-form-item>
        <el-form-item label="标签">
          <el-input
            v-model="accountImportForm.tagsText"
            placeholder="逗号分隔，如 im,smoke"
          />
        </el-form-item>
        <el-form-item label="导入方式">
          <el-radio-group v-model="accountImportForm.importMode">
            <el-radio-button label="range">手机号段</el-radio-button>
            <el-radio-button label="text">文本导入</el-radio-button>
          </el-radio-group>
        </el-form-item>
        <template v-if="accountImportForm.importMode === 'range'">
          <el-row :gutter="16">
            <el-col :span="12">
              <el-form-item label="起始号码">
                <el-input
                  v-model="accountImportForm.rangeStart"
                  placeholder="例如：18800001000"
                  autocomplete="off"
                />
              </el-form-item>
            </el-col>
            <el-col :span="12">
              <el-form-item label="结束号码">
                <el-input
                  v-model="accountImportForm.rangeEnd"
                  placeholder="例如：18800001099"
                  autocomplete="off"
                />
              </el-form-item>
            </el-col>
          </el-row>
          <el-alert
            :title="accountRangePreview"
            type="success"
            :closable="false"
            class="tool-alert compact"
          />
        </template>
        <el-form-item v-else label="账号文本">
          <el-input
            v-model="accountImportForm.raw_text"
            type="textarea"
            :rows="10"
            placeholder="每行一个账号：账号,手机号,用户ID,昵称&#10;1850000001,13800000001,154484441,测试账号&#10;1850000002"
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="accountImportVisible = false">取消</el-button>
        <el-button
          type="primary"
          :loading="accountSaving"
          @click="importAccounts"
          >确认导入</el-button
        >
      </template>
    </el-dialog>

    <el-dialog
      v-model="accountAllocateVisible"
      title="分配账号"
      width="640px"
      :close-on-click-modal="false"
    >
      <el-alert
        title="从账号池中按环境、业务域和标签分配可用账号，分配后账号会进入占用状态。"
        type="info"
        :closable="false"
        show-icon
        class="tool-alert"
      />
      <el-form :model="accountAllocateForm" label-width="110px">
        <el-row :gutter="16">
          <el-col :span="12">
            <el-form-item label="环境">
              <el-select
                v-model="accountAllocateForm.environment"
                style="width: 100%"
              >
                <el-option
                  v-for="item in accountOptions.environments"
                  :key="item.value"
                  :label="item.label"
                  :value="item.value"
                />
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="业务域">
              <el-select
                v-model="accountAllocateForm.business_domain"
                clearable
                placeholder="不选则不限业务域"
                style="width: 100%"
              >
                <el-option
                  v-for="item in accountOptions.business_domains"
                  :key="item.value"
                  :label="item.label"
                  :value="item.value"
                />
              </el-select>
            </el-form-item>
          </el-col>
        </el-row>
        <el-form-item label="分配数量">
          <el-input-number
            v-model="accountAllocateForm.count"
            :min="1"
            :max="1000"
          />
        </el-form-item>
        <el-form-item label="用途">
          <el-input
            v-model="accountAllocateForm.purpose"
            placeholder="例如：社区活跃模拟 / IM刷屏 / 进房压测"
          />
        </el-form-item>
        <el-form-item label="标签">
          <el-input
            v-model="accountAllocateForm.tagsText"
            placeholder="可选，逗号分隔，如 im,smoke"
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="accountAllocateVisible = false">取消</el-button>
        <el-button
          type="primary"
          :loading="accountSaving"
          @click="allocateAccounts"
          >确认分配</el-button
        >
      </template>
    </el-dialog>

    <el-dialog
      v-model="businessLoadDialogVisible"
      :title="
        businessLoadDialogMode === 'create'
          ? '创建业务压测任务'
          : '编辑业务压测任务'
      "
      width="1120px"
      :close-on-click-modal="false"
    >
      <el-alert
        :title="getBusinessLoadDialogTip()"
        type="info"
        :closable="false"
        show-icon
        class="tool-alert"
      />
      <el-form :model="businessLoadForm" label-width="120px">
        <el-divider content-position="left">基础配置</el-divider>
        <el-row :gutter="16">
          <el-col :span="12">
            <el-form-item label="任务名称" required>
              <el-input v-model="businessLoadForm.name" placeholder="" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="压测场景" required>
              <el-select
                v-model="businessLoadForm.scenario_type"
                style="width: 100%"
                @change="handleBusinessLoadScenarioChange"
              >
                <el-option
                  v-for="item in businessLoadOptions.scenarios"
                  :key="item.value"
                  :label="item.label"
                  :value="item.value"
                />
              </el-select>
            </el-form-item>
          </el-col>
        </el-row>
        <el-row :gutter="16">
          <el-col :span="8">
            <el-form-item label="环境">
              <el-select
                v-model="businessLoadForm.environment"
                style="width: 100%"
              >
                <el-option
                  v-for="item in businessLoadOptions.environments"
                  :key="item.value"
                  :label="item.label"
                  :value="item.value"
                />
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :span="8">
            <el-form-item label="账号数量">
              <template v-if="businessLoadIsCommunityActivityScenario">
                <el-tag type="warning" size="large"
                  >{{ businessLoadActivityAccountTotal }} 个账号</el-tag
                >
                <span class="form-tip">由固定用户 + 流动用户自动计算。</span>
              </template>
              <el-input-number
                v-else
                v-model="businessLoadForm.account_count"
                :min="1"
                :max="500"
              />
            </el-form-item>
          </el-col>
          <el-col :span="8">
            <el-form-item label="持续时间(秒)">
              <el-input-number
                v-model="businessLoadForm.duration_seconds"
                :min="1"
                :max="86400"
              />
            </el-form-item>
          </el-col>
        </el-row>

        <template v-if="businessLoadIsImScenario">
          <el-divider content-position="left">IM 消息配置</el-divider>
          <el-row :gutter="16">
            <el-col :span="8">
              <el-form-item label="目标类型">
                <el-select
                  v-model="businessLoadForm.target_type"
                  style="width: 100%"
                  @change="handleBusinessLoadImTargetTypeChange"
                >
                  <el-option label="C2C" value="c2c" />
                  <el-option label="群组" value="group" />
                  <el-option label="房间" value="room" />
                  <el-option label="组队" value="party" />
                </el-select>
              </el-form-item>
            </el-col>
            <el-col v-if="!businessLoadNeedsRoomTarget" :span="8">
              <el-form-item label="目标ID" required>
                <el-input
                  v-model="businessLoadForm.target_id"
                  placeholder="用户ID / 群ID / 房间ID"
                />
              </el-form-item>
            </el-col>
            <el-col v-if="!businessLoadNeedsRoomTarget" :span="8">
              <el-form-item label="目标名称">
                <el-input
                  v-model="businessLoadForm.target_name"
                  placeholder=""
                />
              </el-form-item>
            </el-col>
          </el-row>
          <el-row :gutter="16">
            <el-col :span="12">
              <el-form-item label="服务地址">
                <el-input
                  v-model="businessLoadForm.base_url"
                  placeholder="请输入业务服务地址，如 https://your-domain.com"
                />
              </el-form-item>
            </el-col>
            <el-col :span="6">
              <el-form-item label="发送间隔">
                <el-input-number
                  v-model="businessLoadForm.interval_ms"
                  :min="500"
                  :max="60000"
                />
                <span class="form-tip">单位：毫秒</span>
              </el-form-item>
            </el-col>
            <el-col :span="6">
              <el-form-item label="登录间隔">
                <el-input-number
                  v-model="businessLoadForm.login_interval_ms"
                  :min="0"
                  :max="10000"
                />
                <span class="form-tip">单位：毫秒</span>
              </el-form-item>
            </el-col>
          </el-row>
          <template v-if="businessLoadNeedsRoomTarget">
            <el-divider content-position="left">社区 / 语音房</el-divider>
            <el-row :gutter="16">
              <el-col :span="15">
                <el-form-item label="目标社区" required>
                  <el-select
                    v-model="businessLoadForm.server_id"
                    filterable
                    remote
                    reserve-keyword
                    :remote-method="searchBusinessCommunities"
                    :loading="businessCommunityLoading"
                    placeholder="输入社区昵称或社区号搜索"
                    style="width: 100%"
                    @change="handleBusinessCommunityChange"
                  >
                    <el-option
                      v-for="item in businessCommunityOptions"
                      :key="item.server_id"
                      :label="getBusinessCommunityLabel(item)"
                      :value="item.server_id"
                    >
                      <span>{{ item.server_name }}</span>
                      <span class="option-extra">
                        {{
                          item.server_no
                            ? `社区号 ${item.server_no}`
                            : `serverId ${item.server_id}`
                        }}
                        · {{ item.source }}
                      </span>
                    </el-option>
                  </el-select>
                  <div class="form-tip">
                    支持按社区昵称模糊搜索，或按社区号精确搜索。
                  </div>
                </el-form-item>
              </el-col>
              <el-col :span="9">
                <el-form-item label="探测账号">
                  <el-input
                    v-model="businessLoadForm.probe_phone"
                    placeholder=""
                  />
                </el-form-item>
              </el-col>
            </el-row>
            <el-form-item label="目标房间" required>
              <div class="room-picker">
                <div class="room-picker-toolbar">
                  <el-button
                    type="primary"
                    :loading="businessRoomLoading"
                    @click="loadBusinessRooms('normal')"
                    >加载房间列表</el-button
                  >
                  <el-button
                    v-if="selectedBusinessCommunityHasExclusiveRooms"
                    type="success"
                    plain
                    :loading="businessRoomLoading"
                    @click="loadBusinessRooms('exclusive')"
                  >
                    加载专属语音房
                  </el-button>
                  <el-radio-group
                    v-model="businessRoomTypeFilter"
                    size="small"
                    class="room-type-filter"
                  >
                    <el-radio-button
                      v-for="item in businessRoomTypeFilterOptions"
                      :key="item.value"
                      :label="item.value"
                    >
                      {{ item.label }}
                    </el-radio-button>
                  </el-radio-group>
                  <el-input
                    v-model="businessRoomOrderKeyword"
                    clearable
                    class="room-order-search"
                    placeholder="按房间序号搜索"
                  />
                  <span class="form-tip">
                    已选择 {{ selectedBusinessRooms.length }} 个房间
                  </span>
                </div>
                <el-table
                  v-loading="businessRoomLoading"
                  :data="filteredBusinessRoomPreviewList"
                  row-key="channel_id"
                  border
                  height="260"
                  empty-text="暂无房间，请先选择社区并加载房间列表"
                  @selection-change="handleBusinessRoomSelectionChange"
                >
                  <el-table-column type="selection" width="48" />
                  <el-table-column
                    prop="display_order"
                    label="序号"
                    width="70"
                  />
                  <el-table-column label="置顶" width="72">
                    <template #default="{ row }">
                      <el-tag v-if="row.is_top_room" type="warning" size="small"
                        >置顶</el-tag
                      >
                      <span v-else class="muted">-</span>
                    </template>
                  </el-table-column>
                  <el-table-column
                    prop="channel_name"
                    label="房间名称"
                    min-width="220"
                  />
                  <el-table-column
                    prop="channel_id"
                    label="房间ID"
                    width="150"
                  />
                  <el-table-column label="来源" width="110">
                    <template #default="{ row }">{{
                      getBusinessRoomSourceLabel(row)
                    }}</template>
                  </el-table-column>
                  <el-table-column
                    prop="sort_index_num"
                    label="排序"
                    width="100"
                  />
                  <el-table-column label="在线/容量" width="100">
                    <template #default="{ row }"
                      >{{ row.online_count || 0 }}/{{
                        row.capacity || "-"
                      }}</template
                    >
                  </el-table-column>
                  <el-table-column
                    prop="room_type_label"
                    label="房间模式"
                    width="150"
                  />
                </el-table>
              </div>
            </el-form-item>
          </template>
          <el-form-item label="消息模板">
            <el-input
              v-model="businessLoadForm.message_template"
              type="textarea"
              :rows="3"
              placeholder="QAFlow_IM_{{run_id}}_{{account_no}}_{{sequence}}_{{timestamp}}"
            />
            <div class="form-tip" v-pre>
              支持变量：{{ run_id }}、{{ account_no }}、{{ user_id }}、{{
                sequence
              }}、{{ timestamp }}。
            </div>
          </el-form-item>
          <el-form-item label="自动重连">
            <el-switch v-model="businessLoadForm.auto_reconnect" />
            <span class="form-tip">连接异常时允许 runner 自动重连。</span>
          </el-form-item>
          <el-form-item label="真实发送">
            <el-switch v-model="businessLoadForm.real_traffic_enabled" />
            <span class="form-tip"
              >开启后会调用 IM runner
              产生真实业务流量，建议先用少量账号试跑。</span
            >
          </el-form-item>
          <el-form-item
            v-if="businessLoadForm.real_traffic_enabled"
            label="Runner路径"
          >
            <el-input
              v-model="businessLoadForm.runner_path"
              placeholder="请输入 IM Runner 可执行文件路径"
            />
            <div class="form-tip">填写本机 IM runner 可执行文件路径。</div>
          </el-form-item>
        </template>

        <template v-else>
          <el-divider content-position="left">社区 / 语音房</el-divider>
          <el-row :gutter="16">
            <el-col :span="14">
              <el-form-item label="目标社区">
                <el-select
                  v-model="businessLoadForm.server_id"
                  filterable
                  remote
                  reserve-keyword
                  :remote-method="searchBusinessCommunities"
                  :loading="businessCommunityLoading"
                  placeholder="输入社区昵称或社区号搜索"
                  style="width: 100%"
                  @change="handleBusinessCommunityChange"
                >
                  <el-option
                    v-for="item in businessCommunityOptions"
                    :key="item.server_id"
                    :label="getBusinessCommunityLabel(item)"
                    :value="item.server_id"
                  >
                    <span>{{ item.server_name }}</span>
                    <span class="option-extra">
                      {{
                        item.server_no
                          ? `社区号 ${item.server_no}`
                          : `serverId ${item.server_id}`
                      }}
                      · {{ item.source }}
                    </span>
                  </el-option>
                </el-select>
                <div class="form-tip">
                  {{
                    businessLoadUsesRoomList
                      ? "选择社区后可加载该社区下的语音房列表。"
                      : "关注社区压测只需要选择目标社区，不需要选择语音房。"
                  }}
                </div>
              </el-form-item>
            </el-col>
            <el-col :span="10">
              <el-form-item label="探测账号">
                <el-input
                  v-model="businessLoadForm.probe_phone"
                  placeholder=""
                />
              </el-form-item>
            </el-col>
          </el-row>
          <el-row :gutter="16">
            <el-col :span="14">
              <el-form-item label="服务地址">
                <el-input
                  v-model="businessLoadForm.base_url"
                  placeholder="请输入业务服务地址，如 https://your-domain.com"
                />
              </el-form-item>
            </el-col>
            <el-col v-if="businessLoadUsesRoomList" :span="10">
              <el-form-item label="选房方式">
                <el-radio-group v-model="businessLoadForm.room_selection_mode">
                  <el-radio-button label="auto">自动选择</el-radio-button>
                  <el-radio-button label="manual">手动选择</el-radio-button>
                </el-radio-group>
              </el-form-item>
            </el-col>
          </el-row>
          <el-form-item v-if="businessLoadUsesRoomList" label="目标房间">
            <div class="room-picker">
              <div class="room-picker-toolbar">
                <el-button
                  type="primary"
                  :loading="businessRoomLoading"
                  @click="loadBusinessRooms('normal')"
                  >加载房间列表</el-button
                >
                <el-button
                  v-if="selectedBusinessCommunityHasExclusiveRooms"
                  type="success"
                  plain
                  :loading="businessRoomLoading"
                  @click="loadBusinessRooms('exclusive')"
                >
                  加载专属语音房
                </el-button>
                <el-radio-group
                  v-model="businessRoomTypeFilter"
                  size="small"
                  class="room-type-filter"
                >
                  <el-radio-button
                    v-for="item in businessRoomTypeFilterOptions"
                    :key="item.value"
                    :label="item.value"
                  >
                    {{ item.label }}
                  </el-radio-button>
                </el-radio-group>
                <el-input
                  v-model="businessRoomOrderKeyword"
                  clearable
                  class="room-order-search"
                  placeholder="按房间序号搜索"
                />
                <span class="form-tip">
                  已选择 {{ selectedBusinessRooms.length }} 个房间
                </span>
              </div>
              <el-table
                v-loading="businessRoomLoading"
                :data="filteredBusinessRoomPreviewList"
                row-key="channel_id"
                border
                height="260"
                empty-text="暂无房间，请先选择社区并加载房间列表"
                @selection-change="handleBusinessRoomSelectionChange"
              >
                <el-table-column type="selection" width="48" />
                <el-table-column prop="display_order" label="序号" width="70" />
                <el-table-column label="置顶" width="72">
                  <template #default="{ row }">
                    <el-tag v-if="row.is_top_room" type="warning" size="small"
                      >置顶</el-tag
                    >
                    <span v-else class="muted">-</span>
                  </template>
                </el-table-column>
                <el-table-column
                  prop="channel_name"
                  label="房间名称"
                  min-width="220"
                />
                <el-table-column prop="channel_id" label="房间ID" width="150" />
                <el-table-column label="来源" width="110">
                  <template #default="{ row }">{{
                    getBusinessRoomSourceLabel(row)
                  }}</template>
                </el-table-column>
                <el-table-column
                  prop="sort_index_num"
                  label="排序"
                  width="100"
                />
                <el-table-column label="在线/容量" width="100">
                  <template #default="{ row }"
                    >{{ row.online_count || 0 }}/{{
                      row.capacity || "-"
                    }}</template
                  >
                </el-table-column>
                <el-table-column
                  prop="room_type_label"
                  label="房间模式"
                  width="150"
                />
              </el-table>
            </div>
          </el-form-item>
        </template>

        <template v-if="businessLoadIsTeamScenario">
          <el-divider content-position="left">发布组队配置</el-divider>
          <el-alert
            title="发布组队会真实进房、心跳、发布组队并发送 IM 通知；开启通知后保活时，会按基础配置的持续时间维持房间在线。"
            type="warning"
            :closable="false"
            show-icon
            class="tool-alert compact"
          />
          <el-row :gutter="16">
            <el-col :span="8">
              <el-form-item label="有效期(分钟)">
                <el-input-number
                  v-model="businessLoadForm.team_duration_minutes"
                  :min="1"
                  :max="60"
                />
              </el-form-item>
            </el-col>
            <el-col :span="8">
              <el-form-item label="人数上限">
                <el-input-number
                  v-model="businessLoadForm.team_max_members_num"
                  :min="1"
                  :max="99"
                />
              </el-form-item>
            </el-col>
            <el-col :span="8">
              <el-form-item label="区服标签">
                <el-input v-model="businessLoadForm.team_mode" placeholder="" />
              </el-form-item>
            </el-col>
          </el-row>
          <el-row :gutter="16">
            <el-col :span="8">
              <el-form-item label="通知后保活">
                <el-switch
                  v-model="businessLoadForm.team_keepalive_after_notify"
                />
              </el-form-item>
            </el-col>
            <el-col :span="8">
              <el-form-item label="端上数量校验">
                <el-switch
                  v-model="businessLoadForm.team_publish_reliable_visible"
                  disabled
                />
                <span class="form-tip"
                  >按已选房间可靠发布，端上少一个组队都算失败。</span
                >
              </el-form-item>
            </el-col>
            <el-col :span="8">
              <div class="form-tip keepalive-tip">
                开启后，第 8
                步发送通知完成后会维持房间在线，直到基础持续时间结束或手动中断。
              </div>
            </el-col>
          </el-row>
          <el-form-item label="组队文案">
            <el-input
              v-model="businessLoadForm.team_message_template"
              type="textarea"
              :rows="3"
              placeholder="QAFlow_team_{{run_id}}_{{account_no}}_{{timestamp}}"
            />
            <div class="form-tip" v-pre>
              支持变量：{{ run_id }}、{{ account_no }}、{{ user_id }}、{{
                timestamp
              }}。
            </div>
          </el-form-item>
          <el-form-item label="真实发送">
            <el-switch v-model="businessLoadForm.real_traffic_enabled" />
            <span class="form-tip"
              >开启后会调用真实接口发布组队和 IM 通知。</span
            >
          </el-form-item>
          <el-form-item
            v-if="businessLoadForm.real_traffic_enabled"
            label="Runner路径"
          >
            <el-input
              v-model="businessLoadForm.runner_path"
              placeholder="请输入 IM Runner 可执行文件路径"
            />
            <div class="form-tip">发布组队依赖 IM runner 发送组队通知。</div>
          </el-form-item>
        </template>

        <template v-if="businessLoadIsCommunityActivityScenario">
          <el-divider content-position="left">社区活跃模型</el-divider>
          <el-alert
            title="固定用户负责占房和心跳保活，流动用户负责进出房/切房，用来制造社区房间列表的动态变化。建议先用 2+2 小流量试跑。"
            type="warning"
            :closable="false"
            show-icon
            class="tool-alert compact"
          />
          <el-row :gutter="16">
            <el-col :span="8">
              <el-form-item label="固定用户数">
                <el-input-number
                  v-model="businessLoadForm.resident_user_count"
                  :min="0"
                  :max="500"
                  @change="syncCommunityActivityAccountCount"
                />
                <span class="form-tip">长期留在房内，维持在线。</span>
              </el-form-item>
            </el-col>
            <el-col :span="8">
              <el-form-item label="流动用户数">
                <el-input-number
                  v-model="businessLoadForm.transient_user_count"
                  :min="0"
                  :max="500"
                  @change="syncCommunityActivityAccountCount"
                />
                <span class="form-tip">进出房或切换房间，制造变化。</span>
              </el-form-item>
            </el-col>
            <el-col :span="8">
              <el-form-item label="每房固定用户">
                <el-input-number
                  v-model="businessLoadForm.users_per_room"
                  :min="1"
                  :max="100"
                />
                <span class="form-tip">用于把固定用户分散到多个房间。</span>
              </el-form-item>
            </el-col>
          </el-row>
          <el-row :gutter="16">
            <el-col :span="8">
              <el-form-item label="切房比例">
                <el-input-number
                  v-model="businessLoadForm.transient_switch_ratio"
                  :min="0"
                  :max="100"
                />
                <span class="form-tip"
                  >单位：%，命中后先退房再进新房，其余直接切房。</span
                >
              </el-form-item>
            </el-col>
            <el-col :span="8">
              <el-form-item label="优先固定房">
                <el-input-number
                  v-model="businessLoadForm.transient_to_resident_ratio"
                  :min="0"
                  :max="100"
                />
                <span class="form-tip"
                  >单位：%，让流动用户更偏向已有热房。</span
                >
              </el-form-item>
            </el-col>
            <el-col :span="8">
              <el-form-item label="结束后清场">
                <el-switch v-model="businessLoadForm.cleanup_after_stop" />
                <span class="form-tip">试跑结束后主动退房。</span>
              </el-form-item>
            </el-col>
          </el-row>
          <el-row :gutter="16">
            <el-col :span="8">
              <el-form-item label="最短停留(秒)">
                <el-input-number
                  v-model="businessLoadForm.transient_stay_min_seconds"
                  :min="0"
                  :max="3600"
                />
              </el-form-item>
            </el-col>
            <el-col :span="8">
              <el-form-item label="最长停留(秒)">
                <el-input-number
                  v-model="businessLoadForm.transient_stay_max_seconds"
                  :min="0"
                  :max="3600"
                />
              </el-form-item>
            </el-col>
            <el-col :span="8">
              <el-form-item label="心跳间隔(秒)">
                <el-input-number
                  v-model="businessLoadForm.heartbeat_interval_seconds"
                  :min="5"
                  :max="300"
                />
              </el-form-item>
            </el-col>
          </el-row>
        </template>

        <el-collapse
          v-model="businessLoadAdvancedOpen"
          class="advanced-config-collapse"
        >
          <el-collapse-item
            title="高级配置：限流、账号标签、能力链路"
            name="advanced"
          >
            <el-row :gutter="16">
              <el-col :span="8">
                <el-form-item label="请求速率">
                  <el-input-number
                    v-model="businessLoadForm.request_rate_per_second"
                    :min="1"
                    :max="200"
                  />
                  <span class="form-tip">每秒请求数，仅用于压测节奏控制。</span>
                </el-form-item>
              </el-col>
              <el-col :span="8">
                <el-form-item label="账号分配">
                  <el-select
                    v-model="businessLoadForm.room_assignment_mode"
                    style="width: 100%"
                  >
                    <el-option label="轮询分配" value="round_robin" />
                    <el-option label="优先填满" value="fill_first" />
                  </el-select>
                </el-form-item>
              </el-col>
              <el-col v-if="!businessLoadIsCommunityActivityScenario" :span="8">
                <el-form-item label="每房账号数">
                  <el-input-number
                    v-model="businessLoadForm.users_per_room"
                    :min="1"
                    :max="100"
                  />
                </el-form-item>
              </el-col>
            </el-row>
            <el-form-item label="账号标签">
              <el-input
                v-model="businessLoadForm.accountTagsText"
                placeholder="不填则使用当前业务域可用账号"
              />
            </el-form-item>
            <el-form-item label="用途说明">
              <el-input
                v-model="businessLoadForm.purpose"
                placeholder="可选，便于后续识别任务用途"
              />
            </el-form-item>
            <el-form-item label="能力链路">
              <div class="capability-chain-preview">
                <el-tag
                  v-for="capability in selectedBusinessLoadScenario?.capabilities ||
                  []"
                  :key="capability.key"
                  class="capability-tag"
                >
                  {{ capability.order }}. {{ capability.label }}
                </el-tag>
              </div>
            </el-form-item>
          </el-collapse-item>
        </el-collapse>
      </el-form>
      <template #footer>
        <el-button @click="businessLoadDialogVisible = false">取消</el-button>
        <el-button
          type="primary"
          :loading="businessLoadSaving"
          @click="saveBusinessLoadTask"
          >保存</el-button
        >
      </template>
    </el-dialog>

    <el-dialog
      v-model="teamRepublishDialogVisible"
      title="重新发布组队"
      width="680px"
      :close-on-click-modal="false"
    >
      <el-alert
        title="本次只针对当前房间重新发布：平台会登录、进社区、进房、心跳、发布组队并发送 IM 通知；如需手动关闭，可在房间管理中点击取消招募。"
        type="warning"
        :closable="false"
        show-icon
        class="tool-alert compact"
      />
      <el-form :model="teamRepublishForm" label-width="120px">
        <el-form-item label="目标房间">
          <div class="readonly-room">
            <strong>{{ teamRepublishForm.channel_name || "-" }}</strong>
            <span>房间ID：{{ teamRepublishForm.channel_id || "-" }}</span>
          </div>
        </el-form-item>
        <el-row :gutter="16">
          <el-col :span="12">
            <el-form-item label="有效期(分钟)">
              <el-input-number
                class="team-number-input"
                v-model="teamRepublishForm.team_duration_minutes"
                :min="1"
                :max="60"
              />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="人数上限">
              <el-input-number
                class="team-number-input"
                v-model="teamRepublishForm.team_max_members_num"
                :min="1"
                :max="99"
              />
            </el-form-item>
          </el-col>
        </el-row>
        <el-row :gutter="16">
          <el-col :span="12">
            <el-form-item label="区服标签">
              <el-input
                v-model="teamRepublishForm.team_mode"
                placeholder="如 all"
              />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="通知后保活">
              <el-switch
                v-model="teamRepublishForm.team_keepalive_after_notify"
              />
            </el-form-item>
          </el-col>
        </el-row>
        <el-form-item label="组队文案">
          <el-input
            v-model="teamRepublishForm.team_message_template"
            type="textarea"
            :rows="4"
            placeholder="QAFlow_team_{{run_id}}_{{account_no}}_{{timestamp}}"
          />
          <div class="form-tip" v-pre>
            支持变量：{{ run_id }}、{{ account_no }}、{{ user_id }}、{{
              timestamp
            }}。
          </div>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="teamRepublishDialogVisible = false">取消</el-button>
        <el-button
          type="warning"
          :loading="teamRoomCancelLoading[teamRepublishForm.channel_id]"
          @click="cancelTeamRoomRecruit(teamRepublishTask, teamRepublishForm)"
        >
          取消招募
        </el-button>
        <el-button
          type="primary"
          :loading="teamRepublishLoading"
          @click="republishTeamRoom"
          >重新发布</el-button
        >
      </template>
    </el-dialog>

    <el-dialog
      v-model="toolDialogVisible"
      :title="
        getToolDisplayName(currentTool?.name) || currentTool?.display_name
      "
      width="1200px"
      :close-on-click-modal="false"
      @close="resetToolForm"
    >
      <div v-if="currentTool" class="tool-execution">
        <el-alert
          :title="
            getToolDescription(currentTool?.name) || currentTool.description
          "
          type="info"
          :closable="false"
          show-icon
          class="tool-alert"
        />

        <!-- 测试数据生成表单 -->
        <div v-if="currentCategory === 'test_data'" class="tool-form">
          <el-form label-width="120px">
            <el-form-item :label="$t('dataFactory.form.count')">
              <el-input-number v-model="toolForm.count" :min="1" :max="100" />
              <span class="form-tip">{{
                $t("dataFactory.form.countTip")
              }}</span>
            </el-form-item>
            <el-form-item
              v-if="currentTool.name === 'generate_chinese_phone'"
              :label="$t('dataFactory.form.carrier')"
            >
              <el-select
                v-model="toolForm.region"
                :placeholder="$t('dataFactory.form.carrier')"
              >
                <el-option
                  :label="$t('dataFactory.form.carrierOptions.all')"
                  value="all"
                />
                <el-option
                  :label="$t('dataFactory.form.carrierOptions.mobile')"
                  value="mobile"
                />
                <el-option
                  :label="$t('dataFactory.form.carrierOptions.unicom')"
                  value="unicom"
                />
                <el-option
                  :label="$t('dataFactory.form.carrierOptions.telecom')"
                  value="telecom"
                />
              </el-select>
            </el-form-item>
            <el-form-item
              v-if="currentTool.name === 'generate_chinese_email'"
              :label="$t('dataFactory.form.emailDomain')"
            >
              <el-select
                v-model="toolForm.domain"
                :placeholder="$t('dataFactory.form.emailDomain')"
              >
                <el-option
                  :label="$t('dataFactory.form.emailDomainOptions.random')"
                  value="random"
                />
                <el-option
                  :label="$t('dataFactory.form.emailDomainOptions.qq')"
                  value="qq.com"
                />
                <el-option
                  :label="$t('dataFactory.form.emailDomainOptions.netease163')"
                  value="163.com"
                />
                <el-option
                  :label="$t('dataFactory.form.emailDomainOptions.netease126')"
                  value="126.com"
                />
                <el-option
                  :label="$t('dataFactory.form.emailDomainOptions.gmail')"
                  value="gmail.com"
                />
              </el-select>
            </el-form-item>
            <el-form-item
              v-if="currentTool.name === 'generate_chinese_address'"
              :label="$t('dataFactory.form.addressType')"
            >
              <el-switch
                v-model="toolForm.full_address"
                :active-text="$t('dataFactory.form.fullAddress')"
                :inactive-text="$t('dataFactory.form.shortAddress')"
              />
            </el-form-item>
          </el-form>
        </div>

        <!-- 字符串工具表单 -->
        <div v-else-if="currentCategory === 'string'" class="tool-form">
          <el-form label-width="120px">
            <el-form-item
              v-if="currentTool.name !== 'text_diff'"
              :label="$t('dataFactory.form.inputText')"
            >
              <el-input
                v-model="toolForm.text"
                type="textarea"
                :rows="4"
                :placeholder="$t('dataFactory.form.inputText') + '...'"
              />
            </el-form-item>
            <el-form-item
              v-if="currentTool.name === 'replace_string'"
              :label="$t('dataFactory.form.findContent')"
            >
              <el-input
                v-model="toolForm.old_str"
                :placeholder="$t('dataFactory.form.findContentPlaceholder')"
              />
            </el-form-item>
            <el-form-item
              v-if="currentTool.name === 'replace_string'"
              :label="$t('dataFactory.form.replaceContent')"
            >
              <el-input
                v-model="toolForm.new_str"
                :placeholder="$t('dataFactory.form.replaceContentPlaceholder')"
              />
            </el-form-item>
            <el-form-item
              v-if="currentTool.name === 'replace_string'"
              :label="$t('dataFactory.form.regex')"
            >
              <el-switch v-model="toolForm.is_regex" />
              <span class="form-tip">{{
                $t("dataFactory.form.regexTip")
              }}</span>
            </el-form-item>
            <el-form-item
              v-if="currentTool.name === 'escape_string'"
              :label="$t('dataFactory.form.escapeType')"
            >
              <el-select
                v-model="toolForm.escape_type"
                :placeholder="$t('dataFactory.form.escapeType')"
              >
                <el-option label="JSON" value="json" />
                <el-option label="HTML" value="html" />
                <el-option label="URL" value="url" />
                <el-option label="XML" value="xml" />
              </el-select>
            </el-form-item>
            <el-form-item
              v-if="currentTool.name === 'unescape_string'"
              :label="$t('dataFactory.form.unescapeType')"
            >
              <el-select
                v-model="toolForm.unescape_type"
                :placeholder="$t('dataFactory.form.unescapeType')"
              >
                <el-option label="JSON" value="json" />
                <el-option label="HTML" value="html" />
                <el-option label="URL" value="url" />
              </el-select>
            </el-form-item>
            <el-form-item
              v-if="currentTool.name === 'regex_test'"
              :label="$t('dataFactory.form.regex')"
            >
              <el-input
                v-model="toolForm.pattern"
                :placeholder="$t('dataFactory.form.regexPatternPlaceholder')"
              />
            </el-form-item>
            <el-form-item
              v-if="currentTool.name === 'regex_test'"
              :label="$t('dataFactory.form.flags')"
            >
              <el-checkbox-group v-model="toolForm.flags">
                <el-checkbox label="i">{{
                  $t("dataFactory.form.flagIgnoreCase")
                }}</el-checkbox>
                <el-checkbox label="m">{{
                  $t("dataFactory.form.flagMultiline")
                }}</el-checkbox>
                <el-checkbox label="s">{{
                  $t("dataFactory.form.flagSingleline")
                }}</el-checkbox>
              </el-checkbox-group>
            </el-form-item>
            <el-form-item
              v-if="currentTool.name === 'case_convert'"
              :label="$t('dataFactory.form.convertType')"
            >
              <el-select
                v-model="toolForm.convert_type"
                :placeholder="$t('dataFactory.form.convertType')"
              >
                <el-option
                  :label="$t('dataFactory.form.convertTypeOptions.upper')"
                  value="upper"
                />
                <el-option
                  :label="$t('dataFactory.form.convertTypeOptions.lower')"
                  value="lower"
                />
                <el-option
                  :label="$t('dataFactory.form.convertTypeOptions.capitalize')"
                  value="capitalize"
                />
                <el-option
                  :label="$t('dataFactory.form.convertTypeOptions.title')"
                  value="title"
                />
                <el-option
                  :label="$t('dataFactory.form.convertTypeOptions.swapcase')"
                  value="swapcase"
                />
              </el-select>
            </el-form-item>
            <el-form-item
              v-if="currentTool.name === 'string_format'"
              :label="$t('dataFactory.form.formatType')"
            >
              <el-select
                v-model="toolForm.format_type"
                :placeholder="$t('dataFactory.form.formatType')"
              >
                <el-option
                  :label="$t('dataFactory.form.formatTypeOptions.trim')"
                  value="trim"
                />
                <el-option
                  :label="$t('dataFactory.form.formatTypeOptions.reverse')"
                  value="reverse"
                />
                <el-option
                  :label="$t('dataFactory.form.formatTypeOptions.split')"
                  value="split"
                />
                <el-option
                  :label="$t('dataFactory.form.formatTypeOptions.join')"
                  value="join"
                />
              </el-select>
            </el-form-item>
            <el-form-item
              v-if="currentTool.name === 'text_diff'"
              :label="$t('dataFactory.form.text1')"
            >
              <el-input
                v-model="toolForm.text1"
                type="textarea"
                :rows="6"
                :placeholder="$t('dataFactory.form.text1Placeholder')"
              />
            </el-form-item>
            <el-form-item
              v-if="currentTool.name === 'text_diff'"
              :label="$t('dataFactory.form.text2')"
            >
              <el-input
                v-model="toolForm.text2"
                type="textarea"
                :rows="6"
                :placeholder="$t('dataFactory.form.text2Placeholder')"
              />
            </el-form-item>
          </el-form>
        </div>

        <!-- 闂傚懎绻戝┃鈧€规悶鍎遍崣?-->
        <div v-else-if="currentCategory === 'random'" class="tool-form">
          <el-form label-width="120px">
            <el-form-item
              v-if="currentTool.name === 'random_int'"
              :label="$t('dataFactory.form.minValue')"
            >
              <el-input-number
                v-model="toolForm.min_val"
                :min="-999999"
                :max="999999"
              />
            </el-form-item>
            <el-form-item
              v-if="currentTool.name === 'random_int'"
              :label="$t('dataFactory.form.maxValue')"
            >
              <el-input-number
                v-model="toolForm.max_val"
                :min="-999999"
                :max="999999"
              />
            </el-form-item>
            <el-form-item
              v-if="currentTool.name === 'random_float'"
              :label="$t('dataFactory.form.minValue')"
            >
              <el-input-number v-model="toolForm.min_val" :step="0.1" />
            </el-form-item>
            <el-form-item
              v-if="currentTool.name === 'random_float'"
              :label="$t('dataFactory.form.maxValue')"
            >
              <el-input-number v-model="toolForm.max_val" :step="0.1" />
            </el-form-item>
            <el-form-item
              v-if="currentTool.name === 'random_float'"
              :label="$t('dataFactory.form.precision')"
            >
              <el-input-number
                v-model="toolForm.precision"
                :min="0"
                :max="10"
              />
            </el-form-item>
            <el-form-item
              v-if="currentTool.name === 'random_string'"
              :label="$t('dataFactory.form.length')"
            >
              <el-input-number v-model="toolForm.length" :min="1" :max="1000" />
            </el-form-item>
            <el-form-item
              v-if="currentTool.name === 'random_string'"
              :label="$t('dataFactory.form.charType')"
            >
              <el-select
                v-model="toolForm.char_type"
                :placeholder="$t('dataFactory.form.charType')"
              >
                <el-option
                  :label="$t('dataFactory.form.charTypeOptions.all')"
                  value="all"
                />
                <el-option
                  :label="$t('dataFactory.form.charTypeOptions.letters')"
                  value="letters"
                />
                <el-option
                  :label="$t('dataFactory.form.charTypeOptions.lowercase')"
                  value="lowercase"
                />
                <el-option
                  :label="$t('dataFactory.form.charTypeOptions.uppercase')"
                  value="uppercase"
                />
                <el-option
                  :label="$t('dataFactory.form.charTypeOptions.digits')"
                  value="digits"
                />
                <el-option
                  :label="$t('dataFactory.form.charTypeOptions.alphanumeric')"
                  value="alphanumeric"
                />
                <el-option
                  :label="$t('dataFactory.form.charTypeOptions.hex')"
                  value="hex"
                />
                <el-option
                  :label="$t('dataFactory.form.charTypeOptions.chinese')"
                  value="chinese"
                />
                <el-option
                  :label="$t('dataFactory.form.charTypeOptions.special')"
                  value="special"
                />
              </el-select>
            </el-form-item>
            <el-form-item
              v-if="currentTool.name === 'random_uuid'"
              :label="$t('dataFactory.form.uuidVersion')"
            >
              <el-select
                v-model="toolForm.version"
                :placeholder="$t('dataFactory.form.uuidVersion')"
              >
                <el-option label="UUID v1" :value="1" />
                <el-option label="UUID v4" :value="4" />
              </el-select>
            </el-form-item>
            <el-form-item
              v-if="currentTool.name === 'random_mac_address'"
              :label="$t('dataFactory.form.separator')"
            >
              <el-select
                v-model="toolForm.separator"
                :placeholder="$t('dataFactory.form.separator')"
              >
                <el-option
                  :label="$t('dataFactory.form.separatorOptions.colon')"
                  value=":"
                />
                <el-option
                  :label="$t('dataFactory.form.separatorOptions.hyphen')"
                  value="-"
                />
                <el-option
                  :label="$t('dataFactory.form.separatorOptions.none')"
                  value=""
                />
              </el-select>
            </el-form-item>
            <el-form-item
              v-if="currentTool.name === 'random_ip_address'"
              :label="$t('dataFactory.form.ipVersion')"
            >
              <el-select
                v-model="toolForm.ip_version"
                :placeholder="$t('dataFactory.form.ipVersion')"
              >
                <el-option label="IPv4" :value="4" />
                <el-option label="IPv6" :value="6" />
              </el-select>
            </el-form-item>
            <el-form-item
              v-if="currentTool.name === 'random_date'"
              :label="$t('dataFactory.form.startDate')"
            >
              <el-date-picker
                v-model="toolForm.start_date"
                type="date"
                :placeholder="$t('dataFactory.form.selectStartDate')"
              />
            </el-form-item>
            <el-form-item
              v-if="currentTool.name === 'random_date'"
              :label="$t('dataFactory.form.endDate')"
            >
              <el-date-picker
                v-model="toolForm.end_date"
                type="date"
                :placeholder="$t('dataFactory.form.selectEndDate')"
              />
            </el-form-item>
            <el-form-item
              v-if="currentTool.name === 'random_date'"
              :label="$t('dataFactory.form.dateFormat')"
            >
              <el-input v-model="toolForm.date_format" placeholder="%Y-%m-%d" />
            </el-form-item>
            <el-form-item
              v-if="currentTool.name === 'random_color'"
              :label="$t('dataFactory.form.colorFormat')"
            >
              <el-select
                v-model="toolForm.format"
                :placeholder="$t('dataFactory.form.colorFormat')"
              >
                <el-option
                  :label="$t('dataFactory.form.colorFormatOptions.hex')"
                  value="hex"
                />
                <el-option
                  :label="$t('dataFactory.form.colorFormatOptions.rgb')"
                  value="rgb"
                />
                <el-option
                  :label="$t('dataFactory.form.colorFormatOptions.rgba')"
                  value="rgba"
                />
              </el-select>
            </el-form-item>
            <el-form-item
              v-if="currentTool.name === 'random_password'"
              :label="$t('dataFactory.form.passwordLength')"
            >
              <el-input-number v-model="toolForm.length" :min="4" :max="50" />
            </el-form-item>
            <el-form-item
              v-if="currentTool.name === 'random_password'"
              :label="$t('dataFactory.form.charOptions')"
            >
              <el-checkbox-group v-model="toolForm.char_options">
                <el-checkbox label="include_uppercase">{{
                  $t("dataFactory.form.charOptionsItems.uppercase")
                }}</el-checkbox>
                <el-checkbox label="include_lowercase">{{
                  $t("dataFactory.form.charOptionsItems.lowercase")
                }}</el-checkbox>
                <el-checkbox label="include_digits">{{
                  $t("dataFactory.form.charOptionsItems.digits")
                }}</el-checkbox>
                <el-checkbox label="include_special">{{
                  $t("dataFactory.form.charOptionsItems.special")
                }}</el-checkbox>
              </el-checkbox-group>
            </el-form-item>
            <el-form-item
              v-if="
                [
                  'random_int',
                  'random_float',
                  'random_string',
                  'random_uuid',
                  'random_mac_address',
                  'random_ip_address',
                  'random_date',
                  'random_boolean',
                  'random_color',
                  'random_password',
                  'random_sequence',
                ].includes(currentTool.name)
              "
              :label="$t('dataFactory.form.count')"
            >
              <el-input-number v-model="toolForm.count" :min="1" :max="100" />
            </el-form-item>
            <el-form-item
              v-if="currentTool.name === 'random_sequence'"
              :label="$t('dataFactory.form.sequenceData')"
            >
              <el-input
                v-model="toolForm.sequence"
                type="textarea"
                :rows="4"
                :placeholder="$t('dataFactory.form.sequenceDataPlaceholder')"
              />
            </el-form-item>
            <el-form-item
              v-if="currentTool.name === 'random_sequence'"
              :label="$t('dataFactory.form.unique')"
            >
              <el-switch v-model="toolForm.unique" />
              <span class="form-tip">{{
                $t("dataFactory.form.uniqueTip")
              }}</span>
            </el-form-item>
          </el-form>
        </div>

        <!-- 编码工具表单 -->
        <div v-else-if="currentCategory === 'encoding'" class="tool-form">
          <el-form label-width="120px">
            <el-form-item
              v-if="
                ['generate_barcode', 'generate_qrcode'].includes(
                  currentTool.name,
                )
              "
              :label="$t('dataFactory.form.data')"
            >
              <el-input
                v-model="toolForm.data"
                :placeholder="$t('dataFactory.form.data')"
              />
            </el-form-item>
            <el-form-item
              v-if="currentTool.name === 'generate_barcode'"
              :label="$t('dataFactory.form.barcodeType')"
            >
              <el-select
                v-model="toolForm.barcode_type"
                :placeholder="$t('dataFactory.form.barcodeType')"
              >
                <el-option label="Code128" value="code128" />
                <el-option label="Code39" value="code39" />
                <el-option label="EAN13" value="ean13" />
                <el-option label="EAN8" value="ean8" />
              </el-select>
            </el-form-item>
            <el-form-item
              v-if="currentTool.name === 'generate_qrcode'"
              :label="$t('dataFactory.form.imageSize')"
            >
              <el-input-number
                v-model="toolForm.image_size"
                :min="100"
                :max="1000"
                :step="50"
              />
              <span class="form-tip">{{
                $t("dataFactory.form.imageSizeTip")
              }}</span>
            </el-form-item>
            <el-form-item
              v-if="currentTool.name === 'decode_qrcode'"
              :label="$t('dataFactory.form.uploadQrCode')"
            >
              <el-upload
                class="qr-code-upload"
                :show-file-list="false"
                :before-upload="handleQrCodeUpload"
                accept="image/*"
                drag
              >
                <div v-if="!qrCodeImage" class="upload-placeholder">
                  <el-icon class="upload-icon"><Upload /></el-icon>
                  <div class="upload-text">
                    {{ $t("dataFactory.form.uploadQrCodeText") }}
                  </div>
                  <div class="upload-tip">
                    {{ $t("dataFactory.form.uploadQrCodeTip") }}
                  </div>
                </div>
                <div v-else class="upload-preview">
                  <img
                    :src="qrCodeImage"
                    :alt="$t('dataFactory.form.qrCodePreview')"
                  />
                  <div class="upload-mask" @click="clearQrCodeImage">
                    <el-icon><Delete /></el-icon>
                    <span>{{ $t("dataFactory.form.clickToDelete") }}</span>
                  </div>
                </div>
              </el-upload>
            </el-form-item>
            <el-form-item
              v-if="currentTool.name === 'timestamp_convert'"
              :label="$t('dataFactory.form.timestampOrDate')"
            >
              <el-input
                v-model="toolForm.timestamp"
                :placeholder="$t('dataFactory.form.timestampPlaceholder')"
              />
            </el-form-item>
            <el-form-item
              v-if="currentTool.name === 'timestamp_convert'"
              :label="$t('dataFactory.form.timestampConvertType')"
            >
              <el-select
                v-model="toolForm.timestamp_convert_type"
                :placeholder="$t('dataFactory.form.timestampConvertType')"
              >
                <el-option
                  :label="
                    $t('dataFactory.form.timestampConvertOptions.toDatetime')
                  "
                  value="to_datetime"
                />
                <el-option
                  :label="
                    $t('dataFactory.form.timestampConvertOptions.toTimestamp')
                  "
                  value="to_timestamp"
                />
                <el-option
                  :label="
                    $t(
                      'dataFactory.form.timestampConvertOptions.currentTimestamp',
                    )
                  "
                  value="current_timestamp"
                />
              </el-select>
            </el-form-item>
            <el-form-item
              v-if="
                currentTool.name === 'timestamp_convert' &&
                toolForm.timestamp_convert_type === 'to_datetime'
              "
              :label="$t('dataFactory.form.timestampUnit')"
            >
              <el-select
                v-model="toolForm.timestamp_unit"
                :placeholder="$t('dataFactory.form.timestampUnit')"
              >
                <el-option
                  :label="$t('dataFactory.form.timestampUnitOptions.auto')"
                  value="auto"
                />
                <el-option
                  :label="$t('dataFactory.form.timestampUnitOptions.second')"
                  value="second"
                />
                <el-option
                  :label="
                    $t('dataFactory.form.timestampUnitOptions.millisecond')
                  "
                  value="millisecond"
                />
              </el-select>
            </el-form-item>
            <el-form-item
              v-if="currentTool.name === 'base_convert'"
              :label="$t('dataFactory.form.numberValue')"
            >
              <el-input
                v-model="toolForm.number"
                :placeholder="$t('dataFactory.form.numberValuePlaceholder')"
              />
            </el-form-item>
            <el-form-item
              v-if="currentTool.name === 'base_convert'"
              :label="$t('dataFactory.form.fromBase')"
            >
              <el-input-number
                v-model="toolForm.from_base"
                :min="2"
                :max="36"
              />
            </el-form-item>
            <el-form-item
              v-if="currentTool.name === 'base_convert'"
              :label="$t('dataFactory.form.toBase')"
            >
              <el-input-number v-model="toolForm.to_base" :min="2" :max="36" />
            </el-form-item>
            <el-form-item
              v-if="currentTool.name === 'unicode_convert'"
              :label="$t('dataFactory.form.text')"
            >
              <el-input
                v-model="toolForm.text"
                :placeholder="$t('dataFactory.form.inputText')"
              />
            </el-form-item>
            <el-form-item
              v-if="currentTool.name === 'unicode_convert'"
              :label="$t('dataFactory.form.unicodeConvertType')"
            >
              <el-select
                v-model="toolForm.unicode_convert_type"
                :placeholder="$t('dataFactory.form.unicodeConvertType')"
              >
                <el-option
                  :label="
                    $t('dataFactory.form.unicodeConvertOptions.toUnicode')
                  "
                  value="to_unicode"
                />
                <el-option
                  :label="
                    $t('dataFactory.form.unicodeConvertOptions.fromUnicode')
                  "
                  value="from_unicode"
                />
              </el-select>
            </el-form-item>
            <el-form-item
              v-if="currentTool.name === 'ascii_convert'"
              :label="$t('dataFactory.form.text')"
            >
              <el-input
                v-model="toolForm.text"
                :placeholder="$t('dataFactory.form.inputText')"
              />
            </el-form-item>
            <el-form-item
              v-if="currentTool.name === 'ascii_convert'"
              :label="$t('dataFactory.form.asciiConvertType')"
            >
              <el-select
                v-model="toolForm.convert_type"
                :placeholder="$t('dataFactory.form.asciiConvertType')"
              >
                <el-option
                  :label="$t('dataFactory.form.asciiConvertOptions.toAscii')"
                  value="to_ascii"
                />
                <el-option
                  :label="$t('dataFactory.form.asciiConvertOptions.fromAscii')"
                  value="from_ascii"
                />
              </el-select>
            </el-form-item>
            <el-form-item
              v-if="currentTool.name === 'color_convert'"
              :label="$t('dataFactory.form.colorValue')"
            >
              <el-input
                v-model="toolForm.color"
                :placeholder="$t('dataFactory.form.colorValuePlaceholder')"
              />
            </el-form-item>
            <el-form-item
              v-if="currentTool.name === 'color_convert'"
              :label="$t('dataFactory.form.sourceFormat')"
            >
              <el-select
                v-model="toolForm.from_type"
                :placeholder="$t('dataFactory.form.sourceFormat')"
              >
                <el-option
                  :label="$t('dataFactory.form.colorFormatOptions.hex')"
                  value="hex"
                />
                <el-option
                  :label="$t('dataFactory.form.colorFormatOptions.rgb')"
                  value="rgb"
                />
              </el-select>
            </el-form-item>
            <el-form-item
              v-if="currentTool.name === 'color_convert'"
              :label="$t('dataFactory.form.targetFormat')"
            >
              <el-select
                v-model="toolForm.to_type"
                :placeholder="$t('dataFactory.form.targetFormat')"
              >
                <el-option
                  :label="$t('dataFactory.form.colorFormatOptions.hex')"
                  value="hex"
                />
                <el-option
                  :label="$t('dataFactory.form.colorFormatOptions.rgb')"
                  value="rgb"
                />
                <el-option
                  :label="$t('dataFactory.form.colorFormatOptions.rgba')"
                  value="rgba"
                />
                <el-option label="HSL" value="hsl" />
              </el-select>
            </el-form-item>
            <el-form-item
              v-if="
                ['base64_encode', 'base64_decode'].includes(currentTool.name)
              "
              :label="$t('dataFactory.form.text')"
            >
              <el-input
                v-model="toolForm.text"
                type="textarea"
                :rows="4"
                :placeholder="$t('dataFactory.form.inputText')"
              />
            </el-form-item>
            <el-form-item
              v-if="
                ['base64_encode', 'base64_decode'].includes(currentTool.name)
              "
              :label="$t('dataFactory.form.encoding')"
            >
              <el-input v-model="toolForm.encoding" placeholder="utf-8" />
            </el-form-item>
            <el-form-item
              v-if="currentTool.name === 'url_encode'"
              :label="$t('dataFactory.form.urlData')"
            >
              <el-input
                v-model="toolForm.data"
                type="textarea"
                :rows="4"
                :placeholder="$t('dataFactory.form.urlDataEncodePlaceholder')"
              />
            </el-form-item>
            <el-form-item
              v-if="currentTool.name === 'url_encode'"
              :label="$t('dataFactory.form.encodeMethod')"
            >
              <el-select
                v-model="toolForm.plus"
                :placeholder="$t('dataFactory.form.encodeMethod')"
              >
                <el-option
                  :label="$t('dataFactory.form.encodeMethodOptions.standard')"
                  :value="false"
                />
                <el-option
                  :label="$t('dataFactory.form.encodeMethodOptions.plus')"
                  :value="true"
                />
              </el-select>
              <span class="form-tip">{{
                $t("dataFactory.form.plusEncodeTip")
              }}</span>
            </el-form-item>
            <el-form-item
              v-if="currentTool.name === 'url_decode'"
              :label="$t('dataFactory.form.urlData')"
            >
              <el-input
                v-model="toolForm.data"
                type="textarea"
                :rows="4"
                :placeholder="$t('dataFactory.form.urlDataDecodePlaceholder')"
              />
            </el-form-item>
            <el-form-item
              v-if="currentTool.name === 'url_decode'"
              :label="$t('dataFactory.form.decodeMethod')"
            >
              <el-select
                v-model="toolForm.plus"
                :placeholder="$t('dataFactory.form.decodeMethod')"
              >
                <el-option
                  :label="$t('dataFactory.form.decodeMethodOptions.standard')"
                  :value="false"
                />
                <el-option
                  :label="$t('dataFactory.form.decodeMethodOptions.plus')"
                  :value="true"
                />
              </el-select>
            </el-form-item>
            <el-form-item
              v-if="currentTool.name === 'jwt_decode'"
              :label="$t('dataFactory.form.jwtToken')"
            >
              <el-input
                v-model="toolForm.token"
                type="textarea"
                :rows="6"
                :placeholder="$t('dataFactory.form.jwtTokenPlaceholder')"
              />
            </el-form-item>
            <el-form-item
              v-if="currentTool.name === 'jwt_decode'"
              :label="$t('dataFactory.form.verifySignature')"
            >
              <el-switch v-model="toolForm.verify" />
              <span class="form-tip">{{
                $t("dataFactory.form.verifySignatureTip")
              }}</span>
            </el-form-item>
            <el-form-item
              v-if="currentTool.name === 'jwt_decode' && toolForm.verify"
              :label="$t('dataFactory.form.secretKey')"
            >
              <el-input
                v-model="toolForm.secret"
                type="password"
                :placeholder="$t('dataFactory.form.secretKeyPlaceholder')"
                show-password
              />
            </el-form-item>
            <el-form-item
              v-if="currentTool.name === 'image_to_base64'"
              :label="$t('dataFactory.form.uploadImage')"
            >
              <el-upload
                ref="uploadRef"
                class="image-upload"
                :auto-upload="false"
                :show-file-list="false"
                :on-change="handleImageChange"
                accept="image/*"
              >
                <el-button type="primary">{{
                  $t("dataFactory.actions.selectImage")
                }}</el-button>
                <template #tip>
                  <div class="el-upload__tip">
                    {{ $t("dataFactory.form.uploadImageTip") }}
                  </div>
                </template>
              </el-upload>
            </el-form-item>
            <el-form-item
              v-if="currentTool.name === 'image_to_base64' && imagePreview"
              :label="$t('dataFactory.form.imagePreview')"
            >
              <div class="image-preview">
                <img
                  :src="imagePreview"
                  :alt="$t('dataFactory.image.preview')"
                />
              </div>
            </el-form-item>
            <el-form-item
              v-if="currentTool.name === 'image_to_base64'"
              :label="$t('dataFactory.form.imageFormat')"
            >
              <el-select
                v-model="toolForm.image_format"
                :placeholder="$t('dataFactory.form.selectImageFormat')"
              >
                <el-option label="PNG" value="png" />
                <el-option label="JPEG" value="jpeg" />
                <el-option label="GIF" value="gif" />
                <el-option label="WebP" value="webp" />
                <el-option label="BMP" value="bmp" />
              </el-select>
            </el-form-item>
            <el-form-item
              v-if="currentTool.name === 'image_to_base64'"
              :label="$t('dataFactory.form.includePrefix')"
            >
              <el-switch v-model="toolForm.include_prefix" />
              <span class="form-tip">{{
                $t("dataFactory.form.includePrefixTip")
              }}</span>
            </el-form-item>
            <el-form-item
              v-if="currentTool.name === 'base64_to_image'"
              :label="$t('dataFactory.form.base64Code')"
            >
              <el-input
                v-model="toolForm.base64_str"
                type="textarea"
                :rows="10"
                :placeholder="$t('dataFactory.form.base64CodePlaceholder')"
              />
            </el-form-item>
          </el-form>
        </div>

        <!-- 加密工具表单 -->
        <div v-else-if="currentCategory === 'encryption'" class="tool-form">
          <el-form label-width="120px">
            <el-form-item
              v-if="
                [
                  'md5_hash',
                  'sha1_hash',
                  'sha256_hash',
                  'sha512_hash',
                  'password_strength',
                ].includes(currentTool.name)
              "
              :label="$t('dataFactory.form.text')"
            >
              <el-input
                v-model="toolForm.text"
                type="textarea"
                :rows="4"
                :placeholder="$t('dataFactory.form.inputText')"
              />
            </el-form-item>
            <el-form-item
              v-if="currentTool.name === 'hash_comparison'"
              :label="$t('dataFactory.form.text')"
            >
              <el-input
                v-model="toolForm.text"
                :placeholder="$t('dataFactory.form.inputText')"
              />
            </el-form-item>
            <el-form-item
              v-if="currentTool.name === 'hash_comparison'"
              :label="$t('dataFactory.form.hashValue')"
            >
              <el-input
                v-model="toolForm.hash_value"
                :placeholder="$t('dataFactory.form.hashValuePlaceholder')"
              />
            </el-form-item>
            <el-form-item
              v-if="currentTool.name === 'hash_comparison'"
              :label="$t('dataFactory.form.algorithm')"
            >
              <el-select
                v-model="toolForm.algorithm"
                :placeholder="$t('dataFactory.form.algorithm')"
              >
                <el-option label="MD5" value="md5" />
                <el-option label="SHA1" value="sha1" />
                <el-option label="SHA256" value="sha256" />
                <el-option label="SHA512" value="sha512" />
              </el-select>
            </el-form-item>
            <el-form-item
              v-if="['aes_encrypt', 'aes_decrypt'].includes(currentTool.name)"
              :label="$t('dataFactory.form.text')"
            >
              <el-input
                v-model="toolForm.text"
                type="textarea"
                :rows="4"
                :placeholder="$t('dataFactory.form.inputText')"
              />
            </el-form-item>
            <el-form-item
              v-if="['aes_encrypt', 'aes_decrypt'].includes(currentTool.name)"
              :label="$t('dataFactory.form.password')"
            >
              <el-input
                v-model="toolForm.password"
                type="password"
                :placeholder="$t('dataFactory.form.passwordPlaceholder')"
              />
            </el-form-item>
            <el-form-item
              v-if="['aes_encrypt', 'aes_decrypt'].includes(currentTool.name)"
              :label="$t('dataFactory.form.mode')"
            >
              <el-select
                v-model="toolForm.mode"
                :placeholder="$t('dataFactory.form.mode')"
              >
                <el-option label="CBC" value="CBC" />
                <el-option label="ECB" value="ECB" />
              </el-select>
            </el-form-item>
            <el-form-item
              v-if="currentTool.name === 'generate_salt'"
              :label="$t('dataFactory.form.length')"
            >
              <el-input-number v-model="toolForm.length" :min="8" :max="64" />
            </el-form-item>
            <el-form-item
              v-if="
                ['base64_encode', 'base64_decode'].includes(currentTool.name)
              "
              :label="$t('dataFactory.form.text')"
            >
              <el-input
                v-model="toolForm.text"
                type="textarea"
                :rows="4"
                :placeholder="$t('dataFactory.form.inputText')"
              />
            </el-form-item>
            <el-form-item
              v-if="
                ['base64_encode', 'base64_decode'].includes(currentTool.name)
              "
              :label="$t('dataFactory.form.encoding')"
            >
              <el-input v-model="toolForm.encoding" placeholder="utf-8" />
            </el-form-item>
          </el-form>
        </div>

        <!-- JSONPath 查询工具 -->
        <div
          v-else-if="
            currentCategory === 'json' &&
            ['jsonpath_query'].includes(currentTool.name)
          "
          class="tool-form json-path-tool"
        >
          <el-row :gutter="20">
            <el-col :span="24">
              <div class="path-input-panel">
                <h4>{{ $t("dataFactory.form.jsonPathExpr") }}</h4>
                <el-input
                  v-model="toolForm.jsonpath_expr"
                  :placeholder="$t('dataFactory.form.jsonPathExprPlaceholder')"
                  @input="handleJsonPathInput"
                />
                <div class="form-tip">
                  <a
                    href="https://goessner.net/articles/JsonPath/"
                    target="_blank"
                    >{{ $t("dataFactory.form.jsonPathSyntaxRef") }}</a
                  >
                </div>
              </div>
            </el-col>
          </el-row>
          <el-row :gutter="20">
            <el-col :span="12">
              <div class="json-input-panel">
                <h4>{{ $t("dataFactory.form.jsonDataInput") }}</h4>
                <el-input
                  v-model="toolForm.json_str"
                  type="textarea"
                  :rows="15"
                  :placeholder="$t('dataFactory.form.jsonDataPlaceholder')"
                  @input="handleJsonPathInput"
                />
              </div>
            </el-col>
            <el-col :span="12">
              <div class="json-input-panel">
                <h4>{{ $t("dataFactory.form.queryResult") }}</h4>
                <div v-if="toolResult" class="result-display">
                  <pre>{{
                    JSON.stringify(toolResult.result || toolResult, null, 2)
                  }}</pre>
                </div>
                <div v-else class="result-empty">
                  <el-empty
                    :description="$t('dataFactory.form.queryResultEmpty')"
                    :image-size="60"
                  />
                </div>
              </div>
            </el-col>
          </el-row>
        </div>

        <!-- JSON 差异对比工具 -->
        <div
          v-else-if="
            currentCategory === 'json' &&
            ['json_diff_enhanced'].includes(currentTool.name)
          "
          class="tool-form json-diff-tool"
        >
          <el-row :gutter="20">
            <el-col :span="12">
              <div class="json-input-panel">
                <h4>{{ $t("dataFactory.form.jsonData1") }}</h4>
                <el-input
                  v-model="toolForm.json_str1"
                  type="textarea"
                  :rows="15"
                  :placeholder="$t('dataFactory.form.jsonData1Placeholder')"
                  @input="handleJsonDiffInput"
                />
              </div>
            </el-col>
            <el-col :span="12">
              <div class="json-input-panel">
                <h4>{{ $t("dataFactory.form.jsonData2") }}</h4>
                <el-input
                  v-model="toolForm.json_str2"
                  type="textarea"
                  :rows="15"
                  :placeholder="$t('dataFactory.form.jsonData2Placeholder')"
                  @input="handleJsonDiffInput"
                />
              </div>
            </el-col>
          </el-row>
          <el-row :gutter="20" class="diff-options">
            <el-col :span="24">
              <el-form label-width="120px">
                <el-form-item :label="$t('dataFactory.form.ignoreWhitespace')">
                  <el-switch
                    v-model="toolForm.ignore_whitespace"
                    @change="handleJsonDiffInput"
                  />
                </el-form-item>
                <el-form-item :label="$t('dataFactory.form.showOnlyDiff')">
                  <el-switch
                    v-model="toolForm.show_only_diff"
                    @change="handleJsonDiffInput"
                  />
                </el-form-item>
              </el-form>
            </el-col>
          </el-row>
        </div>

        <!-- JSON 格式化工具 -->
        <div
          v-else-if="
            currentCategory === 'json' && currentTool.name === 'format_json'
          "
          class="tool-form json-format-tool"
        >
          <el-row :gutter="20">
            <el-col :span="12">
              <div class="json-input-panel">
                <div class="panel-header">
                  <h4>{{ $t("dataFactory.form.input") }}</h4>
                  <div class="input-stats">
                    <span
                      >{{ $t("dataFactory.form.chars") }}:
                      {{ getInputStats().chars }}</span
                    >
                    <span
                      >{{ $t("dataFactory.form.lines") }}:
                      {{ getInputStats().lines }}</span
                    >
                  </div>
                </div>
                <el-input
                  v-model="toolForm.json_str"
                  type="textarea"
                  :rows="20"
                  :placeholder="$t('dataFactory.form.jsonDataPlaceholder')"
                  @input="handleJsonInput"
                />
              </div>
            </el-col>
            <el-col :span="12">
              <div class="json-input-panel">
                <div class="panel-header">
                  <h4>{{ $t("dataFactory.form.output") }}</h4>
                  <!-- <div class="output-stats">
                    <span>字符数 {{ getOutputStats().chars }}</span>
                    <span>行数 {{ getOutputStats().lines }}</span>
                  </div> -->
                </div>
                <div v-if="jsonTreeData" class="result-display json-tree-view">
                  <div class="json-tree-actions">
                    <el-button size="small" @click="expandAllJson">
                      <el-icon><Operation /></el-icon>
                      {{ $t("dataFactory.actions.expandAll") }}
                    </el-button>
                    <el-button size="small" @click="collapseAllJson">
                      <el-icon><Operation /></el-icon>
                      {{ $t("dataFactory.actions.collapseAll") }}
                    </el-button>
                  </div>
                  <el-tree
                    :data="[jsonTreeData]"
                    :props="{ label: 'label', children: 'children' }"
                    :expand-on-click-node="false"
                    :default-expand-all="false"
                    :default-expanded-keys="jsonExpandedKeys"
                    @node-expand="handleNodeExpand"
                    @node-collapse="handleNodeCollapse"
                    node-key="key"
                    class="json-tree"
                  >
                    <template #default="{ node, data }">
                      <span
                        class="json-tree-node"
                        :class="`json-type-${data.type}`"
                      >
                        <span class="json-node-label">{{ data.label }}</span>
                      </span>
                    </template>
                  </el-tree>
                </div>
                <div
                  v-else-if="toolResult && toolResult.result"
                  class="result-display"
                >
                  <pre>{{ toolResult.result }}</pre>
                </div>
                <div v-else class="result-empty">
                  <el-empty
                    :description="$t('dataFactory.form.formatResultEmpty')"
                    :image-size="60"
                  />
                </div>
              </div>
            </el-col>
          </el-row>
          <el-row :gutter="20" class="format-options">
            <el-col :span="24">
              <div class="options-bar">
                <div class="option-group">
                  <span class="option-label"
                    >{{ $t("dataFactory.form.indent") }}:</span
                  >
                  <el-radio-group
                    v-model="toolForm.indent"
                    @change="handleJsonInput"
                  >
                    <el-radio-button :value="2">{{
                      $t("dataFactory.form.indentSpaces2")
                    }}</el-radio-button>
                    <el-radio-button :value="4">{{
                      $t("dataFactory.form.indentSpaces4")
                    }}</el-radio-button>
                  </el-radio-group>
                </div>
                <div class="option-group">
                  <el-switch
                    v-model="toolForm.sort_keys"
                    @change="handleJsonInput"
                  />
                  <span class="option-label">{{
                    $t("dataFactory.form.sortKeys")
                  }}</span>
                </div>
                <div class="option-group">
                  <el-switch
                    v-model="toolForm.compress"
                    @change="handleJsonInput"
                  />
                  <span class="option-label">{{
                    $t("dataFactory.form.compress")
                  }}</span>
                </div>
              </div>
            </el-col>
          </el-row>
        </div>

        <!-- JSON 通用工具表单 -->
        <div
          v-else-if="
            currentCategory === 'json' &&
            !['format_json', 'jsonpath_query', 'json_diff_enhanced'].includes(
              currentTool.name,
            )
          "
          class="tool-form json-tool"
        >
          <el-form label-width="120px">
            <el-form-item
              v-if="
                [
                  'format_json',
                  'validate_json',
                  'json_to_xml',
                  'json_to_yaml',
                  'json_to_csv',
                  'json_path_list',
                  'json_flatten',
                ].includes(currentTool.name)
              "
              :label="$t('dataFactory.form.jsonData')"
            >
              <el-input
                v-model="toolForm.json_str"
                type="textarea"
                :rows="8"
                :placeholder="$t('dataFactory.form.jsonDataPlaceholder')"
                @input="handleJsonInput"
              />
            </el-form-item>
            <el-form-item
              v-if="currentTool.name === 'format_json'"
              :label="$t('dataFactory.form.indent')"
            >
              <el-input-number
                v-model="toolForm.indent"
                :min="0"
                :max="8"
                @change="handleJsonInput"
              />
            </el-form-item>
            <el-form-item
              v-if="currentTool.name === 'format_json'"
              :label="$t('dataFactory.form.sortKeys')"
            >
              <el-switch
                v-model="toolForm.sort_keys"
                @change="handleJsonInput"
              />
            </el-form-item>
            <el-form-item
              v-if="currentTool.name === 'format_json'"
              :label="$t('dataFactory.form.compress')"
            >
              <el-switch
                v-model="toolForm.compress"
                @change="handleJsonInput"
              />
            </el-form-item>
            <el-form-item
              v-if="currentTool.name === 'xml_to_json'"
              :label="$t('dataFactory.form.xmlData')"
            >
              <el-input
                v-model="toolForm.xml_str"
                type="textarea"
                :rows="8"
                :placeholder="$t('dataFactory.form.xmlDataPlaceholder')"
              />
            </el-form-item>
            <el-form-item
              v-if="currentTool.name === 'yaml_to_json'"
              :label="$t('dataFactory.form.yamlData')"
            >
              <el-input
                v-model="toolForm.yaml_str"
                type="textarea"
                :rows="8"
                :placeholder="$t('dataFactory.form.yamlDataPlaceholder')"
              />
            </el-form-item>
            <el-form-item
              v-if="currentTool.name === 'csv_to_json'"
              :label="$t('dataFactory.form.csvData')"
            >
              <el-input
                v-model="toolForm.csv_str"
                type="textarea"
                :rows="8"
                :placeholder="$t('dataFactory.form.csvDataPlaceholder')"
              />
            </el-form-item>
            <el-form-item
              v-if="currentTool.name === 'csv_to_json'"
              :label="$t('dataFactory.form.csvSeparator')"
            >
              <el-input
                v-model="toolForm.separator"
                :placeholder="$t('dataFactory.form.csvSeparatorPlaceholder')"
              />
            </el-form-item>
            <el-form-item
              v-if="currentTool.name === 'csv_to_json'"
              :label="$t('dataFactory.form.hasHeader')"
            >
              <el-switch v-model="toolForm.has_header" />
            </el-form-item>
          </el-form>
        </div>

        <!-- Mock 数据表单 -->
        <div v-else-if="currentCategory === 'mock'" class="tool-form">
          <el-form label-width="120px">
            <el-form-item :label="$t('dataFactory.form.count')">
              <el-input-number v-model="toolForm.count" :min="1" :max="100" />
            </el-form-item>
            <el-form-item
              v-if="currentTool.name === 'mock_string'"
              :label="$t('dataFactory.form.length')"
            >
              <el-input-number v-model="toolForm.length" :min="1" :max="100" />
            </el-form-item>
            <el-form-item
              v-if="currentTool.name === 'mock_string'"
              :label="$t('dataFactory.form.charType')"
            >
              <el-select
                v-model="toolForm.char_type"
                :placeholder="$t('dataFactory.form.charType')"
              >
                <el-option
                  :label="$t('dataFactory.form.charTypeOptions.all')"
                  value="all"
                />
                <el-option
                  :label="$t('dataFactory.form.charTypeOptions.letters')"
                  value="letters"
                />
                <el-option
                  :label="$t('dataFactory.form.charTypeOptions.digits')"
                  value="digits"
                />
                <el-option
                  :label="$t('dataFactory.form.charTypeOptions.alphanumeric')"
                  value="alphanumeric"
                />
              </el-select>
            </el-form-item>
            <el-form-item
              v-if="currentTool.name === 'mock_number'"
              :label="$t('dataFactory.form.minValue')"
            >
              <el-input-number v-model="toolForm.min_val" />
            </el-form-item>
            <el-form-item
              v-if="currentTool.name === 'mock_number'"
              :label="$t('dataFactory.form.maxValue')"
            >
              <el-input-number v-model="toolForm.max_val" />
            </el-form-item>
            <el-form-item
              v-if="currentTool.name === 'mock_number'"
              :label="$t('dataFactory.form.decimals')"
            >
              <el-input-number v-model="toolForm.decimals" :min="0" :max="10" />
            </el-form-item>
            <el-form-item
              v-if="currentTool.name === 'mock_date'"
              :label="$t('dataFactory.form.startDate')"
            >
              <el-date-picker
                v-model="toolForm.start_date"
                type="date"
                :placeholder="$t('dataFactory.form.selectStartDate')"
              />
            </el-form-item>
            <el-form-item
              v-if="currentTool.name === 'mock_date'"
              :label="$t('dataFactory.form.endDate')"
            >
              <el-date-picker
                v-model="toolForm.end_date"
                type="date"
                :placeholder="$t('dataFactory.form.selectEndDate')"
              />
            </el-form-item>
            <el-form-item
              v-if="currentTool.name === 'mock_datetime'"
              :label="$t('dataFactory.form.startDate')"
            >
              <el-date-picker
                v-model="toolForm.start_date"
                type="datetime"
                :placeholder="$t('dataFactory.form.selectStartDateTime')"
              />
            </el-form-item>
            <el-form-item
              v-if="currentTool.name === 'mock_datetime'"
              :label="$t('dataFactory.form.endDate')"
            >
              <el-date-picker
                v-model="toolForm.end_date"
                type="datetime"
                :placeholder="$t('dataFactory.form.selectEndDateTime')"
              />
            </el-form-item>
          </el-form>
        </div>

        <!-- Crontab 表达式表单 -->
        <div v-else-if="currentCategory === 'crontab'" class="tool-form">
          <el-form label-width="120px">
            <el-form-item
              v-if="currentTool.name === 'generate_expression'"
              :label="$t('dataFactory.form.minute')"
            >
              <el-input
                v-model="toolForm.minute"
                placeholder="0-59, *, */5, 1,3,5, 1-10"
              />
              <span class="form-tip">{{
                $t("dataFactory.form.minuteTip")
              }}</span>
            </el-form-item>
            <el-form-item
              v-if="currentTool.name === 'generate_expression'"
              :label="$t('dataFactory.form.hour')"
            >
              <el-input
                v-model="toolForm.hour"
                placeholder="0-23, *, */2, 9,18, 8-18"
              />
              <span class="form-tip">{{ $t("dataFactory.form.hourTip") }}</span>
            </el-form-item>
            <el-form-item
              v-if="currentTool.name === 'generate_expression'"
              :label="$t('dataFactory.form.day')"
            >
              <el-input
                v-model="toolForm.day"
                placeholder="1-31, *, */7, 1,15, 1-10"
              />
              <span class="form-tip">{{ $t("dataFactory.form.dayTip") }}</span>
            </el-form-item>
            <el-form-item
              v-if="currentTool.name === 'generate_expression'"
              :label="$t('dataFactory.form.month')"
            >
              <el-input
                v-model="toolForm.month"
                placeholder="1-12, *, */3, 1,4,7,10, 6-9"
              />
              <span class="form-tip">{{
                $t("dataFactory.form.monthTip")
              }}</span>
            </el-form-item>
            <el-form-item
              v-if="currentTool.name === 'generate_expression'"
              :label="$t('dataFactory.form.weekday')"
            >
              <el-input
                v-model="toolForm.weekday"
                placeholder="0-6, *, */2, 1-5, 1,3,5"
              />
              <span class="form-tip">{{
                $t("dataFactory.form.weekdayTip")
              }}</span>
            </el-form-item>
            <el-form-item
              v-if="
                [
                  'parse_expression',
                  'get_next_runs',
                  'validate_expression',
                ].includes(currentTool.name)
              "
              :label="$t('dataFactory.form.crontabExpression')"
            >
              <el-input
                v-model="toolForm.expression"
                type="textarea"
                :rows="3"
                :placeholder="
                  $t('dataFactory.form.crontabExpressionPlaceholder')
                "
              />
            </el-form-item>
            <el-form-item
              v-if="currentTool.name === 'get_next_runs'"
              :label="$t('dataFactory.form.runCount')"
            >
              <el-input-number v-model="toolForm.count" :min="1" :max="20" />
            </el-form-item>
          </el-form>
        </div>

        <el-form label-width="120px" class="tool-options">
          <el-form-item :label="$t('dataFactory.form.saveResult')">
            <el-switch v-model="toolForm.isSaved" />
            <span class="form-tip">{{
              $t("dataFactory.form.saveResultTip")
            }}</span>
          </el-form-item>
          <el-form-item :label="$t('dataFactory.form.tags')">
            <el-input
              v-model="toolForm.tags"
              :placeholder="$t('dataFactory.form.tagsPlaceholder')"
            />
          </el-form-item>
        </el-form>

        <div
          v-if="
            toolResult &&
            currentTool?.name !== 'jsonpath_query' &&
            currentTool?.name !== 'format_json'
          "
          class="tool-result"
        >
          <div class="result-header">
            <h4>{{ $t("dataFactory.form.result") }}</h4>
            <el-button
              v-if="
                [
                  'json_to_xml',
                  'json_to_yaml',
                  'json_to_csv',
                  'xml_to_json',
                  'yaml_to_json',
                  'csv_to_json',
                ].includes(currentTool?.name)
              "
              type="primary"
              size="small"
              @click="downloadResult"
            >
              <el-icon><Download /></el-icon>
              {{ $t("dataFactory.actions.download") }}
            </el-button>
          </div>
          <div
            v-if="
              [
                'generate_barcode',
                'generate_qrcode',
                'base64_to_image',
              ].includes(currentTool?.name)
            "
            class="image-result"
          >
            <div class="image-preview">
              <img
                v-if="toolResult.url"
                :src="getImageUrl(toolResult.url)"
                :alt="currentTool.display_name"
              />
              <div v-else class="no-image">
                {{ $t("dataFactory.image.generateFailed") }}
              </div>
            </div>
            <div class="image-actions">
              <el-button type="primary" @click="downloadImage(toolResult)">
                <el-icon><Download /></el-icon>
                {{ $t("dataFactory.actions.downloadImage") }}
              </el-button>
              <el-tag v-if="toolResult.filename" type="info">{{
                toolResult.filename
              }}</el-tag>
            </div>
          </div>
          <el-input
            v-else-if="typeof toolResult === 'string'"
            v-model="toolResult"
            type="textarea"
            :rows="6"
            readonly
          />
          <pre v-else>{{ JSON.stringify(toolResult, null, 2) }}</pre>
        </div>
      </div>
      <template #footer>
        <el-button @click="toolDialogVisible = false">{{
          $t("dataFactory.actions.cancel")
        }}</el-button>
        <el-button type="primary" :loading="executing" @click="executeTool">
          {{ $t("dataFactory.actions.execute") }}
        </el-button>
      </template>
    </el-dialog>

    <!-- 历史记录弹窗 -->
    <el-dialog
      v-model="showHistory"
      :title="$t('dataFactory.history.title')"
      width="1200px"
    >
      <el-tabs v-model="historyTab">
        <el-tab-pane :label="$t('dataFactory.history.allRecords')" name="all">
          <div class="history-content">
            <el-table
              v-loading="historyLoading"
              :data="historyRecords"
              stripe
              class="history-table"
            >
              <el-table-column
                :label="$t('dataFactory.history.toolName')"
                min-width="180"
              >
                <template #default="{ row }">
                  <span>{{ getToolDisplayName(row.tool_name) }}</span>
                </template>
              </el-table-column>
              <el-table-column
                prop="tool_category_display"
                :label="$t('dataFactory.history.category')"
                min-width="120"
              />
              <el-table-column
                prop="tool_scenario_display"
                :label="$t('dataFactory.history.scenario')"
                min-width="120"
              />
              <el-table-column
                :label="$t('dataFactory.history.usageTime')"
                min-width="180"
              >
                <template #default="{ row }">
                  {{ formatDateTime(row.created_at) }}
                </template>
              </el-table-column>
              <el-table-column
                :label="$t('dataFactory.history.operation')"
                width="100"
                align="center"
                fixed="right"
              >
                <template #default="{ row }">
                  <el-button
                    size="small"
                    type="danger"
                    @click="deleteRecord(row)"
                    >{{ $t("dataFactory.actions.delete") }}</el-button
                  >
                </template>
              </el-table-column>
            </el-table>
            <el-pagination
              v-model:current-page="historyCurrentPage"
              v-model:page-size="historyPageSize"
              :page-sizes="[10, 20, 50, 100]"
              :total="historyTotal"
              layout="total, sizes, prev, pager, next, jumper"
              @size-change="handleHistorySizeChange"
              @current-change="handleHistoryPageChange"
              class="history-pagination"
            />
          </div>
        </el-tab-pane>
        <el-tab-pane :label="$t('dataFactory.history.statistics')" name="stats">
          <div class="stats-container">
            <el-row :gutter="20">
              <el-col :span="24">
                <el-card class="total-stats-card" v-loading="statsLoading">
                  <div class="total-stats">
                    <div class="total-stat-item">
                      <div class="total-stat-value">
                        {{ statistics.total_records || 0 }}
                      </div>
                      <div class="total-stat-label">
                        {{ $t("dataFactory.history.totalRecords") }}
                      </div>
                    </div>
                  </div>
                </el-card>
              </el-col>
            </el-row>
            <el-row :gutter="20" style="margin-top: 20px">
              <el-col :span="12">
                <el-card v-loading="statsLoading">
                  <template #header>
                    <span class="card-header-title">{{
                      $t("dataFactory.history.categoryStats")
                    }}</span>
                  </template>
                  <div
                    v-if="
                      statistics.category_stats &&
                      Object.keys(statistics.category_stats).length > 0
                    "
                  >
                    <div
                      v-for="(count, category) in statistics.category_stats"
                      :key="category"
                      class="stat-item"
                    >
                      <div class="stat-item-content">
                        <span class="stat-label">{{ category }}</span>
                        <el-progress
                          :percentage="
                            calculatePercentage(count, statistics.total_records)
                          "
                          :stroke-width="12"
                          :show-text="false"
                        />
                        <span class="stat-count">{{ count }}</span>
                      </div>
                    </div>
                  </div>
                  <el-empty
                    v-else
                    :description="$t('dataFactory.history.noData')"
                    :image-size="80"
                  />
                </el-card>
              </el-col>
              <el-col :span="12">
                <el-card v-loading="statsLoading">
                  <template #header>
                    <span class="card-header-title">{{
                      $t("dataFactory.history.scenarioStats")
                    }}</span>
                  </template>
                  <div
                    v-if="
                      statistics.scenario_stats &&
                      Object.keys(statistics.scenario_stats).length > 0
                    "
                  >
                    <div
                      v-for="(count, scenario) in statistics.scenario_stats"
                      :key="scenario"
                      class="stat-item"
                    >
                      <div class="stat-item-content">
                        <span class="stat-label">{{ scenario }}</span>
                        <el-progress
                          :percentage="
                            calculatePercentage(count, statistics.total_records)
                          "
                          :stroke-width="12"
                          :show-text="false"
                        />
                        <span class="stat-count">{{ count }}</span>
                      </div>
                    </div>
                  </div>
                  <el-empty
                    v-else
                    :description="$t('dataFactory.history.noData')"
                    :image-size="80"
                  />
                </el-card>
              </el-col>
            </el-row>
          </div>
        </el-tab-pane>
      </el-tabs>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, watch, onMounted, computed, nextTick } from "vue";
import { useRouter } from "vue-router";
import { useI18n } from "vue-i18n";
import { ElMessage, ElMessageBox, ElEmpty } from "element-plus";
import {
  DataLine,
  Menu,
  Grid,
  Clock,
  Operation,
  ArrowRight,
  Document,
  List,
  Lock,
  User,
  MagicStick,
  VideoPlay,
  ChatDotSquare,
  Picture,
  Connection,
  Phone,
  Message,
  Location,
  Ticket,
  OfficeBuilding,
  CreditCard,
  CircleCheck,
  DocumentCopy,
  Search,
  Delete,
  Edit,
  Unlock,
  DataLine as DataLineIcon,
  Sort,
  Share,
  View,
  Upload,
} from "@element-plus/icons-vue";
import request from "@/utils/api";
import { debounce } from "lodash-es";

const normalizeApiUrl = (url) => {
  return url.startsWith("/api/") ? url.slice(4) : url;
};

const axios = {
  get: (url, config) => request.get(normalizeApiUrl(url), config),
  post: (url, data, config) => request.post(normalizeApiUrl(url), data, config),
  patch: (url, data, config) =>
    request.patch(normalizeApiUrl(url), data, config),
  delete: (url, config) => request.delete(normalizeApiUrl(url), config),
};

const DEFAULT_BUSINESS_BASE_URL = "";
const DEFAULT_IM_RUNNER_PATH = "";

// 简单本地缓存
const cache = {
  get: (key) => {
    try {
      const item = localStorage.getItem(key);
      if (item) {
        const parsed = JSON.parse(item);
        if (parsed.expiry > Date.now()) return parsed.data;
        localStorage.removeItem(key);
      }
    } catch (error) {
      console.error("Cache get error:", error);
    }
    return null;
  },
  set: (key, data, expiry = 300000) => {
    // 默认缓存 5 分钟
    try {
      localStorage.setItem(
        key,
        JSON.stringify({ data, expiry: Date.now() + expiry }),
      );
    } catch (error) {
      console.error("Cache set error:", error);
    }
  },
  remove: (key) => {
    try {
      localStorage.removeItem(key);
    } catch (error) {
      console.error("Cache remove error:", error);
    }
  },
};

const router = useRouter();
const { t } = useI18n();

const viewMode = ref("category");
const categories = ref([]);
const scenarios = ref([]);
const currentScenario = ref(null);
const toolDialogVisible = ref(false);
const currentTool = ref(null);
const currentCategory = ref("");
const toolForm = ref({
  count: 1,
  text: "",
  isSaved: false,
  tags: "",
  gender: "random",
  region: "all",
  domain: "random",
  full_address: true,
  company_type: "all",
  old_str: "",
  new_str: "",
  is_regex: false,
  escape_type: "json",
  unescape_type: "json",
  pattern: "",
  flags: [],
  text1: "",
  text2: "",
  convert_type: "upper",
  format_type: "trim",
  min_val: 1,
  max_val: 100,
  precision: 2,
  length: 8,
  char_type: "all",
  version: 4,
  separator: ":",
  ip_version: 4,
  start_date: "2025-01-01",
  end_date: "2025-12-31",
  date_format: "%Y-%m-%d",
  format: "hex",
  char_options: [
    "include_uppercase",
    "include_lowercase",
    "include_digits",
    "include_special",
  ],
  data: "",
  barcode_type: "code128",
  timestamp: "",
  timestamp_convert_type: "to_datetime",
  timestamp_unit: "auto",
  number: "",
  from_base: 10,
  to_base: 16,
  from_type: "hex",
  to_type: "rgb",
  encoding: "utf-8",
  unicode_convert_type: "to_unicode",
  hash_value: "",
  algorithm: "md5",
  password: "",
  mode: "CBC",
  json_str: "",
  json_str1: "",
  json_str2: "",
  xml_str: "",
  yaml_str: "",
  csv_str: "",
  jsonpath_expr: "",
  root_tag: "root",
  indent: 2,
  sort_keys: false,
  compress: false,
  ignore_whitespace: true,
  has_header: true,
  show_only_diff: false,
  array_length: 5,
  item_type: "string",
  keys: "",
  value_type: "string",
  plus: false,
  token: "",
  verify: false,
  secret: "",
  minute: "*",
  hour: "*",
  day: "*",
  month: "*",
  weekday: "*",
  expression: "",
  image_data: "",
  image_format: "png",
  include_prefix: true,
  base64_str: "",
});
const toolResult = ref(null);
const imagePreview = ref("");
const qrCodeImage = ref("");
const uploadRef = ref(null);
const executing = ref(false);
const showHistory = ref(false);
const historyTab = ref("all");
const historyRecords = ref([]);
const historyTotal = ref(0);
const historyCurrentPage = ref(1);
const historyPageSize = ref(10);
const statistics = ref({});
const historyLoading = ref(false);
const statsLoading = ref(false);
const jsonTreeData = ref(null);
const jsonExpandedKeys = ref([]);
const jsonCollapseState = ref({});
const accountLoading = ref(false);
const accountSaving = ref(false);
const accountRecords = ref([]);
const accountTotal = ref(0);
const accountCurrentPage = ref(1);
const accountPageSize = ref(20);
const accountStats = ref({});
const accountOptions = ref({
  environments: [
    { value: "test", label: "测试环境" },
    { value: "test1", label: "Test1" },
    { value: "staging", label: "预发环境" },
    { value: "dev", label: "开发环境" },
  ],
  business_domains: [
    { value: "common", label: "通用" },
    { value: "im", label: "IM" },
    { value: "room", label: "房间" },
    { value: "mic", label: "麦序" },
    { value: "community", label: "社区" },
    { value: "team", label: "组队" },
  ],
  statuses: [
    { value: "available", label: "可用" },
    { value: "in_use", label: "使用中" },
    { value: "disabled", label: "禁用" },
    { value: "invalid", label: "失效" },
  ],
});
const accountFilters = ref({
  environment: "",
  business_domain: "",
  status: "",
  keyword: "",
});
const accountDialogVisible = ref(false);
const accountDialogMode = ref("create");
const accountForm = ref({});
const accountImportVisible = ref(false);
const accountImportForm = ref({
  environment: "test",
  business_domain: "common",
  purpose: "",
  tagsText: "",
  importMode: "range",
  rangeStart: "",
  rangeEnd: "",
  raw_text: "",
});
const accountAllocateVisible = ref(false);
const accountAllocateForm = ref({
  environment: "test",
  business_domain: "",
  count: 1,
  purpose: "",
  tagsText: "",
});
const businessLoadLoading = ref(false);
const businessLoadSaving = ref(false);
const businessLoadTrialLoading = ref({});
const businessLoadTasks = ref([]);
const businessLoadTotal = ref(0);
const businessLoadCurrentPage = ref(1);
const businessLoadPageSize = ref(20);
const businessLoadActiveScenario = ref("");
const businessLoadDialogVisible = ref(false);
const businessLoadDialogMode = ref("create");
const businessLoadForm = ref({});
const businessLoadDetailVisible = ref(false);
const businessLoadDetailTask = ref(null);
const businessLoadAdvancedOpen = ref([]);
const teamRepublishDialogVisible = ref(false);
const teamRepublishLoading = ref(false);
const teamRoomCancelLoading = ref({});
const teamRepublishTask = ref(null);
const teamRepublishForm = ref({});
const businessCommunityLoading = ref(false);
const businessRoomLoading = ref(false);
const businessCommunityOptions = ref([]);
const businessRoomPreviewList = ref([]);
const selectedBusinessRooms = ref([]);
const businessRoomOrderKeyword = ref("");
const businessRoomTypeFilter = ref("all");
const businessRoomTypeFilterOptions = [
  { label: "全部", value: "all" },
  { label: "游戏语音房", value: "game" },
  { label: "互动语音房", value: "interactive" },
];
const businessLoadOptions = ref({
  scenarios: [
    {
      value: "room_list_load",
      label: "房间列表压测",
      business_domain: "room",
      default_config: {
        server_id: 55984,
        account_count: 10,
        duration_seconds: 60,
        request_rate_per_second: 5,
        dry_run: true,
      },
      capabilities: [],
    },
  ],
  environments: [
    { value: "test", label: "测试环境" },
    { value: "test1", label: "Test1" },
    { value: "staging", label: "预发环境" },
    { value: "dev", label: "开发环境" },
  ],
  business_domains: [
    { value: "common", label: "通用" },
    { value: "im", label: "IM" },
    { value: "room", label: "房间" },
    { value: "community", label: "社区" },
  ],
  statuses: [
    { value: "draft", label: "草稿" },
    { value: "ready", label: "就绪" },
    { value: "running", label: "运行中" },
    { value: "completed", label: "已完成" },
    { value: "failed", label: "失败" },
    { value: "stopped", label: "已停止" },
  ],
});
const businessLoadFilters = ref({
  scenario_type: "",
  status: "",
  keyword: "",
});

const iconMap = {
  document: Document,
  code: List,
  distribute: Grid,
  lock: Lock,
  user: User,
  magic: MagicStick,
  video: VideoPlay,
  chat: ChatDotSquare,
  clock: Clock,
  picture: Picture,
  phone: Phone,
  message: Message,
  location: Location,
  ticket: Ticket,
  office: OfficeBuilding,
  "credit-card": CreditCard,
  "circle-check": CircleCheck,
  "document-copy": DocumentCopy,
  search: Search,
  delete: Delete,
  edit: Edit,
  unlock: Unlock,
  "data-line": DataLineIcon,
  sort: Sort,
  share: Share,
  view: View,
};

const getIcon = (iconName) => {
  return iconMap[iconName] || Operation;
};

const getScenarioIcon = (scenario) => {
  const iconMapping = {
    test_data: User,
    json: List,
    string: Document,
    encoding: Connection,
    random: MagicStick,
    encryption: Lock,
    crontab: Clock,
  };
  return iconMapping[scenario] || Operation;
};

const fetchCategories = async () => {
  try {
    const response = await axios.get("/api/data-factory/categories/");
    categories.value = response.data.categories;
  } catch (error) {
    ElMessage.error(t("dataFactory.messages.fetchCategoriesFailed"));
  }
};

const fetchScenarios = () => {
  try {
    const scenarioMap = {};
    categories.value.forEach((category) => {
      category.tools.forEach((tool) => {
        const scenario = tool.scenario || "other";
        if (!scenarioMap[scenario]) {
          scenarioMap[scenario] = {
            scenario: scenario,
            name: getScenarioName(scenario),
            description: getScenarioDesc(scenario),
            tool_count: 0,
          };
        }
        scenarioMap[scenario].tool_count++;
      });
    });
    scenarios.value = Object.values(scenarioMap);
  } catch (error) {
    ElMessage.error(t("dataFactory.messages.fetchScenariosFailed"));
  }
};

const getScenarioName = (scenario) => {
  return t(`dataFactory.scenarios.${scenario}`) || scenario;
};

const getCategoryName = (category) => {
  return t(`dataFactory.scenarios.${category}`) || category;
};

const getScenarioDesc = (scenario) => {
  return t(`dataFactory.scenarioDescs.${scenario}`) || "";
};

const getToolDisplayName = (toolName) => {
  return t(`dataFactory.tools.${toolName}`) || toolName;
};

const getToolDescription = (toolName) => {
  return t(`dataFactory.toolDescs.${toolName}`) || "";
};

const executeTool = async () => {
  if (!currentTool.value) return;

  // 二维码解码需要先上传图片
  if (
    currentTool.value.name === "decode_qrcode" &&
    !toolForm.value.image_data
  ) {
    ElMessage.warning("请先上传二维码图片");
    return;
  }

  executing.value = true;
  try {
    const input_data = buildInputData();
    console.log(
      "Executing tool:",
      currentTool.value.name,
      "with input:",
      input_data,
    );
    const response = await axios.post("/api/data-factory/", {
      tool_name: currentTool.value.name,
      tool_category: currentCategory.value,
      tool_scenario: currentTool.value.scenario || "other",
      input_data: input_data,
      is_saved: toolForm.value.isSaved,
      tags: toolForm.value.tags ? toolForm.value.tags.split(",") : [],
    });

    console.log("Tool execution result:", response.data);
    toolResult.value = response.data;
    ElMessage.success(t("dataFactory.messages.executeSuccess"));
  } catch (error) {
    console.error(
      "Tool execution error:",
      error,
      "Tool:",
      currentTool.value.name,
    );
    ElMessage.error(
      error.response?.data?.error || t("dataFactory.messages.executeFailed"),
    );
  } finally {
    executing.value = false;
  }
};

const resetToolForm = () => {
  toolForm.value = {
    count: 1,
    text: "",
    isSaved: false,
    tags: "",
    gender: "random",
    region: "all",
    domain: "random",
    full_address: true,
    company_type: "all",
    old_str: "",
    new_str: "",
    is_regex: false,
    escape_type: "json",
    unescape_type: "json",
    pattern: "",
    flags: [],
    text1: "",
    text2: "",
    convert_type: "upper",
    format_type: "trim",
    min_val: 1,
    max_val: 100,
    precision: 2,
    length: 8,
    char_type: "all",
    image_size: 300,
    separator: ":",
    ip_version: 4,
    start_date: "2025-01-01",
    end_date: "2025-12-31",
    date_format: "%Y-%m-%d",
    format: "hex",
    char_options: [
      "include_uppercase",
      "include_lowercase",
      "include_digits",
      "include_special",
    ],
    data: "",
    barcode_type: "code128",
    timestamp: "",
    timestamp_convert_type: "to_datetime",
    timestamp_unit: "auto",
    number: "",
    from_base: 10,
    to_base: 16,
    from_type: "hex",
    to_type: "rgb",
    encoding: "utf-8",
    unicode_convert_type: "to_unicode",
    hash_value: "",
    algorithm: "md5",
    password: "",
    mode: "CBC",
    json_str: "",
    json_str1: "",
    json_str2: "",
    xml_str: "",
    yaml_str: "",
    csv_str: "",
    jsonpath_expr: "",
    root_tag: "root",
    indent: 2,
    sort_keys: false,
    compress: false,
    ignore_whitespace: true,
    has_header: true,
    show_only_diff: false,
    array_length: 5,
    item_type: "string",
    keys: "",
    value_type: "string",
    minute: "*",
    hour: "*",
    day: "*",
    month: "*",
    weekday: "*",
    expression: "",
    image_data: "",
    image_format: "png",
    include_prefix: true,
    base64_str: "",
    sequence: "",
    unique: false,
  };
  toolResult.value = null;
  imagePreview.value = "";
  qrCodeImage.value = "";
  jsonTreeData.value = null;
  jsonExpandedKeys.value = [];
  jsonCollapseState.value = {};
};

let debounceTimer = null;
const handleJsonInput = async () => {
  if (debounceTimer) {
    clearTimeout(debounceTimer);
  }

  debounceTimer = setTimeout(async () => {
    if (currentTool.value?.name === "format_json" && toolForm.value.json_str) {
      try {
        const response = await axios.post("/api/data-factory/", {
          tool_name: "format_json",
          tool_category: "json",
          tool_scenario: "data_validation",
          input_data: {
            json_str: toolForm.value.json_str,
            indent: toolForm.value.indent,
            sort_keys: toolForm.value.sort_keys,
            compress: toolForm.value.compress,
          },
          is_saved: false,
        });
        toolResult.value = response.data;
        jsonTreeData.value = parseJsonToTree(response.data.result);
        saveJsonCollapseState();
      } catch (error) {
        toolResult.value = null;
        jsonTreeData.value = null;
      }
    }
  }, 300);
};

const parseJsonToTree = (jsonStr) => {
  try {
    const obj = JSON.parse(jsonStr);
    return convertObjectToTree(obj);
  } catch (e) {
    return null;
  }
};

const convertObjectToTree = (obj, key = "root", path = "") => {
  const currentPath = path ? `${path}.${key}` : key;

  if (obj === null) {
    return {
      key: currentPath,
      label: `${key}: null`,
      value: null,
      type: "null",
      children: [],
    };
  }

  if (typeof obj === "object") {
    const isArray = Array.isArray(obj);
    const children = Object.keys(obj).map((k) =>
      convertObjectToTree(obj[k], k, currentPath),
    );

    return {
      key: currentPath,
      label: `${key}${isArray ? ` [${obj.length}]` : ""}`,
      value: isArray
        ? `Array(${obj.length})`
        : `Object{${Object.keys(obj).length}}`,
      type: isArray ? "array" : "object",
      children: children,
    };
  }

  const type = typeof obj;
  return {
    key: currentPath,
    label: `${key}: ${String(obj)}`,
    value: String(obj),
    type: type,
    children: [],
  };
};

const expandAllJson = () => {
  const getAllKeys = (nodes) => {
    let keys = [];
    nodes.forEach((node) => {
      keys.push(node.key);
      if (node.children && node.children.length > 0) {
        keys = keys.concat(getAllKeys(node.children));
      }
    });
    return keys;
  };

  if (jsonTreeData.value) {
    jsonExpandedKeys.value = getAllKeys([jsonTreeData.value]);
    saveJsonCollapseState();
  }
};

const collapseAllJson = () => {
  jsonExpandedKeys.value = [];
  saveJsonCollapseState();
};

const saveJsonCollapseState = () => {
  if (currentTool.value?.name === "format_json") {
    const state = {
      expandedKeys: jsonExpandedKeys.value,
      timestamp: Date.now(),
    };
    localStorage.setItem("json_format_collapse_state", JSON.stringify(state));
  }
};

const loadJsonCollapseState = () => {
  try {
    const state = localStorage.getItem("json_format_collapse_state");
    if (state) {
      const parsed = JSON.parse(state);
      jsonExpandedKeys.value = parsed.expandedKeys || [];
    }
  } catch (e) {
    jsonExpandedKeys.value = [];
  }
};

watch(
  () => currentTool.value,
  (newTool) => {
    if (newTool?.name === "format_json") {
      loadJsonCollapseState();
    }
    if (newTool?.name !== "decode_qrcode") {
      qrCodeImage.value = "";
      toolForm.value.image_data = "";
    }
    // 切换工具时重置转换类型默认值
    if (newTool?.name === "case_convert") {
      toolForm.value.convert_type = "upper";
    } else if (newTool?.name === "ascii_convert") {
      toolForm.value.convert_type = "to_ascii";
    }
  },
);

const handleNodeExpand = (data, node) => {
  if (!jsonExpandedKeys.value.includes(data.key)) {
    jsonExpandedKeys.value.push(data.key);
    saveJsonCollapseState();
  }
};

const handleNodeCollapse = (data, node) => {
  const index = jsonExpandedKeys.value.indexOf(data.key);
  if (index > -1) {
    jsonExpandedKeys.value.splice(index, 1);
    saveJsonCollapseState();
  }
};

const handleQrCodeUpload = (file) => {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = (e) => {
      const base64Data = e.target.result;
      qrCodeImage.value = base64Data;
      toolForm.value.image_data = base64Data;
      resolve(false);
    };
    reader.onerror = () => {
      ElMessage.error(t("dataFactory.messages.imageReadFailed"));
      reject(false);
    };
    reader.readAsDataURL(file);
  });
};

const clearQrCodeImage = () => {
  qrCodeImage.value = "";
  toolForm.value.image_data = "";
};

const getInputStats = () => {
  const text = toolForm.value.json_str || "";
  return {
    chars: text.length,
    lines: text.split("\n").length,
  };
};

const getOutputStats = () => {
  if (!toolResult.value || !toolResult.value.result) {
    return { chars: 0, lines: 0 };
  }
  const text = toolResult.value.result;
  return {
    chars: text.length,
    lines: text.split("\n").length,
  };
};

const handleJsonDiffInput = async () => {
  if (currentTool.value?.name === "json_diff_enhanced") {
    if (!toolForm.value.json_str1 || !toolForm.value.json_str2) {
      toolResult.value = null;
      return;
    }
    try {
      const response = await axios.post("/api/data-factory/", {
        tool_name: "json_diff_enhanced",
        tool_category: "json",
        tool_scenario: "data_validation",
        input_data: {
          json_str1: toolForm.value.json_str1,
          json_str2: toolForm.value.json_str2,
          ignore_whitespace: toolForm.value.ignore_whitespace,
          show_only_diff: toolForm.value.show_only_diff,
        },
        is_saved: false,
      });
      toolResult.value = response.data;
    } catch (error) {
      toolResult.value = null;
    }
  }
};

const handleJsonPathInput = async () => {
  if (
    currentTool.value?.name === "jsonpath_query" &&
    toolForm.value.json_str &&
    toolForm.value.jsonpath_expr
  ) {
    try {
      const response = await axios.post("/api/data-factory/", {
        tool_name: "jsonpath_query",
        tool_category: "json",
        tool_scenario: "data_validation",
        input_data: {
          json_str: toolForm.value.json_str,
          jsonpath_expr: toolForm.value.jsonpath_expr,
        },
        is_saved: false,
      });
      toolResult.value = response.data;
    } catch (error) {
      toolResult.value = null;
    }
  }
};

const handleImageChange = (file) => {
  if (file.raw.size > 10 * 1024 * 1024) {
    ElMessage.error(t("dataFactory.messages.fileSizeLimit"));
    return false;
  }

  const reader = new FileReader();
  reader.onload = (e) => {
    imagePreview.value = e.target.result;
  };
  reader.readAsDataURL(file.raw);

  const fileReader = new FileReader();
  fileReader.onload = (e) => {
    const result = e.target.result;
    if (result.startsWith("data:image")) {
      toolForm.value.image_data = result.split(",")[1];
    } else {
      toolForm.value.image_data = result;
    }
  };
  fileReader.readAsDataURL(file.raw);
};

const downloadResult = () => {
  if (!toolResult.value) return;

  let content = "";
  let filename = "";
  let mimeType = "text/plain";

  const toolName = currentTool.value?.name;

  if (toolName === "json_to_xml") {
    content = toolResult.value.result || toolResult.value;
    filename = `${toolName}_${Date.now()}.xml`;
    mimeType = "application/xml";
  } else if (toolName === "xml_to_json") {
    content = toolResult.value.result || toolResult.value;
    filename = `${toolName}_${Date.now()}.json`;
    mimeType = "application/json";
  } else if (toolName === "json_to_yaml") {
    content = toolResult.value.result || toolResult.value;
    filename = `${toolName}_${Date.now()}.yaml`;
    mimeType = "text/yaml";
  } else if (toolName === "yaml_to_json") {
    content = toolResult.value.result || toolResult.value;
    filename = `${toolName}_${Date.now()}.json`;
    mimeType = "application/json";
  } else if (toolName === "json_to_csv") {
    content = toolResult.value.result || toolResult.value;
    filename = `${toolName}_${Date.now()}.csv`;
    mimeType = "text/csv;charset=utf-8";
    content = "\ufeff" + content;
  } else if (toolName === "csv_to_json") {
    content = toolResult.value.result || toolResult.value;
    filename = `${toolName}_${Date.now()}.csv`;
    mimeType = "text/csv;charset=utf-8";
    content = "\ufeff" + content;
  } else {
    content =
      typeof toolResult.value === "string"
        ? toolResult.value
        : JSON.stringify(toolResult.value, null, 2);
    filename = `${toolName}_${Date.now()}.json`;
    mimeType = "application/json";
  }

  const blob = new Blob([content], { type: mimeType });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  URL.revokeObjectURL(url);
};

const filterByScenario = (scenario) => {
  currentScenario.value = scenario;
  viewMode.value = "category";
  ElMessage.success(`${t("dataFactory.messages.filtered")}: ${scenario.name}`);
};

const clearScenario = () => {
  currentScenario.value = null;
};

const filteredCategories = () => {
  if (!currentScenario.value) return categories.value;
  return categories.value
    .map((category) => ({
      ...category,
      tools: category.tools.filter(
        (tool) => tool.scenario === currentScenario.value.scenario,
      ),
    }))
    .filter((category) => category.tools.length > 0);
};

// 防抖加载历史记录
const debouncedFetchHistory = debounce(async () => {
  if (historyLoading.value) return;

  historyLoading.value = true;
  try {
    const response = await axios.get("/api/data-factory/", {
      params: {
        page: historyCurrentPage.value,
        page_size: historyPageSize.value,
        _t: Date.now(),
      },
    });

    historyRecords.value = response.data.results;
    historyTotal.value = response.data.count;
  } catch (error) {
    ElMessage.error(t("dataFactory.messages.fetchHistoryFailed"));
  } finally {
    historyLoading.value = false;
  }
}, 300);

const fetchHistory = async () => {
  debouncedFetchHistory();
};

const fetchHistoryImmediate = async () => {
  if (historyLoading.value) return;

  historyLoading.value = true;
  try {
    const response = await axios.get("/api/data-factory/", {
      params: {
        page: historyCurrentPage.value,
        page_size: historyPageSize.value,
        _t: Date.now(),
      },
    });

    historyRecords.value = response.data.results;
    historyTotal.value = response.data.count;
  } catch (error) {
    ElMessage.error(t("dataFactory.messages.fetchHistoryFailed"));
  } finally {
    historyLoading.value = false;
  }
};

const handleHistoryPageChange = (page) => {
  historyCurrentPage.value = page;
  fetchHistory();
};

const handleHistorySizeChange = (size) => {
  historyPageSize.value = size;
  historyCurrentPage.value = 1;
  fetchHistory();
};

const fetchStatistics = async () => {
  if (statsLoading.value) return;

  statsLoading.value = true;
  try {
    const response = await axios.get("/api/data-factory/statistics/", {
      params: {
        _t: Date.now(),
      },
    });

    statistics.value = response.data;
  } catch (error) {
    ElMessage.error(t("dataFactory.messages.fetchStatsFailed"));
  } finally {
    statsLoading.value = false;
  }
};

const deleteRecord = async (record) => {
  try {
    console.log("Delete record:", record);
    if (!record || !record.id) {
      ElMessage.error("记录不存在或已删除");
      return;
    }
    const response = await axios.delete(`/api/data-factory/${record.id}/`);
    ElMessage.success(t("dataFactory.history.deleteSuccess"));

    // 删除后清理统计缓存
    cache.remove("statistics");

    // 重新加载历史和统计数据
    await fetchHistoryImmediate();
    await fetchStatistics();
  } catch (error) {
    console.error("Delete error:", error);
    if (error.response && error.response.status === 404) {
      ElMessage.error("记录不存在或已删除");
      // 记录已不存在时刷新列表
      fetchHistory();
    } else if (error.response && error.response.status === 403) {
      ElMessage.error("没有删除权限");
    } else {
      ElMessage.error(t("dataFactory.history.deleteFailed"));
    }
  }
};

const calculatePercentage = (value, total) => {
  if (!total) return 0;
  return Math.round((value / total) * 100);
};

const formatDateTime = (dateTime) => {
  if (!dateTime) return "";
  const date = new Date(dateTime);
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  const hours = String(date.getHours()).padStart(2, "0");
  const minutes = String(date.getMinutes()).padStart(2, "0");
  const seconds = String(date.getSeconds()).padStart(2, "0");
  return `${year}-${month}-${day} ${hours}:${minutes}:${seconds}`;
};

const getImageUrl = (url) => {
  if (!url) return "";
  if (url.startsWith("http")) return url;
  return `/api/data-factory/download_static_file/?filename=${url.split("/").pop()}`;
};

const downloadImage = (result) => {
  if (!result || !result.url) {
    ElMessage.error(t("dataFactory.messages.imageUrlNotFound"));
    return;
  }

  const link = document.createElement("a");
  const filename = result.url.split("/").pop();
  const downloadUrl = `/api/data-factory/download_static_file/?filename=${filename}`;
  link.href = downloadUrl;
  link.download = result.filename || "image.png";
  link.target = "_blank";
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  ElMessage.success(t("dataFactory.messages.downloadStarted"));
};

const parseTagsText = (text) => {
  if (!text) return [];
  return text
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean);
};

const accountRangePreview = computed(() => {
  const start = accountImportForm.value.rangeStart.trim();
  const end = accountImportForm.value.rangeEnd.trim();
  if (!start || !end) return "请输入起始号码和结束号码";
  if (!/^\d+$/.test(start) || !/^\d+$/.test(end)) return "号段只能填写数字";

  const startNumber = Number.parseInt(start, 10);
  const endNumber = Number.parseInt(end, 10);
  if (startNumber > endNumber) return "起始号码不能大于结束号码";

  const count = endNumber - startNumber + 1;
  if (count > 10000) return `本次将导入 ${count} 个账号，超过上限 10000 个`;
  return `预计导入 ${count} 个账号：${start} ~ ${end}`;
});

const selectedBusinessLoadScenario = computed(() => {
  return businessLoadOptions.value.scenarios.find(
    (item) => item.value === businessLoadForm.value.scenario_type,
  );
});

const businessLoadScenarioCards = computed(() => {
  const meta = {
    room_list_load: {
      icon: List,
      description: "拉取普通/专属语音房列表，观察接口、排序、置顶和房间数据。",
      fit: "适合列表巡检、选房准备",
      badge: "基础",
      statusType: "info",
    },
    voice_room_online: {
      icon: VideoPlay,
      description: "账号进入指定语音房并心跳保活，验证进房和在线稳定性。",
      fit: "适合进房、心跳、保活",
      badge: "可用",
      statusType: "success",
    },
    im_message_flood: {
      icon: ChatDotSquare,
      description: "按真实链路进入社区/房间后发送 IM 消息，模拟刷屏流量。",
      fit: "适合 IM 消息压力",
      badge: "可用",
      statusType: "success",
    },
    team_recruit_publish: {
      icon: Share,
      description: "进入房间后发布组队、发送通知、保活并支持取消招募。",
      fit: "适合组队招募验证",
      badge: "可用",
      statusType: "success",
    },
    community_activity_simulation: {
      icon: Connection,
      description:
        "固定用户占房 + 流动用户进出房，制造社区维度的房间列表动态变化。",
      fit: "适合社区热度造数",
      badge: "新增",
      statusType: "warning",
    },
  };
  return (businessLoadOptions.value.scenarios || []).map((scenario) => ({
    ...scenario,
    ...(meta[scenario.value] || {
      icon: Operation,
      description: scenario.description || "按配置执行业务压测链路。",
      fit: "适合定制业务场景",
      badge: "可用",
      statusType: "info",
    }),
  }));
});

const currentBusinessLoadScenarioCard = computed(() => {
  return businessLoadScenarioCards.value.find(
    (item) => item.value === businessLoadActiveScenario.value,
  );
});

const businessLoadRequiresRoom = computed(() => {
  return (selectedBusinessLoadScenario.value?.capabilities || []).some(
    (item) => item.key === "enter_room",
  );
});

const businessLoadUsesRoomList = computed(() => {
  return (selectedBusinessLoadScenario.value?.capabilities || []).some((item) =>
    ["fetch_room_list", "enter_room"].includes(item.key),
  );
});

const businessLoadIsImScenario = computed(() => {
  return businessLoadForm.value.scenario_type === "im_message_flood";
});

const businessLoadIsTeamScenario = computed(() => {
  return businessLoadForm.value.scenario_type === "team_recruit_publish";
});

const businessLoadIsCommunityActivityScenario = computed(() => {
  return (
    businessLoadForm.value.scenario_type === "community_activity_simulation"
  );
});

const businessLoadActivityAccountTotal = computed(() => {
  const residentCount = Number(businessLoadForm.value.resident_user_count || 0);
  const transientCount = Number(
    businessLoadForm.value.transient_user_count || 0,
  );
  return residentCount + transientCount;
});

const businessLoadNeedsRoomTarget = computed(() => {
  return (
    businessLoadIsTeamScenario.value ||
    (businessLoadIsImScenario.value &&
      ["room", "party"].includes(businessLoadForm.value.target_type))
  );
});

const getBusinessLoadDialogTip = () => {
  if (businessLoadIsTeamScenario.value) {
    return "发布组队会真实进房、心跳、发布组队并发送 IM 通知；建议先小流量试跑。";
  }
  if (businessLoadIsImScenario.value) {
    return "IM 场景支持选择社区/房间后发送消息；开启真实发送前请确认账号数和发送间隔。";
  }
  if (businessLoadIsCommunityActivityScenario.value) {
    return "社区活跃模拟会先固定用户占房，再让流动用户进出/切房；优先选多个目标房间后小流量试跑。";
  }
  return "先选择社区和语音房，再执行预检查和小流量试跑。";
};

const filteredBusinessRoomPreviewList = computed(() => {
  const keyword = String(businessRoomOrderKeyword.value || "").trim();
  return businessRoomPreviewList.value.filter((room) => {
    const keywordMatched =
      !keyword ||
      [
        room.display_order,
        room.room_order,
        room.sort_index_num,
        room.channel_id,
        room.channel_name,
      ].some((value) => String(value || "").includes(keyword));
    return keywordMatched && isBusinessRoomTypeMatched(room);
  });
});

const isBusinessRoomTypeMatched = (room) => {
  const filterValue = businessRoomTypeFilter.value;
  if (filterValue === "all") return true;

  const label = String(
    room.room_type_label || room.roomTypeLabel || room.room_mode_label || "",
  ).trim();
  const model = Number(
    room.channel_model ??
      room.channelModel ??
      room.room_type ??
      room.roomType ??
      room.model,
  );
  const mode = String(room.room_mode || room.roomMode || room.mode || "")
    .trim()
    .toLowerCase();

  // 后续专属语音房也复用这个判断，只要列表项继续带 room_source + 模式字段即可。
  const isInteractive =
    label.includes("麦序") ||
    label.includes("互动") ||
    mode.includes("interactive") ||
    model === 3;
  if (filterValue === "interactive") return isInteractive;
  if (filterValue === "game") return !isInteractive;
  return true;
};

const selectedBusinessCommunity = computed(() => {
  const serverId = String(businessLoadForm.value.server_id || "");
  return businessCommunityOptions.value.find(
    (item) => String(item.server_id) === serverId,
  );
});

const selectedBusinessCommunityHasExclusiveRooms = computed(() => {
  return !!selectedBusinessCommunity.value?.has_exclusive_rooms;
});

const selectedBusinessRoomTarget = computed(() => {
  return selectedBusinessRooms.value[0] || null;
});

const getBusinessRoomSourceLabel = (room) => {
  const source = String(room?.room_source || "").toLowerCase();
  if (source === "exclusive") return "专属房";
  if (source === "toplist") return "普通置顶";
  if (source === "pagelist" || source === "normal") return "普通房";
  return source ? source : "-";
};

const mergeBusinessRoomPreviewList = (rooms, roomSource = "normal") => {
  const normalizedRooms = (rooms || []).map((room) => ({
    ...room,
    source_display_order: room.source_display_order || room.display_order,
    room_source: room.room_source || roomSource,
  }));
  const nextRooms =
    roomSource === "exclusive" ? [...businessRoomPreviewList.value] : [];
  const seenChannelIds = new Set(
    nextRooms.map((room) => String(room.channel_id || "")),
  );

  normalizedRooms.forEach((room) => {
    const channelId = String(room.channel_id || "");
    if (!channelId || seenChannelIds.has(channelId)) return;
    nextRooms.push(room);
    seenChannelIds.add(channelId);
  });

  businessRoomPreviewList.value = nextRooms.map((room, index) => ({
    ...room,
    display_order: index + 1,
  }));
};

const imTargetTypeMap = {
  c2c: { label: "C2C", bizType: 1 },
  group: { label: "Group", bizType: 2 },
  room: { label: "Room", bizType: 5 },
  party: { label: "Party", bizType: 6 },
};

const getImTargetLabel = (config = {}) => {
  const targetType =
    imTargetTypeMap[config.target_type] || imTargetTypeMap.room;
  const targetName = config.target_name || targetType.label;
  const targetId = config.target_id || "-";
  return `${targetType.label} / ${targetName} / ${targetId}`;
};

const getTeamPublishRoomRows = (task = {}) => {
  const configuredRooms = task.config?.target_rooms || [];
  const trialRecords = task.metrics?.last_trial_run?.room_entry_records || [];
  const trialAccountResults =
    task.metrics?.last_trial_run?.account_results || [];
  const publishRecords = task.metrics?.team_room_publish_records || {};
  const roomMap = new Map();
  const trialResultMap = new Map();

  trialAccountResults.forEach((result) => {
    const channelId = String(
      result.channel_id || result.room_entry?.channel_id || "",
    );
    if (channelId) trialResultMap.set(channelId, result);
  });

  configuredRooms.forEach((room, index) => {
    const channelId = String(room.channel_id || room.channelId || "");
    if (!channelId) return;
    roomMap.set(channelId, {
      channel_id: channelId,
      channel_name: room.channel_name || room.channelName || `房间${index + 1}`,
      room_type_label: room.room_type_label || room.roomTypeLabel || "-",
      display_order: room.display_order || room.displayOrder || index + 1,
      heartbeat: false,
      heartbeat_rounds: 0,
      team_published: false,
      im_notification_sent: false,
      cleaned: false,
      last_message: task.config?.team_message_template || "",
      last_template: task.config?.team_message_template || "",
      current_duration_minutes: task.config?.team_duration_minutes || "",
      current_max_members: task.config?.team_max_members_num || "",
      current_team_mode: task.config?.team_mode || "",
      last_published_at: "",
      last_cancelled_at: "",
      cancelled: false,
      source: "configured",
    });
  });

  trialRecords.forEach((record) => {
    const channelId = String(record.channel_id || "");
    if (!channelId) return;
    const current = roomMap.get(channelId) || { channel_id: channelId };
    const trialResult = trialResultMap.get(channelId) || {};
    const teamContext = trialResult.team_context || {};
    roomMap.set(channelId, {
      ...current,
      channel_name: current.channel_name || record.channel_name || "",
      room_type_label: current.room_type_label || record.room_type_label || "-",
      heartbeat: !!record.heartbeat,
      heartbeat_rounds:
        record.heartbeat_rounds || current.heartbeat_rounds || 0,
      team_published: !!record.team_published,
      im_notification_sent: !!record.im_notification_sent,
      cleaned: !!(record.team_closed && record.left),
      rid: record.rid || current.rid || "",
      last_message: teamContext.message || current.last_message || "",
      current_duration_minutes:
        teamContext.duration_minutes || current.current_duration_minutes || "",
      current_max_members:
        teamContext.max_members || current.current_max_members || "",
      current_team_mode:
        teamContext.team_mode || current.current_team_mode || "",
      source: "trial",
    });
  });

  Object.values(publishRecords).forEach((record) => {
    const channelId = String(record.channel_id || "");
    if (!channelId) return;
    const current = roomMap.get(channelId) || { channel_id: channelId };
    const result = record.last_result || {};
    const roomEntry = result.room_entry || {};
    roomMap.set(channelId, {
      ...current,
      channel_name:
        record.channel_name ||
        current.channel_name ||
        roomEntry.channel_name ||
        "",
      room_type_label:
        record.room_type_label ||
        current.room_type_label ||
        roomEntry.room_type_label ||
        "-",
      heartbeat: !!roomEntry.heartbeat,
      heartbeat_rounds:
        roomEntry.heartbeat_rounds ||
        result.team_keepalive_rounds ||
        current.heartbeat_rounds ||
        0,
      team_published: !!roomEntry.team_published,
      im_notification_sent: !!roomEntry.im_notification_sent,
      cleaned: !!(roomEntry.team_closed && roomEntry.left),
      cancelled: !!record.cancelled,
      last_cancelled_at:
        record.last_cancelled_at || current.last_cancelled_at || "",
      last_message:
        result.team_context?.message ||
        record.last_overrides?.team_message_template ||
        current.last_message ||
        "",
      last_template:
        record.last_overrides?.team_message_template ||
        current.last_template ||
        task.config?.team_message_template ||
        "",
      current_duration_minutes:
        result.team_context?.duration_minutes ||
        record.last_overrides?.team_duration_minutes ||
        current.current_duration_minutes ||
        "",
      current_max_members:
        result.team_context?.max_members ||
        record.last_overrides?.team_max_members_num ||
        current.current_max_members ||
        "",
      current_team_mode:
        result.team_context?.team_mode ||
        record.last_overrides?.team_mode ||
        current.current_team_mode ||
        "",
      last_published_at: record.last_published_at || "",
      stage: record.stage || "",
      passed: !!record.passed,
      source: "republish",
    });
  });

  return Array.from(roomMap.values()).sort((a, b) => {
    return Number(a.display_order || 9999) - Number(b.display_order || 9999);
  });
};

const getTeamRoomRecruitStatus = (room = {}) => {
  if (room.stage) return room.stage;
  if (room.cancelled) return "已取消";
  if (room.cleaned) return "已清理";
  if (room.team_published) return "招募中";
  return "待发布";
};

const getTeamRoomRecruitStatusType = (room = {}) => {
  if (room.cancelled) return "info";
  if (room.cleaned) return "success";
  if (room.team_published) return "warning";
  return "info";
};

const getBusinessCommunityLabel = (item) => {
  const serverNo = item.server_no
    ? `社区号 ${item.server_no}`
    : `serverId ${item.server_id}`;
  return `${item.server_name} (${serverNo})`;
};

const getAccountApiError = (error, fallback) => {
  const data = error.response?.data;
  if (typeof data === "string") return data;
  if (Array.isArray(data)) return data.join("; ");
  return data?.detail || data?.error || fallback;
};

const openAccountPool = async () => {
  viewMode.value = "account_pool";
  await fetchAccountOptions();
  await Promise.all([fetchAccountPool(), fetchAccountStats()]);
};

const fetchAccountOptions = async () => {
  try {
    const response = await axios.get("/api/data-factory/account-pool/options/");
    accountOptions.value = response.data;
  } catch (error) {
    console.warn("Fetch account options failed:", error);
  }
};

const fetchAccountStats = async () => {
  try {
    const response = await axios.get(
      "/api/data-factory/account-pool/statistics/",
      {
        params: {
          environment: accountFilters.value.environment || undefined,
          business_domain: accountFilters.value.business_domain || undefined,
          status: accountFilters.value.status || undefined,
          keyword: accountFilters.value.keyword || undefined,
          _t: Date.now(),
        },
      },
    );
    accountStats.value = response.data;
  } catch (error) {
    ElMessage.error("加载账号统计失败");
  }
};

const fetchAccountPool = async () => {
  accountLoading.value = true;
  try {
    const response = await axios.get("/api/data-factory/account-pool/", {
      params: {
        page: accountCurrentPage.value,
        page_size: accountPageSize.value,
        environment: accountFilters.value.environment || undefined,
        business_domain: accountFilters.value.business_domain || undefined,
        status: accountFilters.value.status || undefined,
        keyword: accountFilters.value.keyword || undefined,
        _t: Date.now(),
      },
    });
    accountRecords.value = response.data.results || [];
    accountTotal.value = response.data.count || 0;
    await fetchAccountStats();
  } catch (error) {
    ElMessage.error("加载账号池失败");
  } finally {
    accountLoading.value = false;
  }
};

const resetAccountForm = () => {
  accountForm.value = {
    account_no: "",
    phone: "",
    user_id: "",
    nickname: "",
    password: "",
    token: "",
    environment: accountFilters.value.environment || "test",
    business_domain: accountFilters.value.business_domain || "common",
    status: "available",
    purpose: "",
    tagsText: "",
    remark: "",
  };
};

const openAccountDialog = async (row = null) => {
  const isCreate = !row;
  accountDialogMode.value = row ? "edit" : "create";
  if (row) {
    accountForm.value = {
      ...row,
      password: "",
      token: "",
      tagsText: Array.isArray(row.tags) ? row.tags.join(",") : "",
    };
  } else {
    resetAccountForm();
  }
  accountDialogVisible.value = true;
  await nextTick();
  setTimeout(() => {
    accountForm.value.password = "";
    accountForm.value.token = "";
    if (isCreate) {
      accountForm.value.purpose = "";
    }
  }, 100);
};

const buildAccountPayload = () => ({
  account_no: accountForm.value.account_no,
  phone: accountForm.value.phone || "",
  user_id: accountForm.value.user_id || "",
  nickname: accountForm.value.nickname || "",
  environment: accountForm.value.environment,
  business_domain: accountForm.value.business_domain,
  status: accountForm.value.status || "available",
  purpose: accountForm.value.purpose || "",
  tags: parseTagsText(accountForm.value.tagsText),
  remark: accountForm.value.remark || "",
  ...(accountForm.value.password
    ? { password: accountForm.value.password }
    : {}),
  ...(accountForm.value.token ? { token: accountForm.value.token } : {}),
});

const saveAccount = async () => {
  if (!accountForm.value.account_no) {
    ElMessage.warning("请填写账号");
    return;
  }
  accountSaving.value = true;
  try {
    const payload = buildAccountPayload();
    if (accountDialogMode.value === "edit") {
      await axios.patch(
        `/api/data-factory/account-pool/${accountForm.value.id}/`,
        payload,
      );
    } else {
      await axios.post("/api/data-factory/account-pool/", payload);
    }
    ElMessage.success("账号保存成功");
    accountDialogVisible.value = false;
    await fetchAccountPool();
  } catch (error) {
    ElMessage.error(getAccountApiError(error, "账号保存失败"));
  } finally {
    accountSaving.value = false;
  }
};

const importAccounts = async () => {
  let rawText = accountImportForm.value.raw_text.trim();
  if (accountImportForm.value.importMode === "range") {
    const start = accountImportForm.value.rangeStart.trim();
    const end = accountImportForm.value.rangeEnd.trim();
    if (!start || !end) {
      ElMessage.warning("请填写起始号码和结束号码");
      return;
    }
    if (!/^\d+$/.test(start) || !/^\d+$/.test(end)) {
      ElMessage.warning("号段只能填写数字");
      return;
    }
    const startNumber = Number.parseInt(start, 10);
    const endNumber = Number.parseInt(end, 10);
    if (startNumber > endNumber) {
      ElMessage.warning("起始号码不能大于结束号码");
      return;
    }
    if (endNumber - startNumber + 1 > 10000) {
      ElMessage.warning("单次最多导入 10000 个账号");
      return;
    }
    rawText = `${start}~${end}`;
  } else if (!rawText) {
    ElMessage.warning("请填写账号文本");
    return;
  }

  accountSaving.value = true;
  try {
    const response = await axios.post(
      "/api/data-factory/account-pool/bulk-import/",
      {
        environment: accountImportForm.value.environment,
        business_domain: accountImportForm.value.business_domain,
        purpose: accountImportForm.value.purpose || "",
        tags: parseTagsText(accountImportForm.value.tagsText),
        raw_text: rawText,
      },
    );
    ElMessage.success(
      `导入完成：新增 ${response.data.created_count}，更新 ${response.data.updated_count}，跳过 ${response.data.skipped_count}`,
    );
    accountImportVisible.value = false;
    accountImportForm.value.raw_text = "";
    accountImportForm.value.rangeStart = "";
    accountImportForm.value.rangeEnd = "";
    await fetchAccountPool();
  } catch (error) {
    ElMessage.error(getAccountApiError(error, "账号导入失败"));
  } finally {
    accountSaving.value = false;
  }
};

const openAccountAllocateDialog = () => {
  accountAllocateForm.value = {
    environment: accountFilters.value.environment || "test",
    business_domain: accountFilters.value.business_domain || "",
    count: 1,
    purpose: "",
    tagsText: "",
  };
  accountAllocateVisible.value = true;
};

const allocateAccounts = async () => {
  accountSaving.value = true;
  try {
    const response = await axios.post(
      "/api/data-factory/account-pool/allocate/",
      {
        environment: accountAllocateForm.value.environment,
        business_domain: accountAllocateForm.value.business_domain || undefined,
        count: accountAllocateForm.value.count,
        purpose: accountAllocateForm.value.purpose || "",
        tags: parseTagsText(accountAllocateForm.value.tagsText),
      },
    );
    ElMessage.success(`已分配 ${response.data.count} 个账号`);
    accountAllocateVisible.value = false;
    await fetchAccountPool();
  } catch (error) {
    ElMessage.error(getAccountApiError(error, "账号分配失败"));
  } finally {
    accountSaving.value = false;
  }
};

const releaseAccount = async (row) => {
  try {
    await axios.post(`/api/data-factory/account-pool/${row.id}/release/`);
    ElMessage.success("账号已释放");
    await fetchAccountPool();
  } catch (error) {
    ElMessage.error(getAccountApiError(error, "账号释放失败"));
  }
};

const deleteAccount = async (row) => {
  try {
    await ElMessageBox.confirm(`确认删除账号 ${row.account_no}？`, "删除账号", {
      type: "warning",
    });
    await axios.delete(`/api/data-factory/account-pool/${row.id}/`);
    ElMessage.success("账号已删除");
    await fetchAccountPool();
  } catch (error) {
    if (error !== "cancel") {
      ElMessage.error(getAccountApiError(error, "账号删除失败"));
    }
  }
};

const openBusinessLoad = async () => {
  viewMode.value = "business_load";
  await fetchBusinessLoadOptions();
  if (businessLoadActiveScenario.value) {
    await fetchBusinessLoadTasks();
  }
};

const fetchBusinessLoadOptions = async () => {
  try {
    const response = await axios.get(
      "/api/data-factory/business-load/tasks/options/",
    );
    businessLoadOptions.value = response.data;
  } catch (error) {
    ElMessage.error("加载业务压测配置失败");
  }
};

const fetchBusinessLoadTasks = async () => {
  if (!businessLoadActiveScenario.value) {
    businessLoadTasks.value = [];
    businessLoadTotal.value = 0;
    return;
  }
  businessLoadLoading.value = true;
  try {
    const response = await axios.get("/api/data-factory/business-load/tasks/", {
      params: {
        page: businessLoadCurrentPage.value,
        page_size: businessLoadPageSize.value,
        scenario_type: businessLoadActiveScenario.value,
        status: businessLoadFilters.value.status || undefined,
        keyword: businessLoadFilters.value.keyword || undefined,
        _t: Date.now(),
      },
    });
    businessLoadTasks.value = response.data.results || [];
    businessLoadTotal.value = response.data.count || 0;
    if (businessLoadDetailVisible.value && businessLoadDetailTask.value?.id) {
      const latest = businessLoadTasks.value.find(
        (item) => item.id === businessLoadDetailTask.value.id,
      );
      if (latest) businessLoadDetailTask.value = latest;
    }
  } catch (error) {
    ElMessage.error("加载业务压测任务失败");
  } finally {
    businessLoadLoading.value = false;
  }
};

const enterBusinessLoadScenario = (scenarioValue) => {
  const scenario = businessLoadScenarioCards.value.find(
    (item) => item.value === scenarioValue,
  );
  if (scenario?.disabled) {
    ElMessage.info("这个场景会独立设计页面，暂时不接入当前通用表单。");
    return;
  }
  businessLoadActiveScenario.value = scenarioValue;
  businessLoadFilters.value.scenario_type = scenarioValue;
  businessLoadFilters.value.status = "";
  businessLoadFilters.value.keyword = "";
  businessLoadCurrentPage.value = 1;
  fetchBusinessLoadTasks();
};

const backBusinessLoadScenarioHome = () => {
  businessLoadActiveScenario.value = "";
  businessLoadFilters.value.scenario_type = "";
  businessLoadFilters.value.status = "";
  businessLoadFilters.value.keyword = "";
  businessLoadCurrentPage.value = 1;
  businessLoadTasks.value = [];
  businessLoadTotal.value = 0;
};

const openBusinessLoadDetail = (row) => {
  businessLoadDetailTask.value = row;
  businessLoadDetailVisible.value = true;
};

const handleBusinessLoadCommand = (command, row) => {
  const actions = {
    start: () => startBusinessLoadTask(row),
    trial: () => trialRunBusinessLoadTask(row),
    stop: () => stopBusinessLoadTask(row),
    delete: () => deleteBusinessLoadTask(row),
  };
  actions[command]?.();
};

const getBusinessLoadTargetBrief = (row) => {
  if (row?.scenario_type === "im_message_flood") {
    return getImTargetLabel(row.config);
  }
  const config = row?.config || {};
  const community =
    config.server_name || config.server_no || config.server_id || "-";
  const rooms = Array.isArray(config.target_rooms)
    ? config.target_rooms.length
    : 0;
  return `社区 ${community} · ${rooms ? `${rooms} 个房间` : "自动选房"}`;
};

const getBusinessLoadScaleBrief = (row) => {
  const config = row?.config || {};
  if (row?.scenario_type === "community_activity_simulation") {
    const residentCount = config.resident_user_count ?? 0;
    const transientCount = config.transient_user_count ?? 0;
    const duration = config.duration_seconds || row?.duration_seconds || "-";
    return `固定 ${residentCount} · 流动 ${transientCount} · ${duration}s`;
  }
  const duration = config.duration_seconds || row?.duration_seconds || "-";
  const rate = config.request_rate_per_second || "-";
  return `${row?.account_count || 0} 个账号 · ${duration}s · ${rate}/s`;
};

const getBusinessLoadTrialSummaryStats = (task = {}) => {
  const summary = task.metrics?.last_trial_run?.summary || {};
  if (task.scenario_type === "community_activity_simulation") {
    return [
      { label: "账号数", value: summary.total_accounts || 0 },
      {
        label: "固定在线",
        value: summary.resident_online || 0,
        type: "success",
      },
      {
        label: "流动用户",
        value: summary.transient_executed || 0,
        type: "success",
      },
      {
        label: "切房次数",
        value: summary.transient_switches || 0,
        type: "success",
      },
      { label: "占用房间", value: summary.occupied_room_count || 0 },
      { label: "失败数", value: summary.failed_count || 0, type: "danger" },
    ].map((item) => ({ ...item, span: 4 }));
  }
  if (task.scenario_type === "team_recruit_publish") {
    return [
      { label: "账号数", value: summary.total_accounts || 0 },
      {
        label: "发布成功",
        value: summary.publish_team_success || 0,
        type: "success",
      },
      {
        label: "端上可见",
        value: `${summary.team_visible_success || 0}/${summary.team_visible_expected || 0}`,
        type: (summary.team_visible_missing || 0) > 0 ? "danger" : "success",
      },
      {
        label: "IM通知成功",
        value: summary.im_notification_success || 0,
        type: "success",
      },
      { label: "失败数", value: summary.failed_count || 0, type: "danger" },
    ];
  }
  return [
    { label: "账号数", value: summary.total_accounts || 0 },
    {
      label: "进房成功",
      value: summary.enter_room_success || 0,
      type: "success",
    },
    {
      label: "心跳成功",
      value: summary.heartbeat_success || 0,
      type: "success",
    },
    { label: "失败数", value: summary.failed_count || 0, type: "danger" },
  ];
};

const syncCommunityActivityAccountCount = () => {
  if (!businessLoadIsCommunityActivityScenario.value) return;
  businessLoadForm.value.account_count = businessLoadActivityAccountTotal.value;
};

const resetBusinessLoadForm = () => {
  const scenario = businessLoadOptions.value.scenarios[0] || {};
  const config = scenario.default_config || {};
  businessLoadForm.value = {
    name: "",
    scenario_type: scenario.value || "room_list_load",
    environment: "test",
    business_domain: scenario.business_domain || "room",
    account_count: config.account_count || 10,
    accountTagsText: "",
    purpose: "",
    base_url: config.base_url || DEFAULT_BUSINESS_BASE_URL,
    probe_phone: "",
    server_id: config.server_id || 55984,
    server_name: config.server_name || "",
    server_no: config.server_no || "",
    room_selection_mode: config.room_selection_mode || "auto",
    room_assignment_mode: config.room_assignment_mode || "round_robin",
    users_per_room: config.users_per_room || 2,
    duration_seconds: config.duration_seconds || 60,
    request_rate_per_second:
      config.request_rate_per_second || config.enter_rate_per_second || 5,
    target_type: config.target_type || "room",
    target_id: config.target_id || "",
    target_name: config.target_name || "",
    biz_type: config.biz_type || 5,
    message_template:
      config.message_template ||
      "QAFlow_IM_{{run_id}}_{{account_no}}_{{sequence}}_{{timestamp}}",
    team_message_template:
      config.team_message_template ||
      "QAFlow_team_{{run_id}}_{{account_no}}_{{timestamp}}",
    team_duration_minutes: config.team_duration_minutes || 1,
    team_max_members_num: config.team_max_members_num || 2,
    team_mode: config.team_mode || "all",
    team_publish_concurrency: config.team_publish_concurrency || 1,
    team_publish_interval_ms: config.team_publish_interval_ms ?? 500,
    team_publish_reliable_visible:
      config.team_publish_reliable_visible !== false,
    team_visibility_wait_seconds: config.team_visibility_wait_seconds ?? 10,
    team_keepalive_after_notify: config.team_keepalive_after_notify !== false,
    resident_user_count: config.resident_user_count ?? 10,
    transient_user_count: config.transient_user_count ?? 10,
    transient_switch_ratio: config.transient_switch_ratio ?? 55,
    transient_to_resident_ratio: config.transient_to_resident_ratio ?? 80,
    transient_stay_min_seconds: config.transient_stay_min_seconds ?? 3,
    transient_stay_max_seconds: config.transient_stay_max_seconds ?? 5,
    heartbeat_interval_seconds: config.heartbeat_interval_seconds ?? 30,
    enter_rate_per_second: config.enter_rate_per_second ?? 5,
    leave_rate_per_second: config.leave_rate_per_second ?? 6,
    room_failure_cooldown_seconds: config.room_failure_cooldown_seconds ?? 45,
    cleanup_after_stop: config.cleanup_after_stop !== false,
    interval_ms: config.interval_ms || 1000,
    login_interval_ms: config.login_interval_ms || 100,
    auto_reconnect: config.auto_reconnect !== false,
    real_traffic_enabled: !!config.real_traffic_enabled,
    runner_path: config.runner_path || DEFAULT_IM_RUNNER_PATH,
    runner_timeout_seconds: config.runner_timeout_seconds || 120,
  };
  businessRoomPreviewList.value = [];
  selectedBusinessRooms.value = [];
  businessRoomOrderKeyword.value = "";
  businessRoomTypeFilter.value = "all";
};

const openBusinessLoadDialog = async (row = null, scenarioValue = "") => {
  if (!businessLoadOptions.value.scenarios.length) {
    await fetchBusinessLoadOptions();
  }
  const requestedScenario = businessLoadOptions.value.scenarios.find(
    (item) => item.value === scenarioValue,
  );
  if (scenarioValue && !requestedScenario) {
    ElMessage.info("这个场景会独立设计页面，暂时不接入当前通用表单。");
    return;
  }
  businessLoadDialogMode.value = row ? "edit" : "create";
  businessLoadAdvancedOpen.value = [];
  if (row) {
    businessLoadForm.value = {
      ...row,
      accountTagsText: Array.isArray(row.account_tags)
        ? row.account_tags.join(",")
        : "",
      base_url: row.config?.base_url || DEFAULT_BUSINESS_BASE_URL,
      probe_phone: row.config?.probe_phone || "",
      server_id: row.config?.server_id || 55984,
      server_name: row.config?.server_name || "",
      server_no: row.config?.server_no || "",
      room_selection_mode: row.config?.room_selection_mode || "auto",
      room_assignment_mode: row.config?.room_assignment_mode || "round_robin",
      users_per_room: row.config?.users_per_room || 2,
      duration_seconds: row.config?.duration_seconds || 60,
      request_rate_per_second:
        row.config?.request_rate_per_second ||
        row.config?.enter_rate_per_second ||
        5,
      target_type: row.config?.target_type || "room",
      target_id: row.config?.target_id || "",
      target_name: row.config?.target_name || "",
      biz_type: row.config?.biz_type || 5,
      message_template:
        row.config?.message_template ||
        "QAFlow_IM_{{run_id}}_{{account_no}}_{{sequence}}_{{timestamp}}",
      team_message_template:
        row.config?.team_message_template ||
        "QAFlow_team_{{run_id}}_{{account_no}}_{{timestamp}}",
      team_duration_minutes: row.config?.team_duration_minutes || 1,
      team_max_members_num: row.config?.team_max_members_num || 2,
      team_mode: row.config?.team_mode || "all",
      team_publish_concurrency: row.config?.team_publish_concurrency || 1,
      team_publish_interval_ms: row.config?.team_publish_interval_ms ?? 500,
      team_publish_reliable_visible:
        row.config?.team_publish_reliable_visible !== false,
      team_visibility_wait_seconds:
        row.config?.team_visibility_wait_seconds ?? 10,
      team_keepalive_after_notify:
        row.config?.team_keepalive_after_notify !== false,
      resident_user_count: row.config?.resident_user_count ?? 10,
      transient_user_count: row.config?.transient_user_count ?? 10,
      transient_switch_ratio: row.config?.transient_switch_ratio ?? 55,
      transient_to_resident_ratio:
        row.config?.transient_to_resident_ratio ?? 80,
      transient_stay_min_seconds: row.config?.transient_stay_min_seconds ?? 3,
      transient_stay_max_seconds: row.config?.transient_stay_max_seconds ?? 5,
      heartbeat_interval_seconds: row.config?.heartbeat_interval_seconds ?? 30,
      enter_rate_per_second: row.config?.enter_rate_per_second ?? 5,
      leave_rate_per_second: row.config?.leave_rate_per_second ?? 6,
      room_failure_cooldown_seconds:
        row.config?.room_failure_cooldown_seconds ?? 45,
      cleanup_after_stop: row.config?.cleanup_after_stop !== false,
      interval_ms: row.config?.interval_ms || 1000,
      login_interval_ms: row.config?.login_interval_ms || 100,
      auto_reconnect: row.config?.auto_reconnect !== false,
      real_traffic_enabled: !!row.config?.real_traffic_enabled,
      runner_path: row.config?.runner_path || DEFAULT_IM_RUNNER_PATH,
      runner_timeout_seconds: row.config?.runner_timeout_seconds || 120,
    };
    businessRoomPreviewList.value = row.config?.target_rooms || [];
    selectedBusinessRooms.value = row.config?.target_rooms || [];
    businessRoomOrderKeyword.value = "";
    businessRoomTypeFilter.value = "all";
  } else {
    resetBusinessLoadForm();
    if (requestedScenario) {
      businessLoadForm.value.scenario_type = requestedScenario.value;
      handleBusinessLoadScenarioChange();
    }
  }
  businessLoadDialogVisible.value = true;
  if (!businessLoadIsImScenario.value || businessLoadNeedsRoomTarget.value) {
    await searchBusinessCommunities(
      String(businessLoadForm.value.server_id || ""),
    );
  }
};

const handleBusinessLoadScenarioChange = () => {
  const scenario = selectedBusinessLoadScenario.value;
  if (!scenario) return;
  const config = scenario.default_config || {};
  businessLoadForm.value.business_domain =
    scenario.business_domain || businessLoadForm.value.business_domain;
  businessLoadForm.value.account_count =
    config.account_count || businessLoadForm.value.account_count || 1;
  businessLoadForm.value.base_url =
    config.base_url ||
    businessLoadForm.value.base_url ||
    DEFAULT_BUSINESS_BASE_URL;
  businessLoadForm.value.server_id =
    config.server_id || businessLoadForm.value.server_id || 55984;
  businessLoadForm.value.room_selection_mode =
    config.room_selection_mode ||
    businessLoadForm.value.room_selection_mode ||
    "auto";
  businessLoadForm.value.room_assignment_mode =
    config.room_assignment_mode ||
    businessLoadForm.value.room_assignment_mode ||
    "round_robin";
  businessLoadForm.value.users_per_room =
    config.users_per_room || businessLoadForm.value.users_per_room || 2;
  businessLoadForm.value.duration_seconds =
    config.duration_seconds || businessLoadForm.value.duration_seconds || 60;
  businessLoadForm.value.request_rate_per_second =
    config.request_rate_per_second ||
    config.enter_rate_per_second ||
    businessLoadForm.value.request_rate_per_second ||
    5;
  businessLoadForm.value.target_type =
    config.target_type || businessLoadForm.value.target_type || "room";
  businessLoadForm.value.target_id = config.target_id || "";
  businessLoadForm.value.target_name = config.target_name || "";
  businessLoadForm.value.biz_type =
    config.biz_type ||
    imTargetTypeMap[businessLoadForm.value.target_type]?.bizType ||
    5;
  businessLoadForm.value.message_template =
    config.message_template ||
    "QAFlow_IM_{{run_id}}_{{account_no}}_{{sequence}}_{{timestamp}}";
  businessLoadForm.value.team_message_template =
    config.team_message_template ||
    "QAFlow_team_{{run_id}}_{{account_no}}_{{timestamp}}";
  businessLoadForm.value.team_duration_minutes =
    config.team_duration_minutes || 1;
  businessLoadForm.value.team_max_members_num =
    config.team_max_members_num || 2;
  businessLoadForm.value.team_mode = config.team_mode || "all";
  businessLoadForm.value.team_publish_concurrency =
    config.team_publish_concurrency || 1;
  businessLoadForm.value.team_publish_interval_ms =
    config.team_publish_interval_ms ?? 500;
  businessLoadForm.value.team_publish_reliable_visible =
    config.team_publish_reliable_visible !== false;
  businessLoadForm.value.team_visibility_wait_seconds =
    config.team_visibility_wait_seconds ?? 10;
  businessLoadForm.value.team_keepalive_after_notify =
    config.team_keepalive_after_notify !== false;
  businessLoadForm.value.resident_user_count = config.resident_user_count ?? 10;
  businessLoadForm.value.transient_user_count =
    config.transient_user_count ?? 10;
  businessLoadForm.value.transient_switch_ratio =
    config.transient_switch_ratio ?? 55;
  businessLoadForm.value.transient_to_resident_ratio =
    config.transient_to_resident_ratio ?? 80;
  businessLoadForm.value.transient_stay_min_seconds =
    config.transient_stay_min_seconds ?? 3;
  businessLoadForm.value.transient_stay_max_seconds =
    config.transient_stay_max_seconds ?? 5;
  businessLoadForm.value.heartbeat_interval_seconds =
    config.heartbeat_interval_seconds ?? 30;
  businessLoadForm.value.enter_rate_per_second =
    config.enter_rate_per_second ??
    businessLoadForm.value.request_rate_per_second ??
    5;
  businessLoadForm.value.leave_rate_per_second =
    config.leave_rate_per_second ?? 6;
  businessLoadForm.value.room_failure_cooldown_seconds =
    config.room_failure_cooldown_seconds ?? 45;
  businessLoadForm.value.cleanup_after_stop =
    config.cleanup_after_stop !== false;
  syncCommunityActivityAccountCount();
  businessLoadForm.value.interval_ms = config.interval_ms || 1000;
  businessLoadForm.value.login_interval_ms = config.login_interval_ms || 100;
  businessLoadForm.value.auto_reconnect = config.auto_reconnect !== false;
  businessLoadForm.value.real_traffic_enabled = !!config.real_traffic_enabled;
  businessLoadForm.value.runner_path =
    config.runner_path || DEFAULT_IM_RUNNER_PATH;
  businessLoadForm.value.runner_timeout_seconds =
    config.runner_timeout_seconds || 120;
  if (businessLoadIsImScenario.value || businessLoadIsTeamScenario.value) {
    businessRoomPreviewList.value = [];
    selectedBusinessRooms.value = [];
    businessRoomOrderKeyword.value = "";
    businessRoomTypeFilter.value = "all";
  }
};

const handleBusinessLoadImTargetTypeChange = () => {
  businessLoadForm.value.biz_type =
    imTargetTypeMap[businessLoadForm.value.target_type]?.bizType || 5;
  if (businessLoadNeedsRoomTarget.value) {
    businessLoadForm.value.target_id = "";
    businessLoadForm.value.target_name = "";
  } else {
    businessRoomPreviewList.value = [];
    selectedBusinessRooms.value = [];
    businessRoomOrderKeyword.value = "";
    businessRoomTypeFilter.value = "all";
  }
};

const searchBusinessCommunities = async (keyword = "") => {
  businessCommunityLoading.value = true;
  try {
    const response = await axios.get(
      "/api/data-factory/business-load/tasks/community-candidates/",
      {
        params: {
          keyword,
          environment: businessLoadForm.value.environment || "test",
          base_url:
            businessLoadForm.value.base_url || DEFAULT_BUSINESS_BASE_URL,
          probe_phone: businessLoadForm.value.probe_phone || undefined,
          _t: Date.now(),
        },
      },
    );
    businessCommunityOptions.value = response.data.communities || [];
  } catch (error) {
    ElMessage.error("搜索社区失败");
  } finally {
    businessCommunityLoading.value = false;
  }
};

const handleBusinessCommunityChange = () => {
  const selected = selectedBusinessCommunity.value;
  businessLoadForm.value.server_name = selected?.server_name || "";
  businessLoadForm.value.server_no = selected?.server_no || "";
  businessRoomPreviewList.value = [];
  selectedBusinessRooms.value = [];
  businessRoomOrderKeyword.value = "";
  businessRoomTypeFilter.value = "all";
};

const loadBusinessRooms = async (roomSource = "normal") => {
  if (!businessLoadForm.value.server_id) {
    ElMessage.warning("请先选择目标社区");
    return;
  }
  if (
    roomSource === "exclusive" &&
    !selectedBusinessCommunityHasExclusiveRooms.value
  ) {
    ElMessage.info("当前社区未检测到专属语音房插件");
    return;
  }
  businessRoomLoading.value = true;
  try {
    const response = await axios.post(
      "/api/data-factory/business-load/tasks/room-list-preview/",
      {
        server_id: businessLoadForm.value.server_id,
        base_url: businessLoadForm.value.base_url || DEFAULT_BUSINESS_BASE_URL,
        probe_phone: businessLoadForm.value.probe_phone || "",
        environment: businessLoadForm.value.environment || "test",
        room_source: roomSource,
        page_size: 50,
        max_pages: 2,
      },
    );
    mergeBusinessRoomPreviewList(
      response.data.rooms || [],
      response.data.room_source || roomSource,
    );
    selectedBusinessRooms.value = [];
    businessRoomOrderKeyword.value = "";
    businessRoomTypeFilter.value = "all";
    ElMessage.success(
      response.data.message ||
        `已加载 ${businessRoomPreviewList.value.length} 个房间`,
    );
  } catch (error) {
    ElMessage.error("加载房间列表失败");
  } finally {
    businessRoomLoading.value = false;
  }
};

const handleBusinessRoomSelectionChange = (rows) => {
  selectedBusinessRooms.value = rows.map((row) => ({
    channel_id: row.channel_id,
    channel_name: row.channel_name,
    channel_type: row.channel_type,
    channel_model: row.channel_model,
    channel_template: row.channel_template,
    room_type: row.room_type,
    room_type_label: row.room_type_label,
    display_order: row.display_order,
    sort_index_num: row.sort_index_num,
    is_top_room: row.is_top_room,
    room_source: row.room_source,
    room_order: row.room_order,
    online_count: row.online_count,
    capacity: row.capacity,
  }));
  if (selectedBusinessRooms.value.length) {
    businessLoadForm.value.room_selection_mode = "manual";
    if (businessLoadNeedsRoomTarget.value) {
      const room = selectedBusinessRoomTarget.value;
      businessLoadForm.value.target_id = room?.channel_id || "";
      businessLoadForm.value.target_name = room?.channel_name || "";
    }
  }
};

const buildBusinessLoadPayload = () => {
  syncCommunityActivityAccountCount();
  const imRoomTarget = businessLoadNeedsRoomTarget.value
    ? selectedBusinessRoomTarget.value
    : null;
  const targetId =
    imRoomTarget?.channel_id || businessLoadForm.value.target_id || "";
  const targetName =
    imRoomTarget?.channel_name || businessLoadForm.value.target_name || "";
  const targetRooms = selectedBusinessRooms.value;
  const durationSeconds = normalizeTeamKeepaliveDuration();
  return {
    name: businessLoadForm.value.name,
    scenario_type: businessLoadForm.value.scenario_type,
    environment: businessLoadForm.value.environment,
    business_domain: businessLoadForm.value.business_domain,
    account_count: businessLoadForm.value.account_count,
    account_tags: parseTagsText(businessLoadForm.value.accountTagsText),
    purpose: businessLoadForm.value.purpose || "",
    config: {
      base_url: businessLoadForm.value.base_url || DEFAULT_BUSINESS_BASE_URL,
      server_id: businessLoadForm.value.server_id,
      server_name:
        businessLoadForm.value.server_name ||
        selectedBusinessCommunity.value?.server_name ||
        "",
      server_no:
        businessLoadForm.value.server_no ||
        selectedBusinessCommunity.value?.server_no ||
        "",
      account_count: businessLoadForm.value.account_count,
      duration_seconds: durationSeconds,
      request_rate_per_second: businessLoadForm.value.request_rate_per_second,
      probe_phone: businessLoadForm.value.probe_phone || "",
      room_selection_mode: targetRooms.length
        ? "manual"
        : businessLoadForm.value.room_selection_mode,
      room_assignment_mode:
        businessLoadForm.value.room_assignment_mode || "round_robin",
      users_per_room: businessLoadForm.value.users_per_room || 1,
      target_rooms: targetRooms,
      target_type: businessLoadForm.value.target_type || "room",
      target_id: targetId,
      target_name: targetName,
      biz_type:
        businessLoadForm.value.biz_type ||
        imTargetTypeMap[businessLoadForm.value.target_type]?.bizType ||
        5,
      message_template:
        businessLoadForm.value.message_template ||
        "QAFlow_IM_{{run_id}}_{{account_no}}_{{sequence}}_{{timestamp}}",
      team_message_template:
        businessLoadForm.value.team_message_template ||
        "QAFlow_team_{{run_id}}_{{account_no}}_{{timestamp}}",
      team_duration_minutes: businessLoadForm.value.team_duration_minutes || 1,
      team_max_members_num: businessLoadForm.value.team_max_members_num || 2,
      team_mode: businessLoadForm.value.team_mode || "all",
      team_publish_concurrency:
        businessLoadForm.value.team_publish_concurrency || 1,
      team_publish_interval_ms:
        businessLoadForm.value.team_publish_interval_ms ?? 500,
      team_publish_reliable_visible:
        businessLoadForm.value.team_publish_reliable_visible !== false,
      team_visibility_wait_seconds:
        businessLoadForm.value.team_visibility_wait_seconds ?? 10,
      team_keepalive_after_notify:
        businessLoadForm.value.team_keepalive_after_notify !== false,
      resident_user_count: businessLoadForm.value.resident_user_count ?? 0,
      transient_user_count: businessLoadForm.value.transient_user_count ?? 0,
      transient_switch_ratio:
        businessLoadForm.value.transient_switch_ratio ?? 55,
      transient_to_resident_ratio:
        businessLoadForm.value.transient_to_resident_ratio ?? 80,
      transient_stay_min_seconds:
        businessLoadForm.value.transient_stay_min_seconds ?? 3,
      transient_stay_max_seconds:
        businessLoadForm.value.transient_stay_max_seconds ?? 5,
      heartbeat_interval_seconds:
        businessLoadForm.value.heartbeat_interval_seconds ?? 30,
      enter_rate_per_second:
        businessLoadForm.value.enter_rate_per_second ??
        businessLoadForm.value.request_rate_per_second ??
        5,
      leave_rate_per_second: businessLoadForm.value.leave_rate_per_second ?? 6,
      room_failure_cooldown_seconds:
        businessLoadForm.value.room_failure_cooldown_seconds ?? 45,
      cleanup_after_stop: businessLoadForm.value.cleanup_after_stop !== false,
      interval_ms: businessLoadForm.value.interval_ms || 1000,
      login_interval_ms: businessLoadForm.value.login_interval_ms || 100,
      auto_reconnect: businessLoadForm.value.auto_reconnect !== false,
      runner_status:
        businessLoadIsImScenario.value || businessLoadIsTeamScenario.value
          ? "cli_adapter"
          : undefined,
      real_traffic_enabled:
        businessLoadIsImScenario.value || businessLoadIsTeamScenario.value
          ? !!businessLoadForm.value.real_traffic_enabled
          : false,
      runner_path: businessLoadForm.value.runner_path || "",
      runner_timeout_seconds:
        businessLoadForm.value.runner_timeout_seconds || 120,
      dry_run: true,
    },
  };
};

const normalizeTeamKeepaliveDuration = () => {
  let durationSeconds = Number(businessLoadForm.value.duration_seconds || 0);
  if (!businessLoadIsTeamScenario.value) {
    return durationSeconds;
  }
  const teamDurationSeconds =
    Number(businessLoadForm.value.team_duration_minutes || 1) * 60;
  if (teamDurationSeconds > durationSeconds) {
    businessLoadForm.value.duration_seconds = teamDurationSeconds;
    ElMessage.info(
      `组队有效期为 ${businessLoadForm.value.team_duration_minutes} 分钟，已自动将基础持续时间调整为 ${teamDurationSeconds} 秒。`,
    );
    durationSeconds = teamDurationSeconds;
  }
  return durationSeconds;
};

const saveBusinessLoadTask = async () => {
  if (!businessLoadForm.value.name || !businessLoadForm.value.scenario_type) {
    ElMessage.warning("请填写任务名称并选择压测场景");
    return;
  }
  if (
    businessLoadNeedsRoomTarget.value &&
    !selectedBusinessRooms.value.length
  ) {
    ElMessage.warning("请选择目标房间");
    return;
  }
  if (
    businessLoadIsImScenario.value &&
    !businessLoadNeedsRoomTarget.value &&
    !String(businessLoadForm.value.target_id || "").trim()
  ) {
    ElMessage.warning("请填写 IM 目标 ID");
    return;
  }
  if (
    businessLoadIsCommunityActivityScenario.value &&
    businessLoadActivityAccountTotal.value <= 0
  ) {
    ElMessage.warning("固定用户和流动用户至少需要配置 1 个");
    return;
  }
  if (
    businessLoadRequiresRoom.value &&
    businessLoadForm.value.room_selection_mode === "manual" &&
    !selectedBusinessRooms.value.length
  ) {
    ElMessage.warning("请选择目标房间");
    return;
  }
  businessLoadSaving.value = true;
  try {
    const payload = buildBusinessLoadPayload();
    if (businessLoadDialogMode.value === "edit") {
      await axios.patch(
        `/api/data-factory/business-load/tasks/${businessLoadForm.value.id}/`,
        payload,
      );
    } else {
      await axios.post("/api/data-factory/business-load/tasks/", payload);
    }
    ElMessage.success("任务保存成功");
    businessLoadDialogVisible.value = false;
    await fetchBusinessLoadTasks();
  } catch (error) {
    ElMessage.error(getAccountApiError(error, "任务保存失败"));
  } finally {
    businessLoadSaving.value = false;
  }
};

const precheckBusinessLoadTask = async (row) => {
  try {
    const response = await axios.post(
      `/api/data-factory/business-load/tasks/${row.id}/precheck/`,
    );
    ElMessage.success(response.data.message || "预检查完成");
    await fetchBusinessLoadTasks();
  } catch (error) {
    ElMessage.error(getAccountApiError(error, "预检查失败"));
  }
};

const openTeamRoomRepublishDialog = (task, room) => {
  teamRepublishTask.value = task;
  const roomOverride =
    task.config?.team_room_overrides?.[room.channel_id] || {};
  teamRepublishForm.value = {
    channel_id: room.channel_id,
    channel_name: room.channel_name,
    team_message_template:
      room.last_message ||
      room.last_template ||
      roomOverride.team_message_template ||
      task.config?.team_message_template ||
      "QAFlow_team_{{run_id}}_{{account_no}}_{{timestamp}}",
    team_duration_minutes:
      room.current_duration_minutes ||
      roomOverride.team_duration_minutes ||
      task.config?.team_duration_minutes ||
      1,
    team_max_members_num:
      room.current_max_members ||
      roomOverride.team_max_members_num ||
      task.config?.team_max_members_num ||
      2,
    team_mode:
      room.current_team_mode ||
      roomOverride.team_mode ||
      task.config?.team_mode ||
      "all",
    team_keepalive_after_notify:
      roomOverride.team_keepalive_after_notify ??
      task.config?.team_keepalive_after_notify !== false,
    team_published: !!room.team_published,
    im_notification_sent: !!room.im_notification_sent,
    cleaned: !!room.cleaned,
    cancelled: !!room.cancelled,
    last_message: room.last_message || "",
    last_published_at: room.last_published_at || "",
    last_cancelled_at: room.last_cancelled_at || "",
    current_duration_minutes: room.current_duration_minutes || "",
    current_max_members: room.current_max_members || "",
    current_team_mode: room.current_team_mode || "",
  };
  teamRepublishDialogVisible.value = true;
};

const republishTeamRoom = async () => {
  if (!teamRepublishTask.value?.id || !teamRepublishForm.value.channel_id) {
    ElMessage.warning("请选择要重新发布的房间");
    return;
  }
  if (!String(teamRepublishForm.value.team_message_template || "").trim()) {
    ElMessage.warning("请填写组队文案");
    return;
  }

  teamRepublishLoading.value = true;
  try {
    const response = await axios.post(
      `/api/data-factory/business-load/tasks/${teamRepublishTask.value.id}/team-room-republish/`,
      {
        channel_id: teamRepublishForm.value.channel_id,
        team_message_template: teamRepublishForm.value.team_message_template,
        team_duration_minutes: teamRepublishForm.value.team_duration_minutes,
        team_max_members_num: teamRepublishForm.value.team_max_members_num,
        team_mode: teamRepublishForm.value.team_mode,
        team_keepalive_after_notify:
          teamRepublishForm.value.team_keepalive_after_notify !== false,
      },
    );
    const result =
      response.data.metrics?.last_team_room_republish?.last_result || {};
    if (result.passed) {
      ElMessage.success("房间重新发布成功");
    } else {
      ElMessage.warning(result.error || "房间重新发布失败，请展开查看结果");
    }
    teamRepublishDialogVisible.value = false;
    await fetchBusinessLoadTasks();
  } catch (error) {
    ElMessage.error(getAccountApiError(error, "房间重新发布失败"));
    await fetchBusinessLoadTasks();
  } finally {
    teamRepublishLoading.value = false;
  }
};

const cancelTeamRoomRecruit = async (task, room) => {
  if (!task?.id || !room?.channel_id) {
    ElMessage.warning("请选择需要取消招募的房间");
    return;
  }
  try {
    await ElMessageBox.confirm(
      `确认取消房间「${room.channel_name || room.channel_id}」的组队招募？`,
      "取消招募确认",
      { type: "warning" },
    );
  } catch (error) {
    return;
  }

  teamRoomCancelLoading.value = {
    ...teamRoomCancelLoading.value,
    [room.channel_id]: true,
  };
  try {
    const response = await axios.post(
      `/api/data-factory/business-load/tasks/${task.id}/team-room-cancel/`,
      {
        channel_id: room.channel_id,
      },
    );
    const result =
      response.data.metrics?.last_team_room_cancel?.last_cancel_result || {};
    if (result.passed) {
      ElMessage.success("取消招募成功");
      teamRepublishDialogVisible.value = false;
    } else {
      ElMessage.warning(result.error || "取消招募失败，请展开查看结果");
    }
    await fetchBusinessLoadTasks();
  } catch (error) {
    ElMessage.error(getAccountApiError(error, "取消招募失败"));
    await fetchBusinessLoadTasks();
  } finally {
    teamRoomCancelLoading.value = {
      ...teamRoomCancelLoading.value,
      [room.channel_id]: false,
    };
  }
};

const interruptBusinessLoadTask = async (row) => {
  if (!["ready", "running"].includes(row?.status)) {
    ElMessage.info(
      "当前任务已结束，无需中断；如果要处理残留招募，请点击取消招募。",
    );
    return;
  }
  await stopBusinessLoadTask(row);
};

const startBusinessLoadTask = async (row) => {
  try {
    const response = await axios.post(
      `/api/data-factory/business-load/tasks/${row.id}/start/`,
    );
    ElMessage.success(
      response.data.logs?.slice(-1)?.[0]?.message || "任务已启动",
    );
    await fetchBusinessLoadTasks();
  } catch (error) {
    ElMessage.error(getAccountApiError(error, "任务启动失败"));
    await fetchBusinessLoadTasks();
  }
};

const trialRunBusinessLoadTask = async (row) => {
  try {
    const confirmMessage = `确认执行小流量试跑：${row.name}？`;
    await ElMessageBox.confirm(confirmMessage, "小流量试跑确认", {
      type: "warning",
    });
  } catch (error) {
    return;
  }

  businessLoadTrialLoading.value[row.id] = true;
  try {
    const response = await axios.post(
      `/api/data-factory/business-load/tasks/${row.id}/trial-run/`,
      {
        max_accounts: 3,
      },
    );
    const summary = response.data.metrics?.last_trial_run?.summary || {};
    if (row.scenario_type === "im_message_flood") {
      if (response.data.metrics?.last_trial_run?.safety?.real_traffic) {
        ElMessage.success(
          `IM 试跑完成，计划发送 ${summary.planned_message_count || 0} 条消息`,
        );
      } else {
        ElMessage.success(
          `IM 试跑完成，计划发送 ${summary.planned_message_count || 0} 条消息`,
        );
      }
    } else if (row.scenario_type === "team_recruit_publish") {
      const message = `发布组队试跑完成：端上可见 ${summary.team_visible_success || 0}/${summary.team_visible_expected || 0}，发布 ${summary.publish_team_success || 0}，IM通知 ${summary.im_notification_success || 0}，保活 ${summary.team_keepalive_rounds || 0} 轮，失败 ${summary.failed_count || 0}`;
      if (response.data.metrics?.last_trial_run?.passed) {
        ElMessage.success(message);
      } else {
        ElMessage.warning(message);
      }
    } else if (row.scenario_type === "community_activity_simulation") {
      ElMessage.success(
        `社区活跃试跑完成：固定 ${summary.resident_executed || 0}，流动 ${summary.transient_executed || 0}，切房 ${summary.transient_switches || 0}，失败 ${summary.failed_count || 0}`,
      );
    } else {
      ElMessage.success(
        `试跑完成：进房 ${summary.enter_room_success || 0}，失败 ${summary.failed_count || 0}`,
      );
    }
    await fetchBusinessLoadTasks();
  } catch (error) {
    ElMessage.error(getAccountApiError(error, "小流量试跑失败"));
    await fetchBusinessLoadTasks();
  } finally {
    businessLoadTrialLoading.value[row.id] = false;
  }
};

const stopBusinessLoadTask = async (row) => {
  try {
    await axios.post(`/api/data-factory/business-load/tasks/${row.id}/stop/`);
    ElMessage.success("任务已停止");
    await fetchBusinessLoadTasks();
  } catch (error) {
    ElMessage.error(getAccountApiError(error, "停止任务失败"));
  }
};

const deleteBusinessLoadTask = async (row) => {
  try {
    await ElMessageBox.confirm(`确认删除任务 ${row.name}？`, "删除任务", {
      type: "warning",
    });
    await axios.delete(`/api/data-factory/business-load/tasks/${row.id}/`);
    ElMessage.success("任务已删除");
    await fetchBusinessLoadTasks();
  } catch (error) {
    if (error !== "cancel") {
      ElMessage.error(getAccountApiError(error, "删除任务失败"));
    }
  }
};

const handleBusinessLoadSearch = () => {
  businessLoadCurrentPage.value = 1;
  fetchBusinessLoadTasks();
};

const resetBusinessLoadTaskFilters = () => {
  businessLoadFilters.value = {
    scenario_type: businessLoadActiveScenario.value,
    status: "",
    keyword: "",
  };
  businessLoadCurrentPage.value = 1;
  fetchBusinessLoadTasks();
};

const resetBusinessLoadFilters = () => {
  backBusinessLoadScenarioHome();
};

const handleBusinessLoadPageChange = (page) => {
  businessLoadCurrentPage.value = page;
  fetchBusinessLoadTasks();
};

const handleBusinessLoadSizeChange = (size) => {
  businessLoadPageSize.value = size;
  businessLoadCurrentPage.value = 1;
  fetchBusinessLoadTasks();
};

const getBusinessLoadStatusType = (statusValue) => {
  const mapping = {
    draft: "info",
    ready: "primary",
    running: "warning",
    completed: "success",
    failed: "danger",
    stopped: "info",
  };
  return mapping[statusValue] || "";
};

const isBusinessLoadPlanGenerated = (row) => {
  return row?.status === "completed" && row?.metrics?.dry_run !== false;
};

const getBusinessLoadNextStepTitle = (row) => {
  if (row.status === "running") return "任务运行中，请等待执行完成或手动停止。";
  if (row.metrics?.last_trial_run)
    return row.metrics.last_trial_run.passed
      ? "最近试跑通过，可以扩大账号数后正式执行。"
      : "最近试跑失败，请展开查看错误并调整配置。";
  if (row.metrics?.last_precheck) return "预检查已完成，可以执行小流量试跑。";
  return "请先编辑任务，选择账号和房间，然后执行预检查。";
};

const getBusinessLoadStatusText = (row) => {
  if (row?.metrics?.last_trial_run) {
    return row.metrics.last_trial_run.passed ? "试跑通过" : "试跑失败";
  }
  if (isBusinessLoadPlanGenerated(row)) {
    return "计划已生成";
  }
  return row?.status_display || row?.status || "-";
};

const handleAccountSearch = () => {
  accountCurrentPage.value = 1;
  fetchAccountPool();
};

const resetAccountFilters = () => {
  accountFilters.value = {
    environment: "",
    business_domain: "",
    status: "",
    keyword: "",
  };
  accountCurrentPage.value = 1;
  fetchAccountPool();
};

const handleAccountPageChange = (page) => {
  accountCurrentPage.value = page;
  fetchAccountPool();
};

const handleAccountSizeChange = (size) => {
  accountPageSize.value = size;
  accountCurrentPage.value = 1;
  fetchAccountPool();
};

const getAccountStatusType = (statusValue) => {
  const mapping = {
    available: "success",
    in_use: "warning",
    disabled: "info",
    invalid: "danger",
  };
  return mapping[statusValue] || "";
};

watch(showHistory, (newVal) => {
  if (newVal) {
    fetchHistory();
  }
});

watch(historyTab, (newVal) => {
  if (newVal === "stats") {
    fetchStatistics();
  }
});

onMounted(async () => {
  await fetchCategories();
  fetchScenarios();
  fetchStatistics();
});
</script>

<style scoped lang="scss">
.data-factory-container {
  padding: 20px;
  min-height: calc(100vh - 60px);
  background: #f5f7fa;
}

.header-card {
  margin-bottom: 20px;

  .header-content {
    display: flex;
    flex-direction: column;
    gap: 15px;
  }

  .page-title {
    font-size: 28px;
    font-weight: 600;
    color: #2c3e50;
    display: flex;
    align-items: center;
    gap: 10px;
    margin: 0;
    cursor: pointer;
    transition: color 0.3s;

    &:hover {
      color: #409eff;
    }

    .title-icon {
      font-size: 32px;
      color: #409eff;
    }
  }

  .page-subtitle {
    font-size: 16px;
    color: #7f8c8d;
    margin: 0;
  }

  .header-actions {
    display: flex;
    gap: 10px;
    justify-content: flex-end;
  }
}

.category-view {
  display: flex;
  flex-direction: column;
  gap: 20px;

  .category-section {
    .category-card {
      .category-header {
        display: flex;
        align-items: center;
        gap: 10px;

        .category-icon {
          font-size: 24px;
        }

        .category-title {
          flex: 1;
          font-size: 18px;
          font-weight: 600;
        }
      }

      .tools-grid {
        display: grid;
        grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
        gap: 15px;
        margin-top: 15px;
      }

      .tool-item {
        background: #f8f9fa;
        border: 1px solid #e9ecef;
        border-radius: 8px;
        padding: 15px;
        cursor: pointer;
        transition: all 0.3s;
        display: flex;
        align-items: center;
        gap: 12px;

        &:hover {
          background: #fff;
          border-color: #409eff;
          box-shadow: 0 2px 8px rgba(64, 158, 255, 0.1);
          transform: translateY(-2px);
        }

        .tool-icon {
          width: 40px;
          height: 40px;
          background: #e6f7ff;
          border-radius: 8px;
          display: flex;
          align-items: center;
          justify-content: center;
          color: #409eff;
          font-size: 20px;
        }

        .tool-info {
          flex: 1;

          .tool-name {
            font-size: 14px;
            font-weight: 600;
            margin: 0 0 5px 0;
            color: #2c3e50;
          }

          .tool-desc {
            font-size: 12px;
            color: #7f8c8d;
            margin: 0;
            line-height: 1.4;
          }
        }

        .tool-arrow {
          color: #c0c4cc;
          transition: transform 0.3s;
        }

        &:hover .tool-arrow {
          transform: translateX(5px);
          color: #409eff;
        }
      }
    }
  }
}

.scenario-view {
  .scenario-card {
    margin-bottom: 20px;
    cursor: pointer;
    transition: all 0.3s;

    &:hover {
      box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
      transform: translateY(-5px);
    }

    .scenario-content {
      text-align: center;
      padding: 20px;

      .scenario-icon {
        font-size: 48px;
        color: #409eff;
        margin-bottom: 15px;
      }

      .scenario-title {
        font-size: 18px;
        font-weight: 600;
        margin: 0 0 10px 0;
        color: #2c3e50;
      }

      .scenario-desc {
        font-size: 14px;
        color: #7f8c8d;
        margin: 0 0 15px 0;
        line-height: 1.5;
      }

      .scenario-stats {
        display: flex;
        justify-content: center;
      }
    }
  }
}

.account-pool-view,
.business-load-view {
  display: flex;
  flex-direction: column;
  gap: 16px;

  .account-stats {
    .stat-card {
      display: flex;
      flex-direction: column;
      gap: 8px;

      .stat-label {
        color: #7f8c8d;
        font-size: 13px;
      }

      strong {
        color: #2c3e50;
        font-size: 26px;
        line-height: 1;

        &.success {
          color: #67c23a;
        }

        &.warning {
          color: #e6a23c;
        }

        &.danger {
          color: #f56c6c;
        }
      }
    }
  }

  .account-pool-card,
  .business-load-card {
    .account-toolbar {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 16px;

      h3 {
        margin: 0;
        color: #2c3e50;
        font-size: 18px;
      }

      p {
        margin: 6px 0 0;
        color: #7f8c8d;
        font-size: 13px;
      }

      .account-actions {
        display: flex;
        flex-wrap: wrap;
        gap: 8px;
        justify-content: flex-end;
      }
    }

    .account-filters {
      padding: 14px 14px 0;
      margin-bottom: 16px;
      background: #f8fafc;
      border: 1px solid #edf1f7;
      border-radius: 10px;
    }

    .business-scenario-board {
      margin-bottom: 16px;
      padding: 16px;
      border: 1px solid #e5edf7;
      border-radius: 14px;
      background: linear-gradient(135deg, #f8fbff 0%, #f7faf6 100%);
    }

    .business-scenario-detail {
      padding-top: 16px;
    }

    .section-heading {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 12px;
      margin-bottom: 12px;

      h4 {
        margin: 0;
        color: #1f2d3d;
        font-size: 16px;
      }

      p {
        margin: 4px 0 0;
        color: #7f8c8d;
        font-size: 13px;
      }
    }

    .business-scenario-grid {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
      gap: 12px;
    }

    .business-scenario-card {
      min-height: 148px;
      padding: 14px;
      border: 1px solid #e5e7eb;
      border-radius: 12px;
      background: #fff;
      cursor: pointer;
      transition: all 0.2s ease;

      &:hover {
        transform: translateY(-2px);
        border-color: #409eff;
        box-shadow: 0 8px 22px rgba(30, 64, 175, 0.08);
      }

      &.active {
        border-color: #409eff;
        box-shadow: 0 0 0 2px rgba(64, 158, 255, 0.12);
      }

      &.disabled {
        cursor: not-allowed;
        opacity: 0.72;

        &:hover {
          transform: none;
          border-color: #e5e7eb;
          box-shadow: none;
        }
      }

      .scenario-card-top,
      .scenario-card-footer {
        display: flex;
        align-items: center;
        justify-content: space-between;
        gap: 8px;
      }

      .el-icon {
        width: 34px;
        height: 34px;
        border-radius: 10px;
        background: #eef6ff;
        color: #2b7de9;
        font-size: 18px;
      }

      h4 {
        margin: 12px 0 6px;
        color: #1f2937;
        font-size: 15px;
      }

      p {
        min-height: 40px;
        margin: 0 0 12px;
        color: #64748b;
        font-size: 13px;
        line-height: 1.55;
      }

      .scenario-card-footer span {
        color: #94a3b8;
        font-size: 12px;
      }
    }

    .task-brief {
      display: flex;
      flex-direction: column;
      gap: 4px;

      strong {
        color: #1f2937;
        font-weight: 600;
      }

      span {
        color: #64748b;
        font-size: 12px;
      }
    }

    .muted {
      color: #a8abb2;
      font-size: 12px;
    }

    .capability-tag {
      margin: 2px 4px 2px 0;
    }
  }
}

.business-detail-drawer {
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.detail-hero {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 18px;
  padding: 18px;
  border-radius: 14px;
  background: linear-gradient(135deg, #f8fbff 0%, #f7faf6 100%);
  border: 1px solid #e5edf7;

  h3 {
    margin: 8px 0 6px;
    color: #1f2937;
  }

  p {
    margin: 0;
    color: #64748b;
  }
}

.detail-actions {
  display: flex;
  flex-wrap: wrap;
  justify-content: flex-end;
  gap: 8px;
}

.detail-descriptions {
  margin-top: 4px;
}

.detail-tabs {
  margin-top: 4px;
}

.advanced-config-collapse {
  margin-top: 12px;
  border: 1px solid #edf1f7;
  border-radius: 10px;
  overflow: hidden;

  :deep(.el-collapse-item__header) {
    padding: 0 14px;
    background: #f8fafc;
    font-weight: 600;
  }

  :deep(.el-collapse-item__content) {
    padding: 16px 14px 4px;
  }
}

.capability-chain-preview {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.option-extra {
  float: right;
  color: #909399;
  font-size: 12px;
}

.room-picker {
  width: 100%;
}

.room-picker-toolbar {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 12px;
  margin-bottom: 10px;
}

.room-order-search {
  width: 220px;
}

.business-plan-expand {
  padding: 12px 18px;
  background: #f8fafc;
}

.plan-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 14px;
  margin-bottom: 10px;
  color: #606266;
  font-size: 13px;
}

.trial-result-panel {
  margin-top: 14px;
  padding: 14px;
  border: 1px solid #dbeafe;
  border-radius: 10px;
  background: #f8fbff;
}

.team-room-panel {
  margin-top: 14px;
  padding: 14px;
  border: 1px solid #bfdbfe;
  border-radius: 12px;
  background: linear-gradient(180deg, #f8fbff 0%, #eff6ff 100%);
}

.team-room-panel :deep(.el-table__body tr) {
  background: #e8f4ff;
}

.team-room-panel :deep(.el-table__body tr:hover > td) {
  background: #dbeeff;
}

.readonly-room {
  display: flex;
  flex-direction: column;
  gap: 4px;
  color: #1f2937;
}

.readonly-room span {
  color: #64748b;
  font-size: 13px;
}

.team-number-input {
  width: 160px;
}

.trial-section-title {
  margin-bottom: 10px;
  font-weight: 700;
  color: #1f2d3d;
}

.trial-summary {
  margin-bottom: 12px;
}

.trial-stat {
  display: flex;
  flex-direction: column;
  gap: 6px;
  padding: 12px;
  border-radius: 8px;
  background: #ffffff;
  border: 1px solid #e5e7eb;
}

.trial-stat span {
  color: #6b7280;
  font-size: 12px;
}

.trial-stat strong {
  color: #111827;
  font-size: 22px;
}

.trial-stat.success strong {
  color: #16a34a;
}

.trial-stat.danger strong {
  color: #dc2626;
}

.trial-table {
  margin-top: 10px;
}

.performance-panel {
  margin-top: 12px;
  padding: 12px;
  border-radius: 8px;
  background: #ffffff;
}

.performance-metrics {
  display: flex;
  flex-wrap: wrap;
  gap: 10px 16px;
  color: #475569;
  font-size: 13px;
}

.performance-analysis {
  margin: 8px 0 0;
  padding-left: 18px;
  color: #334155;
  line-height: 1.7;
}

.tool-execution {
  max-height: calc(100vh - 200px);
  overflow-y: auto;
  padding-right: 10px;

  .tool-alert {
    margin-bottom: 20px;
  }

  .tool-form {
    margin-bottom: 20px;
    padding: 15px;
    background: #f8f9fa;
    border-radius: 8px;

    .form-tip {
      margin-left: 10px;
      font-size: 12px;
      color: #909399;
    }
  }

  .tool-options {
    margin-bottom: 20px;

    .form-tip {
      margin-left: 10px;
      font-size: 12px;
      color: #909399;
    }
  }

  .tool-result {
    background: #f8f9fa;
    border: 1px solid #e9ecef;
    border-radius: 8px;
    padding: 15px;

    h4 {
      margin: 0 0 10px 0;
      font-size: 14px;
      font-weight: 600;
      color: #2c3e50;
    }

    pre {
      margin: 0;
      padding: 10px;
      background: #fff;
      border-radius: 4px;
      overflow-x: auto;
      max-height: 400px;
      overflow-y: auto;
    }

    .image-result {
      display: flex;
      flex-direction: column;
      gap: 15px;

      .image-preview {
        display: flex;
        justify-content: center;
        align-items: center;
        padding: 20px;
        background: #fff;
        border-radius: 8px;
        border: 2px dashed #dcdfe6;
        min-height: 200px;

        img {
          max-width: 100%;
          max-height: 400px;
          border-radius: 4px;
          box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
        }

        .no-image {
          color: #909399;
          font-size: 14px;
        }
      }

      .image-actions {
        display: flex;
        justify-content: center;
        align-items: center;
        gap: 15px;
        padding: 10px;
        background: #fff;
        border-radius: 8px;
      }
    }
  }
}

.history-table {
  :deep(.el-table) {
    .el-table__cell {
      text-align: center;
    }

    .el-table__header-wrapper {
      .el-table__header {
        th {
          text-align: center;
          background-color: #f5f7fa;
        }
      }
    }
  }
}

.history-content {
  max-height: calc(100vh - 300px);
  display: flex;
  flex-direction: column;

  .history-table {
    flex: 1;
    overflow-y: auto;

    :deep(.el-table) {
      overflow: visible;
    }
  }

  .history-pagination {
    margin-top: 20px;
    display: flex;
    justify-content: center;
    padding: 10px 0;
    flex-shrink: 0;
  }
}

.stats-container {
  .total-stats-card {
    background: linear-gradient(135deg, #1e3a8a 0%, #3b82f6 100%);
    border: none;

    :deep(.el-card__body) {
      padding: 30px;
    }

    .total-stats {
      display: flex;
      justify-content: center;
      align-items: center;

      .total-stat-item {
        text-align: center;
        color: white;

        .total-stat-value {
          font-size: 48px;
          font-weight: 700;
          margin-bottom: 10px;
          text-shadow: 0 2px 4px rgba(0, 0, 0, 0.2);
        }

        .total-stat-label {
          font-size: 18px;
          opacity: 0.9;
        }
      }
    }
  }

  .card-header-title {
    font-size: 16px;
    font-weight: 600;
    color: #2c3e50;
  }

  .stat-item {
    margin-bottom: 20px;

    &:last-child {
      margin-bottom: 0;
    }

    .stat-item-content {
      display: flex;
      align-items: center;
      gap: 15px;

      .stat-label {
        width: 100px;
        font-size: 14px;
        color: #2c3e50;
        font-weight: 500;
        flex-shrink: 0;
      }

      .stat-count {
        width: 50px;
        text-align: right;
        font-size: 14px;
        color: #409eff;
        font-weight: 600;
        flex-shrink: 0;
      }
    }
  }
}

.json-path-tool {
  .path-input-panel {
    margin-bottom: 15px;

    h4 {
      margin: 0 0 10px 0;
      font-size: 14px;
      font-weight: 600;
      color: #2c3e50;
    }
  }

  .json-input-panel {
    h4 {
      margin: 0 0 10px 0;
      font-size: 14px;
      font-weight: 600;
      color: #2c3e50;
    }
  }
}

.json-format-tool {
  .json-input-panel {
    height: 100%;
    display: flex;
    flex-direction: column;
    min-width: 0;

    .panel-header {
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-bottom: 10px;
      padding: 10px;
      background: #f5f7fa;
      border-radius: 6px;

      h4 {
        margin: 0;
        font-size: 14px;
        font-weight: 600;
        color: #2c3e50;
      }

      .input-stats,
      .output-stats {
        display: flex;
        gap: 15px;
        font-size: 12px;
        color: #606266;

        span {
          padding: 2px 8px;
          background: #fff;
          border-radius: 4px;
          border: 1px solid #dcdfe6;
        }
      }
    }

    .result-display {
      flex: 1;
      overflow: auto;
      overflow-x: auto;
      padding: 10px;
      background: #f5f7fa;
      border-radius: 6px;
      border: 1px solid #dcdfe6;
      display: flex;
      flex-direction: column;
      min-width: 0;

      pre {
        margin: 0;
        font-family: "Courier New", monospace;
        font-size: 13px;
        line-height: 1.5;
        color: #2c3e50;
        white-space: pre;
        word-wrap: normal;
        min-width: fit-content;
        overflow-x: auto;
      }
    }

    .result-empty {
      flex: 1;
      display: flex;
      align-items: center;
      justify-content: center;
      min-height: 200px;
      background: #f5f7fa;
      border-radius: 6px;
      border: 1px solid #dcdfe6;
    }
  }

  .json-tree-view {
    display: flex;
    flex-direction: column;
    min-width: 0;

    .json-tree-actions {
      display: flex;
      gap: 10px;
      margin-bottom: 10px;
      padding-bottom: 10px;
      border-bottom: 1px solid #e9ecef;
    }

    .json-tree {
      flex: 1;
      overflow: auto;
      overflow-x: auto;
      background: #fff;
      border-radius: 4px;
      padding: 10px;
      max-height: 280px;
      min-width: fit-content;

      :deep(.el-tree-node) {
        min-width: fit-content;
      }

      :deep(.el-tree-node__content) {
        padding: 4px 0;
        height: auto;
        min-width: fit-content;
      }

      :deep(.el-tree-node__label) {
        font-family: "Courier New", monospace;
        font-size: 13px;
        white-space: nowrap;
      }
    }

    .json-tree-node {
      display: inline-flex;
      align-items: center;
      gap: 8px;

      .json-node-label {
        white-space: nowrap;
      }

      &.json-type-object {
        color: #e91e63;
      }

      &.json-type-array {
        color: #9c27b0;
      }

      &.json-type-string {
        color: #4caf50;
      }

      &.json-type-number {
        color: #2196f3;
      }

      &.json-type-boolean {
        color: #ff9800;
      }

      &.json-type-null {
        color: #9e9e9e;
      }
    }
  }

  .format-options {
    margin-top: 15px;
    padding: 15px;
    background: #f0f2f5;
    border-radius: 8px;

    .options-bar {
      display: flex;
      align-items: center;
      gap: 30px;
      flex-wrap: wrap;

      .option-group {
        display: flex;
        align-items: center;
        gap: 8px;

        .option-label {
          font-size: 14px;
          color: #606266;
          font-weight: 500;
        }
      }
    }
  }
}

.json-diff-tool {
  .json-input-panel {
    margin-bottom: 15px;

    h4 {
      margin: 0 0 10px 0;
      font-size: 14px;
      font-weight: 600;
      color: #2c3e50;
    }
  }

  .diff-options {
    margin-top: 15px;
    padding: 15px;
    background: #f0f2f5;
    border-radius: 8px;
  }
}

.image-upload {
  width: 100%;

  :deep(.el-upload) {
    width: 100%;
  }

  :deep(.el-upload-dragger) {
    width: 100%;
    height: 200px;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    border: 2px dashed #d9d9d9;
    border-radius: 8px;
    background: #fafafa;
    transition: all 0.3s;

    &:hover {
      border-color: #409eff;
      background: #f0f9ff;
    }
  }

  .el-upload__tip {
    margin-top: 10px;
    color: #909399;
    font-size: 12px;
  }
}

.qr-code-upload {
  width: 100%;

  :deep(.el-upload) {
    width: 100%;
  }

  :deep(.el-upload-dragger) {
    width: 100%;
    height: 200px;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    border: 2px dashed #d9d9d9;
    border-radius: 8px;
    background: #fafafa;
    transition: all 0.3s;

    &:hover {
      border-color: #409eff;
      background: #f0f9ff;
    }
  }

  .upload-placeholder {
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    gap: 12px;

    .upload-icon {
      font-size: 48px;
      color: #c0c4cc;
    }

    .upload-text {
      font-size: 14px;
      color: #606266;
      font-weight: 500;
    }

    .upload-tip {
      font-size: 12px;
      color: #909399;
    }
  }

  .upload-preview {
    width: 100%;
    height: 100%;
    display: flex;
    align-items: center;
    justify-content: center;
    position: relative;

    img {
      max-width: 100%;
      max-height: 100%;
      object-fit: contain;
    }

    .upload-mask {
      position: absolute;
      top: 0;
      left: 0;
      width: 100%;
      height: 100%;
      background: rgba(0, 0, 0, 0.5);
      display: flex;
      flex-direction: column;
      align-items: center;
      justify-content: center;
      gap: 8px;
      color: #fff;
      opacity: 0;
      transition: opacity 0.3s;
      cursor: pointer;

      &:hover {
        opacity: 1;
      }

      .el-icon {
        font-size: 24px;
      }

      span {
        font-size: 14px;
      }
    }
  }
}

.image-preview {
  width: 100%;
  max-width: 400px;
  border: 1px solid #dcdfe6;
  border-radius: 8px;
  overflow: hidden;
  margin-top: 10px;

  img {
    width: 100%;
    height: auto;
    display: block;
  }
}

.json-path-tool {
  .path-input-panel {
    margin-bottom: 15px;

    h4 {
      margin: 0 0 10px 0;
      font-size: 14px;
      font-weight: 600;
      color: #2c3e50;
    }
  }

  .json-input-panel {
    margin-bottom: 15px;

    h4 {
      margin: 0 0 10px 0;
      font-size: 14px;
      font-weight: 600;
      color: #2c3e50;
    }
  }

  .result-display {
    height: 100%;
    min-height: 300px;
    background: #f8f9fa;
    border: 1px solid #e9ecef;
    border-radius: 8px;
    padding: 15px;
    overflow: auto;
    overflow-x: auto;
    display: flex;
    flex-direction: column;
    min-width: 0;

    pre {
      margin: 0;
      padding: 10px;
      background: #fff;
      border-radius: 4px;
      max-height: 280px;
      font-size: 13px;
      line-height: 1.4;
      white-space: pre;
      word-wrap: normal;
      min-width: fit-content;
      overflow-x: auto;
    }
  }

  .result-empty {
    height: 100%;
    min-height: 300px;
    display: flex;
    align-items: center;
    justify-content: center;
  }

  .json-tree-view {
    display: flex;
    flex-direction: column;
    min-width: 0;

    .json-tree-actions {
      display: flex;
      gap: 10px;
      margin-bottom: 10px;
      padding-bottom: 10px;
      border-bottom: 1px solid #e9ecef;
    }

    .json-tree {
      flex: 1;
      overflow: auto;
      overflow-x: auto;
      background: #fff;
      border-radius: 4px;
      padding: 10px;
      max-height: 280px;
      min-width: fit-content;

      :deep(.el-tree-node) {
        min-width: fit-content;
      }

      :deep(.el-tree-node__content) {
        padding: 4px 0;
        height: auto;
        min-width: fit-content;
      }

      :deep(.el-tree-node__label) {
        font-family: "Courier New", monospace;
        font-size: 13px;
        white-space: nowrap;
      }
    }

    .json-tree-node {
      display: inline-flex;
      align-items: center;
      gap: 8px;

      .json-node-label {
        white-space: nowrap;
      }

      &.json-type-object {
        color: #e91e63;
      }

      &.json-type-array {
        color: #9c27b0;
      }

      &.json-type-string {
        color: #4caf50;
      }

      &.json-type-number {
        color: #2196f3;
      }

      &.json-type-boolean {
        color: #ff9800;
      }

      &.json-type-null {
        color: #9e9e9e;
      }
    }
  }
}
</style>
