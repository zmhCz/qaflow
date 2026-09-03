<template>
  <div class="case-library-page">
    <div class="page-header">
      <div>
        <h3>自动化用例库</h3>
        <p>按业务目录管理用例资产，按测试集组织执行。</p>
      </div>
      <div class="header-actions">
        <el-button :icon="Refresh" :loading="loading" @click="refreshAll"
          >刷新</el-button
        >
        <el-button type="primary" @click="createCase">新建用例</el-button>
      </div>
    </div>

    <el-card class="context-card" shadow="never">
      <el-form :model="form" label-width="84px" size="small">
        <el-row :gutter="14">
          <el-col :xs="24" :sm="12" :lg="5">
            <el-form-item label="所属项目">
              <el-select
                v-model="form.projectId"
                placeholder="全部项目"
                clearable
                filterable
                style="width: 100%"
                @change="handleProjectChange"
              >
                <el-option
                  v-for="proj in projectList"
                  :key="proj.id"
                  :label="proj.name"
                  :value="proj.id"
                />
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :xs="24" :sm="12" :lg="5">
            <el-form-item label="执行设备">
              <el-select
                v-model="form.deviceId"
                placeholder="运行用例时选择"
                filterable
                clearable
                style="width: 100%"
                :loading="devicesLoading"
              >
                <el-option
                  v-for="device in availableDevices"
                  :key="device.id"
                  :label="`${device.name || device.device_id} (${device.device_id})`"
                  :value="device.id"
                  :disabled="
                    device.status !== 'available' && device.status !== 'online'
                  "
                />
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :xs="24" :sm="12" :lg="5">
            <el-form-item label="应用包">
              <el-select
                v-model="form.packageId"
                placeholder="筛选/运行可选"
                clearable
                filterable
                style="width: 100%"
                @change="reloadCases"
              >
                <el-option
                  v-for="pkg in appPackages"
                  :key="pkg.id"
                  :label="`${pkg.name} (${pkg.package_name})`"
                  :value="pkg.id"
                />
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :xs="24" :sm="12" :lg="9">
            <el-form-item label="搜索">
              <el-input
                v-model="filters.q"
                placeholder="搜名称、描述、标签"
                clearable
                @clear="reloadCases"
                @keyup.enter="reloadCases"
              >
                <template #prefix>
                  <el-icon><Search /></el-icon>
                </template>
                <template #append>
                  <el-button :icon="Search" @click="reloadCases"
                    >搜索</el-button
                  >
                </template>
              </el-input>
            </el-form-item>
          </el-col>
        </el-row>
      </el-form>
    </el-card>

    <div class="library-workbench">
      <el-card class="folder-panel" shadow="never">
        <template #header>
          <div class="panel-header">
            <span>业务目录</span>
            <el-button
              link
              type="primary"
              :icon="FolderAdd"
              @click="openFolderDialog('create')"
            >
              新建
            </el-button>
          </div>
        </template>

        <el-tree
          ref="folderTreeRef"
          class="folder-tree"
          :data="folderTreeData"
          node-key="treeKey"
          :props="folderTreeProps"
          :current-node-key="selectedFolderKey"
          default-expand-all
          highlight-current
          @node-click="handleFolderClick"
        >
          <template #default="{ data }">
            <div class="folder-node">
              <span>{{ data.name }}</span>
              <el-tag size="small" effect="plain">{{
                data.case_count ?? 0
              }}</el-tag>
            </div>
          </template>
        </el-tree>

        <div
          class="folder-actions"
          v-if="selectedFolder && !selectedFolder.synthetic"
        >
          <el-button size="small" @click="openFolderDialog('rename')"
            >重命名</el-button
          >
          <el-button size="small" type="danger" plain @click="removeFolder"
            >删除</el-button
          >
        </div>
      </el-card>

      <div class="case-main">
        <el-card class="filter-card" shadow="never">
          <div class="filter-row">
            <el-select
              v-model="filters.priority"
              placeholder="优先级"
              clearable
              @change="reloadCases"
            >
              <el-option
                v-for="item in options.priorities"
                :key="item.value"
                :label="item.label"
                :value="item.value"
              />
            </el-select>
            <el-select
              v-model="filters.case_type"
              placeholder="用例类型"
              clearable
              @change="reloadCases"
            >
              <el-option
                v-for="item in options.case_types"
                :key="item.value"
                :label="item.label"
                :value="item.value"
              />
            </el-select>
            <el-select
              v-model="filters.lifecycle_status"
              placeholder="生命周期"
              clearable
              @change="reloadCases"
            >
              <el-option
                v-for="item in options.lifecycles"
                :key="item.value"
                :label="item.label"
                :value="item.value"
              />
            </el-select>
            <el-select
              v-model="filters.data_impact"
              placeholder="数据影响"
              clearable
              @change="reloadCases"
            >
              <el-option
                v-for="item in options.data_impacts"
                :key="item.value"
                :label="item.label"
                :value="item.value"
              />
            </el-select>
            <el-select
              v-model="filters.tagIds"
              placeholder="标签"
              clearable
              multiple
              collapse-tags
              @change="reloadCases"
            >
              <el-option
                v-for="tag in tagList"
                :key="tag.id"
                :label="tag.name"
                :value="tag.id"
              />
            </el-select>
            <el-select
              v-model="filters.latest_result"
              placeholder="最近结果"
              clearable
              @change="reloadCases"
            >
              <el-option label="未执行" value="not_run" />
              <el-option label="通过" value="passed" />
              <el-option label="失败" value="failed" />
              <el-option label="执行异常" value="error" />
              <el-option label="已停止" value="stopped" />
            </el-select>
            <el-switch
              v-model="filters.includeDeprecated"
              active-text="显示废弃"
              @change="reloadCases"
            />
            <el-button text @click="resetFilters">重置筛选</el-button>
            <el-button text type="primary" @click="openTagDialog"
              >标签管理</el-button
            >
          </div>
        </el-card>

        <div v-if="selectedCases.length > 0" class="batch-bar">
          <span
            >已选择 <strong>{{ selectedCases.length }}</strong> 条</span
          >
          <el-button
            type="success"
            size="small"
            :loading="precheckingDevice"
            @click="batchRun"
          >
            批量执行
          </el-button>
          <el-button type="primary" size="small" @click="openBatchGovernance">
            批量治理
          </el-button>
          <el-button size="small" @click="clearSelection">取消选择</el-button>
        </div>

        <el-table
          ref="tableRef"
          v-loading="loading"
          :data="testCases"
          class="case-table"
          empty-text="暂无测试用例"
          @selection-change="handleSelectionChange"
          @row-click="openCaseDetail"
        >
          <el-table-column type="selection" width="46" />
          <el-table-column label="用例名称" min-width="250">
            <template #default="{ row }">
              <div class="case-name">
                <span>{{ row.name }}</span>
                <div class="case-meta">
                  <span>{{ row.folder_name || "未分类" }}</span>
                  <span>{{ row.step_count || 0 }} 步</span>
                </div>
              </div>
            </template>
          </el-table-column>
          <el-table-column label="优先级" width="90">
            <template #default="{ row }">
              <el-tag :type="priorityTagType(row.priority)" effect="plain">{{
                row.priority || "-"
              }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column label="类型" width="100">
            <template #default="{ row }">{{
              row.case_type_display ||
              findOptionLabel("case_types", row.case_type)
            }}</template>
          </el-table-column>
          <el-table-column label="状态" width="105">
            <template #default="{ row }">
              <el-tag
                :type="lifecycleTagType(row.lifecycle_status)"
                effect="light"
              >
                {{
                  row.lifecycle_status_display ||
                  findOptionLabel("lifecycles", row.lifecycle_status)
                }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column label="数据影响" width="110">
            <template #default="{ row }">{{
              row.data_impact_display ||
              findOptionLabel("data_impacts", row.data_impact)
            }}</template>
          </el-table-column>
          <el-table-column label="标签" min-width="170">
            <template #default="{ row }">
              <el-tag
                v-for="tag in (row.tag_details || []).slice(0, 3)"
                :key="tag.id"
                class="tag-item"
                size="small"
                effect="plain"
              >
                {{ tag.name }}
              </el-tag>
              <span v-if="!row.tag_details || row.tag_details.length === 0"
                >-</span
              >
            </template>
          </el-table-column>
          <el-table-column label="维护人" width="110">
            <template #default="{ row }">{{
              row.maintainer_name || row.created_by_name || "-"
            }}</template>
          </el-table-column>
          <el-table-column label="最近结果" width="115">
            <template #default="{ row }">
              <el-tag
                :type="latestResultTagType(row.latest_execution)"
                size="small"
              >
                {{ row.latest_execution?.result_text || "未执行" }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column label="更新时间" width="155">
            <template #default="{ row }">{{
              formatDateTime(row.updated_at)
            }}</template>
          </el-table-column>
          <el-table-column label="操作" width="190" fixed="right">
            <template #default="{ row }">
              <el-button
                link
                type="success"
                size="small"
                :loading="precheckingDevice"
                @click.stop="runCase(row)"
              >
                运行
              </el-button>
              <el-button
                link
                type="primary"
                size="small"
                @click.stop="editCase(row)"
              >
                编辑
              </el-button>
              <el-button
                link
                type="info"
                size="small"
                @click.stop="openCaseDetail(row)"
              >
                详情
              </el-button>
              <el-button
                link
                type="danger"
                size="small"
                @click.stop="deleteCase(row)"
              >
                删除
              </el-button>
            </template>
          </el-table-column>
        </el-table>

        <el-pagination
          v-show="caseTotal > 0"
          v-model:current-page="caseCurrentPage"
          v-model:page-size="casePageSize"
          :page-sizes="[10, 20, 30, 50, 100]"
          :total="caseTotal"
          layout="total, sizes, prev, pager, next, jumper"
          class="pagination"
          @size-change="handleCaseSizeChange"
          @current-change="handleCasePageChange"
        />
      </div>
    </div>

    <el-card class="execution-card" shadow="never">
      <template #header>
        <div class="panel-header">
          <span>最近执行记录</span>
          <div>
            <el-button link type="primary" @click="refreshExecutions"
              >刷新</el-button
            >
            <el-button link type="primary" @click="viewAllExecutions"
              >查看全部</el-button
            >
          </div>
        </div>
      </template>

      <el-table
        v-loading="executionsLoading"
        :data="executionData.results"
        style="width: 100%"
      >
        <el-table-column prop="case_name" label="测试用例" min-width="220" />
        <el-table-column prop="device_name" label="设备" width="150" />
        <el-table-column prop="status" label="状态" width="100">
          <template #default="{ row }">
            <el-tag
              :type="getDisplayStatus(row.status, row.result).type"
              size="small"
            >
              {{ getDisplayStatus(row.status, row.result).text }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="执行进度" width="220">
          <template #default="{ row }">
            <div class="progress-wrapper">
              <el-progress
                :percentage="calculateProgress(row)"
                :status="getProgressStatus(row)"
                :stroke-width="8"
                :show-text="false"
                style="flex: 1"
              />
              <span class="progress-text">{{ calculateProgress(row) }}%</span>
            </div>
          </template>
        </el-table-column>
        <el-table-column prop="started_at" label="开始时间" width="165">
          <template #default="{ row }">{{
            formatDateTime(row.started_at)
          }}</template>
        </el-table-column>
        <el-table-column label="操作" width="170">
          <template #default="{ row }">
            <template
              v-if="row.status === 'completed' || row.status === 'error'"
            >
              <el-button
                link
                type="primary"
                size="small"
                @click="viewStandardReport(row)"
                >标准报告</el-button
              >
              <el-button
                v-if="row.report_path"
                link
                type="success"
                size="small"
                @click="viewAllureReport(row)"
                >Allure</el-button
              >
            </template>
            <el-button
              v-if="row.status === 'running'"
              link
              type="danger"
              size="small"
              @click="stopTest(row)"
            >
              停止
            </el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <el-drawer v-model="detailVisible" title="用例详情" size="420px">
      <template v-if="currentCase">
        <div class="detail-title">
          <h4>{{ currentCase.name }}</h4>
          <el-tag :type="lifecycleTagType(currentCase.lifecycle_status)">
            {{
              currentCase.lifecycle_status_display ||
              findOptionLabel("lifecycles", currentCase.lifecycle_status)
            }}
          </el-tag>
        </div>
        <el-descriptions :column="1" border size="small">
          <el-descriptions-item label="业务目录">{{
            currentCase.folder_name || "未分类"
          }}</el-descriptions-item>
          <el-descriptions-item label="优先级">{{
            currentCase.priority || "-"
          }}</el-descriptions-item>
          <el-descriptions-item label="用例类型">{{
            currentCase.case_type_display || "-"
          }}</el-descriptions-item>
          <el-descriptions-item label="数据影响">{{
            currentCase.data_impact_display || "-"
          }}</el-descriptions-item>
          <el-descriptions-item label="维护人">{{
            currentCase.maintainer_name || currentCase.created_by_name || "-"
          }}</el-descriptions-item>
          <el-descriptions-item label="来源">{{
            currentCase.source_display || "-"
          }}</el-descriptions-item>
          <el-descriptions-item label="自动化步骤"
            >{{ currentCase.step_count || 0 }} 步</el-descriptions-item
          >
          <el-descriptions-item label="所属测试集">
            {{
              currentCase.suite_names?.length
                ? currentCase.suite_names.join("、")
                : "-"
            }}
          </el-descriptions-item>
          <el-descriptions-item label="最近结果">
            {{ currentCase.latest_execution?.result_text || "未执行" }}
          </el-descriptions-item>
          <el-descriptions-item label="描述">
            {{ currentCase.description || "-" }}
          </el-descriptions-item>
        </el-descriptions>

        <div class="detail-tags">
          <el-tag
            v-for="tag in currentCase.tag_details || []"
            :key="tag.id"
            effect="plain"
          >
            {{ tag.name }}
          </el-tag>
          <span
            v-if="
              !currentCase.tag_details || currentCase.tag_details.length === 0
            "
            >暂无标签</span
          >
        </div>

        <div class="detail-actions">
          <el-button
            type="success"
            :loading="precheckingDevice"
            @click="runCase(currentCase)"
            >运行</el-button
          >
          <el-button type="primary" @click="editCase(currentCase)"
            >编辑</el-button
          >
          <el-button @click="markSingleCase(currentCase, 'maintenance')"
            >标记维护中</el-button
          >
          <el-button @click="markSingleCase(currentCase, 'deprecated')"
            >废弃</el-button
          >
        </div>
      </template>
    </el-drawer>

    <el-dialog
      v-model="folderDialogVisible"
      :title="folderDialogMode === 'create' ? '新建业务目录' : '重命名业务目录'"
      width="420px"
    >
      <el-form :model="folderForm" label-width="86px">
        <el-form-item label="所属项目" required>
          <el-select
            v-model="folderForm.project"
            placeholder="请选择项目"
            :disabled="folderDialogMode === 'rename'"
            filterable
            style="width: 100%"
          >
            <el-option
              v-for="proj in projectList"
              :key="proj.id"
              :label="proj.name"
              :value="proj.id"
            />
          </el-select>
        </el-form-item>
        <el-form-item v-if="folderDialogMode === 'create'" label="父目录">
          <el-select
            v-model="folderForm.parent"
            placeholder="根目录"
            clearable
            filterable
            style="width: 100%"
          >
            <el-option
              v-for="folder in folderOptions"
              :key="folder.id"
              :label="folder.label"
              :value="folder.id"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="目录名称" required>
          <el-input v-model="folderForm.name" maxlength="120" show-word-limit />
        </el-form-item>
        <el-form-item label="说明">
          <el-input
            v-model="folderForm.description"
            type="textarea"
            :rows="3"
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="folderDialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="folderSaving" @click="submitFolder"
          >保存</el-button
        >
      </template>
    </el-dialog>

    <el-dialog v-model="tagDialogVisible" title="受控标签" width="520px">
      <el-alert
        title="标签用于横向特征，业务归属请优先放到左侧目录。"
        type="info"
        show-icon
        :closable="false"
        class="dialog-tip"
      />
      <el-form :model="tagForm" label-width="86px">
        <el-form-item label="所属项目" required>
          <el-select
            v-model="tagForm.project"
            placeholder="请选择项目"
            filterable
            style="width: 100%"
          >
            <el-option
              v-for="proj in projectList"
              :key="proj.id"
              :label="proj.name"
              :value="proj.id"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="标签名称" required>
          <el-input
            v-model="tagForm.name"
            placeholder="例如：主链路、数据依赖"
            maxlength="80"
          />
        </el-form-item>
        <el-form-item label="颜色">
          <el-input v-model="tagForm.color" placeholder="可选，例如 #409eff" />
        </el-form-item>
        <el-form-item label="说明">
          <el-input v-model="tagForm.description" type="textarea" :rows="3" />
        </el-form-item>
      </el-form>
      <div class="tag-preview-list">
        <el-tag v-for="tag in tagList" :key="tag.id" effect="plain">
          {{ tag.name }}
          <span class="tag-count">({{ tag.usage_count || 0 }})</span>
        </el-tag>
      </div>
      <template #footer>
        <el-button @click="tagDialogVisible = false">关闭</el-button>
        <el-button type="primary" :loading="tagSaving" @click="submitTag"
          >新增标签</el-button
        >
      </template>
    </el-dialog>

    <el-dialog v-model="batchDialogVisible" title="批量治理用例" width="620px">
      <el-alert
        :title="`将处理 ${selectedCases.length} 条用例；不填写的字段不会变更。`"
        type="info"
        show-icon
        :closable="false"
        class="dialog-tip"
      />
      <el-form :model="batchForm" label-width="96px">
        <el-row :gutter="12">
          <el-col :span="12">
            <el-form-item label="移动目录">
              <el-select
                v-model="batchForm.folder"
                placeholder="不变更"
                clearable
                filterable
                style="width: 100%"
              >
                <el-option
                  v-for="folder in folderOptions"
                  :key="folder.id"
                  :label="folder.label"
                  :value="folder.id"
                />
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="维护人">
              <el-select
                v-model="batchForm.maintainer"
                placeholder="不变更"
                clearable
                filterable
                style="width: 100%"
              >
                <el-option
                  v-for="user in userList"
                  :key="user.id"
                  :label="user.username || user.name"
                  :value="user.id"
                />
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="优先级">
              <el-select
                v-model="batchForm.priority"
                placeholder="不变更"
                clearable
                style="width: 100%"
              >
                <el-option
                  v-for="item in options.priorities"
                  :key="item.value"
                  :label="item.label"
                  :value="item.value"
                />
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="用例类型">
              <el-select
                v-model="batchForm.case_type"
                placeholder="不变更"
                clearable
                style="width: 100%"
              >
                <el-option
                  v-for="item in options.case_types"
                  :key="item.value"
                  :label="item.label"
                  :value="item.value"
                />
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="生命周期">
              <el-select
                v-model="batchForm.lifecycle_status"
                placeholder="不变更"
                clearable
                style="width: 100%"
              >
                <el-option
                  v-for="item in options.lifecycles"
                  :key="item.value"
                  :label="item.label"
                  :value="item.value"
                />
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="数据影响">
              <el-select
                v-model="batchForm.data_impact"
                placeholder="不变更"
                clearable
                style="width: 100%"
              >
                <el-option
                  v-for="item in options.data_impacts"
                  :key="item.value"
                  :label="item.label"
                  :value="item.value"
                />
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="来源">
              <el-select
                v-model="batchForm.source"
                placeholder="不变更"
                clearable
                style="width: 100%"
              >
                <el-option
                  v-for="item in options.sources"
                  :key="item.value"
                  :label="item.label"
                  :value="item.value"
                />
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="加入套件">
              <el-select
                v-model="batchForm.suite_id"
                placeholder="不加入"
                clearable
                filterable
                style="width: 100%"
              >
                <el-option
                  v-for="suite in suiteList"
                  :key="suite.id"
                  :label="suite.name"
                  :value="suite.id"
                />
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :span="24">
            <el-form-item label="标签处理">
              <div class="tag-governance-row">
                <el-select v-model="batchForm.tag_mode" style="width: 120px">
                  <el-option label="替换" value="replace" />
                  <el-option label="追加" value="append" />
                  <el-option label="移除" value="remove" />
                </el-select>
                <el-select
                  v-model="batchForm.tag_ids"
                  placeholder="不处理标签"
                  clearable
                  multiple
                  collapse-tags
                  style="flex: 1"
                >
                  <el-option
                    v-for="tag in tagList"
                    :key="tag.id"
                    :label="tag.name"
                    :value="tag.id"
                  />
                </el-select>
              </div>
            </el-form-item>
          </el-col>
        </el-row>
      </el-form>
      <template #footer>
        <el-button @click="batchDialogVisible = false">取消</el-button>
        <el-button
          type="primary"
          :loading="batchSaving"
          @click="submitBatchGovernance"
          >保存治理结果</el-button
        >
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
import { computed, nextTick, onBeforeUnmount, onMounted, ref } from "vue";
import { useRouter } from "vue-router";
import { ElMessage, ElMessageBox } from "element-plus";
import { FolderAdd, Refresh, Search } from "@element-plus/icons-vue";
import StandardExecutionReportDialog from "../reports/components/StandardExecutionReportDialog.vue";
import {
  batchUpdateTestCaseGovernance,
  createTestCaseFolder,
  createTestCaseTag,
  deleteTestCase as apiDeleteTestCase,
  deleteTestCaseFolder,
  executeTestCase as apiExecuteTestCase,
  getAppProjects,
  getAuthUsers,
  getDeviceList,
  getExecutionDetail,
  getExecutionList,
  getExecutionReportSummary,
  getPackageList,
  getTestCaseFolderTree,
  getTestCaseGovernanceOptions,
  getTestCaseList,
  getTestCaseTags,
  getTestSuiteList,
  getWsStatus,
  healthCheckDevice,
  stopExecution as apiStopExecution,
  updateTestCaseFolder,
} from "@/api/app-automation";
import {
  getDisplayStatus,
  formatDateTime,
} from "@/utils/app-automation-helpers";

