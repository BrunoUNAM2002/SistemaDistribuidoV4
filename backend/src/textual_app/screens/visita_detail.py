"""
Visit Detail Modal - Shows detailed information about a visit
"""

from datetime import datetime
from typing import Dict, Any

from textual.app import ComposeResult
from textual.screen import ModalScreen
from textual.widgets import Static, Button, Label
from textual.containers import Container, Vertical, Horizontal, Grid
from textual.binding import Binding
from rich.text import Text
from rich.panel import Panel


class VisitDetailModal(ModalScreen):
    """Modal screen to show detailed visit information"""

    BINDINGS = [
        Binding("escape", "dismiss", "Cerrar", show=True),
    ]

    CSS = """
    VisitDetailModal {
        align: center middle;
    }

    #detail-container {
        width: 80;
        height: auto;
        max-height: 90%;
        background: $surface;
        border: thick $primary;
        padding: 2;
    }

    #detail-title {
        text-style: bold;
        color: $primary;
        text-align: center;
        padding-bottom: 1;
        border-bottom: solid $border;
        margin-bottom: 1;
    }

    .detail-section {
        margin: 1 0;
        padding: 1;
        background: $panel;
        border: solid $border;
    }

    .section-title {
        text-style: bold;
        color: $primary;
        margin-bottom: 1;
    }

    .field-label {
        color: $text-secondary;
        width: 20;
    }

    .field-value {
        color: $text-primary;
        text-style: bold;
    }

    .field-row {
        height: auto;
        margin: 0 0 1 0;
    }

    #button-container {
        align: center middle;
        margin-top: 2;
    }

    #close-btn {
        margin: 0 1;
    }

    #cerrar-visita-btn {
        margin: 0 1;
    }

    .estado-badge {
        padding: 0 2;
        text-align: center;
    }

    .estado-activa {
        background: $success;
        color: $surface;
        text-style: bold;
    }

    .estado-completada {
        background: $text-muted;
        color: $surface;
    }

    .estado-cancelada {
        background: $error;
        color: $surface;
        text-style: bold;
    }
    """

    def __init__(self, visita: Dict[str, Any], flask_app, username: str):
        super().__init__()
        self.visita = visita
        self.flask_app = flask_app
        self.username = username

    def compose(self) -> ComposeResult:
        """Compose the detail modal UI"""
        with Container(id="detail-container"):
            # Title
            yield Label(
                f"📋 DETALLE DE VISITA: {self.visita.get('folio', 'N/A')}",
                id="detail-title"
            )

            # Patient section
            with Vertical(classes="detail-section"):
                yield Label("👤 INFORMACIÓN DEL PACIENTE", classes="section-title")

                with Horizontal(classes="field-row"):
                    yield Label("Nombre:", classes="field-label")
                    yield Label(self.visita.get('paciente', 'N/A'), classes="field-value")

            # Medical staff section
            with Vertical(classes="detail-section"):
                yield Label("👨‍⚕️ PERSONAL MÉDICO", classes="section-title")

                with Horizontal(classes="field-row"):
                    yield Label("Doctor asignado:", classes="field-label")
                    yield Label(self.visita.get('doctor', 'N/A'), classes="field-value")

            # Location section
            with Vertical(classes="detail-section"):
                yield Label("🏥 UBICACIÓN", classes="section-title")

                with Horizontal(classes="field-row"):
                    yield Label("Sala:", classes="field-label")
                    yield Label(str(self.visita.get('sala', 'N/A')), classes="field-value")

                with Horizontal(classes="field-row"):
                    yield Label("Cama:", classes="field-label")
                    yield Label(str(self.visita.get('cama', 'N/A')), classes="field-value")

            # Clinical info section
            with Vertical(classes="detail-section"):
                yield Label("📝 INFORMACIÓN CLÍNICA", classes="section-title")

                # Estado with color badge
                estado = self.visita.get('estado', 'desconocido')
                estado_classes = f"estado-badge estado-{estado}"

                with Horizontal(classes="field-row"):
                    yield Label("Estado:", classes="field-label")
                    yield Label(estado.upper(), classes=estado_classes)

                # Timestamps
                timestamp = self.visita.get('timestamp', '')
                if timestamp:
                    try:
                        dt = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
                        timestamp_formatted = dt.strftime('%d/%m/%Y %H:%M:%S')
                    except:
                        timestamp_formatted = timestamp
                else:
                    timestamp_formatted = 'N/A'

                with Horizontal(classes="field-row"):
                    yield Label("Fecha de ingreso:", classes="field-label")
                    yield Label(timestamp_formatted, classes="field-value")

                # Fecha cierre (if exists)
                fecha_cierre = self.visita.get('fecha_cierre', '')
                if fecha_cierre:
                    try:
                        dt = datetime.fromisoformat(fecha_cierre.replace('Z', '+00:00'))
                        cierre_formatted = dt.strftime('%d/%m/%Y %H:%M:%S')
                    except:
                        cierre_formatted = fecha_cierre

                    with Horizontal(classes="field-row"):
                        yield Label("Fecha de cierre:", classes="field-label")
                        yield Label(cierre_formatted, classes="field-value")

            # Buttons
            with Horizontal(id="button-container"):
                # Show "Cerrar Visita" button only if visit is active
                if self.visita.get('estado') == 'activa':
                    yield Button(
                        "🩺 Cerrar Visita",
                        variant="success",
                        id="cerrar-visita-btn"
                    )

                yield Button("← Volver", variant="primary", id="close-btn")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button presses"""
        if event.button.id == "close-btn":
            self.dismiss()
        elif event.button.id == "cerrar-visita-btn":
            self.action_cerrar_visita()

    def action_cerrar_visita(self) -> None:
        """Close the visit - TODO: Implement full closure workflow"""
        self.notify(
            "🚧 Funcionalidad de cierre en construcción",
            title="Próximamente",
            severity="warning",
            timeout=3
        )
        # TODO: Implement visit closure
        # - Show form to enter diagnostico
        # - Update visit in DB
        # - Replicate to cluster
        # - Refresh parent screen
        # - Close modal

    def action_dismiss(self) -> None:
        """Dismiss the modal"""
        self.dismiss()


# Export
__all__ = ['VisitDetailModal']
