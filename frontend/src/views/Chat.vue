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
          <!-- Tool messages: collapsible thinking process -->
          <div v-if="msg.role === 'tool' || msg.role === 'tool_result'" class="thinking-group">
            <div v-if="msg.role === 'tool'" class="thinking-toggle" @click="toggleThinking(msg._key)">
              <span>🔧 思考过程</span>
              <span class="toggle-arrow">{{ thinkingOpen[msg._key] !== false ? '▼' : '▶' }}</span>
            </div>
            <div v-show="thinkingOpen[msg._key] !== false" class="thinking-body">
              <div class="message-content" v-html="msg._html"></div>
            </div>
          </div>

          <!-- Regular messages -->
          <div v-else :class="['message', msg.role]">
            <div class="message-content" v-html="msg._html"></div>
            <div v-if="msg.execResults && msg.execResults.length" class="exec-results">
              <div v-for="(er, ei) in msg.execResults" :key="ei" class="exec-result-item">
                <div class="exec-result-header">
                  <span :style="{ color: er.exitCode === 0 ? '#67c23a' : '#f56c6c' }">
                    {{ er.exitCode === 0 ? '执行成功' : '执行失败' }}
                    <template v-if="er.attempt">(第{{ er.attempt }}次)</template> ({{ er.execTimeMs }}ms)
                  </span>
                </div>
                <div v-if="er.images && er.images.length" class="exec-images">
                  <img v-for="(img, ii) in er.images" :key="ii" :src="'data:image/png;base64,' + img" class="exec-image" @click="previewImage(img)" />
                </div>
                <pre v-if="er.stdout" class="exec-stdout">{{ er.stdout }}</pre>
                <pre v-if="er.stderr" class="exec-stderr">{{ er.stderr }}</pre>
              </div>
            </div>
          </div>
        </template>

        <div v-if="loadingConvId === currentConvId" class="message assistant">
          <div class="message-content"><em>思考中...</em></div>
        </div>
      </div>
      <div class="chat-input">
        <el-input v-model="input" placeholder="请输入无线通信相关问题..." @keyup.enter="sendMessage" :disabled="loading">
          <template #append>
            <el-button @click="sendMessage" :loading="loading" type="primary">发送</el-button>
          </template>
        </el-input>
      </div>
    </el-card>

    <Teleport to="body">
      <div v-if="previewSrc" class="image-lightbox" @click="previewSrc = null"><img :src="previewSrc" /></div>
    </Teleport>
  </div>
</template>

<script setup>
import { ref, computed, nextTick, shallowRef, onMounted } from "vue";
import { ElMessage, ElMessageBox } from "element-plus";
import { marked } from "marked";
import katex from "katex";
import "katex/dist/katex.min.css";
import api from "../api";

const input = ref("");
const messages = shallowRef([]);
const loadingConvId = ref(null);
const loading = computed(() => loadingConvId.value !== null);
const messagesContainer = ref(null);
const codeMap = {};
const executingKeys = ref(new Set());
const thinkingOpen = ref({}); // key → bool for collapsible thinking groups
const previewSrc = ref(null);
const conversations = ref([]);
const currentConvId = ref(null);
const hasMore = ref(false);
const oldestMsgId = ref(null);
let msgUid = 0;

