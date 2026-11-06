#!/usr/bin/env python3
"""Build the animated SVG panels for the profile README.

    python scripts/build.py            # fetch live data from GitHub, write assets/
    python scripts/build.py --offline  # reuse assets/data.json (no network)

Edit scripts/profile.json for copy. Everything visual lives here: one dark and
one light SVG per panel, CSS animation only (GitHub strips JS), Geist and
Geist Mono subset and embedded so the type renders the same everywhere.
Token order of preference: $GH_TOKEN, $GITHUB_TOKEN, `gh auth token`.
"""
from __future__ import annotations

import base64
import datetime as dt
import html
import io
import json
import math
import os
import re
import subprocess
import sys
import urllib.request
from collections import Counter, defaultdict

from fontTools import subset
from fontTools.ttLib import TTFont
from fontTools.varLib import instancer

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ASSETS = os.path.join(ROOT, "assets")
FONTS = os.path.join(ROOT, "scripts", "fonts")
CFG = json.load(open(os.path.join(ROOT, "scripts", "profile.json"), encoding="utf-8"))

W = 1000  # every full-width panel shares this width so they line up in the README

# ---------------------------------------------------------------- themes ----
# Taken from the vintercept.ai tokens: indigo = acting, red = the attacker,
# nothing else gets colour.
THEMES = {
    "dark": dict(
        bg="#0b0b0d", bg2="#141417", panel="#131316", surface="#1e1e22", surface2="#26262b",
        line="#2e2e33", line_strong="#64646b", text="#fafaf7", muted="#a1a1a8", faint="#85858c",
        accent="#5b57ff", accent_text="#a9a7ff", threat="#cc171e", threat_text="#ff5a5f",
        cell_top="#26262b", cell_left="#1e1e22", cell_right="#16161a", dot="#2e2e33",
        heat=["#1a1a1e", "#2b2a5c", "#3e3a9e", "#5b57ff", "#a9a7ff"],
    ),
    "light": dict(
        bg="#fafaf7", bg2="#f3f3ee", panel="#ffffff", surface="#f0f0eb", surface2="#e6e6e0",
        line="#e2e2dc", line_strong="#8f8f88", text="#0b0b0d", muted="#55555c", faint="#6b6b72",
        accent="#5b57ff", accent_text="#3b3bf5", threat="#b61a1e", threat_text="#b61a1e",
        cell_top="#e3e3dc", cell_left="#c6c6be", cell_right="#d5d5cd", dot="#dcdcd5",
        heat=["#ebebe5", "#cfcdfb", "#a3a0fd", "#5b57ff", "#2c27c9"],
    ),
}

EASE = "cubic-bezier(.2,.8,.2,1)"
EASE_POP = "cubic-bezier(.3,1.6,.5,1)"
EASE_PING = "cubic-bezier(0,.6,.4,1)"


# ----------------------------------------------------------------- fonts ----
class Font:
    def __init__(self, family: str, path: str):
        self.family, self.path = family, path
        self._inst: dict[int, TTFont] = {}
        self._b64: dict[str, str] = {}

    def _instance(self, wght: int) -> TTFont:
        if wght not in self._inst:
            self._inst[wght] = instancer.instantiateVariableFont(TTFont(self.path), {"wght": wght})
        return self._inst[wght]

    def width(self, text: str, size: float, wght: int = 400, ls: float = 0.0) -> float:
        """Advance width in px. ls is letter-spacing in em (SVG adds it after every glyph)."""
        f = self._instance(wght)
        cmap, hmtx, upm = f.getBestCmap(), f["hmtx"], f["head"].unitsPerEm
        adv = sum(hmtx[cmap.get(ord(c)) or cmap[ord("?")]][0] for c in text)
        return adv * size / upm + ls * size * len(text)

    def face(self, chars: str) -> str:
        if chars not in self._b64:
            f = TTFont(self.path)
            opts = subset.Options()
            opts.flavor = "woff2"
            opts.layout_features = ["kern", "liga", "calt", "tnum"]
            opts.name_IDs = [1, 2]
            sub = subset.Subsetter(opts)
            sub.populate(text=chars + " ?")
            sub.subset(f)
            buf = io.BytesIO()
            f.flavor = "woff2"
            f.save(buf)
            self._b64[chars] = base64.b64encode(buf.getvalue()).decode()
        return (f"@font-face{{font-family:'{self.family}';font-weight:100 900;"
                f"src:url(data:font/woff2;base64,{self._b64[chars]}) format('woff2')}}")


SANS = Font("G", os.path.join(FONTS, "Geist.woff2"))
MONO = Font("GM", os.path.join(FONTS, "GeistMono.woff2"))

BASE_CSS = f"""
.s{{font-family:'G',ui-sans-serif,system-ui,-apple-system,'Segoe UI',sans-serif}}
.m{{font-family:'GM',ui-monospace,SFMono-Regular,Menlo,monospace}}
.u{{text-transform:uppercase}}
@keyframes rise{{from{{opacity:0;transform:translateY(12px)}}}}
@keyframes fade{{from{{opacity:0}}}}
@keyframes growx{{from{{transform:scaleX(0)}}}}
@keyframes blink{{0%,49%{{opacity:1}}50%,100%{{opacity:0}}}}
@keyframes ping{{0%{{transform:scale(1);opacity:.8}}75%,100%{{transform:scale(3.2);opacity:0}}}}
.gx{{transform-box:fill-box;transform-origin:0 50%;animation:growx 1.1s {EASE} .15s both}}
.cur{{animation:blink 1.06s steps(1) infinite}}
.png{{transform-box:fill-box;transform-origin:center;animation:ping 2s {EASE_PING} infinite}}
"""
REDUCED = "@media (prefers-reduced-motion:reduce){*{animation:none!important}}"


def esc(s: str) -> str:
    return html.escape(str(s), quote=True)


def svg_doc(w: int, h: int, body: str, title: str, css: str = "") -> str:
    # Subset the fonts to exactly the characters this file draws.
    texts = re.findall(r"<text[^>]*>(.*?)</text>", body, flags=re.S)
    chars = "".join(sorted(set(html.unescape(re.sub(r"<[^>]+>", "", "".join(texts))))))
    fonts = SANS.face(chars) + MONO.face(chars)
    return (f'<svg xmlns="http://www.w3.org/2000/svg" xml:space="preserve" width="{w}" height="{h}" viewBox="0 0 {w} {h}" '
            f'fill="none" role="img" aria-label="{esc(title)}"><title>{esc(title)}</title>'
            f"<style>{fonts}{BASE_CSS}{css}{REDUCED}</style>{body}</svg>")


