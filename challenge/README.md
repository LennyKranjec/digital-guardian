# Digitální hlídač nežádoucích účinků – Digital adverse-effect watch

Rakathon 2026, challenge 3 (FN Motol, oncology): _"Pravidelný dotazník pro pacienta, rady k zvládání symptomů a upozornění
týmu při varovných hodnotách."_ – and, in the clinic's words, _"Chceme být ihned informováni o závažných nežádoucích
účincích, nikoli o každé drobnosti."_

> **Research prototype, synthetic data only.** No diagnosis, no therapy decision, no autonomous action. All clinical
> content (thresholds, safety floors, tips, triage rules) is `status: placeholder` until a clinician approves it. A language
> model never sets a colour, level, grade or alert.

Everything in this folder was written **during** the event (16.10.2026 12:00 – 17.10.2026). The neutral platform
(`platform/`, tag `pre-rakathon`) existed before; it was only touched by 6 marked bug fixes (`platform-fix:`), see
[`provenance/PROVENANCE.md`](../provenance/PROVENANCE.md) and [`provenance/TABLE.md`](../provenance/TABLE.md).

## What it does

| Clinic slide             | What the prototype does                                                                                                                                                                                                                                                                                                                         |
| ------------------------ | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Dotazník**             | Patient check-in in Czech/English (PRO-CTCAE-like structure, own wording), tailored to the current therapy and due on a schedule. An **adaptive session** asks one question per card and stops as soon as the result is certain: about **5–6 instead of 14–17 questions** in synthetic sessions. A full questionnaire also adapts to the diagnosis group (ICD-10). |
| **Rady pacientovi**      | Deterministic tip rules per symptom (`ADV-<SYM>-NN`); on acute values tips are suppressed and the patient sees the clinic instruction first: _kontaktujte ambulanci nebo volejte 155_.                                                                                                                                                         |
| **Upozornění týmu**      | Rule engine (severity, urgency, change from baseline, Theil-Sen trend, missing reports) plus a compiled **triage decision tree** per therapy profile. A **noise brake** keeps repeats quiet; a worsening always breaks through; safety floors (e.g. fever ⇒ red) cannot be configured away. Only red notifies immediately.                         |
| **Physician side**       | Work list sorted by urgency, patient cockpit with full history (metrics, alerts, explanation with evidence, counterfactuals), acknowledgement, CTCAE v6 grading by the physician only for the tracked symptoms, drug search by name, kód SÚKL or ATC, short **LLM summary draft** in which every sentence must cite evidence (otherwise a fixed template is used). |
| **Hospital integration** | HL7 **FHIR R4** export per patient (collection and transaction bundle in the clinic format, Condition with ICD-10), push to a configured FHIR server (administration only).                                                                                                                                                                  |
| **Knowledge base**       | C61/C64 (prostate, kidney): 30 substances, 533 adverse-effect rows from the Czech SmPC section 4.8, each with document, section, verbatim term and retrieval date; 350 rows mapped to CTCAE v6 and exported as FHIR `MedicinalProductUndesirableEffect` + `Provenance` (706 resources).                                                     |

## Run the demo

```powershell
scripts/setup.ps1                                                     # once
powershell -ExecutionPolicy Bypass -File challenge/demo/start.ps1 -Reset
```

Linux/macOS: `bash scripts/setup.sh`, then `bash challenge/demo/start.sh --reset`. Open `http://127.0.0.1:5173`; password
for all accounts `demo-passwort-2026` (`patient2` = synthetic patient SYN-0002, `doctor`, `admin`). Start the backend at
least one minute before presenting (the triage trees are compiled and verified at start-up). Click path and expected state:
[`demo/README.md`](demo/README.md), [`pitch/DEMO_RUNBOOK.md`](pitch/DEMO_RUNBOOK.md).

Tests: `scripts/test.ps1` / `scripts/test.sh` (ruff, mypy, pytest, eslint, prettier, tsc, vitest, build, Playwright).

## Measured results (claim level: synthetic / rule-derived)

| Claim                                                                                      | Evidence                                                    |
| ------------------------------------------------------------------------------------------ | ----------------------------------------------------------- |
| Compiled decision tree equals the rulebook at every grid point (up to 2 048 000 per profile) | `docs/verification/T-15.md`, `T-20b.md` (independent reference) |
| 0 under-triage, 0 over-triage in 20 000 synthetic sessions over 8 profiles                 | `docs/verification/T-15.md`, `CLAIMS-CHECK.md`              |
| ≈ 5–6 questions per adaptive session instead of 14–17 (first four profiles)                | `docs/verification/T-14.md`, `T-15.md`                      |
| FHIR bundles of all 7 synthetic patients and the knowledge bundle: 0 HAPI validator errors | `docs/verification/T-08.md`, `T-20b.md`, `CLAIMS-CHECK.md`   |
| Final integration: pytest 2 042, vitest 750, Playwright 174 green                          | `docs/verification/INT-4b.md`                               |

This shows **faithful implementation of placeholder rules**, not clinical validity.

## Architecture

Full German description of state, architecture, safety strategy and roadmap: [`ARCHITECTURE.md`](ARCHITECTURE.md);
project course and decisions: [`docs/PROJECT_STATE.md`](../docs/PROJECT_STATE.md).

Plug-in on the neutral platform: FastAPI backend (`backend/plugin.py`, package `waechter`, SQLite + Alembic migrations
`w001–w007`, prefix `/api/v1/waechter`, server-side authorisation) and React/Vite frontend (`frontend/plugin.tsx`).
Content as versioned YAML (`content/`), validated against `contract/content.schema.json`; API contract in
`contract/openapi.yaml`, triage contract in `contract/triage.md`. Business logic lives in `backend/waechter/services` and
`backend/waechter/triage` (safe expression parser, own exact entropy tree, verification V1/V3/V4, counterfactuals), never in
routes or UI components. LLM adapters (`template` | `cached` | `openai`) sit behind a deterministic verifier.

## Honest limits

- No clinical data access: synthetic patients only; the shared dataset was used for aggregate counts only (k ≥ 5).
- No live LLM answered (gateway returned 404 for every model name); the summary runs on the template fallback.
- The deterministic checker is deliberately strict: on real SmPC table layouts it would confirm only 93 of 351 rows; the
  matrix was second-read by a separate AI test agent (533/533 terms, 331/533 frequency classes), not by a clinician.
- Czech/German texts are not reviewed by native speakers; question wording is not the official PRO-CTCAE text.
- FHIR push was tested against a local test server only; no IRIS instance was connected.
- Open clinical questions: [`knowledge/CLINICAL_TODO.md`](knowledge/CLINICAL_TODO.md), assumptions in `provenance/PROVENANCE.md`.

## Who built it

AI agents (lead, builders, independent tester, pitch) under human direction; roles in [`agents/`](../agents/), decisions in
[`docs/PROJECT_STATE.md`](../docs/PROJECT_STATE.md), test reports in [`docs/verification/`](../docs/verification/).
