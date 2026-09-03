import { createRouter, createWebHistory } from "vue-router";
import { useUserStore } from "@/stores/user";
import { trackPageView } from "@/utils/tracker";
import {
  DEFAULT_AUTHENTICATED_ROUTE,
  LEGACY_HOME_ROUTE,
} from "@/config/platformModules";

// 闈欐€佸鍏ュ父鐢ㄧ粍浠舵潵閬垮厤鍔ㄦ€佸鍏ラ棶棰?
import Login from "@/views/auth/Login.vue";
import Register from "@/views/auth/Register.vue";
import Layout from "@/layout/index.vue";
import ProjectList from "@/views/projects/ProjectList.vue";
import Home from "@/views/Home.vue";
import DataFactory from "@/views/data-factory/DataFactory.vue";
import ApiDashboard from "@/views/api-testing/Dashboard.vue";
import ApiProjectManagement from "@/views/api-testing/ProjectManagement.vue";
import ApiInterfaceManagement from "@/views/api-testing/InterfaceManagement.vue";
import ApiAutomationTesting from "@/views/api-testing/AutomationTesting.vue";
import ApiRequestHistory from "@/views/api-testing/RequestHistory.vue";
import ApiEnvironmentManagement from "@/views/api-testing/EnvironmentManagement.vue";
import ApiReportView from "@/views/api-testing/ReportView.vue";
import ApiScheduledTasks from "@/views/api-testing/ScheduledTasks.vue";
import ApiAIServiceConfig from "@/views/api-testing/AIServiceConfig.vue";
import NotificationLogs from "@/views/notification/NotificationLogs.vue";
import UiDashboard from "@/views/ui-automation/dashboard/Dashboard.vue";
import UiProjectList from "@/views/ui-automation/projects/ProjectList.vue";
import UiElementManagerEnhanced from "@/views/ui-automation/elements/ElementManagerEnhanced.vue";
import UiTestCaseManager from "@/views/ui-automation/test-cases/TestCaseManager.vue";
import UiScriptEditorEnhanced from "@/views/ui-automation/scripts/ScriptEditorEnhanced.vue";
import UiScriptList from "@/views/ui-automation/scripts/ScriptList.vue";
import UiSuiteList from "@/views/ui-automation/suites/SuiteList.vue";
import UiExecutionList from "@/views/ui-automation/executions/ExecutionList.vue";
import UiReportList from "@/views/ui-automation/reports/ReportList.vue";
import UiScheduledTasks from "@/views/ui-automation/scheduled-tasks/ScheduledTasks.vue";
import UiNotificationLogs from "@/views/ui-automation/notification/NotificationLogs.vue";
import UiAITesting from "@/views/ui-automation/ai/AITesting.vue";
import UiAICaseList from "@/views/ui-automation/ai/AICaseList.vue";
import UiAIExecutionRecords from "@/views/ui-automation/ai/AIExecutionRecords.vue";

