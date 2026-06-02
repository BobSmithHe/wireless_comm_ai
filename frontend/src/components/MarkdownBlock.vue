<template>
  <div class="message-text" v-html="html" />
</template>

<script setup>
import { ref, watch, nextTick } from "vue";
import { marked } from "marked";
import katex from "katex";
import "katex/dist/katex.min.css";

const props = defineProps({
  text: { type: String, default: "" },
  msgKey: { type: Number, default: 0 },
});

const html = ref("");

function render(text) {
  if (!text) { html.value = ""; return; }

  // Phase 1: protect code blocks
  const codeBlocks = [];
  let processed = text
    .replace(/```(\w*)\n([\s\S]*?)```/g, (_, lang, code) => {
      const idx = codeBlocks.length;
      codeBlocks.push({ lang, code: code.trimEnd() });
      return `%%CB${idx}%%`;
    })
    .replace(/```(\w*)\n([\s\S]*?)$/g, (_, lang, code) => {
      const idx = codeBlocks.length;
      codeBlocks.push({ lang, code: code.trimEnd() });
      return `%%CB${idx}%%`;
    });

  // Phase 2: protect math
  const mathExprs = [];
  processed = processed
    .replace(/\$\$([\s\S]*?)\$\$/g, (_, f) => { mathExprs.push({f:f.trim(),d:true}); return `%%M${mathExprs.length-1}%%`; })
    .replace(/\$\$([\s\S]*?)$/g, (_, f) => { mathExprs.push({f:f.trim(),d:true}); return `%%M${mathExprs.length-1}%%`; })
    .replace(/(?<!\$)\$(?!\$)([^$\n]+?)\$(?!\$)/g, (_, f) => { mathExprs.push({f:f.trim(),d:false}); return `%%M${mathExprs.length-1}%%`; });

  // Phase 3: auto-close incomplete syntax, then parse
  const completed = autoClose(processed);
  let h = marked.parse(completed);

  // Phase 4: restore math with KaTeX
  mathExprs.forEach((e, i) => {
    const ph = `%%M${i}%%`;
    try {
      h = h.replace(ph, katex.renderToString(e.f, { displayMode: e.d, throwOnError: false }));
    } catch { h = h.replace(ph, `<code>${escapeHtml(e.f)}</code>`); }
  });

  // Phase 5: restore code blocks
  codeBlocks.forEach((b, i) => {
    const ph = `%%CB${i}%%`;
    const codeHtml = `<div class="code-block-wrapper"><div class="code-block-header"><span>${escapeHtml(b.lang||'text')}</span></div><pre><code>${escapeHtml(b.code)}</code></pre></div>`;
    h = h.replace(new RegExp(`<p>\\s*${ph.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}\\s*</p>`, 'g'), codeHtml);
    h = h.replace(ph, codeHtml);
  });

  html.value = h;
}

function autoClose(text) {
  let r = text;
  if ((r.match(/```/g) || []).length % 2 !== 0) r += '\n```';
  if ((r.match(/(?<!`)`(?!`)/g) || []).length % 2 !== 0) r += '`';
  if ((r.match(/\$\$/g) || []).length % 2 !== 0) r += '$$';
  const nd = r.replace(/\$\$/g, '');
  if ((nd.match(/(?<!\$)\$(?!\$)/g) || []).length % 2 !== 0) r += '$';
  return r;
}

function escapeHtml(t) { return t.replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;"); }

// Async watch — does NOT block the streaming loop
watch(() => props.text, (val) => {
  nextTick(() => render(val));
}, { immediate: true });
</script>
