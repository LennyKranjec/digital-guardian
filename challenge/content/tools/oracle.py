"""Unabhängige Orakelberechnung für challenge/content/scenario.yaml (T-01, Owner A1).

Rechnet die Regelsemantik aus challenge/contract/README.md §3 aus rules.yaml + scenario.yaml nach, OHNE Backend-Code
(reine Standardbibliothek + PyYAML, exakte Bruchrechnung mit fractions.Fraction – keine Gleitkomma-Schwellenfehler).

Aufruf:  python challenge/content/tools/oracle.py   → Tabelle je Patient:in; Exitcode 1, wenn `expected` in scenario.yaml abweicht.
         (scenario.yaml entsteht mit tools/build_scenario.py, das expected aus diesem Orakel schreibt.)

Vertrag v1.1 legt Statistik (G-01), Tagesgrenzen/Zeitzone (G-04), Dedupe-Ausnahme (G-02) und R-MIS-01-Referenz (G-19) fest. Zur Sicherheit
werden die früher offenen Auslegungen WEITER als Varianten gerechnet: jede Variante wird
gerechnet; weichen Varianten voneinander ab, bricht das Orakel mit Fehler ab (das Szenario muss robust gegen die Auslegung
sein). Varianten: Fensteruntergrenze inklusiv/exklusiv; „Tage seit letzter Antwort“ als Bruchteil bzw. als Kalendertage;
Schwellenvergleich von Steigung und Prognose mit ±0,02 Abstand (keine Entscheidung auf der Gleitkomma-Kante).
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from datetime import datetime, timedelta
from fractions import Fraction
from pathlib import Path
from typing import Any

import yaml

CONTENT = Path(__file__).resolve().parent.parent
DAY = timedelta(days=1)
DEFAULT_HOUR = 9  # Vertrag v1.1: hour fehlt ⇒ 9 Uhr Prager Ortszeit
LEVEL_ORDER = {"red": 3, "yellow": 2, "grey": 1}


def _frac(x: Any) -> Fraction:
    return Fraction(str(x))


def _median(values: list[Fraction]) -> Fraction:
    s = sorted(values)
    n = len(s)
    mid = n // 2
    return s[mid] if n % 2 else (s[mid - 1] + s[mid]) / 2


def _days(delta: timedelta) -> Fraction:
    return Fraction(int(delta.total_seconds()), 86400)


@dataclass(frozen=True)
class Variant:
    lower_inclusive: bool
    calendar_days: bool
    trend_eps: Fraction  # Sicherheitsabstand für Divisionsergebnisse (Steigung, Prognose); schützt vor Gleitkomma-Kanten


VARIANTS = [
    Variant(li, cd, eps)
    for li in (True, False)
    for cd in (True, False)
    for eps in (Fraction(-1, 50), Fraction(1, 50))
]


def load() -> tuple[dict, dict]:
    rules = yaml.safe_load((CONTENT / "rules.yaml").read_text(encoding="utf-8"))
    scenario = yaml.safe_load((CONTENT / "scenario.yaml").read_text(encoding="utf-8"))
    return rules, scenario


def _anchor(scenario: dict) -> datetime:
    a = scenario["anchor"]
    return a if isinstance(a, datetime) else datetime.fromisoformat(str(a))


def _when(anchor: datetime, day_offset: int, hour: int | None) -> datetime:
    base = anchor.replace(hour=0, minute=0, second=0, microsecond=0)
    return base + timedelta(days=day_offset, hours=DEFAULT_HOUR if hour is None else hour)


def _applies(rule: dict, symptom: str, attribute: str) -> bool:
    keys = rule.get("symptom_keys") or []
    attrs = rule.get("attributes") or []
    return (not keys or symptom in keys) and (not attrs or attribute in attrs)


def evaluate(rules: dict, scenario: dict, patient: dict, v: Variant) -> dict:
    """Liefert {'alerts': [(day_offset, hour, rule_id, symptom_key, attribute, level)], 'traffic_light': str, ...}."""
    anchor = _anchor(scenario)
    responses = sorted(
        patient["responses"], key=lambda r: (r["day_offset"], r.get("hour", DEFAULT_HOUR))
    )
    series: dict[tuple[str, str], list[tuple[datetime, Fraction]]] = {}
    for r in responses:  # Zeitreihe je (Symptom, Attribut); null zählt nie als Wert
        t = _when(anchor, r["day_offset"], r.get("hour"))
        for key, val in r["answers"].items():
            if val is None:
                continue
            sym, attr = key.split(".", 1)
            series.setdefault((sym, attr), []).append((t, Fraction(val)))
    active = [r for r in rules["rules"] if r["enabled"]]
    level_of = {r["id"]: r["level"] for r in rules["rules"]}
    open_value: dict[
        tuple[str, str, str], Fraction
    ] = {}  # höchster Wert der offenen Meldungen je Tripel
    alerts: list[tuple[int, int, str, str, str, str]] = []
    for (
        r
    ) in responses:  # chronologisch; im Seed wird nichts quittiert ⇒ offene Meldungen bleiben offen
        t = _when(anchor, r["day_offset"], r.get("hour"))
        hour = r.get("hour", DEFAULT_HOUR)
        for key in sorted(r["answers"]):
            val = r["answers"][key]
            if val is None:
                continue
            sym, attr = key.split(".", 1)
            val_f = Fraction(val)
            hist = series[(sym, attr)]
            for rule in active:
                if rule["kind"] == "missing" or not _applies(rule, sym, attr):
                    continue
                p = rule["params"]
                fired = False
                if rule["kind"] == "threshold":
                    fired = val_f >= _frac(p["min_value"])
                elif rule["kind"] == "baseline_delta":
                    lo = t - int(p["baseline_days"]) * DAY
                    base = [
                        x
                        for (tt, x) in hist
                        if (tt >= lo if v.lower_inclusive else tt > lo) and tt < t
                    ]
                    if len(base) >= 2:
                        fired = val_f - _median(base) >= _frac(p["min_delta"]) and val_f >= _frac(
                            p["min_value"]
                        )
                elif rule["kind"] == "trend":
                    lo = t - int(p["window_days"]) * DAY
                    pts = [
                        (tt, x)
                        for (tt, x) in hist
                        if (tt >= lo if v.lower_inclusive else tt > lo) and tt <= t
                    ]
                    if len(pts) >= int(p["min_points"]):
                        slopes = [
                            (pts[j][1] - pts[i][1]) / _days(pts[j][0] - pts[i][0])
                            for i in range(len(pts))
                            for j in range(i + 1, len(pts))
                            if pts[j][0] > pts[i][0]  # Paare mit Δt = 0 verworfen (G-01)
                        ]
                        if slopes:
                            slope = _median(slopes)
                            projected = val_f + slope * _frac(p["horizon_days"])
                            fired = (
                                slope >= _frac(p["min_slope_per_day"]) + v.trend_eps
                                and projected >= _frac(p["target_value"]) + v.trend_eps
                                and val_f < _frac(p["target_value"])
                            )
                if fired:
                    triple = (rule["id"], sym, attr)
                    # Rauschbremse: höchstens eine offene Meldung je Tripel, AUSSER der Wert ist höher als der der
                    # offenen Meldung (G-02: Safety vor Rauschbremse)
                    if triple not in open_value or val_f > open_value[triple]:
                        open_value[triple] = val_f
                        alerts.append(
                            (r["day_offset"], hour, rule["id"], sym, attr, level_of[rule["id"]])
                        )
    # R-MIS-01 (missing): nur Ampel, nie in alerts. Referenz = max(letzte Antwort mit >= 1 Wert, Zyklusstart) (G-19)
    missing_rule = next((x for x in active if x["kind"] == "missing"), None)
    missing = False
    if missing_rule:
        cycle_start = _when(anchor, patient["cycle_start_offset"], 0)
        with_value = [
            _when(anchor, r["day_offset"], r.get("hour"))
            for r in responses
            if any(x is not None for x in r["answers"].values())
        ]
        ref = max([cycle_start, *with_value])
        limit = _frac(missing_rule["params"]["max_days_without_response"])
        if v.calendar_days:
            gap = Fraction(
                (anchor.date() - ref.date()).days
            )  # ganze Tage = Differenz der Kalendertage (G-04)
        else:
            gap = _days(anchor - ref)
        missing = gap > limit
    levels = [a[5] for a in alerts]
    if missing and missing_rule:
        levels.append(missing_rule["level"])
    light = max(levels, key=lambda lv: LEVEL_ORDER[lv]) if levels else "green"
    return {"alerts": sorted(alerts), "traffic_light": light, "missing": missing}


def oracle(rules: dict, scenario: dict, patient: dict) -> dict:
    """Rechnet alle Auslegungsvarianten; Abweichung ⇒ AssertionError (Szenario nicht robust)."""
    results = [evaluate(rules, scenario, patient, v) for v in VARIANTS]
    first = results[0]
    for v, res in zip(VARIANTS, results):
        assert res == first, (
            f"{patient['pseudonym']}: Auslegungsvariante {v} weicht ab: {res} != {first}"
        )
    return first


def expected_block(res: dict) -> dict:
    return {
        "alerts": [
            {
                "day_offset": d,
                "hour": h,
                "rule_id": r,
                "symptom_key": s,
                "attribute": a,
                "level": lv,
            }
            for (d, h, r, s, a, lv) in res["alerts"]
        ],
        "traffic_light_at_anchor": res["traffic_light"],
    }


def main(argv: list[str]) -> int:
    rules, scenario = load()
    ok = True
    blocks: dict[str, dict] = {}
    for p in scenario["patients"]:
        res = oracle(rules, scenario, p)
        blocks[p["pseudonym"]] = expected_block(res)
        print(
            f"{p['pseudonym']}  Ampel={res['traffic_light']:6s} fehlend(R-MIS-01)={res['missing']}"
        )
        for d, h, rule_id, sym, attr, lv in res["alerts"]:
            print(f"    Tag {d:+d} {h:02d}h  {rule_id}  {sym}.{attr}  [{lv}]")
        if p.get("expected") is not None and p["expected"] != blocks[p["pseudonym"]]:
            ok = False
            print("    !! expected in scenario.yaml weicht vom Orakel ab")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
