<template>
  <el-dialog
    v-model="dialogVisible"
    :title="isEdit ? '编辑元素' : '新增元素'"
    width="760px"
    @close="handleClose"
  >
    <el-form ref="formRef" :model="formData" :rules="rules" label-width="120px">
      <el-form-item label="语义命名" required>
        <div class="semantic-name-guide">
          <el-select
            v-model="formData.config.semantic_page"
            placeholder="选择页面"
            filterable
            allow-create
            default-first-option
          >
            <el-option
              v-for="item in semanticPageOptions"
              :key="item"
              :label="item"
              :value="item"
            />
          </el-select>
          <el-autocomplete
            v-model="formData.config.semantic_object"
            :fetch-suggestions="querySemanticObjectSuggestions"
            placeholder="选择或输入业务对象，如：手机号、登录、社区名称"
            clearable
            style="width: 100%"
          />
          <el-select
            v-model="formData.config.semantic_role"
            placeholder="控件角色"
            filterable
          >
            <el-option
              v-for="item in semanticRoleOptions"
              :key="item"
              :label="item"
              :value="item"
            />
          </el-select>
        </div>
        <div class="semantic-name-preview">
          标准名称：{{
            generatedSemanticName || "请选择页面、填写业务对象并选择控件角色"
          }}
        </div>
      </el-form-item>

      <el-form-item label="元素名称" prop="name">
        <el-input
          v-model="formData.name"
          readonly
          placeholder="由语义命名自动生成"
        />
      </el-form-item>

      <el-form-item label="所属项目">
        <el-select
          v-model="formData.project"
          placeholder="请选择项目"
          clearable
          filterable
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

      <el-form-item label="元素类型" prop="element_type">
        <el-radio-group
          v-model="formData.element_type"
          @change="handleTypeChange"
        >
          <el-radio value="image">图片元素</el-radio>
          <el-radio value="pos">坐标元素</el-radio>
          <el-radio value="region">区域元素</el-radio>
          <el-radio value="selector">定位元素</el-radio>
        </el-radio-group>
      </el-form-item>

      <el-form-item label="标签">
        <el-select
          v-model="formData.tags"
          multiple
          filterable
          allow-create
          default-first-option
          placeholder="输入后回车创建标签"
          style="width: 100%"
        />
      </el-form-item>

      <el-form-item label="用途">
        <el-select
          v-model="formData.config.semantic_purpose"
          placeholder="可选，用于后续筛选和治理"
          clearable
          filterable
          style="width: 100%"
        >
          <el-option
            v-for="item in semanticPurposeOptions"
            :key="item"
            :label="item"
            :value="item"
          />
        </el-select>
      </el-form-item>

      <template v-if="formData.element_type === 'image'">
        <el-divider content-position="left">图片配置</el-divider>

        <el-form-item label="图片分类">
          <div class="category-row">
            <el-select
              v-model="formData.config.image_category"
              placeholder="选择分类"
              filterable
              style="flex: 1"
            >
              <el-option
                v-for="category in imageCategories"
                :key="category"
                :label="category"
                :value="category"
              >
                <div class="category-option">
                  <span>{{ category }}</span>
                  <el-button
                    v-if="category !== 'common'"
                    type="danger"
                    size="small"
                    link
                    :icon="Delete"
                    @click.stop="handleDeleteCategory(category)"
                  />
                </div>
              </el-option>
            </el-select>
            <el-button
              type="primary"
              :icon="Plus"
              @click="showCreateCategoryDialog"
            />
          </div>
        </el-form-item>

        <el-form-item label="元素图片">
          <div class="image-area">
            <div
              v-if="isEdit && currentImageUrl && !imagePreview"
              class="image-card"
            >
              <div class="image-card-title">当前图片</div>
              <el-image
                :src="currentImageUrl"
                fit="contain"
                class="image-preview"
                :preview-src-list="[currentImageUrl]"
                preview-teleported
              >
                <template #error>
                  <div class="image-error">
                    <el-icon><Picture /></el-icon>
                    <span>加载失败</span>
                  </div>
                </template>
              </el-image>
              <div class="image-path">
                {{ formData.config.image_path || "-" }}
              </div>
            </div>

            <div v-if="imagePreview" class="image-card image-card-new">
              <div class="image-card-title">待上传图片</div>
              <el-image
                :src="imagePreview"
                fit="contain"
                class="image-preview"
                :preview-src-list="[imagePreview]"
                preview-teleported
              />
              <div class="image-path">{{ imageFile?.name || "-" }}</div>
            </div>

            <el-upload
              ref="uploadRef"
              :auto-upload="false"
              :show-file-list="false"
              :limit="1"
              :on-change="handleImageChange"
              :on-exceed="handleExceed"
              accept="image/png,image/jpg,image/jpeg"
            >
              <el-button type="primary" :icon="Upload">选择图片</el-button>
            </el-upload>
          </div>
        </el-form-item>

        <el-form-item label="匹配阈值">
          <el-slider
            v-model="formData.config.image_threshold"
            :min="0.5"
            :max="1"
            :step="0.05"
            show-input
          />
        </el-form-item>

        <el-form-item label="颜色模式">
          <el-switch
            v-model="formData.config.rgb"
            active-text="RGB"
            inactive-text="灰度"
          />
        </el-form-item>
      </template>

      <template v-if="formData.element_type === 'pos'">
        <el-divider content-position="left">坐标配置</el-divider>

        <el-form-item label="X 坐标">
          <el-input-number
            v-model="formData.config.x"
            :min="0"
            style="width: 100%"
          />
        </el-form-item>

        <el-form-item label="Y 坐标">
          <el-input-number
            v-model="formData.config.y"
            :min="0"
            style="width: 100%"
          />
        </el-form-item>
      </template>

      <template v-if="formData.element_type === 'region'">
        <el-divider content-position="left">区域配置</el-divider>

        <el-form-item label="左上角坐标">
          <el-space>
            <el-input-number
              v-model="formData.config.x1"
              :min="0"
              placeholder="X1"
            />
            <el-input-number
              v-model="formData.config.y1"
              :min="0"
              placeholder="Y1"
            />
          </el-space>
        </el-form-item>

        <el-form-item label="右下角坐标">
          <el-space>
            <el-input-number
              v-model="formData.config.x2"
              :min="0"
              placeholder="X2"
            />
            <el-input-number
              v-model="formData.config.y2"
              :min="0"
              placeholder="Y2"
            />
          </el-space>
        </el-form-item>
      </template>

      <template v-if="formData.element_type === 'selector'">
        <el-divider content-position="left">定位配置</el-divider>

        <el-form-item label="应用包名">
          <el-input
            v-model="formData.config.package"
            placeholder="如：com.example.demo"
          />
        </el-form-item>

        <el-form-item label="页面 Activity">
          <el-input
            v-model="formData.config.activity"
            placeholder="如：com.example.demo.activity.LoginActivity"
          />
        </el-form-item>

        <el-form-item label="resource-id">
          <el-input
            v-model="formData.config.resource_id"
            placeholder="如：com.example.demo:id/btnLogin"
          />
        </el-form-item>

        <el-form-item label="文本 text">
          <el-input v-model="formData.config.text" placeholder="如：登录" />
        </el-form-item>

        <el-form-item label="描述 content-desc">
          <el-input
            v-model="formData.config.content_desc"
            placeholder="content-desc"
          />
        </el-form-item>

        <el-form-item label="提示 hint">
          <el-input
            v-model="formData.config.hint"
            placeholder="如：请输入手机号"
          />
        </el-form-item>

        <el-form-item label="控件 class">
          <el-input
            v-model="formData.config.class"
            placeholder="如：android.widget.EditText"
          />
        </el-form-item>

        <el-form-item label="定位键">
          <el-input
            v-model="formData.config.locator_key"
            placeholder="如：btn_login"
          />
        </el-form-item>

        <el-form-item label="中文说明">
          <el-input
            v-model="formData.config.description"
            placeholder="如：登录按钮、手机号输入框、协议勾选框"
          />
        </el-form-item>

        <el-form-item label="补充说明">
          <el-input
            v-model="formData.config.manual_note"
            type="textarea"
            :rows="2"
            placeholder="补充元素用途、页面位置、使用注意事项，便于后续理解"
          />
        </el-form-item>

        <el-form-item label="来源文件">
          <el-input
            v-model="formData.config.source_file"
            placeholder="如：community_password_login.yaml"
          />
        </el-form-item>

        <el-form-item label="边界 bounds">
          <el-input
            v-model="formData.config.bounds"
            placeholder="如：[96,984][984,1128]"
          />
        </el-form-item>

        <el-form-item label="状态标记">
          <el-space wrap>
            <el-checkbox v-model="formData.config.clickable"
              >clickable</el-checkbox
            >
            <el-checkbox v-model="formData.config.focusable"
              >focusable</el-checkbox
            >
            <el-checkbox v-model="formData.config.enabled">enabled</el-checkbox>
          </el-space>
        </el-form-item>
      </template>
    </el-form>

    <template #footer>
      <el-button @click="handleClose">取消</el-button>
      <el-button type="primary" :loading="submitting" @click="handleSubmit"
        >保存</el-button
      >
    </template>
  </el-dialog>

  <el-dialog v-model="createCategoryVisible" title="创建图片分类" width="420px">
    <el-form>
      <el-form-item label="分类名称">
        <el-input
          v-model="newCategoryName"
          placeholder="如：button、icon、login"
          @keyup.enter="handleCreateCategory"
        />
      </el-form-item>
    </el-form>

    <template #footer>
      <el-button @click="createCategoryVisible = false">取消</el-button>
      <el-button
        type="primary"
        :loading="creatingCategory"
        @click="handleCreateCategory"
      >
        创建
      </el-button>
    </template>
  </el-dialog>
