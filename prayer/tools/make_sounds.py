"""목탁·싱잉볼 소리를 코드로 합성해 MP3로 저장한다 (저작권 걱정 없는 자체 제작 소리).

사용법:  pip install lameenc  →  python3 prayer/tools/make_sounds.py
결과물:  prayer/sounds/moktak.mp3, bowl.mp3, bowl-5m.mp3, bowl-15m.mp3, bowl-30m.mp3

bowl-Nm.mp3 는 '싱잉볼 한 번 + 무음'으로 정확히 N분 길이인 파일이다.
이 파일을 반복 재생하면 코드 타이머 없이도 N분마다 종이 울리므로,
화면이 꺼져 브라우저가 코드를 멈춰도 소리는 계속 난다.
"""
import math
import os
import random

import lameenc

OUT = os.path.join(os.path.dirname(__file__), "..", "sounds")
random.seed(108)


def encode(samples, rate, path, kbps):
    peak = max(abs(s) for s in samples) or 1.0
    scale = 0.89 * 32767 / peak
    pcm = bytearray()
    for s in samples:
        v = int(s * scale)
        pcm += v.to_bytes(2, "little", signed=True)
    enc = lameenc.Encoder()
    enc.set_bit_rate(kbps)
    enc.set_in_sample_rate(rate)
    enc.set_channels(1)
    enc.set_quality(2)
    data = enc.encode(bytes(pcm)) + enc.flush()
    with open(path, "wb") as f:
        f.write(data)
    print(f"{os.path.basename(path):14s} {len(samples) / rate:8.1f}s {len(data) / 1024:8.0f} KB")


def bowl(rate, seconds=16.0):
    """싱잉볼: 비조화 배음 + 살짝 어긋난 쌍으로 '웅웅' 맥놀이를 만든다."""
    f0 = 196.0
    # (배음 비율, 크기, 소리가 줄어드는 시간(초), 맥놀이 폭 Hz)
    partials = [(1.0, 1.0, 7.0, 0.9), (2.71, 0.55, 4.5, 1.6), (5.12, 0.22, 2.4, 2.3), (8.19, 0.08, 1.2, 3.1)]
    n = int(rate * seconds)
    out = [0.0] * n
    for ratio, amp, tau, beat in partials:
        f = f0 * ratio
        for fa in (f - beat / 2, f + beat / 2):
            w = 2 * math.pi * fa / rate
            ph = random.random() * 2 * math.pi
            for i in range(n):
                t = i / rate
                out[i] += 0.5 * amp * math.exp(-t / tau) * math.sin(w * i + ph)
    attack = int(rate * 0.004)
    for i in range(attack):
        out[i] *= i / attack
    fade = int(rate * 1.0)
    for i in range(fade):
        out[n - fade + i] *= 1 - i / fade
    # 채로 친 순간의 짧은 '틱'
    for i in range(int(rate * 0.012)):
        out[i] += 0.08 * (random.random() * 2 - 1) * (1 - i / (rate * 0.012))
    return out


def moktak(rate, seconds=0.45):
    """목탁: 빠르게 사라지는 속 빈 나무 공명 + 두드리는 소리."""
    modes = [(420.0, 0.6, 0.09), (880.0, 1.0, 0.055), (1510.0, 0.35, 0.025), (2630.0, 0.15, 0.012)]
    n = int(rate * seconds)
    out = [0.0] * n
    for f, amp, tau in modes:
        w = 2 * math.pi * f / rate
        for i in range(n):
            out[i] += amp * math.exp(-(i / rate) / tau) * math.sin(w * i)
    click = int(rate * 0.006)
    prev = 0.0
    for i in range(click):
        prev = 0.6 * prev + 0.4 * (random.random() * 2 - 1)
        out[i] += 0.9 * prev * (1 - i / click)
    attack = int(rate * 0.001)
    for i in range(attack):
        out[i] *= i / attack
    return out


def main():
    os.makedirs(OUT, exist_ok=True)
    encode(moktak(44100), 44100, os.path.join(OUT, "moktak.mp3"), 96)
    encode(bowl(44100), 44100, os.path.join(OUT, "bowl.mp3"), 96)
    # 타이머용 긴 파일: 용량을 줄이려고 16kHz·32kbps 모노로 저장
    rate = 16000
    ring = bowl(rate)
    for minutes in (5, 15, 30):
        total = rate * 60 * minutes
        encode(ring + [0.0] * (total - len(ring)), rate, os.path.join(OUT, f"bowl-{minutes}m.mp3"), 32)


if __name__ == "__main__":
    main()
