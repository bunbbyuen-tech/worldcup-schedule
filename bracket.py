"""
Knockout bracket PNG generator for the World Cup 2026 family dashboard.

Two jobs:
  1. RESOLVE — turn the schedule's placeholder tokens (1E / 2A / 3A/B/C/D/F /
     W74 / L101) into real team names as the tournament fills in. Group winners
     and runners-up come from our own standings the moment a group finishes;
     match winners/losers come from finished knockout results (recursively).
     Anything not yet known stays a short placeholder.
  2. DRAW — render the classic two-sided bracket (the screenshot layout) to a
     PNG: 32強 → 16強 → 8強 → 4強 on each side, meeting at 決賽 in the centre.

Pure Pillow so it renders identically on macOS (dev) and Streamlit Cloud
(Linux, via fonts-noto-cjk in packages.txt). Chinese team names, no flags.
"""

import io
import re
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

import api

# Each side of the bracket, top-to-bottom, matching the official 2026 layout
# (and the reference screenshot). Numbers are the schedule's Round-of-32 `num`.
LEFT_R32 = [74, 77, 73, 75, 83, 84, 81, 82]
RIGHT_R32 = [76, 78, 79, 80, 86, 88, 85, 87]

# The feed tree: which two match numbers each later match takes its teams from.
R16_FEEDS = {89: (74, 77), 90: (73, 75), 93: (83, 84), 94: (81, 82),
             91: (76, 78), 92: (79, 80), 95: (86, 88), 96: (85, 87)}
QF_FEEDS = {97: (89, 90), 98: (93, 94), 99: (91, 92), 100: (95, 96)}
SF_FEEDS = {101: (97, 98), 102: (99, 100)}
FINAL_NUM = 104   # W101 vs W102
THIRD_NUM = 103   # L101 vs L102

GROUP_MATCHES = 6   # matches per group; a group is "settled" once all 6 are done

# FIFA Annex C — best-third-place allocation to the Round of 32.
# openfootball leaves these eight slots as combo placeholders (e.g. "3A/B/C/D/F")
# until it manually fills the real teams, which lags the group stage by days.
# Once the group stage finished, the eight best third-placed teams came from
# groups B, D, E, F, I, J, K, L, and Annex C fixes exactly which group's third
# team meets which group winner. We apply it ourselves so the bracket fills the
# moment the groups settle. GUARDED: only applied if our own standings reproduce
# this same qualifying set — if the data ever differs, we fall back to the
# placeholder rather than show a wrong team.
# Source: 2026 FIFA World Cup knockout stage, Annex C combination table
# (en.wikipedia.org/wiki/2026_FIFA_World_Cup_knockout_stage), verified 2026-06-28.
THIRD_QUALIFIED = frozenset("BDEFIJKL")
THIRD_SLOT_GROUP = {74: "D", 77: "F", 79: "E", 80: "K",
                    81: "B", 82: "I", 85: "J", 87: "L"}


# ----------------------------------------------------------------------------
# Resolution
# ----------------------------------------------------------------------------
def _group_ranks():
    """{group_letter: [rank1_team_zh, rank2_team_zh]} for settled groups only."""
    groups, _ = api.load_standings()
    ranks = {}
    for g in groups:
        # g["name"] looks like "A 組"; first char is the group letter.
        letter = g["name"].split()[0]
        rows = g["rows"]
        played = sum(r["played"] for r in rows)
        # 4 teams x 6 group matches = each match counted twice -> 12 team-games.
        if rows and played >= GROUP_MATCHES * 2:
            ranks[letter] = [rows[0]["team"], rows[1]["team"]]
    return ranks


def _settled_groups():
    """[(letter, rows)] for groups where all matches are played; rows are the
    standings rows (already Chinese, already sorted 1st->4th)."""
    groups, _ = api.load_standings()
    out = []
    for g in groups:
        letter = g["name"].split()[0]
        rows = g["rows"]
        played = sum(r["played"] for r in rows)
        if len(rows) >= 3 and played >= GROUP_MATCHES * 2:
            out.append((letter, rows))
    return out


def _third_place():
    """({letter: third_place_team_zh}, qualified_ok). qualified_ok is True only
    when all 12 groups are settled AND the eight best third-placed teams match
    the Annex C combination we encoded (THIRD_QUALIFIED)."""
    settled = _settled_groups()
    thirds = {letter: rows[2]["team"] for letter, rows in settled}
    if len(settled) < 12:
        return thirds, False
    ranked = sorted(
        settled,
        key=lambda lr: (-lr[1][2]["points"], -lr[1][2]["gd"], -lr[1][2]["gf"]),
    )
    top8 = frozenset(letter for letter, _ in ranked[:8])
    return thirds, top8 == THIRD_QUALIFIED


