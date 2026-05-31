# 信道估计: LS 与 MMSE

```python
"""
OFDM 信道估计: LS (最小二乘) vs MMSE (最小均方误差)
对比两种估计算法的 MSE 和 BER 性能
"""

import numpy as np
import matplotlib.pyplot as plt

# ============ 信道生成 ============
def generate_frequency_channel(n_subcarriers, n_taps=8, delay_spread=3):
    """生成多径频率选择性信道"""
    # 时域冲激响应
    delays = np.arange(n_taps)
    power_profile = np.exp(-0.5 * delays)  # 指数衰减功率谱
    power_profile /= np.sum(power_profile)

    h_t = np.sqrt(power_profile) * (
        np.random.randn(n_taps) + 1j * np.random.randn(n_taps)
    ) / np.sqrt(2)

    # 频域响应 (补零到 N 点做 FFT)
    h_f_padded = np.zeros(n_subcarriers, dtype=complex)
    h_f_padded[:n_taps] = h_t
    h_f = np.fft.fft(h_f_padded)

    # 归一化
    h_f /= np.sqrt(np.mean(np.abs(h_f)**2))
    return h_f

# ============ LS 估计算法 ============
def ls_channel_estimation(rx_pilots, tx_pilots):
    """
    LS: H_LS = Y / X
    简单相除, 无噪声抑制
    """
    return rx_pilots / tx_pilots

# ============ MMSE 估计算法 ============
def mmse_channel_estimation(rx_pilots, tx_pilots, snr_linear, n_fft, n_taps):
    """
    MMSE: H_MMSE = R_HH * (R_HH + (1/SNR) * I)^{-1} * H_LS
    R_HH 通过 FFT 从时延功率谱构造
    """
    # 构造频域信道相关矩阵 R_HH
    delays = np.arange(n_taps)
    power_profile = np.exp(-0.5 * delays)
    power_profile /= np.sum(power_profile)

    # 频域相关矩阵 (Toeplitz, 由功率延迟谱的 IDFT 得到)
    freq_corr = np.zeros(n_fft, dtype=complex)
    freq_corr[:n_taps] = power_profile
    r_time = np.fft.ifft(freq_corr).real  # 时域相关

    # 构建 Toeplitz 矩阵
    first_col = r_time
    if n_fft == len(r_time):
        first_row = r_time
    else:
        first_row = np.zeros(n_fft)
        first_row[0] = r_time[0]
        for i in range(1, min(n_fft, len(r_time))):
            first_row[i] = r_time[i]

    from scipy.linalg import toeplitz
    r_hh = toeplitz(first_col[:n_fft])

    # LS 估计
    h_ls = ls_channel_estimation(rx_pilots, tx_pilots)

    # MMSE
    noise_var = 1.0 / snr_linear
    h_mmse = r_hh @ np.linalg.solve(r_hh + noise_var * np.eye(n_fft), h_ls)

    return h_mmse

# ============ BER 计算 ============
def compute_ber_lte_fading(h_ch, snr_db, n_subcarriers, modulation='QPSK'):
    """
    基于 LTE 参考模型计算瑞利衰落下的 BER
    对于每个子载波独立计算该子载波上的 BER
    """
    snr_linear = 10**(snr_db / 10)
    channel_gain_sq = np.abs(h_ch)**2

    if modulation == 'QPSK':
        # QPSK BER in Rayleigh: 0.5*(1 - sqrt(γ/(1+γ)))
        per_subcarrier_snr = snr_linear * channel_gain_sq
        per_subcarrier_ber = 0.5 * (1 - np.sqrt(per_subcarrier_snr / (1 + per_subcarrier_snr)))
        return np.mean(per_subcarrier_ber)
    elif modulation == '16QAM':
        # 16QAM approx BER
        per_subcarrier_snr = snr_linear * channel_gain_sq
        per_subcarrier_ber = (3/8) * (
            1 - np.sqrt(2 * per_subcarrier_snr / (5 + 2 * per_subcarrier_snr))
        )
        return np.mean(np.clip(per_subcarrier_ber, 0, 0.5))
    return 0.0

# ============ 仿真对比 ============
def run_estimation_comparison(snr_range_db, n_subcarriers=64):
    """对比 LS 和 MMSE 信道估计的 MSE 和 BER"""
    n_taps = 8
    pilot_symbols = np.ones(n_subcarriers, dtype=complex)  # BPSK 导频
    n_runs = 200

    mse_ls = np.zeros(len(snr_range_db))
    mse_mmse = np.zeros(len(snr_range_db))
    ber_ls = np.zeros(len(snr_range_db))
    ber_mmse = np.zeros(len(snr_range_db))
    ber_perfect = np.zeros(len(snr_range_db))

    for i, snr_db in enumerate(snr_range_db):
        snr_linear = 10**(snr_db / 10)
        mse_ls_accum = 0
        mse_mmse_accum = 0
        ber_ls_accum = 0
        ber_mmse_accum = 0
        ber_perfect_accum = 0

        for _ in range(n_runs):
            # 生成信道
            h_true = generate_frequency_channel(n_subcarriers, n_taps)

            # 接收导频 (含噪声)
            noise_power = 1.0 / snr_linear
            noise = np.sqrt(noise_power / 2) * (
                np.random.randn(n_subcarriers) + 1j * np.random.randn(n_subcarriers)
            )
            rx_pilots = h_true * pilot_symbols + noise

            # LS 估计
            h_ls_est = ls_channel_estimation(rx_pilots, pilot_symbols)
            mse_ls_accum += np.mean(np.abs(h_ls_est - h_true)**2)

            # MMSE 估计
            h_mmse_est = mmse_channel_estimation(
                rx_pilots, pilot_symbols, snr_linear, n_subcarriers, n_taps
            )
            mse_mmse_accum += np.mean(np.abs(h_mmse_est - h_true)**2)

            # BER (基于估计信道做均衡后)
            ber_ls_accum += compute_ber_lte_fading(
                h_true / (h_ls_est + 1e-10), snr_db, n_subcarriers
            )
            ber_mmse_accum += compute_ber_lte_fading(
                h_true / (h_mmse_est + 1e-10), snr_db, n_subcarriers
            )
            ber_perfect_accum += compute_ber_lte_fading(h_true, snr_db, n_subcarriers)

        mse_ls[i] = mse_ls_accum / n_runs
        mse_mmse[i] = mse_mmse_accum / n_runs
        ber_ls[i] = ber_ls_accum / n_runs
        ber_mmse[i] = ber_mmse_accum / n_runs
        ber_perfect[i] = ber_perfect_accum / n_runs

    return mse_ls, mse_mmse, ber_ls, ber_mmse, ber_perfect

# ============ 可视化 ============
if __name__ == "__main__":
    snr_range = np.arange(0, 31, 2)
    mse_ls, mse_mmse, ber_ls, ber_mmse, ber_perfect = run_estimation_comparison(snr_range)

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12, 5))

    # MSE 对比
    ax1.semilogy(snr_range, mse_ls, 'o-', label='LS Estimation')
    ax1.semilogy(snr_range, mse_mmse, 's-', label='MMSE Estimation')
    ax1.set_xlabel('SNR (dB)')
    ax1.set_ylabel('MSE')
    ax1.set_title('Channel Estimation MSE')
    ax1.grid(True, alpha=0.3)
    ax1.legend()

    # BER 对比
    ax2.semilogy(snr_range, ber_ls, 'o-', label='LS + ZF Equalization')
    ax2.semilogy(snr_range, ber_mmse, 's-', label='MMSE + ZF Equalization')
    ax2.semilogy(snr_range, ber_perfect, '--', label='Perfect CSI (Lower Bound)')
    ax2.set_xlabel('SNR (dB)')
    ax2.set_ylabel('BER')
    ax2.set_title('BER with Imperfect Channel Estimation')
    ax2.grid(True, alpha=0.3)
    ax2.legend()

    plt.tight_layout()
    plt.show()

# ============ 关键结论 ============
# 1. MMSE 在低 SNR 下显著优于 LS (利用信道统计信息抑制噪声)
# 2. 高 SNR 下两者趋于一致 (噪声影响减小)
# 3. MMSE 需要信道相关矩阵和噪声方差先验知识
# 4. 实际系统中 LS + 插值因其简单性更常用
```
