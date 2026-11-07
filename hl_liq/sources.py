"""Data sources. Each yields raw messages (dicts) containing an `events` array.

- NodeFillsSource: tails the fills files written by your own non-validating
  Hyperliquid node (`hl-node ... --write-fills --batch-by-block`). Free, but you
  run the node.
- WebSocketSource: a provider stream that exposes node-level trades with the
  `liquidation` object (e.g. QuickNode `hl_subscribe` / streamType "trades").
- ReplaySource: reads a JSONL file — for testing and demos.
"""
from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path
from typing import AsyncIterator

log = logging.getLogger(__name__)


class ReplaySource:
    def __init__(self, path: str, delay: float = 0.0):
        self.path = Path(path)
        self.delay = delay

    async def messages(self) -> AsyncIterator[dict]:
        for line in self.path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError:
                continue
            if self.delay:
                await asyncio.sleep(self.delay)


class NodeFillsSource:
    """Follow the newest file under the node's fills directory, line by line."""

    def __init__(self, directory: str, poll: float = 0.25):
        self.dir = Path(directory).expanduser()
        self.poll = poll

    def _newest(self) -> Path | None:
        files = [p for p in self.dir.rglob("*") if p.is_file()]
        return max(files, key=lambda p: p.stat().st_mtime) if files else None

    async def messages(self) -> AsyncIterator[dict]:
        current: Path | None = None
        fh = None
        last_check = 0.0
        loop = asyncio.get_running_loop()
        while True:
            now = loop.time()
            if fh is None or now - last_check > 5:
                last_check = now
                newest = self._newest()
                if newest and newest != current:
                    if fh:
                        # drain the rest of the previous file before switching
                        for line in fh:
                            msg = _loads(line)
                            if msg:
                                yield msg
                        fh.close()
                    log.info("Following %s", newest)
                    fh = newest.open("r", encoding="utf-8")
                    if current is None:
                        fh.seek(0, 2)  # start at the end on first open
                    current = newest
            if fh is None:
                await asyncio.sleep(1)
                continue
            line = fh.readline()
            if not line:
                await asyncio.sleep(self.poll)
                continue
            msg = _loads(line)
            if msg:
                yield msg


class WebSocketSource:
    DEFAULT_SUBSCRIBE = {
        "jsonrpc": "2.0",
        "method": "hl_subscribe",
        "params": {"streamType": "trades", "filters": {"liquidation": ["*"]}},
        "id": 1,
    }

    def __init__(self, url: str, subscribe: dict | None = None):
        self.url = url
        self.subscribe = subscribe or self.DEFAULT_SUBSCRIBE

    async def messages(self) -> AsyncIterator[dict]:
        try:
            import websockets
        except ImportError as e:
            raise SystemExit("Install websockets: pip install websockets") from e
        backoff = 1
        while True:
            try:
                async with websockets.connect(self.url, ping_interval=20, max_size=None) as ws:
                    await ws.send(json.dumps(self.subscribe))
                    log.info("Connected to stream")
                    backoff = 1
                    async for raw in ws:
                        msg = _loads(raw)
                        if msg:
                            yield msg
            except Exception as e:
                log.warning("Stream error: %s — reconnecting in %ss", e, backoff)
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, 60)


def _loads(raw) -> dict | None:
    try:
        msg = json.loads(raw)
        return msg if isinstance(msg, dict) else None
    except (json.JSONDecodeError, TypeError):
        return None
