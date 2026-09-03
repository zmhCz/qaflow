<template>
  <div class="login-container">
    <section class="showcase-section">
      <div class="language-switcher">
        <el-dropdown @command="handleLanguageChange">
          <span class="language-trigger">
            {{
              currentLanguage === "zh-cn"
                ? $t("auth.languageZhCN")
                : $t("auth.languageEn")
            }}
            <el-icon><ArrowDown /></el-icon>
          </span>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item
                command="zh-cn"
                :disabled="currentLanguage === 'zh-cn'"
              >
                简体中文
              </el-dropdown-item>
              <el-dropdown-item
                command="en"
                :disabled="currentLanguage === 'en'"
              >
                English
              </el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
      </div>

      <div class="showcase-content">
        <div class="brand-header">
          <div class="logo-icon">
            <svg
              viewBox="0 0 24 24"
              fill="none"
              xmlns="http://www.w3.org/2000/svg"
            >
              <path
                d="M12 2L2 7L12 12L22 7L12 2Z"
                stroke="currentColor"
                stroke-width="2"
                stroke-linecap="round"
                stroke-linejoin="round"
              />
              <path
                d="M2 17L12 22L22 17"
                stroke="currentColor"
                stroke-width="2"
                stroke-linecap="round"
                stroke-linejoin="round"
              />
              <path
                d="M2 12L12 17L22 12"
                stroke="currentColor"
                stroke-width="2"
                stroke-linecap="round"
              />
            </svg>
          </div>
          <div>
            <h1>QAFlow</h1>
            <p>AI-Powered Testing Platform</p>
          </div>
        </div>

        <div class="feature-grid">
          <div
            v-for="feature in features"
            :key="feature.title"
            class="feature-card"
          >
            <div class="feature-icon" :style="{ background: feature.color }">
              <component :is="feature.icon" />
            </div>
            <div>
              <h3>{{ feature.title }}</h3>
              <p>{{ feature.description }}</p>
            </div>
          </div>
        </div>
      </div>
    </section>

    <section class="login-section">
      <div class="login-card">
        <div class="form-header">
          <p class="eyebrow">Welcome</p>
          <h2>{{ $t("auth.welcomeBack") }}</h2>
          <p>{{ $t("auth.loginSubtitle") }}</p>
        </div>

        <el-alert
          v-if="loginError"
          :title="loginError"
          type="error"
          show-icon
          :closable="true"
          class="login-error"
          @close="loginError = ''"
        />

        <el-form
          ref="formRef"
          :model="form"
          :rules="rules"
          class="login-form"
          @submit.prevent="handleLogin"
        >
          <el-form-item prop="username">
            <el-input
              v-model="form.username"
              :placeholder="$t('auth.usernamePlaceholder')"
              size="large"
              :prefix-icon="User"
              clearable
            />
          </el-form-item>

          <el-form-item prop="password">
            <el-input
              v-model="form.password"
              type="password"
              :placeholder="$t('auth.passwordPlaceholder')"
              size="large"
              :prefix-icon="Lock"
              show-password
              clearable
              @keyup.enter="handleLogin"
            />
          </el-form-item>

          <el-form-item>
            <el-button
              type="primary"
              size="large"
              :loading="loading"
              class="login-button"
              @click="handleLogin"
            >
              {{ loading ? $t("auth.loggingIn") : $t("auth.login") }}
            </el-button>
          </el-form-item>
        </el-form>

        <div class="form-footer">
          <router-link to="/register" class="register-link">
            {{ $t("auth.noAccount") }} <span>{{ $t("auth.signUpNow") }}</span>
          </router-link>
        </div>

        <p class="bottom-info">{{ $t("auth.copyright") }}</p>
      </div>
    </section>
  </div>
</template>

<script setup>
import { computed, reactive, ref } from "vue";
import { useRoute, useRouter } from "vue-router";
import { useI18n } from "vue-i18n";
import { ElMessage } from "element-plus";
import {
  ArrowDown,
  Connection,
  Document,
  Lock,
  MagicStick,
  TrendCharts,
  User,
} from "@element-plus/icons-vue";
import { DEFAULT_AUTHENTICATED_ROUTE } from "@/config/platformModules";
import { useAppStore } from "@/stores/app";
import { useUserStore } from "@/stores/user";

const router = useRouter();
const route = useRoute();
const userStore = useUserStore();
const appStore = useAppStore();
const { t } = useI18n();

const formRef = ref();
const loading = ref(false);
const loginError = ref("");

const currentLanguage = computed(() => appStore.language);

const form = reactive({
  username: "",
  password: "",
});

const resolvePostLoginRoute = () => {
  return typeof route.query.redirect === "string" && route.query.redirect
    ? route.query.redirect
    : DEFAULT_AUTHENTICATED_ROUTE;
};

