"""Build a HyperFrames project from an episode JSON, optionally render it.

    python -m pixel_diary build episodes/day0.json --out work/day0 [--render out.mp4]
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

from PIL import Image

from . import audio, scenes
from .plan import EpisodeError, load, plan as make_plan

PKG = Path(__file__).resolve().parent
REPO = PKG.parent
HF_VERSION = "0.8.181"

THEMES = {
    "night": {"bg": "#0a1729", "bg2": "#0e2643", "win": "#122a4c", "edge": "#eaf3ff", "edge-light": "#eaf3ff", "rim": "#35609a",
              "ring": "#071121", "drop": "rgba(0,0,0,0.35)", "bar": "#081325", "bar-ink": "#f3f7ff", "ink": "#f3f7ff",
              "dim": "#bccde6", "accent": "#ff8a5c", "on-accent": "#13203a", "aqua": "#62e3cf", "paper": "#f5eadb",
              "paper-rim": "#d9c3a6", "floor": "#ead8c2", "floor-edge": "#dcc3a4", "shadow": "#d2b894", "note": "#ffe9a8",
              "dots": "rgba(170,120,80,0.16)", "grid": "rgba(140,190,255,0.045)", "bubble": "rgba(150,210,255,0.22)",
              "stamp-bg": "rgba(10,23,41,0.82)"},
    "paper": {"bg": "#f4ebdc", "bg2": "#efe2cc", "win": "#fffaf1", "edge": "#4a2e22", "edge-light": "#fffaf1", "rim": "#d9b896",
              "ring": "#4a2e22", "drop": "rgba(74,46,34,0.25)", "bar": "#4a2e22", "bar-ink": "#fffaf1", "ink": "#3a2318",
              "dim": "#8a6a55", "accent": "#e8692f", "on-accent": "#fffaf1", "aqua": "#2f8f83", "paper": "#fff6ea",
              "paper-rim": "#e6cfb3", "floor": "#f0dcc2", "floor-edge": "#e2c6a2", "shadow": "#d9bf9c", "note": "#ffe9a8",
              "dots": "rgba(170,120,80,0.14)", "grid": "rgba(120,80,40,0.05)", "bubble": "rgba(120,80,40,0.16)",
              "stamp-bg": "rgba(255,250,241,0.88)"},
    "tide": {"bg": "#0b2226", "bg2": "#0f3036", "win": "#123a40", "edge": "#f1f6ee", "edge-light": "#f1f6ee", "rim": "#3f7f78",
             "ring": "#06171a", "drop": "rgba(0,0,0,0.35)", "bar": "#08191c", "bar-ink": "#f1f6ee", "ink": "#f3f8f2",
             "dim": "#b9d3cc", "accent": "#f2c66d", "on-accent": "#14262a", "aqua": "#7fe3d5", "paper": "#f6efe0",
             "paper-rim": "#dccaa5", "floor": "#e9dcc0", "floor-edge": "#dbc9a3", "shadow": "#cdb88d", "note": "#fff1a8",
             "dots": "rgba(150,120,70,0.15)", "grid": "rgba(127,227,213,0.05)", "bubble": "rgba(127,227,213,0.2)",
             "stamp-bg": "rgba(11,34,38,0.84)"},
    "sakura": {"bg": "#2a1730", "bg2": "#3a1d3f", "win": "#3b2147", "edge": "#fff0f6", "edge-light": "#fff0f6", "rim": "#a05a8c",
               "ring": "#140a18", "drop": "rgba(0,0,0,0.35)", "bar": "#1c0f22", "bar-ink": "#fff0f6", "ink": "#fff5fa",
               "dim": "#e2bfd6", "accent": "#ff8fb8", "on-accent": "#2a1730", "aqua": "#7fe0ff", "paper": "#fdeef3",
               "paper-rim": "#e9bfd0", "floor": "#f6d9e4", "floor-edge": "#ecc3d3", "shadow": "#e0b0c3", "note": "#fff1a8",
               "dots": "rgba(200,90,140,0.14)", "grid": "rgba(255,170,210,0.05)", "bubble": "rgba(255,180,220,0.22)",
               "stamp-bg": "rgba(42,23,48,0.84)"},
}
PORTRAIT_W, PORTRAIT_H, FLOOR_GAP = 642, 872, 70


def _theme(ep):
    t = dict(THEMES.get(ep.get("theme", "night"), THEMES["night"]))
    t.update(ep.get("theme_overrides") or {})
    t["on_accent"] = t["on-accent"]
    return t


def _cast(ep, base: Path):
    cast = {}
    for who, c in (ep.get("cast") or {}).items():
        d = (base / c["sprite"]).resolve()
        if not (d / "n.png").exists():
            raise EpisodeError(f"cast {who}: no n.png in {d}")
        w, h = Image.open(d / "n.png").size
        faces = sorted(p.stem for p in d.glob("*.png") if p.stem != "base")
        cast[who] = {**c, "_dir": d, "px_w": w, "px_h": h, "faces": faces}
    if not cast:
        raise EpisodeError("episode has no cast")
    # layout: one actor big in the middle, or several side by side with their feet on the floor
    n = len(cast)
    slot = PORTRAIT_W / n
    tallest = max(c["px_h"] for c in cast.values())
    for i, (who, c) in enumerate(cast.items()):
        scale = int(min((PORTRAIT_H - FLOOR_GAP - 60) / tallest, (slot - 30) / c["px_w"], 6 if n == 1 else 5))
        w, h = c["px_w"] * scale, c["px_h"] * scale
        c.update(scale=scale, w=w, h=h, x=round(slot * i + (slot - w) / 2), y=PORTRAIT_H - FLOOR_GAP - h)
    return cast


def _strings(obj, out):
    if isinstance(obj, str):
        out.append(obj)
    elif isinstance(obj, dict):
        for k, v in obj.items():
            if k not in ("sprite", "src", "who", "type", "id", "style", "cue", "theme", "lang", "color", "on_color"):
                _strings(v, out)
    elif isinstance(obj, list):
        for v in obj:
            _strings(v, out)


def _fonts(font_src: Path, text: str, out_dir: Path):
    from fontTools import subset
    from fontTools.ttLib import TTFont
    from fontTools.varLib import instancer

    chars = "".join(sorted(set(text + "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz .,!?:;'\"()-+×✓·…")))
    out_dir.mkdir(parents=True, exist_ok=True)
    for wght in (500, 800, 900):
        out = out_dir / f"pd-{wght}.woff2"
        stamp = out.with_suffix(".chars")
        if out.exists() and stamp.exists() and stamp.read_text(encoding="utf-8") == chars:
            continue
        f = TTFont(font_src)
        if "fvar" in f:
            f = instancer.instantiateVariableFont(f, {"wght": wght})
        opts = subset.Options()
        opts.flavor = "woff2"
        opts.layout_features = ["*"]
        sub = subset.Subsetter(opts)
        sub.populate(text=chars)
        sub.subset(f)
        f.flavor = "woff2"
        f.save(out)
        stamp.write_text(chars, encoding="utf-8")


def _font_src() -> Path:
    for p in (os.environ.get("PIXEL_DIARY_FONT"), REPO / "fonts" / "NotoSansSC-VF.ttf"):
        if p and Path(p).exists():
            return Path(p)
    raise EpisodeError("no CJK font: put NotoSansSC-VF.ttf in fonts/ (see fonts/README.md) or set PIXEL_DIARY_FONT")


def _copy_media(ep, base: Path, assets: Path):
    """Images and clips referenced by scenes are copied next to the page and their src rewritten."""
    media = assets / "media"
    for sc in ep["scenes"]:
        if sc.get("src"):
            src = (base / sc["src"]).resolve()
            if not src.exists():
                raise EpisodeError(f"scene {sc.get('id')}: {src} not found")
            media.mkdir(parents=True, exist_ok=True)
            dst = media / src.name
            if not dst.exists() or dst.stat().st_mtime < src.stat().st_mtime:
                shutil.copy2(src, dst)
            sc["src"] = f"assets/media/{src.name}"


def _moves(p, cast):
    js = []
    prev_face = {}
    for i, L in enumerate(p["lines"]):
        who, typ_end = L["who"], L["times"][-1] + 0.08
        move = L.get("move")
        if move == "hop" or (move is None and L["after"] == "h" and L["face"] != "h"):
            js.append(f'hop(tl, "{who}", {round(typ_end if L["face"] != "h" else L["start"], 3)});')
        elif move is None and L["face"] == "h" and prev_face.get(who) != "h":
            js.append(f'hop(tl, "{who}", {L["start"]});')
        if move == "shake" or (move is None and L["face"] == "s" and prev_face.get(who) != "s"):
            js.append(f'shake(tl, "{who}", {L["start"]});')
        prev_face[who] = L["after"]
    return "\n        ".join(js)


def build(episode_path: str, out_dir: str, dry: bool = False) -> dict:
    """dry=True checks the episode (speakers, cues, scene fields, media) without writing anything."""
    ep = load(episode_path)
    base = Path(ep["_dir"])
    out = Path(out_dir).resolve()
    assets = out / "assets"
    theme = _theme(ep)
    cast = _cast(ep, base)
    if dry:
        for sc in ep["scenes"]:
            if sc.get("src") and not (base / sc["src"]).exists():
                raise EpisodeError(f"scene {sc.get('id')}: {sc['src']} not found")
    else:
        (assets / "audio").mkdir(parents=True, exist_ok=True)
        _copy_media(ep, base, assets)
    # carry per-line extras the plan doesn't keep
    p = make_plan(ep)
    flat = [ln for sc in ep["scenes"] for ln in sc.get("lines", [])]
    for L, src in zip(p["lines"], flat):
        for k in ("react", "move"):
            if k in src:
                L[k] = src[k]
    html_parts, js_parts, events, root_media, duck = [], [], [], [], []
    for sc, sp in zip(ep["scenes"], p["scenes"]):
        fn = scenes.RENDERERS.get(sc["type"])
        if not fn:
            raise EpisodeError(f"unknown scene type {sc['type']!r}")
        c = scenes.Ctx(sc, sp, p, theme, cast)
        html_parts.append(fn(c))
        js_parts.extend(c.js)
        events.extend(c.sfx)
        root_media.extend(c.root)
        duck.extend(c.duck)
    if dry:
        return p
    # cast sprites
    actors = []
    for who, c in cast.items():
        d = assets / "cast" / who
        d.mkdir(parents=True, exist_ok=True)
        for f in c["faces"]:
            shutil.copy2(c["_dir"] / f"{f}.png", d / f"{f}.png")
        imgs = "".join(f'<img data-face="{f}" src="assets/cast/{who}/{f}.png" alt="" />' for f in c["faces"])
        cell = 6 * c["scale"]
        actors.append(f'<div class="actor" id="actor-{who}" style="left:{c["x"]}px;top:{c["y"]}px;width:{c["w"]}px;height:{c["h"]}px">'
                      f'<i class="shadow"></i><div class="bob" id="bob-{who}"><div class="hop" id="hop-{who}">'
                      f'<div class="clipbox" id="clip-{who}">{imgs}</div><div class="blocks" id="blocks-{who}"></div>'
                      f'<div class="sgrid" id="grid-{who}" style="background-size:{cell}px {cell}px"></div></div></div></div>')
    cast_js = {w: {"name": c.get("name", w), "color": c.get("color", theme["accent"]), "on_color": c.get("on_color", theme["on-accent"]),
                   "scale": c["scale"], "w": c["w"], "h": c["h"], "dir": f"assets/cast/{w}"} for w, c in cast.items()}
    # header from the second scene on
    hdr = ep.get("header") or {}
    header = ""
    if hdr:
        hf = min(int(hdr.get("from_scene", 1)), len(p["scenes"]) - 1)
        h0 = p["scenes"][hf]["start"]
        chip = f'<span class="chip">{scenes.e(hdr["chip"])}</span>' if hdr.get("chip") else ""
        header = (f'<div id="hdr" class="clip" data-start="{h0}" data-duration="{round(p["duration"] - h0, 3)}" data-track-index="1">'
                  f'<div id="hdr-inner"><span class="hdr-t">{scenes.e(hdr.get("title", ""))}</span>{chip}</div></div>')
        js_parts.append(f'slide(tl, "#hdr-inner", {h0}, {{ y: -30 }});')
    if ep.get("ai_tag"):
        header += f'<div id="tag">{scenes.e(ep["ai_tag"])}</div>'
    # audio
    audio.write_wav(assets / "audio" / "sfx.wav", audio.sfx_track(p, events, cast))
    if ep.get("bgm_file"):
        raise EpisodeError("bgm_file: convert your track to assets/audio/bgm.wav yourself and set bgm to 'none'")
    if ep.get("bgm", "cheerful") != "none":
        audio.write_wav(assets / "audio" / "bgm.wav", audio.bgm_track(p["duration"], ep.get("bgm", "cheerful"), duck))
    else:
        audio.write_wav(assets / "audio" / "bgm.wav", audio.np.zeros(int(audio.SR * p["duration"])))
    # fonts
    texts = []
    _strings({k: v for k, v in ep.items() if not k.startswith("_")}, texts)
    _fonts(_font_src(), "".join(texts), assets / "fonts")
    # page
    tpl = (PKG / "template.html").read_text(encoding="utf-8")
    theme_vars = " ".join(f"--{k}: {v};" for k, v in theme.items() if k != "on_accent")
    rep = {
        "__LANG__": "zh-CN" if p["lang"] == "zh" else "en",
        "__THEME_VARS__": theme_vars,
        "__WORD_BREAK__": "break-all" if p["lang"] == "zh" else "normal",
        "__DURATION__": str(p["duration"]),
        "__HEADER__": header,
        "__SCENES__": "\n".join(html_parts),
        "__ROOT_MEDIA__": "\n".join(root_media),
        "__ACTORS__": "".join(actors),
        "__BGM_VOL__": str(ep.get("bgm_volume", 0.8)),
        "__PLAN__": json.dumps(p, ensure_ascii=False),
        "__CAST__": json.dumps(cast_js, ensure_ascii=False),
        "__SCENES_JS__": "\n        ".join(js_parts),
        "__MOVES_JS__": _moves(p, cast),
    }
    for k, v in rep.items():
        tpl = tpl.replace(k, v)
    (out / "index.html").write_text(tpl, encoding="utf-8")
    (out / "plan.json").write_text(json.dumps(p, ensure_ascii=False, indent=1), encoding="utf-8")
    name = out.name
    (out / "hyperframes.json").write_text(json.dumps({"paths": {"assets": "assets"}, "media": {"autoProxy": True}}, indent=2))
    (out / "meta.json").write_text(json.dumps({"id": name, "name": name}, indent=2))
    (out / "package.json").write_text(json.dumps({"name": name, "private": True, "type": "module", "scripts": {
        "check": f"npx --yes hyperframes@{HF_VERSION} check", "render": f"npx --yes hyperframes@{HF_VERSION} render"}}, indent=2))
    return p


def render(out_dir: str, mp4: str, loudnorm: bool = True) -> Path:
    out = Path(out_dir).resolve()
    target = Path(mp4).resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    raw = target.with_suffix(".raw.mp4") if loudnorm else target
    subprocess.run(["npx", "--yes", f"hyperframes@{HF_VERSION}", "render", "--quality", "high", "--output", str(raw)],
                   cwd=out, check=True)
    if loudnorm:
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(raw), "-c:v", "copy", "-af", "loudnorm=I=-16:TP=-1.5:LRA=11",
                        "-c:a", "aac", "-b:a", "192k", str(target)], check=True)
        raw.unlink()
    return target


def main(argv=None):
    ap = argparse.ArgumentParser(prog="pixel_diary")
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build", help="episode JSON → HyperFrames project")
    b.add_argument("episode")
    b.add_argument("--out", required=True)
    b.add_argument("--render", metavar="MP4", help="also render to this file")
    b.add_argument("--no-loudnorm", action="store_true")
    c = sub.add_parser("check", help="validate an episode without building")
    c.add_argument("episode")
    a = ap.parse_args(argv)
    if a.cmd == "check":
        try:
            p = build(a.episode, "/nonexistent", dry=True)
        except (EpisodeError, KeyError, TypeError, ValueError) as exc:
            print(f"episode error: {type(exc).__name__}: {exc}", file=sys.stderr)
            return 2
        print(json.dumps({"ok": True, "duration": p["duration"], "lines": len(p["lines"]), "scenes": [s["id"] for s in p["scenes"]]}))
        return 0
    try:
        p = build(a.episode, a.out)
    except (EpisodeError, KeyError, TypeError, ValueError) as exc:
        print(f"episode error: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2
    print(f"built {a.out}: {p['duration']}s, {len(p['lines'])} lines")
    for s in p["scenes"]:
        print(f"  {s['id']:12s} {s['type']:8s} {s['start']:6.2f} → {s['end']:6.2f}")
    if a.render:
        print("rendered", render(a.out, a.render, not a.no_loudnorm))
    return 0
