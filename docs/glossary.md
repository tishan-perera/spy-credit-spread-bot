# Glossary

**0DTE** ("zero days to expiration"). An option that expires the same day it is traded. SPY has these every trading day.

**Backtest.** Testing a strategy on past data to see how it would have done.

**Bid / ask.** The highest price a buyer offers / the lowest price a seller accepts. The gap between them is a hidden cost.

**Break-even credit.** The smallest average payment a spread must collect, after fees and slippage, for the strategy to break even over time.

**Call spread.** Selling a call option and buying a further-away call option as protection. It pays if SPY does **not** rise past the short strike.

**Credit.** The money received up front when the spread is sold. It is the most the trade can make.

**Credit spread.** Selling one option and buying a cheaper one further away, so the possible loss is capped. Max loss = width − credit.

**Delta.** Roughly, the market's estimate of the chance an option finishes "in the money". A 10-delta option has about a 10% chance.

**Expected move.** How far SPY is likely to move in the time left, worked out from the VIX.

**Fees.** Regulatory and clearing charges: about $0.04 per contract per leg, so about $0.16 to open and close a two-leg spread.

**MCP connector.** The bridge that lets a Claude session read Robinhood data through named tools. This project uses only its read tools.

**Midpoint (mark).** Halfway between bid and ask.

**Paper trading.** Pretend trading with real prices but no real money.

**Put spread.** Selling a put option and buying a further-away put option as protection. It pays if SPY does **not** fall past the short strike.

**Slippage.** How much worse the real fill price is than the midpoint.

**SPY.** An exchange-traded fund that tracks the S&P 500 index.

**Strike.** The price level an option is tied to.

**TDD (test-driven development).** Write an automated test that fails first, then write the code that makes it pass. Every feature here was built that way.

**VIX.** Cboe's "fear index": the market's expectation of how much the S&P 500 will move over the next 30 days, as a yearly percentage.

**Width.** The distance between the two strikes of a spread ($2, $5 or $10 here). It caps the possible loss.
