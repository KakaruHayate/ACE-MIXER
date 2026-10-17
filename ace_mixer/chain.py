#!/usr/bin/env python3
"""
vocal-param 4 通道分析的纯 Python 实现（Energy / Breathiness / Tension / Falsetto）。

输入：单声道音频 (float, [-1,1]) + 逐帧 f0 (Hz, <=0 表示清音/无声)，帧移 256 @ 44.1kHz。
输出：4 条 [n_frames] float32 曲线。

管线（逐阶段说明）：
  1. Energy:      音频 clamp → reflect pad → STFT(2048/256, 周期 Hann) 幅度谱
                  → 128 三角 mel（Fant 刻度, 20..22050Hz, Slaney 面积归一）
                  → 每帧 sqrt(sum(max(mel,1e-8)^2))
  2. 谐波分析:    每帧 4 基音周期对称 Blackman 窗，逐谐波相关求幅度/相位
                  （幅度 = 2|X|/Σw，相位参考到窗中心）
  3. 残差:        用谐波幅度/相位 512 点 Hann OLA 合成谐波信号，原音频减去
  4. Breathiness: 残差做 4 周期 Blackman 窗功率谱（补 2 幂 FFT），
                  24 个对数频带逐带算 10*log10(谐波能量/带内平均噪声谱)，
                  第 12..16 带均值 → 1/(1+10^(m/10)) → 高斯平滑 → clamp[0,1]
  5. Rd 估计:     谐波能量门控，辐射修正后的谐波幅度谱与 LF 声门模型模板做
                  Itakura-Saito 匹配 → 逐帧 Rd → 插值补缺 → 3 点平滑
  6. Tension:     Rd+f0 合成 LF 谱，20*log10(g1/((S2/2S1)*g2)) → 平滑
                  → pitch<=1 置 0 → Box-Cox((|x|+1)^e-1)/e，e=[0.7123,1.2871]，/4.0847
  7. Falsetto:    -log2(Rd) → 平滑 → Box-Cox e=[0.7429,1.2580]，/0.8039
"""

import numpy as np

SR = 44100
HOP = 256
NFFT = 2048
N_MELS = 128
MEL_FMIN = 20.0
MEL_FMAX = 22050.0
MAX_HARMONICS = 100
N_HNR_BANDS = 24

# HNR 频带边缘（对数间隔，0 .. 18180.6 Hz；最高带上界为 Nyquist）
HNR_BAND_EDGES = np.array(
    [
        0.0,
        48.1,
        106.3,
        176.7,
        262.0,
        365.1,
        489.9,
        641.0,
        823.8,
        1045.1,
        1312.8,
        1636.8,
        2028.9,
        2503.5,
        3077.8,
        3772.8,
        4613.8,
        5631.7,
        6863.4,
        8354.1,
        10158.1,
        12341.3,
        14983.3,
        18180.6,
    ],
    dtype=np.float64,
)

# Rd 模板表网格（64 点）与模板频率格（j*200 Hz, j=0..79）
RD_GRID_MIN, RD_GRID_MAX, RD_GRID_N = 0.02, 3.0, 64
RD_TMPL_LEN = 80
RD_TMPL_FSTEP = 200.0
RD_TMPL_F0 = 200.0

# 辐射滤波 smooth-min 常数
RAD_A = 1.441012389579915
RAD_A2 = 2.076516706922817  # = RAD_A**2

# 高斯平滑（帧域）
SMOOTH_SIGMA = 4.0
SMOOTH_RADIUS = 16

# Box-Cox 压缩参数（指数 [正值分支, 负值分支]，除数带符号，最后归一化）
TENSION_EXP = (0.7122999999999999, 1.2871000000000001)  # 内存精确值见下
FALSETTO_EXP = (0.7429000000000001, 1.2580000000000001)
TENSION_NORM = 4.0847
FALSETTO_NORM = 0.8038999999999999

# 从二进制读出的精确 double 位级值（避免十进制舍入差异）
import struct as _struct


def _d(hexle):
    return _struct.unpack("<d", bytes.fromhex(hexle))[0]


