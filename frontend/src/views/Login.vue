<template>
  <div class="auth-page">
    <el-card class="auth-card">
      <h2>无线通信 AI 助手</h2>
      <p class="subtitle">登录</p>
      <el-form @submit.prevent="handleLogin">
        <el-form-item>
          <el-input v-model="username" placeholder="用户名" prefix-icon="User" />
        </el-form-item>
        <el-form-item>
          <el-input v-model="password" type="password" placeholder="密码" show-password />
        </el-form-item>
        <el-form-item>
          <el-button type="primary" @click="handleLogin" :loading="loading" style="width:100%">
            登 录
          </el-button>
        </el-form-item>
      </el-form>
      <p class="switch-link">
        还没有账号？<router-link to="/register">立即注册</router-link>
      </p>
    </el-card>
  </div>
</template>

<script setup>
import { ref } from "vue";
import { useRouter } from "vue-router";
import { ElMessage } from "element-plus";
import { useAuthStore } from "../store";

const username = ref("");
const password = ref("");
const loading = ref(false);
const router = useRouter();
const authStore = useAuthStore();

async function handleLogin() {
  if (!username.value || !password.value) {
    ElMessage.warning("请输入用户名和密码");
    return;
  }
  loading.value = true;
  try {
    await authStore.login(username.value, password.value);
    ElMessage.success("登录成功");
    router.push("/");
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || "登录失败");
  } finally {
    loading.value = false;
  }
}
</script>

<style scoped>
.auth-page {
  display: flex;
  justify-content: center;
  align-items: center;
  height: 100vh;
  background: linear-gradient(135deg, #001529 0%, #003a70 100%);
}
.auth-card {
  width: 400px;
}
.auth-card h2 {
  text-align: center;
  margin-bottom: 4px;
}
.subtitle {
  text-align: center;
  color: #888;
  margin-bottom: 24px;
}
.switch-link {
  text-align: center;
  font-size: 14px;
}
</style>
