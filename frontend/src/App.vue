<template>
  <div id="app-root">
    <el-container>
      <el-aside v-if="isLoggedIn" width="220px">
        <Sidebar />
      </el-aside>
      <el-container>
        <el-header v-if="isLoggedIn">
          <HeaderBar />
        </el-header>
        <el-main>
          <router-view />
        </el-main>
      </el-container>
    </el-container>
  </div>
</template>

<script setup>
import { computed } from "vue";
import { useRouter } from "vue-router";
import Sidebar from "./components/Sidebar.vue";
import HeaderBar from "./components/HeaderBar.vue";
import { useAuthStore } from "./store";

const authStore = useAuthStore();
const isLoggedIn = computed(() => authStore.isLoggedIn);
</script>

<style>
* {
  margin: 0;
  padding: 0;
  box-sizing: border-box;
}
body {
  font-family: "Segoe UI", "Helvetica Neue", Arial, sans-serif;
  background: #f0f2f5;
}
#app-root {
  height: 100vh;
}
.el-aside {
  background: #001529;
  min-height: 100vh;
}
.el-header {
  background: #fff;
  border-bottom: 1px solid #e8e8e8;
  padding: 0 24px;
  display: flex;
  align-items: center;
  justify-content: flex-end;
}
.el-main {
  padding: 24px;
  background: #f0f2f5;
  min-height: calc(100vh - 60px);
}
</style>
