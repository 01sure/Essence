<template>
  <div>
    <!-- 顶部池统计条 -->
    <el-row :gutter="14" style="margin-bottom: 16px">
      <el-col :span="6">
        <el-card shadow="hover" class="stat">
          <div class="stat-label">待抢会话</div>
          <div class="stat-value" style="color: #f56c6c">{{ pool.waiting }}</div>
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card shadow="hover" class="stat">
          <div class="stat-label">我接待中</div>
          <div class="stat-value" style="color: #409eff">{{ pool.mine_active }}</div>
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card shadow="hover" class="stat">
          <div class="stat-label">容量上限</div>
          <div class="stat-value" style="color: #67c23a">{{ pool.capacity }}</div>
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card shadow="hover" class="stat">
          <div class="stat-label">SSE 连接</div>
          <div class="stat-value" :style="{ color: sseOn ? '#67c23a' : '#909399' }">
            {{ sseOn ? "已连接" : "未连接" }}
          </div>
        </el-card>
      </el-col>
    </el-row>

    <el-card shadow="never">
      <el-tabs v-model="tab" @tab-change="onTabChange">
        <el-tab-pane label="🆕 待抢池" name="waiting">
          <div class="sub-tip">用户点击「转人工」后的新会话会自动进入这里，点 <b>抢单</b> 原子领取（并发冲突返回 409）。</div>
          <div style="margin-top: 10px">
            <el-table :data="rows" v-loading="loading" size="default">
              <el-table-column label="会话ID" width="130">
                <template #default="{ row }"><span :title="row.id">{{ row.id.slice(0, 10) }}…</span></template>
              </el-table-column>
              <el-table-column prop="visitor_id" label="访客ID" width="120" show-overflow-tooltip />
              <el-table-column prop="last_message" label="最新消息" min-width="260" show-overflow-tooltip />
              <el-table-column prop="updated_at" label="更新时间" width="170">
                <template #default="{ row }">{{ (row.updated_at || "").replace("T", " ").slice(0, 19) }}</template>
              </el-table-column>
              <el-table-column label="操作" width="140" fixed="right">
                <template #default="{ row }">
                  <el-button size="small" type="primary" @click="claim(row)">抢 单</el-button>
                  <el-button size="small" link type="primary" @click="openDetail(row)">预览</el-button>
                </template>
              </el-table-column>
            </el-table>
          </div>
        </el-tab-pane>

        <el-tab-pane label="💬 我的会话" name="mine">
          <div class="sub-tip">你当前接待的所有会话。可以回复、释放回池、转交同事、交还 AI、结束。</div>
          <div style="margin: 10px 0">
            <el-select v-model="mineFilter" placeholder="按状态筛选" clearable style="width: 160px" @change="load">
              <el-option label="人工接待中" value="human_active" />
              <el-option label="等待人工(回池)" value="waiting_human" />
              <el-option label="已结束" value="closed" />
            </el-select>
          </div>
          <el-table :data="rows" v-loading="loading" size="default">
            <el-table-column label="会话ID" width="130">
              <template #default="{ row }"><span :title="row.id">{{ row.id.slice(0, 10) }}…</span></template>
            </el-table-column>
            <el-table-column prop="status" label="状态" width="120">
              <template #default="{ row }">
                <el-tag :type="STATUS_TYPE[row.status]" size="small">{{ STATUS_TEXT[row.status] }}</el-tag>
              </template>
            </el-table-column>
            <el-table-column prop="last_message" label="最新消息" min-width="260" show-overflow-tooltip />
            <el-table-column prop="rating" label="评分" width="80">
              <template #default="{ row }">{{ row.rating ? "★".repeat(row.rating) : "-" }}</template>
            </el-table-column>
            <el-table-column prop="updated_at" label="更新时间" width="170">
              <template #default="{ row }">{{ (row.updated_at || "").replace("T", " ").slice(0, 19) }}</template>
            </el-table-column>
            <el-table-column label="操作" width="260" fixed="right">
              <template #default="{ row }">
                <el-button size="small" type="primary" @click="openDetail(row)">打开</el-button>
                <el-button size="small" @click="doRelease(row)" v-if="row.status === 'human_active'">释放</el-button>
                <el-button size="small" type="success" plain @click="showTransfer(row)" v-if="row.status === 'human_active'">转交</el-button>
              </template>
            </el-table-column>
          </el-table>
        </el-tab-pane>
      </el-tabs>

      <el-pagination
        style="margin-top: 14px; justify-content: flex-end"
        layout="total, prev, pager, next"
        :total="total" :page-size="20" v-model:current-page="page" @current-change="load"
      />
    </el-card>

    <!-- 会话详情 Drawer -->
    <el-drawer v-model="drawer" :title="'会话详情 ' + (current?.id || '').slice(0, 8)" size="620px">
      <div class="msg-list" ref="msgListRef">
        <div v-for="m in messages" :key="m.id" :class="['msg-row', m.role]">
          <div class="msg-bubble">
            <div class="msg-role">
              {{ ROLE_TEXT[m.role] || m.role }}
              <span v-if="m.intent" class="msg-intent">· {{ INTENTS[m.intent] || m.intent }}</span>
              <span v-if="m.meta?.admin_name" class="msg-intent">· {{ m.meta.admin_name }}</span>
            </div>
            <div style="white-space: pre-wrap">{{ m.content }}</div>
          </div>
        </div>
      </div>
      <div class="reply-box" v-if="canReply">
        <el-input v-model="replyText" type="textarea" :rows="2" placeholder="以人工客服身份回复…（Enter 发送 / Shift+Enter 换行）" @keydown.enter.exact.prevent="sendReply" />
        <div class="reply-actions">
          <el-button type="primary" :disabled="!replyText.trim()" @click="sendReply">发送回复</el-button>
          <el-button @click="doBackToAI" v-if="current?.status === 'human_active'">交还 AI</el-button>
          <el-button @click="doRelease" v-if="current?.status === 'human_active'">释放回池</el-button>
          <el-button type="success" plain @click="showTransfer(current)" v-if="current?.status === 'human_active'">转交同事</el-button>
          <el-button type="danger" plain @click="doClose">结束会话</el-button>
        </div>
      </div>
      <el-alert v-else-if="current?.status === 'closed'" title="会话已结束" type="info" :closable="false" style="margin-top: 10px">
        <template #default>
          <div v-if="u.can_qa" style="margin-top: 8px">
            <el-button size="small" type="warning" @click="showQuality(current)">打 分</el-button>
            <span v-if="current.quality_score != null" style="margin-left: 10px; color: #666">
              得分：<b>{{ current.quality_score }}</b> / 100
              <span v-if="current.quality_remark">（{{ current.quality_remark }}）</span>
            </span>
          </div>
        </template>
      </el-alert>
    </el-drawer>

    <!-- 转交弹窗 -->
    <el-dialog v-model="transferVisible" title="转交会话" width="420px">
      <el-select v-model="targetAdminId" placeholder="选择目标坐席（仅显示在线 / 忙碌）" filterable style="width: 100%">
        <el-option
          v-for="a in onlineAgents.filter(o => o.id !== u.id)"
          :key="a.id"
          :label="`${a.display_name || a.role_label}（${a.role_label} · 容量${a.capacity}）`"
          :value="a.id"
        />
      </el-select>
      <template #footer>
        <el-button @click="transferVisible = false">取消</el-button>
        <el-button type="primary" :disabled="!targetAdminId" @click="doTransfer">确认转交</el-button>
      </template>
    </el-dialog>

    <!-- 质检弹窗 -->
    <el-dialog v-model="qualityVisible" title="会话质检" width="460px">
      <el-form label-width="80px">
        <el-form-item label="评分">
          <el-rate v-model="quality.score" :max="100" :colors="['#f56c6c','#e6a23c','#67c23a']" show-score text-color="#ff9900" />
        </el-form-item>
        <el-form-item label="备注">
          <el-input v-model="quality.remark" type="textarea" :rows="3" maxlength="500" show-word-limit />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="qualityVisible = false">取消</el-button>
        <el-button type="primary" @click="doQuality">提交</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { computed, onMounted, onUnmounted, reactive, ref, nextTick, watch } from "vue";
