"""The daily trade ticket: what plan v2 would do at 10:15, in plain words.

The ticket is advice to a person. The owner places any real order in the Robinhood app;
this project never places, changes or cancels orders.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

from spybot import config
from spybot.compare import RealRow
from spybot.pricetest import cost_per_share


@dataclass(frozen=True)
class Ticket:
    action: str            # "trade", "skip" or "no data"
    reason: str
    side: str | None = None
    short: int | None = None
    long: int | None = None
    width: int | None = None
    limit: float | None = None      # start the limit order at the midpoint credit
    floor: float | None = None      # lowest credit worth taking: break-even + margin, rounded up
    need: float | None = None
    max_loss: float | None = None   # dollars per contract if the spread finishes at full width
    text: str = ""


def _cent_up(x: float) -> float:
    return math.ceil(round(x * 100, 6)) / 100


def make_ticket(row: RealRow | None, need: float | None, halted: str | None = None,
                margin: float = config.EDGE_MARGIN) -> Ticket:
    if row is None or row.status not in ("ok", "skipped"):
        why = "no usable 10:15 quotes" if row is None else row.status
        return Ticket("no data", why, text=f"No ticket today: {why}.")
    base = dict(side=row.side, short=row.short, long=row.long, width=row.setup.width, need=need)
    if row.status == "skipped":
        why = "skip rules: " + ", ".join(row.skipped)
        return Ticket("skip", why, **base, text=f"No trade today ({why}).")
    if halted:
        return Ticket("skip", halted, **base, text=f"No trade today ({halted}).")
    if need is None:
        why = f"no break-even credit for VIX band {row.vix_band}"
        return Ticket("skip", why, **base, text=f"No trade today ({why}).")
    floor = _cent_up(need + margin)
    mid = round(row.mid_credit, 2)
    if row.mid_credit < need + margin:
        why = f"credit ${mid:.2f} is below the ${floor:.2f} needed (break-even ${need:.3f} + ${margin:.2f})"
        return Ticket("skip", why, **base, limit=mid, floor=floor, text=f"No trade today: {why}.")
    max_loss = round((row.setup.width - row.mid_credit + cost_per_share("cautious")) * 100, 2)
    text = (f"Sell 1 SPY {row.short}/{row.long} {row.side} credit spread, expiring today. "
            f"Limit ${mid:.2f} credit, step down one cent at a time to ${floor:.2f}; skip the day if unfilled. "
            f"Close at 3:30 PM ET. Max loss about ${max_loss:.0f}. You place and close this order yourself "
            f"in the Robinhood app; the bot never trades.")
    return Ticket("trade", "credit clears break-even + margin", **base, limit=mid, floor=floor,
                  max_loss=max_loss, text=text)
