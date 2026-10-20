"""Scene types. Each renderer returns the scene's HTML, its GSAP lines, sound events and any root-level media.

Layout: the stage is the 1050×640 box left of the portrait (x 80, y 132 on a 1920×1080 frame).
Every scene's element ids are prefixed with the scene id, so scenes can repeat a type.
"""
from __future__ import annotations

import html
import json

from .plan import EpisodeError, resolve

STAGE_X, STAGE_Y = 80, 132


def e(s) -> str:
    return html.escape(str(s), quote=True)


def px(text, size, scale, color, weight="900", shadow=None, extra="", ident="", maxw=0):
    sh = f' data-shadow="{e(shadow)}"' if shadow else ""
    sh += f' data-maxw="{maxw}"' if maxw else ""
    i = f' id="{ident}"' if ident else ""
    return (f'<div{i} class="px{(" " + extra) if extra else ""}" data-text="{e(text)}" data-size="{size}" '
            f'data-scale="{scale}" data-color="{e(color)}" data-weight="{weight}"{sh}></div>')


class Ctx:
    def __init__(self, scene, sc_plan, plan, theme, cast):
        self.s = scene
        self.p = sc_plan
        self.plan = plan
        self.cues = plan["cues"]
        self.theme = theme
        self.cast = cast
        self.id = sc_plan["id"]
        self.js: list[str] = []
        self.sfx: list[tuple] = []
        self.root: list[str] = []
        self.duck: list[tuple] = []   # windows where a clip's own sound plays and the music steps back

    def at(self, cue, default=0.12):
        return round(resolve(cue, self.p, self.cues, default), 3)

    def slide(self, sel, t, frm="{ x: -70 }", sound="ping"):
        self.js.append(f'slide(tl, "{sel}", {t}, {frm});')
        if sound:
            self.sfx.append((sound, t))

    def pop(self, sel, t, s=0.55, sound="ping"):
        self.js.append(f'pop(tl, "{sel}", {t}, {s});')
        if sound:
            self.sfx.append((sound, t))

    def blink(self, sel, t):
        n = max(0, int((self.p["end"] - t) / 0.9) * 2 - 1)
        self.js.append(f'tl.fromTo("{sel}", {{ opacity: 1 }}, {{ opacity: 0, duration: 0.45, ease: "steps(1)", yoyo: true, repeat: {n} }}, {t});')


def _section(c: Ctx, inner: str) -> str:
    dur = round(c.p["end"] - c.p["start"], 3)
    return (f'<section id="{c.id}" class="scene clip" data-start="{c.p["start"]}" data-duration="{dur}" '
            f'data-track-index="2">{inner}</section>')


# ------------------------------------------------------------------ scene types
def title(c: Ctx) -> str:
    s, T = c.s, c.theme
    press = f'<div id="{c.id}-press" class="press">{e(s["press"])}</div>' if s.get("press") else ""
    sub = f'<div class="sub">{e(s["sub"])}</div>' if s.get("sub") else ""
    inner = (f'<div class="win title-card"><div class="center">'
             f'{px(s["big"], 22, 8, T["accent"], ident=c.id + "-big", maxw=820)}{sub}{press}</div></div>')
    t0 = c.p["start"]
    c.js.append(f'tl.fromTo("#{c.id}-big", {{ y: -40 }}, {{ y: 0, duration: 0.25, ease: "steps(4)" }}, {t0});')
    if press:
        c.blink(f"#{c.id}-press", t0 + 0.9)
    return _section(c, inner)


