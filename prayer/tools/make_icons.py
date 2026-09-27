"""앱 아이콘: 검정 바탕 위 러블리한 3D 핑크 하트(금빛·은빛이 도는 무광 메탈 느낌) + 'mantra' 글씨.

사용법:  pip install numpy pillow  →  python3 prayer/tools/make_icons.py
결과물:  prayer/icons/icon-192.png, icon-512.png, apple-touch-icon.png (180), icon-1024.png (원본 크기),
         icon-maskable-512.png (안드로이드가 동그랗게 잘라도 하트가 잘리지 않도록 여백을 더 둔 것)

글씨체: Yellowtail (Apache License 2.0, tools/fonts/ 에 라이선스 포함) — 굵고 매끈한 필기체.
하트는 make_objects.py 와 같은 방식(레이마칭)으로 3D 계산해 그린다.
"""
import os

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

from make_objects import length, render, rot, smin

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "..", "icons")
FONT = os.path.join(HERE, "fonts", "Yellowtail-Regular.ttf")
S = 1024


def sd_round_cone(p, a, b, r1, r2):
    """두 끝의 굵기가 다른 둥근 원뿔 (Inigo Quilez의 식)."""
    ba = b - a
    l2 = ba @ ba
    rr = r1 - r2
    a2 = l2 - rr * rr
    il2 = 1.0 / l2
    pa = p - a
    y = pa @ ba
    z = y - l2
    q = pa * l2 - np.outer(y, ba)
    x2 = np.sum(q * q, axis=1)
    y2 = y * y * l2
    z2 = z * z * l2
    k = np.sign(rr) * rr * rr * x2
    d_tip = np.sqrt(x2 + z2) * il2 - r2
    d_top = np.sqrt(x2 + y2) * il2 - r1
    d_mid = (np.sqrt(x2 * a2 * il2) + y * rr) * il2 - r1
    return np.where(np.sign(z) * a2 * z2 > k, d_tip, np.where(np.sign(y) * a2 * y2 < k, d_top, d_mid))


HEART_R = rot(-14, 8, 4)  # 살짝 비스듬히 돌려 입체감


def heart_scene(p):
    q = p @ HEART_R
    flat = 0.72  # 앞뒤로 약간 납작한 통통한 하트
    q = q * np.array([1, 1, 1 / flat])
    tip = np.array([0, -1.0, 0])
    left = sd_round_cone(q, np.array([-0.47, 0.3, 0]), tip, 0.6, 0.07)
    right = sd_round_cone(q, np.array([0.47, 0.3, 0]), tip, 0.6, 0.07)
    d = smin(left, right, 0.18) * flat
    return d, np.zeros(len(p), int)


def heart_shade(pos, n, view, mat):
    # 무광 메탈: 아주 고운 결로 반사를 살짝 흐리게
    rng = np.random.default_rng(3)
    jitter = rng.normal(size=n.shape) * 0.03
    nb = n + jitter
    nb /= np.linalg.norm(nb, axis=-1, keepdims=True)
    r = 2 * np.sum(nb * view, axis=-1, keepdims=True) * nb - view
    ry = r[:, 1:2]
    # 스튜디오 조명 반사: 위는 은빛이 도는 밝은 분홍, 가운데는 진한 분홍, 아래는 금빛 반사
    top = np.array([1.0, 0.86, 0.93])
    mid = np.array([0.93, 0.36, 0.6])
    low = np.array([1.0, 0.72, 0.62])
    t_up = np.clip(ry, 0, 1)
    t_dn = np.clip(-ry, 0, 1)
    env = mid * (1 - t_up - t_dn) + top * t_up + low * t_dn
    base = np.array([0.97, 0.5, 0.7])
    L = np.array([-0.45, 0.7, 0.55])
    L /= np.linalg.norm(L)
    diff = np.clip(nb @ L, 0, 1)[:, None]
    h = L + view
    h /= np.linalg.norm(h, axis=-1, keepdims=True)
    spec = np.clip(np.sum(nb * h, axis=-1), 0, 1)[:, None]
    satin = spec ** 14 * 0.55 + spec ** 90 * 0.6          # 넓은 은은한 광택 + 작고 또렷한 반짝임
    fres = (1 - np.clip(np.sum(nb * view, axis=-1), 0, 1))[:, None] ** 2.5
    col = base * (0.25 + 0.55 * diff) * 0.6 + env * 0.55
    col += satin * np.array([1.0, 0.93, 0.8])              # 금빛이 살짝 도는 하이라이트
    col += fres * np.array([0.85, 0.85, 0.95]) * 0.45       # 가장자리 은빛
    return col


