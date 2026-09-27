"""목탁·싱잉볼 이미지(PNG, 투명 배경)를 3D로 계산해 그린다.

사용법:  pip install numpy pillow  →  python3 prayer/tools/make_objects.py
결과물:  prayer/images/moktak.png (목탁), mallet.png (목탁 채), bowl.png (싱잉볼), felt-mallet.png (싱잉볼 채)

■ 진짜 사진으로 바꾸기
  prayer/images/src/ 에 moktak.png / bowl.png (배경이 투명한 PNG)를 넣고 다시 실행하면 그 사진을 쓴다.
  배경이 있는 사진(jpg)은 그대로 쓰면 네모난 배경이 보이므로, 배경을 지운 PNG가 좋다.

원리: 물체의 모양을 '거리 함수'로 정의하고, 화면의 각 점에서 광선을 쏘아 물체에 닿는 곳을 찾은 뒤
      (레이마칭) 빛·광택·나뭇결·금속 반사를 계산한다.
"""
import glob
import os
import shutil

import numpy as np
from PIL import Image, ImageFilter

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "..", "images")
SRC = os.path.join(OUT, "src")


# ───────── 거리 함수 도구 ─────────
def length(v):
    return np.sqrt(np.sum(v * v, axis=-1))


def sd_sphere(p, c, r):
    return length(p - c) - r


def sd_ellipsoid(p, c, r):
    q = (p - c) / r
    k0 = length(q)
    k1 = length(q / r)
    return k0 * (k0 - 1.0) / np.maximum(k1, 1e-6)


def sd_box(p, c, b):
    q = np.abs(p - c) - b
    return length(np.maximum(q, 0)) + np.minimum(np.max(q, axis=-1), 0)


def sd_capsule(p, a, b, r):
    pa, ba = p - a, b - a
    h = np.clip(np.sum(pa * ba, axis=-1) / np.dot(ba, ba), 0, 1)
    return length(pa - ba * h[:, None]) - r


def sd_torus_z(p, c, R, r):
    """z축을 향해 선 고리(도넛)."""
    q = p - c
    d = np.sqrt(q[:, 0] ** 2 + q[:, 1] ** 2) - R
    return np.sqrt(d ** 2 + q[:, 2] ** 2) - r


def smin(a, b, k):
    h = np.clip(0.5 + 0.5 * (b - a) / k, 0, 1)
    return b * (1 - h) + a * h - k * h * (1 - h)


def noise3(p, freq, seed):
    """가벼운 3D 잡음 (사인파 겹치기)."""
    rng = np.random.default_rng(seed)
    v = np.zeros(len(p))
    for i in range(5):
        d = rng.normal(size=3)
        d /= np.linalg.norm(d)
        f = freq * (1.9 ** i)
        v += np.sin(p @ d * f + rng.uniform(0, 6.28)) / (1.6 ** i)
    return v / 2.2


# ───────── 공통 렌더러 ─────────
def render(scene, shade, size, extent, center, pitch_deg, ss=2):
    """정사영 카메라로 장면을 그려 RGBA 이미지를 돌려준다."""
    W, H = size[0] * ss, size[1] * ss
    p = np.radians(pitch_deg)
    fwd = np.array([0, -np.sin(p), -np.cos(p)])
    up = np.array([0, np.cos(p), -np.sin(p)])
    right = np.array([1.0, 0, 0])
    ys, xs = np.mgrid[0:H, 0:W]
    u = (xs / W - 0.5) * extent
    v = -(ys / H - 0.5) * extent * H / W
    origin = center - fwd * 6 + u.reshape(-1, 1) * right + v.reshape(-1, 1) * up
    t = np.zeros(len(origin))
    hit = np.zeros(len(origin), bool)
    alive = np.ones(len(origin), bool)
    for _ in range(140):
        idx = np.nonzero(alive)[0]
        if not len(idx):
            break
        pos = origin[idx] + fwd * t[idx, None]
        d = scene(pos)[0]
        t[idx] += d * 0.9
        done = d < 1e-3
        hit[idx[done]] = True
        alive[idx[done | (t[idx] > 12)]] = False
    rgba = np.zeros((len(origin), 4))
    idx = np.nonzero(hit)[0]
    pos = origin[idx] + fwd * t[idx, None]
    e = 1e-3
    n = np.stack([scene(pos + np.array(o))[0] - scene(pos - np.array(o))[0]
                  for o in ([e, 0, 0], [0, e, 0], [0, 0, e])], axis=1)
    n /= np.maximum(length(n)[:, None], 1e-9)
    mat = scene(pos)[1]
    # 틈새가 어두워지는 효과(AO)
    ao = np.ones(len(pos))
    for k in range(1, 6):
        h = 0.03 * k
        ao -= (h - scene(pos + n * h)[0]) * (0.5 ** k) * 9
    ao = np.clip(ao, 0.25, 1)
    rgba[idx, :3] = shade(pos, n, -fwd, mat) * ao[:, None]
    rgba[idx, 3] = 1
    img = rgba.reshape(H, W, 4)
    out = Image.fromarray((np.clip(img, 0, 1) * 255).astype(np.uint8), "RGBA")
    return out.resize(size, Image.LANCZOS)


