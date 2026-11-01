"""Generate assets/icon.ico (+ PNG) with Pillow - a microphone on a blue rounded square (no fonts needed)."""
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parent.parent
S = 512


def draw() -> Image.Image:
    im = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    for y in range(S):                                     # vertical gradient
        t = y / S
        d.line([(0, y), (S, y)], fill=(int(40 + 30 * t), int(90 + 40 * t), int(255 - 60 * t), 255))
    mask = Image.new("L", (S, S), 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, S - 1, S - 1], radius=110, fill=255)
    im.putalpha(mask)
    d = ImageDraw.Draw(im)
    w = (255, 255, 255, 255)
    d.rounded_rectangle([192, 90, 320, 290], radius=64, fill=w)                    # capsule
    d.arc([140, 170, 372, 372], start=0, end=180, fill=w, width=26)                 # holder
    d.rectangle([243, 372, 269, 420], fill=w)                                       # stem
    d.rounded_rectangle([190, 414, 322, 440], radius=13, fill=w)                    # base
    return im


if __name__ == "__main__":
    out = ROOT / "assets"
    out.mkdir(exist_ok=True)
    im = draw()
    im.save(out / "icon.png")
    im.save(out / "icon.ico", sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    print("icon written")
