"""
World Cup 2026 — Family Dashboard (mobile-first)
A shared dashboard for the family across Sheffield / Hong Kong / San Francisco.

Designed for phones. The 3 family timezones are the hero of every match.
Tabs: 賽程 · 積分榜 · 淘汰賽 · 心水隊
Data: api-football (live), with demo fallback. Stars: shared store (stars.py).
"""

from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo

import streamlit as st

import api
import stars

# centered = narrow column that reads well on a phone (wide stretches awkwardly).
st.set_page_config(page_title="World Cup 2026 · 家庭睇波台", page_icon="⚽", layout="centered")

# Family timezones — converted correctly (incl. daylight saving) via zoneinfo.
# css = the colour class for each city's time box.
ZONES = [
    ("🇬🇧 Sheffield", "Europe/London", "uk"),
    ("🇭🇰 香港", "Asia/Hong_Kong", "hk"),
    ("🇺🇸 三藩市", "America/Los_Angeles", "sf"),
]

STAGE_COLORS = {
    "group": "#085041", "r32": "#3C3489", "r16": "#633806",
    "qf": "#712B13", "sf": "#791F1F", "third": "#555", "final": "#E24B4A",
}

st.markdown("""
<style>
.match-card{border:1px solid #e8e8e6;border-radius:12px;padding:12px 14px;margin-bottom:10px;background:#fff}
.match-card.starred{border-left:5px solid #f4b400;background:#fffdf5}
.match-card.live{border-left:5px solid #e24b4a;background:#fff7f6}
.mhead{display:flex;align-items:center;justify-content:space-between;gap:8px}
.teams{font-size:17px;font-weight:700;color:#1a1a1a;line-height:1.3}
.score{font-size:19px;font-weight:800;color:#111}
.stage-pill{display:inline-block;font-size:11px;font-weight:700;color:#fff;padding:1px 8px;border-radius:5px;margin-bottom:6px}
.live-pill{display:inline-block;font-size:12px;font-weight:800;color:#fff;background:#e24b4a;padding:2px 9px;border-radius:6px}
.done-tag{font-size:12px;color:#999;font-weight:600}
/* the hero: 3 timezone boxes */
.tz-grid{display:flex;gap:6px;margin-top:10px}
.tz-box{flex:1;text-align:center;border-radius:9px;padding:7px 4px}
.tz-box .city{font-size:11px;font-weight:700;display:block;margin-bottom:1px}
.tz-box .time{font-size:16px;font-weight:800;display:block;line-height:1.15}
.tz-box .day{font-size:11px;display:block;opacity:.75;margin-top:1px}
.uk{background:#E6F1FB;color:#0C447C}
.hk{background:#FAECE7;color:#712B13}
.sf{background:#EAF3DE;color:#27500A}
.late{color:#A32D2D !important}
.daydiv{font-size:14px;font-weight:800;color:#333;margin:16px 0 8px;border-bottom:2px solid #eee;padding-bottom:4px}
</style>
""", unsafe_allow_html=True)


# ----------------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------------
def tz_grid(utc_dt):
    """The 3-up timezone block — the most important part of each match."""
    if utc_dt is None:
        return '<div class="meta" style="color:#999;margin-top:8px">時間待定</div>'
    boxes = ""
    for label, tzname, css in ZONES:
        local = utc_dt.astimezone(ZoneInfo(tzname))
        t = local.strftime("%-I:%M%p").lower()
        hour = local.hour
        late = " late" if (hour >= 23 or hour < 6) else ""
        boxes += (
            f'<div class="tz-box {css}">'
            f'<span class="city">{label}</span>'
            f'<span class="time{late}">{t}</span>'
            f'<span class="day">{local.strftime("%a %-d/%-m")}</span>'
            f'</div>'
        )
    return f'<div class="tz-grid">{boxes}</div>'


def stage_pill(m):
    color = STAGE_COLORS.get(m["stage_key"], "#555")
    return f'<span class="stage-pill" style="background:{color}">{m["stage_label"]}</span>'


def score_or_vs(m):
    if (m["finished"] or m["live"]) and m["home_goals"] is not None:
        return f'<span class="score">{m["home_goals"]} - {m["away_goals"]}</span>'
    return '<span style="color:#aaa;font-weight:600">vs</span>'


def render_match(m, starset):
    starred = m["home"] in starset or m["away"] in starset
    cls = "match-card"
    if m["live"]:
        cls += " live"
    elif starred:
        cls += " starred"

    home = ("⭐ " if m["home"] in starset else "") + m["home"]
    away = m["away"] + (" ⭐" if m["away"] in starset else "")

    if m["live"]:
        right = '<span class="live-pill">🔴 進行中</span>'
    elif m["finished"]:
        right = '<span class="done-tag">完場</span>'
    else:
        right = ""

    body = (
        f'<div class="{cls}">'
        f'{stage_pill(m)}'
        f'<div class="mhead"><span class="teams">{home}　{score_or_vs(m)}　{away}</span>{right}</div>'
    )
    # Times are the hero — always show them for upcoming/live; small for finished.
    if not m["finished"]:
        body += tz_grid(m["utc"])
    body += "</div>"
    st.markdown(body, unsafe_allow_html=True)


def day_key(m, tzname="Europe/London"):
    if m["utc"] is None:
        return "待定"
    return m["utc"].astimezone(ZoneInfo(tzname)).strftime("%a %-d %b")