TENSION_EXP = (_d("80b74082e2c7e63f"), _d("40a4dfbe0e9cf43f"))
FALSETTO_EXP = (_d("5839b4c876bee73f"), _d("54e3a59bc420f43f"))

TWO_PI = 6.283185307179586
PI = 3.141592653589793
F32 = np.float32


# ---------------------------------------------------------------- 工具


def _llround(x):
    """MSVC llround：half away from zero。"""
    return int(np.floor(x + 0.5)) if x >= 0 else -int(np.floor(-x + 0.5))


def _rint_even(x):
    """银行家舍入（rint 默认舍入模式）。"""
    return int(np.rint(x))


def _blackman_sym_f32(n):
    """对称 Blackman，float32 计算。"""
    if n == 1:
        return np.ones(1, dtype=F32)
    i = np.arange(n, dtype=F32)
    d = F32(n - 1)
    x = (i * F32(6.2831855)) / d
    w = np.cos(x) * F32(-0.5) + F32(0.42)
    w = np.cos(x + x) * F32(0.08) + w
    return w.astype(F32)


def _hann_sym_f32(n):
    """对称 Hann，float32。"""
    if n == 1:
        return np.ones(1, dtype=F32)
    i = np.arange(n, dtype=F32)
    x = (i * F32(6.2831855)) / F32(n - 1)
    return (F32(0.5) * (F32(1.0) - np.cos(x))).astype(F32)


def _hann_periodic_f32(n):
    """周期 Hann（分母 n），float32。"""
    i = np.arange(n, dtype=F32)
    x = (i * F32(6.2831855)) / F32(n)
    return (F32(0.5) * (F32(1.0) - np.cos(x))).astype(F32)


def gaussian_smooth_nan(x, sigma=SMOOTH_SIGMA, radius=SMOOTH_RADIUS, fill=0.0):
    """NaN 感知高斯平滑（逐语义对齐）：
    - 有效帧: out = sm(x·valid)/sm(valid)（核仍覆盖无效位置，其权重为 0）
    - 无效帧 或 平滑权重 <= 1e-10: out = fill（直接填充，不参与平滑）
    padding 为 symmetric（整样本对称）。"""
    x = np.asarray(x, dtype=np.float64)
    k = np.exp(-(np.arange(-radius, radius + 1, dtype=np.float64) ** 2) / (2.0 * sigma * sigma))
    k /= k.sum()
    valid = np.isfinite(x)
    xv = np.where(valid, x, 0.0)
    w = valid.astype(np.float64)

    def conv(v):
        p = np.pad(v, radius, mode="symmetric")
        return np.convolve(p, k, mode="valid")

    num, den = conv(xv), conv(w)
    out = np.full_like(x, fill)
    ok = valid & (den > 1e-10)
    np.divide(num, den, out=out, where=ok)
    return out


# ---------------------------------------------------------------- LF 声门模型


def lf_params(rd, f0, e0=1.0):
    """Rd + f0 → LF 模型参数 {T0, Tp/T0, Te/T0, Ra, E0}。"""
    if rd < 0.21:
        ra = 1e-6
    elif rd < 2.7:
        ra = (4.8 * rd - 1.0) / 100.0
    else:
        ra = 0.323 / rd
    if rd < 2.7:
        rk = (11.8 * rd + 22.4) / 100.0
        v10 = 0.11 * rd / (1.2 * rk + 0.5) - ra
        v8 = 0.5 * rk / v10
        v9 = rk
    else:
        v7 = 1.0 - 1.0 / (2.17 * rd)
        v8 = 2.0 * (5.96 / (7.96 - 2.0 * v7) + 0.0093552)
        v9 = v7 * v8 - 1.0428
    return (1.0 / f0, 1.0 / v8, (v9 + 1.0) / v8, ra, e0)