const router = useRouter();

const loading = ref(false);
const devicesLoading = ref(false);
const executionsLoading = ref(false);
const precheckingDevice = ref(false);
const folderSaving = ref(false);
const tagSaving = ref(false);
const batchSaving = ref(false);

const projectList = ref([]);
const availableDevices = ref([]);
const appPackages = ref([]);
const folderTree = ref([]);
const tagList = ref([]);
const userList = ref([]);
const suiteList = ref([]);

const form = ref({
  projectId: null,
  deviceId: null,
  packageId: null,
});

const filters = ref({
  q: "",
  priority: "",
  case_type: "",
  lifecycle_status: "",
  data_impact: "",
  latest_result: "",
  tagIds: [],
  includeDeprecated: false,
});

const options = ref({
  case_types: [],
  priorities: [],
  lifecycles: [],
  data_impacts: [],
  sources: [],
});

const testCases = ref([]);
const caseCurrentPage = ref(1);
const casePageSize = ref(20);
const caseTotal = ref(0);
const tableRef = ref(null);
const folderTreeRef = ref(null);
const selectedCases = ref([]);
const selectedFolderKey = ref("all");
const selectedFolder = ref({
  synthetic: true,
  id: null,
  treeKey: "all",
  name: "全部用例",
});

const executionData = ref({ count: 0, results: [] });
const websockets = ref({});
const lastStatusMessages = ref({});
const wsDisabled = ref(false);
const pollingTimers = ref({});
const wsRetryCount = ref({});
const WS_MAX_RETRY = 3;
let refreshTimer = null;

