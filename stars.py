"""
Shared "starred teams" store for the family.

v1 backend = a local JSON file (works for local testing and seeing the UI).
On Streamlit Community Cloud local files are NOT persisted across restarts, so
Phase 2 swaps this for a shared Google Sheet via st-gsheets-connection. The
public functions below are the stable interface; only the bodies change.

Data shape: {team_name: [who, who, ...]}  -- who = optional family member name.
"""

import json
from pathlib import Path

STORE = Path(__file__).parent / "stars.json"


def _load():
    if STORE.exists():
        try:
            return json.loads(STORE.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def _save(data):
    STORE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def get_starred():
    """{team_name: [names...]} for every starred team."""
    return _load()


def starred_teams():
    """Set of starred team names."""
    return set(_load().keys())


def toggle_star(team, who=""):
    """Star/un-star a team. Read-then-write to stay safe with concurrent users.

    Returns True if the team is now starred, False if it was removed.
    """
    data = _load()
    if team in data:
        del data[team]
        _save(data)
        return False
    data[team] = [who] if who else []
    _save(data)
    return True
