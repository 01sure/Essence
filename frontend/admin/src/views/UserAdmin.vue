<template>
  <el-card shadow="never">
    <div class="toolbar">
      <el-input v-model="query.keyword" placeholder="搜用户名 / 昵称" clearable style="width: 260px" @keyup.enter="load" />
      <el-button type="primary" @click="load">查询</el-button>
      <el-button type="success" plain style="margin-left: auto" @click="showCreate">+ 新增账号</el-button>
    </div>

    <el-table :data="rows" v-loading="loading" size="default">
      <el-table-column prop="id" label="ID" width="70" />
      <el-table-column prop="username" label="账号" width="140" />
      <el-table-column prop="display_name" label="昵称" width="140" />
      <el-table-column label="角色" width="130">
        <template #default="{ row }">
          <el-tag :type="ROLE_COLOR[row.role]" size="small">{{ row.role_label || row.role }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="坐席状态" width="120">
        <template #default="{ row }">
          <el-tag v-if="['agent', 'team_leader'].includes(row.role)" :type="row.presence==='online'?'success':(row.presence==='busy'?'warning':'info')" size="small">
            {{ PRESENCE[row.presence] || row.presence }}
          </el-tag>
          <span v-else style="color: #c0c4cc">—</span>
        </template>
      </el-table-column>
      <el-table-column prop="capacity" label="容量" width="80" />
      <el-table-column label="账号状态" width="100">
        <template #default="{ row }">
          <el-switch v-model="row.active" @change="(v) => toggleActive(row, v)" />
        </template>
      </el-table-column>
      <el-table-column prop="last_login_at" label="最近登录" width="170">
        <template #default="{ row }">{{ row.last_login_at ? String(row.last_login_at).replace("T"," ").slice(0,19) : "-" }}</template>
      </el-table-column>
      <el-table-column prop="created_at" label="创建时间" width="170">
        <template #default="{ row }">{{ row.created_at ? String(row.created_at).replace("T"," ").slice(0,19) : "-" }}</template>
      </el-table-column>
      <el-table-column label="操作" width="180" fixed="right">
        <template #default="{ row }">
          <el-button link type="primary" @click="showEdit(row)">编辑</el-button>
          <el-button link type="warning" @click="showResetPwd(row)">重置密码</el-button>
        </template>
      </el-table-column>
    </el-table>

    <el-pagination
      style="margin-top: 14px; justify-content: flex-end"
      layout="total, prev, pager, next"
      :total="total" :page-size="20" v-model:current-page="query.page" @current-change="load"
    />
  </el-card>

  <!-- 新建/编辑 -->
  <el-dialog v-model="formVisible" :title="editing ? '编辑账号' : '新增账号'" width="440px">
    <el-form label-width="90px" :model="form">
      <el-form-item label="账号">
        <el-input v-model="form.username" :disabled="!!editing" placeholder="3-50 位" />
      </el-form-item>
      <el-form-item label="昵称">
        <el-input v-model="form.display_name" placeholder="例如 运营小王" />
      </el-form-item>
      <el-form-item label="角色">
        <el-select v-model="form.role" style="width: 100%">
          <el-option v-for="r in roles" :key="r.key" :label="r.display" :value="r.key" />
        </el-select>
      </el-form-item>
      <el-form-item v-if="['agent', 'team_leader'].includes(form.role)" label="接待容量">
        <el-input-number v-model="form.capacity" :min="1" :max="30" />
      </el-form-item>
      <el-form-item v-if="!editing" label="初始密码">
        <el-input v-model="form.password" type="password" placeholder="至少 6 位" show-password />
      </el-form-item>
      <el-form-item v-if="editing" label="是否启用">
        <el-switch v-model="form.active" />
      </el-form-item>
    </el-form>
    <template #footer>
      <el-button @click="formVisible = false">取消</el-button>
      <el-button type="primary" @click="submitForm">提交</el-button>
    </template>
  </el-dialog>

  <!-- 重置密码 -->
  <el-dialog v-model="pwdVisible" title="重置密码" width="400px">
    <el-input v-model="newPwd" type="password" show-password placeholder="至少 6 位新密码" />
    <template #footer>
      <el-button @click="pwdVisible = false">取消</el-button>
      <el-button type="primary" @click="submitPwd">确认重置</el-button>
    </template>
  </el-dialog>
</template>

<script setup>
import { onMounted, reactive, ref } from "vue";
import { ElMessage } from "element-plus";
import api from "../api";

const ROLE_COLOR = {
  super_admin: "danger",
  admin: "warning",
  team_leader: "success",
  agent: "primary",
  analyst: "info",
};
const PRESENCE = { online: "在线", busy: "忙碌", offline: "离线" };

const rows = ref([]);
const total = ref(0);
const loading = ref(false);
const query = reactive({ page: 1, keyword: "" });
const roles = ref([]);

const formVisible = ref(false);
const editing = ref(null);
const form = reactive({ username: "", password: "", display_name: "", role: "agent", capacity: 8, active: true });

const pwdVisible = ref(false);
const pwdTarget = ref(null);
const newPwd = ref("");

async function loadRoles() {
  try {
    const { data } = await api.get("/admin/auth/roles");
    roles.value = data;
  } catch (_) { roles.value = []; }
}

async function load() {
  loading.value = true;
  try {
    const { data } = await api.get("/admin/auth/users", { params: query });
    rows.value = data.items;
    total.value = data.total;
  } finally {
    loading.value = false;
  }
}

function showCreate() {
  editing.value = null;
  Object.assign(form, { username: "", password: "", display_name: "", role: "agent", capacity: 8, active: true });
  formVisible.value = true;
}

function showEdit(row) {
  editing.value = row;
  Object.assign(form, {
    username: row.username, password: "",
    display_name: row.display_name, role: row.role,
    capacity: row.capacity, active: row.active,
  });
  formVisible.value = true;
}

async function submitForm() {
  try {
    if (!editing.value) {
      await api.post("/admin/auth/users", { ...form });
      ElMessage.success("已创建");
    } else {
      await api.put(`/admin/auth/users/${editing.value.id}`, {
        display_name: form.display_name, role: form.role,
        capacity: form.capacity, active: form.active,
      });
      ElMessage.success("已更新");
    }
    formVisible.value = false;
    load();
  } catch (_) { /* noop */ }
}

async function toggleActive(row, v) {
  try {
    await api.put(`/admin/auth/users/${row.id}`, { active: v });
    ElMessage.success(v ? "已启用" : "已停用");
  } catch (e) {
    row.active = !v; // 回滚 UI
  }
}

function showResetPwd(row) {
  pwdTarget.value = row;
  newPwd.value = "";
  pwdVisible.value = true;
}

async function submitPwd() {
  if (!pwdTarget.value) return;
  if (!newPwd.value || newPwd.value.length < 6) {
    ElMessage.warning("密码至少 6 位");
    return;
  }
  try {
    await api.put(`/admin/auth/users/${pwdTarget.value.id}`, { password: newPwd.value });
    ElMessage.success("密码已重置");
    pwdVisible.value = false;
  } catch (_) { /* noop */ }
}

onMounted(async () => { await loadRoles(); await load(); });
</script>

<style scoped>
.toolbar { display: flex; align-items: center; gap: 10px; margin-bottom: 14px; }
</style>