const detailVisible = ref(false);
const currentCase = ref(null);
const reportDialogVisible = ref(false);
const reportSummaryLoading = ref(false);
const currentReportSummary = ref(null);
const currentReportExecution = ref(null);

const folderDialogVisible = ref(false);
const folderDialogMode = ref("create");
const editingFolderId = ref(null);
const folderForm = ref({
  project: null,
  parent: null,
  name: "",
  description: "",
});

const tagDialogVisible = ref(false);
const tagForm = ref({ project: null, name: "", color: "", description: "" });

const batchDialogVisible = ref(false);
const batchForm = ref({
  folder: null,
  maintainer: null,
  priority: "",
  case_type: "",
  lifecycle_status: "",
  data_impact: "",
  source: "",
  suite_id: null,
  tag_mode: "replace",
  tag_ids: [],
});

const folderTreeProps = {
  label: "name",
  children: "children",
};

const normalizeList = (data) => {
  if (data?.success !== undefined) {
    return data.data?.results || data.data || [];
  }
  return data?.results || data || [];
};

const normalizeCount = (data) => {
  if (data?.success !== undefined) {
    return data.data?.count || 0;
  }
  return data?.count || 0;
};

const withTreeKeys = (nodes) => {
  return (nodes || []).map((node) => ({
    ...node,
    treeKey: String(node.id),
    children: withTreeKeys(node.children || []),
  }));
};

