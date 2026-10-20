"""Paint a character's expressions pixel by pixel from base.png and face.json.

    python -m pixel_diary.faces cast/claude

face.json (coordinates are sprite pixels, boxes are inclusive x0, y0, x1, y1):
{
  "skin": [251, 220, 203],                  colour that erased eye pixels become
  "keep": [[243, 135, 111]],                colours inside an eye box that must stay (hair over the eyes)
  "eyes": [{"box": [14, 26, 22, 35], "line_y": 31}, {"box": [31, 25, 39, 34], "line_y": 30}],
  "mouth": [26, 38],                        left pixel of a two-pixel mouth
  "blush": [[15, 35], [16, 35], [36, 35], [37, 35]],
  "mark": [46, 19],                         top-left of the sweat / anger / zzz / ? marks
  "faces": {"p": {"eyes": "half", "mouth": "frown", "extras": ["blush"]}}   extra expressions
}
Every expression X also gets a talking twin Xt with the mouth open.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image

LINE = (28, 22, 29, 255)
MOUTH, MOUTH_IN = (160, 62, 74, 255), (112, 34, 46, 255)
BLUSH = (246, 160, 152, 255)
SWEAT, SWEAT_HI = (150, 214, 255, 255), (238, 250, 255, 255)
ANGER = (232, 64, 64, 255)
MARK_INK = (90, 120, 220, 255)

DEFAULT_FACES = {
    "n": {"eyes": "open", "mouth": "smile"},
    "b": {"eyes": "closed", "mouth": "smile"},
    "h": {"eyes": "happy", "mouth": "grin"},
    "s": {"eyes": "open", "mouth": "flat", "extras": ["sweat"]},
}


def _put(a, pts, c):
    h, w, _ = a.shape
    for x, y in pts:
        if 0 <= x < w and 0 <= y < h:
            a[y, x] = c


def _clear_eyes(a, spec, top_only=None):
    skin = tuple(spec["skin"]) + (255,)
    keep = {tuple(k) for k in spec.get("keep", [])}
    for eye in spec["eyes"]:
        x0, y0, x1, y1 = eye["box"]
        if top_only is not None:
            y1 = top_only(eye)
        for y in range(y0, y1 + 1):
            for x in range(x0, x1 + 1):
                p = a[y, x]
                if p[3] and tuple(int(v) for v in p[:3]) not in keep:
                    a[y, x] = skin


def eyes(a, spec, kind):
    if kind == "open":
        return
    if kind == "closed":
        _clear_eyes(a, spec)
        for eye in spec["eyes"]:
            x0, _, x1, _ = eye["box"]
            _put(a, [(x, eye["line_y"]) for x in range(x0 + 1, x1)], LINE)
    elif kind == "happy":
        _clear_eyes(a, spec)
        for eye in spec["eyes"]:
            x0, _, x1, _ = eye["box"]
            cx, half = (x0 + x1) / 2, max(1.0, (x1 - x0) / 2 - 1)
            pts = []
            for x in range(x0 + 1, x1):
                d = min(1.0, abs(x - cx) / half)
                pts.append((x, eye["line_y"] + 1 - round(2 * (1 - d))))
            _put(a, pts, LINE)
    elif kind == "half":
        lid = {}
        for eye in spec["eyes"]:
            x0, y0, x1, y1 = eye["box"]
            lid[id(eye)] = y0 + int((y1 - y0) * 0.45)
        _clear_eyes(a, spec, top_only=lambda e: lid[id(e)])
        for eye in spec["eyes"]:
            x0, _, x1, _ = eye["box"]
            _put(a, [(x, lid[id(eye)]) for x in range(x0, x1 + 1)], LINE)
    else:
        raise ValueError(f"unknown eyes {kind}")


def mouth(a, spec, kind):
    mx, my = spec["mouth"]
    m = {
        "smile": ([(mx - 1, my - 1), (mx + 2, my - 1), (mx, my), (mx + 1, my)], []),
        "open": ([(mx, my - 1), (mx + 1, my - 1), (mx - 1, my), (mx + 2, my), (mx, my + 1), (mx + 1, my + 1)], [(mx, my), (mx + 1, my)]),
        "grin": ([(x, my - 1) for x in range(mx - 2, mx + 4)], [(x, my) for x in range(mx - 1, mx + 3)]),
        "flat": ([(x, my) for x in range(mx - 1, mx + 3)], []),
        "frown": ([(mx - 1, my + 1), (mx, my), (mx + 1, my), (mx + 2, my + 1)], []),
        "wavy": ([(mx - 2, my), (mx - 1, my - 1), (mx, my), (mx + 1, my - 1), (mx + 2, my), (mx + 3, my - 1)], []),
        "o": ([(mx, my - 1), (mx + 1, my - 1), (mx - 1, my), (mx + 2, my), (mx, my + 1), (mx + 1, my + 1)], []),
        "shout": ([(x, my - 2) for x in range(mx - 1, mx + 3)] + [(mx - 2, y) for y in range(my - 1, my + 2)]
                  + [(mx + 3, y) for y in range(my - 1, my + 2)] + [(x, my + 2) for x in range(mx - 1, mx + 3)],
                  [(x, y) for x in range(mx - 1, mx + 3) for y in range(my - 1, my + 2)]),
    }
    if kind not in m:
        raise ValueError(f"unknown mouth {kind}")
    edge, inner = m[kind]
    _put(a, edge, MOUTH)
    _put(a, inner, MOUTH_IN)


def extras(a, spec, names):
    mx, my = spec.get("mark", [0, 0])
    ink = tuple(spec.get("mark_ink", MARK_INK[:3])) + (255,)
    for name in names:
        if name == "blush":
            _put(a, [tuple(p) for p in spec.get("blush", [])], BLUSH)
        elif name == "sweat":
            _put(a, [(mx + 2, my), (mx + 1, my + 1), (mx + 2, my + 1), (mx, my + 2), (mx + 1, my + 2), (mx + 2, my + 2), (mx + 3, my + 2),
                     (mx, my + 3), (mx + 1, my + 3), (mx + 2, my + 3), (mx + 3, my + 3), (mx + 1, my + 4), (mx + 2, my + 4)], SWEAT)
            _put(a, [(mx + 1, my + 2), (mx + 1, my + 1)], SWEAT_HI)
        elif name == "anger":
            _put(a, [(mx, my), (mx + 1, my), (mx, my + 1), (mx + 3, my), (mx + 4, my), (mx + 4, my + 1),
                     (mx, my + 3), (mx, my + 4), (mx + 1, my + 4), (mx + 4, my + 3), (mx + 4, my + 4), (mx + 3, my + 4)], ANGER)
        elif name == "zzz":
            for k, (ox, oy) in enumerate(((0, 4), (3, 2), (6, 0))):
                x, y = mx + ox, my + oy
                _put(a, [(x, y), (x + 1, y), (x + 2, y), (x + 1, y + 1), (x, y + 2), (x + 1, y + 2), (x + 2, y + 2)], ink)
        elif name == "q":
            _put(a, [(mx, my), (mx + 1, my), (mx + 2, my), (mx + 3, my + 1), (mx + 2, my + 2), (mx + 1, my + 3), (mx + 1, my + 5)], ink)
        else:
            raise ValueError(f"unknown extra {name}")


def paint(base: np.ndarray, spec: dict, face: dict, talking: bool) -> np.ndarray:
    a = base.copy()
    eyes(a, spec, face.get("eyes", "open"))
    m = face.get("mouth", "smile")
    mouth(a, spec, ("shout" if m == "shout" else "open") if talking else m)
    extras(a, spec, face.get("extras", []))
    return a


def build(cast_dir: str | Path, preview: str | None = None) -> list[str]:
    d = Path(cast_dir)
    spec = json.loads((d / "face.json").read_text(encoding="utf-8"))
    base = np.asarray(Image.open(d / "base.png").convert("RGBA")).copy()
    faces = {**DEFAULT_FACES, **spec.get("faces", {})}
    made, strip = [], []
    for name, f in faces.items():
        for talking in (False, True):
            key = name + ("t" if talking else "")
            img = paint(base, spec, f, talking)
            Image.fromarray(img, "RGBA").save(d / f"{key}.png")
            made.append(key)
            if not talking:
                strip.append(img)
    if preview:
        y0, y1 = spec.get("preview_rows", [0, base.shape[0] // 2])
        rows = [np.pad(s[y0:y1], ((2, 2), (2, 2), (0, 0))) for s in strip]
        cat = np.concatenate(rows, axis=1)
        big = Image.fromarray(cat, "RGBA").resize((cat.shape[1] * 8, cat.shape[0] * 8), Image.NEAREST)
        bg = Image.new("RGBA", big.size, (245, 234, 219, 255))
        bg.alpha_composite(big)
        bg.convert("RGB").save(preview)
    return made


if __name__ == "__main__":
    out = build(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else None)
    print("faces:", " ".join(out))
