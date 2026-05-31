<template>
  <div class="knowledge-page">
    <h2>知识库</h2>
    <p style="color:#666;margin-bottom:16px">检索无线通信专业知识库，支持上传 Markdown / TXT / Python 文件</p>

    <el-row :gutter="16" style="margin-bottom: 16px">
      <el-col :span="18">
        <el-input v-model="searchQuery" placeholder="搜索无线通信知识..." @keyup.enter="search">
          <template #prefix><el-icon><Search /></el-icon></template>
        </el-input>
      </el-col>
      <el-col :span="6">
        <el-button type="primary" @click="search" :loading="searching" style="margin-right:8px">搜索</el-button>
        <el-upload :show-file-list="false" :http-request="handleUpload" accept=".md,.txt,.py">
          <el-button>上传文件</el-button>
        </el-upload>
      </el-col>
    </el-row>

    <div v-if="results.length">
      <el-card v-for="(r, idx) in results" :key="idx" class="result-card">
        <div class="result-header">
          <el-tag size="small">{{ r.source || "unknown" }}</el-tag>
          <span class="score">相关度: {{ (r.score * 100).toFixed(1) }}%</span>
        </div>
        <div class="result-content" v-html="renderMarkdown(r.content.slice(0, 500))"></div>
      </el-card>
    </div>
    <el-empty v-else description="请输入关键词搜索知识库" />
  </div>
</template>

<script setup>
import { ref } from "vue";
import { ElMessage } from "element-plus";
import { marked } from "marked";
import api from "../api";

const searchQuery = ref("");
const results = ref([]);
const searching = ref(false);

function renderMarkdown(text) {
  return marked(text);
}

async function search() {
  if (!searchQuery.value.trim()) return;
  searching.value = true;
  try {
    const res = await api.get("/api/knowledge/search", {
      params: { query: searchQuery.value, top_k: 5 },
    });
    results.value = res.data.results;
  } catch {
    ElMessage.error("搜索失败");
  } finally {
    searching.value = false;
  }
}

async function handleUpload({ file }) {
  const formData = new FormData();
  formData.append("file", file);
  try {
    const res = await api.post("/api/knowledge/upload", formData);
    ElMessage.success(`上传成功: ${res.data.chunks} 个文本块已索引`);
  } catch {
    ElMessage.error("上传失败");
  }
}
</script>

<style scoped>
.result-card {
  margin-bottom: 12px;
}
.result-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
}
.score {
  font-size: 12px;
  color: #999;
}
.result-content {
  font-size: 14px;
  line-height: 1.6;
}
</style>
