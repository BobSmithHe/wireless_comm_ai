<template>
  <div class="chat-page">
    <div class="conv-sidebar">
      <el-button type="primary" @click="newConversation" style="width:100%;margin-bottom:8px">+ 新对话</el-button>
      <div class="conv-list">
        <div v-for="c in conversations" :key="c.id" :class="['conv-item', { active: c.id === currentConvId }]" @click="switchConversation(c.id)">
          <span class="conv-title">{{ c.title }}</span>
          <span class="conv-delete" @click.stop="deleteConversation(c.id)">×</span>
        </div>
      </div>
    </div>

    <el-card class="chat-container">
      <div class="chat-messages" ref="messagesContainer" @click="handleCodeClick">
        <div v-if="hasMore" class="load-more" @click="loadMoreMessages">加载更早的消息</div>

        <template v-for="msg in messages" :key="msg._key">
          <div v-if="msg.role !== 'tool' && msg.role !== 'tool_result'" :class="['message', msg.role]">
            <div class="message-content" v-html="msg._html"></div>
          </div>
        </template>

      </div>
      <div class="chat-input">
        <div class="input-row">
          <el-switch v-model="ragEnabled" active-text="知识库" size="small" style="margin-right:8px" />
            <el-switch v-model="webEnabled" active-text="联网" size="small" style="margin-right:8px" />
          <el-input v-model="input" placeholder="请输入无线通信相关问题..." @keyup.enter="sendMessage" :disabled="loading">
            <template #append>
              <el-button @click="sendMessage" :loading="loading" type="primary">发送</el-button>
            </template>
          </el-input>
        </div>
      </div>
    </el-card>

    <Teleport to="body">
      <div v-if="previewSrc" class="image-lightbox" @click="previewSrc = null"><img :src="previewSrc" /></div>
    </Teleport>
  </div>
</template>

<script setup>
import { ref, computed, nextTick, onMounted } from "vue";
import { ElMessage, ElMessageBox } from "element-plus";
import { marked } from "marked";
import katex from "katex";
import "katex/dist/katex.min.css";
import api from "../api";
import { useRouter, useRoute } from "vue-router";

const input = ref("");
const ragEnabled = ref(true);
const webEnabled = ref(false);
const messages = ref([]);
const loadingConvId = ref(null);
const loading = computed(() => loadingConvId.value !== null);
const messagesContainer = ref(null);
const router = useRouter();
const route = useRoute();
const previewSrc = ref(null);
const conversations = ref([]);
const currentConvId = ref(null);
const hasMore = ref(false);
const oldestMsgId = ref(null);
let msgUid = 0;

onMounted(async () => {
  await loadConversations();
  const q = route.query.q;
  if (q) {
    if (!conversations.value.length) await newConversation();
    input.value = q;
  } else if (conversations.value.length) {
    await switchConversation(conversations.value[0].id);
  } else {
    await newConversation();
  }
});

// ---- Conversations ----
async function loadConversations() {
  try { conversations.value = (await api.get("/api/conversations")).data; } catch {}
}
async function newConversation() {
  try {
    const res = await api.post("/api/conversations");
    conversations.value.unshift(res.data);
    currentConvId.value = res.data.id;
    messages.value = [];
  } catch { ElMessage.error("创建对话失败"); }
}
async function switchConversation(id) {
  currentConvId.value = id; hasMore.value = false; oldestMsgId.value = null;
  try {
    const res = await api.get(`/api/conversations/${id}`, { params: { limit: 50 } });
    messages.value = res.data.messages
      .filter(m => m.role !== "system")
      .map((m) => ({
        _key: ++msgUid, role: m.role, content: m.content,
        _html: renderHtml(m.content, msgUid), execResults: [],
      }));
    hasMore.value = res.data.has_more;
    if (res.data.messages.length > 0) oldestMsgId.value = res.data.messages[0].id;
    await nextTick(); scrollToBottom();
  } catch {}
}
async function loadMoreMessages() {
  if (!hasMore.value || !oldestMsgId.value) return;
  try {
    const res = await api.get(`/api/conversations/${currentConvId.value}`, { params: { before: oldestMsgId.value, limit: 50 } });
    const older = res.data.messages
      .filter(m => m.role !== "system")
      .map((m) => ({
        _key: ++msgUid, role: m.role, content: m.content,
        _html: renderHtml(m.content, msgUid), execResults: [],
      }));
    messages.value = [...older, ...messages.value];
    hasMore.value = res.data.has_more;
    if (res.data.messages.length > 0) oldestMsgId.value = res.data.messages[0].id;
  } catch {}
}
async function deleteConversation(id) {
  try {
    await ElMessageBox.confirm("确定删除该对话？", "提示", { confirmButtonText: "确定", cancelButtonText: "取消", type: "warning" });
    await api.delete(`/api/conversations/${id}`);
    conversations.value = conversations.value.filter((c) => c.id !== id);
    if (currentConvId.value === id) {
      conversations.value.length ? await switchConversation(conversations.value[0].id) : await newConversation();
    }
  } catch {}
}

