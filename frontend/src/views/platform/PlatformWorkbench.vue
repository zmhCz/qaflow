<template>
  <div class="platform-workbench">
    <section class="hero-section">
      <div class="hero-copy">
        <span class="eyebrow">Platform Upgrade</span>
        <h1>QAFlow 平台工作台</h1>
        <p>
          把分散的测试能力收拢成统一平台入口，先完成导航、模块和改造阶段的可视化，再逐步推进对象模型和流程引擎统一。
        </p>
        <div class="hero-actions">
          <el-button type="primary" size="large" @click="goToFirstAutomation">
            进入自动化中心
          </el-button>
          <el-button
            size="large"
            plain
            @click="navigate('/app-automation/exploration')"
          >
            继续 AI 探索
          </el-button>
          <el-button size="large" plain @click="navigate('/platform/backlog')">
            查看质量待办
          </el-button>
          <el-button
            size="large"
            plain
            @click="navigate('/platform/quality-dashboard')"
          >
            查看质量看板
          </el-button>
          <el-button size="large" plain @click="goToConfiguration">
            查看平台配置
          </el-button>
        </div>
      </div>
      <div class="hero-metrics">
        <div v-for="metric in metrics" :key="metric.label" class="metric-card">
          <div class="metric-value">{{ metric.value }}</div>
          <div class="metric-label">{{ metric.label }}</div>
        </div>
      </div>
    </section>

    <section class="task-section">
      <div class="section-header section-header-inline">
        <div>
          <h2>我现在要做什么</h2>
          <p>按真实测试任务组织入口，减少用户在多个模块之间来回找功能。</p>
        </div>
        <el-tag type="success" effect="light">P0：统一用户心智</el-tag>
      </div>
      <div class="task-grid">
        <article
          v-for="task in primaryTasks"
          :key="task.key"
          class="task-card"
          @click="navigate(task.route)"
        >
          <div class="task-card-top">
            <div class="task-icon" :class="task.tone">
              <el-icon>
                <component :is="resolveIcon(task.icon)" />
              </el-icon>
            </div>
            <el-tag :type="task.tagType" effect="light">{{
              task.stage
            }}</el-tag>
          </div>
          <h3>{{ task.title }}</h3>
          <p>{{ task.description }}</p>
          <div class="task-next">
            <span>{{ task.next }}</span>
            <el-icon><ArrowRight /></el-icon>
          </div>
        </article>
      </div>
    </section>

    <section class="route-section">
      <div class="section-header">
        <h2>推荐测试生产链路</h2>
        <p>先把高频路径跑顺，再逐步统一底层对象模型。</p>
      </div>
      <div class="workflow-strip">
        <div
          v-for="(step, index) in workflowSteps"
          :key="step.title"
          class="workflow-step"
          @click="navigate(step.route)"
        >
          <span class="workflow-index">{{ index + 1 }}</span>
          <strong>{{ step.title }}</strong>
          <small>{{ step.desc }}</small>
        </div>
      </div>
    </section>

    <section class="focus-section">
      <div class="section-header">
        <h2>近期建设焦点</h2>
        <p>先做用户能感知的闭环，不急着进入大规模底层重构。</p>
      </div>
      <div class="focus-grid">
        <article
          v-for="item in focusItems"
          :key="item.title"
          class="focus-card"
        >
          <span>{{ item.label }}</span>
          <h3>{{ item.title }}</h3>
          <p>{{ item.desc }}</p>
        </article>
      </div>
    </section>

    <section class="phase-section">
      <div class="section-header">
        <h2>当前改进阶段</h2>
        <p>先统一入口，再统一模型，最后统一流程。</p>
      </div>
      <div class="phase-grid">
        <article
          v-for="phase in platformImprovementPhases"
          :key="phase.phase"
          class="phase-card"
        >
          <span class="phase-tag">{{ phase.phase }}</span>
          <h3>{{ phase.title }}</h3>
          <p>{{ phase.summary }}</p>
        </article>
      </div>
    </section>

    <section
      v-for="section in sectionedModules"
      :key="section.key"
      class="module-section"
    >
      <div class="section-header">
        <h2>{{ section.title }}</h2>
        <p>{{ section.description }}</p>
      </div>
      <div class="module-grid">
        <article
          v-for="module in section.modules"
          :key="module.key"
          class="module-card"
          @click="navigate(module.route)"
        >
          <div class="module-card-top">
            <div class="module-icon">
              <el-icon>
                <component :is="resolveIcon(module.icon)" />
              </el-icon>
            </div>
            <el-tag
              :type="statusTagType[module.status] || 'info'"
              effect="light"
            >
              {{ statusLabel[module.status] || module.status }}
            </el-tag>
          </div>
          <h3>{{ module.title }}</h3>
          <p>{{ module.description }}</p>
          <div class="module-highlights">
            <span v-for="item in module.highlights" :key="item">{{
              item
            }}</span>
          </div>
        </article>
      </div>
    </section>
  </div>
