# LDPC 编码与最小和译码

```python
"""
QC-LDPC 最小和译码 (Min-Sum Algorithm) 仿真
包含: 编码、BP 译码、BER vs SNR 性能
"""

import numpy as np
import matplotlib.pyplot as plt

# ============ LDPC 校验矩阵构造 (简化的 IEEE 802.11n 型) ============
def construct_ieee802_11n_h(z=27):
    """
    构造类似 802.11n 的准循环 LDPC 校验矩阵 (基矩阵 × 提升因子)
    简化版: 4×16 基矩阵, 码率 3/4, 信息位 K ≈ 3*Z*8, N = 4*Z*16
    """
    # 基矩阵 (单位矩阵的循环移位值, -1 表示全零子矩阵)
    base_matrix = np.array([
        [ 0, -1, -1, -1,  0,  0, -1, -1,  0, -1, -1,  0,  1,  0, -1, -1],
        [ 1,  0, -1, -1, -1, -1,  0,  1, -1,  0, -1, -1, -1, -1,  0, -1],
        [-1, -1,  0,  1, -1, -1, -1, -1,  0, -1,  0, -1, -1, -1, -1,  0],
        [ 0, -1, -1, -1, -1,  0, -1, -1, -1, -1,  0, -1,  0,  1,  0, -1],
    ])

    n_base = base_matrix.shape[1]  # 16
    m_base = base_matrix.shape[0]  # 4
    n = n_base * z  # 码长
    m = m_base * z  # 校验节点数

    H = np.zeros((m, n), dtype=int)

    for i in range(m_base):
        for j in range(n_base):
            shift = base_matrix[i, j]
            if shift >= 0:
                for k in range(z):
                    col = j * z + (k + shift) % z
                    row = i * z + k
                    H[row, col] = 1

    return H

def get_identity_submatrix(z, shift):
    """返回 z×z 循环移位单位矩阵"""
    I = np.eye(z, dtype=int)
    return np.roll(I, shift, axis=1)

# ============ LDPC 编码 (基于生成矩阵) ============
def ldpc_encode_gaussian(H, u):
    """
    通过高斯消元求系统生成矩阵 G, 然后编码: c = u × G
    注意: 复杂度 O(n³), 仅适用于中小码长仿真
    """
    m, n = H.shape
    # 高斯消元将 H 化为 [I | P] 形式 (如果可能)
    # 简化为: 假设 H*[p; u] = 0, 求解校验位 p
    # 这里使用 Gaussian elimination over GF(2)

    # 构造系统生成矩阵的简化方法:
    # 将 H 分为 [H1 | H2], 其中 H2 非奇异
    # 则 G = [I | H2^{-1} * H1]

    H_copy = H.copy() % 2
    # 寻找 n-k 列使它们可逆
    k = n - m
    pivot_cols = []
    col_idx = list(range(n))

    H_temp = H_copy.copy()
    for r in range(m):
        found = False
        for c in range(r, n):
            if H_temp[r, c] == 1:
                found = True
                pivot_cols.append(col_idx[c])
                # 交换列
                H_temp[:, [r, c]] = H_temp[:, [r, c]]
                col_idx[r], col_idx[c] = col_idx[c], col_idx[r]
                # 消除其他行
                for rr in range(m):
                    if rr != r and H_temp[rr, r] == 1:
                        H_temp[rr, :] = (H_temp[rr, :] + H_temp[r, :]) % 2
                break
        if not found:
            raise ValueError("H matrix not full rank (try different construction)")

    # 构造系统生成矩阵
    P = H_temp[:, k:]  # m × m 部分
    G_sys = np.hstack([np.eye(k, dtype=int), H_temp[:k, k:]])  # 可能需要调整

    # 简化: 直接使用高斯消元编码
    # 码字 c = [u, p], 满足 H * c^T = 0
    # H1 * u^T + H2 * p^T = 0 → p^T = H2^{-1} * H1 * u^T

    # 取最后 m 列作为 H2
    H1 = H_copy[:, :k]
    H2 = H_copy[:, k:]

    # 编码: p = H2^{-1} * H1 * u (in GF(2))
    h1_u = (H1 @ u.T) % 2
    # 求解 H2 * p = h1_u
    # 高斯消元求解 (简化, 使用 numpy 的 GF(2) 等价)
    H2_inv_h1u = gf2_solve(H2, h1_u)

    codeword = np.hstack([u, H2_inv_h1u]) % 2
    return codeword

def gf2_solve(A, b):
    """GF(2) 上求解线性方程组 Ax = b"""
    n = A.shape[1]
    augmented = np.hstack([A.copy() % 2, b.reshape(-1, 1) % 2])
    m = augmented.shape[0]

    # 高斯消元
    for col in range(min(m, n)):
        # 找主元
        pivot_row = None
        for row in range(col, m):
            if augmented[row, col] == 1:
                pivot_row = row
                break
        if pivot_row is None:
            continue
        # 交换行
        augmented[[col, pivot_row]] = augmented[[pivot_row, col]]
        # 消除其他行
        for row in range(m):
            if row != col and augmented[row, col] == 1:
                augmented[row, :] = (augmented[row, :] + augmented[col, :]) % 2

    # 提取解
    x = np.zeros(n, dtype=int)
    for i in range(min(m, n)):
        if augmented[i, i] == 1:
            x[i] = augmented[i, -1]
    return x

# ============ Min-Sum 译码 ============
def min_sum_decoding(H, rx_llr, max_iter=50, scale_factor=0.75):
    """
    归一化最小和 (Normalized Min-Sum) BP 译码
    输入:
      H: m×n 校验矩阵
      rx_llr: 接收符号的对数似然比 (LLR), 长度 n
      max_iter: 最大迭代次数
      scale_factor: 归一化因子 (补偿 MS 近似误差)
    输出:
      译码比特 (0/1), 迭代次数
    """
    m, n = H.shape

    # 初始化变量节点消息: L(q_ij) = L_channel
    var_msg = np.tile(rx_llr, (m, 1))  # m × n

    # 校验节点消息: L(r_ij)
    check_msg = np.zeros((m, n))

    for iteration in range(max_iter):
        # --- 水平步骤 (校验节点更新) ---
        for i in range(m):
            neighbors = np.where(H[i, :] == 1)[0]
            for j in neighbors:
                # 除 j 列外其他邻居的符号和绝对值最小值
                other = neighbors[neighbors != j]
                signs = np.prod(np.sign(var_msg[i, other]))
                min_val = np.min(np.abs(var_msg[i, other])) if len(other) > 0 else np.inf
                check_msg[i, j] = signs * min_val * scale_factor

        # --- 垂直步骤 (变量节点更新) ---
        for j in range(n):
            neighbors = np.where(H[:, j] == 1)[0]
            for i in neighbors:
                other = neighbors[neighbors != i]
                var_msg[i, j] = rx_llr[j] + np.sum(check_msg[other, j])

        # --- 硬判决 ---
        total_llr = rx_llr.copy()
        for j in range(n):
            neighbors = np.where(H[:, j] == 1)[0]
            total_llr[j] += np.sum(check_msg[neighbors, j])

        decoded = (total_llr < 0).astype(int)

        # --- 校验: H * c^T == 0 ---
        syndrome = (H @ decoded.T) % 2
        if np.all(syndrome == 0):
            return decoded, iteration + 1

    return decoded, max_iter

# ============ BPSK 调制 ============
def bpsk_modulate(bits):
    return 1 - 2 * bits  # 0→+1, 1→-1

def llr_bpsk_awgn(rx_symbols, snr_linear):
    """AWGN 下 BPSK 的 LLR"""
    return 4 * snr_linear * rx_symbols

# ============ 完整仿真 ============
def run_ldpc_simulation(snr_range_db, z=27, n_trials=100, min_frame_errors=50):
    """
    LDPC 译码 BER 仿真
    码参数: N = 16*z, K = N - (4*z)
    """
    H = construct_ieee802_11n_h(z)
    m, n = H.shape
    k = n - m  # 信息位长度

    print(f"LDPC Code: N={n}, K={k}, Rate={k/n:.3f}")

    ber_results = []
    for snr_db in snr_range_db:
        snr_linear = 10**(snr_db / 10)
        total_errors = 0
        total_bits = 0
        frame_errors = 0

        for trial in range(n_trials):
            if frame_errors >= min_frame_errors and trial > 200:
                break

            # 随机信息比特
            u = np.random.randint(0, 2, k)

            # 编码
            try:
                c = ldpc_encode_gaussian(H, u)
            except ValueError:
                continue

            # BPSK
            tx = bpsk_modulate(c)

            # AWGN
            noise = np.sqrt(0.5 / snr_linear) * np.random.randn(n)
            rx = tx + noise

            # 计算 LLR
            llr = llr_bpsk_awgn(rx, snr_linear)

            # 译码
            decoded, iters = min_sum_decoding(H, llr, max_iter=50)

            # 统计
            errors = np.sum(decoded != c)
            total_errors += errors
            total_bits += n
            if errors > 0:
                frame_errors += 1

        ber = total_errors / total_bits if total_bits > 0 else 1.0
        ber_results.append(ber)
        print(f"SNR={snr_db:2d}dB | BER={ber:.2e} | Frame Errors={frame_errors}")

    return np.array(ber_results), n, k

if __name__ == "__main__":
    snr_range = np.arange(1, 8)  # 1-7 dB
    ber, n, k = run_ldpc_simulation(snr_range, z=27, n_trials=500, min_frame_errors=30)

    # 未编码 BPSK 理论 BER
    snr_linear = 10**(snr_range / 10)
    ber_uncoded = 0.5 * (1 - np.sqrt(snr_linear / (1 + snr_linear)))

    plt.semilogy(snr_range, ber, 'o-', label=f'LDPC (N={n}, R={k/n:.2f})')
    plt.semilogy(snr_range, ber_uncoded, '--', label='Uncoded BPSK')
    plt.xlabel('SNR (dB)')
    plt.ylabel('BER')
    plt.grid(True, alpha=0.3)
    plt.legend()
    plt.title('LDPC Min-Sum Decoding Performance')
    plt.show()
```