import { ElMessage } from "element-plus";
import api, { createSSEStream } from "../api";
import { useAuthStore } from "../stores/auth";

const auth = useAuthStore();
const u = computed(() => auth.user || {});

const STATUS_TEXT = { ai_active: "AI 接待中", waiting_human: "等待人工", human_active: "人工接待中", closed: "已结束" };
const STATUS_TYPE = { ai_active: "primary", waiting_human: "danger", human_active: "warning", closed: "info" };
const ROLE_TEXT = { user: "用户", assistant: "AI 小华", admin: "人工客服", system: "系统" };
const INTENTS = { pre_sale: "售前", order_service: "售后", complaint: "投诉", chitchat: "闲聊", human_request: "转人工", escalated: "转人工" };

const tab = ref("waiting");
const page = ref(1);
const rows = ref([]);
const total = ref(0);
const loading = ref(false);
const pool = reactive({ waiting: 0, mine_active: 0, capacity: 0 });
const sseOn = ref(false);
const mineFilter = ref("");

const drawer = ref(false);
const current = ref(null);
const messages = ref([]);
const replyText = ref("");
const msgListRef = ref(null);
let detailTimer = null;
let sseClient = null;
let pageTimer = null;

const transferVisible = ref(false);
const targetAdminId = ref(null);
const onlineAgents = ref([]);
const transferFor = ref(null);

