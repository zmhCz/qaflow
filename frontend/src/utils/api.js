import axios from "axios";
import { ElMessage } from "element-plus";
import { useUserStore } from "@/stores/user";

const api = axios.create({
  baseURL: "/api",
  timeout: 30000,
  headers: {
    "Content-Type": "application/json",
  },
});

let isRefreshing = false;
let failedQueue = [];

const processQueue = (error, token = null) => {
  failedQueue.forEach((prom) => {
    if (error) {
      prom.reject(error);
    } else {
      prom.resolve(token);
    }
  });
  failedQueue = [];
};

const getBusinessMessage = (error) => {
  const data = error?.response?.data;
  if (!data) return "";
  const directMessage = data.detail || data.error || data.message || data.msg;
  if (Array.isArray(directMessage)) return directMessage.join("；");
  if (directMessage) return directMessage;

  if (Array.isArray(data.non_field_errors)) {
    return data.non_field_errors.join("；");
  }

  if (typeof data === "object") {
    const firstFieldError = Object.values(data).find((value) => {
      return Array.isArray(value) || typeof value === "string";
    });
    if (Array.isArray(firstFieldError)) return firstFieldError.join("；");
    if (typeof firstFieldError === "string") return firstFieldError;
  }

  return "";
};

const resolveApiErrorMessage = (error) => {
  if (
    error?.code === "ECONNABORTED" ||
    String(error?.message || "").includes("timeout")
  ) {
    if (error?.config?.timeoutMessage) {
      return error.config.timeoutMessage;
    }
    return "请求超时：服务响应较慢，请稍后重试；如果在操作真机，建议先检查设备连接。";
  }

  if (!error?.response) {
    return "后端服务不可用：请确认 QAFlow 后端服务已启动，或检查本机网络/代理配置。";
  }

  const status = error.response.status;
  const businessMessage = getBusinessMessage(error);

  if (status === 400)
    return businessMessage || "请求参数有误，请检查页面输入。";
  if (status === 401) return "登录已过期，请重新登录。";
  if (status === 403) return businessMessage || "当前账号没有权限执行该操作。";
  if (status === 404)
    return businessMessage || "接口或数据不存在，请刷新页面后重试。";
  if (status === 408)
    return businessMessage || "操作等待超时，请检查设备状态后重试。";
  if (status >= 500)
    return (
      businessMessage || "服务端异常：请稍后重试，必要时导出日志交给开发排查。"
    );

  return businessMessage || error.message || "请求失败，请稍后重试。";
};

api.interceptors.request.use(
  async (config) => {
    const userStore = useUserStore();

    if (config.url === "/auth/token/refresh/") {
      return config;
    }

    if (userStore.accessToken) {
      if (userStore.isTokenExpiringSoon && !userStore.isTokenExpired) {
        if (!isRefreshing) {
          isRefreshing = true;
          try {
            const newToken = await userStore.refreshAccessToken();
            processQueue(null, newToken);
            config.headers.Authorization = `Bearer ${newToken}`;
          } catch (error) {
            processQueue(error, null);
            return Promise.reject(error);
          } finally {
            isRefreshing = false;
          }
        } else {
          return new Promise((resolve, reject) => {
            failedQueue.push({ resolve, reject });
          })
            .then((token) => {
              config.headers.Authorization = `Bearer ${token}`;
              return config;
            })
            .catch((err) => Promise.reject(err));
        }
      }

      config.headers.Authorization = `Bearer ${userStore.accessToken}`;
    }

    return config;
  },
  (error) => Promise.reject(error),
);

api.interceptors.response.use(
  (response) => response,
  async (error) => {
    const userStore = useUserStore();
    const originalRequest = error.config || {};
    error.userMessage = resolveApiErrorMessage(error);

    if (error.response?.status === 401 && !originalRequest._retry) {
      if (originalRequest.url === "/auth/logout/") {
        userStore.$patch((state) => {
          state.accessToken = "";
          state.refreshToken = "";
          state.user = null;
          state.tokenExpiresAt = 0;
        });
        localStorage.removeItem("access_token");
        localStorage.removeItem("refresh_token");
        localStorage.removeItem("token_expires_at");
        localStorage.removeItem("user");
        window.location.href = "/login";
        return Promise.reject(error);
      }

      if (originalRequest.url === "/auth/token/refresh/") {
        await userStore.logout();
        return Promise.reject(error);
      }

      if (userStore.refreshToken && !isRefreshing) {
        originalRequest._retry = true;
        isRefreshing = true;

        try {
          const newToken = await userStore.refreshAccessToken();
          processQueue(null, newToken);
          originalRequest.headers.Authorization = `Bearer ${newToken}`;
          return api(originalRequest);
        } catch (refreshError) {
          refreshError.userMessage = resolveApiErrorMessage(refreshError);
          processQueue(refreshError, null);
          await userStore.logout();
          return Promise.reject(refreshError);
        } finally {
          isRefreshing = false;
        }
      }

      await userStore.logout();
      return Promise.reject(error);
    }

    if (originalRequest.suppressGlobalError) {
      return Promise.reject(error);
    }

    if (!error.response || error.code === "ECONNABORTED") {
      ElMessage.error(error.userMessage);
    } else if (error.response.status === 401) {
      ElMessage.error(error.userMessage);
    } else if (error.response.status >= 500) {
      ElMessage.error(error.userMessage);
    }

    return Promise.reject(error);
  },
);

export default api;
