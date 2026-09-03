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
      <div class="hero-actions">
        <el-button @click="tokenDialogVisible = true">生成绑定令牌</el-button>
        <el-button type="primary" :loading="loading" @click="loadAgents"
          >刷新状态</el-button
        >
      </div>
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

    <el-dialog
      v-model="tokenDialogVisible"
      title="绑定本地执行机"
      width="720px"
      destroy-on-close
    >
      <el-alert type="warning" :closable="false" show-icon>
        <template #title>令牌只展示一次</template>
        <div>
          它用于本地 Agent
          连接云端，不需要再输入平台账号密码。如果怀疑泄露，可以重新生成覆盖旧令牌。
        </div>
      </el-alert>
      <el-form class="token-form" label-width="110px">
        <el-form-item label="执行机标识">
          <el-input
            v-model="tokenForm.agent_id"
            placeholder="例如：my-laptop"
          />
        </el-form-item>
        <el-form-item label="执行机名称">
          <el-input v-model="tokenForm.name" placeholder="例如：我的本地电脑" />
        </el-form-item>
      </el-form>
      <div v-if="generatedCommand" class="generated-block">
        <div class="block-title">首次绑定命令</div>
        <pre>{{ generatedCommand }}</pre>
        <div class="hint">
          第一次运行会把连接配置保存到本地，后续可以直接启动
          Agent，不需要再输入账号密码。
        </div>
      </div>
      <template #footer>
        <el-button @click="tokenDialogVisible = false">关闭</el-button>
        <el-button v-if="generatedCommand" @click="copyCommand"
          >复制命令</el-button
        >
        <el-button
          type="primary"
          :loading="generatingToken"
          @click="generateToken"
          >生成令牌</el-button
        >
      </template>
    </el-dialog>

    <el-card shadow="never">
      <el-table
        v-loading="loading"
        :data="agents"
        empty-text="暂无执行机，先启动本地 Agent 完成一次心跳"
      >
        <el-table-column type="expand">
          <template #default="{ row }">
            <div class="health-panel">
              <div class="health-summary">
                <div>
                  <div class="health-title">环境体检</div>
                  <div class="health-desc">
                    {{
                      row.health_summary || "暂无体检结果，请重新启动本地 Agent"
                    }}
                  </div>
                </div>
                <el-tag :type="healthType(row.health_status)">
                  {{ healthText(row.health_status) }}
                </el-tag>
              </div>

              <el-empty
                v-if="!row.health_checks?.length"
                description="暂无检查项"
                :image-size="72"
              />
              <div v-else class="check-list">
                <div
                  v-for="item in row.health_checks"
                  :key="item.code"
                  class="check-item"
                  :class="`check-${item.status || 'unknown'}`"
                >
                  <div class="check-main">
                    <el-tag size="small" :type="checkType(item.status)">
                      {{ checkText(item.status) }}
                    </el-tag>
                    <span class="check-name">{{ item.name }}</span>
                    <span class="check-message">{{ item.message }}</span>
                  </div>
                  <div v-if="item.suggestion" class="check-suggestion">
                    处理建议：{{ item.suggestion }}
                  </div>
                  <div v-if="item.detail" class="check-detail">
                    {{ item.detail }}
                  </div>
                </div>
              </div>
            </div>
          </template>
        </el-table-column>
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
        <el-table-column label="环境体检" min-width="180">
          <template #default="{ row }">
            <div class="health-cell">
              <el-tag :type="healthType(row.health_status)">
                {{ healthText(row.health_status) }}
              </el-tag>
              <span class="muted">{{ formatTime(row.health_checked_at) }}</span>
            </div>
          </template>
        </el-table-column>
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
import { computed, onMounted, reactive, ref } from "vue";
import { ElMessage } from "element-plus";
import {
  generateExecutionAgentToken,
  getExecutionAgents,
} from "@/api/app-automation";

const loading = ref(false);
const generatingToken = ref(false);
const tokenDialogVisible = ref(false);
const agents = ref([]);
const currentOrigin = computed(() => window.location.origin);
const generatedCommand = ref("");
const tokenForm = reactive({
  agent_id: "",
  name: "",
});

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

const generateToken = async () => {
  generatingToken.value = true;
  try {
    const response = await generateExecutionAgentToken({
      agent_id: tokenForm.agent_id,
      name: tokenForm.name,
    });
    generatedCommand.value = response.data?.command || "";
    ElMessage.success("绑定令牌已生成，请复制命令在本地电脑运行一次");
    await loadAgents();
  } catch (error) {
    ElMessage.error(error.response?.data?.message || "生成绑定令牌失败");
  } finally {
    generatingToken.value = false;
  }
};

const copyCommand = async () => {
  if (!generatedCommand.value) return;
  try {
    if (navigator.clipboard?.writeText) {
      await navigator.clipboard.writeText(generatedCommand.value);
    } else {
      throw new Error("clipboard api unavailable");
    }
    ElMessage.success("命令已复制");
  } catch {
    const textarea = document.createElement("textarea");
    textarea.value = generatedCommand.value;
    textarea.style.position = "fixed";
    textarea.style.opacity = "0";
    document.body.appendChild(textarea);
    textarea.select();
    document.execCommand("copy");
    document.body.removeChild(textarea);
    ElMessage.success("命令已复制");
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

const healthText = (status) =>
  ({
    ready: "可执行",
    warning: "部分可用",
    blocked: "不可执行",
    unknown: "未检查",
  })[status] ||
  status ||
  "未检查";

const healthType = (status) =>
  ({
    ready: "success",
    warning: "warning",
    blocked: "danger",
    unknown: "info",
  })[status] || "info";

const checkText = (status) =>
  ({
    passed: "通过",
    warning: "提醒",
    failed: "失败",
  })[status] ||
  status ||
  "未知";

const checkType = (status) =>
  ({
    passed: "success",
    warning: "warning",
    failed: "danger",
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

.hero-actions {
  display: flex;
  gap: 10px;
  flex-shrink: 0;
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

.token-form {
  margin-top: 16px;
}

.generated-block {
  margin-top: 16px;
}

.block-title {
  margin-bottom: 8px;
  font-weight: 700;
  color: #172033;
}

.generated-block pre {
  margin: 0;
  padding: 12px;
  border-radius: 10px;
  background: #0f172a;
  color: #d1fae5;
  white-space: pre-wrap;
  word-break: break-all;
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

.health-cell {
  display: flex;
  flex-direction: column;
  gap: 6px;
  align-items: flex-start;
}

.health-panel {
  padding: 18px 24px 22px;
  background: #f8fafc;
}

.health-summary {
  display: flex;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 14px;
}

.health-title {
  font-size: 15px;
  font-weight: 700;
  color: #172033;
}

.health-desc {
  margin-top: 4px;
  color: #64748b;
}

.check-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.check-item {
  padding: 12px;
  border-radius: 12px;
  border: 1px solid #e2e8f0;
  background: #ffffff;
}

.check-failed {
  border-color: #fecaca;
  background: #fff7f7;
}

.check-warning {
  border-color: #fed7aa;
  background: #fffaf2;
}

.check-main {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
}

.check-name {
  font-weight: 700;
  color: #172033;
}

.check-message,
.check-suggestion,
.check-detail {
  color: #5b667a;
}

.check-suggestion {
  margin-top: 8px;
}

.check-detail {
  margin-top: 6px;
  font-size: 12px;
  word-break: break-all;
}
</style>
