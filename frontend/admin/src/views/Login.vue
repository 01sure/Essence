<template>
  <div class="login-bg">
    <el-card class="login-card">
      <div class="brand">华米商城 · AI 智能客服</div>
      <div class="sub">运营管理后台</div>
      <el-form @submit.prevent="submit">
        <el-form-item>
          <el-input v-model="form.username" placeholder="用户名" size="large" />
        </el-form-item>
        <el-form-item>
          <el-input v-model="form.password" type="password" placeholder="密码" size="large" show-password @keyup.enter="submit" />
        </el-form-item>
        <el-button type="warning" size="large" style="width: 100%" :loading="loading" @click="submit">登 录</el-button>
      </el-form>
    </el-card>
  </div>
</template>

<script setup>
import { reactive, ref } from "vue";
import { useRouter } from "vue-router";
import { ElMessage } from "element-plus";
import { useAuthStore } from "../stores/auth";

const form = reactive({ username: "", password: "" });
const loading = ref(false);
const auth = useAuthStore();
const router = useRouter();

async function submit() {
  if (!form.username || !form.password) {
    ElMessage.warning("请输入用户名和密码");
    return;
  }
  loading.value = true;
  try {
    await auth.login(form.username, form.password);
    router.push("/");
  } finally {
    loading.value = false;
  }
}
</script>

<style scoped>
.login-bg {
  height: 100vh; display: flex; align-items: center; justify-content: center;
  background: linear-gradient(135deg, #1f2430 0%, #3a2f4a 100%);
}
.login-card { width: 380px; padding: 10px 12px; border-radius: 14px; }
.brand { font-size: 20px; font-weight: 700; text-align: center; color: #ff6b00; }
.sub { text-align: center; color: #999; font-size: 13px; margin: 6px 0 22px; }
</style>
