import copy
import json
import shutil
from datetime import date, time
from pathlib import Path

from spybot import ingest

FIX = Path(__file__).parent / "fixtures" / "logger"
DAY = date(2026, 11, 17)


def load(name):
    return json.loads((FIX / name).read_text())


def set_first_quote(raw, bid, ask):
    q = raw["quotes"][0]["data"]["results"][0]["quote"]
    q["bid_price"], q["ask_price"] = bid, ask


def test_good_file_parses_all_fields():
    snap, problems = ingest.parse(load("good_1507.json"))
    assert problems == []
    assert (snap.day, snap.run.replace(microsecond=0), snap.spy, snap.vix) == (DAY, time(15, 7, 35), 729.825, 26.79)
    # run time = newest Robinhood stamp (SPY trade 20:07:35Z), not the hand-noted 15:07:30
    leg = snap.legs[("put", 726)]
    assert (leg.bid, leg.ask, leg.bid_size, leg.ask_size) == (0.47, 0.48, 399, 276)
    assert (leg.mark, leg.delta, leg.open_interest, leg.volume) == (0.475, -0.193903, 1972, 214499)
    assert leg.updated_at.tzinfo is not None
    assert set(snap.legs) == {("put", 726), ("put", 721), ("call", 741), ("call", 746)}


def test_stale_quotes_rejected():
    snap, problems = ingest.parse(load("stale_1507.json"))
    assert snap is None and any("stale" in p for p in problems)


def test_locked_quote_is_valid():
    raw = load("good_1507.json")
    set_first_quote(raw, "0.10", "0.10")
    assert ingest.parse(raw)[1] == []


def test_crossed_quote_and_wrong_expiry_rejected():
    raw = load("good_1507.json")
    set_first_quote(raw, "0.12", "0.10")
    assert any("bid > ask" in p for p in ingest.parse(raw)[1])
    raw = load("good_1507.json")
    raw["expiry"] = "2026-11-18"
    assert any("expiry" in p for p in ingest.parse(raw)[1])
    raw = load("good_1507.json")
    next(iter(raw["instruments"].values()))["expiry"] = "2026-11-18"
    assert any("expiry" in p for p in ingest.parse(raw)[1])


def test_missing_field_and_unknown_instrument_rejected():
    raw = load("good_1507.json")
    del raw["quotes"][0]["data"]["results"][0]["quote"]["delta"]
    assert any("missing" in p for p in ingest.parse(raw)[1])
    raw = load("good_1507.json")
    raw["instruments"].pop("a6781697-e1cb-4878-a63f-dfd6041f4c12")
    assert any("unknown instrument" in p for p in ingest.parse(raw)[1])


def _write_raw(root, name, hhmm):
    target = root / "data" / "raw" / DAY.isoformat()
    target.mkdir(parents=True)
    shutil.copy(FIX / name, target / f"{hhmm}.json")


def test_ingest_writes_snapshot_and_loads_it(tmp_path):
    _write_raw(tmp_path, "good_1507.json", "1507")
    assert ingest.ingest(tmp_path, DAY, "1507") == []
    snap = ingest.load_snapshot(tmp_path, DAY, "1507")
    assert snap == ingest.parse(load("good_1507.json"))[0]


def test_ingest_writes_bad_marker(tmp_path):
    _write_raw(tmp_path, "stale_1507.json", "1507")
    assert ingest.ingest(tmp_path, DAY, "1507") != []
    assert (tmp_path / "data/snapshots" / DAY.isoformat() / "1507.bad.json").exists()
    assert ingest.load_snapshot(tmp_path, DAY, "1507") is None


def test_ingest_missing_raw_file(tmp_path):
    assert any("missing" in p for p in ingest.ingest(tmp_path, DAY, "1015"))
    assert ingest.load_snapshot(tmp_path, DAY, "1015") is None


def test_strike_label_checked_against_break_even():
    raw = load("good_1507.json")
    q = raw["quotes"][0]["data"]["results"][0]["quote"]       # put 726, ask 0.48
    q["break_even_price"] = "725.520000"                      # 726 - 0.48: consistent
    assert ingest.parse(raw)[1] == []
    q["break_even_price"] = "724.520000"                      # would be the 725 put: mislabeled
    assert any("strike" in p and "break-even" in p for p in ingest.parse(raw)[1])