def _brent_eps(te_minus_t, ta):
    """解 1 - exp(x*(Te-T)) - Ta*x = 0，区间 [1, 2/(Ta+1e-9)]，Brent 法。"""

    def f(x):
        return 1.0 - np.exp(x * te_minus_t) - ta * x

    a = 1.0
    b = 2.0 / (ta + 1e-9)
    fa, fb = f(a), f(b)
    if fa * fb >= 0.0:
        return 0.5 * (a + b)
    if abs(fa) < abs(fb):
        a, b = b, a
        fa, fb = fb, fa
    c, fc = a, fa
    d = e = b - a
    for _ in range(199):
        if abs(b - a) <= 1e-8 or abs(fb) <= 1e-8:
            break
        if fa != fc and fb != fc:
            # 逆二次插值
            s = (
                a * fb * fc / ((fa - fb) * (fa - fc))
                + b * fa * fc / ((fb - fa) * (fb - fc))
                + c * fa * fb / ((fc - fa) * (fc - fb))
            )
        else:
            s = b - fb * (b - a) / (fb - fa)  # 割线
        # Brent 接受条件（Wikipedia 标准形式）
        cond1 = not ((3 * a + b) / 4 < s < b) if a < b else not (b < s < (3 * a + b) / 4)
        m = 0.5 * (a + b)
        cond2 = abs(s - b) >= 0.5 * abs(b - c)
        cond3 = abs(b - c) < 1e-8
        cond4 = abs(s - b) >= 0.5 * abs(c - d)
        cond5 = abs(c - d) < 1e-8
        if cond1 or cond2 or cond3 or cond4 or cond5:
            s = m
        fs = f(s)
        d, c, fc = c, b, fb
        if fa * fs < 0:
            b, fb = s, fs
        else:
            a, fa = s, fs
        if abs(fa) < abs(fb):
            a, b = b, a
            fa, fb = fb, fa
    return b


def lf_spectrum(params, freqs):
    """LF 声门源模型的幅度谱 |S(f)|（闭式，全 double）。

    params = {T0, Tp/T0, Te/T0, Ra, E0}；freqs 为 Hz 数组。
    公式结构（与二进制逐式对应）：
      O1 = conj(-i·G / D)，D = (α²-w²+wg²) - i·2αw      （共轭变体复除）
      E1 = e^{Te(α-iw)} = e1r + i·e1i
      P1 = O1 · ((u·e1i - sn·w·e1r) + i·(e1r·u + e1i·sn·w + wg))
      R2 = E0·e^{-iwTe} / (-ε·Ta·w² + i·ε²·Ta·w)         （标准复除，分母钳 1e-30）
      P2 = R2 · (v87 + i·v88)                             （回归相因子，按 v139 分支）
      |S| = |P2 - conj(P1)| = hypot(Re(P2)-Re(P1), Im(P2)+Im(P1))
    """
    t0, p1, p2, ra, e0 = params
    if t0 >= 0.00125:
        ts, v148 = t0, 1.0
    else:
        ts, v148 = 0.00125, 1.0 / (t0 * 800.0)
    te = p2 * ts
    ta = ra * ts
    wg = PI / (p1 * ts)
    sn = np.sin(te * wg)
    cs = np.cos(te * wg)

    eps = _brent_eps(te - ts, ta)
    e1 = np.exp(eps * (te - ts))
    v59 = (1.0 - e1) / (ta * eps * eps) + (te - ts) * e1 / (ta * eps)

    # Newton 解 α（从 0 起最多 8 步，每步以 |f'|>=1e-15 为继续条件）：
    #   f(a)  = wg*e^{-a*Te} + A*sn*a^2 + sn*a + (wg^2*sn*A - wg*cs)
    #   f'(a) = -Te*wg*e^{-a*Te} + 2*A*sn*a + sn
    alpha = 0.0
    for _ in range(8):
        ea = np.exp(-alpha * te)
        fp = -te * wg * ea + 2.0 * v59 * sn * alpha + sn
        if abs(fp) < 1e-15:
            break
        fv = wg * ea + v59 * sn * alpha * alpha + sn * alpha + (wg * wg * sn * v59 - wg * cs)
        alpha -= fv / fp

    v62 = -e0 / (np.exp(te * alpha) * sn) if abs(sn) > 1e-15 else 0.0
    u = sn * alpha - wg * cs
    v139 = (1.0 - ta * eps) * eps

    freqs = np.asarray(freqs, dtype=np.float64)
    out = np.zeros(len(freqs))
    for i, fr in enumerate(freqs):
        w = TWO_PI * fr / v148
        c = alpha * alpha - w * w + wg * wg  # Re(D)
        dd = -2.0 * alpha * w  # Im(D)
        d2 = c * c + dd * dd
        o1 = complex(-v62 * dd / d2, v62 * c / d2)  # i·v62/conj(D)
        eat = np.exp(te * alpha)
        e1r = eat * np.cos(te * w)  # e^{Te(α-iw)} 的实部
        e1i = -eat * np.sin(te * w)  # 虚部
        v89 = u * e1i - sn * w * e1r
        v90 = e1r * u + e1i * sn * w + wg
        p1c = o1 * complex(v89, v90)
        # R2 = E0·e^{-iwTe} / (re0 + i·im0)
        re0 = -eps * ta * w * w
        im0 = eps * eps * ta * w
        if np.hypot(re0, im0) < 1e-30:
            re0, im0 = 1e-30, 0.0
        r2 = complex(e0 * np.cos(w * te), -e0 * np.sin(w * te)) / complex(re0, im0)
        if v139 >= 1.0:
            phi = w * (te - ts)
            v87 = (1.0 - np.cos(phi)) * v139
            v88 = -np.sin(phi) * v139 - eps * ta * w
        else:
            v87, v88 = 0.0, -w * ta * eps
        p2c = r2 * complex(v87, v88)
        mag = np.hypot(p2c.real - p1c.real, p2c.imag + p1c.imag)
        out[i] = mag if np.isfinite(mag) else 0.0
    return out


