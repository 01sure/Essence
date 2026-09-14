<template>
  <el-card shadow="never">
    <div class="toolbar">
      <el-select v-model="query.status" placeholder="全部状态" clearable style="width: 160px" @change="load">
        <el-option label="AI 接待中" value="ai_active" />
        <el-option label="等待人工" value="waiting_human" />
        <el-option label="人工接待中" value="human_active" />
        <el-option label="已结束" value="closed" />
      </el-select>
      <el-button type="primary" @click="load">刷新</el-button>
      <el-switch v-model="autoRefresh" active-text="自动刷新(10s)" style="margin-left: 12px" />
    </div>

    <el-table :data="rows" v-loading="loading" size="default">
      <el-table-column prop="id" label="会话ID" width="110">
        <template #default="{ row }"><span :title="row.id">{{ row.id.slice(0, 8) }}…</span></template>
      </el-table-column>
      <el-table-column prop="status" label="状态" width="120">
        <template #default="{ row }">
          <el-tag :type="STATUS_TYPE[row.status]" size="small">{{ STATUS_TEXT[row.status] }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="last_message" label="最新消息" min-width="220" show-overflow-tooltip />
      <el-table-column prop="intent_last" label="最近意图" width="100">
        <template #default="{ row }">{{ INTENTS[row.intent_last] || row.intent_last || "-" }}</template>
      </el-table-column>
      <el-table-column prop="rating" label="评分" width="80">
        <template #default="{ row }">{{ row.rating ? "★".repeat(row.rating) : "-" }}</template>
      </el-table-column>
      <el-table-column prop="updated_at" label="更新时间" width="170">
        <template #default="{ row }">{{ (row.updated_at || "").replace("T", " ").slice(0, 19) }}</template>
      </el-table-column>
      <el-table-column label="操作" width="100" fixed="right">
        <template #default="{ row }">
          <el-button link type="primary" @click="openDetail(row)">查看</el-button>
        </template>
      </el-table-column>
    </el-table>

    <el-pagination
      style="margin-top: 14px; justify-content: flex-end"
      layout="total, prev, pager, next"
      :total="total" :page-size="query.size" v-model:current-page="query.page" @current-change="load"
    />
  </el-card>

  <el-drawer v-model="drawer" :title="'会话详情 ' + (current?.id || '').slice(0, 8)" size="520px">
    <div class="msg-list" ref="msgListRef">
      <div v-for="m in messages" :key="m.id" :class="['msg-row', m.role]">
        <div class="msg-bubble">
          <div class="msg-role">{{ ROLE_TEXT[m.role] || m.role }}<span v-if="m.intent" class="msg-intent">· {{ INTENTS[m.intent] || m.intent }}</span></div>
          <div style="white-space: pre-wrap">{{ m.content }}</div>
        </div>
      </div>
    </div>
    <div class="reply-box" v-if="canReply">
      <el-input v-model="replyText" type="textarea" :rows="2" placeholder="以人工客服身份回复…" />
      <div class="reply-actions">
        <el-button type="primary" :disabled="!replyText.trim()" @click="sendReply">发送回复</el-button>
        <el-button @click="backToAI">交还 AI</el-button>
        <el-button type="danger" plain @click="closeSession">结束会话</el-button>
      </div>
    </div>
    <el-alert v-else-if="current?.status === 'closed'" title="会话已结束" type="info" :closable="false" style="margin-top: 10px" />
  </el-drawer>
</template>

<script setup>
import { computed, onMounted, onUnmounted, reactive, ref, nextTick } from "vue";
import api from "../api";

const STATUS_TEXT = { ai_active: "AI 接待中", waiting_human: "等待人工", human_active: "人工接待中", closed: "已结束" };
const STATUS_TYPE = { ai_active: "primary", waiting_human: "danger", human_active: "warning", closed: "info" };
const ROLE_TEXT = { user: "用户", assistant: "AI 小华", admin: "人工客服", system: "系统" };
const INTENTS = { pre_sale: "售前", order_service: "售后", complaint: "投诉", chitchat: "闲聊", human_request: "转人工" };

const rows = ref([]);
const total = ref(0);
const loading = ref(false);
const query = reactive({ status: "", page: 1, size: 20 });
const autoRefresh = ref(false);
const drawer = ref(false);
const current = ref(null);
const messages = ref([]);
const replyText = ref("");
const msgListRef = ref(null);
let detailTimer = null;

const canReply = computed(() => ["waiting_human", "human_active"].includes(current.value?.status));

async function load() {
  loading.value = true;
  try {
    const { data } = await api.get("/admin/sessions", { params: query });
    rows.value = data.items;
    total.value = data.total;
  } finally {
    loading.value = false;
  }
}

async function openDetail(row) {
  current.value = row;
  drawer.value = true;
  await loadDetail();
  clearInterval(detailTimer);
  detailTimer = setInterval(loadDetail, 5000);
}

async function loadDetail() {
  if (!current.value) return;
  const { data } = await api.get(`/admin/sessions/${current.value.id}`);
  messages.value = data.messages;
  if (current.value) current.value.status = data.session.status;
  nextTick(() => { if (msgListRef.value) msgListRef.value.scrollTop = msgListRef.value.scrollHeight; });
}

async function sendReply() {
  const content = replyText.value.trim();
  if (!content) return;
  await api.post(`/admin/sessions/${current.value.id}/messages`, { content });
  replyText.value = "";
  await loadDetail();
}

async function backToAI() {
  await api.post(`/admin/sessions/${current.value.id}/back-to-ai`);
  await loadDetail();
}

async function closeSession() {
  await api.post(`/admin/sessions/${current.value.id}/close`);
  await loadDetail();
  load();
}

onMounted(() => {
  load();
  setInterval(() => { if (autoRefresh.value) load(); }, 10000);
});
onUnmounted(() => clearInterval(detailTimer));
</script>

<style scoped>
.toolbar { display: flex; align-items: center; gap: 10px; margin-bottom: 14px; }
.msg-list { height: calc(100% - 120px); overflow-y: auto; padding: 4px; }
.msg-row { display: flex; margin-bottom: 12px; }
.msg-row.user { justify-content: flex-end; }
.msg-bubble { max-width: 82%; background: #fff; border-radius: 10px; padding: 8px 12px; font-size: 13px; box-shadow: 0 1px 3px rgba(0,0,0,.06); }
.msg-row.assistant .msg-bubble { background: #f0f2f5; }
.msg-row.admin .msg-bubble { background: #e8f4ff; }
.msg-role { font-size: 11px; color: #999; margin-bottom: 4px; }
.msg-intent { color: #ff6b00; margin-left: 4px; }
.reply-box { border-top: 1px solid #eee; padding-top: 10px; }
.reply-actions { margin-top: 8px; display: flex; gap: 8px; }
</style>
