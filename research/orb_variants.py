#!/usr/bin/env python3
"""ORB variants study: which tweaks of the skill's opening-range breakout hold up
out of sample? Standard library only.

    python research/orb_variants.py            # fetch (cached) + run, writes research/out/
    python research/orb_variants.py --offline  # rerun on the cached bars only

Data: Yahoo Finance 5-minute bars, last 60 days (the most Yahoo serves at 5 min).
Every result is in R (multiples of the risk at the stop), after costs of
$0.01 per share each way. Sessions are split by date: the first two thirds
rank the variants (in-sample), the last third checks them (out-of-sample).
Long only, one trade per symbol per day, stop first when a bar touches both.
"""
import argparse
import datetime as dt
import itertools
import json
import math
import os
import statistics
import sys
import time
import urllib.request

SYMBOLS = ["SPY", "QQQ", "TSLA", "NVDA", "AAPL", "AMD", "META", "AMZN", "MSFT", "GOOGL",
           "NFLX", "AVGO", "MU", "PLTR", "COIN"]
HERE = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(HERE, "data")
OUT = os.path.join(HERE, "out")
UA = "Mozilla/5.0 (compatible; day-trader-skill-research/1.0)"
OPEN, CLOSE = 9 * 60 + 30, 16 * 60
COST = 0.01  # $ per share, each way


# ---------------------------------------------------------------- New York time without tz files
def _nth_sunday(y, m, n):
    d = dt.date(y, m, 1)
    d += dt.timedelta(days=(6 - d.weekday()) % 7)
    return d + dt.timedelta(weeks=n - 1)


def to_ny(ts):
    u = dt.datetime.fromtimestamp(ts, dt.timezone.utc).replace(tzinfo=None)
    y = u.year
    start = dt.datetime.combine(_nth_sunday(y, 3, 2), dt.time(7))   # 2:00 EST = 7:00 UTC
    end = dt.datetime.combine(_nth_sunday(y, 11, 1), dt.time(6))    # 2:00 EDT = 6:00 UTC
    return u + dt.timedelta(hours=-4 if start <= u < end else -5)


# ---------------------------------------------------------------- data
def fetch(sym, offline):
    os.makedirs(CACHE, exist_ok=True)
    path = os.path.join(CACHE, sym + ".json")
    if offline or (os.path.exists(path) and time.time() - os.path.getmtime(path) < 6 * 3600):
        with open(path) as fh:
            return json.load(fh)
    last = None
    for host in ("query2", "query1"):
        url = "https://%s.finance.yahoo.com/v8/finance/chart/%s?range=60d&interval=5m" % (host, sym)
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=30) as r:
                doc = json.load(r)
            with open(path, "w") as fh:
                json.dump(doc, fh)
            time.sleep(1.0)
            return doc
        except Exception as e:  # noqa: BLE001 - report and try the other host
            last = e
            time.sleep(3)
    raise SystemExit("could not fetch %s: %s" % (sym, last))


def sessions(doc):
    """{date: [bar,...78]} for full regular sessions; bar = dict(m, o, h, l, c, v)."""
    r = doc["chart"]["result"][0]
    q = r["indicators"]["quote"][0]
    days = {}
    for i, ts in enumerate(r.get("timestamp") or []):
        o, h, l, c, v = (q[k][i] for k in ("open", "high", "low", "close", "volume"))
        if None in (o, h, l, c):
            continue
        t = to_ny(ts)
        m = t.hour * 60 + t.minute
        if t.second or m % 5 or not OPEN <= m < CLOSE:
            continue
        days.setdefault(t.date(), {})[m] = {"m": m, "o": o, "h": h, "l": l, "c": c, "v": v or 0}
    return {d: [b[k] for k in sorted(b)] for d, b in days.items() if len(b) == 78}


# ---------------------------------------------------------------- the rule
def ftick(x):
    return math.floor(round(x, 2) * 100 + 1e-6) / 100.0


def rtick(x):
    return math.floor(x * 100 + 0.5) / 100.0


def trade(day, prev_close, spy_day, v):
    """One session under variant v -> R after costs, or None (no trade)."""
    n = v["or"] // 5
    ob = day[:n]
    oh, ol = rtick(max(b["h"] for b in ob)), rtick(min(b["l"] for b in ob))
    avg_v = sum(b["v"] for b in ob) / n
    cum_pv = sum((b["h"] + b["l"] + b["c"]) / 3 * b["v"] for b in ob)
    cum_v = sum(b["v"] for b in ob)
    for k in range(n, 78):
        b = day[k]
        cum_pv += (b["h"] + b["l"] + b["c"]) / 3 * b["v"]
        cum_v += b["v"]
        end = b["m"] + 5
        if end < OPEN + 15 or end > v["cutoff"]:
            if end > v["cutoff"]:
                return None
            continue
        if b["c"] <= oh:
            continue
        # first close above the range: the signal. Filters decide if we take it.
        f = v["filter"]
        if f == "vol" and not (avg_v and b["v"] >= avg_v):
            return None
        if f == "vwap" and not (cum_v and b["c"] > cum_pv / cum_v):
            return None
        if f == "gap" and not (prev_close and day[0]["o"] > prev_close):
            return None
        if f == "spy":
            if not spy_day or spy_day[k]["c"] <= spy_day[0]["o"]:
                return None
        e = rtick(b["c"])
        s = ftick((oh + ol) / 2) if v["stop"] == "mid" else ftick(ol)
        risk = e - s
        if risk <= 0 or risk < e * 0.0005:
            return None
        t = rtick(e + v["target"] * risk) if v["target"] else None
        for x in day[k + 1:]:
            if x["l"] <= s:
                return -1.0 - 2 * COST / risk
            if t is not None and x["h"] >= t:
                return (t - e - 2 * COST) / risk
            if x["m"] + 5 >= 15 * 60 + 55:
                return (x["c"] - e - 2 * COST) / risk
        return None
    return None


