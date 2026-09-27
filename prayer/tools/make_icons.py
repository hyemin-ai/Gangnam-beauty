"""앱 아이콘(염주 팔찌 그림) PNG를 만든다. 외부 라이브러리 없이 동작.

사용법:  python3 prayer/tools/make_icons.py
결과물:  prayer/icons/icon-192.png, icon-512.png, apple-touch-icon.png
"""
import math
import os
import struct
import zlib

OUT = os.path.join(os.path.dirname(__file__), "..", "icons")
BEADS = 21


def shapes(size):
    """(중심x, 중심y, 반지름, 채움 여부) 목록. 좌표는 0~1 비율."""
    ring = 0.27
    items = []
    for i in range(BEADS):
        a = -math.pi / 2 + (i + 0.5) * 2 * math.pi / BEADS
        items.append((0.5 + ring * math.cos(a), 0.52 + ring * math.sin(a), 0.032, False))
    items.append((0.5, 0.52 - ring, 0.048, True))  # 모주(가장 큰 구슬)
    return items


def render(size, ss=4):
    items = shapes(size)
    stroke = 0.011
    rows = []
    for y in range(size):
        row = bytearray([0])
        for x in range(size):
            ink = 0
            for sy in range(ss):
                for sx in range(ss):
                    px = (x + (sx + 0.5) / ss) / size
                    py = (y + (sy + 0.5) / ss) / size
                    for cx, cy, r, filled in items:
                        d = math.hypot(px - cx, py - cy)
                        if (filled and d <= r) or (not filled and abs(d - r) <= stroke):
                            ink += 1
                            break
            v = 255 - round(255 * ink / (ss * ss) * 0.92)
            row += bytes((v, v, v))
        rows.append(bytes(row))
    raw = b"".join(rows)

    def chunk(tag, data):
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data))

    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", size, size, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b""))


def main():
    os.makedirs(OUT, exist_ok=True)
    for name, size in (("icon-192.png", 192), ("icon-512.png", 512), ("apple-touch-icon.png", 180)):
        with open(os.path.join(OUT, name), "wb") as f:
            f.write(render(size))
        print(name)


if __name__ == "__main__":
    main()
