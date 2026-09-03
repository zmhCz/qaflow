<template>
  <div class="agent-page">
    <div class="page-hero">
      <div>
        <p class="eyebrow">分布式执行</p>
        <h2>执行机 Agent</h2>
        <p class="hero-desc">
          云端负责管理任务和报告，本地电脑负责连接手机执行。Agent
          在线后，会同步本地设备并领取待执行任务。
        </p>
      </div>
      <el-button type="primary" :loading="loading" @click="loadAgents"
        >刷新状态</el-button
      >
    </div>

    <el-alert class="guide-alert" type="info" :closable="false" show-icon>
      <template #title>本地执行机验证方式</template>
      <div class="command-box">
        <code
          >python scripts/qaflow_agent.py --base-url
          {{ currentOrigin }} --username 你的账号 --password 你的密码 --once
          --dry-run</code
        >
      </div>
      <div class="hint">
        先用 dry-run 验证“云端派发 - 本地领取 -
        结果回传”闭环，真机执行迁移会在下一阶段接入。
      </div>
    </el-alert>

    <el-card shadow="never">
      <el-table
        v-loading="loading"
        :data="agents"
        empty-text="暂无执行机，先启动本地 Agent 完成一次心跳"
      >
        <el-table-column prop="name" label="执行机" min-width="160">
          <template #default="{ row }">
            <div class="agent-name">{{ row.name }}</div>
            <div class="agent-id">{{ row.agent_id }}</div>
          </template>
        </el-table-column>
        <el-table-column label="状态" width="110">
          <template #default="{ row }">
            <el-tag :type="statusType(row.status)">{{
              statusText(row.status)
            }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column
          prop="online_device_count"
          label="在线设备"
          width="110"
        />
        <el-table-column prop="device_count" label="设备总数" width="110" />
        <el-table-column
          prop="running_execution_count"
          label="运行任务"
          width="110"
        />
        <el-table-column label="最近心跳" min-width="170">
          <template #default="{ row }">{{
            formatTime(row.last_seen_at)
          }}</template>
        </el-table-column>
        <el-table-column label="能力" min-width="220">
          <template #default="{ row }">
            <el-tag v-if="row.capabilities?.adb" size="small">ADB</el-tag>
            <el-tag v-if="row.capabilities?.dry_run" size="small" type="warning"
              >dry-run</el-tag
            >
            <span
              v-if="!row.capabilities || !Object.keys(row.capabilities).length"
              class="muted"
              >暂无</span
            >
          </template>
        </el-table-column>
      </el-table>
    </el-card>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from "vue";
import { ElMessage } from "element-plus";
import { getExecutionAgents } from "@/api/app-automation";

const loading = ref(false);
const agents = ref([]);
const currentOrigin = computed(() => window.location.origin);

const loadAgents = async () => {
  loading.value = true;
  try {
    const response = await getExecutionAgents();
    agents.value = response.data?.results || response.data || [];
  } catch (error) {
    ElMessage.error(error.response?.data?.message || "加载执行机失败");
  } finally {
    loading.value = false;
  }
};

const statusText = (status) =>
  ({
    online: "在线",
    offline: "离线",
    busy: "执行中",
    disabled: "已停用",
  })[status] ||
  status ||
  "-";

const statusType = (status) =>
  ({
    online: "success",
    busy: "warning",
    disabled: "danger",
    offline: "info",
  })[status] || "info";

const formatTime = (value) => {
  if (!value) return "-";
  return new Date(value).toLocaleString();
};

onMounted(loadAgents);
</script>

<style scoped>
.agent-page {
  padding: 24px;
}

.page-hero {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 24px;
  padding: 24px;
  margin-bottom: 16px;
  border-radius: 18px;
  background: linear-gradient(135deg, #eef7ff 0%, #f7fbf1 100%);
  border: 1px solid #dbeafe;
}

.eyebrow {
  margin: 0 0 6px;
  color: #2563eb;
  font-size: 13px;
  font-weight: 700;
  letter-spacing: 0.08em;
}

h2 {
  margin: 0;
  font-size: 24px;
  color: #172033;
}

.hero-desc {
  max-width: 760px;
  margin: 10px 0 0;
  color: #5b667a;
  line-height: 1.7;
}

.guide-alert {
  margin-bottom: 16px;
}

.command-box {
  margin-top: 8px;
  padding: 10px 12px;
  border-radius: 10px;
  background: #0f172a;
  color: #d1fae5;
  overflow-x: auto;
}

.hint {
  margin-top: 8px;
  color: #64748b;
}

.agent-name {
  font-weight: 700;
  color: #172033;
}

.agent-id,
.muted {
  color: #8a94a6;
  font-size: 12px;
}
</style>
