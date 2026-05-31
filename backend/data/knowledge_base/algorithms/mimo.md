# MIMO (多输入多输出)

## 概述

MIMO 通过在收发两端配置多根天线，利用空间维度提升通信系统的容量和可靠性。它是 4G/5G 的核心技术之一，与 OFDM 结合构成 MIMO-OFDM 系统。

## MIMO 工作模式

### 1. 空间复用 (Spatial Multiplexing)
- 在不同天线上同时传输独立数据流
- 容量随 min(Nt, Nr) 线性增长
- 适用于高 SINR 场景

### 2. 空间分集 (Spatial Diversity)
- 多天线传输相同数据，提高接收可靠性
- 空时分组码 (STBC, Alamouti) 是经典方案
- 适用于低 SINR 场景

### 3. 波束赋形 (Beamforming)
- 调整天线阵列相位，形成定向波束
- Massive MIMO (64T64R / 128T128R) 是 5G 核心特征
- 提升覆盖和能效

## MIMO 信道容量

对于 Nt 根发射天线、Nr 根接收天线的 MIMO 系统：

```
C = log2(det(I + (ρ/Nt) * H * H^H))   bps/Hz
```

其中 H 为 Nr × Nt 信道矩阵，ρ 为 SNR。

在充分散射环境下，容量近似为：

```
C ≈ min(Nt, Nr) × log2(1 + ρ × max(Nt, Nr) / Nt)
```

## 关键技术

- **预编码 (Precoding)**：基于 CSI 在发射端做波束赋形（码本/非码本）
- **信道估计**：利用导频估计 MIMO 信道矩阵（LS、MMSE）
- **信号检测**：ML、ZF、MMSE、球形译码等
- **SVD 分解**：将 MIMO 信道分解为多个并行独立子信道

## 5G NR 中的 MIMO

- FR1: 最高 8 层下行 / 4 层上行
- FR2 (mmWave): 最高 8 层 + 波束管理
- CSI-RS / SRS 用于信道状态信息获取
- 码本类型：Type I (单面板) / Type II (多面板高精度)
