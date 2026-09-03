<template>
  <div class="config-hub">
    <section class="hero-panel">
      <div>
        <span class="eyebrow">Config Hub</span>
        <h1>场景配置中心</h1>
        <p>
          把模型、提示词、APP
          环境、包名、通知策略按使用场景重新组织。第一版只做配置入口收口，
          不搬迁原配置页面，避免为了统一入口打乱现有能力。
        </p>
      </div>
      <div class="hero-actions">
        <el-button
          type="primary"
          @click="navigate('/configuration/app-exploration-model')"
          >配置 AI 探索模型</el-button
        >
        <el-button plain @click="navigate('/configuration/app-env')"
          >配置 APP 环境</el-button
        >
      </div>
    </section>

    <section class="scenario-grid">
      <article
        v-for="scenario in scenarios"
        :key="scenario.key"
        class="scenario-card"
      >
        <div class="scenario-header">
          <span class="scenario-dot" :class="scenario.tone" />
          <el-tag :type="scenario.statusType" effect="light">{{
            scenario.status
          }}</el-tag>
        </div>
        <h2>{{ scenario.title }}</h2>
        <p>{{ scenario.desc }}</p>
        <div class="config-links">
          <button
            v-for="item in scenario.items"
            :key="item.title"
            class="config-link"
            @click="navigate(item.route)"
          >
            <div>
              <strong>{{ item.title }}</strong>
              <span>{{ item.desc }}</span>
            </div>
            <el-icon><ArrowRight /></el-icon>
          </button>
        </div>
      </article>
    </section>

    <section class="checklist-panel">
      <div class="section-title">交付前配置检查</div>
      <div class="checklist-grid">
        <div v-for="item in checklist" :key="item.title" class="check-card">
          <el-tag :type="item.type" effect="plain">{{ item.level }}</el-tag>
          <strong>{{ item.title }}</strong>
          <p>{{ item.desc }}</p>
        </div>
      </div>
    </section>
  </div>
</template>

<script setup>
import { useRouter } from "vue-router";
import { ArrowRight } from "@element-plus/icons-vue";

const router = useRouter();

const scenarios = [
  {
    key: "ai-exploration",
    title: "AI 探索配置",
    desc: "决定探索模块能不能稳定产出分析结论，包括模型、提示词、探索目标和分析策略。",
    tone: "tone-blue",
    status: "7月 KR",
    statusType: "primary",
    items: [
      {
        title: "AI 探索模型",
        desc: "配置探索分析使用的大模型",
        route: "/configuration/app-exploration-model",
      },
      {
        title: "提示词配置",
        desc: "维护分析、复核、报告类提示词",
        route: "/configuration/app-exploration-prompt",
      },
      {
        title: "AI 探索任务",
        desc: "创建和执行探索任务",
        route: "/app-automation/exploration",
      },
    ],
  },
  {
    key: "app-automation",
    title: "APP 自动化配置",
    desc: "决定自动化能不能跑起来，包括设备、包名、环境、语义字典和用例编排基础。",
    tone: "tone-green",
    status: "主链路",
    statusType: "success",
    items: [
      {
        title: "APP 环境配置",
        desc: "配置执行环境与基础参数",
        route: "/configuration/app-env",
      },
      {
        title: "包名管理",
        desc: "维护 Android / iOS 应用标识",
        route: "/app-automation/packages",
      },
      {
        title: "语义字典",
        desc: "约束元素命名和业务术语",
        route: "/app-automation/semantic-dictionaries",
      },
      {
        title: "设备管理",
        desc: "确认设备在线和可执行状态",
        route: "/app-automation/devices",
      },
    ],
  },
  {
    key: "report-delivery",
    title: "报告与通知配置",
    desc: "决定结果能不能被团队消费，包括报告入口、通知规则和后续企微机器人。",
    tone: "tone-orange",
    status: "待增强",
    statusType: "warning",
    items: [
      {
        title: "调度与通知配置",
        desc: "维护通知规则和定时任务配置",
        route: "/configuration/scheduled-task",
      },
      {
        title: "APP 通知日志",
        desc: "查看自动化通知发送记录",
        route: "/app-automation/notification-logs",
      },
      {
        title: "交付出口",
        desc: "组织报告、日志和缺陷材料",
        route: "/platform/delivery",
      },
    ],
  },
  {
    key: "foundation",
    title: "平台基础配置",
    desc: "承接通用模型、生成参数、Dify 等跨模块基础能力。",
    tone: "tone-purple",
    status: "通用底座",
    statusType: "info",
    items: [
      {
        title: "通用 AI 模型",
        desc: "配置需求分析和用例生成模型",
        route: "/configuration/ai-model",
      },
      {
        title: "生成参数",
        desc: "维护 AI 用例生成策略",
        route: "/configuration/generation-config",
      },
      {
        title: "Dify 配置",
        desc: "配置外部 AI 助手集成",
        route: "/configuration/dify",
      },
    ],
  },
];