def flow(c: Ctx) -> str:
    s, T = c.s, c.theme
    a, mid, b = s["a"], s.get("mid", {}), s["b"]
    icon = TV_ICON if a.get("icon", "tv") == "tv" else ""
    kicker = f'<span class="lv">{e(a["kicker"])}</span>' if a.get("kicker") else ""
    inner = (f'<div class="ho"><div id="{c.id}-a" class="win ho-a">{kicker}{icon}<span class="ho-big">{e(a["text"])}</span></div>'
             f'<div id="{c.id}-m" class="ho-mid"><span>{e(mid.get("text", ""))}</span><i class="arrow"></i></div>'
             f'<div id="{c.id}-b" class="win ho-b"><span class="ho-dim">{e(b.get("kicker", ""))}</span>'
             f'{px(b["big"], 22, 6, b.get("color", T["aqua"]), maxw=250)}</div></div>')
    c.slide(f"#{c.id}-a", c.at(a.get("cue")), sound="pop")
    c.slide(f"#{c.id}-m", c.at(mid.get("cue"), 0.6), "{ x: -40 }")
    c.pop(f"#{c.id}-b", c.at(b.get("cue"), 1.0))
    return _section(c, inner)


def status(c: Ctx) -> str:
    s = c.s
    rows = []
    for r in s.get("rows", []):
        cls = {"name": "val-name", "accent": "val-lv"}.get(r.get("style"), "val")
        rows.append(f'<div class="row"><b>{e(r["k"])}</b><span class="{cls}">{e(r["v"])}</span></div>')
    tags = s.get("tags")
    if tags:
        chips = "".join(f'<span id="{c.id}-tag{i}" class="tg">{e(it["text"])}</span>' for i, it in enumerate(tags["items"]))
        rows.append(f'<div class="row"><b>{e(tags.get("k", ""))}</b><div class="tags">{chips}</div></div>')
    inner = (f'<div id="{c.id}-win" class="win status"><div class="bar-title"><i></i>{e(s.get("title", ""))}</div>'
             f'<div class="rows">{"".join(rows)}</div></div>')
    c.slide(f"#{c.id}-win", c.at(s.get("cue")), sound="pop")
    for i, it in enumerate((tags or {}).get("items", [])):
        c.pop(f"#{c.id}-tag{i}", c.at(it.get("cue"), 0.5 + 0.3 * i), 0.4)
    return _section(c, inner)


def cards(c: Ctx) -> str:
    s, T = c.s, c.theme
    items = s["items"]
    if len(items) > 3:
        raise EpisodeError(f"{c.id}: cards holds at most 3 items")
    parts = [px(s["title"], 21, 4, T["accent"], "800", ident=c.id + "-title", extra="rules-title", maxw=940)] if s.get("title") else []
    times = [c.at(it.get("cue"), 0.4 + 0.5 * i) for i, it in enumerate(items)]
    for i, it in enumerate(items):
        sub = f'<div class="card-s">{e(it["s"])}</div>' if it.get("s") else ""
        parts.append(f'<div id="{c.id}-c{i}" class="win card c{i + 1}"><div class="hi" id="{c.id}-hi{i}"></div>'
                     f'<div class="num">{px(str(i + 1), 14, 4, T["on_accent"], shadow="none")}</div>'
                     f'<div><div class="card-t">{e(it["t"])}</div>{sub}</div></div>')
    note = s.get("note")
    if note:
        parts.append(f'<div id="{c.id}-note" class="note"><span class="note-in">{e(note["text"])}</span></div>')
    if s.get("title"):
        c.slide(f"#{c.id}-title", c.at(s.get("cue")), "{ y: -30 }", sound="pop")
    for i, t in enumerate(times):
        c.slide(f"#{c.id}-c{i}", t)
        off = times[i + 1] if i + 1 < len(times) else c.p["end"]
        c.js.append(f'tl.set("#{c.id}-hi{i}", {{ opacity: 1 }}, {t}); tl.set("#{c.id}-hi{i}", {{ opacity: 0 }}, {round(off - 0.01, 3)});')
    if note:
        c.pop(f"#{c.id}-note", c.at(note.get("cue"), 2.0), 0.5)
    return _section(c, inner="".join(parts))