def panel_frame(w: int, h: int, T: dict, uid: str, index: str | None = None,
                title: str | None = None, meta: str | None = None, dots: bool = False) -> str:
    """Square panel: gradient fill, 1px rule, corner ticks, optional header strip."""
    out = [f'<defs><linearGradient id="pf{uid}" x1="0" y1="0" x2="0" y2="1">'
           f'<stop offset="0" stop-color="{T["bg"]}"/><stop offset="1" stop-color="{T["bg2"]}"/></linearGradient>']
    if dots:
        out.append(f'<pattern id="dt{uid}" width="20" height="20" patternUnits="userSpaceOnUse">'
                   f'<rect x="9.5" y="9.5" width="1" height="1" fill="{T["dot"]}"/></pattern>'
                   f'<radialGradient id="dm{uid}" cx=".72" cy=".5" r=".6"><stop offset="0" stop-color="#fff"/>'
                   f'<stop offset="1" stop-color="#fff" stop-opacity="0"/></radialGradient>'
                   f'<mask id="mk{uid}"><rect width="{w}" height="{h}" fill="url(#dm{uid})"/></mask>')
    out.append("</defs>")
    out.append(f'<rect x=".5" y=".5" width="{w-1}" height="{h-1}" fill="url(#pf{uid})" stroke="{T["line"]}"/>')
    if dots:
        out.append(f'<rect width="{w}" height="{h}" fill="url(#dt{uid})" mask="url(#mk{uid})"/>')
    t = 10
    for x, y, sx, sy in ((0, 0, 1, 1), (w, 0, -1, 1), (0, h, 1, -1), (w, h, -1, -1)):
        out.append(f'<path d="M{x+.5*sx} {y+t*sy}V{y+.5*sy}H{x+t*sx}" stroke="{T["line_strong"]}"/>')
    if title:
        out.append(f'<text x="28" y="27" class="m u" font-size="11" letter-spacing=".12em" fill="{T["faint"]}">'
                   f'<tspan fill="{T["accent_text"]}">{esc(index)}</tspan>  /  {esc(title)}</text>')
        if meta:
            out.append(f'<text x="{w-28}" y="27" text-anchor="end" class="m u" font-size="11" '
                       f'letter-spacing=".12em" fill="{T["faint"]}">{esc(meta)}</text>')
        out.append(f'<rect x="1" y="44" width="{w-2}" height="1" fill="{T["line"]}"/>')
        out.append(f'<rect x="1" y="44" width="{(w-2)*.18:.0f}" height="1" fill="{T["accent"]}" class="gx"/>')
    return "".join(out)


def star_path(cx: float, cy: float, r: float) -> str:
    pts = []
    for k in range(10):
        a = -math.pi / 2 + k * math.pi / 5
        rr = r if k % 2 == 0 else r * 0.45
        pts.append(f"{cx + rr*math.cos(a):.2f} {cy + rr*math.sin(a):.2f}")
    return "M" + "L".join(pts) + "Z"


def arrow_ne(x: float, y: float, s: float, color: str, cls: str = "") -> str:
    return (f'<path class="{cls}" d="M{x} {y+s}L{x+s} {y}M{x+s*.3} {y}H{x+s}V{y+s*.7}" '
            f'stroke="{color}" stroke-width="1.4" stroke-linecap="square"/>')


def wrap(text: str, font: Font, size: float, width: float, wght: int = 400) -> list[str]:
    lines, cur = [], ""
    for word in text.split():
        trial = f"{cur} {word}".strip()
        if font.width(trial, size, wght) <= width or not cur:
            cur = trial
        else:
            lines.append(cur)
            cur = word
    if cur:
        lines.append(cur)
    return lines


# ------------------------------------------------------------------ data ----
def gh_token() -> str:
    for k in ("GH_TOKEN", "GITHUB_TOKEN"):
        if os.environ.get(k):
            return os.environ[k]
    return subprocess.check_output(["gh", "auth", "token"], text=True).strip()


def gql(query: str, variables: dict) -> dict:
    req = urllib.request.Request(
        "https://api.github.com/graphql",
        data=json.dumps({"query": query, "variables": variables}).encode(),
        headers={"Authorization": f"bearer {gh_token()}", "User-Agent": "profile-readme-build"},
    )
    with urllib.request.urlopen(req, timeout=60) as r:
        res = json.load(r)
    if res.get("errors"):
        raise SystemExit(f"GraphQL error: {res['errors']}")
    return res["data"]


USER_Q = """
query($login:String!){
  user(login:$login){
    login name createdAt
    followers{totalCount}
    repositories(ownerAffiliations:OWNER,isFork:false,first:100,orderBy:{field:PUSHED_AT,direction:DESC}){
      totalCount
      nodes{ name isPrivate stargazerCount pushedAt primaryLanguage{name}
        languages(first:15,orderBy:{field:SIZE,direction:DESC}){ edges{ size node{ name } } } }
    }
    contributionsCollection{ contributionYears }
  }
}"""


def fetch() -> dict:
    login = CFG["login"]
    u = gql(USER_Q, {"login": login})["user"]
    years = u["contributionsCollection"]["contributionYears"]
    parts = []
    for y in years:
        parts.append(f'y{y}: contributionsCollection(from:"{y}-01-01T00:00:00Z",to:"{y}-12-31T23:59:59Z")'
                     "{contributionCalendar{totalContributions weeks{contributionDays{date contributionCount}}}}")
    yq = "query($login:String!){user(login:$login){" + " ".join(parts) + \
         " last: contributionsCollection{contributionCalendar{totalContributions weeks{contributionDays{date contributionCount weekday}}}}}}"
    c = gql(yq, {"login": login})["user"]
    days = {}
    for y in years:
        for wk in c[f"y{y}"]["contributionCalendar"]["weeks"]:
            for d in wk["contributionDays"]:
                days[d["date"]] = d["contributionCount"]
    return {
        "fetched_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "user": u,
        "years": {str(y): c[f"y{y}"]["contributionCalendar"]["totalContributions"] for y in years},
        "days": days,
        "last": c["last"]["contributionCalendar"],
    }


