import { DEFAULT_AUTHENTICATED_ROUTE } from "@/config/platformModules";

const GLOBAL_NAVIGATION_ITEMS = [
  {
    index: DEFAULT_AUTHENTICATED_ROUTE,
    icon: "Grid",
    label: "平台工作台",
  },
];

const NAVIGATION_MODULES = [
  {
    key: "platform",
    matchPrefix: "/platform",
    title: "平台工作台",
    menuItems: [
      { index: "/platform/assets", icon: "Collection", label: "测试资产中心" },
      {
        index: "/platform/executions",
        icon: "VideoPlay",
        label: "统一执行中心",
      },
      {
        index: "/platform/evidence",
        icon: "DataAnalysis",
        label: "测试证据中心",
      },
      { index: "/platform/backlog", icon: "Warning", label: "质量待办中心" },
      { index: "/platform/config", icon: "Setting", label: "场景配置中心" },
      {
        index: "/platform/quality-dashboard",
        icon: "TrendCharts",
        label: "质量看板",
      },
      {
        index: "/platform/delivery",
        icon: "Promotion",
        label: "通知与交付出口",
      },
    ],
  },
  {
    key: "ai-generation",
    matchPrefix: "/ai-generation",
    titleKey: "modules.aiGeneration",
    menuItems: [
      {
        index: "requirement",
        icon: "MagicStick",
        labelKey: "menu.intelligentCaseGeneration",
        children: [
          {
            index: "/ai-generation/requirement-analysis",
            labelKey: "menu.aiCaseGeneration",
          },
          {
            index: "/ai-generation/generated-testcases",
            labelKey: "menu.aiGeneratedTestcases",
          },
        ],
      },
      {
        index: "/ai-generation/projects",
        icon: "Folder",
        labelKey: "menu.projectManagement",
      },
      {
        index: "/ai-generation/testcases",
        icon: "Document",
        labelKey: "menu.testCases",
      },
      {
        index: "/ai-generation/versions",
        icon: "Flag",
        labelKey: "menu.versionManagement",
      },
      {
        index: "reviews",
        icon: "Check",
        labelKey: "menu.reviewManagement",
        children: [
          { index: "/ai-generation/reviews", labelKey: "menu.reviewList" },
          {
            index: "/ai-generation/review-templates",
            labelKey: "menu.reviewTemplates",
          },
        ],
      },
      {
        index: "/ai-generation/executions",
        icon: "VideoPlay",
        labelKey: "menu.testPlan",
      },
      {
        index: "/ai-generation/reports",
        icon: "DataAnalysis",
        labelKey: "menu.testReport",
      },
    ],
  },
  {
    key: "api-testing",
    matchPrefix: "/api-testing",
    titleKey: "modules.apiTesting",
    menuItems: [
      {
        index: "/api-testing/dashboard",
        icon: "Odometer",
        labelKey: "menu.dashboard",
      },
      {
        index: "/api-testing/projects",
        icon: "Folder",
        labelKey: "menu.projectManagement",
      },
      {
        index: "/api-testing/interfaces",
        icon: "Link",
        labelKey: "menu.interfaceManagement",
      },
      {
        index: "/api-testing/automation",
        icon: "VideoPlay",
        labelKey: "menu.automationTesting",
      },
      {
        index: "/api-testing/history",
        icon: "Timer",
        labelKey: "menu.requestHistory",
      },
      {
        index: "/api-testing/environments",
        icon: "Setting",
        labelKey: "menu.environmentManagement",
      },
      {
        index: "/api-testing/reports",
        icon: "DataAnalysis",
        labelKey: "menu.testReport",
      },
      {
        index: "/api-testing/scheduled-tasks",
        icon: "AlarmClock",
        labelKey: "menu.scheduledTasks",
      },
      {
        index: "/api-testing/notification-logs",
        icon: "Bell",
        labelKey: "menu.notificationList",
      },
    ],
  },
  {
    key: "ui-automation",
    matchPrefix: "/ui-automation",
    titleKey: "modules.uiAutomation",
    menuItems: [
      {
        index: "/ui-automation/dashboard",
        icon: "Odometer",
        labelKey: "menu.dashboard",
      },
      {
        index: "/ui-automation/projects",
        icon: "Folder",
        labelKey: "menu.projectManagement",
      },
      {
        index: "/ui-automation/elements-enhanced",
        icon: "Aim",
        labelKey: "menu.elementManagement",
      },
      {
        index: "/ui-automation/test-cases",
        icon: "Document",
        labelKey: "menu.caseManagement",
      },
      {
        index: "/ui-automation/scripts-enhanced",
        icon: "Edit",
        labelKey: "menu.scriptGeneration",
      },
      {
        index: "/ui-automation/scripts",
        icon: "DocumentCopy",
        labelKey: "menu.scriptList",
      },
      {
        index: "/ui-automation/suites",
        icon: "Collection",
        labelKey: "menu.suiteManagement",
      },
      {
        index: "/ui-automation/executions",
        icon: "VideoPlay",
        labelKey: "menu.executionRecords",
      },
      {
        index: "/ui-automation/reports",
        icon: "DataAnalysis",
        labelKey: "menu.testReport",
      },
      {
        index: "/ui-automation/scheduled-tasks",
        icon: "AlarmClock",
        labelKey: "menu.scheduledTasks",
      },
      {
        index: "/ui-automation/notification-logs",
        icon: "Bell",
        labelKey: "menu.notificationList",
      },
    ],
  },
  {
    key: "app-automation",
    matchPrefix: "/app-automation",
    title: "APP自动化测试",
    menuItems: [
      {
        index: "/app-automation/dashboard",
        icon: "Odometer",
        label: "Dashboard",
      },
      { index: "/app-automation/projects", icon: "Folder", label: "项目管理" },
      {
        index: "/app-automation/devices",
        icon: "Cellphone",
        label: "设备管理",
      },
      {
        index: "/app-automation/execution-agents",
        icon: "Monitor",
        label: "执行机 Agent",
      },
      {
        index: "/app-automation/packages",
        icon: "Collection",
        label: "包名管理",
      },
      { index: "/app-automation/elements", icon: "Aim", label: "元素管理" },
      {
        index: "/app-automation/semantic-elements",
        icon: "Edit",
        label: "语义库工作台",
      },
      {
        index: "/app-automation/semantic-dictionaries",
        icon: "Memo",
        label: "语义字典",
      },
      {
        index: "/app-automation/page-capture",
        icon: "Connection",
        label: "交互录制台",
      },
      {
        index: "/app-automation/recorder",
        icon: "VideoCamera",
        label: "操作录制器",
      },
      {
        index: "/app-automation/scene-builder",
        icon: "Connection",
        label: "用例编排",
      },
      {
        index: "/app-automation/exploration",
        icon: "MagicStick",
        label: "AI 探索测试",
      },
      { index: "/app-automation/page-map", icon: "Share", label: "页面地图" },
      {
        index: "/app-automation/test-cases",
        icon: "Document",
        label: "测试用例",
      },
      {
        index: "/app-automation/test-suites",
        icon: "FolderOpened",
        label: "测试套件",
      },
      {
        index: "/app-automation/executions",
        icon: "VideoPlay",
        label: "执行记录",
      },
      {
        index: "/app-automation/reports",
        icon: "DataAnalysis",
        label: "测试报告",
      },
      {
        index: "/app-automation/scheduled-tasks",
        icon: "AlarmClock",
        label: "定时任务",
      },
      {
        index: "/app-automation/notification-logs",
        icon: "Bell",
        label: "通知列表",
      },
    ],
  },
  {
    key: "ai-intelligent-mode",
    matchPrefix: "/ai-intelligent-mode",
    titleKey: "modules.aiIntelligentMode",
    menuItems: [
      {
        index: "/ai-intelligent-mode/testing",
        icon: "VideoPlay",
        labelKey: "menu.aiIntelligentTesting",
      },
      {
        index: "/ai-intelligent-mode/cases",
        icon: "Document",
        labelKey: "menu.aiCaseManagement",
      },
      {
        index: "/ai-intelligent-mode/execution-records",
        icon: "Timer",
        labelKey: "menu.aiExecutionRecords",
      },
    ],
  },
  {
    key: "configuration",
    matchPrefix: "/configuration",
    titleKey: "modules.configuration",
    menuItems: [
      {
        index: "ai-case-generation",
        icon: "MagicStick",
        labelKey: "menu.aiCaseGenerationConfig",
        children: [
          {
            index: "/configuration/ai-model",
            icon: "Cpu",
            labelKey: "menu.aiModelConfig",
          },
          {
            index: "/configuration/prompt-config",
            icon: "Edit",
            labelKey: "menu.promptConfig",
          },
          {
            index: "/configuration/generation-config",
            icon: "Setting",
            labelKey: "menu.generationConfig",
          },
        ],
      },
      {
        index: "/configuration/app-exploration-model",
        icon: "MagicStick",
        label: "AI探索模型配置",
      },
      {
        index: "/configuration/ui-env",
        icon: "Monitor",
        labelKey: "menu.uiEnvConfig",
      },
      {
        index: "/configuration/app-env",
        icon: "Cellphone",
        label: "APP环境配置",
      },
      {
        index: "/configuration/ai-mode",
        icon: "MagicStick",
        labelKey: "menu.aiModeConfig",
      },
      {
        index: "/configuration/scheduled-task",
        icon: "Timer",
        labelKey: "menu.scheduledTaskConfig",
      },
      {
        index: "/configuration/dify",
        icon: "ChatDotRound",
        labelKey: "menu.difyConfig",
      },
    ],
  },
];

