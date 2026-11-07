"""Turn Hyperliquid node-style fill events into Liquidation objects.

Input format (node_fills / provider "trades" stream):
    {"block_time": "...", "events": [[user_address, fill], ...]}

A liquidation fill carries:
    fill["liquidation"] = {"liquidatedUser": "0x..", "markPx": "..", "method": "market"}

Both sides of a liquidation trade can show up; we keep only the fill that
belongs to the liquidated user and dedupe by trade id (tid).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Iterator

SUPPORTED_COINS = ("BTC", "ETH", "SOL")


@dataclass(frozen=True)
class Liquidation:
    coin: str
    side: str          # "LONG" or "SHORT" — the position that was liquidated
    size: float        # in coin units
    price: float
    mark_price: float
    notional: float    # USD
    user: str
    method: str
    time_ms: int
    tid: int
    hash: str


def _side_from_dir(direction: str, fill_side: str) -> str:
    d = (direction or "").lower()
    if "long" in d:
        return "LONG"
    if "short" in d:
        return "SHORT"
    # Fallback: liquidating a long means selling ("A"), a short means buying ("B")
    return "LONG" if fill_side == "A" else "SHORT"


def parse_fill(user: str, fill: dict) -> Liquidation | None:
    liq = fill.get("liquidation")
    if not liq:
        return None
    liquidated = (liq.get("liquidatedUser") or "").lower()
    if liquidated and user.lower() != liquidated:
        return None  # counterparty fill, not the liquidated position
    try:
        px = float(fill["px"])
        sz = abs(float(fill["sz"]))
        return Liquidation(
            coin=str(fill["coin"]).upper(),
            side=_side_from_dir(fill.get("dir", ""), fill.get("side", "")),
            size=sz,
            price=px,
            mark_price=float(liq.get("markPx") or px),
            notional=px * sz,
            user=liquidated or user,
            method=liq.get("method", ""),
            time_ms=int(fill.get("time", 0)),
            tid=int(fill.get("tid", 0)),
            hash=fill.get("hash", ""),
        )
    except (KeyError, TypeError, ValueError):
        return None


def extract_events(msg: dict) -> list:
    """Find the events array in a message, tolerating common envelopes."""
    if not isinstance(msg, dict):
        return []
    if isinstance(msg.get("events"), list):
        return msg["events"]
    for key in ("params", "result", "data"):
        inner = msg.get(key)
        if isinstance(inner, dict):
            found = extract_events(inner)
            if found:
                return found
    return []


def liquidations_from_message(msg: dict) -> Iterator[Liquidation]:
    for ev in extract_events(msg):
        if isinstance(ev, (list, tuple)) and len(ev) == 2 and isinstance(ev[1], dict):
            liq = parse_fill(str(ev[0]), ev[1])
            if liq:
                yield liq


class Filter:
    """Coin allowlist (subset of BTC/ETH/SOL), min notional, tid dedupe."""

    def __init__(self, coins: Iterable[str], min_usd: float, dedupe_size: int = 5000):
        wanted = {c.strip().upper() for c in coins if c.strip()}
        bad = wanted - set(SUPPORTED_COINS)
        if bad:
            raise ValueError(
                f"Unsupported coins: {', '.join(sorted(bad))}. "
                f"Open-source version supports {', '.join(SUPPORTED_COINS)} only."
            )
        self.coins = wanted or set(SUPPORTED_COINS)
        self.min_usd = float(min_usd)
        self._seen: dict[int, None] = {}
        self._dedupe_size = dedupe_size

    def accept(self, liq: Liquidation) -> bool:
        if liq.coin not in self.coins or liq.notional < self.min_usd:
            return False
        key = liq.tid or hash((liq.hash, liq.user, liq.size))
        if key in self._seen:
            return False
        self._seen[key] = None
        if len(self._seen) > self._dedupe_size:
            self._seen.pop(next(iter(self._seen)))
        return True