/** @type {import('vue-router').RouteRecordRaw[]} */
const routes = [
  {
    path: "/",
    redirect: (to) => ({ path: DEFAULT_AUTHENTICATED_ROUTE, query: to.query }),
  },
  {
    path: LEGACY_HOME_ROUTE,
    name: "Home",
    component: Home,
    meta: { requiresAuth: true },
  },
  {
    path: "/platform",
    component: Layout,
    meta: { requiresAuth: true },
    children: [
      {
        path: "",
        redirect: "workbench",
      },
      {
        path: "workbench",
        name: "PlatformWorkbench",
        component: () => import("@/views/platform/PlatformWorkbench.vue"),
      },
      {
        path: "assets",
        name: "PlatformTestAssetCenter",
        component: () => import("@/views/platform/TestAssetCenter.vue"),
        meta: { title: "测试资产中心" },
      },
      {
        path: "evidence",
        name: "PlatformEvidenceCenter",
        component: () => import("@/views/platform/EvidenceCenter.vue"),
        meta: { title: "测试证据中心" },
      },
      {
        path: "executions",
        name: "PlatformExecutionCenter",
        component: () => import("@/views/platform/ExecutionCenter.vue"),
        meta: { title: "统一执行中心" },
      },
      {
        path: "backlog",
        name: "PlatformQualityBacklog",
        component: () => import("@/views/platform/QualityBacklog.vue"),
        meta: { title: "质量待办中心" },
      },
      {
        path: "config",
        name: "PlatformConfigHub",
        component: () => import("@/views/platform/PlatformConfigHub.vue"),
        meta: { title: "场景配置中心" },
      },
      {
        path: "quality-dashboard",
        name: "PlatformQualityDashboard",
        component: () => import("@/views/platform/QualityDashboard.vue"),
        meta: { title: "质量看板" },
      },
      {
        path: "delivery",
        name: "PlatformDeliveryHub",
        component: () => import("@/views/platform/DeliveryHub.vue"),
        meta: { title: "通知与交付出口" },
      },
    ],
  },
  {
    path: "/login",
    name: "Login",
    component: Login,
    meta: { requiresGuest: true },
  },
  {
    path: "/register",
    name: "Register",
    component: Register,
    meta: { requiresGuest: true },
  },
  {
    path: "/ai-generation/assistant",
    name: "Assistant",
    component: () => import("@/views/assistant/AssistantView.vue"),
    meta: { requiresAuth: true },
  },
  {
    path: "/ai-generation",
    component: Layout,
    meta: { requiresAuth: true },
    children: [
      {
        path: "",
        redirect: "requirement-analysis",
      },
      {
        path: "requirement-analysis",
        name: "RequirementAnalysis",
        component: () =>
          import("@/views/requirement-analysis/RequirementAnalysisView.vue"),
      },
      {
        path: "projects",
        name: "Projects",
        component: ProjectList,
      },
      {
        path: "projects/:id",
        name: "ProjectDetail",
        component: () => import("@/views/projects/ProjectDetail.vue"),
      },
      {
        path: "testcases",
        name: "TestCases",
        component: () => import("@/views/testcases/TestCaseList.vue"),
      },
      {
        path: "testcases/import-records",
        name: "TestCaseImportRecords",
        component: () =>
          import("@/views/testcases/TestCaseImportRecordList.vue"),
      },
      {
        path: "testcases/create",
        name: "CreateTestCase",
        component: () => import("@/views/testcases/TestCaseForm.vue"),
      },
      {
        path: "testcases/:id",
        name: "TestCaseDetail",
        component: () => import("@/views/testcases/TestCaseDetail.vue"),
      },
      {
        path: "testcases/:id/edit",
        name: "EditTestCase",
        component: () => import("@/views/testcases/TestCaseEdit.vue"),
      },
      {
        path: "versions",
        name: "Versions",
        component: () => import("@/views/versions/VersionList.vue"),
      },
      {
        path: "reviews",
        name: "Reviews",
        component: () => import("@/views/reviews/ReviewList.vue"),
      },
      {
        path: "reviews/create",
        name: "CreateReview",
        component: () => import("@/views/reviews/ReviewForm.vue"),
      },
      {
        path: "reviews/:id",
        name: "ReviewDetail",
        component: () => import("@/views/reviews/ReviewDetail.vue"),
      },
      {
        path: "reviews/:id/edit",
        name: "EditReview",
        component: () => import("@/views/reviews/ReviewForm.vue"),
      },
      {
        path: "review-templates",
        name: "ReviewTemplates",
        component: () => import("@/views/reviews/ReviewTemplateList.vue"),
      },
      {
        path: "testsuites",
        name: "TestSuites",
        component: () => import("@/views/testsuites/TestSuiteList.vue"),
      },
      {
        path: "executions",
        name: "Executions",
        component: () => import("@/views/executions/ExecutionListView.vue"),
      },
      {
        path: "executions/:id",
        name: "ExecutionDetail",
        component: () => import("@/views/executions/ExecutionDetailView.vue"),
      },
      {
        path: "reports",
        name: "AiTestReport",
        component: () => import("@/views/reports/AiTestReport.vue"),
      },
      {
        path: "generated-testcases",
        name: "GeneratedTestCases",
        component: () =>
          import("@/views/requirement-analysis/GeneratedTestCaseList.vue"),
      },
      {
        path: "task-detail/:taskId",
        name: "TaskDetail",
        component: () => import("@/views/requirement-analysis/TaskDetail.vue"),
      },
      {
        path: "profile",
        name: "Profile",
        component: () => import("@/views/profile/UserProfile.vue"),
      },
    ],
  },
  {
    path: "/api-testing",
    component: Layout,
    meta: { requiresAuth: true },
    children: [
      {
        path: "",
        redirect: "dashboard",
      },
      {
        path: "dashboard",
        name: "ApiDashboard",
        component: ApiDashboard,
      },
      {
        path: "projects",
        name: "ApiProjects",
        component: ApiProjectManagement,
      },
      {
        path: "interfaces",
        name: "ApiInterfaces",
        component: ApiInterfaceManagement,
      },
      {
        path: "automation",
        name: "ApiAutomation",
        component: ApiAutomationTesting,
      },
      {
        path: "history",
        name: "ApiHistory",
        component: ApiRequestHistory,
      },
      {
        path: "environments",
        name: "ApiEnvironments",
        component: ApiEnvironmentManagement,
      },
      {
        path: "reports",
        name: "ApiReports",
        component: ApiReportView,
      },
      {
        path: "scheduled-tasks",
        name: "ApiScheduledTasks",
        component: ApiScheduledTasks,
      },
      {
        path: "ai-service-config",
        name: "ApiAIServiceConfig",
        component: ApiAIServiceConfig,
      },
      {
        path: "notification-logs",
        name: "ApiNotificationLogs",
        component: NotificationLogs,
      },
    ],
  },
  {
    path: "/ui-automation",
    component: Layout,
    meta: { requiresAuth: true },
    children: [
      {
        path: "",
        redirect: "dashboard",
      },
      {
        path: "dashboard",
        name: "UiDashboard",
        component: UiDashboard,
      },
      {
        path: "projects",
        name: "UiProjects",
        component: UiProjectList,
      },
      {
        path: "elements-enhanced",
        name: "UiElementsEnhanced",
        component: UiElementManagerEnhanced,
      },
      {
        path: "test-cases",
        name: "UiTestCases",
        component: UiTestCaseManager,
      },
      {
        path: "scripts-enhanced",
        name: "UiScriptsEnhanced",
        component: UiScriptEditorEnhanced,
      },
      {
        path: "scripts/editor",
        name: "UiScriptEditor",
        component: UiScriptEditorEnhanced,
      },
      {
        path: "scripts",
        name: "UiScripts",
        component: UiScriptList,
      },
      {
        path: "suites",
        name: "UiSuites",
        component: UiSuiteList,
      },
      {
        path: "executions",
        name: "UiExecutions",
        component: UiExecutionList,
      },
      {
        path: "reports",
        name: "UiReports",
        component: UiReportList,
      },
      {
        path: "scheduled-tasks",
        name: "UiScheduledTasks",
        component: UiScheduledTasks,
      },
      {
        path: "notification-logs",
        name: "UiNotificationLogs",
        component: UiNotificationLogs,
      },
    ],
  },
  {
    path: "/ai-intelligent-mode",
    component: Layout,
    meta: { requiresAuth: true },
    children: [
      {
        path: "",
        redirect: "testing",
      },
      {
        path: "testing",
        name: "AITesting",
        component: UiAITesting,
      },
      {
        path: "cases",
        name: "AICaseList",
        component: UiAICaseList,
      },
      {
        path: "execution-records",
        name: "AIExecutionRecords",
        component: UiAIExecutionRecords,
      },
    ],
  },
  {
    path: "/data-factory",
    name: "DataFactory",
    component: DataFactory,
    meta: { requiresAuth: true },
  },
  {
    path: "/configuration",
    component: Layout,
    meta: { requiresAuth: true },
    children: [
      {
        path: "",
        component: () =>
          import("@/views/configuration/ConfigurationCenter.vue"),
        children: [
          {
            path: "",
            redirect: "ai-model",
          },
          {
            path: "ai-model",
            name: "ConfigAIModel",
            component: () =>
              import("@/views/requirement-analysis/AIModelConfig.vue"),
          },
          {
            path: "app-exploration-model",
            name: "ConfigAppExplorationModel",
            component: () =>
              import("@/views/requirement-analysis/AIModelConfig.vue"),
            meta: { aiModelScope: "app_exploration" },
          },
          {
            path: "prompt-config",
            name: "ConfigPromptConfig",
            component: () =>
              import("@/views/requirement-analysis/PromptConfig.vue"),
          },
          {
            path: "app-exploration-prompt",
            name: "ConfigAppExplorationPrompt",
            component: () =>
              import("@/views/requirement-analysis/PromptConfig.vue"),
            meta: { promptScope: "app_exploration" },
          },
          {
            path: "generation-config",
            name: "ConfigGenerationConfig",
            component: () =>
              import("@/views/requirement-analysis/GenerationConfigView.vue"),
          },
          {
            path: "ui-env",
            name: "ConfigUIEnv",
            component: () =>
              import("@/views/configuration/UIEnvironmentConfig.vue"),
          },
          {
            path: "app-env",
            name: "ConfigAppEnv",
            component: () =>
              import("@/views/app-automation/settings/AppSettings.vue"),
          },
          {
            path: "ai-mode",
            name: "ConfigAIMode",
            component: () =>
              import("@/views/configuration/AIIntelligentModeConfig.vue"),
          },
          {
            path: "scheduled-task",
            name: "ConfigScheduledTask",
            component: () =>
              import("@/views/ui-automation/notification/NotificationConfigs.vue"),
          },
          {
            path: "dify",
            name: "DifyConfig",
            component: () => import("@/views/configuration/DifyConfig.vue"),
          },
        ],
      },
    ],
  },
  // APP鑷姩鍖栨祴璇曡矾鐢?
  {
    path: "/app-automation",
    component: Layout,
    meta: { requiresAuth: true },
    children: [
      {
        path: "",
        redirect: "dashboard",
      },
      {
        path: "dashboard",
        name: "AppAutomationDashboard",
        component: () =>
          import("@/views/app-automation/dashboard/Dashboard.vue"),
      },
      {
        path: "projects",
        name: "AppProjectList",
        component: () =>
          import("@/views/app-automation/projects/ProjectList.vue"),
      },
      {
        path: "devices",
        name: "AppDeviceList",
        component: () =>
          import("@/views/app-automation/devices/DeviceList.vue"),
      },
      {
        path: "packages",
        name: "AppPackageList",
        component: () =>
          import("@/views/app-automation/packages/PackageList.vue"),
      },
      {
        path: "elements",
        name: "AppElementList",
        component: () =>
          import("@/views/app-automation/elements/ElementList.vue"),
      },
      {
        path: "semantic-elements",
        name: "AppSemanticElementWorkbench",
        component: () =>
          import("@/views/app-automation/elements/SemanticElementWorkbench.vue"),
        meta: { title: "语义库工作台" },
      },
      {
        path: "semantic-dictionaries",
        name: "AppSemanticDictionary",
        component: () =>
          import("@/views/app-automation/elements/SemanticDictionary.vue"),
        meta: { title: "语义字典" },
      },
      {
        path: "page-capture",
        name: "AppPageCaptureWorkbench",
        component: () =>
          import("@/views/app-automation/elements/PageCaptureWorkbench.vue"),
        meta: { title: "交互录制台" },
      },
      {
        path: "recorder",
        name: "AppRecordingStudio",
        component: () =>
          import("@/views/app-automation/recorder/RecordingStudio.vue"),
        meta: { title: "操作录制器" },
      },
      {
        path: "scene-builder",
        name: "AppSceneBuilder",
        component: () =>
          import("@/views/app-automation/test-cases/SceneBuilder.vue"),
        meta: { title: "鐢ㄤ緥缂栨帓" },
      },
      {
        path: "exploration",
        name: "AppExplorationTesting",
        component: () =>
          import("@/views/app-automation/exploration/ExplorationTesting.vue"),
        meta: { title: "AI 探索测试" },
      },
      {
        path: "page-map",
        name: "AppPageMapWorkbench",
        component: () =>
          import("@/views/app-automation/exploration/PageMapWorkbench.vue"),
        meta: { title: "页面地图" },
      },
      {
        path: "test-cases",
        name: "AppTestCaseList",
        component: () =>
          import("@/views/app-automation/test-cases/TestCaseList.vue"),
      },
      {
        path: "test-suites",
        name: "AppTestSuiteList",
        component: () => import("@/views/app-automation/suites/SuiteList.vue"),
      },
      {
        path: "scheduled-tasks",
        name: "AppScheduledTasks",
        component: () =>
          import("@/views/app-automation/scheduled-tasks/ScheduledTasks.vue"),
      },
      {
        path: "notification-logs",
        name: "AppNotificationLogs",
        component: () =>
          import("@/views/app-automation/notification/NotificationLogs.vue"),
      },
      {
        path: "executions",
        name: "AppExecutionList",
        component: () =>
          import("@/views/app-automation/executions/ExecutionList.vue"),
      },
      {
        path: "reports",
        name: "AppReportList",
        component: () =>
          import("@/views/app-automation/reports/ReportList.vue"),
      },
    ],
  },
];