def build_rd_template():
    """64×80 Rd 模板：T[k][j] = (S_{Rd_k}((j+1)·200Hz, f0=200) / (j+1))^2。"""
    grid = np.linspace(RD_GRID_MIN, RD_GRID_MAX, RD_GRID_N)
    freqs = (np.arange(RD_TMPL_LEN, dtype=np.float64) + 1.0) * RD_TMPL_FSTEP
    tmpl = np.zeros((RD_GRID_N, RD_TMPL_LEN))
    for k, rd in enumerate(grid):
        s = lf_spectrum(lf_params(rd, RD_TMPL_F0, 1.0), freqs)
        tmpl[k] = (s / (np.arange(RD_TMPL_LEN) + 1.0)) ** 2
    return grid, tmpl


# ---------------------------------------------------------------- 分析器


class VocalParamAnalyzer:
    def __init__(self, sr=SR, hop=HOP, nfft=NFFT):
        self.sr = sr
        self.hop = hop
        self.nfft = nfft
        self.stft_win = _hann_periodic_f32(nfft)
        self.mel_fb = self._build_mel()
        self.rd_grid, self.rd_template = build_rd_template()
        self._blackman_cache = {}

    # ---- 能量链 ----
    def _build_mel(self):
        """Fant/VOICEBOX mel 刻度三角滤波器组 [128, 1025]，Slaney 面积归一。"""

        def f2m(f):
            f = np.asarray(f, dtype=np.float64)
            return np.where(
                f < 1000.0, f / (200.0 / 3.0), np.log(f / 1000.0) / (np.log(6.4) / 27.0) + 15.0
            )

        def m2f(m):
            m = np.asarray(m, dtype=np.float64)
            return np.where(
                m < 15.0, m * (200.0 / 3.0), np.exp((m - 15.0) * (np.log(6.4) / 27.0)) * 1000.0
            )

        n_bins = self.nfft // 2 + 1
        pts = f2m(MEL_FMIN) + np.arange(N_MELS + 2) * (
            (f2m(MEL_FMAX) - f2m(MEL_FMIN)) / (N_MELS + 1)
        )
        fc = m2f(pts)  # Hz
        bc = fc * self.nfft / self.sr  # bin 单位
        k = np.arange(n_bins, dtype=np.float64)
        h = np.zeros((N_MELS, n_bins))
        for m in range(N_MELS):
            lo, mid, hi = bc[m], bc[m + 1], bc[m + 2]
            if mid > lo:
                up = (k - lo) / (mid - lo)
                dn = (hi - k) / (hi - mid) if hi > mid else 0.0
                h[m] = np.where(
                    (k >= lo) & (k <= mid), up, np.where((k > mid) & (k <= hi), dn, 0.0)
                )
            elif hi > mid:
                h[m] = np.where((k > mid) & (k <= hi), (hi - k) / (hi - mid), 0.0)
            h[m] *= 2.0 / (fc[m + 2] - fc[m])  # Slaney 面积归一（Hz 域）
        return h.astype(F32)

    def energy(self, audio):
        """音频 → 每帧能量 = sqrt(Σ max(mel,1e-8)²)。"""
        x = np.clip(np.asarray(audio, dtype=F32), -1.0, 1.0)
        pad = (self.nfft - self.hop) // 2
        xp = np.pad(x, pad, mode="reflect")
        n_frames = (len(xp) - self.nfft) // self.hop + 1
        idx = np.arange(n_frames)[:, None] * self.hop + np.arange(self.nfft)[None, :]
        frames = xp[idx] * self.stft_win  # float32
        spec = np.fft.rfft(frames.astype(np.float64), axis=1)
        mag = np.hypot(spec.real, spec.imag).astype(F32)  # [F, 1025]
        mel = mag @ self.mel_fb.T  # [F, 128] float32
        m = np.maximum(mel, F32(1e-8)).astype(F32)
        sq = (m * m).astype(F32)
        e = np.sqrt(sq.sum(axis=1, dtype=np.float64))
        return e.astype(F32)

    # ---- 谐波链 ----
    def _blackman(self, n):
        w = self._blackman_cache.get(n)
        if w is None:
            w = _blackman_sym_f32(n)
            self._blackman_cache[n] = w
        return w

    def harmonics(self, audio, f0):
        """每帧逐谐波相关分析。返回 (amps[F,100] f32, phases[F,100] f32, counts[F] int32)。"""
        x = np.asarray(audio, dtype=F32)
        f0 = np.asarray(f0, dtype=F32)
        nf = len(f0)
        amps = np.zeros((nf, MAX_HARMONICS), dtype=F32)
        phases = np.zeros((nf, MAX_HARMONICS), dtype=F32)
        counts = np.zeros(nf, dtype=np.int32)
        dt = self.hop / self.sr
        for f in range(nf):
            f0f = float(f0[f])
            if f0f <= 0.0:
                continue
            period = self.sr / f0f
            nh = min(int(period * 0.5), MAX_HARMONICS)
            if nh <= 0:
                continue
            half = _rint_even(period * 4.0 * 0.5)
            if half <= 0:
                continue
            n = 2 * half
            ctr = _rint_even((f * dt) * self.sr)
            buf = np.zeros(n, dtype=F32)
            s0, s1 = ctr - half, ctr + half
            c0, c1 = max(0, s0), min(len(x), s1)
            if c1 > c0:
                buf[c0 - s0 : c0 - s0 + (c1 - c0)] = x[c0:c1]
            w = self._blackman(n)
            buf = (buf * w).astype(F32)
            wsum = float(w.astype(np.float64).sum())
            # 逐谐波相关（double 累加）
            omega0 = TWO_PI * f0f / self.sr
            hs = np.arange(1, nh + 1)
            theta = np.outer(hs, np.arange(n)) * omega0  # [nh, n]
            re = np.cos(theta) @ buf.astype(np.float64)
            im = np.sin(theta) @ buf.astype(np.float64)
            phi = hs * omega0 * half  # 参考到窗中心
            x3 = re * np.cos(phi) + im * np.sin(phi)
            y3 = re * np.sin(phi) - im * np.cos(phi)
            amps[f, :nh] = (2.0 * np.hypot(x3, y3) / wsum).astype(F32)
            phases[f, :nh] = np.arctan2(y3, x3).astype(F32)
            counts[f] = nh
        return amps, phases, counts

    def residual(self, audio, f0, amps, phases, counts):
        """谐波 OLA 合成后从原音频减去，得残差。

        注意：实测该谐波合成路径输出与输入音频逐位一致
        （该分析器配置下合成为空操作），analyze() 不使用本函数；保留仅供核对。"""
        x = np.asarray(audio, dtype=F32)
        f0 = np.asarray(f0, dtype=F32)
        n2 = 2 * self.hop
        sw = _hann_sym_f32(n2)
        synth = np.zeros(len(x), dtype=F32)
        dt = self.hop / self.sr
        for f in range(min(len(f0), len(counts))):
            f0f = float(f0[f])
            nh = int(counts[f])
            if f0f <= 0.0 or nh == 0:
                continue
            ctr = _rint_even((f * dt) * self.sr)
            delta = ((f * dt) * self.sr - ctr) * (f0f / self.sr) * TWO_PI
            omega0 = TWO_PI * (f0f / self.sr)
            hs = np.arange(1, nh + 1)
            ph = phases[f, :nh].astype(np.float64) - hs * (delta + omega0 * self.hop)
            th = np.outer(np.arange(n2), hs) * omega0 + ph[None, :]
            temp = np.cos(th) @ amps[f, :nh].astype(np.float64)  # double
            contrib = (temp.astype(F32) * sw).astype(F32)
            i0 = ctr - self.hop
            lo, hi = max(0, i0), min(len(x), i0 + n2)
            if hi > lo:
                synth[lo:hi] = (synth[lo:hi] + contrib[lo - i0 : lo - i0 + (hi - lo)]).astype(F32)
        return (x - synth).astype(F32)

    # ---- HNR / Breathiness ----
    def hnr_matrix(self, resid, f0, amps, counts):
        """音频功率谱 vs 谐波能量，24 频带 → [F, 24] float32（无效为 NaN）。

        resid 参数名保留历史叫法；实测该合成在该配置下为恒等，
        应传入原始音频。"""
        f0 = np.asarray(f0, dtype=F32)
        nf = len(f0)
        out = np.full((nf, N_HNR_BANDS), np.nan, dtype=F32)
        nyq = 0.5 * self.sr
        dt = self.hop / self.sr
        edges = HNR_BAND_EDGES
        for f in range(nf):
            f0f = float(f0[f])
            nh = int(counts[f]) if f < len(counts) else 0
            if f0f <= 0.0 or nh == 0:
                continue
            half = _llround(self.sr / f0f * 4.0 * 0.5)
            if half <= 0:
                continue
            n2 = 2 * half
            nfft2 = 1
            while nfft2 < n2:
                nfft2 *= 2
            ctr = _llround(f * dt * self.sr)
            w = self._blackman(n2)
            buf = np.zeros(nfft2, dtype=F32)
            s0 = ctr - half
            c0, c1 = max(0, s0), min(len(resid), s0 + n2)
            if c1 > c0:
                seg = resid[c0:c1].astype(F32) * w[c0 - s0 : c0 - s0 + (c1 - c0)]
                buf[c0 - s0 : c0 - s0 + (c1 - c0)] = seg.astype(F32)
            wsq = float((w.astype(np.float64) ** 2).sum())
            spec = np.fft.rfft(buf.astype(np.float64))
            mag2 = (spec.real**2 + spec.imag**2) / wsq  # [nfft2/2+1]
            nb = nfft2 // 2
            hf = np.arange(1, nh + 1) * f0f  # 谐波频率
            ha = amps[f, :nh].astype(np.float64) ** 2
            for j in range(N_HNR_BANDS):
                lo = edges[j - 1] if j > 0 else 0.0
                hi = nyq if j >= N_HNR_BANDS - 1 else edges[j + 1]
                hp = float(ha[(hf >= lo) & (hf < hi)].sum())
                b0 = int(lo / nyq * nb)
                if b0 < 0:
                    b0 = 0
                b1 = int(hi / nyq * nb) + 1
                if b1 > nb:
                    b1 = nb
                npow = float(mag2[b0:b1].mean()) if b1 > b0 else 1e-21
                if hp > 0.0 and npow > 0.0:
                    out[f, j] = np.float32(10.0 * np.log10(hp / npow))
        return out

    @staticmethod
    def breathiness(hnr):
        """频带 12..16 有效均值 → 1/(1+10^(m/10)) → 高斯平滑 → clamp[0,1]。"""
        nf = hnr.shape[0]
        nb = hnr.shape[1]
        lo, hi = min(12, nb), min(17, nb)
        raw = np.full(nf, np.nan)
        for f in range(nf):
            band = hnr[f, lo:hi].astype(np.float64)
            valid = np.isfinite(band)  # 排除 NaN 与 ±Inf
            if valid.any():
                m = band[valid].mean()
                raw[f] = 1.0 / (1.0 + 10.0 ** (m / 10.0))
        sm = gaussian_smooth_nan(raw, fill=1.0)
        return np.clip(sm, 0.0, 1.0).astype(F32)

    # ---- Rd 估计 ----
    def rd_estimate(self, f0, amps, counts):
        """谐波幅度谱 → LF 模型 Rd 曲线（double[F]）。"""
        f0 = np.asarray(f0, dtype=F32)
        nf = len(f0)
        c_rad = 1.0 * 8.0 / 100.0 / 3.0 / PI / 340.0  # 辐射修正尺度（实测标定）
        # 第 1 遍：谐波能量
        energy = np.zeros(nf)
        for i in range(nf):
            n = int(counts[i])
            f0f = float(f0[i])
            if f0f <= 0.0 or n == 0:
                continue
            n = min(n, _llround(8000.0 / f0f))
            energy[i] = float((amps[i, :n].astype(np.float64) ** 2).sum())
        pos = energy[energy > 0.0]
        thr = float(np.median(pos)) * 0.03 if pos.size else 0.0
        # 第 2 遍：逐帧 IS 模板匹配
        rd = np.zeros(nf)
        tmpl, grid = self.rd_template, self.rd_grid
        for k in range(nf):
            f0f = float(f0[k])
            n = int(counts[k])
            if f0f <= 0.0 or n == 0 or not (thr <= energy[k]):
                continue
            m1 = min(n, _llround(8000.0 / f0f))
            m = np.arange(1, m1 + 1)
            y = m * f0f * TWO_PI * c_rad
            g = y * RAD_A / np.sqrt(y * y + RAD_A2)
            corr = amps[k, :m1].astype(np.float64) / (g + 1e-12)
            x = corr[: min(m1, RD_TMPL_LEN)] ** 2
            mm = len(x)
            # Itakura-Saito 散度匹配
            t = tmpl[:, :mm]
            s = x[0] / (t[:, 0] + 1e-30)
            r = x[None, :] / (t * s[:, None] + 1e-30)
            cost = (r - np.log(r + 1e-30) - 1.0).mean(axis=1) + 1e-30
            i_star = int(np.argmin(cost))
            if i_star == 0 or i_star == RD_GRID_N - 1:
                v = float(i_star)
            else:
                denom = cost[i_star - 1] - 2.0 * cost[i_star] + cost[i_star + 1]
                d = (
                    0.5 * (cost[i_star - 1] - cost[i_star + 1]) / denom
                    if abs(denom) >= 1e-30
                    else -0.0
                )
                v = i_star + d
            j = min(max(int(v), 0), RD_GRID_N - 2)  # C 截断
            z = grid[j] + (v - j) * (grid[j + 1] - grid[j])
            if grid[0] < z < grid[-1]:
                rd[k] = z
        # 第 3 遍：0 值补缺（边缘常数延拓 + 中间线性插值）
        idx = np.nonzero(rd != 0.0)[0]
        if idx.size:
            rd[: idx[0]] = rd[idx[0]]
            rd[idx[-1] + 1 :] = rd[idx[-1]]
            for a, b in zip(idx[:-1], idx[1:]):
                if b > a + 1:
                    rd[a : b + 1] = np.linspace(rd[a], rd[b], b - a + 1)
        # 第 4 遍：3 点自定义平滑
        dt = self.hop / self.sr
        i9 = max(_llround(0.02 / dt), 2)
        h = i9 // 2
        n = nf
        if n >= i9:
            out = rd.copy()
            out[:h] = rd[:i9].mean()
            out[n - h :] = rd[n - i9 :].mean()
            for i in range(h, n - h):
                wseg = rd[i - h : i - h + i9]
                mu = wseg.mean()
                psum = np.maximum(wseg - mu, 0.0).sum()
                out[i] = mu + (float((wseg >= mu).sum()) - float((wseg <= mu).sum())) * psum / (
                    i9 * i9
                )
            rd = out
        return rd

    # ---- 张力 / 假声 ----
    def tension_raw(self, f0, rd):
        """20*log10(g1/((S2/(2*S1))*g2))，double[F]（无效 NaN）。"""
        f0 = np.asarray(f0, dtype=F32)
        c2 = 1.0 * 8.0 / 100.0 / 3.0 / PI / 340.0
        out = np.full(len(f0), np.nan)
        for i in range(len(f0)):
            f0f = float(f0[i])
            if f0f <= 0.0:
                continue
            rdi = rd[i] if i < len(rd) else np.nan
            p = lf_params(rdi, f0f, 1.0)
            s1, s2 = lf_spectrum(p, [f0f, 2.0 * f0f])
            r = s2 / (2.0 * s1)
            y1 = TWO_PI * f0f * c2
            y2 = TWO_PI * (2.0 * f0f) * c2
            g1 = y1 * RAD_A / np.sqrt(y1 * y1 + RAD_A2)
            g2 = y2 * RAD_A / np.sqrt(y2 * y2 + RAD_A2)
            out[i] = 20.0 * np.log10(g1 / ((r + 1e-30) * g2))
        return out

    @staticmethod
    def falsetto_raw(f0, rd):
        """-log2(Rd)，double[F]（无效 NaN）。"""
        f0 = np.asarray(f0, dtype=F32)
        out = np.full(len(rd), np.nan)
        for i in range(len(rd)):
            if i >= len(f0) or not np.isfinite(rd[i]) or f0[i] <= 0.0:
                continue
            out[i] = -np.log2(rd[i])
        return out

    @staticmethod
    def _boxcox(x, exps, norm):
        """带符号 Box-Cox：((|x|+1)^e - 1)/(±e) / norm，float32。"""
        x = np.asarray(x, dtype=F32)
        out = np.empty_like(x)
        for i, v in enumerate(x):
            vf = float(v)
            neg = vf < 0.0
            e = exps[1] if neg else exps[0]
            div = -e if neg else e
            out[i] = F32((pow(abs(vf) + 1.0, e) - 1.0) / div / norm)
        return out

    # ---- 总入口 ----
    def analyze(self, audio, f0):
        """返回 (energy, breathiness, tension, falsetto)，各 [F] float32。"""
        audio = np.asarray(audio, dtype=F32)
        f0 = np.asarray(f0, dtype=F32)

        ch_energy = self.energy(audio)

        amps, phases, counts = self.harmonics(audio, f0)
        # 注：此处有谐波 OLA 合成 + 残差，但实测其输出
        # 与输入音频逐位一致（该配置下合成为空操作），HNR 实际用原始音频。
        hnr = self.hnr_matrix(audio, f0, amps, counts)
        ch_breath = self.breathiness(hnr)

        rd = self.rd_estimate(f0, amps, counts)
        t_raw = self.tension_raw(f0, rd)
        t_sm = gaussian_smooth_nan(t_raw.astype(F32).astype(np.float64))
        t_sm = t_sm.astype(F32)
        for j in range(min(len(f0), len(t_sm))):
            if f0[j] <= 1.0:
                t_sm[j] = 0.0
        ch_tension = self._boxcox(t_sm, TENSION_EXP, TENSION_NORM)

        f_raw = self.falsetto_raw(f0, rd)
        f_sm = gaussian_smooth_nan(f_raw.astype(F32).astype(np.float64)).astype(F32)
        ch_falsetto = self._boxcox(f_sm, FALSETTO_EXP, FALSETTO_NORM)

        return ch_energy, ch_breath, ch_tension, ch_falsetto