// ---- Rendering ----
function escapeHtml(t) { return t.replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;"); }
function renderMarkdown(text, withKatex) {
  text = text.replace(/\t/g, '    ');
  if (withKatex) {
    // First: handle display math $$ and \[ \] and [ ]
    text = text.replace(/\$\$([\s\S]*?)\$\$/g, (_,f) => { try { return katex.renderToString(f.trim(),{displayMode:true,throwOnError:false}); } catch { return '<pre>'+escapeHtml(f)+'</pre>'; }});
    text = text.replace(/\\\[([\s\S]*?)\\\]/g, (_,f) => { try { return katex.renderToString(f.trim(),{displayMode:true,throwOnError:false}); } catch { return '<pre>'+escapeHtml(f)+'</pre>'; }});
    text = text.replace(/\\\(([\s\S]*?)\\\)/g, (_,f) => { try { return katex.renderToString(f.trim(),{displayMode:false,throwOnError:false}); } catch { return escapeHtml(f); }});
    // Inline $...$: only replace if dollar count is even AND content looks like math
    text = text.replace(/(?<!\$)\$(?!\$)([^$]+?)\$(?!\$)/g, (_,f) => {
      if (/[\\^_{}]/.test(f)) {
        try { return katex.renderToString(f.trim(),{displayMode:false,throwOnError:false}); } catch { return escapeHtml(f); }
      }
      return '$'+f+'$';
    });
  }
  var html = marked.parse(text, { breaks: true, gfm: true });
  var re = new RegExp('<pre><code( class="language-(\\w+)")?>([\\s\\S]*?)</code></pre>', 'g');
  html = html.replace(re, function(_, cls, lang, code) {
    var ln = lang || "text";
    var ta = document.createElement("textarea");
    ta.innerHTML = code;
    var decoded = ta.value;
    var isPython = ln === "python" || ln === "py";
    var escCode = encodeURIComponent(decoded.trim());
    var runBtn = isPython ? '<button class="run-code-btn" data-code="'+escCode+'">▶ 运行</button>' : '';
    return '<div class="code-block-wrapper"><div class="code-block-header"><span>'+escapeHtml(ln)+'</span><div class="code-block-actions"><button class="copy-code-btn" data-code="'+escCode+'">复制</button>'+runBtn+'</div></div><pre><code class="language-'+escapeHtml(ln)+'">'+code+'</code></pre></div>';
  });
  return html;
}

function renderHtml(raw, msgIdx) {
  if (!raw) return '';
  return renderMarkdown(raw, true);
}
function addLocalMessage(role, content) {
  const m = { _key: ++msgUid, role, content, _html: renderHtml(content || "", msgUid), execResults: [] };
  messages.value = [...messages.value, m];
  return m;
}

// ---- Chat ----
async function sendMessage() {
  const text = input.value.trim();
  if (!text) return;
  addLocalMessage("user", text);
  input.value = "";
  // Clear homepage tag from URL
  if (route.query.q) router.replace({ query: {} });
  const thisConvId = currentConvId.value;
  loadingConvId.value = thisConvId;

  // Add a status message that will be updated during streaming
  // Remove old status messages from previous responses
  messages.value = messages.value.filter(m => m.role !== "system");
  const statusMsg = addLocalMessage("system", "尝试连接...");

  try {
    const token = localStorage.getItem("access_token");
    const resp = await fetch("/api/chat/stream", {
      method: "POST",
      headers: { "Content-Type": "application/json", "Authorization": `Bearer ${token}` },
      body: JSON.stringify({ message: text, conversation_id: thisConvId, use_rag: ragEnabled.value, use_web: webEnabled.value }),
    });

    if (!resp.ok) throw new Error(`请求失败: ${resp.status}`);
    if (!resp.body) throw new Error("响应体为空");

    const reader = resp.body.getReader();
    const decoder = new TextDecoder();
    let sseBuffer = "";
    let fullAnswer = "";
    let assistantMsg = null;

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      sseBuffer += decoder.decode(value, { stream: true });
      const events = sseBuffer.split("\n\n");
      sseBuffer = events.pop() || "";

      let touched = false;
      for (const evt of events) {
        const dataLine = evt.split("\n").find(l => l.startsWith("data: "));
        if (!dataLine) continue;
        try {
          const data = JSON.parse(dataLine.slice(6));
          console.log('[SSE]', data.event, data.content?.substring(0, 60));
          if (data.event === "status" || data.event === "result") {
            statusMsg.content = (statusMsg.content || "") + "\n\n" + data.content;
            statusMsg._html = renderHtml(statusMsg.content, statusMsg._key);
            messages.value = [...messages.value];
            touched = true;
          } else if (data.event === "answer") {
            fullAnswer += data.content;
            if (!assistantMsg) assistantMsg = addLocalMessage("assistant", "");
            assistantMsg._html = renderHtml(fullAnswer, assistantMsg._key);
            assistantMsg.content = fullAnswer;
            messages.value = [...messages.value];
            touched = true;
          } else if (data.event === "done") {
            if (assistantMsg) {
              assistantMsg._html = renderHtml(fullAnswer, assistantMsg._key);
              assistantMsg.content = fullAnswer;
            }
            if (statusMsg.content) statusMsg._html = renderHtml(statusMsg.content, statusMsg._key);
            messages.value = [...messages.value];
          }
        } catch {}
      }
      if (touched) { await nextTick(); scrollToBottom(); }
    }
    await loadConversations();
  } catch (e) {
    if (currentConvId.value === thisConvId) {
      statusMsg.content = "请求失败";
      statusMsg._html = renderHtml("请求失败: " + (e.message || "未知错误"), statusMsg._key);
      messages.value = [...messages.value];
    }
  } finally {
    if (loadingConvId.value === thisConvId) loadingConvId.value = null;
    await nextTick(); scrollToBottom();
  }
}

