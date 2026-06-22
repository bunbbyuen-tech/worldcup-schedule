"""
Data layer for the World Cup 2026 family dashboard.

Source: openfootball/worldcup.json — public-domain, no API key, no rate limit.
It carries the full 104-match schedule (real UTC kickoff times) AND the real
results as matches are played, so scores + standings update automatically for
free. We fetch it (cached), fall back to a bundled copy if the network fails,
and compute group standings ourselves from the finished results.

Source verified 2026-06-15:
  https://github.com/openfootball/worldcup.json  (CC0 / public domain)
"""

import json
import re
from datetime import datetime, timezone, timedelta
from pathlib import Path

import requests
import streamlit as st

DATA_URL = "https://raw.githubusercontent.com/openfootball/worldcup.json/master/2026/worldcup.json"
BUNDLED = Path(__file__).parent / "schedule_2026.json"

# A match is treated as "live" from kickoff until this many hours after.
LIVE_WINDOW_H = 3

# English -> Traditional Chinese (Hong Kong) team names.
TEAMS_ZH = {
    "Algeria": "阿爾及利亞", "Argentina": "阿根廷", "Australia": "澳洲", "Austria": "奧地利",
    "Belgium": "比利時", "Bosnia & Herzegovina": "波斯尼亞", "Brazil": "巴西", "Canada": "加拿大",
    "Cape Verde": "佛得角", "Colombia": "哥倫比亞", "Croatia": "克羅地亞", "Curaçao": "庫拉索",
    "Czech Republic": "捷克", "DR Congo": "民主剛果", "Ecuador": "厄瓜多爾", "Egypt": "埃及",
    "England": "英格蘭", "France": "法國", "Germany": "德國", "Ghana": "加納", "Haiti": "海地",
    "Iran": "伊朗", "Iraq": "伊拉克", "Ivory Coast": "象牙海岸", "Japan": "日本", "Jordan": "約旦",
    "Mexico": "墨西哥", "Morocco": "摩洛哥", "Netherlands": "荷蘭", "New Zealand": "紐西蘭",
    "Norway": "挪威", "Panama": "巴拿馬", "Paraguay": "巴拉圭", "Portugal": "葡萄牙",
    "Qatar": "卡塔爾", "Saudi Arabia": "沙特阿拉伯", "Scotland": "蘇格蘭", "Senegal": "塞內加爾",
    "South Africa": "南非", "South Korea": "南韓", "Spain": "西班牙", "Sweden": "瑞典",
    "Switzerland": "瑞士", "Tunisia": "突尼斯", "Turkey": "土耳其", "USA": "美國",
    "Uruguay": "烏拉圭", "Uzbekistan": "烏茲別克",
}


def _zh(name):
    """Translate a team name (or knockout placeholder) to Traditional Chinese."""
    if not name:
        return name
    if name in TEAMS_ZH:
        return TEAMS_ZH[name]
    m = re.match(r"^([12])([A-L])$", name)          # group winner/runner-up, e.g. 1A / 2B
    if m:
        return f"{m.group(2)}組第{m.group(1)}"
    m = re.match(r"^3(.+)$", name)                   # third-place combos, e.g. 3A/B/C/D/F
    if m:
        return f"第三名（{m.group(1)}）"
    m = re.match(r"^W(\d+)$", name)                  # winner of match N
    if m:
        return f"M{m.group(1)}勝方"
    m = re.match(r"^L(\d+)$", name)                  # loser of match N
    if m:
        return f"M{m.group(1)}負方"
    return name


# ----------------------------------------------------------------------------
# Raw fetch (cached) with bundled fallback
# ----------------------------------------------------------------------------
@st.cache_data(ttl=1800, show_spinner=False)
def _raw():
    """Return (data, source) where source is 'live' or 'bundled'."""
    try:
        r = requests.get(DATA_URL, timeout=15)
        r.raise_for_status()
        data = r.json()
        try:  # opportunistically refresh the local fallback (ignored on read-only FS)
            BUNDLED.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        except Exception:
            pass
        return data, "live"
    except Exception:
        if BUNDLED.exists():
            return json.loads(BUNDLED.read_text(encoding="utf-8")), "bundled"
        return {"matches": []}, "bundled"


def clear_caches():
    _raw.clear()


def raw_data():
    """Raw openfootball payload (data, source) — for the bracket resolver,
    which needs the original placeholder tokens (e.g. '2A', 'W74') that the
    normalised match list translates away."""
    return _raw()


def zh_name(name):
    """Public access to the English -> Traditional Chinese translator."""
    return _zh(name)


