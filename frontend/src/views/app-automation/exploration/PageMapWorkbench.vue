<template>
  <div class="page-map-workbench">
    <section class="page-hero">
      <div>
        <p class="eyebrow">Exploration Asset Graph</p>
        <h2>页面地图</h2>
        <p>
          查看 AI 探索沉淀的页面、控件快照和跳转关系，为后续语义库维护和 AI
          巡检规划提供依据。
        </p>
      </div>
      <el-space wrap>
        <el-button @click="loadAll">刷新</el-button>
        <el-button
          type="primary"
          @click="$router.push('/app-automation/exploration')"
          >返回 AI 探索</el-button
        >
      </el-space>
    </section>

    <el-card shadow="never" class="filter-card">
      <el-form :inline="true" :model="query" class="filter-form">
        <el-form-item label="项目">
          <el-select
            v-model="query.project"
            clearable
            filterable
            placeholder="全部项目"
            style="width: 220px"
            @change="loadAll"
          >
            <el-option
              v-for="project in projects"
              :key="project.id"
              :label="project.name"
              :value="project.id"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="应用">
          <el-select
            v-model="query.app_package"
            clearable
            filterable
            placeholder="全部应用"
            style="width: 220px"
            @change="loadAll"
          >
            <el-option
              v-for="item in packages"
              :key="item.id"
              :label="item.name || item.package_name"
              :value="item.id"
            >
              <span>{{ item.name || item.package_name }}</span>
              <span class="option-meta">{{ item.package_name }}</span>
            </el-option>
          </el-select>
        </el-form-item>
        <el-form-item label="搜索">
          <el-input
            v-model="query.search"
            clearable
            placeholder="页面 / Activity / 控件 / resource-id"
            style="width: 300px"
            @keyup.enter="loadAll"
            @clear="loadAll"
          />
        </el-form-item>
        <el-form-item>
          <el-button type="primary" :loading="loading" @click="loadAll"
            >查询</el-button
          >
        </el-form-item>
      </el-form>
    </el-card>

    <div class="summary-grid">
      <el-card
        v-for="item in summaryCards"
        :key="item.label"
        shadow="never"
        class="summary-card"
      >
        <span>{{ item.label }}</span>
        <strong>{{ item.value }}</strong>
        <em>{{ item.desc }}</em>
      </el-card>
    </div>

    <el-card shadow="never" class="workflow-card">
      <template #header>
        <div class="section-title">
          <span>这个页面怎么用</span>
          <el-tag :type="pageMapWorkflow.tagType" effect="plain">{{
            pageMapWorkflow.badge
          }}</el-tag>
        </div>
      </template>
      <div class="workflow-main">
        <div class="workflow-copy">
          <strong>{{ pageMapWorkflow.title }}</strong>
          <p>{{ pageMapWorkflow.description }}</p>
        </div>
        <div class="workflow-actions">
          <el-button
            v-for="action in pageMapWorkflow.actions"
            :key="action.key"
            :type="action.type || 'primary'"
            :plain="action.plain !== false"
            size="small"
            :disabled="action.disabled"
            @click="handleWorkflowAction(action.key)"
          >
            {{ action.label }}
          </el-button>
        </div>
      </div>
      <div class="workflow-steps">
        <div
          v-for="(step, index) in pageMapWorkflow.steps"
          :key="step.title"
          class="workflow-step"
          :class="{ active: step.active }"
        >
          <span>{{ index + 1 }}</span>
          <div>
            <strong>{{ step.title }}</strong>
            <p>{{ step.desc }}</p>
          </div>
        </div>
      </div>
    </el-card>

    <el-card shadow="never" class="content-card">
      <template #header>
        <div class="section-title">
          <span>页面节点</span>
          <el-tag effect="plain">按最近更新排序</el-tag>
          <el-button
            size="small"
            type="warning"
            plain
            :disabled="!canMergePages"
            :loading="mergingPages"
            @click="mergeSelectedPages"
          >
            合并到当前页面（{{ selectedPageIds.length }}）
          </el-button>
        </div>
      </template>
      <el-table
        v-loading="loading"
        :data="pageNodes"
        border
        row-key="id"
        @row-click="selectPage"
        @selection-change="handlePageSelection"
      >
        <el-table-column type="selection" width="44" />
        <el-table-column label="页面" min-width="220" show-overflow-tooltip>
          <template #default="{ row }">
            <div class="page-title-line">
              <span class="page-title">{{ displayPageName(row) }}</span>
              <el-tag size="small" effect="plain" :type="pageStatusType(row)">
                {{ pageStatusLabel(row) }}
              </el-tag>
            </div>
            <div class="muted">
              {{ row.activity || row.app_identifier || "-" }}
            </div>
          </template>
        </el-table-column>
        <el-table-column label="控件" width="110">
          <template #default="{ row }">{{ row.element_count || 0 }}</template>
        </el-table-column>
        <el-table-column label="可点击" width="110">
          <template #default="{ row }">{{ row.clickable_count || 0 }}</template>
        </el-table-column>
        <el-table-column label="跳转" width="110">
          <template #default="{ row }">{{ row.outgoing_count || 0 }}</template>
        </el-table-column>
        <el-table-column label="访问次数" width="110">
          <template #default="{ row }">{{ row.visit_count || 0 }}</template>
        </el-table-column>
        <el-table-column label="页面签名" min-width="180" show-overflow-tooltip>
          <template #default="{ row }">{{ row.page_signature }}</template>
        </el-table-column>
        <el-table-column label="操作" width="110" fixed="right">
          <template #default="{ row }">
            <el-button
              size="small"
              text
              type="primary"
              @click.stop="openRenamePage(row)"
            >
              {{ row.business_name ? "重命名" : "命名" }}
            </el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <div class="detail-grid">
      <el-card shadow="never" class="content-card">
        <template #header>
          <div class="section-title">
            <span>控件候选</span>
            <el-tag v-if="selectedPage" type="success" effect="plain">{{
              selectedPage.business_name || "当前页面待命名"
            }}</el-tag>
          </div>
        </template>
        <div v-if="selectedPage" class="page-governance-panel">
          <div>
            <strong>整页命名</strong>
            <span
              >页面名称只需确认一次，批量入库时会自动继承，避免每个控件重复填写。</span
            >
          </div>
          <div class="page-governance-actions">
            <el-input
              v-model="pageNameDraft"
              placeholder="例如：社区首页、社区详情页"
              clearable
              style="width: 260px"
            />
            <el-button
              type="primary"
              plain
              :loading="savingPageName"
              @click="savePageName"
              >保存页面名</el-button
            >
            <el-button
              type="success"
              plain
              :loading="loadingInspectionDraft"
              @click="openInspectionDraft"
            >
              生成巡检目标
            </el-button>
            <el-button
              type="warning"
              plain
              :loading="loadingDuplicateCandidates"
              @click="openDuplicateCandidates"
            >
              推荐重复页
            </el-button>
          </div>
        </div>
        <div class="candidate-toolbar">
          <el-checkbox
            v-model="candidateQuery.clickable"
            @change="loadCandidates"
            >只看可点击</el-checkbox
          >
          <el-select
            v-model="candidateQuery.role"
            clearable
            placeholder="控件角色"
            style="width: 150px"
            @change="loadCandidates"
          >
            <el-option label="按钮" value="button" />
            <el-option label="输入框" value="input" />
            <el-option label="开关" value="switch" />
            <el-option label="图片" value="image" />
            <el-option label="文本" value="text" />
            <el-option label="可点击容器" value="clickable" />
          </el-select>
          <el-select
            v-model="candidateQuery.level"
            clearable
            placeholder="推荐等级"
            style="width: 150px"
            @change="handleCandidateLevelChange"
          >
            <el-option label="建议入库" value="recommended" />
            <el-option label="需确认" value="review" />
            <el-option label="不建议" value="not_recommended" />
            <el-option label="已入库" value="promoted" />
            <el-option label="已忽略" value="ignored" />
          </el-select>
          <el-checkbox
            v-model="candidateQuery.includeIgnored"
            @change="loadCandidates"
            >显示已忽略</el-checkbox
          >
          <el-button text type="primary" @click="clearSelectedPage"
            >查看全部候选</el-button
          >
          <el-button
            type="success"
            :disabled="!selectedCandidateIds.length"
            :loading="bulkPromoting"
            @click="bulkPromoteCandidates"
          >
            批量加入语义库（{{ selectedCandidateIds.length }}）
          </el-button>
          <el-button
            type="info"
            plain
            :disabled="!selectedCandidateIds.length"
            :loading="governingCandidates"
            @click="ignoreSelectedCandidates"
          >
            标记无需维护
          </el-button>
        </div>
        <div v-if="selectedCandidate" class="candidate-preview">
          <div class="candidate-preview-shot" :style="candidatePreviewStyle">
            <el-image
              v-if="selectedCandidate.page_screenshot_url"
              :src="selectedCandidate.page_screenshot_url"
              fit="fill"
              class="candidate-shot"
            />
            <div v-else class="candidate-shot placeholder">暂无截图</div>
            <div
              class="candidate-overlay"
              :style="candidateOverlayStyle(selectedCandidate)"
            >
              <span>{{ displayCandidateName(selectedCandidate) }}</span>
            </div>
          </div>
          <div class="candidate-preview-info">
            <strong>{{ displayCandidateName(selectedCandidate) }}</strong>
            <span>{{
              selectedCandidate.page_business_name ||
              selectedCandidate.page_activity ||
              "-"
            }}</span>
            <span>建议：{{ selectedCandidate.candidate_action || "-" }}</span>
            <span>bounds：{{ selectedCandidate.bounds || "-" }}</span>
            <span>resource-id：{{ selectedCandidate.resource_id || "-" }}</span>
          </div>
        </div>
        <el-table
          v-loading="candidateLoading"
          :data="visibleCandidates"
          border
          height="420"
          row-key="id"
          :row-class-name="candidateRowClassName"
          @row-click="selectCandidate"
          @selection-change="handleCandidateSelection"
        >
          <template #empty>
            <div class="candidate-empty">
              <strong>当前筛选下没有可展示控件</strong>
              <span>{{ candidateEmptyTip }}</span>
              <div class="candidate-empty-actions">
                <el-button
                  size="small"
                  type="primary"
                  plain
                  @click="relaxCandidateFilters"
                  >放宽筛选</el-button
                >
                <el-button
                  size="small"
                  text
                  type="primary"
                  @click="clearSelectedPage"
                  >查看全部候选</el-button
                >
                <el-button
                  v-if="selectedPage"
                  size="small"
                  text
                  type="warning"
                  :loading="loadingDuplicateCandidates"
                  @click="openDuplicateCandidates"
                >
                  检查重复页
                </el-button>
              </div>
            </div>
          </template>
          <el-table-column
            type="selection"
            width="44"
            :selectable="isCandidateSelectable"
          />
          <el-table-column
            label="候选控件"
            min-width="260"
            show-overflow-tooltip
          >
            <template #default="{ row }">
              <div class="candidate-name-line">
                <span class="page-title">{{ displayCandidateName(row) }}</span>
                <el-tag
                  size="small"
                  effect="plain"
                  :type="candidateLevelType(row.candidate_level)"
                >
                  {{ row.candidate_level_label || "需确认" }}
                </el-tag>
                <el-tag
                  v-if="isIgnoredCandidate(row)"
                  size="small"
                  type="info"
                  effect="dark"
                  >无需维护</el-tag
                >
              </div>
              <div class="muted">
                {{ row.page_business_name || row.page_activity || "-" }}
              </div>
            </template>
          </el-table-column>
          <el-table-column label="角色" width="90">
            <template #default="{ row }">
              <el-tag size="small" effect="plain">{{
                roleLabel(row.role)
              }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column label="推荐度" width="110">
            <template #default="{ row }">
              <el-progress
                :percentage="Number(row.candidate_score || 0)"
                :stroke-width="8"
                :show-text="false"
                :status="candidateProgressStatus(row.candidate_level)"
              />
              <span class="score-text">{{ row.candidate_score || 0 }}</span>
            </template>
          </el-table-column>
          <el-table-column label="原因" min-width="180" show-overflow-tooltip>
            <template #default="{ row }">{{ row.candidate_reason }}</template>
          </el-table-column>
          <el-table-column
            label="resource-id"
            min-width="220"
            show-overflow-tooltip
          >
            <template #default="{ row }">{{ row.resource_id || "-" }}</template>
          </el-table-column>
          <el-table-column label="操作" width="130" fixed="right">
            <template #default="{ row }">
              <el-button
                v-if="isIgnoredCandidate(row)"
                size="small"
                type="primary"
                plain
                :loading="governingCandidates"
                @click.stop="restoreCandidate(row)"
              >
                恢复
              </el-button>
              <el-tooltip
                v-else
                :content="promoteButtonTip(row)"
                placement="top"
                :disabled="!promoteButtonTip(row)"
              >
                <span>
                  <el-button
                    size="small"
                    :type="
                      row.candidate_level === 'not_recommended'
                        ? 'info'
                        : 'success'
                    "
                    plain
                    :disabled="!isCandidateSelectable(row)"
                    @click.stop="promoteCandidate(row)"
                  >
                    {{ promoteButtonText(row) }}
                  </el-button>
                </span>
              </el-tooltip>
            </template>
          </el-table-column>
        </el-table>
      </el-card>

      <el-card shadow="never" class="content-card">
        <template #header>
          <div class="section-title">
            <span>跳转关系</span>
            <el-tag effect="plain">{{ transitions.length }} 条</el-tag>
          </div>
        </template>
        <el-table
          v-loading="transitionLoading"
          :data="transitions"
          border
          height="486"
        >
          <el-table-column
            label="来源页面"
            min-width="160"
            show-overflow-tooltip
          >
            <template #default="{ row }">
              <div class="transition-page-cell">
                <span>{{ displayTransitionPage(row, "from") }}</span>
                <el-button
                  v-if="row.from_page"
                  size="small"
                  text
                  type="primary"
                  @click.stop="openRenameTransitionPage(row, 'from')"
                >
                  {{ row.from_page_business_name ? "重命名" : "命名" }}
                </el-button>
              </div>
            </template>
          </el-table-column>
          <el-table-column
            label="触发控件"
            min-width="160"
            show-overflow-tooltip
          >
            <template #default="{ row }">{{
              row.trigger_text ||
              shortResource(row.trigger_resource_id) ||
              row.action_type
            }}</template>
          </el-table-column>
          <el-table-column
            label="目标页面"
            min-width="160"
            show-overflow-tooltip
          >
            <template #default="{ row }">
              <div class="transition-page-cell">
                <span>{{ displayTransitionPage(row, "to") }}</span>
                <el-button
                  v-if="row.to_page"
                  size="small"
                  text
                  type="primary"
                  @click.stop="openRenameTransitionPage(row, 'to')"
                >
                  {{ row.to_page_business_name ? "重命名" : "命名" }}
                </el-button>
              </div>
            </template>
          </el-table-column>
          <el-table-column label="可信度" width="100">
            <template #default="{ row }"
              >{{ Math.round(Number(row.confidence || 0) * 100) }}%</template
            >
          </el-table-column>
          <el-table-column label="成功/失败" width="110">
            <template #default="{ row }"
              >{{ row.success_count || 0 }}/{{
                row.failure_count || 0
              }}</template
            >
          </el-table-column>
        </el-table>
      </el-card>
    </div>

    <el-dialog
      v-model="promoteDialog.visible"
      title="加入语义库"
      width="860px"
      destroy-on-close
      class="promote-dialog"
    >
      <div v-if="promoteDialog.row" class="promote-layout">
        <div class="promote-shot" :style="promotePreviewStyle">
          <el-image
            v-if="promoteDialog.row.page_screenshot_url"
            :src="promoteDialog.row.page_screenshot_url"
            fit="fill"
            class="candidate-shot"
          />
          <div v-else class="candidate-shot placeholder">暂无截图</div>
          <div
            class="candidate-overlay"
            :style="candidateOverlayStyle(promoteDialog.row)"
          >
            <span>{{ displayCandidateName(promoteDialog.row) }}</span>
          </div>
        </div>

        <el-form
          ref="promoteFormRef"
          :model="promoteForm"
          :rules="promoteRules"
          label-width="96px"
          class="promote-form"
        >
          <el-alert
            v-if="promoteDialog.row.candidate_level === 'not_recommended'"
            type="warning"
            show-icon
            :closable="false"
            title="该候选置信度较低，请结合截图确认后再入库。"
          />
          <el-form-item label="业务对象" prop="semantic_object">
            <el-autocomplete
              v-model="promoteForm.semantic_object"
              :fetch-suggestions="querySemanticObjectSuggestions"
              clearable
              placeholder="从字典选择，如：退出登录 / 社区名称 / 通知入口"
              style="width: 100%"
            />
          </el-form-item>
          <el-form-item label="页面名称" prop="semantic_page">
            <el-select
              v-model="promoteForm.semantic_page"
              filterable
              allow-create
              clearable
              default-first-option
              placeholder="选择或输入页面名，不再自动采用截图标题"
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
          <el-form-item label="元素角色" prop="semantic_role">
            <el-select
              v-model="promoteForm.semantic_role"
              filterable
              allow-create
              clearable
              default-first-option
              placeholder="按钮 / Tab / 页面入口 / 输入框 / 开关"
              style="width: 100%"
            >
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
              v-model="promoteForm.manual_note"
              type="textarea"
              :rows="4"
              placeholder="可写业务解释、前置条件、为什么这样框选、是否容器承载点击等"
            />
          </el-form-item>
          <el-form-item label="名称预览">
            <el-input
              :model-value="
                promoteNamePreview || '请先填写页面名称、业务对象、元素角色'
              "
              disabled
            />
          </el-form-item>
          <el-form-item label="定位详情">
            <div class="locator-summary">
              <span
                >resource-id：{{ promoteDialog.row.resource_id || "-" }}</span
              >
              <span>bounds：{{ promoteDialog.row.bounds || "-" }}</span>
              <span
                >Activity：{{ promoteDialog.row.page_activity || "-" }}</span
              >
            </div>
          </el-form-item>
        </el-form>
      </div>
      <template #footer>
        <el-button @click="promoteDialog.visible = false">取消</el-button>
        <el-button
          type="primary"
          :loading="promoteDialog.submitting"
          @click="submitPromoteCandidate"
        >
          加入语义库
        </el-button>
      </template>
    </el-dialog>

    <el-dialog
      v-model="duplicateDialog.visible"
      title="疑似重复页面"
      width="920px"
      destroy-on-close
    >
      <div class="duplicate-dialog">
        <el-alert
          type="info"
          show-icon
          :closable="false"
          title="系统只做推荐，不会自动合并。建议结合页面名称、Activity、控件重叠原因确认后再合并。"
        />
        <el-table
          v-loading="loadingDuplicateCandidates"
          :data="duplicateCandidates"
          border
          height="420"
          row-key="id"
          empty-text="暂无疑似重复页面"
          @selection-change="handleDuplicateSelection"
        >
          <el-table-column type="selection" width="44" />
          <el-table-column label="页面" min-width="220" show-overflow-tooltip>
            <template #default="{ row }">
              <div class="page-title-line">
                <span class="page-title">{{ displayPageName(row) }}</span>
                <el-tag
                  size="small"
                  effect="plain"
                  :type="duplicateScoreType(row.duplicate_score)"
                >
                  {{ row.duplicate_score }} 分
                </el-tag>
              </div>
              <div class="muted">{{ row.activity || "-" }}</div>
            </template>
          </el-table-column>
          <el-table-column label="控件" width="90">
            <template #default="{ row }">{{ row.element_count || 0 }}</template>
          </el-table-column>
          <el-table-column label="访问" width="90">
            <template #default="{ row }">{{ row.visit_count || 0 }}</template>
          </el-table-column>
          <el-table-column label="重叠" width="110">
            <template #default="{ row }"
              >{{ row.shared_element_count || 0 }}/{{
                row.candidate_element_count || 0
              }}</template
            >
          </el-table-column>
          <el-table-column
            label="推荐依据"
            min-width="260"
            show-overflow-tooltip
          >
            <template #default="{ row }">{{
              duplicateReasonsText(row)
            }}</template>
          </el-table-column>
          <el-table-column label="操作" width="110" fixed="right">
            <template #default="{ row }">
              <el-button
                size="small"
                type="warning"
                plain
                @click="mergeDuplicatePage(row)"
              >
                合并此页
              </el-button>
            </template>
          </el-table-column>
        </el-table>
      </div>
      <template #footer>
        <el-button @click="duplicateDialog.visible = false">关闭</el-button>
        <el-button
          type="warning"
          :disabled="!selectedDuplicatePageIds.length"
          :loading="mergingPages"
          @click="mergeSelectedDuplicatePages"
        >
          合并选中（{{ selectedDuplicatePageIds.length }}）
        </el-button>
      </template>
    </el-dialog>

    <el-dialog
      v-model="inspectionDraftDialog.visible"
      title="目标巡检草稿"
      width="920px"
      destroy-on-close
    >
      <div v-if="inspectionDraft" class="inspection-draft-dialog">
        <el-alert
          type="success"
          show-icon
          :closable="false"
          :title="`已从「${inspectionDraft.page_name || displayPageName(selectedPage)}」生成 ${inspectionDraft.target_count || 0} 个巡检目标`"
          description="目标巡检会严格按清单查找并点击，找不到就记录未找到，不会点击清单外控件。"
        />
        <el-input
          class="inspection-target-textarea"
          type="textarea"
          :rows="8"
          readonly
          :model-value="inspectionDraftTargetText"
        />
        <el-table
          :data="inspectionDraft.targets || []"
          border
          height="320"
          empty-text="暂无可巡检目标"
        >
          <el-table-column label="目标" min-width="180" show-overflow-tooltip>
            <template #default="{ row }">{{ row.target_name }}</template>
          </el-table-column>
          <el-table-column label="角色" width="90">
            <template #default="{ row }">{{ roleLabel(row.role) }}</template>
          </el-table-column>
          <el-table-column label="推荐度" width="100">
            <template #default="{ row }">{{
              row.candidate_score || 0
            }}</template>
          </el-table-column>
          <el-table-column
            label="resource-id"
            min-width="220"
            show-overflow-tooltip
          >
            <template #default="{ row }">{{ row.resource_id || "-" }}</template>
          </el-table-column>
          <el-table-column label="依据" min-width="220" show-overflow-tooltip>
            <template #default="{ row }">{{
              row.candidate_reason || "-"
            }}</template>
          </el-table-column>
        </el-table>
      </div>
      <template #footer>
        <el-button @click="inspectionDraftDialog.visible = false"
          >关闭</el-button
        >
        <el-button
          :disabled="!inspectionDraftTargetText"
          @click="copyInspectionTargets"
          >复制目标清单</el-button
        >
        <el-button
          type="primary"
          :disabled="!inspectionDraft?.target_count"
          @click="sendInspectionDraftToExploration"
        >
          带入 AI 探索
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from "vue";
import { useRouter } from "vue-router";
import { ElMessage, ElMessageBox } from "element-plus";
import {
  bulkPromotePageMapElements,
  getAppProjects,
  getPackageList,
  getPageMapDuplicateCandidates,
  getPageMapElementCandidates,
  getPageMapInspectionTargetDraft,
  getPageMapNodes,
  getPageMapSummary,
  getPageMapTransitions,
  getSemanticDictionaryOptions,
  governPageMapElements,
  mergePageMapNodes,
  promotePageMapElement,
  setPageMapBusinessName,
} from "@/api/app-automation";
import {
  buildSemanticElementName,
  semanticObjectOptions as defaultSemanticObjectOptions,
  semanticPageOptions as defaultSemanticPageOptions,
  semanticRoleOptions as defaultSemanticRoleOptions,
} from "@/config/semanticNaming";