const sumFolderCases = (nodes) => {
  return (nodes || []).reduce((total, node) => {
    return (
      total + Number(node.case_count || 0) + sumFolderCases(node.children || [])
    );
  }, 0);
};

const folderTreeData = computed(() => [
  {
    synthetic: true,
    id: null,
    treeKey: "all",
    name: "全部用例",
    case_count: sumFolderCases(folderTree.value),
    children: [],
  },
  ...folderTree.value,
]);

const flattenFolders = (nodes, prefix = "") => {
  return (nodes || []).flatMap((node) => {
    const label = `${prefix}${node.name}`;
    return [
      { id: node.id, label, project: node.project, level: node.level },
      ...flattenFolders(node.children || [], `${prefix}${node.name} / `),
    ];
  });
};

const folderOptions = computed(() => flattenFolders(folderTree.value));

const selectedFolderId = computed(() =>
  selectedFolder.value?.synthetic ? null : selectedFolder.value?.id,
);

const loadProjectList = async () => {
  try {
    const res = await getAppProjects({ page_size: 100 });
    projectList.value = normalizeList(res.data);
  } catch {
    projectList.value = [];
  }
};

const loadUsers = async () => {
  try {
    const res = await getAuthUsers({ page_size: 300 });
    userList.value = normalizeList(res.data);
  } catch {
    userList.value = [];
  }
};

