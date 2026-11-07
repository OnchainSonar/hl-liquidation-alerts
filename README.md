# Hyperliquid Liquidation Alerts → Telegram

Real-time Telegram alerts for large **BTC, ETH and SOL** liquidations on Hyperliquid.

```
🔴 LONG LIQUIDATED · ETH
Size: $2.42M (760 ETH) @ 3,182.40
Mark: 3,179.22
Wallet: 0x7a47…214d
```

- Only the liquidated side is reported, deduplicated by trade id
- Minimum size filter (default $100K)
- Pick any subset of BTC / ETH / SOL
- Auto-reconnect, Docker-ready, zero required dependencies besides `websockets`

## Data source

Hyperliquid's public `trades` WebSocket does not flag liquidations. The flag lives in
node-level fill data (`fill.liquidation = {liquidatedUser, markPx, method}`), so you need one of:

| `SOURCE` | What | Cost |
|---|---|---|
| `node` | Your own non-validating node started with `--write-fills`; set `NODE_FILLS_DIR` | Free, you run the node |
| `websocket` | A provider stream of node-level trades (e.g. QuickNode `hl_subscribe`, `streamType: trades`); set `WS_URL` | Provider plan |

The default subscribe message follows QuickNode's documented `hl_subscribe` format.
Other providers: override it with `WS_SUBSCRIBE`. The parser accepts any message that
contains an `events` array of `[user, fill]` pairs, wrapped or not.

## Quick start

```bash
git clone https://github.com/onchainsonar/hl-liquidation-alerts
cd hl-liquidation-alerts
cp .env.example .env      # fill in Telegram token, chat id, source
docker compose up -d
```

Without Docker:

```bash
pip install -r requirements.txt
python -m hl_liq
```

Try it offline with the bundled sample:

```bash
python -m hl_liq --replay tests/fixtures/sample.jsonl --console
```

## Config

| Var | Default | |
|---|---|---|
| `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID` | — | if unset, alerts print to console |
| `COINS` | `BTC,ETH,SOL` | subset of these three |
| `MIN_USD` | `100000` | minimum liquidation size |
| `SOURCE` | `websocket` | `websocket` or `node` |
| `WS_URL`, `WS_SUBSCRIBE` | — | provider stream |
| `NODE_FILLS_DIR` | `~/hl/data/node_fills_by_block` | for `SOURCE=node` |
| `PROMO` | `1` | `0` removes the footer line |

## Getting spammed during cascades?

This repo sends one alert per liquidation. [OnchainSonar](https://onchainsonar.com) Pro adds:

- **Clustering** — a cascade becomes one alert with the total, not 40 messages
- **Whale near-liquidation** — positions close to their liq price, *before* it happens
- All coins, per-coin and adaptive thresholds, OI & funding context, labeled wallets
- Nothing to host — runs 24/7

## Tests

```bash
pip install pytest && pytest -q
```

MIT License. Not financial advice.