const rules = {
  username: [
    {
      required: true,
      message: computed(() => t("auth.usernameRequired")),
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
};

const features = computed(() => [
  {
    icon: Document,
    title: t("auth.aiCaseGeneration"),
    description: t("auth.aiCaseGenerationDesc"),
    color: "linear-gradient(135deg, #4f8cff 0%, #2f54eb 100%)",
  },
  {
    icon: MagicStick,
    title: t("auth.aiIntelligentTesting"),
    description: t("auth.aiIntelligentTestingDesc"),
    color: "linear-gradient(135deg, #33b679 0%, #0f9f6e 100%)",
  },
  {
    icon: Connection,
    title: t("auth.multiTypeTesting"),
    description: t("auth.multiTypeTestingDesc"),
    color: "linear-gradient(135deg, #13c2c2 0%, #08979c 100%)",
  },
  {
    icon: TrendCharts,
    title: t("auth.dataAnalysis"),
    description: t("auth.dataAnalysisDesc"),
    color: "linear-gradient(135deg, #fa8c16 0%, #f5222d 100%)",
  },
]);

const handleLanguageChange = (lang) => {
  appStore.setLanguage(lang);
};

const resolveLoginError = (error, fallback = "登录失败，请稍后重试") => {
  return (
    error?.userMessage ||
    error?.response?.data?.error ||
    error?.response?.data?.detail ||
    error?.response?.data?.message ||
    fallback
  );
};

const submitPasswordLogin = async () => {
  await userStore.login({
    username: form.username,
    password: form.password,
  });
};

const handleLogin = async () => {
  if (!formRef.value || loading.value) return;
  loginError.value = "";

  await formRef.value.validate(async (valid) => {
    if (!valid) return;
    loading.value = true;
    try {
      await submitPasswordLogin();
      ElMessage.success(t("auth.loginSuccess"));
      await router.replace(resolvePostLoginRoute());
    } catch (error) {
      loginError.value = resolveLoginError(error, t("auth.loginFailed"));
    } finally {
      loading.value = false;
    }
  });
};
</script>

<style lang="scss" scoped>
.login-container {
  display: flex;
  min-height: 100vh;
  overflow: hidden;
  background: #f6f8fb;
}

.showcase-section {
  position: relative;
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 64px;
  color: #fff;
  background:
    radial-gradient(
      circle at 18% 20%,
      rgba(255, 255, 255, 0.24),
      transparent 24%
    ),
    radial-gradient(
      circle at 80% 76%,
      rgba(19, 194, 194, 0.26),
      transparent 28%
    ),
    linear-gradient(135deg, #183153 0%, #0f766e 100%);
}

.language-switcher {
  position: absolute;
  top: 24px;
  right: 24px;
}

.language-trigger {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 8px 14px;
  cursor: pointer;
  color: #fff;
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.14);
  border: 1px solid rgba(255, 255, 255, 0.2);
}

.showcase-content {
  width: 100%;
  max-width: 660px;
}

.brand-header {
  display: flex;
  align-items: center;
  gap: 18px;
  margin-bottom: 44px;
}

.logo-icon {
  width: 64px;
  height: 64px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 20px;
  background: rgba(255, 255, 255, 0.16);
  backdrop-filter: blur(12px);
}

.logo-icon svg {
  width: 34px;
  height: 34px;
}

.brand-header h1 {
  margin: 0;
  font-size: 44px;
  letter-spacing: -1px;
}

.brand-header p {
  margin: 6px 0 0;
  opacity: 0.82;
}

.feature-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 18px;
}

.feature-card {
  display: flex;
  gap: 14px;
  padding: 20px;
  border-radius: 18px;
  background: rgba(255, 255, 255, 0.12);
  border: 1px solid rgba(255, 255, 255, 0.16);
  backdrop-filter: blur(12px);
}

.feature-icon {
  width: 46px;
  height: 46px;
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 14px;
}

.feature-icon :deep(svg) {
  width: 22px;
  height: 22px;
}

.feature-card h3 {
  margin: 0 0 8px;
  font-size: 16px;
}

.feature-card p {
  margin: 0;
  opacity: 0.78;
  font-size: 13px;
  line-height: 1.6;
}

.login-section {
  width: 500px;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 48px;
  background: #fff;
}

.login-card {
  width: 100%;
  max-width: 390px;
}

.form-header {
  margin-bottom: 24px;
}

.eyebrow {
  margin: 0 0 8px;
  color: #0f766e;
  font-size: 12px;
  letter-spacing: 0.1em;
  text-transform: uppercase;
}

.form-header h2 {
  margin: 0 0 10px;
  color: #1f2937;
  font-size: 30px;
}

.form-header p {
  margin: 0;
  color: #64748b;
  line-height: 1.6;
}

.login-error {
  margin-bottom: 16px;
}

.login-button {
  width: 100%;
  height: 46px;
  font-weight: 700;
  border: none;
  background: linear-gradient(135deg, #0f766e 0%, #2563eb 100%);
}

.form-footer {
  text-align: center;
}

.register-link {
  color: #64748b;
  text-decoration: none;
}

.register-link span {
  color: #0f766e;
  font-weight: 700;
}

.bottom-info {
  margin-top: 48px;
  text-align: center;
  color: #94a3b8;
  font-size: 12px;
}

@media (max-width: 980px) {
  .login-container {
    flex-direction: column;
  }

  .showcase-section {
    min-height: 42vh;
    padding: 40px 24px;
  }

  .feature-grid {
    grid-template-columns: 1fr;
  }

  .login-section {
    width: 100%;
    padding: 36px 24px;
  }
}

@media (max-width: 640px) {
  .feature-grid {
    display: none;
  }
}
</style>
