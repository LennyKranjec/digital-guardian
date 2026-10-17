"""A3-Referenzorakel (unabhängig von challenge/content/tools/oracle.py und vom Backend).

Rechnet Vertrag v1.1 (README §3 + §9 G-01/G-02/G-04/G-19) mit eigener Implementierung (Gleitkomma statt
Brüche, Kalendertage via Europe/Prague-Regel ohne tzdata) und vergleicht mit `expected` aus scenario.yaml.

    python -X utf8 docs/verification/tools/oracle_a3.py [<content_dir>]     (Exit 1 bei Abweichung)
"""

import statistics
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import yaml

LEVELS = {"red": 3, "yellow": 2, "grey": 1}


class _L(yaml.SafeLoader):
    pass


_L.yaml_implicit_resolvers = {
    k: [(t, r) for t, r in v if t != "tag:yaml.org,2002:timestamp"]
    for k, v in yaml.SafeLoader.yaml_implicit_resolvers.items()
}


def load(directory: Path, name: str) -> Any:
    return yaml.load((directory / name).read_text(encoding="utf-8"), Loader=_L)  # noqa: S506


def last_sunday(year: int, month: int) -> datetime:
    first_next = datetime(year + (month == 12), month % 12 + 1, 1, tzinfo=UTC)
    d = first_next - timedelta(days=1)
    while d.weekday() != 6:
        d -= timedelta(days=1)
    return d.replace(hour=1)


def prague_offset(utc: datetime) -> timedelta:
    on = last_sunday(utc.year, 3) <= utc < last_sunday(utc.year, 10)
    return timedelta(hours=2 if on else 1)


def local_to_utc(naive: datetime) -> datetime:
    """Prager Ortszeit (naiv) → UTC; Nicht-existierende/doppelte Zeiten kommen im Szenario nicht vor."""
    for hours in (1, 2):
        cand = naive.replace(tzinfo=UTC) - timedelta(hours=hours)
        if prague_offset(cand) == timedelta(hours=hours):
            return cand
    raise ValueError(naive)


def at(anchor_local: datetime, day_offset: int, hour: int | None) -> datetime:
    day = anchor_local.replace(hour=0, minute=0) + timedelta(days=day_offset)
    return local_to_utc(day.replace(hour=9 if hour is None else hour))


def median(values: list[float]) -> float:
    return float(statistics.median(values))  # gerade Anzahl: Mittel der zwei mittleren Werte


def evaluate(rules: dict, scenario: dict, patient: dict) -> tuple[list[tuple], str]:
    anchor_aware = datetime.fromisoformat(scenario["anchor"])
    anchor_local = (anchor_aware.astimezone(UTC) + prague_offset(anchor_aware.astimezone(UTC))).replace(
        tzinfo=None
    )
    anchor_utc = anchor_aware.astimezone(UTC)
    rs = sorted(patient["responses"], key=lambda r: (r["day_offset"], r.get("hour", 9)))
    series: dict[tuple[str, str], list[tuple[datetime, float]]] = {}
    for r in rs:
        t = at(anchor_local, r["day_offset"], r.get("hour"))
        for k, v in r["answers"].items():
            if v is not None:
                s, a = k.split(".", 1)
                series.setdefault((s, a), []).append((t, float(v)))
    open_max: dict[tuple[str, str, str], float] = {}
    out: list[tuple] = []
    for r in rs:
        t = at(anchor_local, r["day_offset"], r.get("hour"))
        for k in sorted(r["answers"]):
            v = r["answers"][k]
            if v is None:
                continue
            s, a = k.split(".", 1)
            for rule in rules["rules"]:
                if not rule["enabled"] or rule["kind"] == "missing":
                    continue
                if rule.get("symptom_keys") and s not in rule["symptom_keys"]:
                    continue
                if rule.get("attributes") and a not in rule["attributes"]:
                    continue
                p, hist, fired = rule["params"], series[(s, a)], False
                if rule["kind"] == "threshold":
                    fired = v >= p["min_value"]
                elif rule["kind"] == "baseline_delta":
                    lo = t - timedelta(days=p["baseline_days"])
                    base = [x for (tt, x) in hist if lo <= tt < t]
                    fired = len(base) >= 2 and v - median(base) >= p["min_delta"] and v >= p["min_value"]
                elif rule["kind"] == "trend":
                    lo = t - timedelta(days=p["window_days"])
                    pts = [(tt, x) for (tt, x) in hist if lo <= tt <= t]
                    if len(pts) >= p["min_points"]:
                        sl = [
                            (pts[j][1] - pts[i][1]) / ((pts[j][0] - pts[i][0]).total_seconds() / 86400)
                            for i in range(len(pts))
                            for j in range(i + 1, len(pts))
                            if pts[j][0] != pts[i][0]
                        ]
                        if sl:
                            slope = median(sl)
                            fired = (
                                slope >= p["min_slope_per_day"] - 1e-9
                                and v + slope * p["horizon_days"] >= p["target_value"] - 1e-9
                                and v < p["target_value"]
                            )
                if fired:
                    triple = (rule["id"], s, a)
                    if triple not in open_max or v > open_max[triple]:
                        open_max[triple] = v
                        out.append((r["day_offset"], r.get("hour", 9), rule["id"], s, a, rule["level"]))
    levels = [x[5] for x in out]
    miss = next((x for x in rules["rules"] if x["kind"] == "missing" and x["enabled"]), None)
    if miss:
        cyc = at(anchor_local, patient["cycle_start_offset"], 0)
        have = [
            at(anchor_local, r["day_offset"], r.get("hour"))
            for r in rs
            if any(v is not None for v in r["answers"].values())
        ]
        ref = max([cyc, *have])
        gap_days = (anchor_utc + prague_offset(anchor_utc)).date() - (ref + prague_offset(ref)).date()
        if gap_days.days > miss["params"]["max_days_without_response"]:
            levels.append(miss["level"])
    light = max(levels, key=LEVELS.get) if levels else "green"  # type: ignore[arg-type]
    return sorted(out), light


def main() -> int:
    directory = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("challenge/content")
    rules, scenario = load(directory, "rules.yaml"), load(directory, "scenario.yaml")
    bad = 0
    for patient in scenario["patients"]:
        alerts, light = evaluate(rules, scenario, patient)
        exp = patient["expected"]
        exp_alerts = sorted(
            (e["day_offset"], e.get("hour", 9), e["rule_id"], e["symptom_key"], e["attribute"], e["level"])
            for e in exp["alerts"]
        )
        ok = alerts == exp_alerts and light == exp["traffic_light_at_anchor"]
        bad += not ok
        print(f"{patient['pseudonym']}: Ampel {light} (erwartet {exp['traffic_light_at_anchor']}), "
              f"{len(alerts)} Meldungen (erwartet {len(exp_alerts)}) -> {'OK' if ok else 'ABWEICHUNG'}")
        if not ok:
            print("   A3 :", alerts)
            print("   exp:", exp_alerts)
    print(f"Abweichungen: {bad}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
