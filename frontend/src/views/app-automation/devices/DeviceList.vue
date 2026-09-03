<template>
  <div class="device-management">
    <div class="device-header">
      <div>
        <p class="eyebrow">Device Center</p>
        <h3>设备管理</h3>
        <p class="page-desc">
          先确认设备可执行，再维护元素和运行用例。健康检查会真实验证
          ADB、截图、UI 树和前台应用。
        </p>
      </div>
      <div class="device-actions">
        <el-button
          type="primary"
          :icon="Refresh"
          :loading="refreshing"
          @click="refreshDevices"
        >
          刷新设备
        </el-button>
        <el-button type="success" :icon="Plus" @click="showAddRemoteDialog">
          添加远程设备
        </el-button>
      </div>
    </div>

    <el-alert
      title="建议：执行失败前先跑一次健康检查。"
      type="info"
      :closable="false"
      class="health-tip"
    >
      <template #default>
        如果截图或 UI
        树失败，后续元素录入、用例执行、探索测试大概率也会失败，优先处理设备问题。
      </template>
    </el-alert>

    <el-table
      v-loading="loading"
      :data="devices"
      class="device-table"
      :empty-text="emptyText"
    >
      <el-table-column prop="name" label="设备名称" min-width="150">
        <template #default="{ row }">{{ row.name || row.device_id }}</template>
      </el-table-column>
      <el-table-column
        prop="device_id"
        label="设备序列号"
        min-width="180"
        show-overflow-tooltip
      />
      <el-table-column prop="status" label="状态" width="110">
        <template #default="{ row }">
          <el-tag :type="getStatusType(row.status)" size="small">
            {{ getStatusText(row.status) }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="locked_by" label="锁定用户" width="120">
        <template #default="{ row }">{{ row.locked_by_name || "-" }}</template>
      </el-table-column>
      <el-table-column prop="android_version" label="Android 版本" width="130">
        <template #default="{ row }">{{ row.android_version || "-" }}</template>
      </el-table-column>
      <el-table-column prop="connection_type" label="连接类型" width="130">
        <template #default="{ row }">
          <el-tag
            :type="
              getConnectionType(row.connection_type) === 'local'
                ? 'primary'
                : 'warning'
            "
            size="small"
          >
            {{ getConnectionTypeName(row.connection_type) }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="ip_address" label="IP 地址" width="150">
        <template #default="{ row }">{{ row.ip_address || "-" }}</template>
      </el-table-column>
      <el-table-column prop="updated_at" label="更新时间" width="180">
        <template #default="{ row }">{{ formatDate(row.updated_at) }}</template>
      </el-table-column>
      <el-table-column label="操作" width="330" fixed="right">
        <template #default="{ row }">
          <el-button
            link
            size="small"
            type="primary"
            :loading="healthCheckingId === row.id"
            @click="runHealthCheck(row)"
          >
            健康检查
          </el-button>
          <el-button
            v-if="row.status === 'available' || row.status === 'online'"
            link
            size="small"
            type="primary"
            @click="lockDevice(row)"
          >
            锁定
          </el-button>
          <el-button
            v-if="row.status === 'locked'"
            link
            size="small"
            type="success"
            @click="unlockDevice(row)"
          >
            解锁
          </el-button>
          <el-button
            v-if="
              isRemoteDevice(row.connection_type) && row.status === 'offline'
            "
            link
            size="small"
            type="warning"
            :loading="reconnectingDevices[row.id]"
            @click="reconnectDevice(row)"
          >
            重连
          </el-button>
          <el-button link size="small" @click="viewDeviceInfo(row)"
            >详情</el-button
          >
          <el-button
            v-if="
              isRemoteDevice(row.connection_type) &&
              (row.status === 'online' || row.status === 'available')
            "
            link
            size="small"
            type="warning"
            @click="disconnectDevice(row)"
          >
            断开
          </el-button>
          <el-button
            link
            size="small"
            type="danger"
            @click="handleDeleteDevice(row)"
            >删除</el-button
          >
        </template>
      </el-table-column>
    </el-table>

    <el-dialog
      v-model="addRemoteDialogVisible"
      title="添加远程设备"
      width="500px"
      :close-on-click-modal="false"
    >
      <el-form
        ref="remoteDeviceFormRef"
        :model="remoteDeviceForm"
        :rules="remoteDeviceRules"
        label-width="100px"
      >
        <el-form-item label="IP 地址" prop="ip_address">
          <el-input
            v-model="remoteDeviceForm.ip_address"
            placeholder="请输入远程设备 IP 地址"
          />
        </el-form-item>
        <el-form-item label="端口" prop="port">
          <el-input-number
            v-model="remoteDeviceForm.port"
            :min="1"
            :max="65535"
            style="width: 100%"
          />
        </el-form-item>
        <el-alert title="连接前请确认" type="info" :closable="false">
          <div>1. 远程设备已开启 ADB 调试。</div>
          <div>2. 已执行 adb tcpip 5555 或设备已暴露调试端口。</div>
          <div>3. 当前电脑能访问该设备 IP。</div>
        </el-alert>
      </el-form>
      <template #footer>
        <el-button @click="addRemoteDialogVisible = false">取消</el-button>
        <el-button
          type="primary"
          :loading="connecting"
          @click="connectRemoteDevice"
          >连接</el-button
        >
      </template>
    </el-dialog>

    <el-dialog v-model="deviceInfoDialogVisible" title="设备详情" width="620px">
      <el-descriptions v-if="selectedDevice" :column="2" border>
        <el-descriptions-item label="设备名称">{{
          selectedDevice.name || selectedDevice.device_id
        }}</el-descriptions-item>
        <el-descriptions-item label="设备序列号">{{
          selectedDevice.device_id
        }}</el-descriptions-item>
        <el-descriptions-item label="状态">
          <el-tag :type="getStatusType(selectedDevice.status)" size="small">
            {{ getStatusText(selectedDevice.status) }}
          </el-tag>
        </el-descriptions-item>
        <el-descriptions-item label="锁定用户">{{
          selectedDevice.locked_by_name || "-"
        }}</el-descriptions-item>
        <el-descriptions-item label="锁定时间">
          {{
            selectedDevice.locked_at
              ? formatDate(selectedDevice.locked_at)
              : "-"
          }}
        </el-descriptions-item>
        <el-descriptions-item label="Android 版本">{{
          selectedDevice.android_version || "-"
        }}</el-descriptions-item>
        <el-descriptions-item label="连接类型">{{
          getConnectionTypeName(selectedDevice.connection_type)
        }}</el-descriptions-item>
        <el-descriptions-item label="IP 地址">{{
          selectedDevice.ip_address || "-"
        }}</el-descriptions-item>
        <el-descriptions-item label="端口">{{
          selectedDevice.port || "-"
        }}</el-descriptions-item>
        <el-descriptions-item label="使用次数">{{
          selectedDevice.usage_count || 0
        }}</el-descriptions-item>
        <el-descriptions-item label="创建时间">{{
          formatDate(selectedDevice.created_at)
        }}</el-descriptions-item>
        <el-descriptions-item label="更新时间">{{
          formatDate(selectedDevice.updated_at)
        }}</el-descriptions-item>
      </el-descriptions>
      <template #footer>
        <el-button @click="deviceInfoDialogVisible = false">关闭</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="healthDialogVisible" title="设备健康检查" width="720px">
      <div v-if="healthResult" class="health-summary">
        <div>
          <div class="health-device">{{ healthResult.device_name }}</div>
          <div class="health-meta">
            {{ healthResult.device_id }} · {{ healthResult.checked_at || "-" }}
          </div>
        </div>
        <el-tag :type="getHealthTagType(healthResult.verdict)" size="large">
          {{ healthResult.verdict_text }} · {{ healthResult.score }} 分
        </el-tag>
      </div>

      <el-table v-if="healthResult" :data="healthResult.checks || []" border>
        <el-table-column label="检查项" prop="name" width="140" />
        <el-table-column label="结果" width="90">
          <template #default="{ row }">
            <el-tag :type="row.passed ? 'success' : 'danger'" size="small">
              {{ row.passed ? "通过" : "失败" }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="说明" min-width="220">
          <template #default="{ row }">
            <div>{{ row.message || "-" }}</div>
            <div v-if="row.suggestion" class="check-suggestion">
              {{ row.suggestion }}
            </div>
          </template>
        </el-table-column>
        <el-table-column label="详情" min-width="180">
          <template #default="{ row }">
            <pre class="check-detail">{{ formatDetail(row.detail) }}</pre>
          </template>
        </el-table-column>
      </el-table>

      <el-alert
        v-if="healthResult?.suggestions?.length"
        title="处理建议"
        type="warning"
        :closable="false"
        class="suggestion-alert"
      >
        <div v-for="(item, index) in healthResult.suggestions" :key="index">
          {{ index + 1 }}. {{ item }}
        </div>
      </el-alert>

      <template #footer>
        <el-button @click="healthDialogVisible = false">关闭</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, onMounted, onBeforeUnmount } from "vue";
import { ElMessage, ElMessageBox } from "element-plus";
import { Refresh, Plus } from "@element-plus/icons-vue";
import {
  connectDevice,
  deleteDevice,
  discoverDevices,
  disconnectDevice as apiDisconnectDevice,
  getDeviceList,
  healthCheckDevice,
  lockDevice as apiLockDevice,
  unlockDevice as apiUnlockDevice,
} from "@/api/app-automation";
import {
  getDeviceStatusType,
  getDeviceStatusText,
  formatDateTime,
} from "@/utils/app-automation-helpers";

const remoteDeviceFormRef = ref(null);
const devices = ref([]);
const loading = ref(false);
const refreshing = ref(false);
const connecting = ref(false);
const healthCheckingId = ref(null);
const reconnectingDevices = ref({});
const addRemoteDialogVisible = ref(false);
const deviceInfoDialogVisible = ref(false);
const healthDialogVisible = ref(false);
const selectedDevice = ref(null);
const healthResult = ref(null);
const emptyText = ref("暂无设备，请点击“刷新设备”或添加远程设备");
const refreshTimer = ref(null);

const remoteDeviceForm = ref({
  ip_address: "",
  port: 5555,
});

const remoteDeviceRules = {
  ip_address: [
    { required: true, message: "请输入 IP 地址", trigger: "blur" },
    {
      pattern: /^(\d{1,3}\.){3}\d{1,3}$/,
      message: "请输入有效的 IP 地址",
      trigger: "blur",
    },
  ],
  port: [{ required: true, message: "请输入端口号", trigger: "blur" }],
};

const getDevices = async () => {
  loading.value = true;
  try {
    const res = await getDeviceList({ page: 1, page_size: 1000 });
    const payload = res.data?.data || res.data;
    devices.value = payload?.results || payload || [];
  } catch (error) {
    ElMessage.error(error?.userMessage || "获取设备列表失败");
  } finally {
    loading.value = false;
  }
};

const refreshDevices = async () => {
  refreshing.value = true;
  try {
    const res = await discoverDevices();
    if (res.data.success) {
      devices.value = res.data.devices || [];
      ElMessage.success(res.data.message || "设备列表已刷新");
    } else {
      ElMessage.error(res.data.message || "刷新设备列表失败");
    }
  } catch (error) {
    ElMessage.error(error?.userMessage || "刷新设备列表失败");
  } finally {
    refreshing.value = false;
  }
};

const runHealthCheck = async (device) => {
  healthCheckingId.value = device.id;
  healthResult.value = null;
  try {
    const res = await healthCheckDevice(device.id);
    healthResult.value = res.data?.data || null;
    healthDialogVisible.value = true;
  } catch (error) {
    ElMessage.error(error?.userMessage || "设备健康检查失败");
  } finally {
    healthCheckingId.value = null;
  }
};

const showAddRemoteDialog = () => {
  addRemoteDialogVisible.value = true;
  remoteDeviceForm.value = { ip_address: "", port: 5555 };
  remoteDeviceFormRef.value?.clearValidate();
};

const connectRemoteDevice = async () => {
  if (!remoteDeviceFormRef.value) return;
  await remoteDeviceFormRef.value.validate(async (valid) => {
    if (!valid) return;
    connecting.value = true;
    try {
      const res = await connectDevice(remoteDeviceForm.value);
      if (res.data.success) {
        ElMessage.success(res.data.message || "远程设备连接成功");
        addRemoteDialogVisible.value = false;
        await getDevices();
      } else {
        ElMessage.error(res.data.message || "连接远程设备失败");
      }
    } catch (error) {
      ElMessage.error(error?.userMessage || "连接远程设备失败");
    } finally {
      connecting.value = false;
    }
  });
};

const reconnectDevice = async (device) => {
  if (!device.ip_address || !device.port) {
    ElMessage.error("设备信息不完整，无法重连");
    return;
  }
  reconnectingDevices.value[device.id] = true;
  try {
    const res = await connectDevice({
      ip_address: device.ip_address,
      port: device.port,
    });
    if (res.data.success) {
      ElMessage.success("设备重连成功");
      await getDevices();
    } else {
      ElMessage.error(res.data.message || "设备重连失败，请检查网络连接");
    }
  } catch (error) {
    ElMessage.error(error?.userMessage || "设备重连失败，请检查网络连接");
  } finally {
    reconnectingDevices.value[device.id] = false;
  }
};

const disconnectDevice = async (device) => {
  try {
    await ElMessageBox.confirm(
      `确定要断开设备 ${device.name || device.device_id} 的连接吗？`,
      "提示",
      {
        confirmButtonText: "确定",
        cancelButtonText: "取消",
        type: "warning",
      },
    );
    const res = await apiDisconnectDevice(device.id);
    if (res.data.success) {
      ElMessage.success("设备已断开");
      await getDevices();
    } else {
      ElMessage.error(res.data.message || "断开设备失败");
    }
  } catch (error) {
    if (error !== "cancel") {
      ElMessage.error(error?.userMessage || "断开设备失败");
    }
  }
};

const viewDeviceInfo = (device) => {
  selectedDevice.value = device;
  deviceInfoDialogVisible.value = true;
};

const lockDevice = async (device) => {
  try {
    await ElMessageBox.confirm(
      `确定要锁定设备 ${device.name || device.device_id} 吗？`,
      "提示",
      {
        confirmButtonText: "确定",
        cancelButtonText: "取消",
        type: "warning",
      },
    );
    const res = await apiLockDevice(device.id);
    if (res.data.success) {
      ElMessage.success("设备已锁定");
      await getDevices();
    } else {
      ElMessage.error(res.data.message || "锁定设备失败");
    }
  } catch (error) {
    if (error !== "cancel") {
      ElMessage.error(error?.userMessage || "锁定设备失败");
    }
  }
};

const unlockDevice = async (device) => {
  try {
    await ElMessageBox.confirm(
      `确定要解锁设备 ${device.name || device.device_id} 吗？`,
      "提示",
      {
        confirmButtonText: "确定",
        cancelButtonText: "取消",
        type: "warning",
      },
    );
    const res = await apiUnlockDevice(device.id);
    if (res.data.success) {
      ElMessage.success("设备已解锁");
      await getDevices();
    } else {
      ElMessage.error(res.data.message || "解锁设备失败");
    }
  } catch (error) {
    if (error !== "cancel") {
      ElMessage.error(error?.userMessage || "解锁设备失败");
    }
  }
};

const handleDeleteDevice = async (device) => {
  try {
    await ElMessageBox.confirm(
      `确定要删除设备 ${device.name || device.device_id} 吗？删除后无法恢复。`,
      "删除设备",
      {
        confirmButtonText: "确定",
        cancelButtonText: "取消",
        type: "warning",
      },
    );
    const res = await deleteDevice(device.id);
    if (res.status === 204 || res.status === 200) {
      ElMessage.success("设备已删除");
      await getDevices();
    } else {
      ElMessage.error(res.data?.message || "删除设备失败");
    }
  } catch (error) {
    if (error !== "cancel") {
      ElMessage.error(error?.userMessage || "删除设备失败");
    }
  }
};

const formatDate = formatDateTime;
const getStatusType = getDeviceStatusType;
const getStatusText = getDeviceStatusText;

const getConnectionType = (type) => {
  if (type === "emulator" || type === "usb") return "local";
  return "remote";
};

const getConnectionTypeName = (type) => {
  const typeMap = {
    emulator: "本地模拟器",
    remote_emulator: "远程模拟器",
    remote: "远程设备",
    usb: "USB 连接",
  };
  return typeMap[type] || type || "-";
};

const isRemoteDevice = (type) =>
  type === "remote_emulator" || type === "remote";

const getHealthTagType = (verdict) => {
  if (verdict === "executable") return "success";
  if (verdict === "needs_attention") return "warning";
  return "danger";
};

const formatDetail = (detail) => {
  if (!detail || Object.keys(detail).length === 0) return "-";
  return JSON.stringify(detail, null, 2);
};

onMounted(() => {
  getDevices();
  refreshTimer.value = setInterval(getDevices, 30000);
});

onBeforeUnmount(() => {
  if (refreshTimer.value) {
    clearInterval(refreshTimer.value);
  }
});
</script>

<style scoped lang="scss">
.device-management {
  padding: 20px;
  background: #f6f8fb;
}

.device-header {
  display: flex;
  justify-content: space-between;
  gap: 16px;
  align-items: flex-start;
  margin-bottom: 16px;
  padding: 22px;
  border-radius: 20px;
  background:
    radial-gradient(
      circle at top right,
      rgba(19, 194, 194, 0.18),
      transparent 34%
    ),
    linear-gradient(135deg, #f8fbff 0%, #effaf7 100%);
  border: 1px solid #dfeaf5;

  h3 {
    margin: 0;
    color: #1f2937;
    font-size: 24px;
  }
}

.eyebrow {
  margin: 0 0 6px;
  color: #3f7d6b;
  font-size: 12px;
  letter-spacing: 0.08em;
}

.page-desc {
  max-width: 780px;
  margin: 8px 0 0;
  color: #64748b;
  line-height: 1.7;
}

.device-actions {
  display: flex;
  gap: 10px;
  white-space: nowrap;
}

.health-tip,
.device-table {
  margin-top: 16px;
}

.health-summary {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 16px;
  margin-bottom: 16px;
  padding: 14px 16px;
  border-radius: 14px;
  background: #f8fafc;
  border: 1px solid #edf2f7;
}

.health-device {
  color: #1f2937;
  font-weight: 700;
}

.health-meta {
  margin-top: 4px;
  color: #64748b;
  font-size: 12px;
}

.check-suggestion {
  margin-top: 6px;
  color: #b45309;
  font-size: 12px;
}

.check-detail {
  max-height: 110px;
  margin: 0;
  overflow: auto;
  color: #475569;
  font-size: 12px;
  white-space: pre-wrap;
  word-break: break-all;
}

.suggestion-alert {
  margin-top: 16px;
}

@media (max-width: 900px) {
  .device-header {
    flex-direction: column;
  }
}
</style>
