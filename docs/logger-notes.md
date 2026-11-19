# Logger notes

## Hand run, 2026-11-17 15:14 ET (labelled `1515`)

- SPY 729.39, VIX 27.0. 43 same-day contracts quoted in one `get_option_quotes` call (puts 710–727, calls 733–757); 17 of them (puts 718–727, calls 733–739) copied into `data/raw/2026-11-17/1515.json`.
- `python -m spybot ingest 2026-11-17 1515` → `ok`; snapshot written.
- **Cost:** the 43-contract answer came back inline, about 56,000 characters (~20k tokens), and had to be retyped (~5k tokens). Listing one expiry's instruments (`get_option_instruments`, puts only) came back inline too, about 30k tokens.
- **Near miss:** while retyping, put strikes were first labelled one dollar off. Caught by checking each contract's `break_even_price` (put strike = break-even + ask; call strike = break-even − ask). `ingest` now runs this check on every leg that carries `break_even_price`, and rejects the file on a mismatch.

## Finding: big answers are saved to files automatically

Any tool answer over roughly 100,000 characters is saved by Claude Code to a file instead of being shown (seen for the history downloads: 115k–800k characters). A saved answer can be copied unchanged, with no retyping and no labelling risk.

A quote call with about 90 or more contracts crosses that line (~1,300 characters per contract). So the cheapest and safest logger run quotes **more** contracts, not fewer: for example every listed strike from SPY − 45 to SPY + 45 in one call.

## Budget estimate (to check in the first week)

| Step | Per run | Per day |
|---|---|---|
| SPY + VIX quotes | ~1k tokens | ~5k |
| Instruments (first run only) | ~30k | ~30k |
| Option quotes, ≥ 90 contracts, saved to file | ~2k | ~10k |
| Writing the raw file with a script | ~3k | ~15k |
| **Total** | | **~60k** |

If an answer is not saved to a file (under ~100k characters), a run costs about 25k tokens instead, ~150k a day.

## Scheduled test run, 2026-11-18 10:15 (task spy-logger-test-1015)

- Ran from the project folder (deny rules applied). Quotes taken 10:12:38 ET; ingest **ok**. No order tools called (tool list: chains, instruments, equity/index/option quotes, Bash, Write).
- 65 contracts quoted (21 puts 690-730, 44 calls 733-776). Puts below 715 are listed only every $5, so far put legs are sparse; wide/far setups will often show "not logged".
- 14 far calls (763-776) had bid 0.00; accepted as valid quotes.
- Robinhood's answers came back **inline, not saved to a file**, so the run retyped ~47 KB of quotes. Checked afterwards against the raw tool answer in the run's transcript: 65/65 contracts, 0 fields different.
- Cost of this one run (counted once per model turn): ~38k output tokens, ~152k cache-write, ~1.9M cache-read tokens over 14 turns. ~24k of the output was retyping the 47 KB quote answer in one Write; another ~5k retyping the instrument list. Context grew from ~43k to ~194k tokens per turn because each inline answer stays in context. (An earlier figure of 139k output double-counted turns.)
- Fix (commit 1dbe8dc): quote every listed contract (~150) so the answer passes the ~100k-character auto-save size, and a tested `spybot assemble` command builds the raw file from the saved file. Rebuilt today's 1015 file with it: identical.

## Scheduled test run, 2026-11-18 15:30 (lean version, task spy-logger-test-1530)

- Ran from the project folder at 15:28:59 ET. Read tools only. 146 of 148 contracts quoted in one call.
- The quote answer **was saved to a file automatically** (103,956 characters, just over the ~100k size). Nothing was retyped.
- Cost: ~6.8k output, ~56k cache-write, ~391k cache-read tokens over 5 turns (the 10:15 run used ~38k / ~152k / ~1.9M). This run skipped the once-a-day contract listing.
- Check result: **BAD**, caused only by the in-the-money contracts added as padding:
  - 43 deep in-the-money puts (and one call) have no implied volatility or delta.
  - The strike-label check assumed break-even = strike ± ask. Robinhood actually uses strike ± `adjusted_mark_price`. On out-of-the-money legs with a 1-cent spread, ask and adjusted mark are equal, so it never showed before; on in-the-money legs they differ by a few cents.
  - All out-of-the-money legs (the ones the strategy would use) passed every check.
- Margin is thin: 104k vs a ~100k save size. Days with fewer listed strikes could fall back to inline.
- Fixes (after the 15:30 test): the strike-label check now uses `adjusted_mark_price` (ask only for older files without it); in-the-money legs may lack implied volatility and delta (all prices, sizes and timestamps are still required); re-checking a run replaces its earlier good/bad outcome. In-the-money contracts are **kept**, not dropped: on a losing day the 10:15 short leg is in the money at 3:30, and its 3:30 price is exactly what the report needs. Re-checked the real 1015 and 1530 files: both ok (1530: 146 legs, 43 without greeks).