const loading = ref(false);
const router = useRouter();
const candidateLoading = ref(false);
const transitionLoading = ref(false);
const projects = ref([]);
const packages = ref([]);
const pageNodes = ref([]);
const candidates = ref([]);
const transitions = ref([]);
const duplicateCandidates = ref([]);
const inspectionDraft = ref(null);
const selectedPage = ref(null);
const selectedPageIds = ref([]);
const selectedDuplicatePageIds = ref([]);
const selectedCandidate = ref(null);
const selectedCandidateIds = ref([]);
const summary = ref({});
const pageNameDraft = ref("");
const savingPageName = ref(false);
const mergingPages = ref(false);
const loadingDuplicateCandidates = ref(false);
const loadingInspectionDraft = ref(false);
const bulkPromoting = ref(false);
const governingCandidates = ref(false);
const promoteFormRef = ref(null);
const semanticPageOptions = ref([...defaultSemanticPageOptions]);
const semanticObjectOptions = ref([...defaultSemanticObjectOptions]);
const semanticRoleOptions = ref([...defaultSemanticRoleOptions, "页面入口"]);
const recoveringPageMapState = ref(false);

const promoteDialog = reactive({
  visible: false,
  row: null,
  submitting: false,
});

const duplicateDialog = reactive({
  visible: false,
});

