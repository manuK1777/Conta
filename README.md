# Conta

A CLI + interactive TUI accounting tool for Spanish self-employed professionals (*autónomos*), automating invoice tracking, deductible expenses, and quarterly IVA/IRPF tax obligations.

Built to replace a spreadsheet-based workflow with a typed domain model, **Decimal-precision arithmetic** (to avoid fiscal rounding errors), and a fast terminal-first UX.

## Features

- **Invoicing & expenses** — record issued invoices and deductible expenses, with IVA and IRPF retention calculated per activity type (`programacion` / `musica`).
- **Quarterly tax snapshots** — IVA (Modelo 303) and IRPF (Modelo 130) calculations derived from real recorded data, mirroring the structure of the official Spanish tax forms.
- **Interactive TUI** — a 6-screen terminal interface (dashboard, invoices, expenses, and entry forms) built with [Textual](https://github.com/Textualize/textual), with inline status editing and reactive data reload.
- **CSV exports** — official VAT books (*libros de IVA*) exported per quarter, separately for issued and received invoices.
- **PDF invoice import** — heuristic classification to speed up data entry from scanned invoices.
- **Database backups** — timestamped archive of the SQLite database on demand.

## Tech stack

`Python 3.10+` · `SQLModel` (typed ORM over SQLite) · `Typer` (CLI) · `Textual` (TUI) · `Pydantic` (input validation) · `Rich` (terminal output) · `pandas` (CSV export) · `WeasyPrint` (PDF reports)

## Installation

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -U pip
pip install -e .
cp .env.example .env
conta init
```

`conta init` creates the local SQLite database (`conta.db`) and its tables. Configuration (database path, fiscal rules) lives in `.env` — see `.env.example`.

## Usage

Launch the interactive TUI:

```bash
conta tui
```

| Key | Screen | Description |
|-----|--------|--------------|
| F1 | Dashboard | Quarterly IVA summary + accumulated IRPF |
| F2 | Invoices | Invoice table with filters and inline status editing |
| F3 | Expenses | Deductible expenses table |
| F4 | New invoice | Form to issue a new invoice |
| F5 | New expense | Form to log a new expense |
| F6 | Modelo 130 | Form for a fractioned tax payment |
| q | — | Quit |

On the Invoices screen, press **e** on a row to edit its collection status inline.

Or use the CLI directly — some of the core commands:

```bash
conta emite               # register an issued invoice
conta gasto                # register a deductible expense
conta iva                   # calculate quarterly IVA
conta irpf                   # view accumulated IRPF snapshot
conta import-facturas          # import invoices from PDF
conta export                    # generate a PDF report
conta backup-db                  # create a timestamped database backup
conta --help                      # list all available commands
```

## Data model

Typed SQLModel tables for the core accounting entities: `FacturaEmitida` (issued invoices), `GastoDeducible` (deductible expenses), `PagoAutonomo` (self-employed social security payments), `PagoFraccionado130` (Modelo 130 fractioned payments), and `Presentacion303` (Modelo 303 filings) — each with explicit activity-type enums (`programacion`, `musica`) driving the applicable IVA/IRPF rules.

## Project structure

```
conta/app/
├── cli.py           # Typer CLI commands
├── models.py         # SQLModel tables (domain entities)
├── schemas.py         # Pydantic input DTOs
├── db.py               # database engine/session
├── services/             # fiscal calculations (IVA, IRPF, exports, PDF import)
└── tui/                   # Textual interactive terminal UI
```

---

*Personal project — built to automate my own quarterly tax workflow as a freelance developer in Spain.*