def lines(c: Ctx) -> str:
    T = c.theme
    rows = []
    for i, it in enumerate(c.s["items"]):
        st = it.get("style", "big")
        rid = f"{c.id}-l{i}"
        if st == "pixel":
            rows.append(px(it["text"], 21, 4, T["accent"], "800", ident=rid, maxw=980))
        else:
            mark = f'<span class="mk">{e(it["mark"])}</span>' if it.get("mark") else ""
            rows.append(f'<div id="{rid}" class="ln ln-{e(st)}">{mark}{e(it["text"])}</div>')
        t = c.at(it.get("cue"), 0.12 + 0.6 * i)
        if st == "pixel":
            c.js.append(f'tl.fromTo("#{rid}", {{ opacity: 0, scale: 1.5 }}, {{ opacity: 1, scale: 1, duration: 0.2, ease: "steps(3)" }}, {t});')
            c.sfx.append(("thud", t))
        else:
            c.slide(f"#{rid}", t)
    return _section(c, f'<div class="lines">{"".join(rows)}</div>')


def image(c: Ctx) -> str:
    s, T = c.s, c.theme
    cap = f'<span>{e(s["caption"])}</span>' if s.get("caption") else ""
    parts = [f'<div id="{c.id}-img" class="win draft"><img src="{e(s["src"])}" alt="" />{cap}</div>']
    c.pop(f"#{c.id}-img", c.at(s.get("cue")), 0.7)
    m = s.get("meter")
    if m:
        parts.append(f'<div id="{c.id}-meter" class="meter"><div class="meter-t">{e(m["label"])}</div>'
                     f'<div class="barbox"><i id="{c.id}-fill" class="barfill"></i></div>'
                     f'<div class="meter-s"><span id="{c.id}-doing">{e(m.get("doing", "…"))}</span>'
                     f'<span id="{c.id}-done">{e(m.get("done", "✓"))}</span></div></div>')
        t0 = c.at(m.get("cue"), 1.0)
        d = float(m.get("duration", 3.0))
        c.slide(f"#{c.id}-meter", round(t0 - 0.1, 3))
        c.js.append(f'tl.fromTo("#{c.id}-fill", {{ scaleX: 0 }}, {{ scaleX: 1, duration: {d}, ease: "steps(20)" }}, {t0 + 0.2});')
        c.js.append(f'tl.fromTo("#{c.id}-doing", {{ opacity: 1 }}, {{ opacity: 0, duration: 0.01 }}, {t0 + 0.2 + d});')
        c.js.append(f'tl.fromTo("#{c.id}-done", {{ opacity: 0 }}, {{ opacity: 1, duration: 0.01 }}, {t0 + 0.2 + d});')
        r = s.get("redraw")
        if r:
            wipe = c.at(r.get("wipe", s.get("cue")))
            c.js.append(f'redraw(tl, {json.dumps(r["who"])}, {wipe}, {t0 + 0.2}, {d});')
            c.sfx.append(("sweep", t0 + 0.2, d))
    return _section(c, "".join(parts))


def ledger(c: Ctx) -> str:
    s, T = c.s, c.theme
    ctrs = "".join(f'<div id="{c.id}-k{i}" class="ctr"><b>{e(k["k"])}</b>{px(str(k["v"]), 20, 7, T["ink"], maxw=230)}</div>'
                   for i, k in enumerate(s["counters"]))
    parts = [f'<div id="{c.id}-win" class="win ledger"><div class="bar-title"><i></i>{e(s.get("title", ""))}</div>'
             f'<div class="counters">{ctrs}</div></div>']
    c.slide(f"#{c.id}-win", c.at(s.get("cue")), sound="pop")
    for i, k in enumerate(s["counters"]):
        c.pop(f"#{c.id}-k{i}", c.at(k.get("cue"), 0.5 + 0.4 * i), 0.6)
    st = s.get("stamp")
    if st:
        parts.append(f'<div id="{c.id}-stamp" class="stamp"><span class="stamp-in">{e(st["text"])}</span></div>')
        t = c.at(st.get("cue"), 2.5)
        c.js.append(f'tl.fromTo("#{c.id}-stamp", {{ opacity: 0, scale: 2.2 }}, {{ opacity: 1, scale: 1, duration: 0.16, ease: "steps(3)" }}, {round(t - 0.16, 3)});')
        c.sfx.append(("thud", t))
    return _section(c, "".join(parts))


