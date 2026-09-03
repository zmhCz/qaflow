<template>
  <div class="page-container">
    <div class="page-header">
      <h1 class="page-title">
        {{ isEdit ? $t("reviewForm.editTitle") : $t("reviewForm.createTitle") }}
      </h1>
      <div>
        <el-button @click="$router.back()">{{
          $t("reviewForm.back")
        }}</el-button>
        <el-button type="primary" @click="saveReview" :loading="saving">{{
          $t("reviewForm.save")
        }}</el-button>
      </div>
    </div>

    <div class="form-container">
      <el-form :model="form" :rules="rules" ref="formRef" label-width="120px">
        <el-row :gutter="24">
          <el-col :span="12">
            <el-form-item :label="$t('reviewForm.reviewTitle')" prop="title">
              <el-input
                v-model="form.title"
                :placeholder="$t('reviewForm.reviewTitlePlaceholder')"
              />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item
              :label="$t('reviewForm.associatedProject')"
              prop="projects"
            >
              <el-select
                v-model="form.projects"
                multiple
                :placeholder="$t('reviewForm.selectProject')"
                @change="onProjectChange"
              >
                <el-option
                  v-for="project in projects"
                  :key="project.id"
                  :label="project.name"
                  :value="project.id"
                />
              </el-select>
            </el-form-item>
          </el-col>
        </el-row>

        <el-row :gutter="24">
          <el-col :span="12">
            <el-form-item :label="$t('reviewForm.priority')" prop="priority">
              <el-select
                v-model="form.priority"
                :placeholder="$t('reviewForm.selectPriority')"
              >
                <el-option :label="$t('reviewForm.priorityLow')" value="low" />
                <el-option
                  :label="$t('reviewForm.priorityMedium')"
                  value="medium"
                />
                <el-option
                  :label="$t('reviewForm.priorityHigh')"
                  value="high"
                />
                <el-option
                  :label="$t('reviewForm.priorityUrgent')"
                  value="urgent"
                />
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item :label="$t('reviewForm.deadline')">
              <el-date-picker
                v-model="form.deadline"
                type="datetime"
                :placeholder="$t('reviewForm.deadlinePlaceholder')"
                format="YYYY-MM-DD HH:mm"
                value-format="YYYY-MM-DD HH:mm:ss"
              />
            </el-form-item>
          </el-col>
        </el-row>

        <el-form-item :label="$t('reviewForm.description')">
          <el-input
            v-model="form.description"
            type="textarea"
            :rows="4"
            :placeholder="$t('reviewForm.descriptionPlaceholder')"
          />
        </el-form-item>

        <el-form-item
          :label="$t('reviewForm.selectTestcases')"
          prop="testcases"
        >
          <div class="testcase-selector">
            <div class="search-bar">
              <el-input
                v-model="testcaseSearch"
                :placeholder="$t('reviewForm.searchTestcases')"
                @input="searchTestcases"
                clearable
              >
                <template #prefix>
                  <el-icon><Search /></el-icon>
                </template>
              </el-input>
              <el-button type="primary" @click="showTestcaseSelector">{{
                $t("reviewForm.selectTestcasesBtn")
              }}</el-button>
            </div>

            <div class="selected-testcases">
              <el-tag
                v-for="testcase in selectedTestcases"
                :key="testcase.id"
                closable
                @close="removeTestcase(testcase.id)"
                class="testcase-tag"
              >
                {{ testcase.title }}
              </el-tag>
              <div v-if="selectedTestcases.length === 0" class="empty-tip">
                {{ $t("reviewForm.emptyTestcasesTip") }}
              </div>
            </div>
          </div>
        </el-form-item>

        <el-form-item :label="$t('reviewForm.reviewers')" prop="reviewers">
          <el-select
            v-model="form.reviewers"
            multiple
            :placeholder="$t('reviewForm.selectReviewers')"
            @change="onReviewersChange"
          >
            <el-option
              v-for="user in projectUsers"
              :key="user.id"
              :label="user.username"
              :value="user.id"
            />
          </el-select>
        </el-form-item>

        <el-form-item :label="$t('reviewForm.reviewTemplate')">
          <el-select
            v-model="form.template"
            :placeholder="$t('reviewForm.selectTemplate')"
            @change="applyTemplate"
          >
            <el-option
              v-for="template in templates"
              :key="template.id"
              :label="template.name"
              :value="template.id"
            />
          </el-select>
        </el-form-item>
      </el-form>
    </div>

    <!-- 用例选择对话框 -->
    <el-dialog
      v-model="testcaseSelectorVisible"
      :title="$t('reviewForm.testcaseSelectorTitle')"
      :close-on-click-modal="false"
      width="920px"
    >
      <div class="testcase-selector-content">
        <div class="testcase-filter-bar">
          <el-select
            v-model="testcaseDialogFilters.projectIds"
            multiple
            collapse-tags
            collapse-tags-tooltip
            :placeholder="$t('reviewForm.filterProject')"
            @change="onDialogProjectFilterChange"
          >
            <el-option
              v-for="project in selectedProjectOptions"
              :key="project.id"
              :label="project.name"
              :value="project.id"
            />
          </el-select>
          <el-select
            v-model="testcaseDialogFilters.versionId"
            clearable
            :placeholder="$t('reviewForm.filterVersion')"
            @change="refreshDialogTestcases"
          >
            <el-option
              v-for="version in testcaseVersions"
              :key="version.id"
              :label="version.name"
              :value="version.id"
            />
          </el-select>
          <el-input
            v-model="testcaseSearchInDialog"
            :placeholder="$t('reviewForm.searchTestcases')"
            @input="searchTestcasesInDialog"
            clearable
          >
            <template #prefix>
              <el-icon><Search /></el-icon>
            </template>
          </el-input>
        </div>

        <el-table
          ref="testcaseTableRef"
          v-loading="testcaseDialogLoading"
          :data="testcases"
          row-key="id"
          @selection-change="handleTestcaseSelection"
          max-height="400"
          class="testcase-table"
        >
          <el-table-column
            type="selection"
            width="55"
            :reserve-selection="true"
          />
          <el-table-column
            prop="title"
            :label="$t('reviewForm.testcaseTitle')"
            min-width="240"
            show-overflow-tooltip
          />
          <el-table-column
            prop="project.name"
            :label="$t('reviewForm.associatedProject')"
            width="150"
            show-overflow-tooltip
          />
          <el-table-column
            :label="$t('reviewForm.version')"
            width="150"
            show-overflow-tooltip
          >
            <template #default="{ row }">
              {{ formatVersions(row.versions) }}
            </template>
          </el-table-column>
          <el-table-column
            prop="test_type"
            :label="$t('reviewForm.testType')"
            width="120"
          />
          <el-table-column
            prop="priority"
            :label="$t('reviewForm.priority')"
            width="100"
          >
            <template #default="{ row }">
              <el-tag :class="`priority-tag ${row.priority}`">{{
                getPriorityText(row.priority)
              }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column
            prop="author.username"
            :label="$t('reviewForm.author')"
            width="120"
          />
        </el-table>

        <div class="testcase-pagination">
          <span>{{
            $t("reviewForm.selectedTestcasesCount", {
              count: tempSelectedTestcases.length,
            })
          }}</span>
          <el-pagination
            v-model:current-page="testcaseDialogPagination.page"
            v-model:page-size="testcaseDialogPagination.pageSize"
            :total="testcaseDialogPagination.total"
            :page-sizes="[10, 20, 50]"
            layout="sizes, prev, pager, next, total"
            small
            @current-change="fetchDialogTestcases"
            @size-change="handleDialogPageSizeChange"
          />
        </div>
      </div>
      <template #footer>
        <el-button @click="testcaseSelectorVisible = false">{{
          $t("reviewForm.cancel")
        }}</el-button>
        <el-button type="primary" @click="confirmTestcaseSelection">{{
          $t("reviewForm.confirm")
        }}</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted, computed, nextTick } from "vue";
