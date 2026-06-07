<template>
  <div class="code-page">
    <h2>代码编辑器</h2>
    <p style="margin-bottom:12px;color:#666">
      在线编写、执行和调试 Python 无线通信仿真代码
      <span v-if="fromChat" style="color:#409eff">（代码来自对话）</span>
    </p>

    <el-row :gutter="16">
      <el-col :span="14">
        <el-card>
          <template #header>
            <span>Python 代码</span>
          </template>
          <el-input
            v-model="code"
            type="textarea"
            :rows="20"
            placeholder="在此编写 Python 代码..."
            style="font-family:Consolas,monospace;font-size:13px"
          />
          <div style="margin-top:12px">
            <el-button type="primary" @click="executeCode" :loading="executing">运行</el-button>
            <el-button @click="clearOutput">清空输出</el-button>
            <el-button v-if="fromChat" type="success" @click="returnResult" :disabled="!hasResult">
              返回结果给对话
            </el-button>
          </div>
        </el-card>
      </el-col>
      <el-col :span="10">
        <el-card>
          <template #header>输出结果</template>
          <div v-if="images.length" class="code-images">
            <img v-for="(img, i) in images" :key="i"
              :src="'data:image/png;base64,' + img"
              class="code-image" @click="previewSrc = 'data:image/png;base64,' + img" @error="(e) => e.target.style.display = 'none'" />
          </div>
          <pre class="output-area">{{ output || "尚无输出..." }}</pre>
          <pre v-if="error" class="error-area">{{ error }}</pre>
        </el-card>
      </el-col>
    </el-row>

    <Teleport to="body">
      <div v-if="previewSrc" class="image-lightbox" @click="previewSrc = null">
        <img :src="previewSrc" />
      </div>
    </Teleport>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from "vue";
import { useRouter, useRoute } from "vue-router";
import { ElMessage } from "element-plus";
import api from "../api";
import { useCodeStore } from "../store";

const router = useRouter();
const route = useRoute();
const codeStore = useCodeStore();

const code = ref("");
const output = ref("");
const error = ref("");
const images = ref([]);
const executing = ref(false);
const previewSrc = ref(null);

const fromChat = computed(() => !!codeStore.pendingCode);
const hasResult = computed(() => !!(output.value || error.value || images.value.length));

const defaultCode = `import numpy as np
import matplotlib.pyplot as plt

# BPSK 误码率仿真示例
n_bits = 10000
snr_db = 10
snr_linear = 10**(snr_db / 10)

tx_bits = np.random.randint(0, 2, n_bits)
tx_syms = 1 - 2 * tx_bits  # BPSK: 0→+1, 1→-1

noise = np.sqrt(1/(2*snr_linear)) * np.random.randn(n_bits)
rx_syms = tx_syms + noise
rx_bits = (rx_syms < 0).astype(int)

errors = np.sum(tx_bits != rx_bits)
print(f"SNR: {snr_db} dB")
print(f"BER: {errors/n_bits:.4e}")`;

onMounted(async () => {
  const routeCode = route.query.code;
  if (routeCode) {
    code.value = routeCode;
  } else if (codeStore.pendingCode) {
    code.value = codeStore.pendingCode;
    await executeCode();
  } else {
    code.value = defaultCode;
  }
});

async function executeCode() {
  if (!code.value.trim()) return;
  executing.value = true;
  output.value = "";
  error.value = "";
  images.value = [];
  try {
    const res = await api.post("/api/code/execute", {
      code: code.value,
      language: "python",
    });
    output.value = res.data.stdout || "";
    error.value = res.data.stderr || "";
    images.value = res.data.images || [];
    if (res.data.exit_code !== 0) {
      ElMessage.warning(`执行异常，退出码: ${res.data.exit_code}`);
    } else {
      ElMessage.success("执行成功");
    }
  } catch (e) {
    ElMessage.error("执行失败");
  } finally {
    executing.value = false;
  }
}

function clearOutput() {
  output.value = "";
  error.value = "";
  images.value = [];
}

function returnResult() {
  codeStore.setResult({
    stdout: output.value,
    stderr: error.value,
    images: images.value,
  });
  ElMessage.success("结果已返回，请切换回对话页面");
  router.push("/chat");
}
</script>

<style scoped>
.output-area {
  background: #1e1e1e;
  color: #d4d4d4;
  padding: 12px;
  border-radius: 4px;
  font-family: Consolas, monospace;
  font-size: 13px;
  max-height: 300px;
  overflow-y: auto;
  white-space: pre-wrap;
}
.error-area {
  background: #2d0000;
  color: #ff6b6b;
  padding: 12px;
  border-radius: 4px;
  font-family: Consolas, monospace;
  font-size: 13px;
  margin-top: 8px;
  white-space: pre-wrap;
}
.code-images {
  display: flex; flex-wrap: wrap; gap: 8px; margin-bottom: 8px;
}
.code-image {
  max-width: 280px; max-height: 200px; border-radius: 4px;
  border: 1px solid #d0d7de; cursor: pointer; transition: transform 0.15s;
}
.code-image:hover { transform: scale(1.02); }
.image-lightbox {
  position: fixed; top: 0; left: 0; right: 0; bottom: 0;
  background: rgba(0,0,0,0.8); z-index: 9999;
  display: flex; align-items: center; justify-content: center; cursor: pointer;
}
.image-lightbox img { max-width: 90vw; max-height: 90vh; border-radius: 8px; }
</style>