def _winner_loser(m, want_winner, resolve):
    """Resolved (zh) name of the winner/loser of raw match `m`, or None."""
    ft = (m.get("score") or {}).get("ft")
    pen = (m.get("score") or {}).get("pen") or (m.get("score") or {}).get("p")
    t1 = resolve(m.get("team1"))[0]
    t2 = resolve(m.get("team2"))[0]
    side = None
    if ft and ft[0] != ft[1]:
        side = 0 if ft[0] > ft[1] else 1
    elif pen and pen[0] != pen[1]:
        side = 0 if pen[0] > pen[1] else 1
    if side is None:
        return None
    winners = (t1, t2)
    return winners[side] if want_winner else winners[1 - side]


def build_bracket():
    """Resolve every knockout slot. Returns {num: {home, away, home_ok,
    away_ok, hg, ag, finished}} plus a 'meta' source flag."""
    data, source = api.raw_data()
    by_num = {m["num"]: m for m in data.get("matches", []) if "num" in m}
    ranks = _group_ranks()
    memo = {}

    def resolve(token):
        """(display_name, is_real_team) for a placeholder or real name."""
        if token is None:
            return ("待定", False)
        if token in memo:
            return memo[token]
        out = (api.zh_name(token), token in api.TEAMS_ZH)
        mg = re.match(r"^([12])([A-L])$", token)          # 1A / 2B
        if mg:
            pos, letter = int(mg.group(1)), mg.group(2)
            if letter in ranks:
                out = (ranks[letter][pos - 1], True)
        elif re.match(r"^W(\d+)$", token):                # winner of a match
            n = int(token[1:])
            if n in by_num:
                w = _winner_loser(by_num[n], True, resolve)
                if w:
                    out = (w, True)
        elif re.match(r"^L(\d+)$", token):                # loser of a match
            n = int(token[1:])
            if n in by_num:
                l = _winner_loser(by_num[n], False, resolve)
                if l:
                    out = (l, True)
        # 3A/B/C/D/F third-place combos: keep openfootball's value if it has
        # already been replaced by a real team; otherwise the label stands.
        memo[token] = out
        return out

    thirds, third_ok = _third_place()

    bracket = {}
    for n, m in by_num.items():
        if n < 73:        # group stage
            continue
        home, home_ok = resolve(m.get("team1"))
        away, away_ok = resolve(m.get("team2"))
        # Fill the eight best-third-place slots via Annex C (guarded).
        if third_ok and n in THIRD_SLOT_GROUP:
            team = thirds.get(THIRD_SLOT_GROUP[n])
            if team:
                if (m.get("team1") or "").startswith("3"):
                    home, home_ok = team, True
                if (m.get("team2") or "").startswith("3"):
                    away, away_ok = team, True
        ft = (m.get("score") or {}).get("ft")
        bracket[n] = {
            "home": home, "away": away, "home_ok": home_ok, "away_ok": away_ok,
            "hg": ft[0] if ft else None, "ag": ft[1] if ft else None,
            "finished": bool(ft),
            "utc": api._to_utc(m.get("date"), m.get("time", "")),
        }
    bracket["meta"] = {"source": source}
    return bracket


# ----------------------------------------------------------------------------
# Drawing
# ----------------------------------------------------------------------------
BG = (15, 17, 23)
PANEL = (30, 34, 44)
PANEL_REAL = (40, 46, 60)
LINE = (70, 78, 96)
TXT = (236, 238, 242)
MUTED = (140, 148, 164)
GOLD = (244, 180, 0)
WIN = (88, 196, 122)
TITLE = (248, 250, 252)

_FONT_CANDIDATES = [
    "/System/Library/Fonts/PingFang.ttc",
    "/System/Library/Fonts/Hiragino Sans GB.ttc",
    "/Library/Fonts/Arial Unicode.ttf",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
]


def _font(size):
    for p in _FONT_CANDIDATES:
        if Path(p).exists():
            try:
                return ImageFont.truetype(p, size)
            except Exception:
                continue
    return ImageFont.load_default()