const loadGovernanceOptions = async () => {
  try {
    const res = await getTestCaseGovernanceOptions();
    options.value = res.data?.data || options.value;
  } catch (error) {
    console.error("加载治理选项失败:", error);
  }
};

const loadDevices = async () => {
  devicesLoading.value = true;
  try {
    const res = await getDeviceList({ page_size: 100 });
    availableDevices.value = normalizeList(res.data);
  } catch {
    availableDevices.value = [];
  } finally {
    devicesLoading.value = false;
  }
};

const loadPackages = async () => {
  try {
    const res = await getPackageList({ page_size: 200 });
    appPackages.value = normalizeList(res.data);
  } catch {
    appPackages.value = [];
  }
};

const loadFolders = async () => {
  try {
    const params = {};
    if (form.value.projectId) params.project = form.value.projectId;
    const res = await getTestCaseFolderTree(params);
    folderTree.value = withTreeKeys(res.data?.data || []);
    await nextTick();
    folderTreeRef.value?.setCurrentKey(selectedFolderKey.value);
  } catch {
    folderTree.value = [];
  }
};

const loadTags = async () => {
  try {
    const params = { is_active: true };
    if (form.value.projectId) params.project = form.value.projectId;
    const res = await getTestCaseTags(params);
    tagList.value = normalizeList(res.data);
  } catch {
    tagList.value = [];
  }
};

const loadSuites = async () => {
  try {
    const params = { page_size: 200 };
    if (form.value.projectId) params.project = form.value.projectId;
    const res = await getTestSuiteList(params);
    suiteList.value = normalizeList(res.data);
  } catch {
    suiteList.value = [];
  }
};

const loadTestCases = async () => {
  loading.value = true;
  try {
    const params = {
      page: caseCurrentPage.value,
      page_size: casePageSize.value,
    };
    if (form.value.projectId) params.project = form.value.projectId;
    if (form.value.packageId) params.app_package = form.value.packageId;
    if (selectedFolderId.value) params.folder = selectedFolderId.value;
    if (filters.value.q) {
      params.q = filters.value.q;
      params.search = filters.value.q;
    }
    if (filters.value.priority) params.priority = filters.value.priority;
    if (filters.value.case_type) params.case_type = filters.value.case_type;
    if (filters.value.lifecycle_status)
      params.lifecycle_status = filters.value.lifecycle_status;
    if (filters.value.data_impact)
      params.data_impact = filters.value.data_impact;
    if (filters.value.latest_result)
      params.latest_result = filters.value.latest_result;
    if (filters.value.tagIds?.length)
      params.tags = filters.value.tagIds.join(",");
    if (filters.value.includeDeprecated) params.include_deprecated = 1;

    const res = await getTestCaseList(params);
    testCases.value = normalizeList(res.data);
    caseTotal.value = normalizeCount(res.data);
  } catch (error) {
    console.error("加载测试用例失败:", error);
    testCases.value = [];
    caseTotal.value = 0;
  } finally {
    loading.value = false;
  }
};

const reloadCases = () => {
  caseCurrentPage.value = 1;
  loadTestCases();
};

const refreshAll = async () => {
  await Promise.all([
    loadFolders(),
    loadTags(),
    loadSuites(),
    loadTestCases(),
    loadExecutions(),
  ]);
};

const handleProjectChange = async () => {
  selectedFolderKey.value = "all";
  selectedFolder.value = {
    synthetic: true,
    id: null,
    treeKey: "all",
    name: "全部用例",
  };
  filters.value.tagIds = [];
  await Promise.all([loadFolders(), loadTags(), loadSuites()]);
  reloadCases();
};

const handleFolderClick = (node) => {
  selectedFolder.value = node;
  selectedFolderKey.value = node.treeKey;
  reloadCases();
};

const resetFilters = () => {
  filters.value = {
    q: "",
    priority: "",
    case_type: "",
    lifecycle_status: "",
    data_impact: "",
    latest_result: "",
    tagIds: [],
    includeDeprecated: false,
  };
  reloadCases();
};

const findOptionLabel = (group, value) => {
  return (
    options.value[group]?.find((item) => item.value === value)?.label ||
    value ||
    "-"
  );
};

const priorityTagType = (priority) => {
  return (
    { P0: "danger", P1: "warning", P2: "primary", P3: "info" }[priority] ||
    "info"
  );
};

const lifecycleTagType = (status) => {
  return (
    {
      active: "success",
      draft: "info",
      maintenance: "warning",
      deprecated: "danger",
    }[status] || "info"
  );
};

const latestResultTagType = (execution = {}) => {
  if (execution.result === "passed") return "success";
  if (execution.result === "failed" || execution.status === "error")
    return "danger";
  if (execution.status === "running" || execution.status === "pending")
    return "warning";
  return "info";
};

const loadExecutions = async () => {
  executionsLoading.value = true;
  try {
    const res = await getExecutionList({
      page: 1,
      page_size: 5,
      ordering: "-start_time",
    });
    executionData.value = {
      count: normalizeCount(res.data),
      results: normalizeList(res.data),
    };
    executionData.value.results.forEach((execution) => {
      if (
        (execution.status === "pending" || execution.status === "running") &&
        execution.id
      ) {
        trackExecution(execution.id);
      }
    });
  } catch {
    executionData.value = { count: 0, results: [] };
  } finally {
    executionsLoading.value = false;
  }
};

const refreshExecutions = () => {
  loadExecutions();
};

const viewAllExecutions = () => {
  router.push({ path: "/app-automation/executions" });
};