const qualityVisible = ref(false);
const quality = reactive({ score: 80, remark: "" });
const qualityFor = ref(null);

const canReply = computed(() => ["waiting_human", "human_active"].includes(current.value?.status));

function onTabChange() { page.value = 1; load(); }

async function loadPool() {
  try {
    const { data } = await api.get("/admin/sessions/stats");
    Object.assign(pool, data);
  } catch (_) { /* noop */ }
}

async function load() {
  loading.value = true;
  try {
    const params = { page: page.value, size: 20 };
    if (tab.value === "waiting") params.pool = "waiting";
    else params.mine = true;
    if (tab.value === "mine" && mineFilter.value) params.status = mineFilter.value;
    const { data } = await api.get("/admin/sessions", { params });
    rows.value = data.items;
    total.value = data.total;
  } finally {
    loading.value = false;
  }
}

async function claim(row) {
  try {
    await api.post(`/admin/sessions/${row.id}/claim`);
    ElMessage.success("领取成功，已跳到「我的会话」");
    tab.value = "mine";
  } catch (e) {
    // 409 已由拦截器弹 Notification；这里只刷新列表
  }
  await loadPool();
  await load();
}

async function openDetail(row) {
  current.value = row;
  drawer.value = true;
  await loadDetail();
  clearInterval(detailTimer);
  detailTimer = setInterval(loadDetail, 3500);
}

async function loadDetail() {
  if (!current.value) return;
  try {
    const { data } = await api.get(`/admin/sessions/${current.value.id}`);
    messages.value = data.messages;
    if (current.value) Object.assign(current.value, data.session);
    nextTick(() => { if (msgListRef.value) msgListRef.value.scrollTop = msgListRef.value.scrollHeight; });
  } catch (_) { /* drawer 关闭可能 403 */ }
}

async function sendReply() {
  const content = replyText.value.trim();
  if (!content) return;
  try {
    await api.post(`/admin/sessions/${current.value.id}/messages`, { content });
    replyText.value = "";
  } catch (_) { /* 拦截器已提示 */ }
  await loadDetail();
}

async function doRelease(row = current.value) {
  if (!row) return;
  try {
    await api.post(`/admin/sessions/${row.id}/release`);
    ElMessage.success("已释放回池");
  } catch (_) { /* noop */ }
  await loadPool();
  await loadDetail();
  await load();
}