def stats(rs):
    if not rs:
        return {"n": 0}
    wins = [r for r in rs if r > 0]
    loss = [-r for r in rs if r <= 0]
    eq = peak = dd = 0.0
    for r in rs:
        eq += r
        peak = max(peak, eq)
        dd = max(dd, peak - eq)
    return {"n": len(rs), "win": round(100 * len(wins) / len(rs), 1), "avgR": round(statistics.mean(rs), 3),
            "sumR": round(sum(rs), 1), "pf": round(sum(wins) / sum(loss), 2) if loss else None,
            "maxddR": round(dd, 1)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--offline", action="store_true")
    a = ap.parse_args()
    data = {}
    for sym in SYMBOLS:
        data[sym] = sessions(fetch(sym, a.offline))
        print("%-5s %d full sessions" % (sym, len(data[sym])), file=sys.stderr)
    dates = sorted(set().union(*[set(d) for d in data.values()]))
    cut = dates[int(len(dates) * 2 / 3)]
    grid = [dict(zip(("or", "stop", "target", "cutoff", "filter"), g)) for g in itertools.product(
        (15, 30), ("mid", "low"), (1.0, 1.5, 2.0, None), (15 * 60 + 30, 11 * 60), ("none", "vol", "vwap", "gap", "spy"))]
    rows = []
    for v in grid:
        ins, oos, per_sym = [], [], {}
        for sym, days in data.items():
            ds = sorted(days)
            for i, d in enumerate(ds):
                r = trade(days[d], days[ds[i - 1]][-1]["c"] if i else None, data["SPY"].get(d), v)
                if r is None:
                    continue
                (ins if d < cut else oos).append(r)
                per_sym.setdefault(sym, []).append(r)
        label = "OR%d stop=%s target=%s cutoff=%s filter=%s" % (
            v["or"], v["stop"], ("%gR" % v["target"]) if v["target"] else "close", "15:30" if v["cutoff"] > 900 else "11:00",
            v["filter"])
        rows.append({"variant": label, "v": v, "in": stats(ins), "out": stats(oos), "all": stats(ins + oos),
                     "symbols_positive": sum(1 for x in per_sym.values() if sum(x) > 0), "symbols": len(per_sym)})
    os.makedirs(OUT, exist_ok=True)
    with open(os.path.join(OUT, "orb_variants.json"), "w") as fh:
        json.dump({"dates": [str(dates[0]), str(cut), str(dates[-1])], "symbols": SYMBOLS, "cost_per_share": COST,
                   "rows": rows}, fh, indent=1, default=str)
    base = next(r for r in rows if r["v"] == {"or": 15, "stop": "mid", "target": 1.0, "cutoff": 930, "filter": "none"})
    print("sessions %s .. %s, out-of-sample from %s, %d variants" % (dates[0], dates[-1], cut, len(rows)))
    fmtr = lambda s: "n=%-4s win=%-5s avgR=%-7s sumR=%-6s pf=%-5s dd=%s" % (
        s.get("n"), s.get("win"), s.get("avgR"), s.get("sumR"), s.get("pf"), s.get("maxddR"))
    print("\nBASE (the skill): %s\n  in  %s\n  out %s\n  sym+ %d/%d" % (base["variant"], fmtr(base["in"]), fmtr(base["out"]),
                                                                   base["symbols_positive"], base["symbols"]))
    ok = [r for r in rows if r["in"].get("n", 0) >= 100]
    ok.sort(key=lambda r: r["in"]["avgR"], reverse=True)
    print("\nTOP 12 in-sample (n>=100), with their out-of-sample:")
    for r in ok[:12]:
        print("- %s\n  in  %s\n  out %s  sym+ %d/%d" % (r["variant"], fmtr(r["in"]), fmtr(r["out"]),
                                                       r["symbols_positive"], r["symbols"]))
    both = [r for r in ok if r["in"]["avgR"] > 0 and r["out"].get("n", 0) >= 50 and r["out"]["avgR"] > 0]
    print("\npositive in AND out of sample: %d of %d variants with n>=100" % (len(both), len(ok)))
    for f in ("none", "vol", "vwap", "gap", "spy"):
        sub = [r["all"]["avgR"] for r in rows if r["v"]["filter"] == f and r["all"].get("n")]
        print("filter %-5s median avgR over its variants: %+.3f" % (f, statistics.median(sub)))
    for key, vals in (("target", (1.0, 1.5, 2.0, None)), ("stop", ("mid", "low")), ("cutoff", (930, 660)), ("or", (15, 30))):
        for val in vals:
            sub = [r["all"]["avgR"] for r in rows if r["v"][key] == val and r["all"].get("n")]
            print("%-6s %-5s median avgR: %+.3f" % (key, val, statistics.median(sub)))


if __name__ == "__main__":
    main()