const viewStandardReport = async (execution) => {
  if (!execution?.id) {
    ElMessage.warning("执行记录 ID 无效");
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

const stopTest = async (execution) => {
  try {
    await ElMessageBox.confirm("确定要停止这个测试吗？", "确认停止", {
      confirmButtonText: "确定",
      cancelButtonText: "取消",
      type: "warning",
    });
    const res = await apiStopExecution(execution.id);
    if (res.data.success) {
      ElMessage.success("已停止执行");
      loadExecutions();
    } else {
      ElMessage.error(res.data.message || "停止失败");
    }
  } catch (error) {
    if (error !== "cancel") {
      ElMessage.error(error?.userMessage || "停止失败");
    }
  }
};

const getSelectedDevice = () => {
  return availableDevices.value.find((d) => d.id === form.value.deviceId);
};

const buildExecutionParams = () => {
  const selectedDevice = getSelectedDevice();
  const params = { device_id: selectedDevice?.device_id };
  if (form.value.packageId) {
    const selectedPackage = appPackages.value.find(
      (pkg) => pkg.id === form.value.packageId,
    );
    if (selectedPackage) params.package_name = selectedPackage.package_name;
  }
  return params;
};

const precheckSelectedDevice = async () => {
  const selectedDevice = getSelectedDevice();
  if (!selectedDevice) {
    ElMessage.warning("请先选择设备");
    return false;
  }

  precheckingDevice.value = true;
  try {
    const res = await healthCheckDevice(selectedDevice.id);
    const result = res.data?.data;
    if (!result) {
      ElMessage.warning("设备预检未返回结果，请稍后重试");
      return false;
    }
    if (result.verdict === "executable") return true;

    const suggestions = (result.suggestions || []).slice(0, 3).join("\n");
    const message = [
      `设备当前状态：${result.verdict_text || "需处理"}，评分 ${result.score || 0} 分。`,
      suggestions ? `处理建议：\n${suggestions}` : "",
      result.verdict === "unavailable"
        ? "该设备当前不可执行，请先处理设备问题。"
        : "是否仍要继续提交执行？",
    ]
      .filter(Boolean)
      .join("\n\n");

    if (result.verdict === "unavailable") {
      await ElMessageBox.alert(message, "执行前预检未通过", {
        confirmButtonText: "知道了",
        type: "error",
      });
      return false;
    }

    await ElMessageBox.confirm(message, "执行前预检提醒", {
      confirmButtonText: "继续执行",
      cancelButtonText: "先去处理",
      type: "warning",
    });
    return true;
  } catch (error) {
    ElMessage.error(error?.userMessage || "设备预检失败，请检查设备连接");
    return false;
  } finally {
    precheckingDevice.value = false;
  }
};

const runCase = async (testCase) => {
  if (!form.value.deviceId) {
    ElMessage.warning("请先选择设备");
    return;
  }

  try {
    const canRun = await precheckSelectedDevice();
    if (!canRun) return;
    const res = await apiExecuteTestCase(testCase.id, buildExecutionParams());
    const data = res.data;
    if (data.success || data.execution_id) {
      ElMessage.success("测试已提交执行");
      const executionId = data.execution?.id || data.execution_id;
      if (executionId) {
        trackExecution(executionId);
        checkExecutionStatus(executionId);
      }
      setTimeout(() => loadExecutions(), 1000);
    } else {
      ElMessage.error(`执行失败: ${data.message || "未知错误"}`);
    }
  } catch (error) {
    ElMessage.error(
      error?.userMessage || `执行失败: ${error.message || "未知错误"}`,
    );
  }
};

const checkExecutionStatus = (executionId) => {
  setTimeout(async () => {
    try {
      const res = await getExecutionDetail(executionId);
      const status = res.data.status || res.data.data?.status;
      if (status === "pending") {
        ElMessage.warning("任务未开始，请确认 Celery worker/Redis 已启动");
      }
    } catch (error) {
      console.error("检查执行状态失败:", error);
    }
  }, 3000);
};

const createCase = () => {
  const query = {};
  if (form.value.projectId) query.project_id = form.value.projectId;
  if (selectedFolderId.value) query.folder_id = selectedFolderId.value;
  router.push({ path: "/app-automation/scene-builder", query });
};

const editCase = (testCase) => {
  router.push({
    path: "/app-automation/scene-builder",
    query: { case_id: testCase.id },
  });
};

const deleteCase = async (testCase) => {
  try {
    await ElMessageBox.confirm(
      `确定要删除测试用例「${testCase.name}」吗？`,
      "确认删除",
      {
        confirmButtonText: "确定",
        cancelButtonText: "取消",
        type: "warning",
      },
    );
    await apiDeleteTestCase(testCase.id);
    ElMessage.success("删除成功");
    loadTestCases();
    loadFolders();
  } catch (error) {
    if (error !== "cancel") ElMessage.error(error?.userMessage || "删除失败");
  }
};

const openCaseDetail = (row) => {
  currentCase.value = row;
  detailVisible.value = true;
};

const markSingleCase = async (testCase, lifecycleStatus) => {
  try {
    await batchUpdateTestCaseGovernance({
      case_ids: [testCase.id],
      lifecycle_status: lifecycleStatus,
    });
    ElMessage.success("状态已更新");
    await loadTestCases();
    const latest = testCases.value.find((item) => item.id === testCase.id);
    if (latest) currentCase.value = latest;
  } catch (error) {
    ElMessage.error(error?.userMessage || "状态更新失败");
  }
};

const updateExecutionData = (updates) => {
  if (!updates || !updates.execution_id) return;
  const target = executionData.value.results.find(
    (item) => item.id === updates.execution_id,
  );
  if (!target) {
    loadExecutions();
    return;
  }
  if (updates.status) target.status = updates.status;
  if (updates.result !== undefined) target.result = updates.result;
  if (updates.progress !== null && updates.progress !== undefined)
    target.progress = updates.progress;
  if (updates.report_path !== undefined)
    target.report_path = updates.report_path;
  if (updates.finished_at) target.finished_at = updates.finished_at;
};

const startPolling = (executionId) => {
  if (pollingTimers.value[executionId]) return;
  pollingTimers.value[executionId] = setInterval(async () => {
    try {
      const res = await getExecutionDetail(executionId);
      if (res.data) {
        updateExecutionData({
          execution_id: res.data.id,
          status: res.data.status,
          result: res.data.result,
          progress: res.data.progress,
          report_path: res.data.report_path,
          finished_at: res.data.finished_at,
        });
        if (["completed", "error", "stopped"].includes(res.data.status)) {
          stopPolling(executionId);
          loadTestCases();
        }
      }
    } catch (error) {
      console.error("轮询执行状态失败:", error);
    }
  }, 3000);
};

const stopPolling = (executionId) => {
  if (pollingTimers.value[executionId]) {
    clearInterval(pollingTimers.value[executionId]);
    delete pollingTimers.value[executionId];
  }
};

const stopAllPolling = () => {
  Object.keys(pollingTimers.value).forEach((id) => stopPolling(id));
};

const connectWebSocket = (executionId) => {
  if (websockets.value[executionId]) return;
  const protocol = window.location.protocol === "https:" ? "wss" : "ws";
  const wsUrl = `${protocol}://${window.location.host}/ws/app-automation/executions/${executionId}/`;
  const ws = new WebSocket(wsUrl);
  websockets.value[executionId] = ws;

  ws.onopen = () => {
    wsRetryCount.value[executionId] = 0;
  };

  ws.onmessage = (event) => {
    try {
      const data = JSON.parse(event.data);
      updateExecutionData(data);
      if (
        data.status &&
        lastStatusMessages.value[executionId] !== data.status
      ) {
        lastStatusMessages.value[executionId] = data.status;
        if (data.result === "passed") ElMessage.success("测试执行通过");
        else if (data.result === "failed") ElMessage.error("测试用例失败");
        else if (data.status === "error") ElMessage.error("执行异常");
      }
      if (["completed", "error", "stopped"].includes(data.status)) {
        closeWebSocket(executionId);
        loadTestCases();
      }
    } catch (error) {
      console.error("处理 WebSocket 消息失败:", error);
    }
  };

  ws.onclose = () => {
    delete websockets.value[executionId];
  };

  ws.onerror = () => {
    closeWebSocket(executionId);
    const retries = (wsRetryCount.value[executionId] || 0) + 1;
    wsRetryCount.value[executionId] = retries;
    if (retries <= WS_MAX_RETRY) {
      setTimeout(() => {
        const target = executionData.value.results.find(
          (e) => e.id === executionId,
        );
        if (target && ["pending", "running"].includes(target.status))
          connectWebSocket(executionId);
      }, retries * 1000);
    } else {
      delete wsRetryCount.value[executionId];
      startPolling(executionId);
    }
  };
};

const trackExecution = (executionId) => {
  if (wsDisabled.value) startPolling(executionId);
  else connectWebSocket(executionId);
};

const closeWebSocket = (executionId) => {
  const ws = websockets.value[executionId];
  if (ws) {
    ws.close();
    delete websockets.value[executionId];
  }
};

const closeAllWebSockets = () => {
  Object.keys(websockets.value).forEach((id) => closeWebSocket(id));
};

const handleSelectionChange = (selection) => {
  selectedCases.value = selection;
};

const clearSelection = () => {
  tableRef.value?.clearSelection();
  selectedCases.value = [];
};

const batchRun = async () => {
  if (!form.value.deviceId) {
    ElMessage.warning("请先选择设备");
    return;
  }
  if (selectedCases.value.length === 0) {
    ElMessage.warning("请至少选择一个用例");
    return;
  }

  try {
    const canRun = await precheckSelectedDevice();
    if (!canRun) return;
    await ElMessageBox.confirm(
      `确定要批量执行选中的 ${selectedCases.value.length} 个用例吗？`,
      "确认批量执行",
      {
        confirmButtonText: "执行",
        cancelButtonText: "取消",
        type: "info",
      },
    );
    const baseParams = buildExecutionParams();
    let submitted = 0;
    for (const testCase of selectedCases.value) {
      try {
        await apiExecuteTestCase(testCase.id, { ...baseParams });
        submitted += 1;
      } catch (error) {
        console.error(`执行用例 ${testCase.name} 失败:`, error);
      }
    }
    ElMessage.success(`已提交 ${submitted} 个用例执行`);
    clearSelection();
    setTimeout(() => loadExecutions(), 1500);
  } catch (error) {
    if (error !== "cancel")
      ElMessage.error(error?.userMessage || "批量执行失败");
  }
};

const openFolderDialog = (mode) => {
  if (mode === "create" && !form.value.projectId) {
    ElMessage.warning("请先选择项目，再创建业务目录");
    return;
  }
  folderDialogMode.value = mode;
  if (mode === "rename") {
    if (!selectedFolder.value || selectedFolder.value.synthetic) return;
    editingFolderId.value = selectedFolder.value.id;
    folderForm.value = {
      project: selectedFolder.value.project,
      parent: selectedFolder.value.parent,
      name: selectedFolder.value.name,
      description: selectedFolder.value.description || "",
    };
  } else {
    editingFolderId.value = null;
    folderForm.value = {
      project: form.value.projectId,
      parent: selectedFolderId.value,
      name: "",
      description: "",
    };
  }
  folderDialogVisible.value = true;
};

const submitFolder = async () => {
  if (!folderForm.value.project || !folderForm.value.name?.trim()) {
    ElMessage.warning("请填写项目和目录名称");
    return;
  }
  folderSaving.value = true;
  try {
    const payload = {
      project: folderForm.value.project,
      parent: folderForm.value.parent || null,
      name: folderForm.value.name.trim(),
      description: folderForm.value.description || "",
    };
    if (folderDialogMode.value === "rename") {
      await updateTestCaseFolder(editingFolderId.value, payload);
    } else {
      await createTestCaseFolder(payload);
    }
    ElMessage.success("目录已保存");
    folderDialogVisible.value = false;
    await loadFolders();
  } catch (error) {
    ElMessage.error(error?.userMessage || "目录保存失败");
  } finally {
    folderSaving.value = false;
  }
};

const removeFolder = async () => {
  if (!selectedFolder.value || selectedFolder.value.synthetic) return;
  try {
    await ElMessageBox.confirm(
      `确定删除目录「${selectedFolder.value.name}」吗？非空目录不能删除。`,
      "删除目录",
      {
        confirmButtonText: "删除",
        cancelButtonText: "取消",
        type: "warning",
      },
    );
    await deleteTestCaseFolder(selectedFolder.value.id);
    ElMessage.success("目录已删除");
    selectedFolderKey.value = "all";
    selectedFolder.value = {
      synthetic: true,
      id: null,
      treeKey: "all",
      name: "全部用例",
    };
    await loadFolders();
    reloadCases();
  } catch (error) {
    if (error !== "cancel")
      ElMessage.error(error?.userMessage || "目录删除失败");
  }
};

const openTagDialog = () => {
  if (!form.value.projectId) {
    ElMessage.warning("请先选择项目，再维护标签");
    return;
  }
  tagForm.value = {
    project: form.value.projectId,
    name: "",
    color: "",
    description: "",
  };
  tagDialogVisible.value = true;
};

const submitTag = async () => {
  if (!tagForm.value.project || !tagForm.value.name?.trim()) {
    ElMessage.warning("请填写项目和标签名称");
    return;
  }
  tagSaving.value = true;
  try {
    await createTestCaseTag({
      project: tagForm.value.project,
      name: tagForm.value.name.trim(),
      color: tagForm.value.color || "",
      description: tagForm.value.description || "",
    });
    ElMessage.success("标签已新增");
    tagForm.value.name = "";
    tagForm.value.color = "";
    tagForm.value.description = "";
    await loadTags();
  } catch (error) {
    ElMessage.error(error?.userMessage || "标签新增失败");
  } finally {
    tagSaving.value = false;
  }
};

const openBatchGovernance = () => {
  batchForm.value = {
    folder: null,
    maintainer: null,
    priority: "",
    case_type: "",
    lifecycle_status: "",
    data_impact: "",
    source: "",
    suite_id: null,
    tag_mode: "replace",
    tag_ids: [],
  };
  batchDialogVisible.value = true;
};

const submitBatchGovernance = async () => {
  const payload = { case_ids: selectedCases.value.map((item) => item.id) };
  [
    "folder",
    "maintainer",
    "priority",
    "case_type",
    "lifecycle_status",
    "data_impact",
    "source",
  ].forEach((field) => {
    if (batchForm.value[field] !== null && batchForm.value[field] !== "") {
      payload[field] = batchForm.value[field];
    }
  });
  if (batchForm.value.suite_id) payload.suite_id = batchForm.value.suite_id;
  if (batchForm.value.tag_ids?.length) {
    payload.tag_ids = batchForm.value.tag_ids;
    payload.tag_mode = batchForm.value.tag_mode;
  }

  if (Object.keys(payload).length <= 1) {
    ElMessage.warning("请至少选择一个需要变更的治理项");
    return;
  }

  batchSaving.value = true;
  try {
    const res = await batchUpdateTestCaseGovernance(payload);
    ElMessage.success(res.data?.message || "批量治理完成");
    batchDialogVisible.value = false;
    clearSelection();
    await Promise.all([
      loadTestCases(),
      loadFolders(),
      loadTags(),
      loadSuites(),
    ]);
  } catch (error) {
    ElMessage.error(error?.userMessage || "批量治理失败");
  } finally {
    batchSaving.value = false;
  }
};

const handleCaseSizeChange = () => {
  caseCurrentPage.value = 1;
  loadTestCases();
};

const handleCasePageChange = () => {
  loadTestCases();
};

const calculateProgress = (execution) => {
  if (execution.status === "completed") return 100;
  if (execution.status === "error" || execution.status === "stopped")
    return execution.progress || 0;
  if (execution.status === "running") return execution.progress || 0;
  return 0;
};

const getProgressStatus = (row) => {
  if (row.status === "completed")
    return row.result === "failed" ? "exception" : "success";
  if (row.status === "error") return "exception";
  return undefined;
};

onMounted(async () => {
  try {
    const res = await getWsStatus();
    wsDisabled.value = !res.data?.websocket;
  } catch {
    wsDisabled.value = true;
  }

  await Promise.all([
    loadProjectList(),
    loadUsers(),
    loadDevices(),
    loadPackages(),
    loadGovernanceOptions(),
  ]);
  await Promise.all([
    loadFolders(),
    loadTags(),
    loadSuites(),
    loadTestCases(),
    loadExecutions(),
  ]);

  if (!wsDisabled.value) {
    refreshTimer = setInterval(() => {
      const hasRunning = executionData.value.results.some(
        (e) => e.status === "running",
      );
      if (hasRunning) loadExecutions();
    }, 10000);
  }
});

onBeforeUnmount(() => {
  if (refreshTimer) clearInterval(refreshTimer);
  closeAllWebSockets();
  stopAllPolling();
});
</script>

<style scoped lang="scss">
.case-library-page {
  padding: 0;
}

.page-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 14px;
  padding: 18px 20px;
  background: linear-gradient(135deg, #f7fbff 0%, #ffffff 55%, #f6f8fb 100%);
  border: 1px solid #e8edf5;
  border-radius: 10px;

  h3 {
    margin: 0;
    font-size: 20px;
    color: #1f2d3d;
  }

  p {
    margin: 6px 0 0;
    color: #6b7280;
    font-size: 13px;
  }

  .header-actions {
    display: flex;
    gap: 10px;
  }
}

.context-card {
  margin-bottom: 14px;

  :deep(.el-card__body) {
    padding: 16px 18px 2px;
  }
}

.library-workbench {
  display: grid;
  grid-template-columns: 260px minmax(0, 1fr);
  gap: 14px;
  align-items: start;
}

.folder-panel,
.filter-card,
.execution-card {
  border-radius: 10px;
  border-color: #e8edf5;
}

.folder-panel {
  position: sticky;
  top: 12px;

  :deep(.el-card__body) {
    padding: 12px;
  }
}

.panel-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-weight: 600;
}

.folder-tree {
  max-height: 580px;
  overflow: auto;
}

.folder-node {
  display: flex;
  justify-content: space-between;
  align-items: center;
  width: 100%;
  padding-right: 8px;
}

.folder-actions {
  display: flex;
  gap: 8px;
  padding-top: 12px;
  margin-top: 12px;
  border-top: 1px solid #edf0f5;
}

.case-main {
  min-width: 0;
}

.filter-card {
  margin-bottom: 12px;

  :deep(.el-card__body) {
    padding: 14px;
  }
}

.filter-row {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  align-items: center;

  .el-select {
    width: 138px;
  }
}

.batch-bar {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 14px;
  margin-bottom: 12px;
  background: #f0f7ff;
  border: 1px solid #c8e1ff;
  border-radius: 8px;

  strong {
    color: #1677ff;
  }
}

.case-table {
  width: 100%;
  border-radius: 10px;

  :deep(th.el-table__cell) {
    background: #f7f9fc;
    color: #4b5563;
  }
}

.case-name {
  display: flex;
  flex-direction: column;
  gap: 4px;
  line-height: 1.35;
}

.case-meta {
  display: flex;
  gap: 10px;
  color: #8a94a6;
  font-size: 12px;
}

.tag-item {
  margin-right: 5px;
  margin-bottom: 4px;
}

.pagination {
  margin-top: 14px;
  justify-content: flex-end;
}

.execution-card {
  margin-top: 16px;
}

.progress-wrapper {
  display: flex;
  align-items: center;
  gap: 10px;

  .progress-text {
    width: 40px;
    text-align: right;
    font-size: 12px;
    color: #6b7280;
  }
}

.detail-title {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 14px;

  h4 {
    margin: 0;
    line-height: 1.45;
  }
}

.detail-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin: 16px 0;
  color: #909399;
}

.detail-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  padding-top: 12px;
  border-top: 1px solid #edf0f5;
}

.dialog-tip {
  margin-bottom: 14px;
}

.tag-preview-list {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  padding: 10px;
  background: #f8fafc;
  border-radius: 8px;
}

.tag-count {
  color: #909399;
}

.tag-governance-row {
  display: flex;
  gap: 8px;
  width: 100%;
}

@media screen and (max-width: 1200px) {
  .library-workbench {
    grid-template-columns: 1fr;
  }

  .folder-panel {
    position: static;
  }
}
</style>
