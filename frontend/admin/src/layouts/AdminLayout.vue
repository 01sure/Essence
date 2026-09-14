<template>
  <el-container style="height: 100vh">
    <el-aside width="210px" class="aside">
      <div class="logo">华米 AI 客服</div>
      <el-menu
        :default-active="$route.path"
        router
        background-color="#1f2430"
        text-color="#aab2c0"
        active-text-color="#ff7a18"
      >
        <el-menu-item index="/dashboard">📊 数据看板</el-menu-item>
        <el-menu-item v-if="u.can_agent" index="/workbench">
          <el-badge :value="waitingCount" :hidden="!waitingCount" class="menu-badge">
            🎧 坐席工作台
          </el-badge>
        </el-menu-item>
        <el-menu-item v-if="u.can_agent" index="/chat-window">💬 智能客服窗口</el-menu-item>
        <el-menu-item v-if="u.can_agent" index="/sessions">🧾 会话管理</el-menu-item>
        <el-menu-item v-if="u.can_agent" index="/after-sale">🛠️ 售后工单</el-menu-item>
        <el-menu-item v-if="u.can_qa" index="/quality">🧪 质检中心</el-menu-item>
        <el-menu-item v-if="u.can_configure" index="/kb">📚 知识库</el-menu-item>
        <el-menu-item v-if="u.can_configure" index="/products">📦 商品管理</el-menu-item>
        <el-menu-item v-if="u.can_configure" index="/prompts">✏️ 话术配置</el-menu-item>
        <el-menu-item v-if="u.can_user_admin" index="/users">👤 用户管理</el-menu-item>
      </el-menu>
    </el-aside>

    <el-container>
      <el-header class="header">
        <div class="page-title">{{ $route.meta.title }}</div>
        <div class="header-right">
          <template v-if="u.can_agent">
            <el-tag size="small" :type="presenceColor" effect="dark" style="margin-right: 10px">
              坐席状态：
              <el-select
                v-model="presence"
                size="small"
                :style="{ width: '86px' }"
                @change="setPresence"
                class="presence-select"
              >
                <el-option label="在线" value="online" />
                <el-option label="忙碌" value="busy" />
                <el-option label="离线" value="offline" />
              </el-select>
            </el-tag>
          </template>
          <el-tag v-if="u.role_label" size="small" type="warning" style="margin-right: 10px">
            {{ u.role_label }}
          </el-tag>
          <span class="admin-name">{{ u.display_name || u.username }}</span>
          <el-button link type="danger" @click="logout">退出</el-button>
        </div>
      </el-header>
      <el-main class="main"><router-view /></el-main>
    </el-container>
  </el-container>
</template>

<script setup>
import { computed, onMounted, onUnmounted, ref, watch } from "vue";
import { useRouter } from "vue-router";
import api, { createSSEStream } from "../api";
import { useAuthStore } from "../stores/auth";

const auth = useAuthStore();
const router = useRouter();
const waitingCount = ref(0);
const presence = ref(auth.user?.presence || "offline");
let sseClient = null;
let timer = null;

const u = computed(() => auth.user || {});

const presenceColor = computed(() => {
  if (presence.value === "online") return "success";
  if (presence.value === "busy") return "warning";
  return "info";
});

async function refreshWaiting() {
  if (!u.value.can_agent) return;
  try {
    const { data } = await api.get("/admin/sessions/waiting/count");
    waitingCount.value = data.count;
  } catch (_) { /* ignore */ }
}

async function setPresence(v) {
  try {
    await api.put("/admin/auth/presence", { presence: v });
    if (auth.user) auth.user.presence = v;
    localStorage.setItem("huami_user", JSON.stringify(auth.user));
  } catch (_) { /* 错误已由拦截器提示 */ }
}

function connectSSE() {
  if (!u.value.can_agent) return;
  try {
    sseClient = createSSEStream("/api/admin/sessions/stream", {
      onNewWaiting: refreshWaiting,
      onPoolRefresh: refreshWaiting,
      onKeepalive: () => {},
      onError: (e) => console.warn("SSE error:", e),
    });
  } catch (e) {
    console.warn("SSE init fail:", e);
  }
}

function logout() {
  sseClient?.close();
  clearInterval(timer);
  auth.logout();
  router.push("/login");
}

onMounted(() => {
  refreshWaiting();
  timer = setInterval(refreshWaiting, 15000);
  // 给 pinia 一点初始化时间再连
  setTimeout(connectSSE, 300);
});
onUnmounted(() => {
  sseClient?.close();
  clearInterval(timer);
});

watch(
  () => auth.user?.id,
  (newId, oldId) => {
    if (newId && newId !== oldId) {
      sseClient?.close();
      setTimeout(connectSSE, 200);
    }
  }
);
</script>

<style scoped>
.aside { background: #1f2430; }
.logo { color: #fff; font-size: 17px; font-weight: 700; padding: 22px 20px; letter-spacing: 1px; }
.aside :deep(.el-menu) { border-right: none; }
.menu-badge { width: 100%; }
.header { background: #fff; display: flex; align-items: center; justify-content: space-between; box-shadow: 0 1px 4px rgba(0,0,0,.05); }
.page-title { font-size: 16px; font-weight: 600; }
.admin-name { margin-right: 12px; color: #666; font-size: 14px; }
.main { padding: 20px; overflow: auto; background: #f5f7fa; }
.presence-select :deep(.el-input__wrapper) { background: transparent; box-shadow: none; padding: 0 4px; color: #fff; }
.presence-select :deep(.el-input__inner) { color: #fff !important; font-weight: 600; }
</style>
