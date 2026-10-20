"""Episode JSON → timeline: when every character appears, when every cue fires."""
from __future__ import annotations

import json
import re
from pathlib import Path

LANG = {
    "zh": {"char": 0.078, "hold": 1.0, "per": 0.032,
           "pause": {"，": 0.13, "、": 0.1, "：": 0.16, "。": 0.3, "？": 0.3, "！": 0.3, "…": 0.09, "）": 0.12, " ": -0.05},
           "silent": set("，、：。？！…（）“”‘’《》 ,.!?:;\"'()")},
    "en": {"char": 0.034, "hold": 1.0, "per": 0.011,
           "pause": {",": 0.12, ";": 0.14, ":": 0.14, ".": 0.28, "?": 0.28, "!": 0.28, "—": 0.1, "…": 0.1},
           "silent": set(" ,.!?:;\"'()—…-")},
}


class EpisodeError(ValueError):
    pass


def load(path: str | Path) -> dict:
    p = Path(path)
    ep = json.loads(p.read_text(encoding="utf-8"))
    ep["_dir"] = str(p.parent.resolve())
    return ep


def _speaking_units(text: str, lang: str) -> int:
    silent = LANG[lang]["silent"]
    if lang == "en":
        return len(re.findall(r"[A-Za-z0-9']+", text))
    return sum(1 for ch in text if ch not in silent)


def plan(ep: dict) -> dict:
    lang = ep.get("lang", "zh")
    if lang not in LANG:
        raise EpisodeError(f"unknown lang {lang}")
    L = LANG[lang]
    speed = float(ep.get("speed", 1.0))
    char = L["char"] / speed
    cast = ep.get("cast") or {}
    default_who = next(iter(cast), "host")
    lines, cues, scenes = [], {}, []
    t = float(ep.get("start", 0.0))
    for si, sc in enumerate(ep["scenes"]):
        sid = sc.get("id") or f"s{si}"
        s0 = t
        t += float(sc.get("lead", 0.45))
        scene_lines = sc.get("lines", [])
        for i, ln in enumerate(scene_lines):
            text = ln["t"]
            who = ln.get("who", default_who)
            if cast and who not in cast:
                raise EpisodeError(f"line speaker {who!r} is not in cast")
            times, x = [], t
            for ch in text:
                times.append(round(x, 3))
                x += char + L["pause"].get(ch, 0)
            type_end = times[-1] + char
            units = _speaking_units(text, lang)
            hold = float(ln.get("hold", L["hold"] + (L["per"] if lang == "zh" else L["per"] * 3.2) * units))
            end = type_end + hold
            face = ln.get("face", "n")
            lines.append({"text": text, "who": who, "start": round(t, 3), "times": times, "face": face,
                          "after": ln.get("after", face), "end": round(end, 3), "scene": sid})
            for name, sub in (ln.get("cues") or {}).items():
                if sub not in text:
                    raise EpisodeError(f"cue {name!r}: {sub!r} not found in line {text!r}")
                if name in cues:
                    raise EpisodeError(f"cue {name!r} defined twice")
                cues[name] = times[text.index(sub)]
            t = end + (0.12 if i < len(scene_lines) - 1 else 0)
        if not scene_lines:
            t += float(sc.get("duration", 2.0))
        t += float(sc.get("tail", 0.15))
        scenes.append({"id": sid, "type": sc["type"], "start": round(s0, 3), "end": round(t, 3)})
    duration = round(t + 0.2, 2)
    return {"lang": lang, "lines": lines, "cues": cues, "scenes": scenes, "duration": duration}


def resolve(cue, scene: dict, cues: dict, default: float = 0.12) -> float:
    """A cue is a name defined on a line, a number (seconds after the scene starts) or "+0.3"."""
    if cue is None:
        return scene["start"] + default
    if isinstance(cue, (int, float)):
        return scene["start"] + float(cue)
    if isinstance(cue, str) and re.fullmatch(r"[+-]?\d+(\.\d+)?", cue):
        return scene["start"] + float(cue)
    if cue not in cues:
        raise EpisodeError(f"unknown cue {cue!r} in scene {scene['id']}")
    return cues[cue]
