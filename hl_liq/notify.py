"""Alert formatting and Telegram delivery."""
from __future__ import annotations

import asyncio
import html
import json
import logging
import urllib.request
from datetime import datetime, timezone

from .parser import Liquidation

log = logging.getLogger(__name__)

EXPLORER = "https://app.hyperliquid.xyz/explorer/address/"
PROMO = "Clustered alerts, whale near-liquidation & more → onchainsonar.com"


def fmt_usd(v: float) -> str:
    if v >= 1_000_000:
        return f"${v / 1_000_000:.2f}M"
    if v >= 1_000:
        return f"${v / 1_000:.1f}K"
    return f"${v:,.0f}"


def fmt_price(p: float) -> str:
    return f"{p:,.2f}" if p >= 100 else f"{p:,.4f}"


def short_addr(a: str) -> str:
    return f"{a[:6]}…{a[-4:]}" if len(a) > 12 else a


def format_alert(liq: Liquidation, promo: bool = True) -> str:
    icon = "🔴" if liq.side == "LONG" else "🟢"
    t = datetime.fromtimestamp(liq.time_ms / 1000, tz=timezone.utc).strftime("%H:%M:%S UTC") if liq.time_ms else ""
    lines = [
        f"{icon} <b>{liq.side} LIQUIDATED · {html.escape(liq.coin)}</b>",
        f"Size: <b>{fmt_usd(liq.notional)}</b> ({liq.size:g} {html.escape(liq.coin)}) @ {fmt_price(liq.price)}",
        f"Mark: {fmt_price(liq.mark_price)}",
        f'Wallet: <a href="{EXPLORER}{liq.user}">{short_addr(liq.user)}</a>',
    ]
    if t:
        lines.append(f"<i>{t}</i>")
    if promo:
        lines.append(f"\n<i>{PROMO}</i>")
    return "\n".join(lines)


class TelegramNotifier:
    def __init__(self, token: str, chat_id: str, promo: bool = True):
        self.url = f"https://api.telegram.org/bot{token}/sendMessage"
        self.chat_id = chat_id
        self.promo = promo

    def _post(self, text: str) -> None:
        body = json.dumps({
            "chat_id": self.chat_id,
            "text": text,
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
        }).encode()
        req = urllib.request.Request(self.url, data=body, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=15) as r:
            r.read()

    async def send(self, liq: Liquidation) -> None:
        text = format_alert(liq, self.promo)
        for attempt in range(3):
            try:
                await asyncio.to_thread(self._post, text)
                return
            except Exception as e:  # network / 429
                log.warning("Telegram send failed (%s), retry %d", e, attempt + 1)
                await asyncio.sleep(2 ** attempt * 2)
        log.error("Dropped alert for tid=%s", liq.tid)


class ConsoleNotifier:
    def __init__(self, promo: bool = False):
        self.promo = promo

    async def send(self, liq: Liquidation) -> None:
        import re
        print(re.sub(r"<[^>]+>", "", format_alert(liq, self.promo)), "\n", flush=True)
