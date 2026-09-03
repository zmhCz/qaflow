<template>
  <div class="layout">
    <el-container>
      <el-aside width="240px">
        <div class="logo" @click="router.push(DEFAULT_AUTHENTICATED_ROUTE)">
          <img :src="logoImage" alt="QAFlow" class="logo-img" />
        </div>

        <el-menu
          :default-active="$route.path"
          router
          background-color="#001529"
          text-color="#fff"
          active-text-color="#1890ff"
        >
          <template v-for="item in globalNavigationItems" :key="item.index">
            <el-menu-item :index="item.index">
              <el-icon><component :is="resolveIcon(item.icon)" /></el-icon>
              <span>{{ item.label }}</span>
            </el-menu-item>
          </template>

          <template v-for="item in currentNavigationItems" :key="item.index">
            <el-sub-menu v-if="item.children?.length" :index="item.index">
              <template #title>
                <el-icon><component :is="resolveIcon(item.icon)" /></el-icon>
                <span>{{ item.label }}</span>
              </template>
              <el-menu-item
                v-for="child in item.children"
                :key="child.index"
                :index="child.index"
              >
                <el-icon v-if="child.icon"
                  ><component :is="resolveIcon(child.icon)"
                /></el-icon>
                <span>{{ child.label }}</span>
              </el-menu-item>
            </el-sub-menu>

            <el-menu-item v-else :index="item.index">
              <el-icon><component :is="resolveIcon(item.icon)" /></el-icon>
              <span>{{ item.label }}</span>
            </el-menu-item>
          </template>
        </el-menu>
      </el-aside>

      <el-container>
        <el-header height="60px">
          <div class="header-content">
            <div class="header-left">
              <el-breadcrumb separator="/">
                <el-breadcrumb-item
                  :to="{ path: DEFAULT_AUTHENTICATED_ROUTE }"
                  >{{ $t("nav.home") }}</el-breadcrumb-item
                >
                <el-breadcrumb-item v-if="moduleName">{{
                  moduleName
                }}</el-breadcrumb-item>
                <el-breadcrumb-item>{{ breadcrumbTitle }}</el-breadcrumb-item>
              </el-breadcrumb>
            </div>

            <div class="header-right">
              <el-dropdown
                class="language-dropdown"
                @command="handleLanguageChange"
              >
                <span class="language-selector">
                  <span>{{ currentLanguage }}</span>
                  <el-icon class="el-icon--right"><ArrowDown /></el-icon>
                </span>
                <template #dropdown>
                  <el-dropdown-menu>
                    <el-dropdown-item
                      command="zh-cn"
                      :disabled="appStore.language === 'zh-cn'"
                      >简体中文</el-dropdown-item
                    >
                    <el-dropdown-item
                      command="en"
                      :disabled="appStore.language === 'en'"
                      >English</el-dropdown-item
                    >
                  </el-dropdown-menu>
                </template>
              </el-dropdown>

              <el-dropdown class="user-dropdown" @command="handleCommand">
                <span class="user-info">
                  <el-avatar :size="32" :src="userStore.user?.avatar" />
                  <span class="username">{{ userStore.user?.username }}</span>
                  <el-icon><ArrowDown /></el-icon>
                </span>
                <template #dropdown>
                  <el-dropdown-menu>
                    <el-dropdown-item command="profile">{{
                      $t("nav.profile")
                    }}</el-dropdown-item>
                    <el-dropdown-item divided command="logout">{{
                      $t("nav.logout")
                    }}</el-dropdown-item>
                  </el-dropdown-menu>
                </template>
              </el-dropdown>
            </div>
          </div>
        </el-header>

        <el-main>
          <router-view />
        </el-main>
      </el-container>
    </el-container>
  </div>
</template>

<script setup>
import { computed } from "vue";
import { useRouter, useRoute } from "vue-router";
import { useUserStore } from "@/stores/user";
import { useAppStore } from "@/stores/app";
import { ElMessage } from "element-plus";
import { useI18n } from "vue-i18n";
import {
  buildPlatformNavigation,
  resolveBreadcrumbTitle,
  resolveNavigationModule,
} from "@/config/platformNavigation";
import {
  DEFAULT_AUTHENTICATED_ROUTE,
  LEGACY_HOME_ROUTE,
} from "@/config/platformModules";
import {
  Monitor,
  Folder,
  Document,
  Flag,
  Check,
  Collection,
  VideoPlay,
  DataAnalysis,
  ChatDotRound,
  DocumentCopy,
  Link,
  MagicStick,
  Odometer,
  Timer,
  Setting,
  AlarmClock,
  Bell,
  Aim,
  Edit,
  Cpu,
  ArrowDown,
  Cellphone,
  Connection,
  FolderOpened,
  Grid,
} from "@element-plus/icons-vue";
import logoSvg from "@/assets/images/logo.svg";
import logoHomePng from "@/assets/images/logo_home.png";

