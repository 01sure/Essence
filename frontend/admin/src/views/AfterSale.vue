<template>
  <div>
    <div class="toolbar">
      <el-select v-model="status" clearable placeholder="全部状态" @change="load">
        <el-option label="待处理" value="open" />
        <el-option label="处理中" value="processing" />
        <el-option label="已解决" value="resolved" />
        <el-option label="已关闭" value="closed" />
      </el-select>
      <el-button type="primary" @click="load">刷新工单</el-button>
    </div>
    <el-table :data="items" v-loading="loading" stripe>
      <el-table-column prop="id" label="#" width="70" />
      <el-table-column prop="category" label="问题类型" width="120" />
      <el-table-column prop="order_no" label="订单号" width="180" />
      <el-table-column prop="description" label="用户诉求" min-width="260" show-overflow-tooltip />
      <el-table-column prop="priority" label="优先级" width="90">
        <template #default="{ row }">
          <el-tag :type="row.priority === 'urgent' ? 'danger' : 'info'">{{ row.priority === "urgent" ? "紧急" : "普通" }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="status" label="状态" width="110">
        <template #default="{ row }"><el-tag>{{ statusLabel(row.status) }}</el-tag></template>
      </el-table-column>
      <el-table-column prop="assigned_admin_name" label="负责人" width="120" />
      <el-table-column label="操作" width="250" fixed="right">
        <template #default="{ row }">
          <el-select v-model="row.status" size="small" style="width: 110px" @change="update(row)">
            <el-option label="待处理" value="open" />
            <el-option label="处理中" value="processing" />
            <el-option label="已解决" value="resolved" />
            <el-option label="已关闭" value="closed" />
          </el-select>
          <el-button link type="primary" @click="editResolution(row)">记录结果</el-button>
        </template>
      </el-table-column>
    </el-table>
    <el-dialog v-model="dialogVisible" title="记录售后处理结果" width="520px">
      <el-input v-model="resolution" type="textarea" :rows="5" maxlength="2000" show-word-limit placeholder="填写实际处理结果" />
      <template #footer><el-button @click="dialogVisible = false">取消</el-button><el-button type="primary" @click="saveResolution">保存</el-button></template>
    </el-dialog>
  </div>
</template>

<script setup>
import { onMounted, ref } from "vue";
import { ElMessage } from "element-plus";
import api from "../api";

const items = ref([]);
const status = ref("");
const loading = ref(false);
const dialogVisible = ref(false);
const resolution = ref("");
const editing = ref(null);

const labels = { open: "待处理", processing: "处理中", resolved: "已解决", closed: "已关闭" };
const statusLabel = (value) => labels[value] || value;

async function load() {
  loading.value = true;
  try {
    const { data } = await api.get("/admin/after-sale-tickets", { params: { status: status.value } });
    items.value = data.items || [];
  } finally {
    loading.value = false;
  }
}

async function update(row) {
  await api.patch(`/admin/after-sale-tickets/${row.id}`, { status: row.status, resolution: row.resolution || "" });
  ElMessage.success("工单状态已更新");
  await load();
}

function editResolution(row) {
  editing.value = row;
  resolution.value = row.resolution || "";
  dialogVisible.value = true;
}

async function saveResolution() {
  await api.patch(`/admin/after-sale-tickets/${editing.value.id}`, { status: editing.value.status, resolution: resolution.value });
  dialogVisible.value = false;
  ElMessage.success("处理结果已保存");
  await load();
}

onMounted(load);
</script>

<style scoped>
.toolbar { display: flex; gap: 12px; margin-bottom: 16px; }
</style>