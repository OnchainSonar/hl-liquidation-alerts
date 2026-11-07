import json
from pathlib import Path

import pytest

from hl_liq.notify import format_alert
from hl_liq.parser import Filter, liquidations_from_message

FIX = Path(__file__).parent / "fixtures" / "sample.jsonl"


def all_liqs():
    for line in FIX.read_text().splitlines():
        yield from liquidations_from_message(json.loads(line))


def test_only_liquidated_side_is_parsed():
    liqs = list(all_liqs())
    assert all(l.user.startswith("0x7a47") for l in liqs)
    assert {l.tid for l in liqs} == {1, 2, 3, 4, 6}


def test_filter_threshold_coins_and_dedupe():
    f = Filter(["BTC", "ETH", "SOL"], 100_000)
    kept = [l for l in all_liqs() if f.accept(l)]
    assert [(l.coin, l.side) for l in kept] == [("ETH", "LONG"), ("SOL", "SHORT"), ("BTC", "LONG")]
    assert round(kept[0].notional) == round(3182.4 * 760)


def test_subset_of_coins():
    f = Filter(["sol"], 0)
    assert [l.coin for l in all_liqs() if f.accept(l)] == ["SOL"]


def test_unsupported_coin_rejected():
    with pytest.raises(ValueError):
        Filter(["BTC", "DOGE"], 0)


def test_alert_text():
    liq = next(l for l in all_liqs() if l.coin == "ETH")
    text = format_alert(liq)
    assert "LONG LIQUIDATED · ETH" in text and "$2.42M" in text and "onchainsonar.com" in text
