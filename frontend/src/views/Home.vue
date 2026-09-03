<template>
  <div class="home-container">
    <div class="content-wrapper">
      <div class="header-actions">
        <div class="header-actions-pc">
          <el-dropdown
            class="language-dropdown"
            @command="handleLanguageChange"
          >
            <span class="el-dropdown-link">
              <span class="language-text">{{ currentLanguage }}</span>
              <el-icon class="el-icon--right"><ArrowDown /></el-icon>
            </span>
            <template #dropdown>
              <el-dropdown-menu>
                <el-dropdown-item
                  command="zh-cn"
                  :disabled="currentLanguageCode === 'zh-cn'"
                  >简体中文</el-dropdown-item
                >
                <el-dropdown-item
                  command="en"
                  :disabled="currentLanguageCode === 'en'"
                  >English</el-dropdown-item
                >
              </el-dropdown-menu>
            </template>
          </el-dropdown>

          <el-dropdown @command="handleCommand">
            <span class="el-dropdown-link">
              <el-avatar :size="32" :icon="UserFilled" />
              <span class="username">{{
                userStore.user?.username || $t("home.user")
              }}</span>
              <el-icon class="el-icon--right"><ArrowDown /></el-icon>
            </span>
            <template #dropdown>
              <el-dropdown-menu>
                <el-dropdown-item command="logout">{{
                  $t("home.logout")
                }}</el-dropdown-item>
              </el-dropdown-menu>
            </template>
          </el-dropdown>
        </div>

        <div class="header-actions-mobile">
          <el-dropdown trigger="click" @command="handleHeaderCommand">
            <span class="user-menu-trigger">
              <span class="avatar-wrap">
                <el-avatar :size="28" :icon="UserFilled" />
              </span>
              <el-icon class="trigger-arrow"><ArrowDown /></el-icon>
            </span>
            <template #dropdown>
              <el-dropdown-menu>
                <el-dropdown-item
                  command="zh-cn"
                  :disabled="currentLanguageCode === 'zh-cn'"
                  >简体中文</el-dropdown-item
                >
                <el-dropdown-item
                  command="en"
                  :disabled="currentLanguageCode === 'en'"
                  >English</el-dropdown-item
                >
                <el-dropdown-item command="logout" divided>{{
                  $t("home.logout")
                }}</el-dropdown-item>
              </el-dropdown-menu>
            </template>
          </el-dropdown>
        </div>
      </div>

      <h1 class="main-title">{{ $t("home.title") }}</h1>
      <p class="subtitle">{{ $t("home.subtitle") }}</p>

      <div class="cards-container">
        <div
          v-for="card in homeCards"
          :key="card.key"
          class="nav-card"
          :class="{ 'nav-card-platform': card.key === 'platform' }"
          role="button"
          tabindex="0"
          @click="handleNavigate(card)"
        >
          <div class="card-icon" :class="card.themeClass">
            <el-icon><component :is="resolveIcon(card.icon)" /></el-icon>
          </div>
          <h3>{{ card.title }}</h3>
          <p>{{ card.description }}</p>
        </div>
      </div>
    </div>

    <el-dialog
      v-model="mobileDialogVisible"
      class="mobile-tip-dialog"
      :title="$t('home.mobileTipTitle')"
      width="88%"
      align-center
      :close-on-click-modal="true"
      append-to-body
    >
      <div class="mobile-tip-dialog-body">
        <div class="dialog-icon-wrap">
          <el-icon><Monitor /></el-icon>
        </div>
        <p class="dialog-desc">{{ $t("home.mobileTipDesc") }}</p>
      </div>
      <template #footer>
        <el-button
          type="primary"
          class="dialog-confirm-btn"
          @click="mobileDialogVisible = false"
        >
          {{ $t("home.mobileTipOk") }}
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { computed, onMounted, onUnmounted, ref } from "vue";
import { useRouter } from "vue-router";
import { useI18n } from "vue-i18n";
import { useUserStore } from "@/stores/user";
import { useAppStore } from "@/stores/app";
import { track } from "@/utils/tracker";
import { ElMessage, ElMessageBox } from "element-plus";
import { platformHomeCards } from "@/config/platformModules";
import {
  MagicStick,
  Link,
  Monitor,
  DataLine,
  Cpu,
  Setting,
  ChatDotRound,
  UserFilled,
  ArrowDown,
  Cellphone,
  Grid,
} from "@element-plus/icons-vue";