async function doBackToAI() {
  if (!current.value) return;
  try {
    await api.post(`/admin/sessions/${current.value.id}/back-to-ai`);
    ElMessage.success("已交还 AI 客服");
  } catch (_) { /* noop */ }
  await loadPool();
  await loadDetail();
  await load();
}

async function doClose() {
  if (!current.value) return;
  try {
    await api.post(`/admin/sessions/${current.value.id}/close`);
    ElMessage.success("会话已结束");
  } catch (_) { /* noop */ }
  await loadPool();
  await loadDetail();
  await load();
}

async function showTransfer(row) {
  transferFor.value = row;
  targetAdminId.value = null;
  try {
    const { data } = await api.get("/admin/auth/online-agents");
    onlineAgents.value = data;
  } catch (_) { onlineAgents.value = []; }
  transferVisible.value = true;
}

async function doTransfer() {
  if (!transferFor.value || !targetAdminId.value) return;
  try {
    await api.post(`/admin/sessions/${transferFor.value.id}/transfer`, { target_admin_id: targetAdminId.value });
    ElMessage.success("已转交");
    transferVisible.value = false;
  } catch (_) { /* noop */ }
  await loadPool();
  await loadDetail();
  await load();
}

async function showQuality(row) {
  qualityFor.value = row;
  quality.score = row.quality_score ?? 80;
  quality.remark = row.quality_remark || "";
  qualityVisible.value = true;
}

async function doQuality() {
  if (!qualityFor.value) return;
  try {
    await api.post(`/admin/sessions/${qualityFor.value.id}/quality`, { score: quality.score, remark: quality.remark });
    ElMessage.success("质检已提交");
    qualityVisible.value = false;
  } catch (_) { /* noop */ }
  await loadDetail();
  await load();
}

function connectSSE() {
  try {
    sseClient = createSSEStream("/api/admin/sessions/stream", {
      onConnected: () => { sseOn.value = true; },
      onNewWaiting: () => { loadPool(); if (tab.value === "waiting") load(); },
      onPoolRefresh: () => { loadPool(); load(); },
      onNewMessage: (payload) => {
        if (current.value && payload.session_id === current.value.id) loadDetail();
        else load();
      },
      onKeepalive: () => { sseOn.value = true; },
      onDisconnected: () => { sseOn.value = false; },
      onError: () => { sseOn.value = false; },
    });
  } catch (e) {
    console.warn("workbench SSE init fail:", e);
  }
}

onMounted(async () => {
  await loadPool();
  await load();
  pageTimer = setInterval(async () => {
    await loadPool();
    if (tab.value === "waiting") await load();
  }, 10000);
  setTimeout(connectSSE, 300);
});

onUnmounted(() => {
  sseClient?.close();
  clearInterval(detailTimer);
  clearInterval(pageTimer);
});

watch(tab, () => clearInterval(detailTimer));
</script>

<style scoped>
.stat { height: 100%; }
.stat-label { color: #999; font-size: 13px; }
.stat-value { font-size: 30px; font-weight: 700; margin-top: 8px; }
.sub-tip { color: #909399; font-size: 13px; }

.msg-list { height: calc(100% - 160px); overflow-y: auto; padding: 4px; }
.msg-row { display: flex; margin-bottom: 12px; }
.msg-row.user { justify-content: flex-end; }
.msg-bubble { max-width: 82%; background: #fff; border-radius: 10px; padding: 8px 12px; font-size: 13px; box-shadow: 0 1px 3px rgba(0,0,0,.06); }
.msg-row.assistant .msg-bubble { background: #f0f2f5; }
.msg-row.admin .msg-bubble { background: #e8f4ff; }
.msg-row.system .msg-bubble { background: #f4f4f5; color: #909399; font-size: 12px; }
.msg-role { font-size: 11px; color: #999; margin-bottom: 4px; }
.msg-intent { color: #ff6b00; margin-left: 4px; }
.reply-box { border-top: 1px solid #eee; padding-top: 10px; }
.reply-actions { margin-top: 8px; display: flex; gap: 8px; flex-wrap: wrap; }
</style>
