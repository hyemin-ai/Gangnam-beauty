"""앱에서 쓰는 소리를 만들어 MP3로 저장한다.

사용법:  pip install numpy lameenc miniaudio  →  python3 prayer/tools/make_sounds.py
결과물:  prayer/sounds/click.mp3    염주 넘길 때 짧은 '딸깍'
         prayer/sounds/moktak.mp3   목탁
         prayer/sounds/bowl.mp3     싱잉볼
         prayer/sounds/bowl-5m.mp3, bowl-15m.mp3, bowl-30m.mp3   타이머용 (싱잉볼 한 번 + 무음)

■ 진짜 녹음으로 바꾸기
  prayer/sounds/src/ 폴더에 bowl / moktak / click 이름으로 녹음 파일(.mp3 .wav .flac .ogg)을 넣고
  이 스크립트를 다시 실행하면, 합성 소리 대신 그 녹음을 다듬어(앞 무음 자르기·음량 맞추기) 사용한다.
  예) prayer/sounds/src/bowl.mp3  →  bowl.mp3와 타이머 파일 3개가 모두 이 녹음으로 바뀐다.
  녹음 파일은 반드시 CC0 등 자유 이용이 가능한 것만 쓸 것 (Pixabay, Freesound의 CC0 등).

■ 녹음이 없으면: 실제 악기의 떨림 방식(배음 비율, 맥놀이, 채가 닿는 순간, 공간 울림)을
  흉내 내어 합성한다. 직접 만든 소리라 저작권 문제가 없다.
"""
import glob
import os

import lameenc
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "..", "sounds")
SRC = os.path.join(OUT, "src")
SR = 44100


# ───────── 공통 도구 ─────────
def modes(freqs, amps, taus, seconds, beats=None, phases=None, sr=SR):
    """감쇠하는 사인파(모드)들의 합. beats가 있으면 각 모드를 살짝 어긋난 두 개로 나눠 '웅웅' 맥놀이를 만든다."""
    t = np.arange(int(sr * seconds)) / sr
    out = np.zeros_like(t)
    rng = np.random.default_rng(len(freqs))
    for i, (f, a, tau) in enumerate(zip(freqs, amps, taus)):
        ph = rng.uniform(0, 2 * np.pi) if phases is None else phases[i]
        env = a * np.exp(-t / tau)
        if beats:
            b = beats[i]
            out += 0.5 * env * (np.sin(2 * np.pi * (f - b / 2) * t + ph) + np.sin(2 * np.pi * (f + b / 2) * t + ph * 1.7))
        else:
            out += env * np.sin(2 * np.pi * f * t + ph)
    return out


def pulse(ms, sr=SR):
    """채가 닿는 순간의 힘: 반쪽 사인 모양. 부드러운 채일수록 길다."""
    n = max(2, int(sr * ms / 1000))
    return np.sin(np.pi * np.arange(n) / n)


def strike(response, ms):
    """모드 응답을 채의 타격 모양과 곱해(컨볼루션) 실제로 두드린 소리처럼 만든다."""
    p = pulse(ms)
    return np.convolve(response, p / p.sum())[: len(response)]


def lowpass(x, cutoff, sr=SR):
    a = np.exp(-2 * np.pi * cutoff / sr)
    y = np.empty_like(x)
    acc = 0.0
    for i, v in enumerate(x):  # 짧은 신호에만 사용
        acc = (1 - a) * v + a * acc
        y[i] = acc
    return y


def room(x, seconds, mix, sr=SR, seed=7):
    """방 안의 울림(잔향). 감쇠하는 잡음을 임펄스 응답으로 써서 좌우 약간 다르게 섞는다."""
    rng = np.random.default_rng(seed)
    n = int(sr * seconds)
    t = np.arange(n) / sr
    outs = []
    for ch in range(2):
        noise = rng.standard_normal(n)
        # 높은 소리는 빨리, 낮은 소리는 천천히 사라지도록 두 층으로
        smooth = np.convolve(noise, np.ones(12) / 12, mode="same")
        ir = smooth * np.exp(-6.9 * t / seconds) + 0.35 * noise * np.exp(-6.9 * t / (seconds * 0.35))
        ir[: int(sr * (0.008 + 0.004 * ch))] = 0  # 첫 반사음까지의 짧은 틈
        ir /= np.sqrt(np.sum(ir ** 2))
        m = len(x) + n - 1
        size = 1 << (m - 1).bit_length()
        wet = np.fft.irfft(np.fft.rfft(x, size) * np.fft.rfft(ir, size), size)[: len(x)]
        outs.append((1 - mix) * x + mix * wet * 0.5)
    return np.stack(outs, axis=1)


def fade_out(x, seconds, sr=SR):
    n = min(len(x), int(sr * seconds))
    env = np.ones(len(x))
    env[-n:] = np.linspace(1, 0, n) ** 2
    return x * (env[:, None] if x.ndim == 2 else env)


def load_recording(name):
    """src 폴더의 녹음 파일을 읽어 (길이, 2) 배열로. 없으면 None."""
    files = sorted(glob.glob(os.path.join(SRC, name + ".*")))
    if not files:
        return None
    import miniaudio
    d = miniaudio.decode_file(files[0], output_format=miniaudio.SampleFormat.FLOAT32, nchannels=2, sample_rate=SR)
    x = np.frombuffer(d.samples, dtype=np.float32).reshape(-1, 2).astype(np.float64)
    level = np.abs(x).max(axis=1)
    loud = np.nonzero(level > level.max() * 0.03)[0]  # 앞뒤 무음 자르기 (약 -30dB)
    start = max(0, loud[0] - int(SR * 0.005))
    end = min(len(x), loud[-1] + int(SR * 0.3))
    x = x[start:end]
    x[: int(SR * 0.003)] *= np.linspace(0, 1, int(SR * 0.003))[:, None]
    print(f"  녹음 사용: {os.path.relpath(files[0], OUT)}")
    return fade_out(x, min(1.0, len(x) / SR / 4))