import { useRoute, useRouter } from "vue-router";
import { useI18n } from "vue-i18n";
import { ElMessage } from "element-plus";
import { Search } from "@element-plus/icons-vue";
import api from "@/utils/api";

const route = useRoute();
const router = useRouter();
const { t } = useI18n();
const isEdit = computed(() => !!route.params.id);

const formRef = ref();
const saving = ref(false);
const testcaseSelectorVisible = ref(false);
const testcaseSearch = ref("");
const testcaseSearchInDialog = ref("");
const testcaseTableRef = ref();
const testcaseDialogLoading = ref(false);
const testcaseVersions = ref([]);

const projects = ref([]);
const projectUsers = ref([]);
const templates = ref([]);
const testcases = ref([]);
const selectedTestcases = ref([]);
const tempSelectedTestcases = ref([]);
const testcaseDialogFilters = reactive({
  projectIds: [],
  versionId: "",
});
const testcaseDialogPagination = reactive({
  page: 1,
  pageSize: 20,
  total: 0,
});
let testcaseSearchTimer = null;

const form = reactive({
  title: "",
  description: "",
  projects: [],
  priority: "medium",
  deadline: "",
  testcases: [],
  reviewers: [],
  template: "",
});

const rules = computed(() => ({
  title: [
    { required: true, message: t("reviewForm.titleRequired"), trigger: "blur" },
  ],
  projects: [
    {
      required: true,
      message: t("reviewForm.projectRequired"),
      trigger: "change",
    },
  ],
  testcases: [
    {
      required: true,
      message: t("reviewForm.testcasesRequired"),
      trigger: "change",
    },
  ],
  reviewers: [
    {
      required: true,
      message: t("reviewForm.reviewersRequired"),
      trigger: "change",
    },
  ],
}));

