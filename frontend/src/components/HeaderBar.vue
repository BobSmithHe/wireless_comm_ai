<template>
  <div class="header-bar">
    <span class="greeting">{{ greeting }}</span>
    <el-dropdown>
      <span class="user-info">
        <el-icon><UserFilled /></el-icon>
        {{ authStore.user?.username || "用户" }}
      </span>
      <template #dropdown>
        <el-dropdown-item @click="handleLogout">退出登录</el-dropdown-item>
      </template>
    </el-dropdown>
  </div>
</template>

<script setup>
import { computed } from "vue";
import { useRouter } from "vue-router";
import { useAuthStore } from "../store";

const authStore = useAuthStore();
const router = useRouter();

const greeting = computed(() => {
  const hour = new Date().getHours();
  if (hour < 12) return "上午好";
  if (hour < 18) return "下午好";
  return "晚上好";
});

function handleLogout() {
  authStore.logout();
  router.push("/login");
}
</script>

<style scoped>
.header-bar {
  width: 100%;
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.greeting {
  font-size: 14px;
  color: #666;
}
.user-info {
  cursor: pointer;
  display: flex;
  align-items: center;
  gap: 6px;
}
</style>