const router = useRouter();
const route = useRoute();
const userStore = useUserStore();
const appStore = useAppStore();
const { t } = useI18n();

const iconMap = {
  Monitor,
  Folder,
  Document,
  Flag,
  Check,
  Collection,
  VideoPlay,
  DataAnalysis,
  ChatDotRound,
  DocumentCopy,
  Link,
  MagicStick,
  Odometer,
  Timer,
  Setting,
  AlarmClock,
  Bell,
  Aim,
  Edit,
  Cpu,
  ArrowDown,
  Cellphone,
  Connection,
  FolderOpened,
  Grid,
};

const logoImage = computed(() => {
  return route.path === LEGACY_HOME_ROUTE ? logoSvg : logoHomePng;
});

const currentLanguage = computed(() => {
  return appStore.language === "zh-cn" ? "简体中文" : "English";
});

const navigationState = computed(() => buildPlatformNavigation(t));
const currentNavigation = computed(() =>
  resolveNavigationModule(route.path, t),
);
const globalNavigationItems = computed(() => navigationState.value.globalItems);
const currentNavigationItems = computed(
  () => currentNavigation.value?.menuItems || [],
);
const moduleName = computed(() => currentNavigation.value?.title || "");
const breadcrumbTitle = computed(
  () => resolveBreadcrumbTitle(route.path, t) || route.meta.title || "",
);

const resolveIcon = (iconName) => {
  return iconMap[iconName] || Grid;
};

const handleLanguageChange = (lang) => {
  appStore.setLanguage(lang);
  ElMessage.success(
    lang === "zh-cn" ? "语言已切换为中文" : "Language switched to English",
  );
};

const handleCommand = (command) => {
  if (command === "logout") {
    userStore.logout();
    ElMessage.success("退出登录成功");
    router.push("/login");
    return;
  }

  if (command === "profile") {
    router.push("/ai-generation/profile");
  }
};
</script>

<style lang="scss" scoped>
.layout {
  height: 100vh;
  width: 100vw;
  overflow: hidden;
}

.layout > .el-container {
  height: 100%;
  overflow: hidden;
}

.logo {
  height: 60px;
  display: flex;
  align-items: center;
  justify-content: center;
  background-color: #001529;
  border-bottom: 1px solid #1f1f1f;
  cursor: pointer;
  flex-shrink: 0;

  .logo-img {
    width: 100%;
    height: 100%;
    padding: 8px 18px;
    object-fit: contain;
    background: #fff;
  }
}

.el-aside {
  background-color: #001529;
  height: 100%;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  transition: width 0.3s ease;
  width: 240px !important;

  .el-menu {
    flex: 1;
    overflow-y: auto;
    overflow-x: hidden;
    border-right: none;

    &::-webkit-scrollbar {
      width: 0;
    }
  }
}

.el-menu {
  :deep(.el-sub-menu__title),
  :deep(.el-menu-item) {
    font-size: 14px;
  }
}

.el-header {
  background: #fff;
  border-bottom: 1px solid #e4e7ed;
  padding: 0;
  box-shadow: 0 2px 8px rgba(17, 42, 70, 0.05);
}

.header-content {
  height: 100%;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 20px;
}

.header-left {
  min-width: 0;
}

.header-right {
  display: flex;
  align-items: center;
  gap: 16px;
}

.language-selector,
.user-info {
  display: flex;
  align-items: center;
  gap: 8px;
  cursor: pointer;
  color: #303133;
  white-space: nowrap;
}

.user-info .username {
  color: #303133;
}

.dropdown-flag {
  margin-right: 6px;
}

.el-main {
  background-color: #f5f5f5;
  padding: 20px;
  flex: 1;
  overflow-y: auto;
  overflow-x: hidden;
}

@media screen and (max-width: 1600px) {
  .el-aside {
    width: 200px !important;
  }

  .el-main {
    padding: 16px;
  }
}

@media screen and (max-width: 1280px) {
  .el-aside {
    width: 160px !important;
  }

  .header-content {
    padding: 0 15px;
  }

  .el-main {
    padding: 12px;
  }

  .el-menu {
    :deep(.el-sub-menu__title),
    :deep(.el-menu-item) {
      font-size: 12px;
      padding-left: 15px !important;
    }
  }
}

@media screen and (max-width: 1024px) {
  .el-aside {
    width: 140px !important;
  }

  .el-main {
    padding: 10px;
  }

  .header-content {
    padding: 0 12px;
  }

  .user-info .username {
    display: none;
  }
}

@media screen and (max-width: 768px) {
  .el-aside {
    width: 220px !important;
  }

  .el-main {
    padding: 8px;
  }

  .header-content {
    padding: 0 10px;
  }

  .header-left {
    :deep(.el-breadcrumb__item:not(:last-child)) {
      display: none;
    }
  }
}
</style>