</template>

<script setup>
import { computed } from "vue";
import { useRouter } from "vue-router";
import {
  Aim,
  ArrowRight,
  ChatDotRound,
  Cellphone,
  Cpu,
  DataLine,
  Grid,
  Link,
  MagicStick,
  Monitor,
  Reading,
  Setting,
} from "@element-plus/icons-vue";
import {
  platformImprovementPhases,
  platformModules,
  platformWorkbenchSections,
} from "@/config/platformModules";

const router = useRouter();

const iconMap = {
  Aim,
  ArrowRight,
  ChatDotRound,
  Cellphone,
  Cpu,
  DataLine,
  Grid,
  Link,
  MagicStick,
  Monitor,
  Reading,
  Setting,
};

const statusLabel = {
  improving: "改进中",
  online: "已上线",
  upgrading: "升级中",
};

const statusTagType = {
  improving: "warning",
  online: "success",
  upgrading: "primary",
};

const sectionedModules = computed(() => {
  return platformWorkbenchSections
    .map((section) => ({
      ...section,
      modules: platformModules.filter(
        (module) => module.category === section.key,
      ),
    }))
    .filter((section) => section.modules.length > 0);
});

const metrics = computed(() => {
  const automationCount = platformModules.filter(
    (item) => item.category === "automation",
  ).length;
  const foundationCount = platformModules.filter(
    (item) => item.category === "foundation",
  ).length;
  const workspaceCount = platformModules.filter(
    (item) => item.category === "workspace",
  ).length;

  return [
    { label: "自动化中心", value: automationCount },
    { label: "平台底座", value: foundationCount },
    { label: "智能工作区", value: workspaceCount },
  ];
});

const primaryTasks = [
  {
    key: "requirement-to-case",
    title: "从需求生成用例",
    description:
      "上传或输入需求，先生成测试点和用例草稿，再人工确认沉淀为正式资产。",
    next: "进入 AI 用例生成",
    route: "/ai-generation/requirement-analysis",
    icon: "MagicStick",
    tone: "tone-blue",
    stage: "测试设计",
    tagType: "primary",
  },
  {
    key: "maintain-assets",
    title: "维护测试资产",
    description: "查看手工用例、导入用例和后续自动化资产，先形成统一资产心智。",
    next: "进入资产中心",
    route: "/platform/assets",
    icon: "Reading",
    tone: "tone-green",
    stage: "资产沉淀",
    tagType: "success",
  },
  {
    key: "run-app-automation",
    title: "跑一次 APP 自动化",
    description:
      "从 APP 自动化首页进入设备、元素、编排、执行和报告的完整闭环。",
    next: "进入 APP 自动化",
    route: "/app-automation/dashboard",
    icon: "Cellphone",
    tone: "tone-orange",
    stage: "自动化执行",
    tagType: "warning",
  },
  {
    key: "ai-exploration",
    title: "做一次 AI 探索",
    description:
      "通过受控规则探索 APP 页面，再让 AI 生成报告分析和下一轮探索草稿。",
    next: "进入 AI 探索",
    route: "/app-automation/exploration",
    icon: "Cpu",
    tone: "tone-purple",
    stage: "差异化能力",
    tagType: "info",
  },
  {
    key: "failure-diagnosis",
    title: "处理质量待办",
    description:
      "聚合失败执行、AI 探索疑似问题、等待中任务和证据缺口，先判断今天优先处理什么。",
    next: "进入待办中心",
    route: "/platform/backlog",
    icon: "Aim",
    tone: "tone-red",
    stage: "失败诊断",
    tagType: "danger",
  },
  {
    key: "prepare-data",
    title: "配置与交付",
    description:
      "按场景维护模型、APP 环境、通知出口，并把报告摘要组织成可交付材料。",
    next: "进入配置中心",
    route: "/platform/config",
    icon: "Setting",
    tone: "tone-cyan",
    stage: "平台支撑",
    tagType: "success",
  },
];

const workflowSteps = [
  {
    title: "需求输入",
    desc: "AI 分析与用例草稿",
    route: "/ai-generation/requirement-analysis",
  },
  {
    title: "资产沉淀",
    desc: "人工确认与维护",
    route: "/ai-generation/testcases",
  },
  {
    title: "自动化编排",
    desc: "APP 场景与元素库",
    route: "/app-automation/dashboard",
  },
  { title: "统一执行", desc: "执行记录与状态", route: "/platform/executions" },
  {
    title: "质量待办",
    desc: "失败、疑似问题、证据缺口",
    route: "/platform/backlog",
  },
  {
    title: "质量看板",
    desc: "趋势、汇报、复盘",
    route: "/platform/quality-dashboard",
  },
  { title: "交付出口", desc: "通知、摘要、材料", route: "/platform/delivery" },
];

