<template>
  <div class="semantic-dictionary-page">
    <section class="page-hero">
      <div>
        <p class="eyebrow">Semantic Naming Governance</p>
        <h2>语义字典</h2>
        <p>统一维护页面、业务对象、控件角色和用途，减少元素命名的个人风格。</p>
      </div>
      <el-space wrap>
        <el-button @click="loadData">刷新</el-button>
        <el-button type="success" @click="openImportDialog">导入字典</el-button>
        <el-button type="primary" @click="openCreateDialog">新增词条</el-button>
      </el-space>
    </section>

    <el-card shadow="never">
      <div class="toolbar">
        <el-select
          v-model="query.category"
          placeholder="类目"
          clearable
          style="width: 180px"
          @change="loadData"
        >
          <el-option
            v-for="item in categoryOptions"
            :key="item.value"
            :label="item.label"
            :value="item.value"
          />
        </el-select>
        <el-select
          v-model="query.governance_status"
          placeholder="治理状态"
          clearable
          style="width: 160px"
          @change="loadData"
        >
          <el-option
            v-for="item in statusOptions"
            :key="item.value"
            :label="item.label"
            :value="item.value"
          />
        </el-select>
        <el-select
          v-model="query.project"
          placeholder="项目范围"
          clearable
          filterable
          style="width: 220px"
          @change="loadData"
        >
          <el-option label="全局字典" :value="GLOBAL_PROJECT_VALUE" />
          <el-option
            v-for="project in projects"
            :key="project.id"
            :label="project.name"
            :value="project.id"
          />
        </el-select>
        <el-input
          v-model="query.search"
          placeholder="搜索 value / label / 说明"
          clearable
          style="width: 280px"
          @keyup.enter="loadData"
          @clear="loadData"
        />
        <el-button type="primary" @click="loadData">查询</el-button>
      </div>

      <el-table v-loading="loading" :data="items" border>
        <el-table-column label="类目" width="120">
          <template #default="{ row }">{{
            categoryLabel(row.category)
          }}</template>
        </el-table-column>
        <el-table-column prop="value" label="标准值" min-width="160" />
        <el-table-column prop="label" label="显示名" min-width="160">
          <template #default="{ row }">{{ row.label || row.value }}</template>
        </el-table-column>
        <el-table-column label="范围" width="160">
          <template #default="{ row }">
            <el-tag v-if="row.project" type="warning" size="small">{{
              row.project_name || `项目 ${row.project}`
            }}</el-tag>
            <el-tag v-else type="info" size="small">全局</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="sort_order" label="排序" width="90" />
        <el-table-column label="状态" width="90">
          <template #default="{ row }">
            <el-tag :type="row.is_active ? 'success' : 'info'" size="small">{{
              row.is_active ? "启用" : "禁用"
            }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="治理" width="110">
          <template #default="{ row }">
            <el-tag :type="statusType(row.governance_status)" size="small">
              {{ statusLabel(row.governance_status) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column
          prop="description"
          label="说明"
          min-width="220"
          show-overflow-tooltip
        />
        <el-table-column label="操作" width="260" fixed="right">
          <template #default="{ row }">
            <el-button
              v-if="row.governance_status === 'pending'"
              size="small"
              type="success"
              plain
              @click="approveItem(row)"
            >
              标准化
            </el-button>
            <el-button size="small" @click="openEditDialog(row)"
              >编辑</el-button
            >
            <el-button size="small" type="danger" plain @click="removeItem(row)"
              >删除</el-button
            >
          </template>
        </el-table-column>
      </el-table>

      <div class="pagination-row">
        <el-pagination
          v-model:current-page="query.page"
          v-model:page-size="query.page_size"
          :total="total"
          :page-sizes="[20, 50, 100]"
          layout="total, sizes, prev, pager, next"
          @size-change="loadData"
          @current-change="loadData"
        />
      </div>
    </el-card>

    <el-dialog
      v-model="editVisible"
      :title="editingId ? '编辑词条' : '新增词条'"
      width="560px"
    >
      <el-form label-width="96px">
        <el-form-item label="类目" required>
          <el-select v-model="form.category" style="width: 100%">
            <el-option
              v-for="item in categoryOptions"
              :key="item.value"
              :label="item.label"
              :value="item.value"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="项目范围">
          <el-select
            v-model="form.project"
            clearable
            filterable
            style="width: 100%"
            placeholder="不选则为全局字典"
          >
            <el-option
              v-for="project in projects"
              :key="project.id"
              :label="project.name"
              :value="project.id"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="标准值" required>
          <el-input
            v-model.trim="form.value"
            placeholder="如：登录页、手机号、输入框"
          />
        </el-form-item>
        <el-form-item label="显示名">
          <el-input v-model.trim="form.label" placeholder="默认等于标准值" />
        </el-form-item>
        <el-form-item label="排序">
          <el-input-number v-model="form.sort_order" :min="0" :step="10" />
        </el-form-item>
        <el-form-item label="状态">
          <el-switch
            v-model="form.is_active"
            active-text="启用"
            inactive-text="禁用"
          />
        </el-form-item>
        <el-form-item label="治理状态">
          <el-select v-model="form.governance_status" style="width: 100%">
            <el-option
              v-for="item in statusOptions"
              :key="item.value"
              :label="item.label"
              :value="item.value"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="说明">
          <el-input
            v-model="form.description"
            type="textarea"
            :rows="3"
            placeholder="用于解释这个词什么时候用"
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="editVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="saveItem"
          >保存</el-button
        >
      </template>
    </el-dialog>

    <el-dialog v-model="importVisible" title="导入语义字典" width="760px">
      <el-alert
        type="info"
        show-icon
        :closable="false"
        title="支持 CSV 或 JSON。CSV 字段：category,value,label,description,sort_order,is_active。category 只能是 page/object/role/purpose。"
      />
      <div class="import-scope">
        <span>导入范围</span>
        <el-select
          v-model="importProject"
          clearable
          filterable
          placeholder="不选则导入全局字典"
          style="width: 260px"
        >
          <el-option
            v-for="project in projects"
            :key="project.id"
            :label="project.name"
            :value="project.id"
          />
        </el-select>
      </div>
      <el-input
        v-model="importContent"
        type="textarea"
        :rows="12"
        placeholder="category,value,label,description,sort_order,is_active&#10;page,登录页,登录页,登录相关页面,10,true&#10;object,手机号,手机号,登录账号输入,10,true"
      />
      <template #footer>
        <el-button @click="fillSample">填入示例</el-button>
        <el-button @click="importVisible = false">取消</el-button>
        <el-button type="primary" :loading="importing" @click="submitImport"
          >导入</el-button
        >
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { onMounted, reactive, ref } from "vue";
import { ElMessage, ElMessageBox } from "element-plus";
import {
  createSemanticDictionary,
  deleteSemanticDictionary,
  getAppProjects,
  getSemanticDictionaries,
  importSemanticDictionaries,
  updateSemanticDictionary,
} from "@/api/app-automation";

const GLOBAL_PROJECT_VALUE = "__global__";

const categoryOptions = [
  { label: "页面/场景", value: "page" },
  { label: "业务含义", value: "object" },
  { label: "控件角色", value: "role" },
  { label: "用途", value: "purpose" },
];

const statusOptions = [
  { label: "已规范", value: "approved" },
  { label: "待治理", value: "pending" },
  { label: "已合并", value: "merged" },
  { label: "已停用", value: "deprecated" },
];

const query = reactive({
  category: "",
  governance_status: "",
  project: "",
  search: "",
  page: 1,
  page_size: 20,
});

const form = reactive({
  category: "object",
  project: null,
  value: "",
  label: "",
  description: "",
  governance_status: "approved",
  sort_order: 0,
  is_active: true,
});

const projects = ref([]);
const items = ref([]);
const total = ref(0);
const loading = ref(false);
const saving = ref(false);
const importing = ref(false);
const editVisible = ref(false);
const importVisible = ref(false);
const editingId = ref(null);
const importProject = ref(null);
const importContent = ref("");

const categoryLabel = (value) =>
  categoryOptions.find((item) => item.value === value)?.label || value;
const statusLabel = (value) =>
  statusOptions.find((item) => item.value === value)?.label || "已规范";
const statusType = (value) => {
  if (value === "approved") return "success";
  if (value === "pending") return "warning";
  if (value === "merged") return "info";
  if (value === "deprecated") return "danger";
  return "success";
};

const buildQueryParams = () => {
  const params = {
    page: query.page,
    page_size: query.page_size,
  };
  if (query.category) params.category = query.category;
  if (query.governance_status)
    params.governance_status = query.governance_status;
  if (query.search) params.search = query.search;
  if (query.project && query.project !== GLOBAL_PROJECT_VALUE)
    params.project = query.project;
  if (query.project === GLOBAL_PROJECT_VALUE) params.scope = "global";
  return params;
};

const loadProjects = async () => {
  const { data } = await getAppProjects({ page_size: 100 });
  projects.value = data.results || data.data || [];
};

const loadData = async () => {
  try {
    loading.value = true;
    const { data } = await getSemanticDictionaries(buildQueryParams());
    items.value = data.results || [];
    total.value = data.count || 0;
  } catch (error) {
    ElMessage.error(
      `语义字典加载失败: ${error.response?.data?.message || error.message}`,
    );
  } finally {
    loading.value = false;
  }
};

const resetForm = () => {
  Object.assign(form, {
    category: "object",
    project: null,
    value: "",
    label: "",
    description: "",
    governance_status: "approved",
    sort_order: 0,
    is_active: true,
  });
};

const openCreateDialog = () => {
  editingId.value = null;
  resetForm();
  editVisible.value = true;
};

const openEditDialog = (row) => {
  editingId.value = row.id;
  Object.assign(form, {
    category: row.category,
    project: row.project || null,
    value: row.value,
    label: row.label || "",
    description: row.description || "",
    governance_status: row.governance_status || "approved",
    sort_order: row.sort_order || 0,
    is_active: row.is_active !== false,
  });
  editVisible.value = true;
};

const approveItem = async (row) => {
  try {
    await updateSemanticDictionary(row.id, {
      governance_status: "approved",
      is_active: true,
    });
    ElMessage.success("已标记为规范词");
    loadData();
  } catch (error) {
    ElMessage.error(
      `状态更新失败: ${error.response?.data?.detail || error.message}`,
    );
  }
};

const saveItem = async () => {
  if (!form.category || !form.value) {
    ElMessage.warning("请填写类目和标准值");
    return;
  }

  try {
    saving.value = true;
    const payload = {
      ...form,
      label: form.label || form.value,
      project: form.project || null,
    };
    if (editingId.value) {
      await updateSemanticDictionary(editingId.value, payload);
    } else {
      await createSemanticDictionary(payload);
    }
    ElMessage.success("保存成功");
    editVisible.value = false;
    loadData();
  } catch (error) {
    const detail =
      error.response?.data?.non_field_errors?.[0] ||
      error.response?.data?.value?.[0] ||
      error.response?.data?.detail ||
      error.message;
    ElMessage.error(`保存失败: ${detail}`);
  } finally {
    saving.value = false;
  }
};

const removeItem = async (row) => {
  try {
    await ElMessageBox.confirm(`确定删除词条「${row.value}」吗？`, "删除确认", {
      type: "warning",
    });
    await deleteSemanticDictionary(row.id);
    ElMessage.success("删除成功");
    loadData();
  } catch (error) {
    if (error !== "cancel") {
      ElMessage.error(
        `删除失败: ${error.response?.data?.detail || error.message}`,
      );
    }
  }
};

const openImportDialog = () => {
  importProject.value = null;
  importContent.value = "";
  importVisible.value = true;
};

const fillSample = () => {
  importContent.value = [
    "category,value,label,description,sort_order,is_active",
    "page,登录页,登录页,登录相关页面,10,true",
    "object,手机号,手机号,登录账号输入,10,true",
    "role,输入框,输入框,可输入文本的控件,20,true",
    "purpose,断言,断言,用于检查结果是否出现,30,true",
  ].join("\n");
};

const submitImport = async () => {
  if (!importContent.value.trim()) {
    ElMessage.warning("请先填写 CSV 或 JSON 内容");
    return;
  }

  try {
    importing.value = true;
    const { data } = await importSemanticDictionaries({
      project: importProject.value || null,
      content: importContent.value,
    });
    const result = data.data || {};
    ElMessage.success(
      `导入完成：新增 ${result.created || 0}，更新 ${result.updated || 0}，跳过 ${(result.skipped || []).length}`,
    );
    importVisible.value = false;
    loadData();
  } catch (error) {
    ElMessage.error(
      `导入失败: ${error.response?.data?.message || error.message}`,
    );
  } finally {
    importing.value = false;
  }
};

onMounted(async () => {
  await loadProjects();
  loadData();
});
</script>

<style scoped lang="scss">
.semantic-dictionary-page {
  padding: 20px;
}

.page-hero {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 16px;
  padding: 22px 24px;
  border-radius: 16px;
  background: linear-gradient(135deg, #f4f7f1 0%, #e6f2ee 100%);
  border: 1px solid #dce8df;

  h2 {
    margin: 4px 0 8px;
    font-size: 26px;
    color: #1f352a;
  }

  p {
    margin: 0;
    color: #607069;
  }
}

.eyebrow {
  margin: 0;
  font-size: 12px;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: #3e7b5f;
  font-weight: 700;
}

.toolbar {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  margin-bottom: 14px;
}

.pagination-row {
  display: flex;
  justify-content: flex-end;
  margin-top: 14px;
}

.import-scope {
  display: flex;
  align-items: center;
  gap: 12px;
  margin: 16px 0 12px;
  color: #606266;
}
</style>
