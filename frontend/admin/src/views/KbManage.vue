<template>
  <el-card shadow="never">
    <div class="toolbar">
      <el-select v-model="query.doc_type" placeholder="全部类型" clearable style="width: 140px" @change="load">
        <el-option label="FAQ 问答" value="faq" />
        <el-option label="售后政策" value="policy" />
        <el-option label="销售话术" value="script" />
      </el-select>
      <el-input v-model="query.keyword" placeholder="搜索标题" style="width: 200px" clearable @keyup.enter="load" />
      <el-button type="primary" @click="load">查询</el-button>
      <div style="flex: 1"></div>
      <el-button @click="syncAll" :loading="syncing">同步全部到 ES</el-button>
      <el-button type="warning" @click="openEdit()">新增文档</el-button>
    </div>

    <el-table :data="rows" v-loading="loading">
      <el-table-column prop="id" label="ID" width="60" />
      <el-table-column prop="doc_type" label="类型" width="100">
        <template #default="{ row }">
          <el-tag :type="{ faq: 'success', policy: 'warning', script: 'danger' }[row.doc_type]" size="small">
            {{ { faq: "FAQ", policy: "政策", script: "话术" }[row.doc_type] }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="title" label="标题" min-width="180" show-overflow-tooltip />
      <el-table-column prop="category" label="分类" width="110" />
      <el-table-column label="标签" min-width="160">
        <template #default="{ row }">
          <el-tag v-for="t in row.tags || []" :key="t" size="small" style="margin-right: 4px">{{ t }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="enabled" label="启用" width="80">
        <template #default="{ row }">
          <el-switch :model-value="row.enabled" @change="(v) => toggleEnabled(row, v)" />
        </template>
      </el-table-column>
      <el-table-column prop="es_synced" label="ES" width="70">
        <template #default="{ row }">
          <el-tag :type="row.es_synced ? 'success' : 'info'" size="small">{{ row.es_synced ? "已同步" : "未同步" }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="updated_at" label="更新时间" width="170">
        <template #default="{ row }">{{ (row.updated_at || "").replace("T", " ").slice(0, 19) }}</template>
      </el-table-column>
      <el-table-column label="操作" width="150" fixed="right">
        <template #default="{ row }">
          <el-button link type="primary" @click="openEdit(row)">编辑</el-button>
          <el-button link type="warning" @click="syncOne(row)">同步</el-button>
          <el-popconfirm title="确认删除该文档？" @confirm="remove(row)">
            <template #reference><el-button link type="danger">删除</el-button></template>
          </el-popconfirm>
        </template>
      </el-table-column>
    </el-table>

    <el-pagination
      style="margin-top: 14px; justify-content: flex-end"
      layout="total, prev, pager, next"
      :total="total" :page-size="query.size" v-model:current-page="query.page" @current-change="load"
    />
  </el-card>

  <el-dialog v-model="dialog" :title="form.id ? '编辑文档' : '新增文档'" width="640px" top="6vh">
    <el-form :model="form" label-width="80px">
      <el-form-item label="类型">
        <el-radio-group v-model="form.doc_type">
          <el-radio value="faq">FAQ 问答</el-radio>
          <el-radio value="policy">售后政策</el-radio>
          <el-radio value="script">销售话术</el-radio>
        </el-radio-group>
      </el-form-item>
      <el-form-item label="标题"><el-input v-model="form.title" maxlength="200" /></el-form-item>
      <el-form-item label="分类"><el-input v-model="form.category" style="width: 220px" /></el-form-item>
      <el-form-item label="标签">
        <el-input v-model="tagsText" placeholder="多个标签用逗号分隔，如：退货,7天,无理由" />
      </el-form-item>
      <el-form-item label="内容">
        <el-input v-model="form.content" type="textarea" :rows="12" placeholder="支持多段文本，系统会自动分块向量化" />
      </el-form-item>
      <el-form-item label="启用"><el-switch v-model="form.enabled" /></el-form-item>
    </el-form>
    <template #footer>
      <el-button @click="dialog = false">取消</el-button>
      <el-button type="primary" :loading="saving" @click="save">保存并同步 ES</el-button>
    </template>
  </el-dialog>
</template>

<script setup>
import { onMounted, reactive, ref } from "vue";
import { ElMessage } from "element-plus";
import api from "../api";

const rows = ref([]);
const total = ref(0);
const loading = ref(false);
const syncing = ref(false);
const saving = ref(false);
const dialog = ref(false);
const tagsText = ref("");
const query = reactive({ keyword: "", doc_type: "", page: 1, size: 20 });
const form = reactive({ id: null, doc_type: "faq", title: "", category: "通用", content: "", enabled: true });
const lockUpdatedAt = ref(null);

async function load() {
  loading.value = true;
  try {
    const { data } = await api.get("/admin/kb", { params: query });
    rows.value = data.items;
    total.value = data.total;
  } finally {
    loading.value = false;
  }
}

async function openEdit(row) {
  if (row) {
    const { data } = await api.get(`/admin/kb/${row.id}`);
    Object.assign(form, {
      id: data.id, doc_type: data.doc_type, title: data.title,
      category: data.category, content: data.content, enabled: data.enabled,
    });
    tagsText.value = (data.tags || []).join(",");
    // 编辑时乐观锁 token：优先用 GET doc 详情接口的 updated_at，但目前只从列表拿
    lockUpdatedAt.value = row.updated_at || null;
  } else {
    Object.assign(form, { id: null, doc_type: "faq", title: "", category: "通用", content: "", enabled: true });
    tagsText.value = "";
    lockUpdatedAt.value = null;
  }
  dialog.value = true;
}

async function save() {
  if (!form.title.trim() || (form.id ? false : !form.content.trim())) {
    ElMessage.warning("请填写标题和内容");
    return;
  }
  saving.value = true;
  try {
    const payload = {
      ...form,
      tags: tagsText.value.split(/[,，]/).map((s) => s.trim()).filter(Boolean),
    };
    delete payload.id;
    if (form.id) {
      if (!payload.content || !payload.content.trim()) delete payload.content;
      payload.if_match_updated_at = lockUpdatedAt.value || null;
      const { data } = await api.put(`/admin/kb/${form.id}`, payload);
      if (data?.updated_at) lockUpdatedAt.value = data.updated_at;
    } else {
      await api.post("/admin/kb", payload);
    }
    ElMessage.success("已保存并同步");
    dialog.value = false;
    load();
  } finally {
    saving.value = false;
  }
}

async function toggleEnabled(row, v) {
  try {
    await api.put(`/admin/kb/${row.id}`, {
      doc_type: row.doc_type, title: row.title, category: row.category,
      tags: row.tags, enabled: v, if_match_updated_at: row.updated_at || null,
    });
    ElMessage.success("已更新");
  } catch (_) {
    row.enabled = !v; // 409 回滚 UI
  }
  load();
}

async function syncOne(row) {
  await api.post(`/admin/kb/${row.id}/sync`);
  ElMessage.success("已同步");
  load();
}

async function syncAll() {
  syncing.value = true;
  try {
    const { data } = await api.post("/admin/kb/sync-all");
    ElMessage.success(`已同步 ${data.synced_docs} 篇文档 / ${data.total_chunks} 个分块`);
    load();
  } finally {
    syncing.value = false;
  }
}

async function remove(row) {
  await api.delete(`/admin/kb/${row.id}`);
  ElMessage.success("已删除");
  load();
}

onMounted(load);
</script>

<style scoped>
.toolbar { display: flex; align-items: center; gap: 10px; margin-bottom: 14px; }
</style>
