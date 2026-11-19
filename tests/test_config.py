from datetime import time

import pytest

from spybot import config


def test_plan_v2_values():
    assert config.WIDTHS == (2, 5, 10)
    assert config.K_VALUES[0] == 0.5 and config.K_VALUES[-1] == 2.0 and len(config.K_VALUES) == 16
    assert config.FEES_ROUND_TRIP == pytest.approx(0.16)
    assert config.SLIPPAGE["cautious"] == (0.055, 0.02)
    assert config.ENTRY_TIME == time(10, 15) and config.EXIT_TIME == time(15, 30)
    assert config.MARKET_TZ == "America/New_York"