LIGHT = np.array([-0.5, 0.75, 0.55])
LIGHT /= np.linalg.norm(LIGHT)
RIM = np.array([0.7, 0.3, -0.6])
RIM /= np.linalg.norm(RIM)


def lighting(n, view, base, gloss, shininess, spec_color=(1, 1, 1)):
    diff = np.clip(n @ LIGHT, 0, 1)
    fill = np.clip(n @ np.array([0.6, 0.2, 0.8]), 0, 1) * 0.25
    h = LIGHT + view
    h /= np.linalg.norm(h, axis=-1, keepdims=True)
    spec = np.clip(np.sum(n * h, axis=-1), 0, 1) ** shininess * gloss
    fres = (1 - np.clip(np.sum(n * view, axis=-1), 0, 1)) ** 3
    rim = np.clip(n @ RIM, 0, 1) ** 2 * 0.35 + fres * 0.15  # 뒤쪽의 따뜻한 테두리 빛
    col = base * (0.18 + 0.85 * diff + fill)[:, None]
    col += spec[:, None] * np.array(spec_color)
    col += rim[:, None] * np.array([1.0, 0.75, 0.45])
    return col


def with_shadow(img, squash=0.22, strength=0.55, drop=0.0):
    """물체 아래에 동그랗고 부드러운 그림자를 깐다."""
    a = np.asarray(img.split()[3], dtype=np.float64) / 255
    cols = np.nonzero(a.max(axis=0) > 0.1)[0]
    rows = np.nonzero(a.max(axis=1) > 0.1)[0]
    w = cols[-1] - cols[0]
    cx = (cols[0] + cols[-1]) / 2
    bottom = rows[-1] - drop * img.height
    sh = Image.new("L", img.size, 0)
    yy, xx = np.mgrid[0:img.height, 0:img.width]
    ell = ((xx - cx) / (w * 0.5)) ** 2 + ((yy - bottom) / (w * 0.5 * squash)) ** 2
    sh = Image.fromarray((np.clip(1 - ell, 0, 1) * 255 * strength).astype(np.uint8)).filter(ImageFilter.GaussianBlur(img.width * 0.02))
    base = Image.new("RGBA", img.size, (0, 0, 0, 0))
    base.putalpha(sh)
    base.alpha_composite(img)
    return base


# ───────── 목탁 ─────────
# 스님들이 손에 들고 치는 목탁 모양: 달걀처럼 둥근 몸통이 뒤로 갈수록 가늘어져 납작한 고리 손잡이가 되고,
# 앞쪽 옆면에 길게 갈라진 틈과 그 끝의 둥근 구멍이 있다. 채는 따로 그려서 칠 때마다 움직인다.
def rot(yaw, pitch, roll=0.0):
    y, x, z = np.radians([yaw, pitch, roll])
    Ry = np.array([[np.cos(y), 0, np.sin(y)], [0, 1, 0], [-np.sin(y), 0, np.cos(y)]])
    Rx = np.array([[1, 0, 0], [0, np.cos(x), -np.sin(x)], [0, np.sin(x), np.cos(x)]])
    Rz = np.array([[np.cos(z), -np.sin(z), 0], [np.sin(z), np.cos(z), 0], [0, 0, 1]])
    return Ry @ Rx @ Rz


MOKTAK_R = rot(28, 0, -12)  # 비스듬히 놓인 모습


def moktak_cut(q):
    """앞쪽 옆면의 긴 틈 + 끝의 둥근 구멍."""
    slit = sd_box(q, np.array([-0.95, 0.02, 0.75]), np.array([0.5, 0.035, 0.5]))
    hole = np.sqrt((q[:, 0] + 0.5) ** 2 + (q[:, 1] - 0.02) ** 2) - 0.2
    hole = np.maximum(hole, 0.25 - q[:, 2])
    return np.minimum(slit, hole)