def encode(x, path, kbps, sr=SR, mono=False):
    if x.ndim == 1:
        x = np.stack([x, x], axis=1)
    if mono:
        x = x.mean(axis=1, keepdims=True)
    x = x / (np.abs(x).max() or 1) * 0.89
    pcm = (x * 32767).astype("<i2").tobytes()
    enc = lameenc.Encoder()
    enc.set_bit_rate(kbps)
    enc.set_in_sample_rate(sr)
    enc.set_channels(x.shape[1])
    enc.set_quality(2)
    data = enc.encode(pcm) + enc.flush()
    with open(path, "wb") as f:
        f.write(data)
    print(f"{os.path.basename(path):14s} {len(x) / sr:8.1f}s {len(data) / 1024:8.0f} KB")


# ───────── 소리 합성 ─────────
def bowl():
    """싱잉볼: 실제 볼에서 측정되는 비조화 배음 비율(약 1 : 2.8 : 5.3 : 8.5 : 12.2),
    긴 여운, 각 배음이 둘로 갈라져 생기는 맥놀이, 펠트 채로 친 부드러운 타격, 방 울림."""
    f0 = 221.0
    ratios = [1.0, 2.81, 5.34, 8.57, 12.25, 16.4]
    amps = [1.0, 0.62, 0.30, 0.12, 0.05, 0.02]
    taus = [11.0, 6.5, 3.4, 1.7, 0.9, 0.45]
    beats = [0.75, 1.9, 3.2, 4.4, 5.6, 7.0]
    freqs = [f0 * r for r in ratios]
    sec = 26.0
    # 좌우 채널의 맥놀이 위상을 다르게 해서 소리가 공간에서 천천히 도는 느낌
    left = modes(freqs, amps, taus, sec, beats, phases=[0.0, 1.1, 2.3, 0.4, 1.9, 2.8])
    right = modes(freqs, amps, taus, sec, beats, phases=[1.4, 0.2, 0.9, 2.6, 0.7, 1.3])
    x = np.stack([left, right], axis=1)
    x = np.stack([strike(x[:, 0], 5.0), strike(x[:, 1], 5.0)], axis=1)
    # 채가 금속에 닿는 순간의 '팅' (아주 짧은 높은 배음)
    ting = modes([f0 * 21.3, f0 * 27.9], [0.05, 0.03], [0.06, 0.03], sec)
    x += ting[:, None]
    wet = room(x.mean(axis=1), 3.2, 0.28)
    return fade_out(wet, 4.0)


def moktak():
    """목탁: 속이 빈 나무통의 공명(낮은 '톡')과 나무 몸통의 짧은 떨림, 나무 채가 닿는 순간,
    치는 순간 음이 살짝 내려가는 나무 특유의 성질, 법당 같은 짧은 울림."""
    sec = 0.9
    t = np.arange(int(SR * sec)) / SR
    glide = 1 + 0.035 * np.exp(-t / 0.012)  # 처음 몇 ms 동안 음이 살짝 높다가 내려옴
    parts = [(612.0, 1.0, 0.085), (1290.0, 0.45, 0.032), (2170.0, 0.22, 0.016), (3380.0, 0.12, 0.009), (318.0, 0.35, 0.05)]
    x = np.zeros_like(t)
    for f, a, tau in parts:
        phase = 2 * np.pi * np.cumsum(f * glide) / SR
        x += a * np.exp(-t / tau) * np.sin(phase)
    x = strike(x, 0.9)
    rng = np.random.default_rng(3)
    knock = rng.standard_normal(int(SR * 0.004)) * np.exp(-np.arange(int(SR * 0.004)) / (SR * 0.0012))
    x[: len(knock)] += 0.25 * lowpass(knock, 3500)
    return fade_out(room(x, 0.9, 0.18), 0.25)


def click():
    """염주 '딸깍': 단단한 나무 구슬끼리 한 번 부딪히는 아주 짧은 소리 (약 0.05초)."""
    sec = 0.06
    x = strike(modes([2600.0, 4100.0, 6200.0], [1.0, 0.55, 0.25], [0.0045, 0.003, 0.002], sec), 0.25)
    return fade_out(room(x, 0.08, 0.05), 0.02)


def main():
    os.makedirs(OUT, exist_ok=True)
    rec_click = load_recording("click")
    encode(rec_click if rec_click is not None else click(), os.path.join(OUT, "click.mp3"), 96)
    rec_moktak = load_recording("moktak")
    encode(rec_moktak if rec_moktak is not None else moktak(), os.path.join(OUT, "moktak.mp3"), 128)
    rec_bowl = load_recording("bowl")
    ring = rec_bowl if rec_bowl is not None else bowl()
    encode(ring, os.path.join(OUT, "bowl.mp3"), 128)
    # 타이머용 긴 파일: 종 한 번 + 무음으로 정확히 N분. 용량을 줄이려고 22kHz·40kbps 모노
    sr = 22050
    mono = ring.mean(axis=1) if ring.ndim == 2 else ring
    mono = mono[:: SR // sr]
    for minutes in (5, 15, 30):
        total = sr * 60 * minutes
        track = np.zeros(total)
        track[: min(len(mono), total)] = mono[:total]
        encode(track, os.path.join(OUT, f"bowl-{minutes}m.mp3"), 40, sr=sr, mono=True)


if __name__ == "__main__":
    main()
