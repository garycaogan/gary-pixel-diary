import json
from pathlib import Path

import pytest

from pixel_diary.build import build
from pixel_diary.plan import EpisodeError, load, plan

ROOT = Path(__file__).resolve().parents[1]


def test_demo_episode_plans():
    p = plan(load(ROOT / "episodes/demo/day0.json"))
    assert 60 < p["duration"] < 90
    assert p["lines"][0]["start"] >= 0
    # every cue fires inside its scene
    for sc in p["scenes"]:
        for ln in p["lines"]:
            if ln["scene"] == sc["id"]:
                assert sc["start"] <= ln["start"] <= sc["end"]


def test_dry_build_checks_cues(tmp_path):
    ep = json.loads((ROOT / "episodes/demo/day0.json").read_text(encoding="utf-8"))
    ep["scenes"][1]["lines"][0]["cues"]["arrow"] = "台词里没有这几个字"
    f = ROOT / "episodes/demo/_bad.json"
    f.write_text(json.dumps(ep, ensure_ascii=False), encoding="utf-8")
    try:
        with pytest.raises(EpisodeError, match="not found in line"):
            build(str(f), str(tmp_path), dry=True)
    finally:
        f.unlink()


def test_dry_build_accepts_duo():
    p = build(str(ROOT / "episodes/duo/day0.json"), "/nonexistent", dry=True)
    assert {ln["who"] for ln in p["lines"]} == {"claude", "deepseek"}


def test_english_types_faster_and_counts_words():
    ep = {"lang": "en", "cast": {"a": {"sprite": "x"}}, "scenes": [
        {"id": "s", "type": "lines", "items": [], "lines": [{"who": "a", "t": "Hello there, this is a test line."}]}]}
    zh = {"lang": "zh", "cast": {"a": {"sprite": "x"}}, "scenes": [
        {"id": "s", "type": "lines", "items": [], "lines": [{"who": "a", "t": "你好，这是一句测试台词。"}]}]}
    pe, pz = plan(ep), plan(zh)
    assert pe["lines"][0]["times"][1] - pe["lines"][0]["times"][0] < pz["lines"][0]["times"][1] - pz["lines"][0]["times"][0]
