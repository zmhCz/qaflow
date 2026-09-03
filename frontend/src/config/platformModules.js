export const DEFAULT_AUTHENTICATED_ROUTE = "/platform/workbench";
export const LEGACY_HOME_ROUTE = "/home";

export const platformModules = [
  {
    key: "platform",
    title: "平台工作台",
    description: "统一查看平台能力、改造阶段和各自动化中心入口。",
    route: DEFAULT_AUTHENTICATED_ROUTE,
    category: "core",
    status: "improving",
    icon: "Grid",
    highlights: ["统一入口", "模块导航", "改造路线"],
    homeCard: {
      type: "platform",
      title: "平台工作台",
      description: "统一查看平台能力地图、改造阶段和各测试中心入口。",
      themeClass: "platform-icon",
    },
  },
  {
    key: "ai-generation",
    title: "AI 用例生成",
    description: "围绕需求分析、用例生成、评审与报告形成完整测试设计闭环。",
    route: "/ai-generation/requirement-analysis",
    category: "workspace",
    status: "online",
    icon: "MagicStick",
    highlights: ["需求分析", "测试用例", "评审报告"],
    homeCard: {
      type: "ai",
      titleKey: "home.aiCaseGeneration",
      descriptionKey: "home.aiCaseGenerationDesc",
      themeClass: "ai-icon",
    },
  },
  {
    key: "api-testing",
    title: "接口测试",
    description: "提供接口项目、环境、自动化执行、报告与调度能力。",
    route: "/api-testing/dashboard",
    category: "automation",
    status: "online",
    icon: "Link",
    highlights: ["项目管理", "自动化执行", "测试报告"],
    homeCard: {
      type: "api",
      titleKey: "home.apiTesting",
      descriptionKey: "home.apiTestingDesc",
      themeClass: "api-icon",
    },
  },
  {
    key: "ui-automation",
    title: "UI 自动化",
    description: "面向 Web UI 自动化的元素、脚本、套件、执行与 AI 能力中心。",
    route: "/ui-automation/dashboard",
    category: "automation",
    status: "online",
    icon: "Monitor",
    highlights: ["元素管理", "脚本管理", "AI 辅助"],
    homeCard: {
      type: "ui",
      titleKey: "home.uiAutomation",
      descriptionKey: "home.uiAutomationDesc",
      themeClass: "ui-icon",
    },
  },
  {
    key: "data-factory",
    title: "数据工厂",
    description: "提供测试数据准备、生成和复用能力，服务多测试链路。",
    route: "/data-factory",
    category: "foundation",
    status: "online",
    icon: "DataLine",
    highlights: ["数据准备", "数据复用", "支撑多模块"],
    homeCard: {
      type: "data",
      titleKey: "home.dataFactory",
      descriptionKey: "home.dataFactoryDesc",
      themeClass: "data-icon",
    },
  },
  {
    key: "app-automation",
    title: "APP 自动化",
    description: "面向移动端设备、包管理、场景编排和执行报告的自动化中心。",
    route: "/app-automation/dashboard",
    category: "automation",
    status: "upgrading",
    icon: "Cellphone",
    highlights: ["设备管理", "场景编排", "执行记录"],
    homeCard: {
      type: "app",
      title: "APP自动化测试",
      description: "基于 Airtest 的 Android APP 自动化测试。",
      themeClass: "app-icon",
    },
  },
  {
    key: "ai-intelligent-mode",
    title: "AI 智能模式",
    description: "聚焦 AI 驱动的测试执行、案例管理与执行记录沉淀。",
    route: "/ai-intelligent-mode/testing",
    category: "workspace",
    status: "online",
    icon: "Cpu",
    highlights: ["智能执行", "案例沉淀", "记录分析"],
    homeCard: {
      type: "ai-intelligent",
      titleKey: "home.aiIntelligentMode",
      descriptionKey: "home.aiIntelligentModeDesc",
      themeClass: "ai-intelligent-icon",
    },
  },
  {
    key: "assistant",
    title: "AI 评测助手",
    description: "提供对话式辅助入口，承接测试设计与执行支持。",
    route: "/ai-generation/assistant",
    category: "workspace",
    status: "online",
    icon: "ChatDotRound",
    highlights: ["对话辅助", "评测支持", "入口聚合"],
    homeCard: {
      type: "assistant",
      titleKey: "home.aiEvaluator",
      descriptionKey: "home.aiEvaluatorDesc",
      themeClass: "assistant-icon",
    },
  },
  {
    key: "configuration",
    title: "配置中心",
    description: "统一管理模型、提示词、环境、调度与外部平台接入配置。",
    route: "/configuration/ai-model",
    category: "foundation",
    status: "online",
    icon: "Setting",
    highlights: ["模型配置", "环境配置", "任务调度"],
    homeCard: {
      type: "config",
      titleKey: "home.configCenter",
      descriptionKey: "home.configCenterDesc",
      themeClass: "config-icon",
    },
  },
];

export const platformWorkbenchSections = [
  {
    key: "core",
    title: "核心工作区",
    description: "平台统一入口和协作视角。",
  },
  {
    key: "workspace",
    title: "智能工作区",
    description: "面向测试设计和 AI 协同的业务工作区。",
  },
  {
    key: "automation",
    title: "自动化中心",
    description: "承载接口、UI、APP 多端自动化能力。",
  },
  {
    key: "foundation",
    title: "平台底座",
    description: "提供配置、数据等共性支撑能力。",
  },
];

export const platformImprovementPhases = [
  {
    phase: "Phase 1",
    title: "统一入口",
    summary: "建立平台工作台、统一导航和模块注册机制。",
  },
  {
    phase: "Phase 2",
    title: "统一对象模型",
    summary: "打通项目、用例、执行、报告等核心对象的跨模块表达。",
  },
  {
    phase: "Phase 3",
    title: "统一流程引擎",
    summary: "串联自然语言生成、自动化执行、报告回流与资产沉淀。",
  },
];

export const platformHomeCards = platformModules
  .filter((module) => module.homeCard)
  .map((module) => ({
    key: module.key,
    route: module.route,
    icon: module.icon,
    ...module.homeCard,
  }));

export const platformHomeEntryMap = platformHomeCards.reduce(
  (accumulator, item) => {
    accumulator[item.type] = item.route;
    return accumulator;
  },
  {},
);