def test_run_far_from_its_label_is_rejected(tmp_path):
    _write_raw(tmp_path, "good_1507.json", "1015")            # run_et is 15:07, label says 10:15
    problems = ingest.ingest(tmp_path, DAY, "1015")
    assert any("label" in p for p in problems)


def _assemble_inputs(tmp_path, wrap_quotes=False):
    raw = load("good_1507.json")
    folder = tmp_path / "data" / "raw" / DAY.isoformat()
    folder.mkdir(parents=True)
    (folder / "instruments.json").write_text(json.dumps(raw["instruments"]))
    (folder / "1507.spyvix.json").write_text(
        json.dumps({"run_et": raw["run_et"], "spy": raw["spy"], "vix": raw["vix"]}))
    quotes = json.dumps(raw["quotes"][0])
    if wrap_quotes:
        quotes = json.dumps([{"type": "text", "text": quotes}])
    qpath = tmp_path / "saved-quotes.txt"
    qpath.write_text(quotes)
    return raw, folder, qpath


def test_assemble_builds_raw_file_from_saved_quotes(tmp_path):
    raw, folder, qpath = _assemble_inputs(tmp_path)
    problems = ingest.assemble(tmp_path, DAY, "1507", qpath)
    built = json.loads((folder / "1507.json").read_text())
    assert built == {"run_et": raw["run_et"], "expiry": DAY.isoformat(), "spy": raw["spy"],
                     "vix": raw["vix"], "instruments": raw["instruments"], "quotes": raw["quotes"]}
    assert problems == []  # assemble also runs ingest
    assert ingest.load_snapshot(tmp_path, DAY, "1507") is not None


def test_assemble_accepts_text_block_wrapped_quotes(tmp_path):
    raw, folder, qpath = _assemble_inputs(tmp_path, wrap_quotes=True)
    ingest.assemble(tmp_path, DAY, "1507", qpath)
    assert json.loads((folder / "1507.json").read_text())["quotes"] == raw["quotes"]


def test_assemble_reports_missing_spyvix(tmp_path):
    raw, folder, qpath = _assemble_inputs(tmp_path)
    (folder / "1507.spyvix.json").unlink()
    problems = ingest.assemble(tmp_path, DAY, "1507", qpath)
    assert any("1507.spyvix.json" in p for p in problems)
    assert not (folder / "1507.json").exists()


def test_assemble_command_prints_ok(tmp_path, capsys):
    from spybot.__main__ import main
    _, _, qpath = _assemble_inputs(tmp_path)
    code = main(["assemble", DAY.isoformat(), "1507", str(qpath), "--root", str(tmp_path)])
    assert (code, capsys.readouterr().out.strip()) == (0, "ok")


def test_assemble_reports_spyvix_missing_field(tmp_path):
    raw, folder, qpath = _assemble_inputs(tmp_path)
    (folder / "1507.spyvix.json").write_text(json.dumps({"spy": raw["spy"], "vix": raw["vix"]}))
    problems = ingest.assemble(tmp_path, DAY, "1507", qpath)
    assert any("run_et" in p for p in problems)


def test_assemble_accepts_several_quote_files(tmp_path):
    raw, folder, qpath = _assemble_inputs(tmp_path)
    block = raw["quotes"][0]
    first = {"data": {"results": block["data"]["results"][:2]}}
    second = {"data": {"results": block["data"]["results"][2:]}}
    (tmp_path / "q1.json").write_text(json.dumps(first))
    (tmp_path / "q2.json").write_text(json.dumps(second))
    problems = ingest.assemble(tmp_path, DAY, "1507", [tmp_path / "q1.json", tmp_path / "q2.json"])
    assert problems == []
    assert json.loads((folder / "1507.json").read_text())["quotes"] == [first, second]


def test_strike_label_uses_adjusted_mark_when_present():
    # Real 2026-11-18 15:29 case: break-even = strike - adjusted_mark_price, not strike - ask.
    raw = load("good_1507.json")
    q = raw["quotes"][0]["data"]["results"][0]["quote"]       # put 726
    q["bid_price"], q["ask_price"], q["adjusted_mark_price"] = "0.40", "0.48", "0.44"
    q["break_even_price"] = "725.560000"                      # 726 - 0.44
    assert ingest.parse(raw)[1] == []
    q["break_even_price"] = "724.560000"                      # 725 - 0.44: mislabeled
    assert any("strike" in p and "break-even" in p for p in ingest.parse(raw)[1])


