"""목탁·싱잉볼 이미지(PNG, 투명 배경)를 3D로 계산해 그린다.

사용법:  pip install numpy pillow  →  python3 prayer/tools/make_objects.py
결과물:  prayer/images/moktak.png, prayer/images/bowl.png

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
def moktak_scene(p):
    body = sd_ellipsoid(p, np.array([0, 0, 0.0]), np.array([1.0, 0.86, 0.92]))
    handle = sd_torus_z(p, np.array([0, 0.74, -0.18]), 0.36, 0.085)
    body = smin(body, handle, 0.12)
    slit = sd_box(p, np.array([0, -0.12, 0.85]), np.array([0.74, 0.06, 0.4]))
    slit = smin(slit, sd_ellipsoid(p, np.array([0, -0.12, 0.55]), np.array([0.78, 0.07, 0.5])), 0.05)
    body = np.maximum(body, -slit)
    stick = sd_capsule(p, np.array([1.05, -0.62, 0.62]), np.array([1.95, 0.25, 0.25]), 0.05)
    head = sd_ellipsoid(p, np.array([1.02, -0.66, 0.64]), np.array([0.15, 0.13, 0.13]))
    mallet = smin(stick, head, 0.04)
    d = np.minimum(body, mallet)
    mat = np.where(mallet < body, 1, 0)
    # 입 안쪽(어두운 공간)은 따로 표시
    inside = (np.abs(p[:, 1] + 0.12) < 0.1) & (p[:, 2] > 0.3) & (np.abs(p[:, 0]) < 0.74) & (mat == 0)
    mat = np.where(inside, 2, mat)
    return d, mat


def moktak_shade(pos, n, view, mat):
    g = noise3(pos * np.array([1, 3.5, 1]), 3.0, 5)
    grain = 0.5 + 0.5 * np.sin(pos[:, 1] * 22 + g * 3.2)
    lacquer = np.array([0.42, 0.13, 0.06]) * (1 - grain[:, None] * 0.35) + np.array([0.12, 0.03, 0.01]) * grain[:, None] * 0.3
    light_wood = np.array([0.78, 0.58, 0.36]) * (0.85 + 0.15 * grain[:, None])
    base = np.where((mat == 1)[:, None], light_wood, lacquer)
    base = np.where((mat == 2)[:, None], np.array([0.05, 0.015, 0.01]), base)
    gloss = np.where(mat == 1, 0.15, np.where(mat == 2, 0.0, 0.55))
    return lighting(n, view, base, gloss, 55)


# ───────── 싱잉볼 ─────────
BOWL_C = np.array([0, 0.55, 0.0])


def bowl_scene(p):
    outer = sd_sphere(p, BOWL_C, 1.0)
    inner = sd_sphere(p, BOWL_C, 0.93)
    shell = np.maximum(outer, -inner)
    shell = np.maximum(shell, p[:, 1] - 0.42)          # 위쪽 테두리
    shell = np.maximum(shell, -(p[:, 1] + 0.33))       # 평평한 바닥
    cushion = sd_ellipsoid(p, np.array([0, -0.5, 0.0]), np.array([1.2, 0.24, 1.2]))
    stick = sd_capsule(p, np.array([-1.1, -0.36, 0.95]), np.array([0.35, -0.3, 1.18]), 0.065)
    d = np.minimum(np.minimum(shell, cushion), stick)
    mat = np.where(d == shell, 0, np.where(d == cushion, 1, 2))
    inner_side = (length(p - BOWL_C) < 0.965) & (mat == 0)
    mat = np.where(inner_side, 3, mat)
    return d, mat


def bowl_shade(pos, n, view, mat):
    # 두드려 만든 금속 표면의 작은 울퉁불퉁함
    bump = noise3(pos, 18.0, 9)[:, None] * 0.06
    nb = n + bump
    nb /= np.linalg.norm(nb, axis=-1, keepdims=True)
    refl = 2 * np.sum(nb * view, axis=-1, keepdims=True) * nb - view
    env = np.clip(0.5 + 0.5 * refl[:, 1], 0, 1)[:, None]   # 위는 밝고 아래는 어두운 주변 반사
    bronze = np.array([0.95, 0.66, 0.3])
    metal = bronze * (0.25 + 0.9 * env) + np.array([0.9, 0.75, 0.5]) * env ** 6 * 0.5
    band = (np.abs(pos[:, 1] - 0.3) < 0.035) | (np.abs(pos[:, 1] - 0.22) < 0.012)  # 테두리 아래 장식 줄
    metal = np.where(band[:, None], metal * 0.6, metal)
    inner_metal = bronze * (0.2 + 0.5 * env) * 0.8
    # 방석: 짙은 빨강 천 + 금색 테두리 줄
    ring = np.abs(np.sqrt(pos[:, 0] ** 2 + pos[:, 2] ** 2) - 0.95) < 0.05
    cloth = np.where(ring[:, None], np.array([0.85, 0.62, 0.25]), np.array([0.55, 0.08, 0.1]))
    cloth = cloth * (0.9 + 0.1 * noise3(pos, 40, 3)[:, None])
    wood = np.array([0.6, 0.4, 0.22])
    base = np.select([(mat == 0)[:, None], (mat == 3)[:, None], (mat == 1)[:, None]], [metal, inner_metal, cloth], wood)
    gloss = np.select([mat == 0, mat == 3, mat == 1], [0.9, 0.4, 0.05], 0.2)
    shin = np.where((mat == 0) | (mat == 3), 80, 12)
    col = np.zeros_like(base)
    for s in np.unique(shin):
        m = shin == s
        col[m] = lighting(nb[m], view[m] if view.ndim > 1 else view, base[m], gloss[m], s, (1.0, 0.9, 0.7))
    metal_mask = ((mat == 0) | (mat == 3))[:, None]
    return np.where(metal_mask, base * 0.7 + col * 0.45, col)


def main():
    os.makedirs(OUT, exist_ok=True)
    jobs = [
        ("moktak", moktak_scene, moktak_shade, dict(size=(720, 600), extent=4.6, center=np.array([0.35, -0.05, 0]), pitch_deg=18)),
        ("bowl", bowl_scene, bowl_shade, dict(size=(720, 560), extent=3.4, center=np.array([-0.1, -0.1, 0]), pitch_deg=28)),
    ]
    for name, scene, shade, cam in jobs:
        path = os.path.join(OUT, name + ".png")
        photos = sorted(glob.glob(os.path.join(SRC, name + ".png")))
        if photos:
            shutil.copy(photos[0], path)
            print(f"  사진 사용: src/{name}.png")
        else:
            img = render(scene, shade, **cam)
            with_shadow(img).save(path, optimize=True)
        print(f"{name}.png  {os.path.getsize(path) / 1024:.0f} KB")


if __name__ == "__main__":
    main()