const router = useRouter();
const { t } = useI18n();
const userStore = useUserStore();
const appStore = useAppStore();

const iconMap = {
  MagicStick,
  Link,
  Monitor,
  DataLine,
  Cpu,
  Setting,
  ChatDotRound,
  Cellphone,
  Grid,
};

const currentLanguageCode = computed(() => appStore.language);
const currentLanguage = computed(() =>
  appStore.language === "zh-cn" ? "简体中文" : "English",
);
const isMobile = ref(false);
const mobileTipDismissed = ref(false);
const MOBILE_BREAKPOINT = 768;
const MOBILE_TIP_STORAGE_KEY = "testhub_home_mobile_tip_seen";

const homeCards = computed(() => {
  return platformHomeCards.map((card) => ({
    ...card,
    title: card.titleKey ? t(card.titleKey) : card.title,
    description: card.descriptionKey
      ? t(card.descriptionKey)
      : card.description,
  }));
});

const resolveIcon = (iconName) => {
  return iconMap[iconName] || Grid;
};

const dismissMobileTip = () => {
  mobileTipDismissed.value = true;
  try {
    localStorage.setItem(MOBILE_TIP_STORAGE_KEY, "1");
  } catch {
    // ignore quota / private mode
  }
};

const mobileDialogVisible = computed({
  get: () => isMobile.value && !mobileTipDismissed.value,
  set: (value) => {
    if (!value) {
      dismissMobileTip();
    }
  },
});

const updateMobileTip = () => {
  isMobile.value = window.matchMedia(
    `(max-width: ${MOBILE_BREAKPOINT}px)`,
  ).matches;
};

onMounted(() => {
  try {
    if (localStorage.getItem(MOBILE_TIP_STORAGE_KEY) === "1") {
      mobileTipDismissed.value = true;
    }
  } catch {
    // ignore
  }

  updateMobileTip();
  window.addEventListener("resize", updateMobileTip);
});

onUnmounted(() => {
  window.removeEventListener("resize", updateMobileTip);
});

const handleLanguageChange = (lang) => {
  appStore.setLanguage(lang);
};

const handleCommand = (command) => {
  if (command === "logout") {
    handleLogout();
  }
};

const handleHeaderCommand = (command) => {
  if (command === "logout") {
    handleLogout();
    return;
  }

  if (command === "zh-cn" || command === "en") {
    appStore.setLanguage(command);
  }
};

const handleLogout = () => {
  ElMessageBox.confirm(t("home.logoutConfirm"), t("common.tips"), {
    confirmButtonText: t("common.confirm"),
    cancelButtonText: t("common.cancel"),
    type: "warning",
  })
    .then(() => {
      userStore.logout();
      router.push("/login");
      ElMessage.success(t("home.logoutSuccess"));
    })
    .catch(() => {});
};

const handleNavigate = (card) => {
  track("module_card_click", {
    event_type: "click",
    module: "home",
    page_path: "/home",
    target_path: card.route,
    metadata: {
      card_type: card.type,
      module_key: card.key,
    },
  });

  router.push(card.route);
};
</script>