const inspectionDraftDialog = reactive({
  visible: false,
});

const promoteForm = reactive({
  semantic_object: "",
  semantic_page: "",
  semantic_role: "",
  manual_note: "",
});

const query = reactive({
  project: "",
  app_package: "",
  search: "",
});

const candidateQuery = reactive({
  clickable: true,
  role: "",
  level: "",
  includeIgnored: false,
});

const summaryCards = computed(() => [
  {
    label: "页面节点",
    value: summary.value.page_count || 0,
    desc: "已沉淀页面",
  },
  {
    label: "控件快照",
    value: summary.value.element_count || 0,
    desc: "可复用候选来源",
  },
  {
    label: "可点击控件",
    value: summary.value.clickable_count || 0,
    desc: "优先维护对象",
  },
  {
    label: "跳转关系",
    value: summary.value.transition_count || 0,
    desc: "AI 规划路径基础",
  },
]);

const visibleCandidates = computed(() => {
  if (!candidateQuery.level) return candidates.value;
  return candidates.value.filter(
    (item) => item.candidate_level === candidateQuery.level,
  );
});

const candidateEmptyTip = computed(() => {
  if (!selectedPage.value) {
    return "当前没有选中页面，建议先选择页面，或点击“查看全部候选”。";
  }
  const clickableCount = Number(selectedPage.value.clickable_count || 0);
  const elementCount = Number(
    selectedPage.value.element_count || selectedPage.value.control_count || 0,
  );
  if (candidateQuery.clickable && clickableCount <= 0 && elementCount > 0) {
    return "该页面有控件快照，但没有可点击控件；可以放宽筛选查看文本、图片或容器。";
  }
  if (
    candidateQuery.clickable ||
    candidateQuery.role ||
    candidateQuery.level ||
    !candidateQuery.includeIgnored
  ) {
    return "可能是筛选条件过窄、候选已被忽略，或同名重复页面分散了控件数据。";
  }
  return "该页面暂未沉淀控件快照，建议重新跑一次受控巡检或检查重复页面。";
});