onMounted(async () => {
  await loadConversations();
  if (conversations.value.length) await switchConversation(conversations.value[0].id);
  else await newConversation();
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
async function fetchToolMessages(convId) {
  try {
    const res = await api.get(`/api/conversations/${convId}`, { params: { limit: 50 } });
    const existingContents = new Set(messages.value.map(m => m.content));
    const toolMsgs = [];
    for (const m of res.data.messages) {
      if ((m.role === 'tool' || m.role === 'tool_result') && !existingContents.has(m.content)) {
        toolMsgs.push({
          _key: ++msgUid, role: m.role, content: m.content,
          _html: renderHtml(m.content, msgUid), execResults: [],
        });
        existingContents.add(m.content);
      }
    }
    if (toolMsgs.length > 0) {
      // Insert tool messages before the last assistant message (correct chronological order)
      let insertAt = messages.value.length;
      for (let i = messages.value.length - 1; i >= 0; i--) {
        if (messages.value[i].role === 'assistant') { insertAt = i; break; }
      }
      const updated = [...messages.value];
      updated.splice(insertAt, 0, ...toolMsgs);
      messages.value = updated;
      await nextTick(); scrollToBottom();
    }
  } catch {}
}
async function switchConversation(id) {
  currentConvId.value = id; hasMore.value = false; oldestMsgId.value = null;
  try {
    const res = await api.get(`/api/conversations/${id}`, { params: { limit: 50 } });
    messages.value = res.data.messages.map((m) => ({
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
    const older = res.data.messages.map((m) => ({
      _key: ++msgUid, role: m.role, content: m.content,
      _html: renderHtml(m.content, msgUid), execResults: [],
      _thinkingOpen: m.role === 'tool',
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
function renderHtml(raw, msgIdx) {
  if (!raw) return "";
  Object.keys(codeMap).forEach((k) => { if (codeMap[k].msgIdx === msgIdx) delete codeMap[k]; });
  let blockIdx = 0, remaining = raw;
  remaining = remaining.replace(/```(\w*)\n([\s\S]*?)```/g, (_, lang, code) => {
    const key = `c_${msgIdx}_${blockIdx++}`;
    codeMap[key] = { code: code.trim(), msgIdx };
    const esc = escapeHtml(code.trim()), ln = lang || "text";
    return `<div class="code-block-wrapper"><div class="code-block-header"><span>${escapeHtml(ln)}</span><div class="code-block-actions"><button class="copy-code-btn" data-key="${key}">复制</button><button class="run-code-btn" data-key="${key}">▶ 运行</button></div></div><pre><code class="language-${escapeHtml(ln)}">${esc}</code></pre></div>`;
  });
  remaining = remaining.replace(/`([^`]+)`/g, (_,c) => `<code>${escapeHtml(c)}</code>`);
  remaining = remaining.replace(/\$\$([\s\S]*?)\$\$/g, (_,f) => { try { return katex.renderToString(f.trim(),{displayMode:true,throwOnError:false}); } catch { return `<pre>${escapeHtml(f)}</pre>`; }});
  remaining = remaining.replace(/(?<!\$)\$(?!\$)([^$]+?)\$(?!\$)/g, (_,f) => { try { return katex.renderToString(f.trim(),{displayMode:false,throwOnError:false}); } catch { return escapeHtml(f); }});
  return marked.parse(remaining);
}
function addLocalMessage(role, content) {
  const m = { _key: ++msgUid, role, content, _html: renderHtml(content, msgUid), execResults: [] };
  messages.value = [...messages.value, m];
  return m;
}

// ---- Code execution ----
function extractCodeBlock(t) { const m = t.match(/```\w*\n([\s\S]*?)```/); return m ? m[1].trim() : null; }
function toggleThinking(key) { thinkingOpen.value = { ...thinkingOpen.value, [key]: thinkingOpen.value[key] === false ? true : false }; }

async function handleCodeClick(event) {
  const copyBtn = event.target.closest(".copy-code-btn");
  if (copyBtn) {
    const e = codeMap[copyBtn.dataset.key];
    if (e) { try { await navigator.clipboard.writeText(e.code); } catch { const ta=document.createElement("textarea");ta.value=e.code;document.body.appendChild(ta);ta.select();document.execCommand("copy");document.body.removeChild(ta); } ElMessage.success("已复制"); }
    return;
  }
  const btn = event.target.closest(".run-code-btn");
  if (!btn) return;
  const key = btn.dataset.key, entry = codeMap[key];
  if (!entry) return;
  const msg = messages.value.find((m) => m._key === entry.msgIdx);
  if (!msg || executingKeys.value.has(key)) return;
  executingKeys.value = new Set([...executingKeys.value, key]);

  let currentCode = entry.code;
  const maxRetries = 3, startTime = Date.now();
  // Show thinking process immediately
  const thinkingMsg = addLocalMessage("tool", `[工具调用 代码执行]\n\`\`\`python\n${currentCode}\n\`\`\``);
  const resultMsg = addLocalMessage("tool_result", "运行中...");

  for (let attempt = 0; attempt <= maxRetries; attempt++) {
    try {
      const res = await api.post("/api/code/execute", { code: currentCode, language: "python" });
      // Update result in place
      resultMsg.content = res.data.stdout ? `[执行结果]\n\`\`\`\n${res.data.stdout}\n\`\`\`` : `[执行错误]\n\`\`\`\n${res.data.stderr}\n\`\`\``;
      resultMsg._html = renderHtml(resultMsg.content, resultMsg._key);
      messages.value = [...messages.value];
      msg.execResults.push({ stdout: res.data.stdout || "", stderr: res.data.stderr || "", exitCode: res.data.exit_code ?? -1, execTimeMs: Date.now() - startTime, attempt: attempt + 1, images: res.data.images || [] });
      messages.value = [...messages.value];

      // Save tool result to conversation
      api.post(`/api/conversations/${currentConvId.value}/tool`, {
        code: currentCode, language: "python",
        stdout: res.data.stdout || "", stderr: res.data.stderr || "",
        exit_code: res.data.exit_code ?? -1, attempt: attempt + 1,
      }).catch(() => {});

      if (res.data.exit_code === 0) {
        addLocalMessage("system", `代码执行成功 (第${attempt + 1}次):\n${res.data.stdout}`);
        break;
      }
      if (attempt < maxRetries) {
        try {
          const fixRes = await api.post("/api/chat", {
            message: `代码执行错误，请修正：\n${res.data.stderr.slice(0,500)}`,
            conversation_id: currentConvId.value,
          });
          const fixedCode = extractCodeBlock(fixRes.data.response);
          if (fixedCode) { currentCode = fixedCode;
            thinkingMsg.content = `[工具调用 第${attempt+2}次]\n\`\`\`python\n${fixedCode}\n\`\`\``;
            thinkingMsg._html = renderHtml(thinkingMsg.content, thinkingMsg._key);
            resultMsg.content = "运行中..."; resultMsg._html = renderHtml("运行中...", resultMsg._key);
            messages.value=[...messages.value]; await nextTick(); }
          else { addLocalMessage("system","Agent 未能生成有效修正代码。"); break; }
        } catch { addLocalMessage("system","自动修正请求失败。"); break; }
      } else { addLocalMessage("system",`已重试${maxRetries}次仍未成功。`); }
    } catch (e) {
      msg.execResults.push({ stdout:"", stderr:e.message||"网络错误", exitCode:-1, execTimeMs:Date.now()-startTime, attempt:attempt+1 });
      messages.value=[...messages.value]; break;
    }
  }
  executingKeys.value = new Set([...executingKeys.value].filter((k) => k !== key));
  await nextTick(); scrollToBottom();
}

// ---- Chat ----
async function sendMessage() {
  const text = input.value.trim();
  if (!text) return;
  addLocalMessage("user", text);
  input.value = "";
  const thisConvId = currentConvId.value;
  loadingConvId.value = thisConvId;
  try {
    const res = await api.post("/api/chat", { message: text, conversation_id: thisConvId });
    if (currentConvId.value === thisConvId) {
      addLocalMessage("assistant", res.data.response);
      // Fetch tool messages (thinking process) saved by backend during agent execution
      await fetchToolMessages(thisConvId);
    }
    await loadConversations();
  } catch (e) {
    if (currentConvId.value === thisConvId) {
      if (e.code === "ECONNABORTED") ElMessage.error("请求超时，请重试");
      else if (e.response?.data?.detail) ElMessage.error(e.response.data.detail);
      else ElMessage.error("请求失败: " + (e.message || "未知错误"));
    }
  } finally {
    if (loadingConvId.value === thisConvId) loadingConvId.value = null;
    await nextTick(); scrollToBottom();
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
.chat-messages { flex: 1; overflow-y: auto; padding: 16px; }
.load-more { text-align: center; padding: 8px; color: #1677ff; cursor: pointer; font-size: 13px; margin-bottom: 12px; }
.load-more:hover { color: #409eff; text-decoration: underline; }

.message { margin-bottom: 16px; }
.message.user .message-content { background: #409eff; color: #fff; margin-left: auto; max-width: 70%; border-radius: 12px 12px 4px 12px; }
.message.assistant .message-content { background: #f0f0f0; max-width: 85%; border-radius: 12px 12px 12px 4px; }
.message.system .message-content { background: #f0f9eb; border: 1px solid #b3e19d; max-width: 85%; border-radius: 12px 12px 12px 4px; font-size: 13px; }
.message-content { display: inline-block; padding: 10px 14px; font-size: 14px; line-height: 1.6; }
.message-content :deep(p) { margin: 4px 0; }
.message-content :deep(.katex-display) { margin: 8px 0; overflow-x: auto; }
.chat-input { padding: 12px 0 0; border-top: 1px solid #eee; }

/* Tool / thinking process */
.thinking-group { margin-bottom: 12px; }
.thinking-toggle { cursor: pointer; padding: 8px 12px; background: #fafafa; border: 1px solid #e8e8e8; border-radius: 8px; font-size: 13px; color: #666; display: flex; justify-content: space-between; user-select: none; }
.thinking-toggle:hover { background: #f0f0f0; }
.toggle-arrow { font-size: 11px; }
.thinking-body { padding: 8px 12px; border-left: 3px solid #e8e8e8; margin-left: 8px; }
.thinking-body .message-content { background: #fafafa; border: 1px solid #eee; font-size: 13px; }
.thinking-body :deep(.code-block-actions) { display: none; }

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
