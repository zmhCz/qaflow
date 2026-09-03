<template>
  <div class="register-container">
    <section class="register-card">
      <div class="form-header">
        <p class="eyebrow">Create Account</p>
        <h2>{{ $t("auth.registerTitle") }}</h2>
        <p>{{ $t("auth.registerSubtitle") }}</p>
      </div>

      <el-alert
        v-if="registerError"
        :title="registerError"
        type="error"
        show-icon
        :closable="true"
        class="register-error"
        @close="registerError = ''"
      />

      <el-form
        ref="formRef"
        :model="form"
        :rules="rules"
        class="register-form"
        @submit.prevent="handleRegister"
      >
        <el-form-item prop="username">
          <el-input
            v-model="form.username"
            :placeholder="$t('auth.username')"
            size="large"
            :prefix-icon="User"
            clearable
          />
        </el-form-item>

        <el-form-item prop="phone">
          <el-input
            v-model="form.phone"
            placeholder="请输入手机号"
            size="large"
            :prefix-icon="Phone"
            maxlength="11"
            clearable
          />
        </el-form-item>

        <el-form-item prop="email">
          <el-input
            v-model="form.email"
            type="email"
            :placeholder="$t('auth.email')"
            size="large"
            :prefix-icon="Message"
            clearable
          />
        </el-form-item>

        <el-row :gutter="16">
          <el-col :span="12">
            <el-form-item prop="first_name">
              <el-input
                v-model="form.first_name"
                :placeholder="$t('auth.firstName')"
                size="large"
                clearable
              />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item prop="last_name">
              <el-input
                v-model="form.last_name"
                :placeholder="$t('auth.lastName')"
                size="large"
                clearable
              />
            </el-form-item>
          </el-col>
        </el-row>

        <el-form-item prop="password">
          <el-input
            v-model="form.password"
            type="password"
            :placeholder="$t('auth.password')"
            size="large"
            :prefix-icon="Lock"
            show-password
            clearable
          />
        </el-form-item>

        <el-form-item prop="password_confirm">
          <el-input
            v-model="form.password_confirm"
            type="password"
            :placeholder="$t('auth.confirmPassword')"
            size="large"
            :prefix-icon="Lock"
            show-password
            clearable
            @keyup.enter="handleRegister"
          />
        </el-form-item>

        <el-row :gutter="16">
          <el-col :span="12">
            <el-form-item prop="department">
              <el-input
                v-model="form.department"
                :placeholder="$t('auth.department')"
                size="large"
                clearable
              />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item prop="position">
              <el-input
                v-model="form.position"
                :placeholder="$t('auth.position')"
                size="large"
                clearable
              />
            </el-form-item>
          </el-col>
        </el-row>

        <el-form-item>
          <el-button
            type="primary"
            size="large"
            :loading="loading"
            class="register-button"
            @click="handleRegister"
          >
            {{ $t("auth.register") }}
          </el-button>
        </el-form-item>

        <div class="form-footer">
          <router-link to="/login">{{ $t("auth.hasAccount") }}</router-link>
        </div>
      </el-form>
    </section>
  </div>
</template>

<script setup>
import { computed, reactive, ref } from "vue";
import { useRoute, useRouter } from "vue-router";
import { useI18n } from "vue-i18n";
import { ElMessage } from "element-plus";
import { Lock, Message, Phone, User } from "@element-plus/icons-vue";
import { DEFAULT_AUTHENTICATED_ROUTE } from "@/config/platformModules";
import { useUserStore } from "@/stores/user";

const router = useRouter();
const route = useRoute();
const userStore = useUserStore();
const { t } = useI18n();

const formRef = ref();
const loading = ref(false);
const registerError = ref("");

const form = reactive({
  username: "",
  phone: "",
  email: "",
  first_name: "",
  last_name: "",
  password: "",
  password_confirm: "",
  department: "",
  position: "",
});