const selectedProjectOptions = computed(() =>
  projects.value.filter((project) => form.projects.includes(project.id)),
);

const fetchProjects = async () => {
  try {
    const response = await api.get("/projects/");
    projects.value = response.data.results || response.data;
  } catch (error) {
    ElMessage.error(t("reviewForm.fetchProjectsFailed"));
  }
};

const fetchProjectUsers = async () => {
  try {
    const response = await api.get("/auth/users/");
    projectUsers.value = response.data.results || response.data || [];
    console.log("All users:", projectUsers.value);
  } catch (error) {
    console.error("Fetch users failed:", error);
    ElMessage.error(t("reviewForm.fetchUsersFailed"));
    projectUsers.value = [];
  }
};

const fetchTemplates = async (projectIds) => {
  try {
    // 如果没有选择项目，清空模板列表
    if (!projectIds || projectIds.length === 0) {
      templates.value = [];
      return;
    }

    // 获取所有选中项目的模板
    const promises = projectIds.map((projectId) =>
      api.get("/reviews/review-templates/", { params: { project: projectId } }),
    );

    const responses = await Promise.all(promises);
    const allTemplates = [];

    responses.forEach((response) => {
      const temps = response.data.results || response.data || [];
      allTemplates.push(...temps);
    });

    // 去重（基于模板ID）
    const uniqueTemplates = allTemplates.filter(
      (template, index, self) =>
        index === self.findIndex((t) => t.id === template.id),
    );

    templates.value = uniqueTemplates;
  } catch (error) {
    console.error("Fetch templates failed:", error);
  }
};

const onProjectChange = (projectIds) => {
  if (projectIds && projectIds.length > 0) {
    fetchTemplates(projectIds);
  } else {
    // 如果没有选择项目，清空相关数据
    testcases.value = [];
    templates.value = [];
  }

  // 清空相关选择
  form.reviewers = [];
  form.testcases = [];
  selectedTestcases.value = [];
  tempSelectedTestcases.value = [];
  testcaseVersions.value = [];
  testcaseDialogFilters.projectIds = [...(projectIds || [])];
  testcaseDialogFilters.versionId = "";
};

