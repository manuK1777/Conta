# Architecture

**Conta** is a layered CLI/TUI accounting app — no web server, no client-server split. Everything runs as a single Python process against a local SQLite file.

```
conta/app/
├── cli.py                  Typer commands (presentation layer #1)
├── tui/
│   ├── app.py               Textual App, wires up TabbedContent (F1–F6)
│   └── screens/             one widget module per tab (presentation layer #2)
│       dashboard.py, facturas.py, gastos.py, emite.py, gasto_form.py, m130.py
├── models.py                SQLModel tables (the schema)
├── schemas.py                Pydantic DTOs for validating input (FacturaIn, GastoIn, ...)
├── db.py                    engine + get_session()
└── services/                 pure business logic (fiscal calculations)
    ├── iva.py                quarterly IVA (devengado/deducible)
    ├── irpf.py                Modelo 130 cumulative snapshot
    ├── libros.py              CSV export of IVA books
    ├── exportar.py            annual PDF report (WeasyPrint)
    ├── facturas.py, factura_pdf.py, emisor.py
    └── importacion_pdf/       PDF invoice scraper pipeline
```

## The core rule: two thin front-ends, one shared core

`cli.py` and `tui/screens/*.py` are **both** presentation layers over the same logic — they don't talk to each other, and business logic never lives in either of them:

```
cli.py  ─┐
         ├──►  services/*.py  ──►  db.py (get_session())  ──►  models.py (SQLModel tables) ──► SQLite
tui/*.py ─┘         ▲
                     │
                 schemas.py (Pydantic validation before a table row is built)
```

- **`models.py`** — the actual schema: `FacturaEmitida` (issued invoices), `GastoDeducible` (deductible expenses), `PagoAutonomo` (social security), `PagoFraccionado130` (filed Modelo 130), `Presentacion303` (filed Modelo 303).
- **`schemas.py`** — Pydantic DTOs that validate raw CLI/TUI input before it's turned into a model row.
- **`services/`** — pure functions, each opening its own DB session via `get_session()`. This is where all fiscal math lives (IVA, IRPF, PDF export, PDF import). If a calculation is wrong, the fix belongs here — never in a screen or a CLI command.
- **`db.py`** — the only place that knows about the SQLAlchemy/SQLModel engine.

## Why this split matters in practice

- Both `cli.py` and the TUI screens call the *same* `services/` functions, so a bug fix or rule change made in `services/` automatically applies to both interfaces — there's no logic duplicated between CLI and TUI.
- `services/` functions are self-contained (each opens its own session), so they can be called independently of any UI — e.g. from a script or future API layer.
- The TUI (`tui/app.py`) has one specific coupling worth knowing: switching to the Facturas tab (F2) force-reloads its data, because screens don't share live state — each tab's data can go stale while another tab is being edited.

## Two business domains, one schema

The whole app models one freelancer with two activities — `musica` (domestic, IVA + IRPF retention) and `programacion` (foreign client, no IVA/no retention, export of services). This isn't a separate module per activity; it's a field (`Actividad`) threaded through `models.py` and branched on inside `services/iva.py` and `services/irpf.py` (e.g. `programacion` invoices have 0% IVA cuota so they're excluded from IVA devengado but still count toward IRPF income).

## Notably absent

- No API layer — `make api` references `api.py`, which doesn't exist yet.
- No test suite — `tests/` is empty; `make test` silently swallows failures (`pytest -q || true`).
- `config/rules.yml` exists for fiscal constants but several rates are actually hardcoded in `services/` rather than read from it — worth checking before assuming a YAML edit takes effect.
