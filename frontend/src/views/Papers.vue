<template>
  <div class="papers-page">
    <!-- Left: upload + list -->
    <div class="left-panel">
      <el-upload
        :http-request="handleUpload"
        :show-file-list="false"
        accept=".pdf"
        drag
        :disabled="uploading"
      >
        <div class="upload-area">
          <el-icon :size="32"><UploadFilled /></el-icon>
          <p>拖拽 PDF 论文到此处上传</p>
          <p class="hint">最大 50 MB</p>
        </div>
      </el-upload>
      <div v-if="uploading" style="margin-top:8px; text-align:center;">
        <el-progress :percentage="100" :indeterminate="true" />
        <span style="font-size:13px;color:#888;">正在读取论文并生成摘要...</span>
      </div>

      <div class="paper-list">
        <div v-for="p in papers" :key="p.id"
          :class="['paper-item', { active: currentPaperId === p.id }]"
          @click="selectPaper(p)"
        >
          <div class="paper-name">{{ p.filename }}</div>
          <div class="paper-meta">{{ p.page_count }} 页 · {{ (p.char_count/1000).toFixed(1) }}k 字</div>
          <div class="paper-summary-preview">{{ p.summary }}</div>
          <el-button size="small" type="danger" :icon="Delete" circle @click.stop="confirmDelete(p)" style="position:absolute;top:8px;right:8px;" />
        </div>
        <el-empty v-if="papers.length === 0 && !uploading" description="暂无论文，上传 PDF 开始" />
      </div>
    </div>

    <!-- Right: chat -->
    <div class="right-panel">
      <template v-if="currentPaper">
        <div class="paper-header">
          <h3>{{ currentPaper.filename }}</h3>
          <div class="paper-summary-box">
            <div class="summary-label">AI 摘要</div>
            <div class="summary-text">{{ currentPaper.summary }}</div>
          </div>
        </div>

        <div class="chat-messages" ref="msgContainer">
          <div v-for="(msg, i) in messages" :key="i" :class="['msg', msg.role]">
            <div class="msg-content" v-html="msg._html"></div>
          </div>
          <div v-if="chatting" class="msg assistant"><div class="msg-content"><em>思考中...</em></div></div>
        </div>

        <div class="chat-input">
          <el-input v-model="input" placeholder="针对这篇论文提问..." @keyup.enter="sendMsg" :disabled="chatting" size="large">
            <template #append><el-button @click="sendMsg" :loading="chatting" type="primary">发送</el-button></template>
          </el-input>
        </div>
      </template>
      <el-empty v-else description="选择一篇论文开始对话" style="margin-top:120px;" />
    </div>
  </div>
</template>

<script setup>
import { ref, nextTick, onMounted, computed } from "vue";
import { ElMessage, ElMessageBox } from "element-plus";
import { UploadFilled, Delete } from "@element-plus/icons-vue";
import { marked } from "marked";
import katex from "katex";
import "katex/dist/katex.min.css";
import api from "../api";

const papers = ref([]);
const currentPaperId = ref(null);
const currentPaper = ref(null);
const messages = ref([]);
const input = ref("");
const uploading = ref(false);
const chatting = ref(false);
const msgContainer = ref(null);
let _uid = 0;

// ---- Render ----

