"""Fixed settings from plan v2 (docs/plan-v2.md) and the approved
price-test design (docs/superpowers/specs/2026-11-17-price-test-and-logger-design.md).

Changing any value here changes the test. Owner approval is required.
"""
from __future__ import annotations

from datetime import date, time

# Timing (US Eastern, as in plan v2)
MARKET_TZ = "America/New_York"
ENTRY_TIME = time(10, 15)
EXIT_TIME = time(15, 30)
EXIT_FALLBACK_TIME = time(15, 40)
LOG_TIMES = (time(10, 0), time(10, 15), time(10, 30), time(15, 30), time(15, 40))
EXIT_MINUTES_BEFORE_CLOSE = 30   # exit 30 min before the close (12:30 on 1 PM early-close days)
TRADING_MINUTES_PER_DAY = 390

# Setups swept by the price test
WIDTHS = (2, 5, 10)              # dollars between strikes
K_VALUES = tuple(round(0.5 + 0.1 * i, 1) for i in range(16))  # distance in VIX expected moves, 0.5..2.0

# Costs (plan v2 cost rule)
FEE_PER_CONTRACT_LEG = 0.04      # real: OCC $0.02 + ORF $0.02 (Task 2 review, 2026-11-17)
FEES_ROUND_TRIP = 0.16           # 2 legs x open and close, per contract, dollars
SLIPPAGE = {                     # per share: (entry, exit), worse than the midpoint
    "best": (0.01, 0.01),
    "cautious": (0.055, 0.02),
}

# Direction and skip rules (designer's defaults, approved with the design)
TREND_LOOKBACK = 20              # days in the moving average of closes
TREND_BAND = 0.005               # 0.5% above/below the average = up/down, else unclear
GAP_DOWN_SKIP = 0.01             # skip if the open is more than 1% below the previous close

# Reporting
VIX_BANDS = (15, 20, 30)         # bands: <15, 15-20, 20-30, 30+
PERIODS = {
    "train": (date(2022, 1, 1), date(2023, 12, 31)),
    "validation": (date(2024, 1, 1), date(2024, 12, 31)),
    "test": (date(2025, 1, 1), None),   # sealed: only the `final` command shows it
}
HISTORY_START = date(2022, 1, 3)

# Logger checks
LOGGER_START = date(2026, 11, 24)   # first full day of the five scheduled daily runs (they began 11-23 afternoon)
STALE_QUOTE_SEC = 60
STALE_DROP_MAX_SHARE = 0.05   # up to 5% of contracts may be dropped as stale; more rejects the run

# SPY Tuesday expiries were first listed 2022-11-14 (first expiry Tue 2022-11-15);
# Thursday expiries were first listed 2022-11-16 (first expiry Thu 2022-11-17).
# Source: https://cdn.cboe.com/resources/product_update/2022/Update-Cboe-Options-to-List-SPY-and-QQQ-Tuesday-and-Thursday-Expiring-Weekly-Options.pdf
TUE_THU_0DTE_START = date(2022, 11, 15)