def derive(data: dict) -> dict:
    u = data["user"]
    tz = dt.timezone(dt.timedelta(minutes=CFG["timezone_offset_minutes"]))
    now = dt.datetime.fromisoformat(data["fetched_at"]).astimezone(tz)
    today = now.date()
    repos = u["repositories"]["nodes"]
    pub = [r for r in repos if not r["isPrivate"]]

    # streaks: today may still be empty, so the current streak can end yesterday
    days = {dt.date.fromisoformat(k): v for k, v in data["days"].items()}
    cur, d = 0, today
    if days.get(d, 0) == 0:
        d -= dt.timedelta(days=1)
    while days.get(d, 0) > 0:
        cur += 1
        d -= dt.timedelta(days=1)
    longest = run = 0
    for day in sorted(days):
        if day > today:
            break
        run = run + 1 if days[day] > 0 else 0
        longest = max(longest, run)

    langs = Counter()
    for r in repos:
        for e in r["languages"]["edges"]:
            if e["node"]["name"] not in CFG["exclude_languages"]:
                langs[e["node"]["name"]] += e["size"]
    total = sum(langs.values()) or 1
    top = langs.most_common(6)
    lang_rows = [(n, s / total) for n, s in top]
    rest = 1 - sum(p for _, p in lang_rows)
    if rest > 0.005:
        lang_rows.append(("other", rest))

    created = dt.datetime.fromisoformat(u["createdAt"].replace("Z", "+00:00")).astimezone(tz).date()
    months = (today.year - created.year) * 12 + today.month - created.month - (today.day < created.day)
    stars = {r["name"]: r["stargazerCount"] for r in repos}

    weekday_tot = Counter()
    best = (None, 0)
    for wk in data["last"]["weeks"]:
        for dd in wk["contributionDays"]:
            weekday_tot[dd["weekday"]] += dd["contributionCount"]
            if dd["contributionCount"] > best[1]:
                best = (dd["date"], dd["contributionCount"])

    return dict(
        now=now, today=today,
        total_all=sum(data["years"].values()), total_year=data["last"]["totalContributions"],
        streak=cur, longest=longest,
        stars=sum(r["stargazerCount"] for r in pub), n_public=len(pub),
        n_private=len(repos) - len(pub), n_repos=len(repos),
        followers=u["followers"]["totalCount"],
        langs=lang_rows, stars_by_repo=stars,
        lang_by_repo={r["name"]: (r["primaryLanguage"] or {}).get("name", "") for r in repos},
        uptime=f"{months // 12}y {months % 12}m", since=created.strftime("%b %Y"),
        weeks=data["last"]["weeks"],
        top_weekday=["sunday", "monday", "tuesday", "wednesday", "thursday", "friday", "saturday"][
            max(weekday_tot, key=weekday_tot.get) if weekday_tot else 0],
        best_day=best,
        synced=now.strftime("%d %b %Y").lower(),
    )


# ---------------------------------------------------------------- panels ----
def hero(T: dict, D: dict) -> str:
    h = 380
    css = [f"""
@keyframes lin{{from{{opacity:0;transform:translateY(26px)}}}}
.l{{animation:lin .7s {EASE} both}}
.r1{{animation:rise .7s {EASE} .05s both}}
.r2{{animation:rise .7s {EASE} .75s both}}
.r3{{animation:rise .7s {EASE} .95s both}}
.r4{{animation:fade 1s {EASE} 1.2s both}}
"""]
    b = [panel_frame(W, h, T, "h", dots=True)]

    # top strip: path on the left, live status pill on the right
    b.append(f'<text x="28" y="31" class="m u" font-size="11" letter-spacing=".12em" fill="{T["faint"]}">'
             f'{esc(CFG["login"])} <tspan fill="{T["line_strong"]}">/</tspan> readme.md</text>')
    st = CFG["status"]
    tw = MONO.width(st.upper(), 11, ls=.1)
    px = W - 28 - tw - 40
    b.append(f'<rect x="{px:.1f}" y="14.5" width="{tw+40:.1f}" height="25" fill="{T["accent"]}" fill-opacity=".1" '
             f'stroke="{T["accent"]}" stroke-opacity=".45"/>')
    b.append(f'<circle cx="{px+15:.1f}" cy="27" r="3.5" fill="{T["accent"]}" class="png"/>'
             f'<circle cx="{px+15:.1f}" cy="27" r="3.5" fill="{T["accent"]}"/>')
    b.append(f'<text x="{px+28:.1f}" y="31" class="m u" font-size="11" letter-spacing=".1em" '
             f'fill="{T["accent_text"]}">{esc(st)}</text>')
    b.append(f'<rect x="1" y="54" width="{W-2}" height="1" fill="{T["line"]}"/>'
             f'<rect x="1" y="54" width="180" height="1" fill="{T["accent"]}" class="gx"/>')

    # eyebrow
    b.append(f'<g class="r1"><rect x="40" y="94" width="8" height="8" fill="{T["accent"]}"/>'
             f'<text x="58" y="102" class="m u" font-size="12" letter-spacing=".16em" fill="{T["accent_text"]}">'
             f'{esc(CFG["eyebrow"])}</text></g>')

    # name, letter by letter, two-tone
    size, wght, ls = 76, 560, -0.05
    x, i = 38.0, 0
    first, last = CFG["name"]
    for part, color in ((first, T["text"]), (" " + last, T["muted"])):
        for ch in part:
            if ch != " ":
                b.append(f'<text x="{x:.1f}" y="178" class="s l" style="animation-delay:{.12+i*.045:.3f}s" '
                         f'font-size="{size}" font-weight="{wght}" fill="{color}">{esc(ch)}</text>')
            x += SANS.width(ch, size, wght) + ls * size
            i += 1

    # rotating "i build ___" line
    pre = CFG["rotating_prefix"] + " "
    words = CFG["rotating"]
    fs = 26
    pw = SANS.width(pre, fs, 400)
    step = 2.6
    period = step * len(words)
    a = 100 / len(words)
    css.append(f"""
@keyframes rot{{0%{{opacity:0;transform:translateY(30px)}}{a*.1:.2f}%{{opacity:1;transform:translateY(0)}}
{a*.86:.2f}%{{opacity:1;transform:translateY(0)}}{a:.2f}%,100%{{opacity:0;transform:translateY(-30px)}}}}
.w{{animation:rot {period:.1f}s {EASE} infinite both}}
.w:not(.w0){{opacity:0}}""")
    b.append(f'<defs><clipPath id="rc"><rect x="36" y="200" width="580" height="46"/></clipPath></defs>')
    b.append(f'<g class="r2"><text x="40" y="232" class="s" font-size="{fs}" fill="{T["muted"]}">{esc(pre)}</text>'
             f'<g clip-path="url(#rc)">')
    for k, wd in enumerate(words):
        ww = SANS.width(wd, fs, 500)
        b.append(f'<g class="w w{k}" style="animation-delay:{k*step:.1f}s">'
                 f'<text x="{40+pw:.1f}" y="232" class="s" font-size="{fs}" font-weight="500" fill="{T["text"]}">{esc(wd)}</text>'
                 f'<rect x="{40+pw:.1f}" y="240" width="{ww:.1f}" height="2" fill="{T["accent"]}"/></g>')
    b.append("</g></g>")

    # tagline with a block caret
    tg = "// " + CFG["tagline"]
    tgw = MONO.width(tg, 14)
    b.append(f'<g class="r3"><text x="40" y="288" class="m" font-size="14" fill="{T["faint"]}">{esc(tg)}</text>'
             f'<rect x="{44+tgw:.1f}" y="276" width="8" height="15" fill="{T["accent"]}" class="cur"/></g>')

    # meta row
    mx = 40
    row = ['<g class="r4">']
    for m in CFG["meta"]:
        k, v = m.split("  ", 1)
        row.append(f'<text x="{mx}" y="338" class="m u" font-size="11" letter-spacing=".12em" fill="{T["faint"]}">'
                   f'{esc(k)} <tspan fill="{T["muted"]}">{esc(v)}</tspan></text>')
        mx += MONO.width(f"{k} {v}".upper(), 11, ls=.12) + 30
    row.append("</g>")
    b.extend(row)

    b.append(iso_field(T))
    return svg_doc(W, h, "".join(b), f'{" ".join(CFG["name"])}: {CFG["eyebrow"]}', "".join(css))