function escapeHtml(t) { return t.replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;"); }

function renderHtml(raw) {
  if (!raw) return "";
  let html = raw;
  html = html.replace(/```(\w*)\n([\s\S]*?)```/g, (_, lang, code) => {
    const esc = escapeHtml(code.trim());
    return `<div class="cb"><div class="cb-h"><span>${escapeHtml(lang||'text')}</span></div><pre><code>${esc}</code></pre></div>`;
  });
  html = html.replace(/`([^`]+)`/g, (_, c) => `<code>${escapeHtml(c)}</code>`);
  html = html.replace(/\$\$([\s\S]*?)\$\$/g, (_, f) => { try { return katex.renderToString(f.trim(),{displayMode:true,throwOnError:false}); } catch { return f; }});
  html = html.replace(/(?<!\$)\$(?!\$)([^$]+?)\$(?!\$)/g, (_, f) => { try { return katex.renderToString(f.trim(),{displayMode:false,throwOnError:false}); } catch { return f; }});
  return marked.parse(html);
}

function addMsg(role, content) {
  messages.value = [...messages.value, { role, content, _html: renderHtml(content) }];
  nextTick(() => { if (msgContainer.value) msgContainer.value.scrollTop = msgContainer.value.scrollHeight; });
}

// ---- Paper list ----

async function loadPapers() {
  try {
    const res = await api.get("/api/papers");
    papers.value = res.data.papers || [];
  } catch {}
}

async function selectPaper(p) {
  currentPaperId.value = p.id;
  messages.value = [];
  try {
    const res = await api.get(`/api/papers/${p.id}`);
    currentPaper.value = res.data;
    // Load existing conversation history
    const history = res.data.messages || [];
    messages.value = history.map(m => ({ role: m.role, content: m.content, _html: renderHtml(m.content) }));
    if (history.length === 0) {
      addMsg("assistant", "论文已加载。你可以问我这篇论文讲了什么，或者具体章节的细节。");
    }
    nextTick(() => { if (msgContainer.value) msgContainer.value.scrollTop = msgContainer.value.scrollHeight; });
  } catch {}
}

async function handleUpload(options) {
  uploading.value = true;
  try {
    const fd = new FormData();
    fd.append("file", options.file);
    const res = await api.post("/api/papers/upload", fd);
    ElMessage.success("论文上传成功，摘要已生成");
    await loadPapers();
    // Auto-select the newly uploaded paper
    const p = papers.value.find(x => x.id === res.data.paper_id);
    if (p) await selectPaper(p);
  } catch (e) {
    ElMessage.error("上传失败: " + (e.response?.data?.detail || e.message));
  } finally {
    uploading.value = false;
  }
}

async function confirmDelete(p) {
  try {
    await ElMessageBox.confirm(`确定删除 "${p.filename}"？`, "确认", { type: "warning" });
    await api.delete(`/api/papers/${p.id}`);
    if (currentPaperId.value === p.id) { currentPaperId.value = null; currentPaper.value = null; messages.value = []; }
    await loadPapers();
    ElMessage.success("已删除");
  } catch {}
}

// ---- Chat ----

async function sendMsg() {
  const msg = input.value.trim();
  if (!msg || chatting.value || !currentPaperId.value) return;
  addMsg("user", msg);
  input.value = "";
  chatting.value = true;
  try {
    const res = await api.post(`/api/papers/${currentPaperId.value}/chat`, { message: msg });
    addMsg("assistant", res.data.response);
  } catch (e) {
    addMsg("assistant", "请求失败: " + (e.response?.data?.detail || e.message));
  } finally {
    chatting.value = false;
  }
}

onMounted(loadPapers);
</script>

<style scoped>
.papers-page { display: flex; height: calc(100vh - 140px); gap: 12px; }
.left-panel { width: 380px; min-width: 380px; display: flex; flex-direction: column; gap: 8px; }
.upload-area { padding: 20px 0; text-align: center; color: #888; }
.upload-area p { margin: 6px 0; }
.hint { font-size: 12px; color: #aaa; }
.paper-list { flex: 1; overflow-y: auto; }
.paper-item { padding: 12px 40px 12px 12px; border-radius: 8px; cursor: pointer; margin-bottom: 6px; background: #fff; border: 1px solid #eee; position: relative; }
.paper-item:hover { border-color: #1677ff; }
.paper-item.active { border-color: #1677ff; background: #e6f4ff; }
.paper-name { font-weight: 600; font-size: 14px; margin-bottom: 4px; }
.paper-meta { font-size: 12px; color: #999; margin-bottom: 4px; }
.paper-summary-preview { font-size: 12px; color: #666; display: -webkit-box; -webkit-line-clamp: 3; -webkit-box-orient: vertical; overflow: hidden; line-height: 1.5; }

.right-panel { flex: 1; display: flex; flex-direction: column; background: #fff; border-radius: 8px; overflow: hidden; }
.paper-header { padding: 16px 20px; border-bottom: 1px solid #eee; flex-shrink: 0; }
.paper-header h3 { margin: 0 0 10px; font-size: 16px; }
.paper-summary-box { background: #f0f9eb; border: 1px solid #b3e19d; border-radius: 8px; padding: 12px; }
.summary-label { font-size: 11px; color: #67c23a; font-weight: 600; margin-bottom: 4px; }
.summary-text { font-size: 13px; color: #333; line-height: 1.6; }

.chat-messages { flex: 1; overflow-y: auto; padding: 16px 20px; }
.msg { margin-bottom: 12px; }
.msg.user .msg-content { background: #409eff; color: #fff; margin-left: auto; max-width: 70%; border-radius: 12px 12px 4px 12px; text-align: right; }
.msg.assistant .msg-content { background: #f0f0f0; max-width: 85%; border-radius: 12px 12px 12px 4px; }
.msg-content { display: inline-block; padding: 10px 14px; font-size: 14px; line-height: 1.6; }
.msg-content :deep(p) { margin: 4px 0; }
.msg-content :deep(.katex-display) { margin: 8px 0; overflow-x: auto; }

.chat-input { padding: 12px 20px; border-top: 1px solid #eee; flex-shrink: 0; }

/* Code blocks in chat */
.msg-content :deep(.cb) { margin: 8px 0; border:1px solid #d0d7de; border-radius:6px; overflow:hidden; background:#f6f8fa; }
.msg-content :deep(.cb-h) { padding:4px 12px; background:#eaeef2; color:#57606a; font-size:12px; }
.msg-content :deep(.cb pre) { margin:0; padding:12px 16px; overflow-x:auto; }
.msg-content :deep(.cb code) { background:transparent; padding:0; font-family: Consolas, Monaco, monospace; font-size:13px; }
.msg-content :deep(code) { background:rgba(175,184,193,0.15); padding:2px 6px; border-radius:3px; font-family: Consolas, Monaco, monospace; font-size:13px; }
</style>