const pageMapWorkflow = computed(() => {
  const page = selectedPage.value;
  const candidateCount = visibleCandidates.value.length;
  const clickableCount = Number(page?.clickable_count || 0);
  const hasPageName = Boolean(String(page?.business_name || "").trim());
  const hasSelection = Boolean(page?.id);
  const hasDuplicateSelection = selectedPageIds.value.some(
    (id) => id !== page?.id,
  );

  if (!hasSelection) {
    return {
      badge: "先选页面",
      tagType: "info",
      title: "先从下面选一个你要治理的页面",
      description:
        "页面地图不是测试报告，它是“把探索结果整理成可复用资产”的工作台。先选一个核心页面，再命名、合并重复、治理控件。",
      actions: [
        { key: "select_first", label: "选择第一个有控件页面", type: "primary" },
        { key: "back_exploration", label: "返回 AI 探索", type: "info" },
      ],
      steps: workflowSteps(0),
    };
  }

  if (!hasPageName) {
    return {
      badge: "待命名",
      tagType: "warning",
      title: `当前选中：${displayPageName(page)}，先给它一个业务名`,
      description:
        "页面签名和 Activity 是技术字段，测试同学不应该靠它们判断页面。先把页面命名成“社区首页、消息页、个人中心”这种业务名。",
      actions: [
        {
          key: "focus_page_name",
          label: "去命名页面",
          type: "warning",
          plain: false,
        },
        { key: "duplicates", label: "检查重复页", type: "warning" },
      ],
      steps: workflowSteps(1),
    };
  }

  if (!candidateCount && clickableCount > 0) {
    return {
      badge: "候选为空",
      tagType: "warning",
      title: "这个页面有可点击控件，但当前列表没展示出来",
      description:
        "优先放宽筛选；如果仍为空，多半是前端还停在旧页面节点或旧服务端口，刷新页面后重新选择这个页面。",
      actions: [
        { key: "relax", label: "放宽筛选", type: "warning", plain: false },
        { key: "reload", label: "刷新并重选", type: "primary" },
        { key: "duplicates", label: "检查重复页", type: "warning" },
      ],
      steps: workflowSteps(2),
    };
  }

  if (!candidateCount) {
    return {
      badge: "缺少控件",
      tagType: "warning",
      title: "当前页面还没有可用控件候选",
      description:
        "这类页面暂时不适合生成巡检目标。建议先回 AI 探索重新跑一次，或换一个有控件的核心页面治理。",
      actions: [
        { key: "back_exploration", label: "回 AI 探索重跑", type: "primary" },
        { key: "show_all", label: "查看全部候选", type: "info" },
      ],
      steps: workflowSteps(2),
    };
  }

  if (hasDuplicateSelection) {
    return {
      badge: "可合并",
      tagType: "warning",
      title: "你已经勾选了疑似重复页",
      description:
        "确认这些页面业务上是同一个页面后，可以合并到当前页面，减少后续维护成本。",
      actions: [
        {
          key: "merge_selected",
          label: "合并到当前页面",
          type: "warning",
          plain: false,
        },
        { key: "duplicates", label: "重新推荐重复页", type: "warning" },
      ],
      steps: workflowSteps(1),
    };
  }

  return {
    badge: "可生成目标",
    tagType: "success",
    title: `${page.business_name} 已具备生成巡检目标的基础`,
    description:
      "下一步只维护关键入口，不要把所有控件都入库。确认候选控件后生成目标巡检，再带入 AI 探索执行。",
    actions: [
      { key: "draft", label: "生成巡检目标", type: "success", plain: false },
      { key: "duplicates", label: "检查重复页", type: "warning" },
      { key: "show_all", label: "查看全部候选", type: "primary" },
    ],
    steps: workflowSteps(3),
  };
});

function workflowSteps(activeIndex) {
  const items = [
    { title: "选页面", desc: "优先选 P0 核心页面，例如社区首页。" },
    { title: "命名/合并", desc: "页面名用业务中文，重复页先合并。" },
    { title: "治理控件", desc: "只维护关键入口、按钮、Tab。" },
    { title: "生成巡检", desc: "生成目标清单后带入 AI 探索执行。" },
  ];
  return items.map((item, index) => ({
    ...item,
    active: index === activeIndex,
  }));
}

const canMergePages = computed(
  () =>
    Boolean(selectedPage.value?.id) &&
    selectedPageIds.value.some((id) => id !== selectedPage.value.id),
);

const inspectionDraftTargetText = computed(() =>
  Array.isArray(inspectionDraft.value?.target_list)
    ? inspectionDraft.value.target_list.join("\n")
    : "",
);

const promoteNamePreview = computed(() =>
  buildSemanticElementName({
    page: promoteForm.semantic_page,
    object: promoteForm.semantic_object,
    role: promoteForm.semantic_role,
  }),
);

const promotePreviewStyle = computed(() => {
  const size = promoteDialog.row?.page_screen_size || [];
  const width = Number(size[0] || 0);
  const height = Number(size[1] || 0);
  if (!width || !height) return {};
  return { aspectRatio: `${width} / ${height}` };
});

const promoteRules = {
  semantic_object: [
    { required: true, message: "请填写业务对象", trigger: "blur" },
  ],
  semantic_page: [
    { required: true, message: "请选择或输入页面名称", trigger: "change" },
  ],
  semantic_role: [
    { required: true, message: "请选择或输入元素角色", trigger: "change" },
  ],
};

function baseParams() {
  return {
    project: query.project || undefined,
    app_package: query.app_package || undefined,
    search: query.search || undefined,
  };
}

function normalizeList(response) {
  const payload = response?.data ?? response;
  if (Array.isArray(payload)) return payload;
  if (Array.isArray(payload?.results)) return payload.results;
  if (Array.isArray(payload?.data?.results)) return payload.data.results;
  if (Array.isArray(payload?.data)) return payload.data;
  return [];
}

function isNotFoundError(error) {
  return (
    Number(error?.response?.status) === 404 ||
    Boolean(error?.response?.data?.stale)
  );
}

function pageMapErrorMessage(error, fallback) {
  return (
    error?.response?.data?.message ||
    error?.userMessage ||
    error?.message ||
    fallback
  );
}

async function reconcileSelectedPage() {
  if (!selectedPage.value?.id) return;
  const refreshed = pageNodes.value.find(
    (item) => item.id === selectedPage.value.id,
  );
  if (refreshed) {
    selectedPage.value = refreshed;
    pageNameDraft.value = refreshed.business_name || "";
    return;
  }
  selectedPage.value =
    pageNodes.value.find((item) => Number(item.element_count || 0) > 0) ||
    pageNodes.value[0] ||
    null;
  pageNameDraft.value = selectedPage.value?.business_name || "";
  selectedCandidate.value = null;
  selectedCandidateIds.value = [];
  selectedPageIds.value = [];
}

