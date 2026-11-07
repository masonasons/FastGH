#!/usr/bin/env python3
"""Draws FastGH's icon (the G mark the Python app drew for its tray icon) as
res/fastgh.ico (Windows) and res/mac/FastGH.icns (macOS). Needs Pillow; on macOS
also iconutil. Run again only if the design changes."""
import os, shutil, subprocess, sys, tempfile
from PIL import Image, ImageDraw

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")

def draw(size):
    scale = 4  # draw large and shrink, for smooth edges
    s = size * scale
    img = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([0, 0, s - 1, s - 1], radius=s // 5, fill=(36, 41, 46, 255))
    w = max(scale * 2, s // 9)
    m = s // 5
    # A circle open at the upper right, with the G's bar
    d.arc([m, m, s - m, s - m], start=-20, end=320, fill=(255, 255, 255, 255), width=w)
    d.line([s // 2, s // 2, s - m, s // 2], fill=(255, 255, 255, 255), width=w)
    return img.resize((size, size), Image.LANCZOS)

def main():
    sizes = [16, 24, 32, 48, 64, 128, 256]
    draw(256).save(os.path.join(ROOT, "res", "fastgh.ico"), sizes=[(n, n) for n in sizes])
    if sys.platform == "darwin" and shutil.which("iconutil"):
        tmp = tempfile.mkdtemp()
        iconset = os.path.join(tmp, "FastGH.iconset")
        os.makedirs(iconset)
        for n in [16, 32, 128, 256, 512]:
            draw(n).save(os.path.join(iconset, f"icon_{n}x{n}.png"))
            draw(n * 2).save(os.path.join(iconset, f"icon_{n}x{n}@2x.png"))
        subprocess.check_call(["iconutil", "-c", "icns", iconset, "-o",
                               os.path.join(ROOT, "res", "mac", "FastGH.icns")])
        shutil.rmtree(tmp)

if __name__ == "__main__":
    main()