# ----------------------------------------------------------------------------
# Parsing
# ----------------------------------------------------------------------------
def _to_utc(date_str, time_str):
    """'2026-06-11', '13:00 UTC-6' -> aware UTC datetime."""
    try:
        hm, off = time_str.split(" ")
        h, mn = (int(x) for x in hm.split(":"))
        n = int(re.sub(r"[^0-9-]", "", off.replace("UTC", "")))
        local = timezone(timedelta(hours=n))
        y, mo, d = (int(x) for x in date_str.split("-"))
        return datetime(y, mo, d, h, mn, tzinfo=local).astimezone(timezone.utc)
    except Exception:
        return None


def _stage_of(round_str, group):
    r = (round_str or "").lower()
    if group or "matchday" in r or "group" in r:
        return ("group", "小組賽")
    if "round of 32" in r:
        return ("r32", "32 強")
    if "round of 16" in r:
        return ("r16", "16 強")
    if "quarter" in r:
        return ("qf", "8 強")
    if "semi" in r:
        return ("sf", "4 強")
    if "third" in r:
        return ("third", "季軍戰")
    if "final" in r:
        return ("final", "決賽")
    return ("group", round_str or "—")


def _normalise(m, now):
    ft = (m.get("score") or {}).get("ft")
    kickoff = _to_utc(m.get("date"), m.get("time", ""))
    stage_key, stage_label = _stage_of(m.get("round"), m.get("group"))

    if ft:
        status = "done"
        hg, ag = ft[0], ft[1]
    elif kickoff and kickoff <= now <= kickoff + timedelta(hours=LIVE_WINDOW_H):
        status, hg, ag = "live", None, None
    elif kickoff and now > kickoff:
        status, hg, ag = "done", None, None   # played but result not entered yet
    else:
        status, hg, ag = "upcoming", None, None

    return {
        "utc": kickoff,
        "stage_key": stage_key,
        "stage_label": stage_label,
        "group": m.get("group"),
        "home": _zh(m.get("team1", "TBD")),
        "away": _zh(m.get("team2", "TBD")),
        "home_goals": hg,
        "away_goals": ag,
        "live": status == "live",
        "finished": status == "done",
        "venue": m.get("ground"),
    }


# ----------------------------------------------------------------------------
# Public loaders
# ----------------------------------------------------------------------------
def load_matches():
    """All matches, normalised + sorted by kickoff. Returns (matches, source)."""
    data, source = _raw()
    now = datetime.now(timezone.utc)
    matches = [_normalise(m, now) for m in data.get("matches", [])]
    far = datetime.max.replace(tzinfo=timezone.utc)
    matches.sort(key=lambda m: m["utc"] or far)
    return matches, source


def load_standings():
    """Compute group tables from finished group matches. Returns (groups, source)."""
    matches, source = load_matches()
    groups = {}

    def row(team):
        return {"team": team, "played": 0, "win": 0, "draw": 0, "lose": 0,
                "gf": 0, "ga": 0, "gd": 0, "points": 0}

    for m in matches:
        if m["stage_key"] != "group" or not m["group"]:
            continue
        g = groups.setdefault(m["group"], {})
        for t in (m["home"], m["away"]):
            if t and t != "TBD":
                g.setdefault(t, row(t))
        # only finished matches with a real score count toward the table
        if not m["finished"] or m["home_goals"] is None:
            continue
        h, a = m["home"], m["away"]
        hg, ag = m["home_goals"], m["away_goals"]
        for t, gf, ga in ((h, hg, ag), (a, ag, hg)):
            r = g[t]
            r["played"] += 1
            r["gf"] += gf
            r["ga"] += ga
            r["gd"] = r["gf"] - r["ga"]
            if gf > ga:
                r["win"] += 1; r["points"] += 3
            elif gf == ga:
                r["draw"] += 1; r["points"] += 1
            else:
                r["lose"] += 1

    out = []
    for name in sorted(groups):
        rows = sorted(groups[name].values(),
                      key=lambda r: (-r["points"], -r["gd"], -r["gf"], r["team"]))
        for i, r in enumerate(rows, 1):
            r["rank"] = i
        zh_name = name.replace("Group ", "") + " 組" if name.startswith("Group ") else name
        out.append({"name": zh_name, "rows": rows})
    return out, source


def team_list(matches):
    """Real (non-placeholder) team names, for the star picker."""
    names = set()
    for m in matches:
        if m["stage_key"] != "group":
            continue
        for t in (m["home"], m["away"]):
            if t and t != "TBD":
                names.add(t)
    return sorted(names)
