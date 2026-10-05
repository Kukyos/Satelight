"""Checks the text pasted into the SIH portal and YouTube before it leaves the repo.

    python submission/textcheck.py

- Every number in the marked blocks of docs/25-portal-form.md and docs/26-youtube.md is in
  data/eval-latest.json at the precision written, or in video/script.json's `sourced` list,
  or in SOURCED below with where it comes from (hard rule 1). The same rule as
  video/check.mjs, so the film, the deck and this text answer to one list.
- Each field is within the portal's or YouTube's limit, and the YouTube description has no
  < or >.
- The chapters start at 0:00, there are at least three, each is at least 10 s, and each
  starts on a scene of the film (video/script.json), at the next whole second.

Fails with a non-zero exit on the first list of problems.
"""

import json
import math
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = json.loads((ROOT / "video" / "script.json").read_text(encoding="utf-8"))
E = json.loads((ROOT / "data" / "eval-latest.json").read_text().replace("NaN", "null"))

SOURCED = {
    "187550": "the team's ID on the SIH portal",
    "45": "config: the box's western edge, 45°E", "105": "config: the box's eastern edge, 105°E",
    "5": "config: the box's southern edge, 5°N, and a standard depth",
    "30": "config: the box's northern edge, 30°N",
}
LIMITS = {"title": 100, "abstract": 10_000, "description": 50_000,
          "yt-title": 100, "yt-description": 5_000, "yt-tags": 500}
CHAPTER = re.compile(r"^(\d+):(\d\d) (.+)$")
NUMBER = re.compile(r"(?<![\w.])\d[\d,]*(?:\.\d+)?(?!\w)")


def known_numbers() -> list[float]:
    # ponytail: membership in any harness number, as check.mjs does, so a three-decimal
    # value can match by chance; keyed lookups per claim if a near-miss ever slips through.
    out = []

    def walk(x):
        if isinstance(x, bool):
            return
        if isinstance(x, (int, float)):
            out.append(float(x))
        elif isinstance(x, str):
            out.extend(float(m) for m in re.findall(r"\d+(?:\.\d+)?", x))
        elif isinstance(x, dict):
            for v in x.values():
                walk(v)
        elif isinstance(x, list):
            for v in x:
                walk(v)
    walk(E)
    return out


def blocks(path: Path) -> dict:
    text = path.read_text(encoding="utf-8")
    out = {}
    for name, body in re.findall(r"<!-- ([\w-]+) -->\n(.*?)\n<!-- /\1 -->", text, re.S):
        out[name] = re.sub(r"^```\n|\n```$", "", body.strip())
    return out


def scene_starts() -> tuple[set, float]:
    t, starts = 0.0, set()
    for s in SCRIPT["scenes"]:
        starts.add(math.ceil(t))
        t += sum(c["seconds"] for c in s["clips"]) if s.get("clips") else s["seconds"]
    return starts, t


def check() -> list[str]:
    known = known_numbers()
    sourced = {k.replace(",", "") for k in SCRIPT["sourced"] if k != "_"} | set(SOURCED)
    fields = blocks(ROOT / "docs" / "25-portal-form.md") | blocks(ROOT / "docs" / "26-youtube.md")
    problems = []
    for name in LIMITS:
        if name not in fields:
            problems.append(f"{name}: no marked block")
    for name, text in fields.items():
        n = len(text)
        print(f"  {name:15s} {n:6,d} of {LIMITS.get(name, 0):,} characters")
        if n > LIMITS.get(name, n):
            problems.append(f"{name}: {n} characters, over {LIMITS[name]}")
        for line in text.splitlines():
            if CHAPTER.match(line):
                continue
            for m in NUMBER.finditer(line):
                tok = m.group().replace(",", "").rstrip(".")
                d = len(tok.split(".")[1]) if "." in tok else 0
                if tok not in sourced and not any(round(abs(k), d) == float(tok) for k in known):
                    problems.append(f"{name}: {m.group()} is not harness output or sourced  (... {line[max(0, m.start() - 40):m.end() + 10]} ...)")
    desc = fields.get("yt-description", "")
    if "<" in desc or ">" in desc:
        problems.append("yt-description: YouTube rejects < and >")
    starts, total = scene_starts()
    ch = [int(a) * 60 + int(b) for a, b, _ in (CHAPTER.match(l).groups() for l in desc.splitlines() if CHAPTER.match(l))]
    if len(ch) < 3 or ch[0] != 0:
        problems.append("chapters: need at least three, the first at 0:00")
    for a, b in zip(ch, ch[1:] + [total]):
        if b - a < 10:
            problems.append(f"chapters: {a // 60}:{a % 60:02d} lasts {b - a:.1f} s, under 10")
    for a in ch:
        if a not in starts:
            problems.append(f"chapters: {a // 60}:{a % 60:02d} is not where a scene starts")
    print(f"  {len(ch)} chapters over {total:.1f} s")
    return problems


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    p = check()
    for x in p:
        print(" FAIL", x)
    print("text ok" if not p else f"{len(p)} problems")
    sys.exit(1 if p else 0)
