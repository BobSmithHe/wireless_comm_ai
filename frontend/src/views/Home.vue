<template>
  <div class="home-page">
    <h2>无线通信 AI 助手</h2>
    <p class="subtitle">面向无线通信工程师和研究人员的智能研发助手</p>

    <el-row :gutter="20" style="margin-top: 24px">
      <el-col :span="8">
        <el-card shadow="hover" @click="$router.push('/chat')" class="feature-card">
          <el-icon :size="40" color="#409eff"><ChatDotRound /></el-icon>
          <h3>智能对话</h3>
          <p>基于 RAG 的无线通信专业知识问答，支持代码生成与执行</p>
        </el-card>
      </el-col>
      <el-col :span="8">
        <el-card shadow="hover" @click="$router.push('/knowledge')" class="feature-card">
          <el-icon :size="40" color="#67c23a"><Document /></el-icon>
          <h3>知识库</h3>
          <p>检索无线通信领域算法、协议规范、代码示例等专业知识</p>
        </el-card>
      </el-col>
      <el-col :span="8">
        <el-card shadow="hover" @click="$router.push('/code')" class="feature-card">
          <el-icon :size="40" color="#e6a23c"><Monitor /></el-icon>
          <h3>代码执行</h3>
          <p>在线编写、运行和调试 Python 无线通信仿真代码</p>
        </el-card>
      </el-col>
    </el-row>

    <el-row :gutter="20" style="margin-top: 16px">
      <el-col :span="8">
        <el-card shadow="hover" @click="$router.push('/memory')" class="feature-card">
          <el-icon :size="40" color="#f56c6c"><Clock /></el-icon>
          <h3>记忆系统</h3>
          <p>四层金字塔记忆架构：原始对话 → 原子事实 → 场景聚类 → 用户画像</p>
        </el-card>
      </el-col>
      <el-col :span="16">
        <el-card shadow="hover" class="feature-card">
          <h3>支持领域</h3>
          <el-tag v-for="fact in quickFacts" :key="fact" style="margin: 4px">{{ fact }}</el-tag>
          <p style="margin-top: 12px">点击进入对话，深入探索以上话题。</p>
        </el-card>
      </el-col>
    </el-row>
  </div>
</template>

<script setup>
const quickFacts = [
  "OFDM", "MIMO", "5G NR", "LDPC 编码", "信道估计", "QAM 调制",
  "波束赋形", "注水算法", "瑞利衰落", "Massive MIMO",
  "毫米波", "3GPP 38.211", "Polar 码", "分集合并",
];
</script>

<style scoped>
.home-page h2 {
  margin-bottom: 4px;
}
.subtitle {
  color: #666;
  font-size: 15px;
}
.feature-card {
  cursor: pointer;
  border-radius: 8px;
  transition: transform 0.2s;
}
.feature-card:hover {
  transform: translateY(-2px);
}
.feature-card h3 {
  margin: 12px 0 8px;
}
.feature-card p {
  color: #888;
  font-size: 13px;
}
</style>
