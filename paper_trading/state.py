"""
State persistence for the live paper trading dashboard.
Reads/writes the JSON files consumed by docs/app.js.
"""
import json
from pathlib import Path
from datetime import datetime, timezone
from typing import Optional, Dict, List

# This repo serves GitHub Pages from the repository ROOT (not /docs), but
# also keeps a duplicate copy of the site under /docs for browsing on
# GitHub itself. Both /live/data and /docs/live/data must stay in sync --
# we write to both on every save.
REPO_ROOT = Path(__file__).parent.parent
DATA_DIRS = [
    REPO_ROOT / 'live' / 'data',
    REPO_ROOT / 'docs' / 'live' / 'data',
]
for d in DATA_DIRS:
    d.mkdir(parents=True, exist_ok=True)

DATA_DIR = DATA_DIRS[1]  # canonical read location

STATE_FILE = DATA_DIR / 'state.json'
TRADES_FILE = DATA_DIR / 'trades.json'
PRICE_HISTORY_FILE = DATA_DIR / 'price_history.json'
EQUITY_CURVE_FILE = DATA_DIR / 'equity_curve.json'


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')


def load_json(path: Path, default):
    if path.exists():
        with open(path) as f:
            return json.load(f)
    return default


def save_json(path: Path, data):
    """Write `data` as JSON to `path`'s filename in every DATA_DIRS mirror."""
    filename = path.name
    for d in DATA_DIRS:
        with open(d / filename, 'w') as f:
            json.dump(data, f, indent=2, default=str)


def load_state() -> Optional[Dict]:
    return load_json(STATE_FILE, None)


def save_state(state: Dict):
    save_json(STATE_FILE, state)


def load_trades() -> List[Dict]:
    return load_json(TRADES_FILE, [])


def save_trades(trades: List[Dict]):
    save_json(TRADES_FILE, trades)


def load_price_history() -> List[Dict]:
    return load_json(PRICE_HISTORY_FILE, [])


def save_price_history(history: List[Dict]):
    save_json(PRICE_HISTORY_FILE, history)


def load_equity_curve() -> List[Dict]:
    return load_json(EQUITY_CURVE_FILE, [])


def save_equity_curve(curve: List[Dict]):
    save_json(EQUITY_CURVE_FILE, curve)