async function recoverFromStalePageState(options = {}) {
  const { silent = false } = options;
  if (recoveringPageMapState.value) return true;
  recoveringPageMapState.value = true;
  try {
    selectedPage.value = null;
    pageNameDraft.value = "";
    selectedCandidate.value = null;
    selectedCandidateIds.value = [];
    selectedPageIds.value = [];
    selectedDuplicatePageIds.value = [];
    duplicateDialog.visible = false;
    duplicateCandidates.value = [];
    inspectionDraft.value = null;
    inspectionDraftDialog.visible = false;

    await loadPages();
    const fallbackPage =
      pageNodes.value.find((item) => Number(item.element_count || 0) > 0) ||
      pageNodes.value[0] ||
      null;
    if (fallbackPage) {
      selectedPage.value = fallbackPage;
      pageNameDraft.value = fallbackPage.business_name || "";
      await Promise.allSettled([loadCandidates(), loadTransitions()]);
    }
    if (!silent) {
      ElMessage.warning("页面地图数据已变化，已自动刷新并切换到有效页面");
    }
    return true;
  } catch (error) {
    ElMessage.error(pageMapErrorMessage(error, "页面地图刷新失败，请稍后重试"));
    return false;
  } finally {
    recoveringPageMapState.value = false;
  }
}

async function loadMeta() {
  const [projectResp, packageResp] = await Promise.all([
    getAppProjects({ page_size: 200 }),
    getPackageList({ page_size: 200 }),
  ]);
  projects.value = normalizeList(projectResp);
  packages.value = normalizeList(packageResp);
  await loadSemanticDictionaries();
}

function normalizeDictionaryValues(items = [], fallback = []) {
  const values = items
    .map((item) => item.value || item.label || item)
    .filter(Boolean);
  return Array.from(new Set(values.length ? values : fallback));
}

async function loadSemanticDictionaries() {
  try {
    const params = query.project ? { project: query.project } : {};
    const { data } = await getSemanticDictionaryOptions(params);
    const options = data?.data || {};
    semanticPageOptions.value = normalizeDictionaryValues(
      options.page,
      defaultSemanticPageOptions,
    );
    semanticObjectOptions.value = normalizeDictionaryValues(
      options.object,
      defaultSemanticObjectOptions,
    );
    semanticRoleOptions.value = normalizeDictionaryValues(options.role, [
      ...defaultSemanticRoleOptions,
      "页面入口",
    ]);
  } catch (error) {
    console.warn("语义字典加载失败，已使用前端默认字典:", error);
  }
}

async function loadSummary() {
  const resp = await getPageMapSummary(baseParams());
  summary.value = resp?.data?.data || resp?.data || {};
}

async function loadPages() {
  const resp = await getPageMapNodes({ ...baseParams(), page_size: 50 });
  pageNodes.value = normalizeList(resp);
  await reconcileSelectedPage();
}

async function loadCandidates() {
  candidateLoading.value = true;
  try {
    const resp = await getPageMapElementCandidates({
      ...baseParams(),
      page_id: selectedPage.value?.id || undefined,
      clickable: candidateQuery.clickable ? 1 : undefined,
      role: candidateQuery.role || undefined,
      include_ignored: candidateQuery.includeIgnored ? 1 : undefined,
      page_size: 80,
    });
    candidates.value = normalizeList(resp);
    const currentList = visibleCandidates.value;
    if (
      !selectedCandidate.value ||
      !currentList.some((item) => item.id === selectedCandidate.value.id)
    ) {
      selectedCandidate.value = currentList[0] || null;
    }
  } catch (error) {
    candidates.value = [];
    selectedCandidate.value = null;
    selectedCandidateIds.value = [];
    if (isNotFoundError(error)) {
      await recoverFromStalePageState();
      return;
    }
    ElMessage.error(pageMapErrorMessage(error, "加载控件候选失败"));
  } finally {
    candidateLoading.value = false;
  }
}

async function loadTransitions() {
  transitionLoading.value = true;
  try {
    const resp = await getPageMapTransitions({
      ...baseParams(),
      page_id: selectedPage.value?.id || undefined,
      page_size: 80,
    });
    transitions.value = normalizeList(resp);
  } catch (error) {
    transitions.value = [];
    if (isNotFoundError(error)) {
      await recoverFromStalePageState({ silent: true });
      return;
    }
    ElMessage.error(pageMapErrorMessage(error, "加载跳转关系失败"));
  } finally {
    transitionLoading.value = false;
  }
}

async function loadAll() {
  loading.value = true;
  try {
    await loadSemanticDictionaries();
    await Promise.all([loadSummary(), loadPages()]);
    await Promise.all([loadCandidates(), loadTransitions()]);
  } catch (error) {
    if (isNotFoundError(error)) {
      await recoverFromStalePageState();
    } else {
      ElMessage.error(pageMapErrorMessage(error, "加载页面地图失败"));
    }
  } finally {
    loading.value = false;
  }
}

async function selectPage(row) {
  selectedPage.value = row;
  pageNameDraft.value = row.business_name || "";
  await Promise.all([loadCandidates(), loadTransitions()]);
}

async function clearSelectedPage() {
  selectedPage.value = null;
  pageNameDraft.value = "";
  selectedCandidateIds.value = [];
  await Promise.all([loadCandidates(), loadTransitions()]);
}

function selectCandidate(row) {
  selectedCandidate.value = row;
}

function candidateRowClassName({ row }) {
  return selectedCandidate.value?.id === row.id ? "selected-candidate-row" : "";
}

function handleCandidateSelection(rows) {
  selectedCandidateIds.value = rows
    .filter(isCandidateSelectable)
    .map((row) => row.id);
}

function handlePageSelection(rows) {
  selectedPageIds.value = rows.map((row) => row.id).filter(Boolean);
}

function resetCandidateSelection() {
  selectedCandidateIds.value = [];
  selectedCandidate.value = visibleCandidates.value[0] || null;
}

async function handleCandidateLevelChange() {
  if (candidateQuery.level === "ignored") {
    candidateQuery.includeIgnored = true;
    await loadCandidates();
  }
  resetCandidateSelection();
}

async function handleWorkflowAction(action) {
  if (action === "select_first") {
    const page =
      pageNodes.value.find((item) => Number(item.element_count || 0) > 0) ||
      pageNodes.value[0];
    if (page) await selectPage(page);
    return;
  }
  if (action === "focus_page_name") {
    const input = document.querySelector(".page-governance-actions input");
    if (input) input.focus();
    return;
  }
  if (action === "duplicates") {
    await openDuplicateCandidates();
    return;
  }
  if (action === "relax") {
    await relaxCandidateFilters();
    return;
  }
  if (action === "reload") {
    await loadAll();
    const refreshed = pageNodes.value.find(
      (item) => item.id === selectedPage.value?.id,
    );
    if (refreshed) await selectPage(refreshed);
    return;
  }
  if (action === "show_all") {
    await clearSelectedPage();
    return;
  }
  if (action === "merge_selected") {
    await mergeSelectedPages();
    return;
  }
  if (action === "draft") {
    await openInspectionDraft();
    return;
  }
  if (action === "back_exploration") {
    router.push("/app-automation/exploration");
  }
}

async function relaxCandidateFilters() {
  candidateQuery.clickable = false;
  candidateQuery.role = "";
  candidateQuery.level = "";
  candidateQuery.includeIgnored = true;
  await loadCandidates();
  resetCandidateSelection();
}

function pageStatusLabel(row) {
  if (!row?.business_name) return "待命名";
  if ((row.element_count || 0) <= 0) return "待采集";
  if ((row.clickable_count || 0) <= 0) return "待补控件";
  return "已治理";
}

function pageStatusType(row) {
  const label = pageStatusLabel(row);
  return (
    {
      已治理: "success",
      待采集: "info",
      待补控件: "warning",
      待命名: "danger",
    }[label] || "info"
  );
}

function displayPageName(row) {
  if (!row) return "未命名页面";
  if (row.business_name) return row.business_name;
  const id = row.id || String(row.page_signature || "").slice(-6);
  return id ? `未命名页面 #${id}` : "未命名页面";
}

function displayTransitionPage(row, direction) {
  const businessName = row?.[`${direction}_page_business_name`];
  if (businessName) return businessName;
  const activity = row?.[`${direction}_activity`];
  return activity ? `未命名页面（${activity}）` : "未命名页面";
}

async function savePageName() {
  if (!selectedPage.value?.id) {
    ElMessage.warning("请先选择一个页面节点");
    return;
  }
  const name = pageNameDraft.value.trim();
  if (!name) {
    ElMessage.warning("页面名称不能为空");
    return;
  }
  savingPageName.value = true;
  try {
    const resp = await setPageMapBusinessName(selectedPage.value.id, {
      business_name: name,
    });
    selectedPage.value = resp?.data?.data || {
      ...selectedPage.value,
      business_name: name,
    };
    const page = pageNodes.value.find(
      (item) => item.id === selectedPage.value.id,
    );
    if (page) page.business_name = name;
    ElMessage.success(resp?.data?.message || "页面名称已保存");
  } catch (error) {
    if (isNotFoundError(error)) {
      await recoverFromStalePageState();
      return;
    }
    ElMessage.error(pageMapErrorMessage(error, "保存页面名称失败"));
  } finally {
    savingPageName.value = false;
  }
}