def background():
    yy, xx = np.mgrid[0:S, 0:S] / S
    d = np.sqrt((xx - 0.5) ** 2 + (yy - 0.52) ** 2)
    glow = np.clip(1 - d / 0.55, 0, 1) ** 2.2
    rgb = np.stack([glow * 0.42, glow * 0.1, glow * 0.24], axis=-1)  # 하트 뒤 은은한 분홍 빛
    return Image.fromarray((rgb * 255).astype(np.uint8), "RGB").convert("RGBA")


def lettering(text="mantra"):
    """하트 위 글씨: 은빛~연분홍 그라디언트 + 은은한 빛과 그림자."""
    font = ImageFont.truetype(FONT, int(S * 0.25))
    layer = Image.new("L", (S, S), 0)
    dr = ImageDraw.Draw(layer)
    box = dr.textbbox((0, 0), text, font=font)
    w, h = box[2] - box[0], box[3] - box[1]
    dr.text(((S - w) / 2 - box[0], S * 0.5 - h / 2 - box[1] - S * 0.02), text, font=font, fill=255)
    layer = layer.rotate(8, resample=Image.BICUBIC, center=(S / 2, S / 2))
    yy = np.linspace(0, 1, S)[:, None]
    grad = np.concatenate([np.broadcast_to(c, (S, S))[..., None] for c in (
        255 - 10 * yy, 250 - 40 * yy, 255 - 25 * yy)], axis=-1)  # 흰색 → 연분홍
    fill = Image.fromarray(grad.astype(np.uint8), "RGB").convert("RGBA")
    fill.putalpha(layer)
    shadow = Image.new("RGBA", (S, S), (120, 10, 60, 0))
    shadow.putalpha(layer.filter(ImageFilter.MaxFilter(9)).filter(ImageFilter.GaussianBlur(S * 0.01)).point(lambda v: min(255, int(v * 1.1))))
    glow = Image.new("RGBA", (S, S), (255, 230, 245, 0))
    glow.putalpha(layer.filter(ImageFilter.GaussianBlur(S * 0.02)).point(lambda v: int(v * 0.35)))
    out = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    out.alpha_composite(glow)
    out.alpha_composite(shadow, (int(S * 0.006), int(S * 0.012)))
    out.alpha_composite(fill)
    return out


def main():
    os.makedirs(OUT, exist_ok=True)
    heart = render(heart_scene, heart_shade, size=(S, S), extent=3.1, center=np.array([0, -0.12, 0]), pitch_deg=0, ss=1)
    icon = background()
    icon.alpha_composite(heart)
    icon.alpha_composite(lettering())
    icon = icon.convert("RGB")
    icon.save(os.path.join(OUT, "icon-1024.png"), optimize=True)
    for name, size in (("icon-512.png", 512), ("icon-192.png", 192), ("apple-touch-icon.png", 180)):
        icon.resize((size, size), Image.LANCZOS).save(os.path.join(OUT, name), optimize=True)
        print(name)
    # 안드로이드 '마스크' 아이콘: 가운데 80% 원 안에 모든 내용이 들어가야 하므로 72%로 줄여 가운데에
    small = icon.resize((int(S * 0.72), int(S * 0.72)), Image.LANCZOS)
    mask = background().convert("RGB")
    mask.paste(small, ((S - small.width) // 2, (S - small.height) // 2))
    mask.resize((512, 512), Image.LANCZOS).save(os.path.join(OUT, "icon-maskable-512.png"), optimize=True)
    print("icon-maskable-512.png")


if __name__ == "__main__":
    main()
