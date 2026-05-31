# 最大比合并 (MRC) 分集接收

```python
"""
接收分集技术仿真: MRC (最大比合并) vs SC (选择合并) vs EGC (等增益合并)
"""

import numpy as np
import matplotlib.pyplot as plt
from scipy.special import erfc

# ============ 分集合并实现 ============
class DiversityCombiner:
    """多天线分集合并器"""

    @staticmethod
    def mrc(signals, channel_gains):
        """
        最大比合并 (Maximal Ratio Combining)
        y_mrc = Σ h_i^* × y_i
        权重正比于瞬时信道增益, 最大化输出 SNR
        """
        signals = np.asarray(signals)
        channel_gains = np.asarray(channel_gains)
        weights = np.conj(channel_gains)
        combined = np.sum(weights * signals, axis=0)
        effective_channel = np.sum(np.abs(channel_gains)**2, axis=0)
        return combined, effective_channel

    @staticmethod
    def sc(signals, channel_gains):
        """
        选择合并 (Selection Combining)
        选择瞬时 SNR 最大的支路
        """
        signals = np.asarray(signals)
        channel_gains = np.asarray(channel_gains)
        best_branch = np.argmax(np.abs(channel_gains)**2, axis=0)
        # 索引: signals 形状 [L, N_samples]
        selected = signals[best_branch, np.arange(signals.shape[1])]
        selected_channel = channel_gains[best_branch, np.arange(channel_gains.shape[1])]
        return selected, selected_channel

    @staticmethod
    def egc(signals, channel_gains):
        """
        等增益合并 (Equal Gain Combining)
        y_egc = Σ (h_i^* / |h_i|) × y_i
        各支路等加权, 只做相位对齐
        """
        signals = np.asarray(signals)
        channel_gains = np.asarray(channel_gains)
        phases = np.exp(-1j * np.angle(channel_gains))
        weights = phases
        combined = np.sum(weights * signals, axis=0)
        effective_channel = np.sum(np.abs(channel_gains), axis=0)
        return combined, effective_channel

# ============ 瑞利衰落信道 ============
def rayleigh_fading_channels(n_branches, n_samples):
    """生成独立瑞利衰落信道系数 (i.i.d. 复高斯)"""
    h = (np.random.randn(n_branches, n_samples) +
         1j * np.random.randn(n_branches, n_samples)) / np.sqrt(2)
    return h

# ============ BPSK 仿真 ============
def run_diversity_simulation(snr_range_db, L_values, n_symbols=100000):
    """
    对比不同分集阶数 L 和不同合并方式的 BER
    """
    mod_order = 2  # BPSK
    combiner = DiversityCombiner()

    # 存储结果: {L: {method: [ber_per_snr]}}
    results = {}

    for L in L_values:
        results[L] = {'MRC': [], 'SC': [], 'EGC': []}

        for snr_db in snr_range_db:
            snr_linear = 10**(snr_db / 10)

            # 随机比特
            tx_bits = np.random.randint(0, 2, n_symbols)
            tx_symbols = 1 - 2 * tx_bits  # BPSK: 0→+1, 1→-1

            # 生成信道 (L 条独立瑞利支路)
            h = rayleigh_fading_channels(L, n_symbols)

            # 各支路接收信号
            noise_power_branch = 1.0 / snr_linear  # 每支路噪声功率
            noise = np.sqrt(noise_power_branch / 2) * (
                np.random.randn(L, n_symbols) + 1j * np.random.randn(L, n_symbols)
            )

            rx_signals = h * tx_symbols + noise

            # --- MRC ---
            combined, h_eff = combiner.mrc(rx_signals, h)
            # MRC 后的有效 SNR: γ_mrc = Σ |h_i|² / σ²
            rx_bits_mrc = (combined.real < 0).astype(int)
            ber_mrc = np.mean(tx_bits != rx_bits_mrc)
            results[L]['MRC'].append(ber_mrc)

            # --- SC ---
            combined, h_eff = combiner.sc(rx_signals, h)
            rx_bits_sc = (combined.real / (h_eff + 1e-10) < 0).astype(int)
            ber_sc = np.mean(tx_bits != rx_bits_sc)
            results[L]['SC'].append(ber_sc)

            # --- EGC ---
            combined, h_eff = combiner.egc(rx_signals, h)
            rx_bits_egc = (combined.real / (h_eff + 1e-10) < 0).astype(int)
            ber_egc = np.mean(tx_bits != rx_bits_egc)
            results[L]['EGC'].append(ber_egc)

    return results

# ============ MRC 理论 BER (i.i.d. 瑞利, L 阶分集) ============
def mrc_theoretical_ber(snr_db, L):
    """
    MRC + BPSK 在 i.i.d. 瑞利信道下的理论 BER
    闭合表达式
    """
    snr_linear = 10**(snr_db / 10)
    gamma = snr_linear  # 平均每支路 SNR

    # 参数
    mu = np.sqrt(gamma / (1 + gamma))

    # L 阶 MRC 的 BER
    # P_b = ((1-μ)/2)^L * Σ_{k=0}^{L-1} C(L-1+k, k) * ((1+μ)/2)^k
    term1 = ((1 - mu) / 2)**L
    total = 0
    for k in range(L):
        n_choose_k = np.math.comb(L - 1 + k, k)
        total += n_choose_k * ((1 + mu) / 2)**k
    return term1 * total

# ============ 可视化 ============
if __name__ == "__main__":
    snr_range = np.arange(0, 31, 2)
    L_values = [1, 2, 4]

    print("Running diversity combining simulation...")
    results = run_diversity_simulation(snr_range, L_values, n_symbols=50000)

    fig, axes = plt.subplots(1, len(L_values), figsize=(15, 5))

    colors = {'MRC': 'blue', 'SC': 'red', 'EGC': 'green'}
    markers = {'MRC': 'o', 'SC': 's', 'EGC': '^'}

    for idx, L in enumerate(L_values):
        ax = axes[idx]
        for method in ['MRC', 'SC', 'EGC']:
            ax.semilogy(
                snr_range, results[L][method],
                marker=markers[method], color=colors[method],
                markevery=2, label=method, markersize=5
            )

        # MRC 理论曲线
        ber_theory = [mrc_theoretical_ber(snr, L) for snr in snr_range]
        ax.semilogy(snr_range, ber_theory, '--', color='gray', alpha=0.7,
                    label='MRC Theory')

        ax.set_xlabel('SNR per Branch (dB)')
        ax.set_ylabel('BER')
        ax.set_title(f'L = {L} Branches, BPSK, Rayleigh Fading')
        ax.grid(True, alpha=0.3)
        ax.legend(fontsize=8)
        ax.set_ylim([1e-5, 1])

    plt.tight_layout()
    plt.show()

    # 分集增益总结
    print("\n=== Diversity Gain Summary (BER=10^-3) ===")
    for L in L_values:
        for method in ['MRC', 'SC', 'EGC']:
            # 线性插值找 BER=1e-3 所需的 SNR
            ber_array = np.array(results[L][method])
            if ber_array[-1] < 1e-3:
                from scipy.interpolate import interp1d
                f = interp1d(np.log10(ber_array + 1e-15), snr_range)
                snr_at_1em3 = f(np.log10(1e-3))
                print(f"L={L}, {method}: SNR = {snr_at_1em3:.2f} dB")
```