async function renamePageById(pageId, name) {
  const resp = await setPageMapBusinessName(pageId, { business_name: name });
  const updatedPage = resp?.data?.data || null;
  const page = pageNodes.value.find((item) => item.id === pageId);
  if (page) page.business_name = name;
  if (selectedPage.value?.id === pageId) {
    selectedPage.value = updatedPage || {
      ...selectedPage.value,
      business_name: name,
    };
    pageNameDraft.value = name;
  }
  transitions.value = transitions.value.map((item) => {
    const next = { ...item };
    if (next.from_page === pageId) next.from_page_business_name = name;
    if (next.to_page === pageId) next.to_page_business_name = name;
    return next;
  });
  return resp;
}

async function openRenamePage(row) {
  if (!row?.id) return;
  try {
    const { value } = await ElMessageBox.prompt(
      "给这个页面起一个稳定的业务名称，例如：社区首页、消息页、个人中心页。",
      row.business_name ? "重命名页面" : "命名页面",
      {
        confirmButtonText: "保存",
        cancelButtonText: "取消",
        inputValue: row.business_name || "",
        inputPlaceholder: "请输入页面业务名称",
        inputValidator: (value) => Boolean(String(value || "").trim()),
        inputErrorMessage: "页面名称不能为空",
      },
    );
    const name = String(value || "").trim();
    if (!name) return;
    const resp = await renamePageById(row.id, name);
    ElMessage.success(resp?.data?.message || "页面名称已保存");
    await Promise.all([loadSummary(), loadCandidates(), loadTransitions()]);
  } catch (error) {
    if (error !== "cancel" && error !== "close") {
      if (isNotFoundError(error)) {
        await recoverFromStalePageState();
        return;
      }
      ElMessage.error(pageMapErrorMessage(error, "保存页面名称失败"));
    }
  }
}

async function openRenameTransitionPage(row, direction) {
  const pageId = row?.[`${direction}_page`];
  if (!pageId) return;
  const currentName = row?.[`${direction}_page_business_name`] || "";
  try {
    const { value } = await ElMessageBox.prompt(
      `当前页面：${displayTransitionPage(row, direction)}。建议按业务含义命名，不要用 Activity 或截图标题。`,
      currentName ? "重命名跳转页面" : "命名跳转页面",
      {
        confirmButtonText: "保存",
        cancelButtonText: "取消",
        inputValue: currentName,
        inputPlaceholder: "例如：社区首页、活动详情页、个人中心页",
        inputValidator: (value) => Boolean(String(value || "").trim()),
        inputErrorMessage: "页面名称不能为空",
      },
    );
    const name = String(value || "").trim();
    if (!name) return;
    const resp = await renamePageById(pageId, name);
    ElMessage.success(resp?.data?.message || "页面名称已保存");
    await Promise.all([loadSummary(), loadCandidates(), loadTransitions()]);
  } catch (error) {
    if (error !== "cancel" && error !== "close") {
      if (isNotFoundError(error)) {
        await recoverFromStalePageState();
        return;
      }
      ElMessage.error(pageMapErrorMessage(error, "保存页面名称失败"));
    }
  }
}

async function mergeSelectedPages() {
  if (!canMergePages.value) {
    ElMessage.warning("请先点击一个主页面，再勾选要合并的重复页面");
    return;
  }
  const sourceIds = selectedPageIds.value.filter(
    (id) => id !== selectedPage.value.id,
  );
  await mergePagesIntoCurrent(sourceIds);
}

async function mergePagesIntoCurrent(sourceIds) {
  if (!selectedPage.value?.id || !sourceIds?.length) return;
  const targetPageId = selectedPage.value.id;
  try {
    await ElMessageBox.confirm(
      `将 ${sourceIds.length} 个页面合并到「${displayPageName(selectedPage.value)}」。合并后重复页面会删除，控件和跳转关系会迁移到当前页面。`,
      "确认合并页面",
      {
        confirmButtonText: "确认合并",
        cancelButtonText: "取消",
        type: "warning",
      },
    );
    mergingPages.value = true;
    const resp = await mergePageMapNodes(selectedPage.value.id, {
      page_ids: sourceIds,
      business_name:
        selectedPage.value.business_name || pageNameDraft.value.trim(),
    });
    const data = resp?.data?.data || resp?.data || {};
    const targetPage = data.target_page || selectedPage.value;
    selectedPage.value = targetPage;
    pageNameDraft.value = targetPage.business_name || "";
    selectedPageIds.value = [];
    selectedDuplicatePageIds.value = [];
    duplicateDialog.visible = false;
    duplicateCandidates.value = [];
    ElMessage.success(resp?.data?.message || "页面合并完成");
    await Promise.all([loadSummary(), loadPages()]);
    const refreshedTarget = pageNodes.value.find(
      (item) => item.id === targetPage.id || item.id === targetPageId,
    );
    if (refreshedTarget) {
      selectedPage.value = refreshedTarget;
      pageNameDraft.value = refreshedTarget.business_name || "";
    }
    await Promise.all([loadCandidates(), loadTransitions()]);
  } catch (error) {
    if (error !== "cancel" && error !== "close") {
      if (isNotFoundError(error)) {
        await recoverFromStalePageState();
        return;
      }
      ElMessage.error(pageMapErrorMessage(error, "页面合并失败"));
    }
  } finally {
    mergingPages.value = false;
  }
}

async function openDuplicateCandidates() {
  if (!selectedPage.value?.id) {
    ElMessage.warning("请先选择一个页面节点");
    return;
  }
  duplicateDialog.visible = true;
  selectedDuplicatePageIds.value = [];
  await loadDuplicateCandidates();
}

async function openInspectionDraft() {
  if (!selectedPage.value?.id) {
    ElMessage.warning("请先选择一个页面节点");
    return;
  }
  loadingInspectionDraft.value = true;
  try {
    const resp = await getPageMapInspectionTargetDraft(selectedPage.value.id, {
      limit: 40,
    });
    inspectionDraft.value = resp?.data?.data || null;
    inspectionDraftDialog.visible = true;
    if (!inspectionDraft.value?.target_count) {
      ElMessage.warning(
        "当前页面暂无可生成的巡检目标，建议先治理控件候选或恢复被忽略控件",
      );
    }
  } catch (error) {
    if (isNotFoundError(error)) {
      inspectionDraft.value = null;
      inspectionDraftDialog.visible = false;
      await recoverFromStalePageState();
      return;
    }
    ElMessage.error(pageMapErrorMessage(error, "生成巡检目标失败"));
  } finally {
    loadingInspectionDraft.value = false;
  }
}

async function copyInspectionTargets() {
  const text = inspectionDraftTargetText.value;
  if (!text) return;
  try {
    await navigator.clipboard.writeText(text);
    ElMessage.success("目标清单已复制");
  } catch (error) {
    ElMessage.error("复制失败，请手动选择文本复制");
  }
}

function sendInspectionDraftToExploration() {
  if (!inspectionDraft.value?.target_count) return;
  const page = inspectionDraft.value.page || selectedPage.value || {};
  const draft = {
    source: "page_map",
    created_at: new Date().toISOString(),
    name: `${inspectionDraft.value.page_name || displayPageName(selectedPage.value)} - 目标巡检`,
    project: page.project || query.project || null,
    app_package: page.app_package || query.app_package || null,
    strategy: "target_inspection",
    objective: inspectionDraft.value.objective || "",
    entry_keywords: inspectionDraft.value.target_list || [],
    start_note: inspectionDraft.value.start_note || "",
    max_steps: Math.max(
      Number(inspectionDraft.value.target_count || 0) * 3,
      20,
    ),
    max_duration: 300,
    source_summary: {
      source: "page_map",
      page_id: page.id,
      page_name: inspectionDraft.value.page_name || "",
      target_count: inspectionDraft.value.target_count || 0,
      targets: inspectionDraft.value.targets || [],
    },
  };
  window.localStorage.setItem(
    "qaflow_page_map_inspection_draft",
    JSON.stringify(draft),
  );
  inspectionDraftDialog.visible = false;
  router.push("/app-automation/exploration");
}