</template>

<script setup>
import { computed, nextTick, onMounted, reactive, ref, watch } from "vue";
import { ElMessage, ElMessageBox } from "element-plus";
import { Delete, Picture, Plus, Upload } from "@element-plus/icons-vue";
import {
  createAppElement,
  createAppImageCategory,
  deleteAppImageCategory,
  getAppImageCategories,
  getSemanticDictionaryOptions,
  updateAppElement,
  uploadAppElementImage,
} from "@/api/app-automation";
import {
  buildSemanticElementName,
  buildSemanticTags,
  pickSemanticFields,
  semanticObjectOptions as defaultSemanticObjectOptions,
  semanticPageOptions as defaultSemanticPageOptions,
  semanticPurposeOptions as defaultSemanticPurposeOptions,
  semanticRoleOptions as defaultSemanticRoleOptions,
} from "@/config/semanticNaming";

const props = defineProps({
  modelValue: {
    type: Boolean,
    default: false,
  },
  editData: {
    type: Object,
    default: null,
  },
  projectList: {
    type: Array,
    default: () => [],
  },
});

const emit = defineEmits(["update:modelValue", "success"]);

const defaultConfig = () => ({
  image_category: "common",
  image_threshold: 0.7,
  rgb: false,
  x: 0,
  y: 0,
  x1: 0,
  y1: 0,
  x2: 0,
  y2: 0,
  image_path: "",
  file_hash: "",
  package: "",
  activity: "",
  resource_id: "",
  text: "",
  content_desc: "",
  hint: "",
  class: "",
  locator_key: "",
  description: "",
  manual_note: "",
  source_file: "",
  bounds: "",
  semantic_page: "",
  semantic_object: "",
  semantic_role: "",
  interaction_role: "",
  semantic_purpose: "",
  clickable: false,
  focusable: false,
  enabled: true,
});