def _set_spy(raw, price):
    raw["spy"]["data"]["results"][0]["quote"]["last_trade_price"] = price


def _drop_greeks(raw, index):
    q = raw["quotes"][0]["data"]["results"][index]["quote"]
    q["implied_volatility"], q["delta"] = None, None
    return raw["instruments"][q["instrument_id"]]


def test_in_the_money_leg_may_lack_greeks():
    raw = load("good_1507.json")
    _set_spy(raw, "700.000000")                    # put 726 is now in the money
    assert _drop_greeks(raw, 0) == {"type": "put", "strike": 726.0, "expiry": "2026-11-17"}
    snap, problems = ingest.parse(raw)
    assert problems == []
    leg = snap.legs[("put", 726)]
    assert (leg.iv, leg.delta, leg.bid, leg.ask) == (None, None, 0.47, 0.48)


def test_out_of_the_money_leg_still_needs_greeks():
    raw = load("good_1507.json")                   # SPY 729.825: put 726 out of the money
    _drop_greeks(raw, 0)
    snap, problems = ingest.parse(raw)
    assert snap is None and any("missing implied_volatility, delta" in p for p in problems)


def test_in_the_money_leg_still_needs_prices():
    raw = load("good_1507.json")
    _set_spy(raw, "700.000000")
    q = raw["quotes"][0]["data"]["results"][0]["quote"]
    q["bid_price"] = None
    assert ingest.parse(raw)[0] is None


def test_snapshot_with_missing_greeks_round_trips(tmp_path):
    raw = load("good_1507.json")
    _set_spy(raw, "700.000000")
    _drop_greeks(raw, 0)
    _write_raw_obj(tmp_path, raw, "1507")
    assert ingest.ingest(tmp_path, DAY, "1507") == []
    assert ingest.load_snapshot(tmp_path, DAY, "1507").legs[("put", 726)].delta is None


def _write_raw_obj(root, raw, hhmm):
    folder = root / "data" / "raw" / DAY.isoformat()
    folder.mkdir(parents=True, exist_ok=True)
    (folder / f"{hhmm}.json").write_text(json.dumps(raw))


def test_reingest_replaces_the_previous_outcome(tmp_path):
    raw = load("good_1507.json")
    _drop_greeks(raw, 0)                           # out of the money: bad
    _write_raw_obj(tmp_path, raw, "1507")
    folder = tmp_path / "data" / "snapshots" / DAY.isoformat()
    assert ingest.ingest(tmp_path, DAY, "1507") != []
    assert [p.name for p in folder.iterdir()] == ["1507.bad.json"]
    _write_raw_obj(tmp_path, load("good_1507.json"), "1507")
    assert ingest.ingest(tmp_path, DAY, "1507") == []
    assert [p.name for p in folder.iterdir()] == ["1507.json"]
    _write_raw_obj(tmp_path, raw, "1507")
    assert ingest.ingest(tmp_path, DAY, "1507") != []
    assert [p.name for p in folder.iterdir()] == ["1507.bad.json"]


# --- Robinhood stamps decide the run time (2026-11-24 root cause: hand-noted time was ~70 s early) ---

def test_run_time_comes_from_robinhood_stamps_not_the_noted_time():
    raw = load("good_1507.json")
    raw["run_et"] = "2026-11-17T15:06:20-05:00"     # noted 75 s before the quotes were taken
    snap, problems = ingest.parse(raw)
    assert problems == []
    assert snap.run.replace(microsecond=0) == time(15, 7, 35)


def test_run_time_falls_back_to_noted_time_without_stamps():
    raw = load("good_1507.json")
    del raw["spy"]["data"]["results"][0]["quote"]["venue_last_trade_time"]
    del raw["vix"]["data"]["quotes"][0]["updated_at"]
    snap, problems = ingest.parse(raw)
    assert problems == []
    assert snap.run == time(15, 7, 30)


def test_run_time_is_eastern_even_from_utc_stamps(tmp_path):
    raw = load("good_1507.json")
    raw["run_et"] = "2026-11-17T15:05:00-05:00"
    _write_raw_obj(tmp_path, raw, "1507")
    assert ingest.ingest(tmp_path, DAY, "1507") == []   # 15:07:35 ET is within 5 min of label 1507


