"""Entry point: python -m hl_liq"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os

from .notify import ConsoleNotifier, TelegramNotifier
from .parser import Filter, liquidations_from_message
from .sources import NodeFillsSource, ReplaySource, WebSocketSource

log = logging.getLogger("hl_liq")


def load_dotenv(path: str = ".env") -> None:
    if not os.path.exists(path):
        return
    for line in open(path, encoding="utf-8"):
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def build_source(args):
    if args.replay:
        return ReplaySource(args.replay, delay=args.replay_delay)
    kind = os.getenv("SOURCE", "websocket").lower()
    if kind == "node":
        return NodeFillsSource(os.getenv("NODE_FILLS_DIR", "~/hl/data/node_fills_by_block"))
    url = os.getenv("WS_URL")
    if not url:
        raise SystemExit("Set WS_URL (provider stream) or SOURCE=node with NODE_FILLS_DIR. See README.")
    sub = os.getenv("WS_SUBSCRIBE")
    return WebSocketSource(url, json.loads(sub) if sub else None)


def build_notifier(args):
    token, chat = os.getenv("TELEGRAM_BOT_TOKEN"), os.getenv("TELEGRAM_CHAT_ID")
    if args.console or not (token and chat):
        if not args.console:
            log.warning("TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID not set — printing to console")
        return ConsoleNotifier()
    return TelegramNotifier(token, chat, promo=os.getenv("PROMO", "1") != "0")


async def run(args) -> None:
    flt = Filter(os.getenv("COINS", "BTC,ETH,SOL").split(","), float(os.getenv("MIN_USD", "100000")))
    source, notifier = build_source(args), build_notifier(args)
    log.info("Watching %s, min %s USD", ",".join(sorted(flt.coins)), f"{flt.min_usd:,.0f}")
    async for msg in source.messages():
        for liq in liquidations_from_message(msg):
            if flt.accept(liq):
                await notifier.send(liq)


def main() -> None:
    p = argparse.ArgumentParser(description="Hyperliquid liquidation alerts for BTC/ETH/SOL → Telegram")
    p.add_argument("--replay", help="read events from a JSONL file instead of a live source")
    p.add_argument("--replay-delay", type=float, default=0.0)
    p.add_argument("--console", action="store_true", help="print alerts instead of sending to Telegram")
    args = p.parse_args()
    load_dotenv()
    logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"), format="%(asctime)s %(levelname)s %(message)s")
    try:
        asyncio.run(run(args))
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