const resolvePostRegisterRoute = () => {
  return typeof route.query.redirect === "string" && route.query.redirect
    ? route.query.redirect
    : DEFAULT_AUTHENTICATED_ROUTE;
};

const validatePhone = (rule, value, callback) => {
  if (!value) {
    callback(new Error("请输入手机号"));
  } else if (!/^1[3-9]\d{9}$/.test(value)) {
    callback(new Error("手机号格式不正确"));
  } else {
    callback();
  }
};

const rules = {
  username: [
    {
      required: true,
      message: computed(() => t("auth.usernameRequired")),
      trigger: "blur",
    },
    {
      min: 3,
      max: 20,
      message: computed(() => t("auth.usernameLength")),
      trigger: "blur",
    },
  ],
  phone: [{ required: true, validator: validatePhone, trigger: "blur" }],
  email: [
    {
      required: true,
      message: computed(() => t("auth.emailRequired")),
      trigger: "blur",
    },
    {
      type: "email",
      message: computed(() => t("auth.emailFormat")),
      trigger: "blur",
    },
  ],
  password: [
    {
      required: true,
      message: computed(() => t("auth.passwordRequired")),
      trigger: "blur",
    },
    {
      min: 6,
      message: computed(() => t("auth.passwordLength")),
      trigger: "blur",
    },
  ],
  password_confirm: [
    {
      required: true,
      message: computed(() => t("auth.confirmPasswordRequired")),
      trigger: "blur",
    },
    {
      validator: (rule, value, callback) => {
        if (value !== form.password) {
          callback(new Error(t("auth.passwordMismatch")));
        } else {
          callback();
        }
      },
      trigger: "blur",
    },
  ],
};

const resolveRegisterError = (error, fallback = "注册失败，请稍后重试") => {
  return (
    error?.userMessage ||
    error?.response?.data?.error ||
    error?.response?.data?.detail ||
    error?.response?.data?.message ||
    fallback
  );
};

const handleRegister = async () => {
  if (!formRef.value || loading.value) return;
  registerError.value = "";

  await formRef.value.validate(async (valid) => {
    if (!valid) return;
    loading.value = true;
    try {
      await userStore.register(form);
      ElMessage.success(t("auth.registerSuccess"));
      await router.replace(resolvePostRegisterRoute());
    } catch (error) {
      registerError.value = resolveRegisterError(
        error,
        t("auth.registerFailed"),
      );
    } finally {
      loading.value = false;
    }
  });
};
</script>

<style lang="scss" scoped>
.register-container {
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 40px 20px;
  background:
    radial-gradient(
      circle at 20% 20%,
      rgba(255, 255, 255, 0.28),
      transparent 26%
    ),
    linear-gradient(135deg, #5b7cfa 0%, #7652b8 100%);
}

.register-card {
  width: 100%;
  max-width: 520px;
  padding: 40px;
  background: #fff;
  border-radius: 14px;
  box-shadow: 0 24px 60px rgba(31, 41, 55, 0.18);
}

.form-header {
  text-align: center;
  margin-bottom: 28px;
}

.eyebrow {
  margin: 0 0 8px;
  color: #5b7cfa;
  font-size: 12px;
  letter-spacing: 0.1em;
  text-transform: uppercase;
}

.form-header h2 {
  margin: 0 0 10px;
  color: #1f2937;
  font-size: 28px;
  font-weight: 700;
}

.form-header p {
  margin: 0;
  color: #64748b;
}

.register-error {
  margin-bottom: 16px;
}

.register-button {
  width: 100%;
  height: 44px;
  font-weight: 700;
}

.form-footer {
  text-align: center;
  margin-top: 18px;
}

.form-footer a {
  color: #2563eb;
  text-decoration: none;
  font-weight: 600;
}

.form-footer a:hover {
  text-decoration: underline;
}

@media (max-width: 640px) {
  .register-card {
    padding: 28px 20px;
  }
}
</style>
