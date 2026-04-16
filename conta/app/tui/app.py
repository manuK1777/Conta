from pathlib import Path
from textual.app import App, ComposeResult
from textual.widgets import Footer, Header, TabbedContent, TabPane

from .screens.dashboard import DashboardTab
from .screens.facturas import FacturasTab
from .screens.gastos import GastosTab
from .screens.emite import EmiteTab
from .screens.gasto_form import GastoFormTab
from .screens.m130 import M130Tab

CSS_PATH = Path(__file__).parent / "conta.tcss"


class ContaApp(App):
    """Interfaz TUI para Conta."""

    CSS_PATH = CSS_PATH
    TITLE = "Conta"
    SUB_TITLE = "Contabilidad autónomo"

    BINDINGS = [
        ("f1", "switch_tab('dashboard')", "Dashboard"),
        ("f2", "switch_tab('facturas')", "Facturas"),
        ("f3", "switch_tab('gastos')", "Gastos"),
        ("f4", "switch_tab('emite')", "Emite"),
        ("f5", "switch_tab('gasto')", "Gasto"),
        ("f6", "switch_tab('m130')", "M130"),
        ("q", "quit", "Salir"),
    ]

    def compose(self) -> ComposeResult:
        yield Header()
        with TabbedContent(initial="dashboard"):
            with TabPane("F1 Dashboard", id="dashboard"):
                yield DashboardTab()
            with TabPane("F2 Facturas", id="facturas"):
                yield FacturasTab()
            with TabPane("F3 Gastos", id="gastos"):
                yield GastosTab()
            with TabPane("F4 Emite", id="emite"):
                yield EmiteTab()
            with TabPane("F5 Gasto", id="gasto"):
                yield GastoFormTab()
            with TabPane("F6 M130", id="m130"):
                yield M130Tab()
        yield Footer()

    def action_switch_tab(self, tab_id: str) -> None:
        self.query_one(TabbedContent).active = tab_id


def run() -> None:
    ContaApp().run()