const router = createRouter({
  history: createWebHistory(),
  routes,
});

router.beforeEach(async (to, _from, next) => {
  const userStore = useUserStore();

  // SSO 鎺堟潈鐮佷氦鎹細鍦ㄧ櫥褰曟€佹鏌ヤ箣鍓嶏紝鍏堟妸 URL 涓殑 code 鎹㈡垚 JWT
  const code = to.query.code;
  if (code && !userStore.accessToken) {
    try {
      const api = (await import("@/utils/api")).default;
      const response = await api.post("/auth/exchange-token/", {
        action: "redeem",
        code: code,
      });
      const expiresAt = Date.now() + 30 * 60 * 1000;
      localStorage.setItem("access_token", response.data.access);
      localStorage.setItem("refresh_token", response.data.refresh);
      localStorage.setItem("token_expires_at", expiresAt.toString());
      localStorage.setItem("user", JSON.stringify(response.data.user));
      userStore.accessToken = response.data.access;
      userStore.refreshToken = response.data.refresh;
      userStore.tokenExpiresAt = expiresAt;
      userStore.user = response.data.user;

      // 娓呴櫎 URL 涓殑 code锛屼娇鐢?replace 閬垮厤浜х敓澶氫綑鍘嗗彶璁板綍
      const query = { ...to.query };
      delete query.code;
      next({ path: to.path, query, replace: true });
      return;
    } catch {
      // code 鏃犳晥鎴栧凡杩囨湡锛岀户缁甯告祦绋?
    }
  }

  // 鏈?token 浣嗘病鏈夌敤鎴蜂俊鎭椂锛屽垵濮嬪寲璁よ瘉
  if (!userStore.user && userStore.accessToken) {
    try {
      await userStore.initAuth();
    } catch (error) {
      console.error("璁よ瘉鍒濆鍖栧け璐?", error);
    }
  }

  if (to.meta.requiresAuth && !userStore.isAuthenticated) {
    next({
      path: "/login",
      query: {
        redirect: to.fullPath || to.path,
      },
    });
  } else if (to.meta.requiresGuest && userStore.isAuthenticated) {
    next(DEFAULT_AUTHENTICATED_ROUTE);
  } else {
    next();
  }
});

router.afterEach((to, from) => {
  trackPageView(to, from);
});

export default router;