const uniqueById = (items) => {
  const itemMap = new Map();
  items.forEach((item) => {
    if (item && item.id !== undefined && item.id !== null) {
      itemMap.set(item.id, item);
    }
  });
  return Array.from(itemMap.values());
};

const formatVersions = (versions) => {
  if (!versions || versions.length === 0) return "-";
  return versions.map((version) => version.name).join("、");
};

const syncCurrentPageSelection = async () => {
  await nextTick();
  if (!testcaseTableRef.value) return;

  testcases.value.forEach((row) => {
    testcaseTableRef.value.toggleRowSelection(
      row,
      tempSelectedTestcases.value.some((item) => item.id === row.id),
    );
  });
};

const fetchDialogVersions = async () => {
  const projectIds = testcaseDialogFilters.projectIds;
  if (!projectIds || projectIds.length === 0) {
    testcaseVersions.value = [];
    testcaseDialogFilters.versionId = "";
    return;
  }

  try {
    const responses = await Promise.all(
      projectIds.map((projectId) =>
        api.get(`/versions/projects/${projectId}/versions/`),
      ),
    );
    testcaseVersions.value = uniqueById(
      responses.flatMap(
        (response) => response.data.results || response.data || [],
      ),
    );

    if (
      testcaseDialogFilters.versionId &&
      !testcaseVersions.value.some(
        (version) => version.id === testcaseDialogFilters.versionId,
      )
    ) {
      testcaseDialogFilters.versionId = "";
    }
  } catch (error) {
    console.error("Fetch testcase versions failed:", error);
    testcaseVersions.value = [];
  }
};

const fetchDialogTestcases = async () => {
  if (
    !testcaseDialogFilters.projectIds ||
    testcaseDialogFilters.projectIds.length === 0
  ) {
    testcases.value = [];
    testcaseDialogPagination.total = 0;
    return;
  }

  testcaseDialogLoading.value = true;
  try {
    const params = {
      page: testcaseDialogPagination.page,
      page_size: testcaseDialogPagination.pageSize,
      project_ids: testcaseDialogFilters.projectIds.join(","),
    };

    if (testcaseDialogFilters.versionId) {
      params.version = testcaseDialogFilters.versionId;
    }
    if (testcaseSearchInDialog.value) {
      params.search = testcaseSearchInDialog.value;
    }

    const response = await api.get("/testcases/", { params });
    const results = response.data.results || response.data || [];
    testcases.value = results;
    testcaseDialogPagination.total = response.data.count ?? results.length;
    await syncCurrentPageSelection();
  } catch (error) {
    console.error("Fetch dialog testcases failed:", error);
    ElMessage.error(t("reviewForm.fetchTestcasesFailed"));
  } finally {
    testcaseDialogLoading.value = false;
  }
};

const onDialogProjectFilterChange = async () => {
  testcaseDialogPagination.page = 1;
  await fetchDialogVersions();
  await fetchDialogTestcases();
};

const refreshDialogTestcases = () => {
  testcaseDialogPagination.page = 1;
  fetchDialogTestcases();
};

const handleDialogPageSizeChange = () => {
  testcaseDialogPagination.page = 1;
  fetchDialogTestcases();
};

const showTestcaseSelector = async () => {
  if (!form.projects || form.projects.length === 0) {
    ElMessage.warning(t("reviewForm.selectProjectFirst"));
    return;
  }
  testcaseDialogFilters.projectIds = [...form.projects];
  testcaseDialogFilters.versionId = "";
  testcaseSearchInDialog.value = testcaseSearch.value;
  testcaseDialogPagination.page = 1;
  tempSelectedTestcases.value = [...selectedTestcases.value];
  testcaseSelectorVisible.value = true;

  await fetchDialogVersions();
  await fetchDialogTestcases();
};