const EXTRA_BREADCRUMB_ITEMS = [
  {
    index: "/ai-generation/profile",
    labelKey: "nav.profile",
  },
];

const resolveText = (t, item) => {
  if (item.labelKey) {
    return t(item.labelKey);
  }
  if (item.titleKey) {
    return t(item.titleKey);
  }
  return item.label || item.title || "";
};

const resolveMenuItem = (t, item) => {
  const resolved = {
    ...item,
    label: resolveText(t, item),
  };

  if (item.children?.length) {
    resolved.children = item.children.map((child) => resolveMenuItem(t, child));
  }

  return resolved;
};

const flattenMenuItems = (items, bucket = []) => {
  items.forEach((item) => {
    if (item.index?.startsWith("/")) {
      bucket.push(item);
    }

    if (item.children?.length) {
      flattenMenuItems(item.children, bucket);
    }
  });

  return bucket;
};

export const buildPlatformNavigation = (t) => {
  const globalItems = GLOBAL_NAVIGATION_ITEMS.map((item) =>
    resolveMenuItem(t, item),
  );
  const modules = NAVIGATION_MODULES.map((module) => ({
    ...module,
    title: resolveText(t, module),
    menuItems: module.menuItems.map((item) => resolveMenuItem(t, item)),
  }));
  const extraBreadcrumbItems = EXTRA_BREADCRUMB_ITEMS.map((item) =>
    resolveMenuItem(t, item),
  );

  return {
    globalItems,
    modules,
    extraBreadcrumbItems,
  };
};

export const resolveNavigationModule = (path, t) => {
  const navigation = buildPlatformNavigation(t);
  return (
    navigation.modules.find((module) => path.startsWith(module.matchPrefix)) ||
    null
  );
};

export const resolveBreadcrumbTitle = (path, t) => {
  const navigation = buildPlatformNavigation(t);
  const directMatches = [
    ...flattenMenuItems(navigation.globalItems),
    ...navigation.modules.flatMap((module) =>
      flattenMenuItems(module.menuItems),
    ),
    ...navigation.extraBreadcrumbItems,
  ];

  return directMatches.find((item) => item.index === path)?.label || "";
};