const dialogVisible = computed({
  get: () => props.modelValue,
  set: (value) => emit("update:modelValue", value),
});

const isEdit = computed(() => !!props.editData);
const formRef = ref(null);
const uploadRef = ref(null);
const submitting = ref(false);
const imageFile = ref(null);
const imagePreview = ref("");
const imageCategories = ref(["common"]);
const createCategoryVisible = ref(false);
const newCategoryName = ref("");
const creatingCategory = ref(false);
const imageRefreshKey = ref(Date.now());
const semanticPageOptions = ref([...defaultSemanticPageOptions]);
const semanticObjectOptions = ref([...defaultSemanticObjectOptions]);
const semanticRoleOptions = ref([...defaultSemanticRoleOptions]);
const semanticPurposeOptions = ref([...defaultSemanticPurposeOptions]);
const generatedSemanticName = computed(() =>
  buildSemanticElementName({
    page: formData.config.semantic_page,
    object: formData.config.semantic_object,
    role: formData.config.semantic_role,
  }),
);

const formData = reactive({
  name: "",
  element_type: "image",
  project: null,
  tags: [],
  config: defaultConfig(),
});

const rules = {
  name: [{ required: true, message: "请输入元素名称", trigger: "blur" }],
  element_type: [
    { required: true, message: "请选择元素类型", trigger: "change" },
  ],
};