def iso_field(T: dict) -> str:
    """Isometric field: a cell turns red (detected), an indigo wave rolls out
    from it, the cell goes indigo (contained), then the field rests. 7s loop."""
    n, hw, hh, depth = 7, 23, 11.5, 12
    ox, oy = 798, 104
    threat = (4, 2)
    period = 7.0
    css = f"""
<style>
@keyframes wave{{0%,40%{{transform:translateY(0)}}46%{{transform:translateY(-9px)}}58%,100%{{transform:translateY(0)}}}}
@keyframes wtop{{0%,40%{{fill:{T["cell_top"]}}}46%{{fill:{T["accent"]}}}62%,100%{{fill:{T["cell_top"]}}}}}
@keyframes thr{{0%,9%{{fill:{T["cell_top"]}}}12%,44%{{fill:{T["threat"]}}}50%,76%{{fill:{T["accent"]}}}86%,100%{{fill:{T["cell_top"]}}}}}
@keyframes tring{{0%,10%{{transform:scale(.6);opacity:0}}12%{{opacity:.95}}38%,100%{{transform:scale(3.4);opacity:0}}}}
@keyframes st0{{0%,9%{{opacity:1}}11%,86%{{opacity:0}}90%,100%{{opacity:1}}}}
@keyframes st1{{0%,10%{{opacity:0}}12%,44%{{opacity:1}}47%,100%{{opacity:0}}}}
@keyframes st2{{0%,47%{{opacity:0}}50%,84%{{opacity:1}}87%,100%{{opacity:0}}}}
.cb{{animation:wave {period}s {EASE} infinite}}
.ct{{animation:wtop {period}s {EASE} infinite}}
.tt{{animation:thr {period}s {EASE} infinite}}
.tr{{transform-box:fill-box;transform-origin:center;animation:tring {period}s {EASE_PING} infinite;opacity:0}}
.s0{{animation:st0 {period}s linear infinite}}
.s1{{animation:st1 {period}s linear infinite;opacity:0}}
.s2{{animation:st2 {period}s linear infinite;opacity:0}}
</style>"""
    out = [css, '<g class="r4">']
    cells = sorted(((i, j) for i in range(n) for j in range(n)), key=lambda c: (c[0] + c[1], c[0]))
    for i, j in cells:
        cx = ox + (i - j) * hw
        cy = oy + (i + j) * hh + hh
        dist = math.hypot(i - threat[0], j - threat[1])
        delay = dist * 0.11
        top = f"{cx},{cy-hh} {cx+hw},{cy} {cx},{cy+hh} {cx-hw},{cy}"
        left = f"{cx-hw},{cy} {cx},{cy+hh} {cx},{cy+hh+depth} {cx-hw},{cy+depth}"
        right = f"{cx},{cy+hh} {cx+hw},{cy} {cx+hw},{cy+depth} {cx},{cy+hh+depth}"
        is_t = (i, j) == threat
        tcls = "tt" if is_t else "ct"
        gstyle = "" if is_t else f' style="animation-delay:{delay:.2f}s"'
        out.append(f'<g class="{"" if is_t else "cb"}"{gstyle}>'
                   f'<polygon points="{left}" fill="{T["cell_left"]}" stroke="{T["bg"]}" stroke-width=".8"/>'
                   f'<polygon points="{right}" fill="{T["cell_right"]}" stroke="{T["bg"]}" stroke-width=".8"/>'
                   f'<polygon class="{tcls}"{gstyle} points="{top}" fill="{T["cell_top"]}" stroke="{T["bg"]}" stroke-width=".8"/></g>')
    tx = ox + (threat[0] - threat[1]) * hw
    ty = oy + (threat[0] + threat[1]) * hh + hh
    out.append(f'<ellipse class="tr" cx="{tx}" cy="{ty}" rx="{hw}" ry="{hh}" stroke="{T["threat"]}" stroke-width="1.5"/>')
    # caption under the field
    cy = 338
    out.append(f'<text x="652" y="{cy}" class="m u" font-size="11" letter-spacing=".12em" fill="{T["faint"]}">'
               f'{esc(CFG["field_label"])}</text>')
    for k, (label, color) in enumerate((("monitoring", T["faint"]), ("threat detected", T["threat_text"]),
                                        ("contained", T["accent_text"]))):
        out.append(f'<g class="s{k}"><rect x="{W-40-MONO.width(label.upper(), 11, ls=.12)-14:.1f}" y="{cy-8}" '
                   f'width="7" height="7" fill="{color}"/>'
                   f'<text x="{W-40}" y="{cy}" text-anchor="end" class="m u" font-size="11" letter-spacing=".12em" '
                   f'fill="{color}">{esc(label)}</text></g>')
    out.append("</g>")
    return "".join(out)