def _fit(draw, text, font_for, maxw, start=22, floor=13):
    """Largest font (by size) at which `text` fits in maxw, down to floor."""
    s = start
    while s > floor:
        f = font_for(s)
        if draw.textlength(text, font=f) <= maxw:
            return f
        s -= 1
    return font_for(floor)


# Single-sided "Google style" layout: every match of a round in one tall
# column, flowing left-to-right to the final. Narrow + tall = phone-friendly.
LINEAR_R32 = LEFT_R32 + RIGHT_R32
LINEAR_R16 = [89, 90, 93, 94, 91, 92, 95, 96]
LINEAR_QF = [97, 98, 99, 100]
LINEAR_SF = [101, 102]
ALL_FEEDS = {**R16_FEEDS, **QF_FEEDS, **SF_FEEDS, FINAL_NUM: (101, 102)}

# Google-style cards: one card per match, kickoff date on top, two team rows.
CARD_W = 186
CARD_DATEH = 19
CARD_ROWH = 28
CARD_PAD = 8
CARD_H = CARD_PAD + CARD_DATEH + 2 + 2 * CARD_ROWH + CARD_PAD
CARD_GAP = 16
CARD_COLGAP = 44
LIN_TOP, LIN_BOT, LIN_SIDE = 118, 44, 24

_WD = "一二三四五六日"

# English team name -> flagcdn ISO code. Flags live as small PNGs in flags/.
_FLAG_ISO = {
    "Algeria": "dz", "Argentina": "ar", "Australia": "au", "Austria": "at",
    "Belgium": "be", "Bosnia & Herzegovina": "ba", "Brazil": "br", "Canada": "ca",
    "Cape Verde": "cv", "Colombia": "co", "Croatia": "hr", "Curaçao": "cw",
    "Czech Republic": "cz", "DR Congo": "cd", "Ecuador": "ec", "Egypt": "eg",
    "England": "gb-eng", "France": "fr", "Germany": "de", "Ghana": "gh",
    "Haiti": "ht", "Iran": "ir", "Iraq": "iq", "Ivory Coast": "ci", "Japan": "jp",
    "Jordan": "jo", "Mexico": "mx", "Morocco": "ma", "Netherlands": "nl",
    "New Zealand": "nz", "Norway": "no", "Panama": "pa", "Paraguay": "py",
    "Portugal": "pt", "Qatar": "qa", "Saudi Arabia": "sa", "Scotland": "gb-sct",
    "Senegal": "sn", "South Africa": "za", "South Korea": "kr", "Spain": "es",
    "Sweden": "se", "Switzerland": "ch", "Tunisia": "tn", "Turkey": "tr",
    "USA": "us", "Uruguay": "uy", "Uzbekistan": "uz",
}
# Keyed by the Traditional Chinese name we actually display.
_ZH_ISO = {api.TEAMS_ZH[en]: iso for en, iso in _FLAG_ISO.items() if en in api.TEAMS_ZH}
FLAG_DIR = Path(__file__).parent / "flags"
FLAG_H = 15   # rendered flag height in px

_flag_cache = {}


def _flag_for(zh_name):
    """Resolved RGBA flag image (resized to FLAG_H) for a Chinese team name."""
    iso = _ZH_ISO.get(zh_name)
    if not iso:
        return None
    if iso in _flag_cache:
        return _flag_cache[iso]
    img = None
    p = FLAG_DIR / f"{iso}.png"
    try:
        if p.exists():
            f = Image.open(p).convert("RGBA")
            w = max(1, round(f.width * FLAG_H / f.height))
            img = f.resize((w, FLAG_H), Image.LANCZOS)
    except Exception:
        img = None
    _flag_cache[iso] = img
    return img


def _date_label(utc):
    from zoneinfo import ZoneInfo
    if utc is None:
        return "日期待定"
    hk = utc.astimezone(ZoneInfo("Asia/Hong_Kong"))
    return f"{hk.month}月{hk.day}日（{_WD[hk.weekday()]}）"