def ask(c: Ctx) -> str:
    s = c.s
    parts = [f'<div id="{c.id}-t" class="ask-t">{e(s["title"])}</div>',
             f'<div id="{c.id}-in" class="win input"><div class="typed"><span class="typed-text" data-typed="{e(s.get("typed", ""))}" '
             f'data-at="{c.at(s.get("typed_cue"), 0.6) + 0.35}"></span><i class="caret"></i></div>'
             f'<div class="send">{e(s.get("button", "发送"))}</div></div>']
    c.slide(f"#{c.id}-t", c.at(s.get("cue")), "{ y: -30 }", sound="pop")
    c.slide(f"#{c.id}-in", c.at(s.get("cue"), 0.24), sound=None)
    t = c.at(s.get("typed_cue"), 0.6) + 0.35
    for k in range(len(s.get("typed", ""))):
        c.sfx.append(("click", t + k * 0.22))
    note = s.get("note")
    if note:
        parts.append(f'<div id="{c.id}-n" class="pick">{e(note["text"])}</div>')
        c.slide(f"#{c.id}-n", c.at(note.get("cue"), 2.0), "{ y: 20 }")
    return _section(c, "".join(parts))


def follow(c: Ctx) -> str:
    s = c.s
    parts = [f'<div id="{c.id}-b" class="follow">{e(s["button"])}</div>']
    c.pop(f"#{c.id}-b", c.at(s.get("cue")), 0.6, sound="pop")
    b = s.get("bubble")
    if b:
        parts.append(f'<div id="{c.id}-q" class="bubble-t"><span class="bubble-in">{e(b["text"])}</span></div>')
        c.pop(f"#{c.id}-q", c.at(b.get("cue"), 1.5), 0.6)
    n = s.get("note")
    if n:
        parts.append(f'<div id="{c.id}-n" class="every">{e(n["text"])}</div>')
        c.slide(f"#{c.id}-n", c.at(n.get("cue"), 3.0), "{ y: 20 }")
    return _section(c, "".join(parts))


def end(c: Ctx) -> str:
    s, T = c.s, c.theme
    disc = "".join(f"<span>{e(x)}</span>" for x in s.get("disclaimer", []))
    inner = (f'<div class="center">{px(s["big"], 20, 7, T["accent"], ident=c.id + "-big", maxw=940)}'
             f'<div id="{c.id}-bye" class="bye">{e(s.get("bye", ""))}</div>'
             f'<div id="{c.id}-d" class="disc">{disc}</div></div>')
    t0 = c.p["start"]
    c.js.append(f'tl.fromTo("#{c.id}-big", {{ opacity: 0, y: -60 }}, {{ opacity: 1, y: 0, duration: 0.4, ease: "steps(5)" }}, {t0 + 0.12});')
    c.slide(f"#{c.id}-bye", t0 + 0.5, "{ y: 30 }", sound=None)
    c.slide(f"#{c.id}-d", t0 + 0.8, "{ y: 20 }", sound=None)
    c.sfx.append(("jingle", t0 + 0.3))
    return _section(c, inner)


