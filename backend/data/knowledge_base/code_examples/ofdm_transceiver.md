# OFDM 收发机仿真

```python
"""
OFDM 基带收发机仿真
包含：16QAM 调制、IFFT/FFT、循环前缀、AWGN 信道、BER 计算
"""

import numpy as np
import matplotlib.pyplot as plt
from scipy.fft import fft, ifft, fftshift

# ============ 参数配置 ============
N_SUBCARRIERS = 64       # 子载波数
CP_LEN = 16              # 循环前缀长度
N_SYMBOLS = 1000         # OFDM 符号数
MOD_ORDER = 16           # QAM 阶数 (16QAM)
PILOT_SPACING = 8        # 导频间隔

# ============ 16QAM 星座 ============
def qam_modulate(bits, M=16):
    """将比特流映射为 QAM 符号"""
    k = int(np.log2(M))
    symbols_per_row = int(np.sqrt(M))
    bits = bits[:len(bits) - len(bits) % k].reshape(-1, k)
    real = 2 * bits[:, :k//2].dot(2**np.arange(k//2)[::-1]) - (symbols_per_row - 1)
    imag = 2 * bits[:, k//2:].dot(2**np.arange(k//2)[::-1]) - (symbols_per_row - 1)
    return (real + 1j * imag) / np.sqrt(10)  # 归一化 (E[|s|^2] = 1 for 16QAM)

def qam_demodulate(symbols, M=16):
    """QAM 符号硬判决解调为比特 (对 16QAM)"""
    symbols_per_row = int(np.sqrt(M))
    k = int(np.log2(M))
    syms = symbols * np.sqrt(10)
    real = np.clip(np.round((syms.real + 3) / 2), 0, symbols_per_row - 1).astype(int)
    imag = np.clip(np.round((syms.imag + 3) / 2), 0, symbols_per_row - 1).astype(int)
    bits = np.zeros((len(symbols), k), dtype=int)
    for i in range(k // 2):
        bits[:, i] = (real >> (k//2 - 1 - i)) & 1
        bits[:, k//2 + i] = (imag >> (k//2 - 1 - i)) & 1
    return bits.flatten()

# ============ OFDM 调制与解调 ============
def ofdm_modulate(symbols, n_fft, cp_len):
    """OFDM 调制: 子载波映射 → IFFT → 加 CP → 并串转换"""
    n_symbols = len(symbols) // (n_fft // 2)  # 一半子载波传数据
    symbols = symbols[:n_symbols * n_fft // 2].reshape(n_symbols, -1)

    # 子载波映射 (Hermitian 对称以保证实数 IFFT 输出)
    freq_grid = np.zeros((n_symbols, n_fft), dtype=complex)
    freq_grid[:, 1:n_fft//2] = symbols[:, :n_fft//2 - 1]
    freq_grid[:, n_fft//2 + 1:] = np.conj(symbols[:, ::-1][:, :n_fft//2 - 1])

    # IFFT
    time_signal = ifft(freq_grid, axis=1) * np.sqrt(n_fft)

    # 加 CP (复制末尾 cp_len 个样点到前面)
    cp = time_signal[:, -cp_len:]
    return np.hstack([cp, time_signal]).flatten()

def ofdm_demodulate(signal, n_fft, cp_len):
    """OFDM 解调: 去CP → FFT → 提取数据子载波"""
    total_len = n_symbols_from_signal(len(signal), n_fft, cp_len)
    signal = signal[:total_len * (n_fft + cp_len)]
    signal = signal.reshape(-1, n_fft + cp_len)
    signal = signal[:, cp_len:]
    freq_grid = fft(signal, axis=1) / np.sqrt(n_fft)
    symbols = freq_grid[:, 1:n_fft//2]
    return symbols.flatten()

def n_symbols_from_signal(length, n_fft, cp_len):
    return length // (n_fft + cp_len)

# ============ 信道模拟 ============
def awgn(signal, snr_db):
    """添加复高斯白噪声"""
    signal_power = np.mean(np.abs(signal)**2)
    noise_power = signal_power / (10**(snr_db / 10))
    noise = np.sqrt(noise_power / 2) * (
        np.random.randn(len(signal)) + 1j * np.random.randn(len(signal))
    )
    return signal + noise

def multipath_channel(signal, taps, delays):
    """多径信道 (离散延迟线模型)"""
    output = np.zeros(len(signal) + max(delays), dtype=complex)
    for tap, delay in zip(taps, delays):
        output[delay:delay + len(signal)] += tap * signal
    return output[:len(signal)]

# ============ 完整仿真流程 ============
def run_ofdm_simulation(snr_range_db, n_symbols=N_SYMBOLS):
    """仿真 AWGN 信道下 OFDM 系统 BER"""
    n_fft = N_SUBCARRIERS
    cp_len = CP_LEN
    bits_per_symbol = int(np.log2(MOD_ORDER))
    n_data_carriers = n_fft // 2 - 1

    total_bits = n_symbols * n_data_carriers * bits_per_symbol
    tx_bits = np.random.randint(0, 2, total_bits)

    # 调制
    tx_symbols = qam_modulate(tx_bits, MOD_ORDER)
    ofdm_signal = ofdm_modulate(tx_symbols, n_fft, cp_len)

    ber_results = []
    for snr in snr_range_db:
        # 信道
        rx_signal = awgn(ofdm_signal, snr)
        # 解调
        rx_symbols = ofdm_demodulate(rx_signal, n_fft, cp_len)[:len(tx_symbols)]
        rx_bits = qam_demodulate(rx_symbols, MOD_ORDER)[:len(tx_bits)]
        # BER
        errors = np.sum(tx_bits != rx_bits)
        ber_results.append(errors / len(tx_bits))

    return ber_results

if __name__ == "__main__":
    snr_range = np.arange(0, 26, 2)
    ber = run_ofdm_simulation(snr_range)

    # 理论 16QAM BER (AWGN, Gray mapping, 近似)
    from scipy.special import erfc
    snr_linear = 10**(snr_range / 10)
    ber_theory = (3/8) * erfc(np.sqrt(2 * snr_linear / 5))

    plt.semilogy(snr_range, ber, 'o-', label='OFDM-16QAM Simulated')
    plt.semilogy(snr_range, ber_theory, '--', label='16QAM Theory (AWGN)')
    plt.xlabel('SNR (dB)')
    plt.ylabel('BER')
    plt.grid(True, alpha=0.3)
    plt.legend()
    plt.title('OFDM System BER Performance (64 subcarriers, 16QAM, AWGN)')
    plt.show()
```