function handleCodeClick(event) {
  const copyBtn = event.target.closest(".copy-code-btn");
  if (copyBtn) {
    const code = decodeURIComponent(copyBtn.dataset.code || "");
    try { navigator.clipboard.writeText(code); } catch {
      const ta = document.createElement("textarea"); ta.value = code;
      document.body.appendChild(ta); ta.select(); document.execCommand("copy"); document.body.removeChild(ta);
    }
    ElMessage.success("已复制");
    return;
  }
  const runBtn = event.target.closest(".run-code-btn");
  if (runBtn && runBtn.dataset.code) {
    router.push(`/code?code=${runBtn.dataset.code}`);
    return;
  }
}
function previewImage(b64) { previewSrc.value = "data:image/png;base64," + b64; }
function scrollToBottom() { if (messagesContainer.value) messagesContainer.value.scrollTop = messagesContainer.value.scrollHeight; }
</script>

<style scoped>
.chat-page { display: flex; height: calc(100vh - 140px); gap: 12px; }
.conv-sidebar { width: 200px; min-width: 200px; background: #fff; border-radius: 8px; padding: 12px; display: flex; flex-direction: column; overflow: hidden; }
.conv-list { flex: 1; overflow-y: auto; }
.conv-item { padding: 8px 10px; border-radius: 6px; cursor: pointer; margin-bottom: 4px; display: flex; justify-content: space-between; align-items: center; font-size: 13px; }
.conv-item:hover { background: #f0f2f5; }
.conv-item.active { background: #e6f4ff; color: #1677ff; }
.conv-title { flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.conv-delete { color: #ccc; font-size: 16px; font-weight: bold; cursor: pointer; padding: 0 4px; }
.conv-delete:hover { color: #f56c6c; }

.chat-container { flex: 1; display: flex; flex-direction: column; }
.chat-container :deep(.el-card__body) { flex: 1; display: flex; flex-direction: column; overflow: hidden; }
.chat-messages { flex: 1; overflow-y: auto; padding: 16px; }
.load-more { text-align: center; padding: 8px; color: #1677ff; cursor: pointer; font-size: 13px; margin-bottom: 12px; }
.load-more:hover { color: #409eff; text-decoration: underline; }
.load-more:hover { color: #409eff; text-decoration: underline; }

.message { margin-bottom: 16px; display: flex; flex-direction: column; }
.message.user { align-items: flex-end; }
.message.user .message-content { background: #409eff; color: #fff; max-width: 70%; border-radius: 12px 12px 4px 12px; }
.message.assistant .message-content { background: #f0f0f0; max-width: 85%; border-radius: 12px 12px 12px 4px; }
.message.system .message-content { background: #f0f9eb; border: 1px solid #b3e19d; max-width: 85%; border-radius: 12px 12px 12px 4px; font-size: 13px; }
.message-content { display: inline-block; padding: 10px 14px; font-size: 14px; line-height: 1.6; }
.message-content :deep(p) { margin: 4px 0; }
.message-content :deep(ul), .message-content :deep(ol) { padding-left: 18px; }
.message-content :deep(li) { list-style-position: outside; }
.message-content :deep(.katex-display) { margin: 8px 0; overflow-x: auto; }
.chat-input { padding: 12px 16px; border-top: 1px solid #eee; background: #fff; position: sticky; bottom: 0; z-index: 10; }
.input-row { display: flex; align-items: center; }
.input-row :deep(.el-switch__label) { white-space: nowrap; }

/* Code blocks in chat */
.message-content :deep(.code-block-wrapper) { margin: 8px 0; border: 1px solid #d0d7de; border-radius: 6px; overflow: hidden; background: #f6f8fa; }
.message-content :deep(.code-block-header) { display: flex; justify-content: space-between; align-items: center; padding: 6px 12px; background: #eaeef2; color: #57606a; font-size: 12px; }
.message-content :deep(.code-block-actions) { display: flex; gap: 6px; }
.message-content :deep(.copy-code-btn) { background: #eaeef2; color: #57606a; border: 1px solid #d0d7de; border-radius: 4px; padding: 2px 10px; font-size: 12px; cursor: pointer; }
.message-content :deep(.copy-code-btn:hover) { background: #d0d7de; color: #24292f; }
.message-content :deep(.run-code-btn) { background: #1a7f37; color: #fff; border: 1px solid #1a7f37; border-radius: 4px; padding: 2px 10px; font-size: 12px; cursor: pointer; }
.message-content :deep(.run-code-btn:hover) { background: #116329; }
.message-content :deep(.code-block-wrapper pre) { margin: 0; padding: 12px 16px; background: #f6f8fa; overflow-x: auto; }
.message-content :deep(.code-block-wrapper code) { background: transparent; padding: 0; color: #24292f; font-family: Consolas, Monaco, "Courier New", monospace; font-size: 13px; line-height: 1.5; }
.message-content :deep(code) { background: rgba(175,184,193,0.15); padding: 2px 6px; border-radius: 3px; font-family: Consolas, Monaco, monospace; font-size: 13px; }

/* Exec results */
.exec-results { margin-top: 4px; }
.exec-result-item { background: #161b22; border: 1px solid #30363d; border-radius: 6px; margin-top: 4px; overflow: hidden; max-width: 85%; }
.exec-result-header { padding: 6px 12px; background: #0d1117; font-size: 12px; border-bottom: 1px solid #21262d; }
.exec-images { display: flex; flex-wrap: wrap; gap: 8px; padding: 8px 12px; }
.exec-image { max-width: 320px; max-height: 240px; border-radius: 4px; border: 1px solid #30363d; cursor: pointer; }
.exec-image:hover { transform: scale(1.02); }
.exec-stdout { margin: 0; padding: 8px 12px; background: #0d1117; color: #c9d1d9; font-family: Consolas, Monaco, monospace; font-size: 12px; white-space: pre-wrap; max-height: 200px; overflow-y: auto; }
.exec-stderr { margin: 0; padding: 8px 12px; background: #2d0000; color: #ff6b6b; font-family: Consolas, Monaco, monospace; font-size: 12px; white-space: pre-wrap; max-height: 200px; overflow-y: auto; }
.image-lightbox { position: fixed; top: 0; left: 0; right: 0; bottom: 0; background: rgba(0,0,0,0.8); z-index: 9999; display: flex; align-items: center; justify-content: center; cursor: pointer; }
.image-lightbox img { max-width: 90vw; max-height: 90vh; border-radius: 8px; }
</style>