const currentImageUrl = computed(() => {
  if (props.editData?.id && formData.config.image_path) {
    return `/api/app-automation/elements/${props.editData.id}/preview/?t=${imageRefreshKey.value}`;
  }
  return "";
});

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
    const params = formData.project ? { project: formData.project } : {};
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
    semanticPurposeOptions.value = normalizeDictionaryValues(
      options.purpose,
      defaultSemanticPurposeOptions,
    );
  } catch (error) {
    console.warn("语义字典加载失败，已使用前端默认字典:", error);
  }
};

const resetFormData = () => {
  Object.assign(formData, {
    name: "",
    element_type: "image",
    project: null,
    tags: [],
    config: defaultConfig(),
  });
  imageFile.value = null;
  imagePreview.value = "";
  if (uploadRef.value) {
    uploadRef.value.clearFiles();
  }
};

const applyEditData = (data) => {
  if (!data) {
    resetFormData();
    return;
  }

  Object.assign(formData, {
    name: data.name || "",
    element_type: data.element_type || "image",
    project: data.project || null,
    tags: Array.isArray(data.tags) ? [...data.tags] : [],
    config: {
      ...defaultConfig(),
      ...(data.config || {}),
    },
  });
  normalizeSemanticConfigFromLegacyFields();
  hydrateSemanticFieldsFromName();

  imageFile.value = null;
  imagePreview.value = "";
  imageRefreshKey.value = Date.now();
};

const normalizeSemanticConfigFromLegacyFields = () => {
  const config = formData.config || {};
  if (!config.semantic_role && config.interaction_role) {
    config.semantic_role = config.interaction_role;
  }

  if (!config.semantic_role && Array.isArray(formData.tags)) {
    const roleFromTags = semanticRoleOptions.value.find((role) =>
      formData.tags.includes(role),
    );
    if (roleFromTags) config.semantic_role = roleFromTags;
  }

  if (!config.interaction_role && config.semantic_role) {
    config.interaction_role = config.semantic_role;
  }
};

const hydrateSemanticFieldsFromName = () => {
  if (
    formData.config.semantic_page ||
    formData.config.semantic_object ||
    formData.config.semantic_role ||
    !formData.name
  ) {
    return;
  }
  const parts = String(formData.name).split(".").filter(Boolean);
  if (parts.length >= 3) {
    formData.config.semantic_page = parts[0];
    formData.config.semantic_role = parts[parts.length - 1];
    formData.config.semantic_object = parts.slice(1, -1).join("");
  }
};

const handleTypeChange = () => {
  formData.config = defaultConfig();
  imageFile.value = null;
  imagePreview.value = "";
  nextTick(() => {
    formRef.value?.clearValidate?.();
  });
};

