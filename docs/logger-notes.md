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

## Morning runs rejected, 2026-11-24 (root cause and fix)

- All three morning runs (10:00, 10:15, 10:30) collected all 240 contracts but were marked **BAD**: one contract, the 769 call (about $50 above SPY), had a quote 28, 44 and 59 minutes "old".
- Root cause 1: Robinhood's `updated_at` is the time the bid, ask or sizes **last changed**, not when the quote was served. Across the three runs, 239 contracts changed and had fresh stamps; the 769 call ($0 bid / $0.01 ask, 1,377 offered) never changed and kept its 9:30:01 stamp, while its implied volatility and delta were still recalculated. No contract had an unchanged quote with a refreshed stamp. The 60-second rule assumed the opposite and let one worthless contract reject a whole run.
- Root cause 2 (2026-11-23 3:30 run): `run_et` was noted by hand before the 240-id request, which takes 50-70 s to send, so every quote looked 61-72 s old. Today's 10:00 run was 53 s off.
- Fix (owner approved): the run time comes from Robinhood's SPY/VIX stamps (hand-noted time only as a fallback); a single stale contract is left out and listed under `dropped` in the snapshot (its strike reads "not logged"); more than 5% stale still rejects the run.

## Workflow gaps found and fixed, 2026-11-25 (owner approved "fix all")

A system test (all 8 runs since the fix ok, 118 tests, no orders on the account per Robinhood's own order list) found nine gaps. Fixes:

1. **Logged days did not count** ("0 usable logged days"): history was refreshed by hand and stopped at 11-16. Now a daily `spy-history-refresh` task (read-only, ~16:30 ET) downloads SPY/VIX daily and SPY 5-minute bars in answers big enough to be saved to files, and `spybot save-history` files them; the newest download wins when files overlap. Refreshed once by hand on 11-25: history now runs to 11-24 and the report counts 4 usable days. New VIX jumps on 11-20 and 11-23 match Cboe (real moves).
2. **Early-close days had no exit**: exits are 12:30/12:40 on 1 PM closes (`calendar.exit_runs`); one-time tasks cover 2026-11-27 and 2026-12-24. The report and dashboard read the exit through `ingest.load_day`.
3. **Missed runs were invisible**: planned runs now come from the market calendar (`health.planned`), not a hand-kept list. The dashboard shows ok / bad / error / missed / next / planned.
4. **Nobody was told about failures**: each run ends with `spybot health --new-run-problems` and sends a push notification for a new problem; the background watcher (`ops/watch-service.sh`) raises a Mac notification every 15 minutes for any new problem, even when no Claude run happens.
5. **Calendar ended in 2026**: 2027-2028 holidays and early closes (ICE release of 2025-12-23), Dec 2026 and 2027 Fed/CPI/jobs dates added; a test and a dashboard warning fire when either list covers less than 60 days ahead.
6. **Logged data only on this Mac**: the watcher copies `data/raw`, `snapshots`, `history` and `cboe` to iCloud Drive (`SPY-bot-backup`) every 15 minutes, add/update only.
7. **Runs that stopped before the check left no trace**: `HHMM.error.txt` now shows as an error; unplanned runs write `HHMM.skipped.txt`, which is not a problem.
8. **Cost tracking missed half the runs**: daily-task runs are labelled from the task name and start time; per-day totals added. Real cost with all five runs: about 45-59k output and ~360k new (cache-write) tokens a day, plus 3-4 million cache re-reads. That is above the design's "about 250k a day" if new tokens count; the budget definition is the owner's call (not changed).
9. **Dashboard and report disagreed on usable days** (4 vs 0): the dashboard now uses the report's rule (a 10:15 run plus history up to the day before). Empty `.claude/.cc-writes` folders that the Claude app leaves in `data/raw` are harmless and were removed.

Test values pinned to real data changed for 11-18 and 11-24 (17.34 and 20.34 → 9.34 each): with history through the day before, those days are judged by plan v2 (call spreads in a downtrend) instead of the sell-every-day fallback. Checked with the old code on the new data: same results, so the change comes from the data, not the code.