async function loadDuplicateCandidates() {
  if (!selectedPage.value?.id) return;
  loadingDuplicateCandidates.value = true;
  try {
    const resp = await getPageMapDuplicateCandidates(selectedPage.value.id, {
      min_score: 35,
      limit: 20,
    });
    duplicateCandidates.value = normalizeList(resp);
    if (!duplicateCandidates.value.length) {
      ElMessage.info("暂无疑似重复页面");
    }
  } catch (error) {
    duplicateCandidates.value = [];
    selectedDuplicatePageIds.value = [];
    if (isNotFoundError(error)) {
      duplicateDialog.visible = false;
      await recoverFromStalePageState();
      return;
    }
    ElMessage.error(pageMapErrorMessage(error, "加载疑似重复页面失败"));
  } finally {
    loadingDuplicateCandidates.value = false;
  }
}

function handleDuplicateSelection(rows) {
  selectedDuplicatePageIds.value = rows.map((row) => row.id).filter(Boolean);
}

async function mergeDuplicatePage(row) {
  if (!row?.id) return;
  await mergePagesIntoCurrent([row.id]);
}

async function mergeSelectedDuplicatePages() {
  if (!selectedDuplicatePageIds.value.length) return;
  await mergePagesIntoCurrent(selectedDuplicatePageIds.value);
}

function duplicateReasonsText(row) {
  const reasons = Array.isArray(row?.duplicate_reasons)
    ? row.duplicate_reasons
    : [];
  return reasons.length ? reasons.join(" / ") : "-";
}

function duplicateScoreType(score) {
  const value = Number(score || 0);
  if (value >= 80) return "danger";
  if (value >= 60) return "warning";
  return "info";
}

async function bulkPromoteCandidates() {
  if (!selectedCandidateIds.value.length) return;
  const semanticPage =
    selectedPage.value?.business_name || pageNameDraft.value.trim();
  if (selectedPage.value?.id && !semanticPage) {
    ElMessage.warning("建议先保存页面名称，再批量入库");
    return;
  }
  bulkPromoting.value = true;
  try {
    const resp = await bulkPromotePageMapElements({
      element_ids: selectedCandidateIds.value,
      semantic_page: semanticPage,
      manual_note: "由页面地图批量入库生成，状态为待验证。",
    });
    ElMessage.success(resp?.data?.message || "批量入库完成");
    selectedCandidateIds.value = [];
    await loadCandidates();
  } catch (error) {
    ElMessage.error(pageMapErrorMessage(error, "批量加入语义库失败"));
  } finally {
    bulkPromoting.value = false;
  }
}

async function governCandidates(elementIds, governanceStatus) {
  if (!elementIds?.length) return;
  governingCandidates.value = true;
  try {
    const resp = await governPageMapElements({
      element_ids: elementIds,
      governance_status: governanceStatus,
    });
    ElMessage.success(resp?.data?.message || "控件候选治理完成");
    selectedCandidateIds.value = [];
    await loadCandidates();
  } catch (error) {
    ElMessage.error(pageMapErrorMessage(error, "控件候选治理失败"));
  } finally {
    governingCandidates.value = false;
  }
}

async function ignoreSelectedCandidates() {
  if (!selectedCandidateIds.value.length) return;
  try {
    await ElMessageBox.confirm(
      `将 ${selectedCandidateIds.value.length} 个候选标记为无需维护。默认列表会隐藏它们，后续可勾选“显示已忽略”恢复。`,
      "确认标记无需维护",
      {
        confirmButtonText: "确认忽略",
        cancelButtonText: "取消",
        type: "warning",
      },
    );
    await governCandidates(selectedCandidateIds.value, "ignored");
  } catch (error) {
    if (error !== "cancel" && error !== "close") {
      ElMessage.error(pageMapErrorMessage(error, "标记无需维护失败"));
    }
  }
}

async function restoreCandidate(row) {
  if (!row?.id) return;
  await governCandidates([row.id], "active");
}

async function promoteCandidate(row) {
  if (!isCandidateSelectable(row)) {
    ElMessage.warning(promoteButtonTip(row));
    return;
  }
  promoteDialog.row = row;
  promoteForm.semantic_object = displayCandidateName(row);
  promoteForm.semantic_page =
    selectedPage.value?.business_name || row.page_business_name || "";
  promoteForm.semantic_role = normalizeSemanticRole(row.role);
  promoteForm.manual_note =
    row.candidate_level === "not_recommended"
      ? "低置信候选，已结合截图人工确认后入库。"
      : "";
  promoteDialog.visible = true;
}

async function submitPromoteCandidate() {
  if (!promoteDialog.row) return;
  await promoteFormRef.value?.validate();
  promoteDialog.submitting = true;
  try {
    const semanticPage = promoteForm.semantic_page.trim();
    const semanticObject = promoteForm.semantic_object.trim();
    const semanticRole = promoteForm.semantic_role.trim();
    const resp = await promotePageMapElement({
      element_id: promoteDialog.row.id,
      description: semanticObject,
      semantic_page: semanticPage,
      semantic_role: semanticRole,
      semantic_object: semanticObject,
      manual_note: promoteForm.manual_note,
    });

    if (
      selectedPage.value?.id &&
      semanticPage &&
      selectedPage.value.business_name !== semanticPage
    ) {
      await setPageMapBusinessName(selectedPage.value.id, {
        business_name: semanticPage,
      });
      selectedPage.value.business_name = semanticPage;
      const page = pageNodes.value.find(
        (item) => item.id === selectedPage.value.id,
      );
      if (page) page.business_name = semanticPage;
    }

    ElMessage.success(resp?.data?.message || "已加入语义库候选");
    promoteDialog.visible = false;
    promoteDialog.row = null;
    await Promise.all([loadPages(), loadCandidates(), loadTransitions()]);
  } catch (error) {
    if (error !== false) {
      if (isNotFoundError(error)) {
        await recoverFromStalePageState();
        return;
      }
      ElMessage.error(pageMapErrorMessage(error, "加入语义库失败"));
    }
  } finally {
    promoteDialog.submitting = false;
  }
}

function querySemanticObjectSuggestions(queryString, callback) {
  const keyword = String(queryString || "").trim();
  const candidates = semanticObjectOptions.value
    .filter((item) => !keyword || item.includes(keyword))
    .map((item) => ({ value: item }));
  callback(candidates);
}

function normalizeSemanticRole(role) {
  return (
    {
      button: "按钮",
      input: "输入框",
      switch: "开关",
      image: "图片",
      text: "文本",
      clickable: "页面入口",
      view: "容器",
    }[role] ||
    role ||
    "页面入口"
  );
}

function displayCandidateName(row) {
  return (
    row?.candidate_name ||
    row?.text ||
    row?.content_desc ||
    shortResource(row?.resource_id) ||
    "未命名控件"
  );
}

function isCandidateSelectable(row) {
  return !row?.semantic_element && !isIgnoredCandidate(row);
}

function isIgnoredCandidate(row) {
  return (
    row?.candidate_governance_status === "ignored" ||
    row?.candidate_level === "ignored"
  );
}

function promoteButtonText(row) {
  if (row?.semantic_element || row?.candidate_level === "promoted")
    return "已入库";
  if (row?.candidate_level === "not_recommended") return "谨慎入库";
  return "加入语义库";
}

function promoteButtonTip(row) {
  if (row?.semantic_element || row?.candidate_level === "promoted") {
    return "这个候选已经生成语义元素了";
  }
  if (row?.candidate_level === "not_recommended") {
    return (
      row?.candidate_action ||
      "该候选更像容器或低价值节点，入库前请结合截图确认"
    );
  }
  return "";
}

function candidateLevelType(level) {
  return (
    {
      promoted: "success",
      ignored: "info",
      recommended: "primary",
      review: "warning",
      not_recommended: "info",
    }[level] || "warning"
  );
}

function candidateProgressStatus(level) {
  return (
    {
      promoted: "success",
      ignored: "exception",
      recommended: "success",
      review: "warning",
      not_recommended: "exception",
    }[level] || ""
  );
}

function shortResource(value) {
  const text = String(value || "");
  return text.includes("/") ? text.split("/").pop() : text;
}

function roleLabel(role) {
  return (
    {
      button: "按钮",
      input: "输入框",
      switch: "开关",
      image: "图片",
      text: "文本",
      clickable: "可点击",
      view: "视图",
    }[role] ||
    role ||
    "未知"
  );
}

const candidatePreviewStyle = computed(() => {
  const size = selectedCandidate.value?.page_screen_size || [];
  const width = Number(size[0] || 0);
  const height = Number(size[1] || 0);
  if (!width || !height) return {};
  return { aspectRatio: `${width} / ${height}` };
});

