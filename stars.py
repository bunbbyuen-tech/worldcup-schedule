"""
Shared "starred teams" store for the family.

Backend is a GitHub Gist (a tiny shared stars.json) when configured via secrets
  github_token = "ghp_..."   # classic token with only the 'gist' scope
  gist_id      = "..."        # id of a gist containing a stars.json file
This makes stars persist + shared across the whole family on Streamlit Cloud.

If those secrets are absent (e.g. local dev), it falls back to a local
stars.json file. The public functions are the stable interface.

Data shape: {team_name: [who, who, ...]}  -- who = optional family member name.
"""

import json
from pathlib import Path

import requests
import streamlit as st

LOCAL = Path(__file__).parent / "stars.json"
GIST_FILE = "stars.json"
API = "https://api.github.com/gists"


# ----------------------------------------------------------------------------
# Backend selection
# ----------------------------------------------------------------------------
def _cfg():
    try:
        return st.secrets["github_token"], st.secrets["gist_id"]
    except Exception:
        return None, None


def _headers(token):
    return {"Authorization": f"token {token}", "Accept": "application/vnd.github+json"}


def _gist_load(token, gid):
    r = requests.get(f"{API}/{gid}", headers=_headers(token), timeout=15)
    r.raise_for_status()
    content = r.json().get("files", {}).get(GIST_FILE, {}).get("content") or "{}"
    return json.loads(content)


def _gist_save(token, gid, data):
    body = {"files": {GIST_FILE: {"content": json.dumps(data, ensure_ascii=False, indent=2)}}}
    r = requests.patch(f"{API}/{gid}", headers=_headers(token), json=body, timeout=15)
    r.raise_for_status()


# ----------------------------------------------------------------------------
# Load / save (gist if configured, else local file)
# ----------------------------------------------------------------------------
def _load():
    token, gid = _cfg()
    if token and gid:
        try:
            return _gist_load(token, gid)
        except Exception:
            return {}
    if LOCAL.exists():
        try:
            return json.loads(LOCAL.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def _save(data):
    token, gid = _cfg()
    if token and gid:
        _gist_save(token, gid, data)
        return
    LOCAL.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


# ----------------------------------------------------------------------------
# Public interface
# ----------------------------------------------------------------------------
def get_starred():
    """{team_name: [names...]} for every starred team."""
    return _load()


def starred_teams():
    """Set of starred team names."""
    return set(_load().keys())


def toggle_star(team, who):
    """Toggle THIS person's star on a team (per-person). Read-then-write so
    concurrent family members don't clobber each other.

    A team key holds the list of people who starred it. Returns True if `who`
    now stars the team, False if their star was removed.
    """
    data = _load()
    fans = list(data.get(team, []))
    if who in fans:
        fans.remove(who)
        res = False
    else:
        fans.append(who)
        res = True
    if fans:
        data[team] = fans
    else:
        data.pop(team, None)
    _save(data)
    return res