# --- one stale contract is dropped, not fatal (2026-11-24 root cause: a $0/$0.01 quote that never
#     changes keeps its old updated_at, because Robinhood stamps the last bid/ask change) ---

def _many_legs(n_extra=20):
    """good_1507 plus n_extra out-of-the-money puts (strikes 700, 701, ...) cloned from the 726 put."""
    raw = load("good_1507.json")
    block = raw["quotes"][0]["data"]["results"]
    base_id = block[0]["quote"]["instrument_id"]
    assert raw["instruments"][base_id] == {**raw["instruments"][base_id], "type": "put", "strike": 726.0}
    for i in range(n_extra):
        strike, iid = 700.0 + i, f"clone-{i}"
        q = copy.deepcopy(block[0])
        q["quote"]["instrument_id"] = iid
        mark = float(q["quote"].get("adjusted_mark_price") or q["quote"]["ask_price"])
        q["quote"]["break_even_price"] = f"{strike - mark:.6f}"
        block.append(q)
        raw["instruments"][iid] = {**raw["instruments"][base_id], "strike": strike}
    return raw


def _age_quote(raw, iid, minutes):
    from datetime import timedelta
    for b in raw["quotes"]:
        for r in b["data"]["results"]:
            if r["quote"]["instrument_id"] == iid:
                t = ingest.parse_ts(r["quote"]["updated_at"]) - timedelta(minutes=minutes)
                r["quote"]["updated_at"] = t.isoformat()


def test_one_stale_contract_is_dropped_and_listed():
    raw = _many_legs()
    _age_quote(raw, "clone-3", 30)                 # the 703 put, unchanged for 30 minutes
    snap, problems = ingest.parse(raw)
    assert problems == []
    assert ("put", 703) not in snap.legs
    assert ("put", 702) in snap.legs and ("put", 726) in snap.legs
    assert len(snap.dropped) == 1
    assert snap.dropped[0].startswith("put:703") and "stale" in snap.dropped[0]


def test_good_file_drops_nothing():
    snap, _ = ingest.parse(load("good_1507.json"))
    assert snap.dropped == ()


def test_too_many_stale_contracts_reject_the_whole_run():
    raw = _many_legs()                             # 24 contracts; 5% allows 1, not 2
    _age_quote(raw, "clone-3", 30)
    _age_quote(raw, "clone-4", 30)
    snap, problems = ingest.parse(raw)
    assert snap is None
    assert any("stale" in p for p in problems)


def test_dropped_contracts_are_saved_with_the_snapshot(tmp_path):
    raw = _many_legs()
    _age_quote(raw, "clone-3", 30)
    _write_raw_obj(tmp_path, raw, "1507")
    assert ingest.ingest(tmp_path, DAY, "1507") == []
    saved = json.loads((tmp_path / "data" / "snapshots" / DAY.isoformat() / "1507.json").read_text())
    assert len(saved["dropped"]) == 1 and saved["dropped"][0].startswith("put:703")
    assert ingest.load_snapshot(tmp_path, DAY, "1507").dropped == tuple(saved["dropped"])


# --- a day's entry and exit snapshots (exit is 12:30/12:40 on early-close days) ---

def _save_snap(root, day, hhmm):
    raw = load("good_1507.json")
    folder = root / "data" / "snapshots" / day.isoformat()
    folder.mkdir(parents=True, exist_ok=True)
    snap, _ = ingest.parse(raw)
    (folder / f"{hhmm}.json").write_text(json.dumps(ingest._to_json(snap)))


def test_load_day_uses_1530_on_a_normal_day(tmp_path):
    day = date(2026, 11, 25)
    for h in ("1015", "1530", "1230"):
        _save_snap(tmp_path, day, h)
    snaps = ingest.load_day(tmp_path, day)
    assert set(snaps) == {"1015", "exit", "exit_fallback"}
    assert snaps["1015"] is not None and snaps["exit"] is not None and snaps["exit_fallback"] is None


def test_load_day_uses_1230_on_an_early_close_day(tmp_path):
    day = date(2026, 11, 27)
    _save_snap(tmp_path, day, "1015")
    _save_snap(tmp_path, day, "1530")                # should be ignored on a 1 PM close
    assert ingest.load_day(tmp_path, day)["exit"] is None
    _save_snap(tmp_path, day, "1240")
    snaps = ingest.load_day(tmp_path, day)
    assert snaps["exit"] is None and snaps["exit_fallback"] is not None
