#!/usr/bin/env python3
"""Productivity calculator for PHANTOMSHIFT (stdlib only).

    time_value = cases_per_day * max(0, minutes_before - minutes_after) / 60 * workdays * hourly_cost
    net        = time_value - monthly_price
    annualised = 12 * net

ILLUSTRATIVE, NOT MEASURED. Every default below is an assumption chosen for arithmetic, not an observation
from any customer, pilot or benchmark. Real savings must be measured from observed investigation durations
(before/after, same case mix, same analysts). The $24,800 invoice in the demo is synthetic exposure and is
never "saved" money. No ARR, customers, prevented breaches or TAM figure exists.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from dataclasses import asdict, dataclass

LABEL = "ILLUSTRATIVE, NOT MEASURED"


@dataclass(frozen=True)
class Assumptions:
    cases_per_day: float = 30.0
    minutes_before: float = 18.0
    minutes_after: float = 7.0
    workdays_per_month: float = 20.0
    hourly_cost: float = 85.0       # fully loaded USD per analyst hour
    monthly_price: float = 2500.0   # USD per month

    def validate(self) -> "Assumptions":
        for name, value in asdict(self).items():
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
                raise ValueError(f"{name} must be a finite number >= 0, got {value!r}")
        return self


def minutes_saved(a: Assumptions) -> float:
    return max(0.0, a.minutes_before - a.minutes_after)


def time_value(a: Assumptions) -> float:
    a.validate()
    return a.cases_per_day * minutes_saved(a) / 60 * a.workdays_per_month * a.hourly_cost


def net_monthly(a: Assumptions) -> float:
    return time_value(a) - a.monthly_price


def annualised(a: Assumptions) -> float:
    return 12 * net_monthly(a)


def breakeven_minutes_saved(a: Assumptions) -> float | None:
    """Minutes saved per case at which net == 0 (None when volume, workdays or cost is zero)."""
    a.validate()
    per_minute = a.cases_per_day * a.workdays_per_month * a.hourly_cost / 60
    return None if per_minute == 0 else a.monthly_price / per_minute


def summary(a: Assumptions) -> dict:
    return {"label": LABEL, "assumptions": asdict(a), "minutes_saved_per_case": minutes_saved(a),
            "time_value_per_month": round(time_value(a), 2), "net_per_month": round(net_monthly(a), 2),
            "annualised_net": round(annualised(a), 2),
            "breakeven_minutes_saved_per_case": None if breakeven_minutes_saved(a) is None
            else round(breakeven_minutes_saved(a), 2)}


def sensitivity(a: Assumptions, saved: list[float], volumes: list[float]) -> list[list[float]]:
    """Monthly NET for each (minutes saved per case) x (cases per day); other assumptions unchanged."""
    rows = []
    for m in saved:
        rows.append([net_monthly(Assumptions(**{**asdict(a), "cases_per_day": v, "minutes_before": m, "minutes_after": 0.0}))
                     for v in volumes])
    return rows


def format_table(a: Assumptions, saved: list[float], volumes: list[float]) -> str:
    rows = sensitivity(a, saved, volumes)
    head = "| minutes saved per case \\ cases per day | " + " | ".join(f"{v:g}" for v in volumes) + " |"
    sep = "|---|" + "---:|" * len(volumes)
    body = ["| " + f"{m:g}" + " | " + " | ".join(f"${x:,.0f}" if x >= 0 else f"-${-x:,.0f}" for x in r) + " |"
            for m, r in zip(saved, rows)]
    return "\n".join([head, sep, *body])


DEFAULT_SAVED = [2.0, 5.0, 8.0, 11.0, 15.0]
DEFAULT_VOLUMES = [10.0, 20.0, 30.0, 50.0, 100.0]


def _floats(text: str) -> list[float]:
    return [float(x) for x in text.split(",") if x.strip()]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=f"Productivity calculator ({LABEL}).")
    d = Assumptions()
    ap.add_argument("--cases-per-day", type=float, default=d.cases_per_day)
    ap.add_argument("--minutes-before", type=float, default=d.minutes_before)
    ap.add_argument("--minutes-after", type=float, default=d.minutes_after)
    ap.add_argument("--workdays", type=float, default=d.workdays_per_month)
    ap.add_argument("--hourly-cost", type=float, default=d.hourly_cost)
    ap.add_argument("--monthly-price", type=float, default=d.monthly_price)
    ap.add_argument("--sensitivity", action="store_true", help="also print the minutes-saved x volume table")
    ap.add_argument("--saved", default=",".join(f"{x:g}" for x in DEFAULT_SAVED))
    ap.add_argument("--volumes", default=",".join(f"{x:g}" for x in DEFAULT_VOLUMES))
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    try:
        asm = Assumptions(a.cases_per_day, a.minutes_before, a.minutes_after, a.workdays, a.hourly_cost,
                          a.monthly_price).validate()
        s = summary(asm)
        table = format_table(asm, _floats(a.saved), _floats(a.volumes)) if a.sensitivity else None
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    if a.json:
        print(json.dumps({**s, "sensitivity_table_markdown": table}, indent=2))
        return 0
    print(f"*** {LABEL}: assumptions, not observations. Measure real investigation durations. ***")
    for k, v in s["assumptions"].items():
        print(f"  {k:<20} {v:g}")
    print(f"  minutes saved/case   {s['minutes_saved_per_case']:g}")
    print(f"  time value / month   ${s['time_value_per_month']:,.2f}")
    print(f"  net / month          ${s['net_per_month']:,.2f}")
    print(f"  annualised net       ${s['annualised_net']:,.2f}")
    be = s["breakeven_minutes_saved_per_case"]
    print(f"  break-even minutes saved per case: {'n/a' if be is None else f'{be:.2f}'}")
    if table:
        print("\nMonthly NET (USD), ILLUSTRATIVE:\n" + table)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