def chat(c: Ctx) -> str:
    s = c.s
    msgs = s["messages"]
    if len(msgs) > 5:
        raise EpisodeError(f"{c.id}: chat shows at most 5 messages")
    rows = []
    for i, m in enumerate(msgs):
        who = c.cast.get(m["who"], {})
        rows.append(f'<div id="{c.id}-m{i}" class="msg"><span class="who" style="background:{e(who.get("color", "#888"))};'
                    f'color:{e(who.get("on_color", "#13203a"))}">{e(who.get("name", m["who"]))}</span>'
                    f'<span class="txt">{e(m["text"])}</span></div>')
    inner = (f'<div id="{c.id}-win" class="win chatwin"><div class="bar-title"><i></i>{e(s.get("title", ""))}</div>'
             f'<div class="msgs">{"".join(rows)}</div></div>')
    c.slide(f"#{c.id}-win", c.at(s.get("cue")), sound="pop")
    for i, m in enumerate(msgs):
        c.slide(f"#{c.id}-m{i}", c.at(m.get("cue"), 0.5 + 0.8 * i), "{ y: 24 }")
    return _section(c, inner)


def clip(c: Ctx) -> str:
    """A video in a frame. The <video> lives at the root: HyperFrames forbids a timed video inside a timed section.
    "aspect": "9:16" gives a phone-shaped frame on the left with "notes" (up to 4 lines) beside it."""
    s = c.s
    t = c.at(s.get("cue"), 0.15)
    dur = round(float(s.get("duration", c.p["end"] - t)), 3)
    dur = min(dur, round(c.p["end"] - t, 3))
    vertical = s.get("aspect") == "9:16"
    cap = f'<div id="{c.id}-cap" class="clip-cap{" v" if vertical else ""}">{e(s["caption"])}</div>' if s.get("caption") else ""
    notes = ""
    if vertical and s.get("notes"):
        rows = "".join(f'<div id="{c.id}-n{i}" class="cn">{e(n["text"])}</div>' for i, n in enumerate(s["notes"][:4]))
        notes = f'<div class="clip-notes">{rows}</div>'
    inner = f'<div id="{c.id}-frame" class="win clipframe{" v" if vertical else ""}"></div>{cap}{notes}'
    vol = float(s.get("volume", 0))
    muted = "" if vol > 0 else " muted"
    cls = "clipvid v" if vertical else "clipvid"
    c.root.append(f'<video id="{c.id}-v" class="{cls}" src="{e(s["src"])}" data-start="{t}" data-duration="{dur}" '
                  f'data-media-start="{float(s.get("from", 0))}" data-track-index="4" data-volume="{vol}"{muted} playsinline></video>')
    c.pop(f"#{c.id}-frame", round(t - 0.2, 3), 0.85, sound="pop")
    if cap:
        c.slide(f"#{c.id}-cap", t, "{ y: 20 }", sound=None)
    for i, n in enumerate((s.get("notes") or [])[:4] if vertical else []):
        c.slide(f"#{c.id}-n{i}", c.at(n.get("cue"), 0.6 + 0.8 * i), "{ x: -40 }")
    if vol > 0:
        c.duck.append((t, t + dur))
    return _section(c, inner)


RENDERERS = {"title": title, "flow": flow, "status": status, "cards": cards, "lines": lines, "image": image,
             "ledger": ledger, "ask": ask, "follow": follow, "end": end, "chat": chat, "clip": clip}

TV_ICON = """<svg width="104" height="88" viewBox="0 0 26 22" shape-rendering="crispEdges">
<rect x="6" y="0" width="2" height="2" fill="#eaf3ff" /><rect x="18" y="0" width="2" height="2" fill="#eaf3ff" />
<rect x="8" y="2" width="2" height="2" fill="#eaf3ff" /><rect x="16" y="2" width="2" height="2" fill="#eaf3ff" />
<rect x="0" y="4" width="26" height="16" fill="#eaf3ff" /><rect x="2" y="6" width="22" height="12" fill="#0a1729" />
<rect x="7" y="10" width="3" height="3" fill="#62e3cf" /><rect x="16" y="10" width="3" height="3" fill="#62e3cf" />
<rect x="4" y="20" width="4" height="2" fill="#eaf3ff" /><rect x="18" y="20" width="4" height="2" fill="#eaf3ff" /></svg>"""