const focusItems = [
  {
    label: "P0-1",
    title: "AI 探索可信闭环",
    desc: "继续补关键词清洗、覆盖解释、问题复核、执行阶段反馈和报告证据。",
  },
  {
    label: "P0-2",
    title: "任务型工作台",
    desc: "把入口按用户任务组织，减少“我该去哪个模块”的判断成本。",
  },
  {
    label: "P0-3",
    title: "测试资产中心视图层",
    desc: "先统一资产展示和来源心智，暂不急着大规模迁移底层表。",
  },
  {
    label: "P0-4",
    title: "AI 探索主线打深",
    desc: "壳子补齐后，重点回到 AI 探索闭环、报告复核、误报归档和大模型接入前置能力。",
  },
];

const resolveIcon = (iconName) => {
  return iconMap[iconName] || Grid;
};

const navigate = (path) => {
  router.push(path);
};

const goToFirstAutomation = () => {
  router.push("/app-automation/dashboard");
};

const goToConfiguration = () => {
  router.push("/platform/config");
};
</script>

<style scoped lang="scss">
.platform-workbench {
  min-height: 100%;
  padding: 8px 4px 20px;
  display: flex;
  flex-direction: column;
  gap: 24px;
}

.hero-section {
  display: grid;
  grid-template-columns: minmax(0, 1.5fr) minmax(280px, 0.9fr);
  gap: 20px;
  padding: 28px;
  border-radius: 24px;
  background:
    radial-gradient(
      circle at top right,
      rgba(51, 154, 240, 0.2),
      transparent 32%
    ),
    linear-gradient(135deg, #0f172a 0%, #112a46 45%, #1f5f8b 100%);
  color: #f8fbff;
  box-shadow: 0 20px 50px rgba(15, 23, 42, 0.18);
}

.hero-copy h1 {
  margin: 8px 0 14px;
  font-size: 34px;
  line-height: 1.15;
}

.hero-copy p {
  margin: 0;
  max-width: 720px;
  color: rgba(248, 251, 255, 0.82);
  font-size: 15px;
  line-height: 1.75;
}

.eyebrow {
  display: inline-flex;
  align-items: center;
  padding: 6px 12px;
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.12);
  border: 1px solid rgba(255, 255, 255, 0.16);
  font-size: 12px;
  letter-spacing: 0.08em;
  text-transform: uppercase;
}

.hero-actions {
  margin-top: 22px;
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
}

.hero-metrics {
  display: grid;
  grid-template-columns: repeat(1, minmax(0, 1fr));
  gap: 14px;
}

.metric-card {
  padding: 18px 20px;
  border-radius: 18px;
  background: rgba(255, 255, 255, 0.1);
  border: 1px solid rgba(255, 255, 255, 0.14);
  backdrop-filter: blur(8px);
}

.metric-value {
  font-size: 34px;
  font-weight: 700;
  line-height: 1;
}

.metric-label {
  margin-top: 8px;
  color: rgba(248, 251, 255, 0.75);
  font-size: 13px;
}

.section-header {
  margin-bottom: 14px;
}

.section-header-inline {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
}

.section-header h2 {
  margin: 0 0 6px;
  font-size: 22px;
  color: #18222f;
}

.section-header p {
  margin: 0;
  color: #6b7785;
  line-height: 1.6;
}

.phase-grid,
.module-grid,
.task-grid,
.focus-grid {
  display: grid;
  gap: 16px;
}

.task-grid {
  grid-template-columns: repeat(3, minmax(0, 1fr));
}

.task-card {
  min-height: 220px;
  padding: 20px;
  border-radius: 22px;
  background:
    linear-gradient(
      180deg,
      rgba(255, 255, 255, 0.96),
      rgba(248, 251, 255, 0.96)
    ),
    #fff;
  border: 1px solid #e5edf6;
  box-shadow: 0 14px 36px rgba(17, 42, 70, 0.08);
  cursor: pointer;
  display: flex;
  flex-direction: column;
  transition:
    transform 0.2s ease,
    box-shadow 0.2s ease,
    border-color 0.2s ease;
}

.task-card:hover {
  transform: translateY(-5px);
  border-color: #abcdf4;
  box-shadow: 0 20px 44px rgba(17, 42, 70, 0.13);
}

