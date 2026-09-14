<template>
  <el-card shadow="never">
    <div class="toolbar">
      <el-input v-model="query.keyword" placeholder="搜索商品名称" style="width: 200px" clearable @keyup.enter="load" />
      <el-button type="primary" @click="load">查询</el-button>
      <div style="flex: 1"></div>
      <el-upload :show-file-list="false" accept=".json,.csv" :http-request="doImport">
        <el-button>批量导入(JSON/CSV)</el-button>
      </el-upload>
      <el-button @click="syncAll" :loading="syncing">同步全部到 ES</el-button>
      <el-button type="warning" @click="openEdit()">新增商品</el-button>
    </div>

    <el-table :data="rows" v-loading="loading">
      <el-table-column label="商品" min-width="260">
        <template #default="{ row }">
          <div style="display: flex; align-items: center; gap: 10px">
            <el-image :src="row.image_url" fit="cover" style="width: 46px; height: 46px; border-radius: 8px; flex-shrink: 0" />
            <div>
              <div style="font-size: 13px">{{ row.name }}</div>
              <div style="font-size: 11px; color: #999">{{ row.brand }} · {{ row.category }}</div>
            </div>
          </div>
        </template>
      </el-table-column>
      <el-table-column label="价格" width="130">
        <template #default="{ row }">
          <span style="color: #ff4d00; font-weight: 600">¥{{ row.price }}</span>
          <del v-if="row.original_price" style="color: #bbb; font-size: 12px; margin-left: 4px">¥{{ row.original_price }}</del>
        </template>
      </el-table-column>
      <el-table-column prop="stock" label="库存" width="80" />
      <el-table-column prop="sales" label="月销" width="90" />
      <el-table-column prop="rating" label="评分" width="70" />
      <el-table-column prop="enabled" label="上架" width="70">
        <template #default="{ row }">
          <el-switch :model-value="row.enabled" @change="(v) => toggleEnabled(row, v)" />
        </template>
      </el-table-column>
      <el-table-column prop="es_synced" label="ES" width="70">
        <template #default="{ row }">
          <el-tag :type="row.es_synced ? 'success' : 'info'" size="small">{{ row.es_synced ? "已同步" : "未同步" }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="150" fixed="right">
        <template #default="{ row }">
          <el-button link type="primary" @click="openEdit(row)">编辑</el-button>
          <el-button link type="warning" @click="syncOne(row)">同步</el-button>
          <el-popconfirm title="确认删除该商品？" @confirm="remove(row)">
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

  <el-dialog v-model="dialog" :title="form.id ? '编辑商品' : '新增商品'" width="680px" top="5vh">
    <el-form :model="form" label-width="90px">
      <el-row :gutter="12">
        <el-col :span="12"><el-form-item label="名称"><el-input v-model="form.name" /></el-form-item></el-col>
        <el-col :span="6"><el-form-item label="品牌"><el-input v-model="form.brand" /></el-form-item></el-col>
        <el-col :span="6"><el-form-item label="分类"><el-input v-model="form.category" /></el-form-item></el-col>
      </el-row>
      <el-row :gutter="12">
        <el-col :span="6"><el-form-item label="售价"><el-input-number v-model="form.price" :min="0" :precision="2" style="width: 100%" /></el-form-item></el-col>
        <el-col :span="6"><el-form-item label="原价"><el-input-number v-model="form.original_price" :min="0" :precision="2" style="width: 100%" /></el-form-item></el-col>
        <el-col :span="6"><el-form-item label="库存"><el-input-number v-model="form.stock" :min="0" style="width: 100%" /></el-form-item></el-col>
        <el-col :span="6"><el-form-item label="月销"><el-input-number v-model="form.sales" :min="0" style="width: 100%" /></el-form-item></el-col>
      </el-row>
      <el-form-item label="卖点标签">
        <el-input v-model="tagsText" placeholder="逗号分隔，如：旗舰,双频GPS,长续航" />
      </el-form-item>
      <el-form-item label="核心卖点">
        <el-input v-model="pointsText" type="textarea" :rows="3" placeholder="每行一条，将用于 RAG 检索与销售话术" />
      </el-form-item>
      <el-form-item label="商品描述"><el-input v-model="form.description" type="textarea" :rows="4" /></el-form-item>
      <el-row :gutter="12">
        <el-col :span="12"><el-form-item label="商品链接"><el-input v-model="form.url" /></el-form-item></el-col>
        <el-col :span="12"><el-form-item label="图片URL"><el-input v-model="form.image_url" /></el-form-item></el-col>
      </el-row>
      <el-form-item label="上架"><el-switch v-model="form.enabled" /></el-form-item>
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
const pointsText = ref("");
const query = reactive({ keyword: "", page: 1, size: 20 });
const emptyForm = {
  id: null, name: "", brand: "Amazfit", category: "智能手表", price: 0, original_price: null,
  stock: 0, sales: 0, rating: 4.8, description: "", url: "", image_url: "", enabled: true,
};
const form = reactive({ ...emptyForm });
// 乐观锁：打开编辑弹窗时缓存 updated_at，保存时作为 if_match_updated_at 提交
const lockUpdatedAt = ref(null);

async function load() {
  loading.value = true;
  try {
    const { data } = await api.get("/admin/products", { params: query });
    rows.value = data.items;
    total.value = data.total;
  } finally {
    loading.value = false;
  }
}

function openEdit(row) {
  Object.assign(form, row ? { ...row } : { ...emptyForm });
  tagsText.value = (row?.tags || []).join(",");
  pointsText.value = (row?.selling_points || []).join("\n");
  // 编辑时记录列表接口拿到的 updated_at（乐观锁 token）
  lockUpdatedAt.value = row?.updated_at || null;
  dialog.value = true;
}

async function save() {
  if (!form.name.trim()) { ElMessage.warning("请填写商品名称"); return; }
  saving.value = true;
  try {
    const payload = {
      ...form,
      tags: tagsText.value.split(/[,，]/).map((s) => s.trim()).filter(Boolean),
      selling_points: pointsText.value.split("\n").map((s) => s.trim()).filter(Boolean),
    };
    delete payload.id;
    if (form.id) {
      // 乐观锁：前端读取时的 updated_at -> if_match_updated_at
      payload.if_match_updated_at = lockUpdatedAt.value || null;
      const { data } = await api.put(`/admin/products/${form.id}`, payload);
      // 保存成功后更新本地 token，便于继续编辑
      if (data?.updated_at) lockUpdatedAt.value = data.updated_at;
    } else {
      await api.post("/admin/products", payload);
    }
    ElMessage.success("已保存并同步");
    dialog.value = false;
    load();
  } finally {
    saving.value = false;
  }
}

async function toggleEnabled(row, v) {
  const payload = { ...row, enabled: v, if_match_updated_at: row.updated_at || null };
  delete payload.id;
  try {
    await api.put(`/admin/products/${row.id}`, payload);
  } catch (e) {
    // 409 时回滚开关显示（409 拦截器已提示）
    row.enabled = !v;
  }
  load();
}

async function syncOne(row) {
  await api.post(`/admin/products/${row.id}/sync`);
  ElMessage.success("已同步");
  load();
}

async function syncAll() {
  syncing.value = true;
  try {
    const { data } = await api.post("/admin/products/sync-all");
    ElMessage.success(`已同步 ${data.synced} 个商品`);
    load();
  } finally {
    syncing.value = false;
  }
}

async function doImport({ file }) {
  const fd = new FormData();
  fd.append("file", file);
  const { data } = await api.post("/admin/products/import", fd);
  ElMessage.success(`导入成功 ${data.created} 个${data.errors?.length ? `，失败 ${data.errors.length} 个` : ""}`);
  load();
}

async function remove(row) {
  await api.delete(`/admin/products/${row.id}`);
  ElMessage.success("已删除");
  load();
}

onMounted(load);
</script>

<style scoped>
.toolbar { display: flex; align-items: center; gap: 10px; margin-bottom: 14px; }
</style>