def whoami(T: dict, D: dict) -> str:
    rows = []
    for k, v, c in CFG["whoami"]:
        fill = dict(uptime=D["uptime"], since=D["since"], public=D["n_public"], private=D["n_private"],
                    status=CFG["status"])
        rows.append((k, v.format(**fill), c.format(**fill)))
    lh = 26
    top = 70
    h = top + 30 + (len(rows) + 1) * lh + 30
    cmd = f"cat {CFG['whoami_path']}"
    cw = MONO.width("0", 13)
    type_dur = len(cmd) * 0.035
    css = f"""
@keyframes typ{{from{{width:0}}}}
.ty{{animation:typ {type_dur:.2f}s steps({len(cmd)}) .3s both}}
.ln{{animation:rise .45s {EASE} both}}
"""
    b = [panel_frame(W, h, T, "w", "01", "whoami", CFG["whoami_path"])]
    y = top + 18
    b.append(f'<defs><clipPath id="tc"><rect class="ty" x="{64+cw*2:.1f}" y="{y-16}" width="{cw*len(cmd)+2:.1f}" height="22"/></clipPath></defs>')
    b.append(f'<text x="28" y="{y}" class="m" font-size="13" fill="{T["faint"]}">00</text>'
             f'<text x="64" y="{y}" class="m" font-size="13" fill="{T["accent_text"]}">$</text>'
             f'<text x="{64+cw*2:.1f}" y="{y}" class="m" font-size="13" fill="{T["text"]}" clip-path="url(#tc)">{esc(cmd)}</text>')
    start = .3 + type_dur + .15
    key_w = max(len(k) for k, _, _ in rows) + 2
    for n, (k, v, c) in enumerate(rows, 1):
        y += lh
        delay = start + n * 0.07
        vx = 64 + cw * (key_w + 1)
        line = [f'<g class="ln" style="animation-delay:{delay:.2f}s">',
                f'<text x="28" y="{y}" class="m" font-size="13" fill="{T["line_strong"]}">{n:02d}</text>',
                f'<text x="64" y="{y}" class="m" font-size="13" fill="{T["accent_text"]}">{esc(k)}<tspan fill="{T["faint"]}">:</tspan></text>',
                f'<text x="{vx:.1f}" y="{y}" class="m" font-size="13" fill="{T["text"]}">{esc(v)}']
        if c:
            pad = max(0, 48 - len(v))
            line.append(f'<tspan fill="{T["faint"]}">{"&#160;" * pad}  # {esc(c)}</tspan>')
        line.append("</text></g>")
        b.append("".join(line))
    y += lh + 6
    d = start + (len(rows) + 1) * 0.07
    b.append(f'<g class="ln" style="animation-delay:{d:.2f}s"><text x="28" y="{y}" class="m" font-size="13" '
             f'fill="{T["line_strong"]}">{len(rows)+1:02d}</text>'
             f'<text x="64" y="{y}" class="m" font-size="13" fill="{T["accent_text"]}">$</text>'
             f'<rect x="{64+cw*2:.1f}" y="{y-12}" width="8" height="15" fill="{T["accent"]}" class="cur"/></g>')
    return svg_doc(W, h, "".join(b), "whoami: " + "; ".join(f"{k}: {v}" for k, v, _ in rows), css)


def stack(T: dict, D: dict) -> str:
    x0, x1 = 200, W - 32
    ph, gap, rowgap = 30, 8, 14
    layout, y = [], 72
    for grp in CFG["stack"]:
        x, gy = x0, y
        pills = []
        for it in grp["items"]:
            pw = MONO.width(it, 12) + 28
            if x + pw > x1:
                x, gy = x0, gy + ph + gap
            pills.append((x, gy, pw, it))
            x += pw + gap
        layout.append((grp["label"], y, pills))
        y = gy + ph + rowgap + 10
    h = y + 14
    total = sum(len(p) for _, _, p in layout)
    period = 16
    css = f"""
@keyframes flash{{0%{{fill-opacity:0;stroke:{T["line"]}}}3%{{fill-opacity:.16;stroke:{T["accent"]}}}9%,100%{{fill-opacity:0;stroke:{T["line"]}}}}}
@keyframes ftxt{{0%{{fill:{T["text"]}}}3%{{fill:{T["accent_text"]}}}9%,100%{{fill:{T["text"]}}}}}
.pl{{animation:rise .5s {EASE} both}}
.pb{{animation:flash {period}s {EASE} infinite}}
.pt{{animation:ftxt {period}s {EASE} infinite}}
"""
    b = [panel_frame(W, h, T, "k", "02", "stack", f"{total} tools · 4 domains")]
    k = 0
    for label, ly, pills in layout:
        b.append(f'<text x="28" y="{ly+19}" class="m u" font-size="11" letter-spacing=".12em" fill="{T["faint"]}">'
                 f'<tspan fill="{T["accent_text"]}">›</tspan> {esc(label)}</text>')
        for px, py, pw, it in pills:
            delay = .2 + k * .028
            fd = 2 + k * (period * 0.85 / total)
            b.append(f'<g class="pl" style="animation-delay:{delay:.3f}s">'
                     f'<rect class="pb" style="animation-delay:{fd:.2f}s" x="{px+.5:.1f}" y="{py+.5}" width="{pw-1:.1f}" '
                     f'height="{ph-1}" fill="{T["accent"]}" fill-opacity="0" stroke="{T["line"]}"/>'
                     f'<text class="m pt" style="animation-delay:{fd:.2f}s" x="{px+14:.1f}" y="{py+19.5}" font-size="12" '
                     f'fill="{T["text"]}">{esc(it)}</text></g>')
            k += 1
    alt = "stack: " + "; ".join(f'{g["label"]}: {", ".join(g["items"])}' for g in CFG["stack"])
    return svg_doc(W, h, "".join(b), alt, css)


def flap_number(T: dict, x: float, y: float, value: int, uid: str, delay: float, tile_w=40, tile_h=58) -> tuple[str, float]:
    """Split-flap / odometer digits. Returns (svg, width)."""
    s = f"{value:,}"
    out, cx = [], x
    fs = 40
    k = 0
    for ch in s:
        if ch == ",":
            out.append(f'<text x="{cx+1:.1f}" y="{y+tile_h-10}" class="s" font-size="{fs*0.7:.0f}" fill="{T["faint"]}">,</text>')
            cx += 10
            continue
        d = int(ch)
        steps = 10 + d
        cid = f"fc{uid}{k}"
        out.append(f'<clipPath id="{cid}"><rect x="{cx:.1f}" y="{y}" width="{tile_w}" height="{tile_h}"/></clipPath>')
        out.append(f'<rect x="{cx:.1f}" y="{y}" width="{tile_w}" height="{tile_h}" fill="{T["surface"]}"/>')
        col = [f'<g clip-path="url(#{cid})"><g class="fl" style="transform:translateY(-{steps*tile_h}px);'
               f'animation-delay:{delay + k*0.09:.2f}s;animation-duration:{1.3 + k*0.18:.2f}s">']
        for m in range(steps + 1):
            col.append(f'<text x="{cx+tile_w/2:.1f}" y="{y + 42 + m*tile_h}" text-anchor="middle" class="s" '
                       f'font-size="{fs}" font-weight="560" fill="{T["text"]}">{m % 10}</text>')
        col.append("</g></g>")
        out.append("".join(col))
        out.append(f'<rect x="{cx:.1f}" y="{y+tile_h/2-.5:.1f}" width="{tile_w}" height="1" fill="{T["bg"]}" fill-opacity=".8"/>')
        cx += tile_w + 4
        k += 1
    return "".join(out), cx - x


