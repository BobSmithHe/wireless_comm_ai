<template>
  <div class="auth-page">
    <el-card class="auth-card">
      <h2>注册账号</h2>
      <el-form @submit.prevent="handleRegister">
        <el-form-item>
          <el-input v-model="username" placeholder="用户名" />
        </el-form-item>
        <el-form-item>
          <el-input v-model="email" placeholder="邮箱" />
        </el-form-item>
        <el-form-item>
          <el-input v-model="password" type="password" placeholder="密码" show-password />
        </el-form-item>
        <el-form-item>
          <el-input v-model="confirmPassword" type="password" placeholder="确认密码" show-password />
        </el-form-item>
        <el-form-item>
          <el-button type="primary" @click="handleRegister" :loading="loading" style="width:100%">
            注 册
          </el-button>
        </el-form-item>
      </el-form>
      <p class="switch-link">
        已有账号？<router-link to="/login">去登录</router-link>
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
const email = ref("");
const password = ref("");
const confirmPassword = ref("");
const loading = ref(false);
const router = useRouter();
const authStore = useAuthStore();

async function handleRegister() {
  if (!username.value || !email.value || !password.value) {
    ElMessage.warning("请填写所有字段");
    return;
  }
  if (password.value !== confirmPassword.value) {
    ElMessage.warning("两次密码不一致");
    return;
  }
  loading.value = true;
  try {
    await authStore.register(username.value, email.value, password.value);
    ElMessage.success("注册成功，请登录");
    router.push("/login");
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || "注册失败");
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
  margin-bottom: 24px;
}
.switch-link {
  text-align: center;
  font-size: 14px;
}
</style>