def _team_row(canvas, draw, x, y, w, name, is_real, score, is_win, starset, font_for):
    """One team line inside a match card: flag (or dot) + name + score."""
    starred = is_real and name in starset
    pad = 10
    if starred:
        draw.rounded_rectangle([x + 3, y + 2, x + w - 3, y + CARD_ROWH - 2],
                               radius=5, fill=(58, 50, 18))
    col = WIN if is_win else (TXT if is_real else MUTED)
    sw = 0
    if score is not None:
        sf = font_for(16)
        sw = draw.textlength(str(score), font=sf) + 10
        draw.text((x + w - pad, y + CARD_ROWH / 2), str(score),
                  font=sf, fill=col, anchor="rm")
    cyd = y + CARD_ROWH / 2
    flag = _flag_for(name) if is_real else None
    if flag is not None:
        fx, fy = int(x + pad), int(cyd - FLAG_H / 2)
        canvas.paste(flag, (fx, fy), flag)
        text_x = x + pad + flag.width + 8
    else:
        r = 4
        dot = GOLD if starred else (col if is_real else LINE)
        draw.ellipse([x + pad, cyd - r, x + pad + 2 * r, cyd + r], fill=dot)
        text_x = x + pad + 2 * r + 8
    nf = _fit(draw, name, font_for, x + w - pad - sw - text_x, start=19, floor=12)
    draw.text((text_x, cyd), name, font=nf, fill=col, anchor="lm")


def render_linear_png(bracket, starset=None):
    """Single-sided tall bracket, Google-style match cards (phone-friendly)."""
    starset = starset or set()
    span = CARD_H + CARD_GAP
    total = 16 * span - CARD_GAP
    H = LIN_TOP + total + LIN_BOT
    cy = {n: LIN_TOP + i * span + CARD_H / 2 for i, n in enumerate(LINEAR_R32)}
    for n in LINEAR_R16 + LINEAR_QF + LINEAR_SF + [FINAL_NUM]:
        a, b = ALL_FEEDS[n]
        cy[n] = (cy[a] + cy[b]) / 2

    cols = [LINEAR_R32, LINEAR_R16, LINEAR_QF, LINEAR_SF, [FINAL_NUM]]
    step = CARD_W + CARD_COLGAP
    colx = [LIN_SIDE + i * step for i in range(5)]
    W = colx[4] + CARD_W + LIN_SIDE

    img = Image.new("RGB", (int(W), int(H)), BG)
    d = ImageDraw.Draw(img)

    def font_for(s):
        return _font(s)

    # connectors from each card's edge to its parent card
    for ci, col in enumerate(cols[1:], start=1):
        for num in col:
            a, b = ALL_FEEDS[num]
            px = colx[ci]
            for child in (a, b):
                x0 = colx[ci - 1] + CARD_W
                xm = (x0 + px) / 2
                d.line([(x0, cy[child]), (xm, cy[child]), (xm, cy[num]),
                        (px, cy[num])], fill=LINE, width=2)

    def card(num, x):
        m = bracket.get(num)
        if not m:
            return
        y = cy[num] - CARD_H / 2
        d.rounded_rectangle([x, y, x + CARD_W, y + CARD_H], radius=11,
                            fill=PANEL, outline=LINE, width=1)
        d.text((x + 12, y + CARD_PAD + CARD_DATEH / 2), _date_label(m.get("utc")),
               font=font_for(13), fill=MUTED, anchor="lm")
        hw = m["finished"] and m["hg"] is not None and m["hg"] > m["ag"]
        aw = m["finished"] and m["ag"] is not None and m["ag"] > m["hg"]
        ry = y + CARD_PAD + CARD_DATEH + 2
        _team_row(img, d, x, ry, CARD_W, m["home"], m["home_ok"], m["hg"], hw, starset, font_for)
        _team_row(img, d, x, ry + CARD_ROWH, CARD_W, m["away"], m["away_ok"], m["ag"], aw, starset, font_for)

    for ci, col in enumerate(cols):
        for num in col:
            card(num, colx[ci])

    lf = font_for(15)
    names = ["32強", "16強", "8強", "4強", "決賽"]
    for ci, nm in enumerate(names):
        d.text((colx[ci] + CARD_W / 2, LIN_TOP - 24), nm, font=lf, fill=MUTED, anchor="mm")

    tf = _fit(d, "世界盃 2026 · 淘汰賽", font_for, W - 40, start=30, floor=18)
    d.text((W / 2, 36), "世界盃 2026 · 淘汰賽", font=tf, fill=TITLE, anchor="mm")
    fm = bracket.get(FINAL_NUM, {})
    champ = None
    if fm.get("finished") and fm.get("hg") is not None:
        champ = fm["home"] if fm["hg"] > fm["ag"] else fm["away"]
    d.text((W / 2, 68), f"🏆 冠軍：{champ}" if champ else "冠軍待定",
           font=font_for(16), fill=GOLD, anchor="mm")

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()