def telemetry(T: dict, D: dict) -> str:
    h = 330
    css = f"""
@keyframes roll{{from{{transform:translateY(0)}}}}
.fl{{animation-name:roll;animation-timing-function:cubic-bezier(.2,.9,.3,1);animation-fill-mode:both}}
.lg{{animation:fade .5s {EASE} both}}
"""
    b = [panel_frame(W, h, T, "t", "03", "telemetry", f"synced {D['synced']}")]
    tiles = [
        ("contributions", D["total_all"], f"{D['total_year']:,} in the last year"),
        ("current streak", D["streak"], f"days · longest {D['longest']}"),
        ("stars earned", D["stars"], f"across {D['n_public']} public repos"),
        ("repositories", D["n_repos"], f"{D['n_public']} public · {D['n_private']} private"),
    ]
    tw = (W - 56) / 4
    for i, (label, val, sub) in enumerate(tiles):
        x = 28 + i * tw
        if i:
            b.append(f'<rect x="{x:.1f}" y="66" width="1" height="128" fill="{T["line"]}"/>')
        ix = x + (18 if i else 0)
        b.append(f'<text x="{ix:.1f}" y="80" class="m u" font-size="11" letter-spacing=".12em" fill="{T["faint"]}">{esc(label)}</text>')
        num, _ = flap_number(T, ix, 96, val, f"t{i}", .25 + i * .15)
        b.append(num)
        b.append(f'<text x="{ix:.1f}" y="180" class="m" font-size="12" fill="{T["muted"]}">{esc(sub)}</text>')

    # languages
    y = 222
    b.append(f'<text x="28" y="{y}" class="m u" font-size="11" letter-spacing=".12em" fill="{T["faint"]}">'
             f'languages <tspan fill="{T["line_strong"]}">·</tspan> by bytes, own repos</text>')
    shades = [1, .78, .6, .45, .33, .23, .14]
    bx, bw = 28, W - 56
    x = bx
    for i, (name, p) in enumerate(D["langs"]):
        w = max(bw * p - 2, 1)
        color, op = (T["line_strong"], .5) if name == "other" else (T["accent"], shades[i])
        b.append(f'<rect x="{x:.1f}" y="{y+14}" width="{w:.1f}" height="10" fill="{color}" fill-opacity="{op}" '
                 f'class="gx" style="animation-delay:{.4 + i*.12:.2f}s"/>')
        x += bw * p
    lx, ly = 28, y + 54
    colw = (W - 56) / 4
    for i, (name, p) in enumerate(D["langs"]):
        cx = lx + (i % 4) * colw
        cy = ly + (i // 4) * 24
        color, op = (T["line_strong"], .5) if name == "other" else (T["accent"], shades[i])
        b.append(f'<g class="lg" style="animation-delay:{.6 + i*.08:.2f}s">'
                 f'<rect x="{cx:.1f}" y="{cy-9}" width="9" height="9" fill="{color}" fill-opacity="{op}"/>'
                 f'<text x="{cx+17:.1f}" y="{cy}" class="m" font-size="12" fill="{T["text"]}">{esc(name.lower())} '
                 f'<tspan fill="{T["faint"]}">{p*100:.1f}%</tspan></text></g>')
    alt = (f"{D['total_all']:,} contributions all time, {D['total_year']:,} in the last year; "
           f"current streak {D['streak']} days, longest {D['longest']}; {D['stars']} stars; "
           f"{D['n_repos']} repositories. Languages: " + ", ".join(f"{n} {p*100:.1f}%" for n, p in D["langs"]))
    return svg_doc(W, h, "".join(b), alt, css)


def activity(T: dict, D: dict) -> str:
    weeks = D["weeks"][-53:]
    cs, gap = 13, 4
    pitch = cs + gap
    x0, y0 = 66, 92
    h = y0 + 7 * pitch + 64
    counts = [d["contributionCount"] for wk in weeks for d in wk["contributionDays"]]
    nz = sorted(c for c in counts if c > 0)

    def level(c):
        if c <= 0:
            return 0
        q = [nz[int(len(nz) * f)] for f in (.25, .5, .75)] if nz else [1, 2, 3]
        return 1 + sum(c > t for t in q)

    scan = 6.0
    css = f"""
@keyframes rip{{from{{opacity:0;transform:scale(.3)}}}}
@keyframes glint{{0%,100%{{opacity:0}}2%{{opacity:.95}}9%{{opacity:0}}}}
@keyframes scan{{from{{transform:translateX(0)}}to{{transform:translateX({53*pitch}px)}}}}
.c{{transform-box:fill-box;transform-origin:center;animation:rip .5s {EASE_POP} both}}
.g{{animation:glint {scan}s linear infinite;opacity:0}}
.sc{{animation:scan {scan}s linear infinite}}
"""
    b = [panel_frame(W, h, T, "a", "04", "activity", f"{D['total_year']:,} contributions · last 12 months")]
    b.append(f'<defs><linearGradient id="sg" x1="0" x2="1"><stop offset="0" stop-color="{T["accent"]}" stop-opacity="0"/>'
             f'<stop offset="1" stop-color="{T["accent"]}" stop-opacity=".35"/></linearGradient>'
             f'<clipPath id="hc"><rect x="{x0-4}" y="{y0-4}" width="{53*pitch+4}" height="{7*pitch+4}"/></clipPath></defs>')
    for wi, wk in enumerate(weeks):
        firsts = [dt.date.fromisoformat(d["date"]) for d in wk["contributionDays"]]
        firsts = [d for d in firsts if d.day == 1]
        if firsts and wi < 51:
            b.append(f'<text x="{x0 + wi*pitch}" y="{y0-12}" class="m" font-size="11" fill="{T["faint"]}">'
                     f'{firsts[0].strftime("%b").lower()}</text>')
        for d in wk["contributionDays"]:
            r = d["weekday"]
            x, y = x0 + wi * pitch, y0 + r * pitch
            lv = level(d["contributionCount"])
            b.append(f'<rect class="c" style="animation-delay:{(wi + r*2)*0.011:.3f}s" x="{x}" y="{y}" width="{cs}" '
                     f'height="{cs}" fill="{T["heat"][lv]}"><title>{d["date"]}: {d["contributionCount"]}</title></rect>')
            if lv:
                b.append(f'<rect class="g" style="animation-delay:{1.2 + wi*scan/53:.2f}s" x="{x-1.5}" y="{y-1.5}" '
                         f'width="{cs+3}" height="{cs+3}" stroke="{T["accent_text"]}" fill="none"/>')
    for r, lab in ((1, "mon"), (3, "wed"), (5, "fri")):
        b.append(f'<text x="28" y="{y0 + r*pitch + 10}" class="m" font-size="11" fill="{T["faint"]}">{lab}</text>')
    b.append(f'<g clip-path="url(#hc)"><g class="sc" style="animation-delay:1.2s">'
             f'<rect x="{x0-40}" y="{y0-4}" width="40" height="{7*pitch}" fill="url(#sg)"/>'
             f'<rect x="{x0-1}" y="{y0-4}" width="1.5" height="{7*pitch}" fill="{T["accent"]}"/></g></g>')
    fy = y0 + 7 * pitch + 30
    bd, bc = D["best_day"]
    best = dt.date.fromisoformat(bd).strftime("%d %b %Y").lower() if bd else "-"
    b.append(f'<text x="28" y="{fy}" class="m u" font-size="11" letter-spacing=".1em" fill="{T["faint"]}">'
             f'busiest weekday <tspan fill="{T["text"]}">{D["top_weekday"]}</tspan>   '
             f'<tspan fill="{T["line_strong"]}">/</tspan>   best day <tspan fill="{T["text"]}">{best} ({bc})</tspan>   '
             f'<tspan fill="{T["line_strong"]}">/</tspan>   streak <tspan fill="{T["accent_text"]}">{D["streak"]}d</tspan></text>')
    lx = W - 28 - 5 * 17 - 34
    b.append(f'<text x="{lx-8}" y="{fy}" text-anchor="end" class="m u" font-size="11" letter-spacing=".1em" fill="{T["faint"]}">less</text>')
    for i in range(5):
        b.append(f'<rect x="{lx + i*17}" y="{fy-11}" width="13" height="13" fill="{T["heat"][i]}"/>')
    b.append(f'<text x="{W-28}" y="{fy}" text-anchor="end" class="m u" font-size="11" letter-spacing=".1em" fill="{T["faint"]}">more</text>')
    alt = f"contribution heatmap: {D['total_year']:,} contributions in the last 12 months, current streak {D['streak']} days"
    return svg_doc(W, h, "".join(b), alt, css)


def section(T: dict, index: str, title: str, meta: str) -> str:
    h = 46
    b = [f'<text x="0" y="22" class="m u" font-size="11" letter-spacing=".12em" fill="{T["faint"]}">'
         f'<tspan fill="{T["accent_text"]}">{esc(index)}</tspan>  /  {esc(title)}</text>',
         f'<text x="{W}" y="22" text-anchor="end" class="m u" font-size="11" letter-spacing=".12em" fill="{T["faint"]}">{esc(meta)}</text>',
         f'<rect x="0" y="36" width="{W}" height="1" fill="{T["line"]}"/>',
         f'<rect x="0" y="36" width="{W*.18:.0f}" height="1" fill="{T["accent"]}" class="gx"/>']
    return svg_doc(W, h, "".join(b), f"{index} {title}")


def card(T: dict, D: dict, i: int, p: dict) -> str:
    cw, h = 490, 196
    name = p["repo"]
    stars = D["stars_by_repo"].get(name, 0)
    lang = D["lang_by_repo"].get(name, "") or "-"
    css = f"""
@keyframes run{{0%{{transform:translateX(-80px)}}55%,100%{{transform:translateX({cw}px)}}}}
@keyframes nudge{{0%,70%,100%{{transform:translate(0,0)}}80%{{transform:translate(3px,-3px)}}}}
.rn{{animation:run 4.5s cubic-bezier(.65,0,.35,1) infinite}}
.ar{{animation:nudge 3s {EASE} infinite}}
.ci{{animation:rise .6s {EASE} both}}
"""
    b = [panel_frame(cw, h, T, f"c{i}")]
    b.append(f'<defs><clipPath id="tp{i}"><rect x="0" y="0" width="{cw}" height="2"/></clipPath>'
             f'<linearGradient id="rg{i}" x1="0" x2="1"><stop offset="0" stop-color="{T["accent"]}" stop-opacity="0"/>'
             f'<stop offset="1" stop-color="{T["accent"]}"/></linearGradient></defs>')
    b.append(f'<g clip-path="url(#tp{i})"><rect class="rn" style="animation-delay:{i*.7:.1f}s" x="0" y="0" width="80" height="2" fill="url(#rg{i})"/></g>')
    b.append(f'<g class="ci" style="animation-delay:{.1 + i*.08:.2f}s">')
    b.append(f'<text x="24" y="34" class="m u" font-size="11" letter-spacing=".12em" fill="{T["faint"]}">'
             f'{i+1:02d}  <tspan fill="{T["accent_text"]}">{esc(p["tag"])}</tspan></text>')
    sw = MONO.width(str(stars), 12)
    b.append(f'<path d="{star_path(cw-30-sw, 29.5, 6)}" fill="{T["accent"] if stars else "none"}" '
             f'stroke="{T["accent"] if stars else T["line_strong"]}" stroke-width="1"/>'
             f'<text x="{cw-24}" y="34" text-anchor="end" class="m" font-size="12" fill="{T["muted"]}">{stars}</text>')
    b.append(f'<text x="24" y="76" class="s" font-size="25" font-weight="560" letter-spacing="-.02em" fill="{T["text"]}">{esc(name)}</text>')
    for k, line in enumerate(wrap(p["desc"], SANS, 14, cw - 48)[:3]):
        b.append(f'<text x="24" y="{106 + k*21}" class="s" font-size="14" fill="{T["muted"]}">{esc(line)}</text>')
    b.append(f'<rect x="1" y="{h-40}" width="{cw-2}" height="1" fill="{T["line"]}"/>')
    b.append(f'<rect x="24" y="{h-24}" width="8" height="8" fill="{T["accent"]}" fill-opacity=".7"/>'
             f'<text x="40" y="{h-16}" class="m u" font-size="11" letter-spacing=".1em" fill="{T["muted"]}">{esc(lang)}</text>')
    b.append(f'<text x="{cw-46}" y="{h-16}" text-anchor="end" class="m" font-size="11" fill="{T["faint"]}">'
             f'github.com/{esc(CFG["login"])}/{esc(name)}</text>')
    b.append(arrow_ne(cw - 36, h - 26, 10, T["accent_text"], "ar"))
    b.append("</g>")
    return svg_doc(cw, h, "".join(b), f"{name}: {p['desc']}", css)


def link_button(T: dict, i: int, label: str) -> str:
    tw = MONO.width(label.upper(), 12, ls=.14)
    w, h = int(tw + 64), 40
    css = f"""
@keyframes nudge{{0%,70%,100%{{transform:translate(0,0)}}80%{{transform:translate(3px,-3px)}}}}
.ar{{animation:nudge 3s {EASE} infinite}}"""
    b = [f'<rect x=".5" y=".5" width="{w-1}" height="{h-1}" fill="{T["bg"]}" stroke="{T["line_strong"]}"/>',
         f'<text x="18" y="25" class="m u" font-size="12" letter-spacing=".14em" fill="{T["text"]}">{esc(label)}</text>',
         f'<g class="ar" style="animation-delay:{i*.35:.2f}s">{arrow_ne(w-30, 15, 9, T["accent_text"])}</g>']
    return svg_doc(w, h, "".join(b), label, css)


def footer(T: dict, D: dict) -> str:
    h = 130
    mid = W / 2
    css = f"""
@keyframes flowl{{from{{stroke-dashoffset:0}}to{{stroke-dashoffset:-220}}}}
@keyframes flowr{{from{{stroke-dashoffset:0}}to{{stroke-dashoffset:220}}}}
@keyframes hit{{0%,40%{{fill:{T["threat"]}}}55%,100%{{fill:{T["accent"]}}}}}
.fa{{animation:flowl 3.2s linear infinite}}
.fb{{animation:flowr 3.2s linear infinite}}
.hb{{animation:hit 3.2s linear infinite}}
"""
    b = []
    lab = "end of transmission"
    lw = MONO.width(lab.upper(), 12, ls=.18)
    gapw = lw / 2 + 36
    for k, dy in enumerate((-18, 0, 18)):
        y = 56 + dy
        # converging curves from both edges to the centre label
        b.append(f'<path d="M0 {y}C{mid*.45} {y} {mid*.6} 56 {mid-gapw} 56" stroke="{T["line"]}"/>'
                 f'<path d="M{W} {y}C{W-mid*.45} {y} {W-mid*.6} 56 {mid+gapw} 56" stroke="{T["line"]}"/>')
        b.append(f'<path class="fa" style="animation-delay:{k*.5:.1f}s" d="M0 {y}C{mid*.45} {y} {mid*.6} 56 {mid-gapw} 56" '
                 f'stroke="{T["accent"]}" stroke-width="1.5" stroke-dasharray="36 184"/>'
                 f'<path class="fb" style="animation-delay:{k*.5+.25:.2f}s" d="M{W} {y}C{W-mid*.45} {y} {W-mid*.6} 56 {mid+gapw} 56" '
                 f'stroke="{T["accent"]}" stroke-width="1.5" stroke-dasharray="36 184"/>')
    b.append(f'<rect x="{mid-gapw+8:.1f}" y="40.5" width="{2*gapw-16:.1f}" height="31" fill="{T["bg"]}" stroke="{T["line_strong"]}"/>')
    b.append(f'<rect class="hb" x="{mid-lw/2-14:.1f}" y="52" width="7" height="7" fill="{T["accent"]}"/>')
    b.append(f'<text x="{mid+4:.1f}" y="61" text-anchor="middle" class="m u" font-size="12" letter-spacing=".18em" '
             f'fill="{T["text"]}">{lab}</text>')
    b.append(f'<text x="{mid}" y="112" text-anchor="middle" class="m" font-size="12" fill="{T["faint"]}">'
             f'built from live github data · rebuilt by actions · last sync {D["synced"]}</text>')
    return svg_doc(W, h, "".join(b), "end of transmission", css)


# ---------------------------------------------------------------- readme ----
def pic(name: str, alt: str, width: str | None = None) -> str:
    w = f' width="{width}"' if width else ""
    return (f'<picture><source media="(prefers-color-scheme: dark)" srcset="assets/{name}-dark.svg">'
            f'<source media="(prefers-color-scheme: light)" srcset="assets/{name}-light.svg">'
            f'<img alt="{esc(alt)}" src="assets/{name}-dark.svg"{w}></picture>')


def readme(D: dict) -> str:
    login = CFG["login"]
    out = ["<!--\n  generated by scripts/build.py from scripts/profile.json and live GitHub data;\n"
           "  rebuilt by .github/workflows/profile.yml. edit profile.json, not this file.\n-->\n",
           '<div align="center">\n\n',
           pic("hero", f'{" ".join(CFG["name"])}: {CFG["eyebrow"]}. {CFG["tagline"]}', "100%"), "\n\n",
           " ".join(f'<a href="{esc(l["url"])}">{pic("link-" + l["label"], l["label"])}</a>' for l in CFG["links"]),
           "\n\n<br>\n\n"]
    for name, alt in (("whoami", "whoami"), ("stack", "stack"), ("telemetry", "github telemetry"),
                      ("activity", "contribution activity"), ("work", "selected work")):
        out += [pic(name, alt, "100%"), "\n\n"]
    ps = CFG["projects"]
    for i in range(0, len(ps), 2):
        # both cards on one source line: a newline would become a <br> in some renderers
        out.append(" ".join(f'<a href="https://github.com/{login}/{p["repo"]}">'
                            f'{pic("card-" + p["repo"].lower(), p["repo"] + ": " + p["desc"], "49%")}</a>'
                            for p in ps[i:i + 2]))
        out.append("\n\n")
    out.append("</div>\n\n")
    if CFG.get("more_repos"):
        out.append("<details>\n<summary><sub>&nbsp;more repositories</sub></summary>\n<br>\n\n| repo | what |\n|---|---|\n")
        for r, what in CFG["more_repos"]:
            out.append(f"| [{r}](https://github.com/{login}/{r}) | {what} |\n")
        out.append("\n</details>\n\n")
    out += ['<div align="center">\n\n', pic("footer", "end of transmission", "100%"), "\n\n</div>\n"]
    return "".join(out)


# ------------------------------------------------------------------ main ----
def main() -> None:
    os.makedirs(ASSETS, exist_ok=True)
    cache = os.path.join(ASSETS, "data.json")
    if "--offline" in sys.argv:
        data = json.load(open(cache))
    else:
        data = fetch()
        # keep the cache free of private repo names: only aggregates are needed offline
        safe = json.loads(json.dumps(data))
        for r in safe["user"]["repositories"]["nodes"]:
            if r["isPrivate"]:
                r["name"] = "private"
        json.dump(safe, open(cache, "w"), indent=1)
    D = derive(data)

    out = {}
    for mode, T in THEMES.items():
        out[f"hero-{mode}"] = hero(T, D)
        out[f"whoami-{mode}"] = whoami(T, D)
        out[f"stack-{mode}"] = stack(T, D)
        out[f"telemetry-{mode}"] = telemetry(T, D)
        out[f"activity-{mode}"] = activity(T, D)
        out[f"work-{mode}"] = section(T, "05", "selected work",
                                      f"{D['n_public']} public repos · {D['stars']} stars")
        out[f"footer-{mode}"] = footer(T, D)
        for i, p in enumerate(CFG["projects"]):
            out[f"card-{p['repo'].lower()}-{mode}"] = card(T, D, i, p)
        for i, l in enumerate(CFG["links"]):
            out[f"link-{l['label']}-{mode}"] = link_button(T, i, l["label"])
    for name, svg in out.items():
        with open(os.path.join(ASSETS, f"{name}.svg"), "w", encoding="utf-8") as f:
            f.write(svg)
    with open(os.path.join(ROOT, "README.md"), "w", encoding="utf-8") as f:
        f.write(readme(D))
    total = sum(len(s) for s in out.values())
    print(f"wrote {len(out)} svgs ({total/1024:.0f} KB) · {D['total_all']} contributions · "
          f"streak {D['streak']} · {D['stars']} stars · {D['n_repos']} repos")


if __name__ == "__main__":
    main()
