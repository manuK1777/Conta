# Conta MVP

Contabilidad personal para autónomos. CLI + TUI interactiva.

## Requisitos
- Python 3.10+
- make, tar

## Instalación
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -U pip
pip install -e .
cp .env.example .env
conta init

## TUI interactiva

Lanza la interfaz de terminal completa con:

```bash
conta tui
```

| Tecla | Pantalla | Descripción |
|-------|----------|-------------|
| F1 | Dashboard | Resumen IVA trimestral + IRPF acumulado |
| F2 | Facturas | Tabla de facturas con filtros y edición de estado |
| F3 | Gastos | Tabla de gastos deducibles |
| F4 | Emite | Formulario para nueva factura |
| F5 | Gasto | Formulario para nuevo gasto |
| F6 | M130 | Formulario para pago fraccionado |
| q | — | Salir |

En la pantalla de Facturas, pulsa **e** sobre una fila para editar el estado de cobro inline.