# ----------------------------------------------------------------------------
# Load data
# ----------------------------------------------------------------------------
matches, source = api.load_matches()
starset = stars.starred_teams()

st.title("⚽ World Cup 2026")
st.caption("Sheffield · 香港 · 三藩市 — 一齊睇波、跟排名同晉級、star 心水隊")

if source == "bundled":
    st.info("暫時連唔到最新數據，顯示緊本機備份賽程；比數可能未係最新。", icon="📶")

with st.sidebar:
    st.header("設定")
    if st.button("🔄 更新賽果", use_container_width=True):
        api.clear_caches()
        st.rerun()
    st.caption("賽程同比數每半個鐘自動更新；㩒呢個掣即刻拎最新。")

FAMILY = ["Nam", "Tung", "Dad", "Mum"]

tab_sched, tab_table, tab_ko, tab_star = st.tabs(["📅 賽程", "📊 積分榜", "🏆 淘汰賽", "⭐ 心水隊"])


# ----------------------------------------------------------------------------
# Tab 1 — Schedule
# ----------------------------------------------------------------------------
with tab_sched:
    now = datetime.now(timezone.utc)
    week_ahead = now + timedelta(days=7)
    live = [m for m in matches if m["live"]]
    upcoming = [m for m in matches if not m["live"] and not m["finished"]
                and m["utc"] and now <= m["utc"] <= week_ahead]
    finished = [m for m in matches if m["finished"]]

    only_star = st.toggle("只睇心水隊", value=False)
    if only_star:
        flt = lambda lst: [m for m in lst if m["home"] in starset or m["away"] in starset]
        live, upcoming, finished = flt(live), flt(upcoming), flt(finished)

    if live:
        st.subheader("🔴 進行中")
        for m in live:
            render_match(m, starset)

    st.subheader("⏭️ 即將開賽（未來一週）")
    if upcoming:
        last_day = None
        for m in upcoming:
            d = day_key(m)
            if d != last_day:
                st.markdown(f'<div class="daydiv">{d}</div>', unsafe_allow_html=True)
                last_day = d
            render_match(m, starset)
    else:
        st.caption("未來一週暫時無場次。")

    if finished:
        with st.expander(f"✅ 已賽（{len(finished)} 場）"):
            for m in reversed(finished):
                render_match(m, starset)


# ----------------------------------------------------------------------------
# Tab 2 — Group standings (single column for mobile)
# ----------------------------------------------------------------------------
with tab_table:
    groups, _ = api.load_standings()
    st.caption("積分榜根據已賽結果即時計算（勝 3 分 · 和 1 分），按分數、淨球排名。")
    if not groups:
        st.info("積分榜未有數據。")
    for g in groups:
        st.markdown(f"**{g['name']}**")
        rows = []
        for r in g["rows"]:
            name = ("⭐ " if r["team"] in starset else "") + r["team"]
            rows.append({
                "#": r["rank"], "隊伍": name, "賽": r["played"],
                "勝": r["win"], "和": r["draw"], "負": r["lose"],
                "淨球": r["gd"], "分": r["points"],
            })
        st.dataframe(rows, hide_index=True, use_container_width=True)


# ----------------------------------------------------------------------------
# Tab 3 — Knockout bracket
# ----------------------------------------------------------------------------
with tab_ko:
    ko_order = [("r32", "32 強"), ("r16", "16 強"), ("qf", "8 強"),
                ("sf", "4 強"), ("third", "季軍戰"), ("final", "決賽")]
    ko = [m for m in matches if m["stage_key"] in dict(ko_order)]
    if not ko:
        st.info("淘汰賽未開始 — 小組賽完成後自動填上對陣。")
    else:
        for key, label in ko_order:
            stage_matches = [m for m in ko if m["stage_key"] == key]
            if not stage_matches:
                continue
            st.subheader(label)
            for m in stage_matches:
                render_match(m, starset)


# ----------------------------------------------------------------------------
# Tab 4 — Star teams (shared, 2 columns for mobile)
# ----------------------------------------------------------------------------
with tab_star:
    st.caption("揀返你係邊個，再 star 你嘅心水隊。全家都會睇到大家心水邊隊（賽程／積分榜會 ⭐ 突出）。")
    who = st.selectbox("你係邊個？", FAMILY, index=None, placeholder="揀你嘅名", key="who")
    starred = stars.get_starred()

    if starred:
        st.markdown("**全家心水隊：** " + " · ".join(
            f"⭐{t}（{'、'.join(w)}）" if w else f"⭐{t}" for t, w in starred.items()))
    else:
        st.markdown("_仲未有人 star。_")

    st.divider()
    if not who:
        st.info("☝️ 先揀你係邊個，先可以 star。")
    teams = api.team_list(matches)
    if not teams:
        st.info("未有隊伍資料。")
    cols = st.columns(2)
    for i, t in enumerate(teams):
        with cols[i % 2]:
            fans = starred.get(t, [])
            mine = bool(who) and who in fans
            tag = f" ·{len(fans)}" if fans else ""
            label = ("⭐ " if mine else "☆ ") + t + tag
            if st.button(label, key=f"star_{t}", use_container_width=True, disabled=not who):
                stars.toggle_star(t, who)
                st.rerun()