.task-card-top {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.task-icon {
  width: 52px;
  height: 52px;
  border-radius: 18px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  color: #fff;
  font-size: 24px;
}

.tone-blue {
  background: linear-gradient(135deg, #2563eb, #38bdf8);
}

.tone-green {
  background: linear-gradient(135deg, #059669, #34d399);
}

.tone-orange {
  background: linear-gradient(135deg, #f97316, #facc15);
}

.tone-purple {
  background: linear-gradient(135deg, #7c3aed, #c084fc);
}

.tone-red {
  background: linear-gradient(135deg, #dc2626, #fb7185);
}

.tone-cyan {
  background: linear-gradient(135deg, #0891b2, #22d3ee);
}

.task-card h3,
.focus-card h3 {
  margin: 16px 0 8px;
  color: #172033;
  font-size: 18px;
}

.task-card p,
.focus-card p {
  margin: 0;
  color: #64748b;
  line-height: 1.7;
}

.task-next {
  margin-top: auto;
  padding-top: 18px;
  display: inline-flex;
  align-items: center;
  gap: 6px;
  color: #1d63d1;
  font-weight: 600;
}

.workflow-strip {
  display: grid;
  grid-template-columns: repeat(6, minmax(0, 1fr));
  gap: 10px;
  padding: 14px;
  border-radius: 22px;
  background: #f6f9fd;
  border: 1px solid #e3ecf6;
}

.workflow-step {
  position: relative;
  min-height: 118px;
  padding: 16px;
  border-radius: 18px;
  background: #fff;
  border: 1px solid #e8eef5;
  cursor: pointer;
  transition:
    transform 0.2s ease,
    border-color 0.2s ease;
}

.workflow-step:hover {
  transform: translateY(-3px);
  border-color: #abcdf4;
}

.workflow-index {
  width: 28px;
  height: 28px;
  border-radius: 50%;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  background: #eaf4ff;
  color: #1d63d1;
  font-weight: 700;
  font-size: 13px;
}

.workflow-step strong {
  display: block;
  margin-top: 12px;
  color: #172033;
}

.workflow-step small {
  display: block;
  margin-top: 6px;
  color: #64748b;
  line-height: 1.5;
}

.focus-grid {
  grid-template-columns: repeat(4, minmax(0, 1fr));
}

.focus-card {
  padding: 18px;
  border-radius: 20px;
  background: linear-gradient(180deg, #ffffff 0%, #f8fbff 100%);
  border: 1px solid #e8eef5;
}

.focus-card span {
  display: inline-flex;
  align-items: center;
  padding: 5px 10px;
  border-radius: 999px;
  background: #eef6ff;
  color: #1d63d1;
  font-size: 12px;
  font-weight: 700;
}

.phase-grid {
  grid-template-columns: repeat(3, minmax(0, 1fr));
}

.phase-card,
.module-card {
  border-radius: 20px;
  background: #fff;
  border: 1px solid #e8eef5;
  box-shadow: 0 10px 30px rgba(17, 42, 70, 0.06);
}

.phase-card {
  padding: 20px;
}

.phase-card h3,
.module-card h3 {
  margin: 10px 0 8px;
  color: #18222f;
}

.phase-card p,
.module-card p {
  margin: 0;
  color: #6b7785;
  line-height: 1.7;
}

.phase-tag {
  display: inline-flex;
  align-items: center;
  padding: 5px 10px;
  border-radius: 999px;
  background: #edf5ff;
  color: #1d63d1;
  font-size: 12px;
  font-weight: 600;
}

.module-grid {
  grid-template-columns: repeat(3, minmax(0, 1fr));
}

.module-card {
  padding: 20px;
  cursor: pointer;
  transition:
    transform 0.2s ease,
    box-shadow 0.2s ease,
    border-color 0.2s ease;
}

.module-card:hover {
  transform: translateY(-4px);
  border-color: #bfd7f5;
  box-shadow: 0 16px 36px rgba(17, 42, 70, 0.1);
}

.module-card-top {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.module-icon {
  width: 50px;
  height: 50px;
  border-radius: 16px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  background: linear-gradient(145deg, #eef6ff 0%, #d9ebff 100%);
  color: #1d63d1;
  font-size: 24px;
}

.module-highlights {
  margin-top: 16px;
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.module-highlights span {
  display: inline-flex;
  align-items: center;
  padding: 5px 10px;
  border-radius: 999px;
  background: #f4f8fc;
  color: #4f5d6b;
  font-size: 12px;
}

@media (max-width: 1280px) {
  .hero-section,
  .module-grid,
  .phase-grid,
  .task-grid,
  .focus-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .workflow-strip {
    grid-template-columns: repeat(3, minmax(0, 1fr));
  }
}

@media (max-width: 900px) {
  .hero-section,
  .module-grid,
  .phase-grid,
  .task-grid,
  .focus-grid,
  .workflow-strip {
    grid-template-columns: 1fr;
  }

  .hero-section {
    padding: 22px;
  }

  .hero-copy h1 {
    font-size: 28px;
  }

  .section-header-inline {
    flex-direction: column;
  }
}
</style>