def moktak_scene(p):
    q = p @ MOKTAK_R
    head = sd_ellipsoid(q, np.array([-0.45, 0, 0.0]), np.array([0.95, 0.78, 0.8]))
    neck = sd_ellipsoid(q, np.array([0.45, -0.02, 0.0]), np.array([0.62, 0.42, 0.44]))
    body = smin(head, neck, 0.35)
    # 납작한 고리 손잡이 (수평으로 누운 도넛을 위아래로 눌러 놓은 모양)
    hq = q - np.array([1.25, -0.06, 0.0])
    ring = np.sqrt((np.sqrt(hq[:, 0] ** 2 + hq[:, 2] ** 2) - 0.36) ** 2 + (hq[:, 1] / 0.75) ** 2) - 0.12
    body = smin(body, ring * 0.8, 0.12)
    cut = moktak_cut(q)
    d = np.maximum(body, -cut)
    mat = np.where(cut < 0.02, 2, 0)
    return d, mat


def moktak_shade(pos, n, view, mat):
    q = pos @ MOKTAK_R
    g = noise3(q * np.array([0.6, 2.5, 2.5]), 2.2, 5)
    grain = 0.5 + 0.5 * np.sin((q[:, 1] + 0.35 * q[:, 2]) * 38 + g * 4.5)
    grain = grain ** 4
    wood = np.array([0.78, 0.36, 0.15]) * (1 - 0.45 * grain[:, None]) + np.array([0.08, 0.02, 0.0]) * grain[:, None]
    wood = wood * (0.92 + 0.12 * noise3(q, 9.0, 11)[:, None])
    base = np.where((mat == 2)[:, None], np.array([0.06, 0.02, 0.01]), wood)
    gloss = np.where(mat == 2, 0.0, 0.45)
    return lighting(n, view, base, gloss, 45)


def mallet_scene(p):
    """목탁 채: 한쪽 끝의 동그란 머리(치는 부분) + 가는 목 + 손잡이 쪽으로 굵어지는 막대."""
    x = p[:, 0]
    h = np.clip((x + 0.8) / 1.95, 0, 1)
    r = 0.045 + 0.04 * h
    xc = np.clip(x, -0.8, 1.15)
    stick = np.sqrt((x - xc) ** 2 + p[:, 1] ** 2 + p[:, 2] ** 2) - r
    knob = sd_ellipsoid(p, np.array([-0.98, 0, 0]), np.array([0.15, 0.13, 0.13]))
    d = smin(stick, knob, 0.06) * 0.7
    return d, np.zeros(len(p), int)


def mallet_shade(pos, n, view, mat):
    g = noise3(pos * np.array([0.3, 4, 4]), 3.0, 21)
    grain = 0.5 + 0.5 * np.sin(pos[:, 1] * 40 + g * 3)
    base = np.array([0.93, 0.8, 0.6]) * (0.93 + 0.07 * grain[:, None])
    return lighting(n, view, base, 0.12, 20)


def crop(img, pad=4):
    box = img.getbbox()
    return img.crop((max(0, box[0] - pad), max(0, box[1] - pad), min(img.width, box[2] + pad), min(img.height, box[3] + pad)))


# ───────── 싱잉볼 ─────────
# 망치로 두드려 만든 광택 나는 황동 볼을 옆에서 본 모습. 깊고 둥근 몸통, 살짝 안으로 말린 입구,
# 두드린 자국과 군데군데 어두운 얼룩. 펠트 머리 채는 따로 그려서 칠 때마다 움직인다.
BOWL_C = np.array([0, 0.3, 0.0])


def bowl_scene(p):
    outer = sd_ellipsoid(p, BOWL_C, np.array([1.1, 0.95, 1.1]))
    inner = sd_ellipsoid(p, BOWL_C, np.array([1.03, 0.89, 1.03]))
    shell = np.maximum(outer, -inner)
    shell = np.maximum(shell, p[:, 1] - 0.27)          # 입구
    shell = np.maximum(shell, -(p[:, 1] + 0.6))       # 평평한 바닥
    lip = sd_torus_z(p[:, [0, 2, 1]], np.array([0, 0, 0.27]), 1.05, 0.03)  # 입구 테두리
    d = smin(shell, lip, 0.02)
    inside = sd_ellipsoid(p, BOWL_C, np.array([1.065, 0.92, 1.065])) < 0
    mat = np.where(inside, 3, 0)
    return d, mat