const handleImageChange = (file) => {
  if (!file?.raw) return;
  imageFile.value = file.raw;

  const reader = new FileReader();
  reader.onload = (event) => {
    if (typeof event.target?.result === "string") {
      imagePreview.value = event.target.result;
    }
  };
  reader.onerror = () => {
    ElMessage.error("图片读取失败");
  };
  reader.readAsDataURL(file.raw);
};

const handleExceed = () => {
  ElMessage.warning("最多只能上传 1 个图片文件");
};

const buildSubmitConfig = () => {
  const semanticFields = pickSemanticFields(formData.config);

  if (formData.element_type === "image") {
    return {
      ...semanticFields,
      image_category: formData.config.image_category || "common",
      image_threshold: formData.config.image_threshold,
      rgb: formData.config.rgb,
      image_path: formData.config.image_path || "",
      file_hash: formData.config.file_hash || "",
    };
  }

  if (formData.element_type === "pos") {
    return {
      ...semanticFields,
      x: formData.config.x,
      y: formData.config.y,
    };
  }

  if (formData.element_type === "region") {
    return {
      ...semanticFields,
      x1: formData.config.x1,
      y1: formData.config.y1,
      x2: formData.config.x2,
      y2: formData.config.y2,
    };
  }

  return {
    ...semanticFields,
    package: formData.config.package || "",
    activity: formData.config.activity || "",
    resource_id: formData.config.resource_id || "",
    text: formData.config.text || "",
    content_desc: formData.config.content_desc || "",
    hint: formData.config.hint || "",
    class: formData.config.class || "",
    locator_key: formData.config.locator_key || "",
    description:
      formData.config.description || generatedSemanticName.value || "",
    manual_note: formData.config.manual_note || "",
    source_file: formData.config.source_file || "",
    bounds: formData.config.bounds || "",
    clickable: !!formData.config.clickable,
    focusable: !!formData.config.focusable,
    enabled: formData.config.enabled !== false,
  };
};

const handleSubmit = async () => {
  try {
    if (!generatedSemanticName.value) {
      ElMessage.warning("请先完成语义命名：页面、业务对象、控件角色");
      return;
    }
    formData.name = generatedSemanticName.value;
    formData.tags = buildSemanticTags(formData.tags);
    await formRef.value.validate();
    submitting.value = true;

    if (formData.element_type === "image") {
      if (!isEdit.value && !imageFile.value) {
        ElMessage.warning("请选择图片文件");
        submitting.value = false;
        return;
      }

      if (imageFile.value) {
        const { data: uploadData } = await uploadAppElementImage(
          imageFile.value,
          formData.config.image_category || "common",
          props.editData?.id || null,
        );

        if (!uploadData.success) {
          let errorMessage = uploadData.message || "上传图片失败";
          if (uploadData.detail) {
            errorMessage += `\n\n${uploadData.detail}`;
          }
          if (uploadData.suggestion) {
            errorMessage += `\n\n建议：${uploadData.suggestion}`;
          }
          ElMessage.error({
            message: errorMessage,
            duration: 8000,
            showClose: true,
          });
          submitting.value = false;
          return;
        }

        formData.config.image_path = uploadData.data.image_path;
        formData.config.file_hash = uploadData.data.file_hash;
      }
    }

    const payload = {
      name: formData.name,
      element_type: formData.element_type,
      project: formData.project || null,
      tags: buildSemanticTags(formData.tags),
      config: buildSubmitConfig(),
    };

    if (isEdit.value) {
      await updateAppElement(props.editData.id, payload);
    } else {
      await createAppElement(payload);
    }

    ElMessage.success(isEdit.value ? "更新成功" : "创建成功");
    emit("success");
    handleClose();
  } catch (error) {
    if (error !== "validation failed") {
      console.error("元素保存失败:", error);
      ElMessage.error("操作失败");
    }
  } finally {
    submitting.value = false;
  }
};

const handleClose = () => {
  formRef.value?.resetFields?.();
  resetFormData();
  emit("update:modelValue", false);
};