const checklist = [
  {
    level: "必须",
    type: "danger",
    title: "AI 探索模型可用",
    desc: "否则探索报告无法进入 AI 分析闭环。",
  },
  {
    level: "必须",
    type: "danger",
    title: "APP 包名与设备可用",
    desc: "否则执行任务会卡在启动或连接阶段。",
  },
  {
    level: "建议",
    type: "warning",
    title: "语义字典已维护",
    desc: "否则元素和用例命名会继续依赖个人风格。",
  },
  {
    level: "建议",
    type: "warning",
    title: "通知出口已配置",
    desc: "否则报告只能在平台内查看，协同效率有限。",
  },
];

const navigate = (path) => {
  router.push(path);
};
</script>

<style scoped lang="scss">
.config-hub {
  min-height: 100%;
  padding: 8px 4px 20px;
  display: flex;
  flex-direction: column;
  gap: 22px;
}

.hero-panel {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: 20px;
  padding: 28px;
  border-radius: 24px;
  color: #f8fbff;
  background:
    radial-gradient(
      circle at top right,
      rgba(45, 212, 191, 0.25),
      transparent 30%
    ),
    linear-gradient(135deg, #0f172a 0%, #164e63 48%, #0f766e 100%);
  box-shadow: 0 20px 50px rgba(15, 23, 42, 0.16);
}

.hero-panel h1 {
  margin: 8px 0 12px;
  font-size: 32px;
}

.hero-panel p {
  max-width: 800px;
  margin: 0;
  color: rgba(248, 251, 255, 0.84);
  line-height: 1.75;
}

.eyebrow {
  display: inline-flex;
  padding: 6px 12px;
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.12);
  border: 1px solid rgba(255, 255, 255, 0.16);
  font-size: 12px;
  letter-spacing: 0.08em;
}

.hero-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
}

.scenario-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 16px;
}

.scenario-card,
.checklist-panel {
  border-radius: 20px;
  background: #fff;
  border: 1px solid #e8eef5;
  box-shadow: 0 10px 30px rgba(17, 42, 70, 0.06);
}

.scenario-card {
  padding: 20px;
}

.scenario-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.scenario-dot {
  width: 13px;
  height: 13px;
  border-radius: 50%;
}

.tone-blue {
  background: #3b82f6;
}
.tone-green {
  background: #10b981;
}
.tone-orange {
  background: #f97316;
}
.tone-purple {
  background: #8b5cf6;
}

.scenario-card h2 {
  margin: 16px 0 8px;
  color: #172033;
}

.scenario-card p {
  margin: 0 0 16px;
  color: #64748b;
  line-height: 1.65;
}

.config-links {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.config-link {
  width: 100%;
  border: 1px solid #e8eef5;
  border-radius: 16px;
  padding: 14px;
  background: #f8fbff;
  color: #172033;
  display: flex;
  align-items: center;
  justify-content: space-between;
  text-align: left;
  cursor: pointer;
}

.config-link:hover {
  border-color: #14b8a6;
  background: #f0fdfa;
}

.config-link strong,
.config-link span {
  display: block;
}

.config-link span {
  margin-top: 4px;
  color: #64748b;
  font-size: 13px;
}

.checklist-panel {
  padding: 18px;
}

.section-title {
  margin-bottom: 14px;
  color: #172033;
  font-size: 18px;
  font-weight: 700;
}

.checklist-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 14px;
}

.check-card {
  padding: 16px;
  border-radius: 16px;
  background: #f8fbff;
  border: 1px solid #e8eef5;
}

.check-card strong {
  display: block;
  margin-top: 10px;
  color: #172033;
}

.check-card p {
  margin: 8px 0 0;
  color: #64748b;
  line-height: 1.6;
}

@media (max-width: 1080px) {
  .scenario-grid,
  .checklist-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

@media (max-width: 760px) {
  .hero-panel,
  .scenario-grid,
  .checklist-grid {
    grid-template-columns: 1fr;
  }

  .hero-panel {
    flex-direction: column;
    align-items: stretch;
  }
}
</style>