<style scoped lang="scss">
.home-container {
  min-height: 100vh;
  background: linear-gradient(135deg, #f5f7fa 0%, #c3cfe2 100%);
  display: flex;
  justify-content: center;
  align-items: center;
  padding: 20px;
}

.content-wrapper {
  text-align: center;
  max-width: 1200px;
  width: 100%;
  position: relative;
}

.nav-card-platform {
  background:
    radial-gradient(
      circle at top right,
      rgba(24, 144, 255, 0.18),
      transparent 35%
    ),
    rgba(255, 255, 255, 0.94);
}

.header-actions {
  position: absolute;
  top: 0;
  right: 0;
  padding: 10px;
}

.header-actions-pc {
  display: flex;
  align-items: center;
  gap: 20px;

  .language-dropdown {
    .el-dropdown-link {
      display: flex;
      align-items: center;
      cursor: pointer;
      color: #5e6d82;
      transition: color 0.3s;
      outline: none;

      &:focus {
        outline: none;
      }

      .language-text {
        margin: 0 5px;
        font-size: 14px;
      }

      &:hover {
        color: #409eff;
      }
    }
  }

  .el-dropdown-link {
    display: flex;
    align-items: center;
    cursor: pointer;
    color: #5e6d82;
    transition: color 0.3s;
    outline: none;

    &:focus {
      outline: none;
    }

    .username {
      margin: 0 8px;
    }

    &:hover {
      color: #409eff;
    }
  }
}

.header-actions-mobile {
  display: none;
}

.main-title {
  font-size: 3rem;
  font-weight: 700;
  color: #2c3e50;
  margin-bottom: 1rem;
  line-height: 1.2;
}

.subtitle {
  font-size: 1.2rem;
  color: #5e6d82;
  margin-bottom: 4rem;
  max-width: 700px;
  margin-left: auto;
  margin-right: auto;
  line-height: 1.6;
}

.cards-container {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
  gap: 24px;
  padding: 20px;
}

.nav-card {
  background: rgba(255, 255, 255, 0.9);
  border-radius: 20px;
  padding: 30px 20px;
  box-shadow: 0 8px 32px rgba(0, 0, 0, 0.08);
  backdrop-filter: blur(10px);
  border: 1px solid rgba(255, 255, 255, 0.2);
  cursor: pointer;
  transition: all 0.3s ease;
  text-align: center;

  &:hover {
    transform: translateY(-8px);
    box-shadow: 0 16px 48px rgba(0, 0, 0, 0.12);
  }

  h3 {
    font-size: 1.35rem;
    font-weight: 600;
    color: #2c3e50;
    margin: 16px 0 12px;
  }

  p {
    font-size: 0.95rem;
    color: #7f8c8d;
    line-height: 1.6;
    margin: 0;
  }
}

.card-icon {
  width: 72px;
  height: 72px;
  border-radius: 18px;
  display: flex;
  align-items: center;
  justify-content: center;
  margin: 0 auto;
  font-size: 34px;
  color: #fff;
}

.platform-icon {
  background: linear-gradient(135deg, #1890ff 0%, #0050b3 100%);
}

.ai-icon {
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
}

.api-icon {
  background: linear-gradient(135deg, #4facfe 0%, #00f2fe 100%);
}

.ui-icon {
  background: linear-gradient(135deg, #43e97b 0%, #38f9d7 100%);
}

.data-icon {
  background: linear-gradient(135deg, #fa709a 0%, #fee140 100%);
}

.app-icon {
  background: linear-gradient(135deg, #ff6b6b 0%, #ee5a6f 100%);
}

.ai-intelligent-icon {
  background: linear-gradient(135deg, #a18cd1 0%, #fbc2eb 100%);
}

.assistant-icon {
  background: linear-gradient(135deg, #f093fb 0%, #f5576c 100%);
}

.config-icon {
  background: linear-gradient(135deg, #96fbc4 0%, #f9f586 100%);
  color: #2c3e50;
}

.header-actions-mobile .user-menu-trigger {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 10px;
  background: rgba(255, 255, 255, 0.9);
  border-radius: 20px;
  cursor: pointer;
}

@media screen and (max-width: 1280px) {
  .main-title {
    font-size: 2.4rem;
  }

  .subtitle {
    font-size: 1rem;
  }

  .cards-container {
    gap: 20px;
    padding: 12px;
    grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
  }

  .nav-card {
    padding: 25px 12px;

    h3 {
      font-size: 1.2rem;
    }
  }

  .card-icon {
    width: 60px;
    height: 60px;
    font-size: 30px;
  }
}

@media screen and (max-width: 1024px) {
  .home-container {
    padding: 15px;
  }

  .main-title {
    font-size: 2.2rem;
  }

  .subtitle {
    font-size: 1rem;
    margin-bottom: 3rem;
  }

  .cards-container {
    gap: 18px;
    padding: 10px;
    grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
  }

  .nav-card {
    padding: 20px 10px;

    h3 {
      font-size: 1.1rem;
    }

    p {
      font-size: 0.9rem;
    }
  }
}

@media screen and (max-width: 768px) {
  .home-container {
    align-items: flex-start;
    padding: 16px;
    padding-top: max(16px, env(safe-area-inset-top));
  }

  .header-actions {
    position: static;
    margin-bottom: 12px;
    padding: 0;
  }

  .header-actions-pc {
    display: none;
  }

  .header-actions-mobile {
    display: flex;
    justify-content: flex-end;
  }

  .main-title {
    font-size: 1.75rem;
    letter-spacing: 0.5px;
    color: #1f2d3d;
    margin-bottom: 8px;
  }

  .subtitle {
    font-size: 0.9375rem;
    color: #7a8494;
    margin: 0 auto 24px;
    max-width: 280px;
    line-height: 1.5;
  }

  .cards-container {
    grid-template-columns: repeat(2, 1fr);
    gap: 14px;
  }

  .nav-card {
    min-height: 148px;
    padding: 18px 12px 16px;
    border-radius: 14px;
    background: rgba(255, 255, 255, 0.88);
    border: 1px solid rgba(255, 255, 255, 0.95);
    box-shadow:
      0 4px 14px rgba(31, 45, 61, 0.07),
      0 1px 3px rgba(31, 45, 61, 0.04);

    &:hover {
      transform: none;
      box-shadow:
        0 6px 18px rgba(31, 45, 61, 0.1),
        0 2px 4px rgba(31, 45, 61, 0.05);
    }

    &:active {
      transform: scale(0.98);
      background: rgba(255, 255, 255, 0.96);
    }

    h3 {
      font-size: 15px;
      margin: 12px 0 6px;
      line-height: 1.35;
    }

    p {
      font-size: 12px;
      line-height: 1.45;
      display: -webkit-box;
      -webkit-line-clamp: 3;
      -webkit-box-orient: vertical;
      overflow: hidden;
    }
  }

  .card-icon {
    width: 48px;
    height: 48px;
    font-size: 24px;
    border-radius: 14px;
  }
}

@media screen and (max-width: 480px) {
  .home-container {
    padding: 12px 12px 20px;
    padding-top: max(12px, env(safe-area-inset-top));
  }

  .header-actions {
    margin-bottom: 16px;
  }

  .main-title {
    font-size: 1.5rem;
  }

  .subtitle {
    font-size: 0.875rem;
    margin-bottom: 20px;
  }

  .cards-container {
    gap: 12px;
  }

  .nav-card {
    min-height: 140px;
    padding: 16px 10px 14px;
    border-radius: 12px;

    h3 {
      font-size: 14px;
      margin: 10px 0 5px;
    }

    p {
      font-size: 11px;
      -webkit-line-clamp: 3;
    }
  }

  .card-icon {
    width: 44px;
    height: 44px;
    font-size: 22px;
    border-radius: 12px;
  }
}
</style>

<style lang="scss">
.mobile-tip-dialog.el-dialog {
  max-width: 340px;
  border-radius: 16px;
  overflow: hidden;

  .el-dialog__header {
    padding: 20px 20px 8px;
    margin-right: 0;
    text-align: center;

    .el-dialog__title {
      font-size: 17px;
      font-weight: 600;
      color: #303133;
      line-height: 1.4;
    }

    .el-dialog__headerbtn {
      top: 14px;
      right: 14px;
    }
  }

  .el-dialog__body {
    padding: 4px 24px 8px;
  }

  .el-dialog__footer {
    padding: 8px 20px 20px;

    .dialog-confirm-btn {
      width: 100%;
      height: 40px;
      border-radius: 20px;
      font-size: 15px;
    }
  }
}

.mobile-tip-dialog-body {
  text-align: center;

  .dialog-icon-wrap {
    width: 56px;
    height: 56px;
    margin: 0 auto 14px;
    border-radius: 14px;
    background: linear-gradient(145deg, #ecf5ff 0%, #d9ecff 100%);
    color: #409eff;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 28px;
  }

  .dialog-desc {
    margin: 0;
    font-size: 14px;
    color: #606266;
    line-height: 1.6;
  }
}
</style>