const loadImageCategories = async () => {
  try {
    const { data } = await getAppImageCategories();
    if (data.success && Array.isArray(data.data) && data.data.length > 0) {
      imageCategories.value = data.data.map((item) => item.name || item);
    } else {
      imageCategories.value = ["common"];
    }
  } catch (error) {
    console.error("加载图片分类失败:", error);
    imageCategories.value = ["common"];
  }
};

const showCreateCategoryDialog = () => {
  newCategoryName.value = "";
  createCategoryVisible.value = true;
};

const handleCreateCategory = async () => {
  const categoryName = newCategoryName.value.trim();
  if (!categoryName) {
    ElMessage.warning("请输入分类名称");
    return;
  }

  try {
    creatingCategory.value = true;
    const { data } = await createAppImageCategory(categoryName);
    if (!data.success) {
      ElMessage.error(data.message || "创建失败");
      return;
    }

    await loadImageCategories();
    formData.config.image_category = data.data.name;
    createCategoryVisible.value = false;
    ElMessage.success("创建成功");
  } catch (error) {
    console.error("创建分类失败:", error);
    ElMessage.error("创建失败");
  } finally {
    creatingCategory.value = false;
  }
};

const handleDeleteCategory = async (categoryName) => {
  try {
    await ElMessageBox.confirm(
      `确定要删除分类 "${categoryName}" 吗？只能删除空目录。`,
      "删除确认",
      {
        confirmButtonText: "删除",
        cancelButtonText: "取消",
        type: "warning",
      },
    );

    const { data } = await deleteAppImageCategory(categoryName);
    if (!data.success) {
      ElMessage.error(data.message || "删除失败");
      return;
    }

    await loadImageCategories();
    if (formData.config.image_category === categoryName) {
      formData.config.image_category = "common";
    }
    ElMessage.success("删除成功");
  } catch (error) {
    if (error !== "cancel") {
      console.error("删除分类失败:", error);
      ElMessage.error("删除失败");
    }
  }
};

watch(
  () => props.modelValue,
  (visible) => {
    if (!visible) return;
    if (props.editData) {
      applyEditData(props.editData);
    } else {
      resetFormData();
    }
    loadSemanticDictionaries();
  },
);

watch(
  () => props.editData,
  (data) => {
    if (props.modelValue) {
      applyEditData(data);
    }
  },
  { immediate: true },
);

watch(generatedSemanticName, (value) => {
  if (value) {
    formData.name = value;
  }
});

watch(
  () => formData.project,
  () => {
    if (props.modelValue) {
      loadSemanticDictionaries();
    }
  },
);

onMounted(() => {
  loadImageCategories();
  loadSemanticDictionaries();
});
</script>

<style scoped lang="scss">
.category-row {
  display: flex;
  gap: 12px;
  width: 100%;
}

.category-option {
  display: flex;
  align-items: center;
  justify-content: space-between;
  width: 100%;
}

.semantic-name-guide {
  display: grid;
  grid-template-columns: 1fr 1.2fr 1fr;
  gap: 8px;
  width: 100%;
}

.semantic-name-preview {
  margin-top: 6px;
  color: #606266;
  font-size: 12px;
  line-height: 1.5;
}

.image-area {
  display: flex;
  flex-wrap: wrap;
  gap: 16px;
  align-items: flex-start;
}

.image-card {
  width: 240px;
  padding: 12px;
  border: 1px solid #e4e7ed;
  border-radius: 8px;
  background: #fafafa;
}

.image-card-new {
  border-color: #67c23a;
}

.image-card-title {
  margin-bottom: 8px;
  color: #606266;
  font-weight: 600;
}

.image-preview {
  width: 100%;
  height: 150px;
  border-radius: 6px;
  background: #fff;
}

.image-path {
  margin-top: 8px;
  color: #909399;
  font-size: 12px;
  word-break: break-all;
}

.image-error {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  width: 100%;
  height: 100%;
  color: #909399;
  gap: 8px;
}
</style>
