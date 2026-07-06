# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

Conta MVP — personal accounting for a Spanish freelancer (autónomo), covering two
activities: `musica` (music, domestic clients, IVA + IRPF retention applies) and
`programacion` (programming, foreign client JPL Media/Australia, no IVA/no retention —
export of services). CLI (Typer) + interactive TUI (Textual), backed by SQLite via SQLModel.

## Commands

```bash
# Setup
python3 -m venv .venv && source .venv/bin/activate
pip install -e .
cp .env.example .env
conta init                       # creates conta.db and tables

# Run
conta tui                        # interactive Textual TUI (F1-F6 switch tabs, q to quit)
conta --help                     # list all CLI commands
conta <command> --help           # per-command help

# Dev loop (Makefile)
make install                     # pip install -e .
make dev                         # conta init
make api                         # uvicorn conta.app.api:app --reload (note: api.py does not currently exist)
make test                        # pytest -q || true  (tests/ is currently empty — no tests exist yet)
make backup                      # tar czf backup of conta.db + reports/
make fmt                         # ruff check --fix || true
```

There is no test suite yet (`tests/` is empty). If you add tests, run them with `pytest -q`
directly rather than relying on `make test`, since that target swallows failures (`|| true`).

## Configuration

- `.env` (see `.env.example`): `CONTA_DB_PATH` (default `./conta.db`), `CONTA_RULES_PATH`
  (default `./config/rules.yml`).
- `config/rules.yml`: fiscal constants — IVA rates (general/reducido/superreducido),
  IRPF retention % per `Actividad`, Modelo 130 pago fraccionado %, rounding precision.
  Note: several of these values are currently hardcoded in `services/` rather than actually
  read from this file — check before assuming a rule change here takes effect.

## Architecture

**Layering:** `cli.py` (Typer commands) and `tui/screens/*.py` (Textual widgets) are both
thin presentation layers over the same core: `models.py` (SQLModel tables) → `db.py`
(engine/session) → `services/*.py` (fiscal calculations, pure functions that open their own
session via `get_session()`). `schemas.py` holds Pydantic input DTOs (`FacturaIn`, `GastoIn`,
etc.) used to validate CLI input before constructing a table model. The TUI and CLI do not
share business logic beyond these services — if you fix a calculation, fix it in
`services/`, not in a screen or command.

**Core tables** (`models.py`):
- `FacturaEmitida` — issued invoice (income). Has both `estado` (free-text IVA status) and
  `estado_cobro` (collection status, default "Pendiente") — these are separate concepts.
- `GastoDeducible` — deductible expense. `afecto_pct` (business-use %) weights both the
  base and the IVA cuota when computing quarterly deductible amounts. `iva_deducible=False`
  marks expenses where IVA can't be reclaimed (e.g. OSS/non-EU purchases) — in that case the
  IVA becomes part of the deductible expense base for IRPF instead.
  Cuota IVA is normally computed as `base * tipo_iva / 100`, but can be overridden with an
  exact value from the PDF (`--cuota-iva` in `conta gasto`) when rounding on the source
  invoice doesn't match the naive calculation.
- `PagoAutonomo` — self-employment social security quotas, deductible as an expense.
- `PagoFraccionado130` — record of a filed Modelo 130 (IRPF quarterly advance payment).
  Filing quarter Q must exist before computing quarter Q+1, since `irpf_snapshot_acumulado`
  subtracts prior quarters' `resultado` as `pagos_previos`.
- `Presentacion303` — record of a filed Modelo 303 (IVA quarterly return).

**Fiscal calculations** (`services/`):
- `iva.py` (`iva_trimestre`) — quarterly IVA (devengado vs. deducible), only counts invoices
  with non-zero `cuota_iva` as devengado (i.e. `programacion` invoices, which have 0% IVA,
  are excluded from devengado but their base still flows into IRPF income).
- `irpf.py` (`irpf_snapshot_acumulado`) — Modelo 130: **cumulative from Jan 1 to end of
  the requested quarter**, not quarter-isolated (matches how the AEAT form actually works).
  `solo_programacion=True` filters to just the programming activity and zeroes out
  retenciones (used for what-if/analysis, not official filing).
  Q4 additionally regularizes the full year (see note printed by `conta m130`).
- `libros.py` — exports quarterly IVA books (emitidas/recibidas) to CSV via pandas.
- `exportar.py` — builds a full annual PDF report (WeasyPrint, inline HTML template) with
  facturas/gastos/cuotas/M130/M303 tables and a fiscal summary; the M303 section is
  *calculated* from `iva_trimestre` per quarter rather than read from `Presentacion303` rows.
- `importacion_pdf/` — best-effort PDF invoice scraper (`importador_factura.py` orchestrates
  `extractor_pdf` → `campos_factura` → `clasificador_fiscal` → `normalizador_texto`).
  Activity is guessed by checking for the word "software" in the extracted text; IVA/IRPF
  are classified heuristically from text patterns, not asserted from structured fields —
  always spot-check with `conta import-facturas <carpeta> --dry-run` before real import.

**Periods:** Most list/report commands accept either a quarter string `YYYYQ#` (e.g.
`2025Q3`) or `--year YYYY`, but never both in the same call — this validation is duplicated
across several CLI commands rather than factored into a shared helper.

**Money:** All monetary fields are `Decimal`. Quantize to `Decimal("0.01")` with
`ROUND_HALF_UP` at display/storage boundaries, matching the pattern already used throughout
`services/` and `cli.py` — don't introduce float arithmetic for money.

**TUI:** `tui/app.py` wires up `TabbedContent` with one `TabPane` per screen in
`tui/screens/`. Switching to the Facturas tab (F2) auto-reloads its data
(`ContaApp.action_switch_tab`) — follow this pattern if you add a new tab that shows
data which can go stale while another tab is active.