function candidateOverlayStyle(row) {
  const normalized = row?.normalized_bounds || {};
  if (
    normalized.x1 !== undefined &&
    normalized.y1 !== undefined &&
    normalized.x2 !== undefined &&
    normalized.y2 !== undefined
  ) {
    return {
      left: `${Number(normalized.x1) * 100}%`,
      top: `${Number(normalized.y1) * 100}%`,
      width: `${Math.max(0.8, (Number(normalized.x2) - Number(normalized.x1)) * 100)}%`,
      height: `${Math.max(0.8, (Number(normalized.y2) - Number(normalized.y1)) * 100)}%`,
    };
  }
  const bounds = parseBounds(row?.bounds);
  const size = row?.page_screen_size || [];
  const width = Number(size[0] || 0);
  const height = Number(size[1] || 0);
  if (!bounds || !width || !height) return { display: "none" };
  return {
    left: `${(bounds.x1 / width) * 100}%`,
    top: `${(bounds.y1 / height) * 100}%`,
    width: `${Math.max(0.8, ((bounds.x2 - bounds.x1) / width) * 100)}%`,
    height: `${Math.max(0.8, ((bounds.y2 - bounds.y1) / height) * 100)}%`,
  };
}

function parseBounds(bounds) {
  const match = String(bounds || "").match(/\[(\d+),(\d+)\]\[(\d+),(\d+)\]/);
  if (!match) return null;
  const [, x1, y1, x2, y2] = match.map(Number);
  return { x1, y1, x2, y2 };
}

onMounted(async () => {
  await loadMeta();
  await loadAll();
});
</script>

<style scoped>
.page-map-workbench {
  padding: 20px;
}

.page-hero {
  display: flex;
  justify-content: space-between;
  gap: 20px;
  align-items: flex-start;
  padding: 24px;
  border-radius: 20px;
  background:
    radial-gradient(
      circle at top right,
      rgba(34, 197, 94, 0.16),
      transparent 34%
    ),
    linear-gradient(135deg, #f7fff9 0%, #eef8ff 100%);
  border: 1px solid #d7f5df;
}

.eyebrow {
  margin: 0 0 8px;
  color: #16803c;
  font-size: 13px;
  letter-spacing: 0.08em;
  text-transform: uppercase;
}

.page-hero h2 {
  margin: 0;
  color: #102033;
  font-size: 28px;
}

.page-hero p:last-child {
  max-width: 760px;
  margin: 10px 0 0;
  color: #4c5f70;
  line-height: 1.7;
}

.filter-card,
.content-card,
.summary-grid,
.detail-grid {
  margin-top: 16px;
}

.filter-form {
  margin-bottom: -18px;
}

.option-meta {
  float: right;
  color: #909399;
  font-size: 12px;
}

.transition-page-cell {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  min-width: 0;
}

.transition-page-cell span {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.summary-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 14px;
}

.summary-card {
  border-color: #e5edf6;
}

.summary-card span,
.summary-card em,
.muted {
  color: #64748b;
  font-size: 13px;
  font-style: normal;
}

.summary-card strong {
  display: block;
  margin: 8px 0 4px;
  color: #14532d;
  font-size: 28px;
}

.workflow-card {
  margin-top: 16px;
  border-color: #bfdbfe;
  background: linear-gradient(135deg, #eff6ff 0%, #ffffff 70%);
}

.workflow-main {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 14px;
}

.workflow-copy strong {
  display: block;
  color: #0f172a;
  font-size: 17px;
  margin-bottom: 6px;
}

.workflow-copy p {
  margin: 0;
  color: #475569;
  line-height: 1.6;
}

.workflow-actions {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  flex-wrap: wrap;
  gap: 8px;
  min-width: 280px;
}

.workflow-steps {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 10px;
}

.workflow-step {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  padding: 12px;
  border-radius: 12px;
  border: 1px solid #e2e8f0;
  background: rgba(255, 255, 255, 0.88);
}

.workflow-step.active {
  border-color: #60a5fa;
  box-shadow: 0 10px 24px rgba(37, 99, 235, 0.1);
}

.workflow-step > span {
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

.workflow-step strong {
  display: block;
  color: #0f172a;
  font-size: 13px;
  margin-bottom: 4px;
}

.workflow-step p {
  margin: 0;
  color: #64748b;
  font-size: 12px;
  line-height: 1.5;
}

.section-title {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  align-items: center;
  font-weight: 700;
}

.page-title {
  color: #0f172a;
  font-weight: 700;
}

.page-title-line {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
}

.page-title-line .page-title {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.candidate-name-line {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
}

.candidate-name-line .page-title {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.score-text {
  display: inline-block;
  margin-top: 3px;
  color: #64748b;
  font-size: 12px;
}

.detail-grid {
  display: grid;
  grid-template-columns: minmax(0, 1.2fr) minmax(0, 1fr);
  gap: 16px;
}

.candidate-toolbar {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 12px;
  margin-bottom: 12px;
}

.page-governance-panel {
  display: flex;
  justify-content: space-between;
  gap: 14px;
  align-items: center;
  margin-bottom: 12px;
  padding: 12px;
  border-radius: 16px;
  border: 1px solid #bbf7d0;
  background: #f0fdf4;
}

.page-governance-panel strong {
  display: block;
  color: #14532d;
}

.page-governance-panel span {
  color: #4b7159;
  font-size: 13px;
}

.page-governance-actions {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.candidate-preview {
  display: grid;
  grid-template-columns: 180px minmax(0, 1fr);
  gap: 14px;
  align-items: center;
  margin-bottom: 12px;
  padding: 12px;
  border-radius: 16px;
  border: 1px solid #bfdbfe;
  background: #eff6ff;
}

.candidate-preview-shot {
  position: relative;
  width: 180px;
  max-height: 360px;
  overflow: hidden;
  border-radius: 14px;
  border: 1px solid #cbd5e1;
  background: #fff;
}

.candidate-shot {
  display: block;
  width: 100%;
  height: 100%;
  background: #fff;
}

.candidate-shot.placeholder {
  min-height: 240px;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #94a3b8;
}

.candidate-overlay {
  position: absolute;
  border: 3px solid #f97316;
  border-radius: 8px;
  background: rgba(249, 115, 22, 0.16);
  box-shadow:
    0 0 0 3px rgba(249, 115, 22, 0.22),
    0 10px 22px rgba(124, 45, 18, 0.22);
  pointer-events: none;
}

.candidate-overlay span {
  position: absolute;
  left: 0;
  bottom: calc(100% + 4px);
  max-width: 180px;
  padding: 3px 6px;
  border-radius: 6px;
  background: #f97316;
  color: #fff;
  font-size: 12px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.candidate-preview-info {
  display: grid;
  gap: 6px;
  min-width: 0;
}

.candidate-preview-info strong {
  color: #0f172a;
  font-size: 16px;
}

.candidate-preview-info span {
  color: #475569;
  font-size: 13px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.candidate-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
  padding: 28px 12px;
  color: #64748b;
  line-height: 1.5;
}

.candidate-empty strong {
  color: #0f172a;
  font-size: 14px;
}

.candidate-empty-actions {
  display: flex;
  align-items: center;
  justify-content: center;
  flex-wrap: wrap;
  gap: 8px;
}

.promote-layout {
  display: grid;
  grid-template-columns: 240px minmax(0, 1fr);
  gap: 18px;
  align-items: flex-start;
}

.promote-shot {
  position: sticky;
  top: 0;
  width: 240px;
  max-height: 520px;
  overflow: hidden;
  border: 1px solid #cbd5e1;
  border-radius: 16px;
  background: #f8fafc;
}

.promote-form {
  min-width: 0;
}

.locator-summary {
  display: grid;
  gap: 4px;
  min-width: 0;
  color: #64748b;
  font-size: 12px;
  line-height: 1.6;
}

.locator-summary span {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.inspection-draft-dialog,
.duplicate-dialog {
  display: grid;
  gap: 12px;
}

.inspection-target-textarea {
  font-family: Consolas, "Liberation Mono", monospace;
}

:deep(.selected-candidate-row) {
  --el-table-tr-bg-color: #fff7ed;
}

@media (max-width: 1000px) {
  .page-hero {
    flex-direction: column;
  }

  .summary-grid,
  .workflow-steps,
  .detail-grid {
    grid-template-columns: 1fr;
  }

  .workflow-main {
    flex-direction: column;
  }

  .workflow-actions {
    justify-content: flex-start;
    min-width: 0;
  }

  .candidate-preview {
    grid-template-columns: 1fr;
  }

  .page-governance-panel {
    align-items: flex-start;
    flex-direction: column;
  }

  .promote-layout {
    grid-template-columns: 1fr;
  }

  .promote-shot {
    position: relative;
    width: 100%;
  }
}
</style>
