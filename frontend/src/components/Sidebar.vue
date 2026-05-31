<template>
  <div class="sidebar">
    <div class="logo">
      <h2>无线通信 AI</h2>
    </div>
    <el-menu
      :default-active="activeMenu"
      background-color="#001529"
      text-color="#ffffffa6"
      active-text-color="#fff"
      router
    >
      <el-menu-item index="/">
        <el-icon><HomeFilled /></el-icon>
        <span>首页</span>
      </el-menu-item>
      <el-menu-item index="/chat">
        <el-icon><ChatDotRound /></el-icon>
        <span>智能对话</span>
      </el-menu-item>
      <el-menu-item index="/knowledge">
        <el-icon><Document /></el-icon>
        <span>知识库</span>
      </el-menu-item>
      <el-menu-item index="/code">
        <el-icon><Monitor /></el-icon>
        <span>代码编辑器</span>
      </el-menu-item>
      <el-menu-item index="/papers">
        <el-icon><Reading /></el-icon>
        <span>论文阅读</span>
      </el-menu-item>
    </el-menu>
  </div>
</template>

<script setup>
import { computed } from "vue";
import { useRoute } from "vue-router";

const route = useRoute();
const activeMenu = computed(() => route.path);
</script>

<style scoped>
.logo {
  padding: 20px 16px;
  text-align: center;
}
.logo h2 {
  color: #fff;
  font-size: 16px;
  font-weight: 600;
}
.sidebar {
  height: 100%;
}
</style>