const handleTestcaseSelection = (selection) => {
  const currentPageIds = new Set(
    testcases.value.map((testcase) => testcase.id),
  );
  const previousPages = tempSelectedTestcases.value.filter(
    (testcase) => !currentPageIds.has(testcase.id),
  );
  tempSelectedTestcases.value = uniqueById([...previousPages, ...selection]);
};

const confirmTestcaseSelection = () => {
  selectedTestcases.value = [...tempSelectedTestcases.value];
  form.testcases = selectedTestcases.value.map((tc) => tc.id);
  testcaseSelectorVisible.value = false;
};

const removeTestcase = (id) => {
  selectedTestcases.value = selectedTestcases.value.filter(
    (tc) => tc.id !== id,
  );
  form.testcases = selectedTestcases.value.map((tc) => tc.id);
};

const onReviewersChange = () => {
  // 可以在这里添加评审人员变更的逻辑
};

const applyTemplate = async (templateId) => {
  if (!templateId) return;

  try {
    const template = templates.value.find((t) => t.id === templateId);
    if (template) {
      // 应用模板的默认评审人员
      form.reviewers = template.default_reviewers.map((u) => u.id);
    }
  } catch (error) {
    console.error("Apply template failed:", error);
  }
};

const saveReview = async () => {
  if (!formRef.value) return;

  try {
    await formRef.value.validate();
    saving.value = true;

    const data = {
      ...form,
      testcases: form.testcases,
      reviewers: form.reviewers,
      // 确保包含 template 字段
      template: form.template || null,
    };

    if (isEdit.value) {
      await api.put(`/reviews/reviews/${route.params.id}/`, data);
      ElMessage.success(t("reviewForm.updateSuccess"));
    } else {
      await api.post("/reviews/reviews/", data);
      ElMessage.success(t("reviewForm.createSuccess"));
    }

    router.push("/ai-generation/reviews");
  } catch (error) {
    if (error.response?.data) {
      const errors = Object.values(error.response.data).flat();
      ElMessage.error(errors[0] || t("reviewForm.saveFailed"));
    } else {
      ElMessage.error(t("reviewForm.saveFailed"));
    }
  } finally {
    saving.value = false;
  }
};

const getPriorityText = (priority) => {
  const textMap = {
    low: t("reviewForm.priorityLow"),
    medium: t("reviewForm.priorityMedium"),
    high: t("reviewForm.priorityHigh"),
    critical: t("reviewForm.priorityUrgent"),
  };
  return textMap[priority] || priority;
};

const findMatchingTemplate = (review, templateList) => {
  if (!templateList || templateList.length === 0) return null;

  // 获取评审的项目ID列表和评审人ID列表
  const reviewProjectIds = review.projects.map((p) => p.id).sort();
  const reviewReviewerIds = review.assignments.map((a) => a.reviewer.id).sort();

  let bestMatch = null;
  let bestScore = 0;

  for (const template of templateList) {
    let score = 0;

    // 检查项目匹配度
    const templateProjectIds = (template.project || []).map((p) => p.id).sort();
    const projectIntersection = reviewProjectIds.filter((id) =>
      templateProjectIds.includes(id),
    );
    if (projectIntersection.length > 0) {
      score += projectIntersection.length * 2; // 项目匹配权重更高
    }

    // 检查默认评审人匹配度
    const templateReviewerIds = (template.default_reviewers || [])
      .map((r) => r.id)
      .sort();
    const reviewerIntersection = reviewReviewerIds.filter((id) =>
      templateReviewerIds.includes(id),
    );
    if (reviewerIntersection.length > 0) {
      score += reviewerIntersection.length; // 评审人匹配
    }

    // 如果有更高的匹配分数，更新最佳匹配
    if (score > bestScore) {
      bestScore = score;
      bestMatch = template;
    }
  }

  // 只有当匹配分数大于0时才返回匹配的模板
  return bestScore > 0 ? bestMatch : null;
};

