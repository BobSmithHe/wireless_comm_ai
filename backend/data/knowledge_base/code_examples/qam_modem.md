# QAM 调制解调 & 星座图

```python
"""
QAM 调制解调完整实现
支持: BPSK, QPSK, 16QAM, 64QAM, 256QAM
包含: Gray 映射/解映射, 星座图绘制, EVM 计算, BER 仿真
"""

import numpy as np
import matplotlib.pyplot as plt

# ============ QAM 调制器 ============
class QAMModem:
    """
    通用 M-QAM 调制解调器 (M = 2^k, k 为偶数)
    """

    def __init__(self, M):
        """
        参数:
          M: 调制阶数 (4, 16, 64, 256)
        """
        self.M = M
        self.k = int(np.log2(M))        # 每符号比特数
        self.m = int(np.sqrt(M))        # 每维星座点数
        if self.m ** 2 != M:
            raise ValueError(f"M={M} 不是标准方形 QAM")

        # 构造 Gray 映射星座
        self._build_constellation()

    def _binary_reflected_gray(self, n):
        """生成长度为 n 的 Gray 码序列"""
        if n == 1:
            return np.array([0, 1])
        prev = self._binary_reflected_gray(n - 1)
        return np.concatenate([prev, 2**(n-1) + prev[::-1]])

    def _build_constellation(self):
        """构造 Gray 映射的 QAM 星座图"""
        half_k = self.k // 2

        # I/Q 各 half_k 比特的 Gray 码
        gray_seq = self._binary_reflected_gray(half_k)

        # 星座点坐标: (2*i - m + 1) 归一化
        coords = 2 * np.arange(self.m) - self.m + 1

        # 平均能量归一化: E[|s|^2] = 1
        energy = np.mean(coords**2) * 2  # I² + Q² 均为 0 均值
        self.constellation_coords = coords / np.sqrt(energy / 2)

        # 构造完整星座 (I + jQ)
        self.constellation = np.zeros(self.M, dtype=complex)
        self.bit_to_symbol = {}  # 比特串 → 符号索引

        I_bits = gray_seq
        Q_bits = gray_seq
        for i, bi in enumerate(I_bits):
            for q, bq in enumerate(Q_bits):
                idx = i * self.m + q
                self.constellation[idx] = (
                    self.constellation_coords[i] + 1j * self.constellation_coords[q]
                )
                # 合并 I/Q 比特 (I 高半, Q 低半)
                bits = (bi << half_k) | bq
                self.bit_to_symbol[bits] = idx

        self.avg_energy = np.mean(np.abs(self.constellation)**2)

    def modulate(self, bits):
        """
        比特 → QAM 符号
        bits: [N] 或 [N_frames, k] 的 0/1 数组
        """
        bits = np.asarray(bits, dtype=int)
        if bits.ndim == 1:
            bits = bits[:len(bits) - len(bits) % self.k].reshape(-1, self.k)

        symbols = np.zeros(bits.shape[0], dtype=complex)
        half_k = self.k // 2

        for idx, bit_vec in enumerate(bits):
            # I 部分 (高 half_k 比特)
            i_gray = 0
            for b in range(half_k):
                i_gray = (i_gray << 1) | bit_vec[b]
            # Q 部分 (低 half_k 比特)
            q_gray = 0
            for b in range(half_k, self.k):
                q_gray = (q_gray << 1) | bit_vec[b]

            # Gray → 二进制索引
            i_idx = self._gray_to_binary(i_gray, half_k)
            q_idx = self._gray_to_binary(q_gray, half_k)

            symbols[idx] = (
                self.constellation_coords[i_idx] + 1j * self.constellation_coords[q_idx]
            )

        return symbols

    def _gray_to_binary(self, gray_val, n_bits):
        """Gray 码转二进制"""
        binary = gray_val
        for i in range(1, n_bits):
            binary = binary ^ (gray_val >> i)
        return binary

    def demodulate(self, symbols, method='hard'):
        """
        QAM 符号 → 比特
        method:
          'hard': 硬判决 (最近星座点)
          'soft': 软输出 (LLR, 需提供 SNR)
        """
        if method == 'hard':
            return self._hard_demodulate(symbols)

    def _hard_demodulate(self, symbols):
        """硬判决解调: 最近星座点 → Gray 逆映射"""
        symbols = np.asarray(symbols).flatten()
        n_syms = len(symbols)
        half_k = self.k // 2
        bits = np.zeros((n_syms, self.k), dtype=int)

        # 量化到最近星座点
        I_rx = np.clip(
            np.round((symbols.real / self.constellation_coords[rand_enough()])
        )
        # 简化: 直接找最近邻
        for idx, sym in enumerate(symbols):
            distances = np.abs(self.constellation - sym)
            nearest = np.argmin(distances)

            # 星座索引 → I/Q 坐标索引
            i_idx = nearest // self.m
            q_idx = nearest % self.m

            # 坐标索引 → Gray 码
            i_gray = i_idx ^ (i_idx >> 1)  # binary to gray
            q_gray = q_idx ^ (q_idx >> 1)

            # I/Q Gray 码 → 比特
            for b in range(half_k):
                bits[idx, b] = (i_gray >> (half_k - 1 - b)) & 1
                bits[idx, half_k + b] = (q_gray >> (half_k - 1 - b)) & 1

        return bits.flatten()

    def llr_demodulate(self, symbols, snr_linear):
        """
        软解调: 最大似然 LLR 输出
        LLR(b_k) = log( Σ_{s∈S_k^0} exp(-|y-s|²/σ²) / Σ_{s∈S_k^1} exp(-|y-s|²/σ²) )
        使用 max-log 近似: L ≈ (min_1 - min_0) / σ²
        """
        symbols = np.asarray(symbols).flatten()
        n_syms = len(symbols)
        sigma2 = 1.0 / snr_linear
        llrs = np.zeros((n_syms, self.k))

        for idx, y in enumerate(symbols):
            for bit_pos in range(self.k):
                # 比特为 0 的集合
                d0_min = np.inf
                d1_min = np.inf
                for s_idx, s in enumerate(self.constellation):
                    dist = np.abs(y - s)**2
                    bit_val = (s_idx >> (self.k - 1 - bit_pos)) & 1
                    if bit_val == 0:
                        d0_min = min(d0_min, dist)
                    else:
                        d1_min = min(d1_min, dist)

                # Max-log 近似
                llrs[idx, bit_pos] = (d0_min - d1_min) / sigma2

        return llrs.flatten()

# ============ 星座图绘制 ============
def plot_constellation(modem, title=None):
    """绘制 QAM 星座图"""
    fig, ax = plt.subplots(figsize=(6, 6))
    ax.scatter(modem.constellation.real, modem.constellation.imag, s=60, c='blue', zorder=3)

    # 标注比特标签
    for idx, s in enumerate(modem.constellation):
        i_idx = idx // modem.m
        q_idx = idx % modem.m
        i_gray = i_idx ^ (i_idx >> 1)
        q_gray = q_idx ^ (q_idx >> 1)
        bits = (i_gray << (modem.k // 2)) | q_gray
        label = f'{bits:0{modem.k}b}'
        ax.annotate(label, (s.real, s.imag), textcoords="offset points",
                    xytext=(6, 6), fontsize=7, alpha=0.8)

    ax.axhline(0, color='gray', alpha=0.3)
    ax.axvline(0, color='gray', alpha=0.3)
    ax.set_xlabel('In-phase (I)')
    ax.set_ylabel('Quadrature (Q)')
    ax.set_aspect('equal')
    ax.grid(True, alpha=0.2)
    ax.set_title(title or f'{modem.M}-QAM Constellation (Gray Mapping)')
    return fig

# ============ EVM 计算 ============
def compute_evm(tx_symbols, rx_symbols):
    """
    EVM (Error Vector Magnitude)
    EVM_RMS = sqrt(mean(|s_rx - s_tx|²) / mean(|s_tx|²))
    """
    error = rx_symbols - tx_symbols
    evm = np.sqrt(np.mean(np.abs(error)**2) / np.mean(np.abs(tx_symbols)**2))
    return evm * 100  # 百分比

# ============ 完整仿真 ============
def qam_ber_simulation(modem, snr_range_db, n_symbols=50000):
    """仿真 QAM BER vs SNR"""
    ber_hard = np.zeros(len(snr_range_db))
    ber_soft = np.zeros(len(snr_range_db))

    # 随机比特
    total_bits = n_symbols * modem.k
    tx_bits = np.random.randint(0, 2, total_bits)

    # 调制
    tx_symbols = modem.modulate(tx_bits)

    for i, snr_db in enumerate(snr_range_db):
        snr_linear = 10**(snr_db / 10)

        # AWGN
        noise_power = 1.0 / snr_linear
        noise = np.sqrt(noise_power / 2) * (
            np.random.randn(len(tx_symbols)) + 1j * np.random.randn(len(tx_symbols))
        )
        rx_symbols = tx_symbols + noise

        # 硬判决
        rx_bits_hard = modem.demodulate(rx_symbols, 'hard')[:total_bits]
        ber_hard[i] = np.mean(tx_bits != rx_bits_hard)

        # 软判决 LLR → 硬判决比较
        llrs = modem.llr_demodulate(rx_symbols, snr_linear)[:total_bits]
        rx_bits_soft = (llrs < 0).astype(int)
        ber_soft[i] = np.mean(tx_bits != rx_bits_soft)

    return ber_hard, ber_soft

if __name__ == "__main__":
    # 星座图
    fig, axes = plt.subplots(1, 3, figsize=(18, 6))
    for ax, M in zip(axes, [4, 16, 64]):
        modem = QAMModem(M)
        ax.scatter(modem.constellation.real, modem.constellation.imag, s=50, c='blue')
        ax.axhline(0, color='gray', lw=0.5)
        ax.axvline(0, color='gray', lw=0.5)
        ax.set_aspect('equal')
        ax.grid(True, alpha=0.2)
        ax.set_title(f'{M}-QAM')
        ax.set_xlabel('I')
        ax.set_ylabel('Q')
    plt.tight_layout()
    plt.show()

    # BER 仿真 - 16QAM
    print("Simulating 16QAM BER...")
    modem_16qam = QAMModem(16)
    snr_range = np.arange(0, 21, 2)
    ber_hard, ber_soft = qam_ber_simulation(modem_16qam, snr_range, n_symbols=20000)

    plt.semilogy(snr_range, ber_hard, 'o-', label='Hard Decision')
    plt.semilogy(snr_range, ber_soft, 's-', label='Soft Decision (Max-Log)')
    plt.xlabel('SNR (dB)')
    plt.ylabel('BER')
    plt.grid(True, alpha=0.3)
    plt.legend()
    plt.title('16QAM BER Performance: Hard vs Soft Decision')
    plt.show()
```
