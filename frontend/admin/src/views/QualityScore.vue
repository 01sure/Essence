<template>
  <el-card shadow="never">
    <div class="toolbar">
      <el-select v-model="query.status" placeholder="会话状态" clearable style="width: 150px" @change="load">
        <el-option label="已结束" value="closed" />
        <el-option label="人工接待中" value="human_active" />
        <el-option label="AI 接待中" value="ai_active" />
        <el-option label="等待人工" value="waiting_human" />
      </el-select>
      <el-input v-model="query.visitor" placeholder="访客ID模糊搜" clearable style="width: 180px" @keyup.enter="load" />
      <el-input-number v-model="query.minScore" :min="0" :max="100" :step="5" controls-position="right" placeholder="最低分" style="width: 140px; margin-left: 6px" />
      <el-input-number v-model="query.maxScore" :min="0" :max="100" :step="5" controls-position="right" placeholder="最高分" style="width: 140px; margin-left: 6px" />
      <el-checkbox v-model="onlyUnscored" style="margin-left: 10px" @change="load">只看未打分</el-checkbox>
      <el-button type="primary" @click="load">查询</el-button>
    </div>

    <el-table :data="rows" v-loading="loading" size="default">
      <el-table-column label="会话ID" width="130">
        <template #default="{ row }"><span :title="row.id">{{ row.id.slice(0, 10) }}…</span></template>
      </el-table-column>
      <el-table-column prop="visitor_id" label="访客ID" width="120" show-overflow-tooltip />
      <el-table-column prop="status" label="状态" width="110">
        <template #default="{ row }">
          <el-tag :type="STATUS_TYPE[row.status]" size="small">{{ STATUS_TEXT[row.status] }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="human_admin_name" label="接待坐席" width="120">
        <template #default="{ row }">{{ row.human_admin_name || "-" }}</template>
      </el-table-column>
      <el-table-column label="质检分" width="100">
        <template #default="{ row }">
          <el-tag v-if="row.quality_score != null" :type="scoreType(row.quality_score)" size="small">{{ row.quality_score }}</el-tag>
          <span v-else style="color: #c0c4cc">未打分</span>
        </template>
      </el-table-column>
      <el-table-column prop="rating" label="用户评分" width="90">
        <template #default="{ row }">{{ row.rating ? "★".repeat(row.rating) : "-" }}</template>
      </el-table-column>
      <el-table-column prop="last_message" label="消息预览" min-width="260" show-overflow-tooltip />
      <el-table-column prop="updated_at" label="更新时间" width="170">
        <template #default="{ row }">{{ (row.updated_at || "").replace("T", " ").slice(0, 19) }}</template>
      </el-table-column>
      <el-table-column label="操作" width="160" fixed="right">
        <template #default="{ row }">
          <el-button link type="primary" @click="openDetail(row)">详情</el-button>
          <el-button link type="warning" @click="showScore(row)">打分</el-button>
        </template>
      </el-table-column>
    </el-table>

    <el-pagination
      style="margin-top: 14px; justify-content: flex-end"
      layout="total, prev, pager, next"
      :total="total" :page-size="20" v-model:current-page="query.page" @current-change="load"
    />
  </el-card>

  <!-- 会话详情 Drawer -->
  <el-drawer v-model="drawer" :title="'会话详情 ' + (current?.id || '').slice(0, 8)" size="560px">
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
    <div style="border-top: 1px solid #eee; padding: 12px 0">
      <el-form label-width="80px">
        <el-form-item label="质检分">
          <el-rate v-model="form.score" :max="100" :colors="['#f56c6c','#e6a23c','#67c23a']" show-score text-color="#ff9900" />
        </el-form-item>
        <el-form-item label="备注">
          <el-input v-model="form.remark" type="textarea" :rows="2" maxlength="500" show-word-limit />
        </el-form-item>
        <el-form-item>
          <el-button type="primary" @click="submit">提交评分</el-button>
          <span v-if="current?.quality_created_at" style="margin-left: 10px; color: #909399; font-size: 12px">
            最近打分：{{ current.quality_created_at.replace("T", " ").slice(0, 19) }}
            <span v-if="current.quality_admin_name"> · by {{ current.quality_admin_name }}</span>
          </span>
        </el-form-item>
      </el-form>
    </div>
  </el-drawer>
</template>

<script setup>
import { onMounted, reactive, ref, nextTick } from "vue";
import { ElMessage } from "element-plus";
import api from "../api";

const STATUS_TEXT = { ai_active: "AI 接待中", waiting_human: "等待人工", human_active: "人工接待中", closed: "已结束" };
const STATUS_TYPE = { ai_active: "primary", waiting_human: "danger", human_active: "warning", closed: "info" };
const ROLE_TEXT = { user: "用户", assistant: "AI 小华", admin: "人工客服", system: "系统" };
const INTENTS = { pre_sale: "售前", order_service: "售后", complaint: "投诉", chitchat: "闲聊", human_request: "转人工", escalated: "转人工" };

function scoreType(s) {
  if (s >= 85) return "success";
  if (s >= 60) return "warning";
  return "danger";
}

const rows = ref([]);
const total = ref(0);
const loading = ref(false);
const query = reactive({ page: 1, status: "closed", visitor: "", minScore: null, maxScore: null });
const onlyUnscored = ref(true);

const drawer = ref(false);
const current = ref(null);
const messages = ref([]);
const msgListRef = ref(null);
const form = reactive({ score: 80, remark: "" });

async function load() {
  loading.value = true;
  try {
    const params = { page: query.page, size: 20 };
    if (query.status) params.status = query.status;
    if (query.visitor) params.keyword = query.visitor;
    const { data } = await api.get("/admin/sessions", { params });
    let items = data.items || [];
    if (query.minScore != null) items = items.filter(i => i.quality_score != null && i.quality_score >= query.minScore);
    if (query.maxScore != null) items = items.filter(i => i.quality_score != null && i.quality_score <= query.maxScore);
    if (onlyUnscored.value) items = items.filter(i => i.quality_score == null);
    rows.value = items;
    total.value = data.total;
  } finally {
    loading.value = false;
  }
}

async function openDetail(row) {
  current.value = row;
  drawer.value = true;
  form.score = row.quality_score ?? 80;
  form.remark = row.quality_remark || "";
  try {
    const { data } = await api.get(`/admin/sessions/${row.id}`);
    messages.value = data.messages;
    Object.assign(current.value, data.session);
    nextTick(() => { if (msgListRef.value) msgListRef.value.scrollTop = msgListRef.value.scrollHeight; });
  } catch (_) { /* noop */ }
}

function showScore(row) { openDetail(row); }

async function submit() {
  if (!current.value) return;
  try {
    await api.post(`/admin/sessions/${current.value.id}/quality`, { score: form.score, remark: form.remark });
    ElMessage.success("打分成功");
    // 回写到列表对应行
    const idx = rows.value.findIndex(r => r.id === current.value.id);
    if (idx >= 0) rows.value[idx].quality_score = form.score;
    if (current.value) current.value.quality_score = form.score;
    if (current.value) current.value.quality_remark = form.remark;
  } catch (_) { /* noop */ }
}

onMounted(load);
</script>

<style scoped>
.toolbar { display: flex; align-items: center; gap: 10px; margin-bottom: 14px; flex-wrap: wrap; }
.msg-list { height: calc(100% - 200px); overflow-y: auto; padding: 4px; margin-bottom: 16px; border: 1px dashed #eee; border-radius: 8px; }
.msg-row { display: flex; margin-bottom: 12px; }
.msg-row.user { justify-content: flex-end; }
.msg-bubble { max-width: 82%; background: #fff; border-radius: 10px; padding: 8px 12px; font-size: 13px; box-shadow: 0 1px 3px rgba(0,0,0,.06); }
.msg-row.assistant .msg-bubble { background: #f0f2f5; }
.msg-row.admin .msg-bubble { background: #e8f4ff; }
.msg-row.system .msg-bubble { background: #f4f4f5; color: #909399; font-size: 12px; }
.msg-role { font-size: 11px; color: #999; margin-bottom: 4px; }
.msg-intent { color: #ff6b00; margin-left: 4px; }
</style>
