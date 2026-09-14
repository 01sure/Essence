import axios from "axios";
import { ElMessage, ElNotification } from "element-plus";

const api = axios.create({ baseURL: "/api", timeout: 60000 });

api.interceptors.request.use((config) => {
  const token = localStorage.getItem("huami_token");
  if (token) config.headers.Authorization = `Bearer ${token}`;
  return config;
});

api.interceptors.response.use(
  (resp) => resp,
  (error) => {
    const status = error.response?.status;
    const detail = error.response?.data?.detail || error.message || "请求失败";

    if (status === 401) {
      localStorage.removeItem("huami_token");
      localStorage.removeItem("huami_user");
      if (!location.hash.includes("login")) location.hash = "#/login";
    } else if (status === 403) {
      ElMessage.error("权限不足：" + String(detail));
    } else if (status === 409) {
      // 409 冲突：默认 warning，让调用方决定是否做业务级处理
      ElNotification.warning({
        title: "并发冲突",
        message: String(detail),
        duration: 3200,
      });
    } else if (status === 429) {
      ElMessage.warning("请求过于频繁，请稍后再试");
    } else {
      ElMessage.error(String(detail));
    }
    return Promise.reject(error);
  }
);

/**
 * 带事件解析的 SSE 客户端（坐席工作台用）。
 * 浏览器 EventSource 不能加自定义 header，这里改用 fetch + ReadableStream 手动解析。
 */
export function createSSEStream(url, handlers) {
  const ctrl = new AbortController();
  let closed = false;
  const buffer = { text: "" };

  function dispatch(raw) {
    if (!raw) return;
    try {
      const payload = JSON.parse(raw);
      const ev = payload.event;
      if (ev === "connected") {
        handlers.onConnected?.(payload);
      } else if (ev === "new_waiting") {
        handlers.onNewWaiting?.(payload);
      } else if (ev === "pool_refresh") {
        handlers.onPoolRefresh?.(payload);
      } else if (ev === "new_message") {
        handlers.onNewMessage?.(payload);
      } else if (ev === "keepalive") {
        handlers.onKeepalive?.();
      }
      handlers.onAny?.(payload);
    } catch (_) {
      /* ignore parse error */
    }
  }

  async function run() {
    const token = localStorage.getItem("huami_token");
    try {
      const resp = await fetch(url, {
        signal: ctrl.signal,
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      });
      if (!resp.ok) throw new Error("SSE HTTP " + resp.status);
      const reader = resp.body.getReader();
      const decoder = new TextDecoder("utf-8");
      while (!closed) {
        const { value, done } = await reader.read();
        if (done) break;
        buffer.text += decoder.decode(value, { stream: true });
        let idx;
        while ((idx = buffer.text.indexOf("\n\n")) >= 0) {
          const chunk = buffer.text.slice(0, idx);
          buffer.text = buffer.text.slice(idx + 2);
          const dataLine = chunk
            .split("\n")
            .map((s) => s.trim())
            .find((s) => s.startsWith("data:"));
          if (dataLine) dispatch(dataLine.slice(5).trim());
        }
      }
    } catch (e) {
      if (closed) return;
      handlers.onError?.(e);
    } finally {
      if (!closed) handlers.onDisconnected?.();
    }
  }

  run();
  return {
    close() {
      closed = true;
      try { ctrl.abort(); } catch (_) { /* noop */ }
    },
  };
}

export default api;
