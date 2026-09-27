"""염주 구슬 이미지(PNG, 투명 배경)를 만든다.

사용법:  pip install numpy pillow  →  python3 prayer/tools/make_beads.py
결과물:  prayer/images/bead.png  (구슬)   prayer/images/head.png  (모주: 큰 구슬)

■ 진짜 사진으로 바꾸기
  prayer/images/src/ 폴더에 bead.jpg(또는 .png), head.jpg 를 넣고 다시 실행하면
  사진 가운데를 동그랗게 잘라 구슬 이미지로 쓴다. 구슬이 사진 한가운데에 꽉 차게 찍힌 사진이 좋다.
  사진은 반드시 자유 이용이 가능한 것(직접 찍은 사진, Pixabay, Unsplash 등)만 쓸 것.

■ 사진이 없으면: 나무 구슬을 3D로 계산해 그린다(나뭇결, 광택, 그림자 포함).
"""
import glob
import os

import numpy as np
from PIL import Image, ImageFilter

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "..", "images")
SRC = os.path.join(OUT, "src")
SIZE = 160  # 결과 이미지 크기(px). 구슬은 가운데 80% 크기
SS = 3      # 가장자리를 매끄럽게 하기 위한 확대 배율


def value_noise(shape, scale, rng, stretch=1):
    """부드러운 잡음 (나뭇결의 불규칙함용). stretch>1이면 가로로 길게 늘어진 결."""
    small = rng.random((max(2, shape[0] // scale), max(2, shape[1] // (scale * stretch))))
    img = Image.fromarray((small * 255).astype(np.uint8)).resize((shape[1], shape[0]), Image.BICUBIC)
    return np.asarray(img, dtype=np.float64) / 255.0


def render(dark, light, grain_freq, seed, gloss):
    rng = np.random.default_rng(seed)
    n = SIZE * SS
    c = np.linspace(-1.25, 1.25, n)
    x, y = np.meshgrid(c, c)
    r2 = x ** 2 + y ** 2
    inside = r2 <= 1.0
    z = np.sqrt(np.clip(1 - r2, 0, 1))

    # 나뭇결: 구멍 방향(가로축)을 따라 흐르는 결. 나무 중심이 구슬 밖에 있어 결이 휘어 보인다
    warp = value_noise((n, n), n // 4, rng) * 0.25 + value_noise((n, n), n // 24, rng, stretch=6) * 0.05
    ring = np.sqrt((y - 2.4) ** 2 + (z * 0.8 + 0.4) ** 2) + warp
    grain = 0.5 + 0.5 * np.sin(2 * np.pi * grain_freq * ring)
    grain = grain ** 1.6
    fine = value_noise((n, n), 3, rng, stretch=20) * 0.18  # 가로로 가는 잔결
    t = np.clip(grain * 0.7 + fine, 0, 1)[..., None]
    base = np.array(dark) * (1 - t) + np.array(light) * t

    # 빛: 왼쪽 위에서
    L = np.array([-0.45, -0.6, 0.66])
    L /= np.linalg.norm(L)
    nx, ny, nz = x, y, z
    diffuse = np.clip(nx * L[0] + ny * L[1] + nz * L[2], 0, 1)
    H = L + np.array([0, 0, 1.0])
    H /= np.linalg.norm(H)
    spec = np.clip(nx * H[0] + ny * H[1] + nz * H[2], 0, 1) ** 90 * gloss * 0.7
    soft = np.clip(nx * H[0] + ny * H[1] + nz * H[2], 0, 1) ** 10 * gloss * 0.12
    rim = (1 - z) ** 3 * 0.35  # 가장자리가 어두워지는 효과
    shade = 0.22 + 0.9 * diffuse - rim
    color = base * shade[..., None] + (spec + soft)[..., None] * 255
    # 구멍이 뚫린 양 끝이 살짝 들어가 보이도록 (가로축 끝부분을 약간 어둡게)
    hole = np.exp(-(((np.abs(x) - 1.0) / 0.12) ** 2) - (y / 0.22) ** 2) * 0.55
    color *= (1 - hole)[..., None]

    rgba = np.zeros((n, n, 4))
    rgba[..., :3] = np.clip(color, 0, 255)
    rgba[..., 3] = inside * 255
    img = Image.fromarray(rgba.astype(np.uint8), "RGBA")
    return add_shadow(img.resize((SIZE, SIZE), Image.LANCZOS))


def add_shadow(img):
    """구슬 아래 오른쪽에 옅은 그림자를 깐다."""
    a = img.split()[3]
    shadow = Image.new("RGBA", img.size, (0, 0, 0, 0))
    sh_alpha = a.point(lambda v: int(v * 0.5)).filter(ImageFilter.GaussianBlur(SIZE * 0.04))
    shadow.putalpha(sh_alpha)
    canvas = Image.new("RGBA", img.size, (0, 0, 0, 0))
    canvas.alpha_composite(shadow, (int(SIZE * 0.03), int(SIZE * 0.05)))
    canvas.alpha_composite(img)
    return canvas


def from_photo(path):
    """사진 가운데를 동그랗게 잘라 구슬 이미지로."""
    img = Image.open(path).convert("RGBA")
    s = min(img.size)
    left, top = (img.width - s) // 2, (img.height - s) // 2
    img = img.crop((left, top, left + s, top + s)).resize((SIZE * SS, SIZE * SS), Image.LANCZOS)
    n = SIZE * SS
    c = np.linspace(-1.25, 1.25, n)
    x, y = np.meshgrid(c, c)
    mask = Image.fromarray(((x ** 2 + y ** 2 <= 1.0) * 255).astype(np.uint8))
    # 사진 전체가 원 안(80%)에 들어가도록 축소 후 가운데 배치
    inner = img.resize((int(n / 1.25), int(n / 1.25)), Image.LANCZOS)
    canvas = Image.new("RGBA", (n, n), (0, 0, 0, 0))
    canvas.paste(inner, ((n - inner.width) // 2, (n - inner.height) // 2))
    canvas.putalpha(mask)
    print(f"  사진 사용: {os.path.relpath(path, OUT)}")
    return add_shadow(canvas.resize((SIZE, SIZE), Image.LANCZOS))


def make(name, **wood):
    photos = sorted(glob.glob(os.path.join(SRC, name + ".*")))
    img = from_photo(photos[0]) if photos else render(**wood)
    path = os.path.join(OUT, name + ".png")
    img.save(path, optimize=True)
    print(f"{name}.png  {os.path.getsize(path) / 1024:.0f} KB")


def main():
    os.makedirs(OUT, exist_ok=True)
    # 구슬: 따뜻한 갈색 단향목 느낌 / 모주: 짙은 자단 느낌
    make("bead", dark=(128, 74, 38), light=(222, 156, 92), grain_freq=5.5, seed=21, gloss=0.6)
    make("head", dark=(96, 36, 20), light=(176, 84, 46), grain_freq=4.0, seed=108, gloss=0.85)


if __name__ == "__main__":
    main()