const fetchReviewData = async (reviewId) => {
  try {
    const response = await api.get(`/reviews/reviews/${reviewId}/`);
    const review = response.data;

    // 填充表单数据
    form.title = review.title;
    form.description = review.description;
    form.projects = review.projects.map((p) => p.id);
    form.priority = review.priority;
    form.deadline = review.deadline;
    form.reviewers = review.assignments.map((a) => a.reviewer.id);

    // 处理测试用例
    selectedTestcases.value = review.testcases;
    form.testcases = review.testcases.map((tc) => tc.id);

    // 加载项目相关数据
    if (form.projects.length > 0) {
      await fetchTemplates(form.projects);

      // 在模板加载完成后，尝试找到匹配的模板
      const matchingTemplate = findMatchingTemplate(review, templates.value);
      if (matchingTemplate) {
        form.template = matchingTemplate.id;
      }
    }
  } catch (error) {
    console.error("Fetch review data failed:", error);
    ElMessage.error(t("reviewForm.fetchReviewFailed"));
    router.push("/ai-generation/reviews");
  }
};

const searchTestcases = () => {
  testcaseSearchInDialog.value = testcaseSearch.value;
  if (testcaseSelectorVisible.value) {
    searchTestcasesInDialog();
  }
  // 搜索用例的逻辑
};

const searchTestcasesInDialog = () => {
  clearTimeout(testcaseSearchTimer);
  testcaseSearchTimer = setTimeout(() => {
    refreshDialogTestcases();
  }, 300);
  // 在对话框中搜索用例的逻辑
};

onMounted(async () => {
  await fetchProjects();
  fetchProjectUsers(); // 页面加载时就获取所有用户

  if (isEdit.value) {
    // 如果是编辑模式，加载现有数据
    fetchReviewData(route.params.id);
  } else {
    // 创建模式，检查是否有模板参数
    const templateId = route.query.template;
    if (templateId) {
      try {
        // 获取模板详情
        const response = await api.get(
          `/reviews/review-templates/${templateId}/`,
        );
        const template = response.data;

        // 设置模板ID到表单
        form.template = parseInt(templateId);

        // 自动填充项目
        if (template.project && template.project.length > 0) {
          form.projects = template.project.map((p) => p.id);

          // 触发项目变更，加载对应的用例和模板
          await onProjectChange(form.projects);

          // 应用模板的默认评审人
          if (
            template.default_reviewers &&
            template.default_reviewers.length > 0
          ) {
            form.reviewers = template.default_reviewers.map((u) => u.id);
          }
        }
      } catch (error) {
        console.error("加载模板失败:", error);
      }
    }
  }
});
</script>

<style lang="scss" scoped>
.testcase-selector {
  .search-bar {
    display: flex;
    gap: 12px;
    margin-bottom: 16px;
  }

  .selected-testcases {
    border: 1px solid #dcdfe6;
    border-radius: 4px;
    min-height: 80px;
    padding: 8px;

    .testcase-tag {
      margin: 4px;
    }

    .empty-tip {
      color: #909399;
      text-align: center;
      padding: 24px;
    }
  }
}

.testcase-selector-content {
  .testcase-filter-bar {
    display: grid;
    grid-template-columns: minmax(180px, 1fr) minmax(160px, 0.8fr) minmax(
        220px,
        1.2fr
      );
    gap: 12px;
    margin-bottom: 16px;
  }

  .testcase-pagination {
    display: flex;
    justify-content: space-between;
    align-items: center;
    gap: 12px;
    margin-top: 12px;
  }

  @media (max-width: 768px) {
    .testcase-filter-bar {
      grid-template-columns: 1fr;
    }

    .testcase-pagination {
      align-items: flex-start;
      flex-direction: column;
    }
  }
}

.priority-tag {
  &.low {
    color: #67c23a;
  }
  &.medium {
    color: #e6a23c;
  }
  &.high {
    color: #f56c6c;
  }
  &.critical {
    color: #f56c6c;
    font-weight: bold;
  }
}
</style>