def bowl_shade(pos, n, view, mat):
    # 망치로 두드린 자국: 여러 겹 잡음으로 표면을 살짝 울퉁불퉁하게
    bump = np.stack([noise3(pos, 11.0, 9 + i) for i in range(3)], axis=1) * 0.06
    nb = n + bump
    nb /= np.linalg.norm(nb, axis=-1, keepdims=True)
    refl = 2 * np.sum(nb * view, axis=-1, keepdims=True) * nb - view
    ry = refl[:, 1:2]
    # 주변 반사: 위쪽 밝은 빛, 수평선 근처 따뜻한 띠, 아래는 어두움 → 광택 금속 느낌
    env = 0.55 + 0.35 * np.clip(ry, -1, 1) + np.exp(-((ry - 0.1) / 0.18) ** 2) * 0.35 + 0.15 * noise3(refl, 3.0, 50)[:, None]
    brass = np.array([1.0, 0.72, 0.3])
    metal = brass * (0.18 + 0.95 * env) + np.array([1.0, 0.93, 0.78]) * np.clip(ry - 0.55, 0, 1) * 1.4
    # 군데군데 어두운 얼룩 (바닥 쪽에 더 많이)
    spots = noise3(pos, 6.0, 31) + noise3(pos, 14.0, 32) * 0.3 - 0.25 * pos[:, 1]
    stain = np.clip((spots - 0.6) * 3, 0, 1)[:, None]
    metal = metal * (1 - 0.4 * stain)
    inner = brass * (0.15 + 0.6 * env) * 0.85
    base = np.where((mat == 3)[:, None], inner, metal)
    col = lighting(nb, view, base * 0.35, np.where(mat == 3, 0.4, 1.0), 90, (1.0, 0.92, 0.75))
    return (base * 0.8 + col * 0.6) * np.array([1.08, 1.0, 0.9])


def felt_mallet_scene(p):
    """싱잉볼 채: 매끈한 나무 막대 + 동그란 펠트 머리."""
    x = p[:, 0]
    xc = np.clip(x, -0.75, 1.2)
    stick = np.sqrt((x - xc) ** 2 + p[:, 1] ** 2 + p[:, 2] ** 2) - 0.055
    head = sd_sphere(p, np.array([-0.95, 0, 0]), 0.2)
    d = np.minimum(stick, head)
    return d, np.where(head < stick, 1, 0)


def felt_mallet_shade(pos, n, view, mat):
    fuzz = noise3(pos, 60.0, 41)[:, None]
    felt = np.array([0.62, 0.6, 0.56]) * (0.85 + 0.2 * fuzz)
    wood = np.array([0.9, 0.74, 0.52]) * (0.95 + 0.05 * noise3(pos * np.array([0.3, 5, 5]), 3, 42)[:, None])
    base = np.where((mat == 1)[:, None], felt, wood)
    return lighting(n, view, base, np.where(mat == 1, 0.0, 0.18), 25)


def main():
    os.makedirs(OUT, exist_ok=True)
    jobs = [
        ("moktak", moktak_scene, moktak_shade, dict(size=(720, 560), extent=3.9, center=np.array([0.15, 0.0, 0]), pitch_deg=22)),
        ("mallet", mallet_scene, mallet_shade, dict(size=(640, 140), extent=2.5, center=np.array([0.08, 0.0, 0]), pitch_deg=15)),
        ("bowl", bowl_scene, bowl_shade, dict(size=(720, 500), extent=2.8, center=np.array([0, -0.1, 0]), pitch_deg=14)),
        ("felt-mallet", felt_mallet_scene, felt_mallet_shade, dict(size=(640, 160), extent=2.6, center=np.array([0.1, 0.0, 0]), pitch_deg=15)),
    ]
    for name, scene, shade, cam in jobs:
        path = os.path.join(OUT, name + ".png")
        photos = sorted(glob.glob(os.path.join(SRC, name + ".png")))
        if photos:
            shutil.copy(photos[0], path)
            print(f"  사진 사용: src/{name}.png")
        else:
            img = render(scene, shade, **cam)
            img = crop(img) if "mallet" in name else with_shadow(img)  # 채는 움직이므로 그림자 없이 딱 맞게 자름
            img.save(path, optimize=True)
        print(f"{name}.png  {os.path.getsize(path) / 1024:.0f} KB")


if __name__ == "__main__":
    main()
