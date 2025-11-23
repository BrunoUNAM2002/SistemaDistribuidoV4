"""
Create Visit Wizard - Multi-step wizard for creating emergency visits
"""

import asyncio
from typing import Dict, Any, List, Tuple, Optional
from datetime import datetime

from textual.app import ComposeResult
from textual.screen import Screen
from textual.widgets import Static, Input, Button, Label, Select
from textual.containers import Container, Vertical, Horizontal
from textual.reactive import reactive
from textual import work
from textual.binding import Binding
from rich.text import Text


class CreateVisitWizard(Screen):
    """
    Multi-step wizard for creating emergency visits

    Steps:
    1. Patient Information
    2. Medical Resources (Doctor, Bed)
    3. Symptoms
    4. Confirmation & Creation
    """

    BINDINGS = [
        Binding("escape", "cancel", "Cancelar", show=True),
    ]

    CSS = """
    CreateVisitWizard {
        background: $surface;
    }

    #wizard-header {
        background: $primary;
        color: $surface;
        padding: 1 2;
        dock: top;
        height: 5;
    }

    #wizard-title {
        text-style: bold;
        color: $surface;
        text-align: center;
    }

    #wizard-steps {
        color: $surface;
        text-align: center;
        margin-top: 1;
    }

    #wizard-content {
        padding: 2;
        height: 1fr;
    }

    #wizard-form {
        background: $panel;
        border: solid $border;
        padding: 2;
        width: 80;
        height: auto;
    }

    .form-section {
        margin: 1 0;
    }

    .form-label {
        color: $text-secondary;
        padding: 1 0 0 0;
    }

    .form-label-required::after {
        content: " *";
        color: $error;
    }

    Input {
        margin: 0 0 1 0;
    }

    Select {
        margin: 0 0 1 0;
    }

    #button-container {
        align: center middle;
        padding: 2 0;
    }

    Button {
        margin: 0 1;
        min-width: 16;
    }

    .step-active {
        color: $success;
        text-style: bold;
    }

    .step-pending {
        color: $text-muted;
    }

    .step-completed {
        color: $success;
    }

    #error-message {
        color: $error;
        text-style: bold;
        text-align: center;
        margin: 1 0;
    }

    #summary-container {
        background: $panel;
        border: solid $primary;
        padding: 2;
    }

    .summary-section {
        margin: 1 0;
        padding: 1;
        background: $surface;
        border: solid $border;
    }

    .summary-label {
        color: $text-secondary;
    }

    .summary-value {
        color: $text-primary;
        text-style: bold;
    }
    """

    # Wizard state
    current_step: reactive[int] = reactive(1, init=False)
    total_steps: int = 4

    # Form data
    form_data: Dict[str, Any] = {}

    def __init__(self, flask_app, bully_manager, username: str):
        super().__init__()
        self.flask_app = flask_app
        self.bully_manager = bully_manager
        self.username = username

        # Available resources
        self.available_doctors: List[Tuple[int, str]] = []
        self.available_beds: List[Tuple[int, str]] = []

        # Initialize form data
        self.form_data = {
            # Step 1: Patient
            'nombre': '',
            'edad': '',
            'sexo': '',
            'curp': '',
            'telefono': '',
            'contacto_emergencia': '',
            # Step 2: Resources
            'id_doctor': None,
            'id_cama': None,
            # Step 3: Symptoms
            'sintomas': '',
        }

    def compose(self) -> ComposeResult:
        """Compose the wizard UI"""
        # Header
        with Container(id="wizard-header"):
            yield Label("🏥 NUEVA VISITA DE EMERGENCIA", id="wizard-title")
            yield Static("", id="wizard-steps")

        # Content area
        with Container(id="wizard-content"):
            with Vertical(id="wizard-form"):
                yield Static("", id="step-container")
                yield Static("", id="error-message")

                with Horizontal(id="button-container"):
                    yield Button("← Atrás", variant="default", id="btn-back")
                    yield Button("Siguiente →", variant="primary", id="btn-next")
                    yield Button("Cancelar", variant="error", id="btn-cancel")

    def on_mount(self) -> None:
        """Initialize wizard"""
        # Load available resources
        self.load_resources()

        # Show first step
        self.update_step_display()

    def load_resources(self) -> None:
        """Load available doctors and beds from database"""
        try:
            with self.flask_app.app_context():
                from models import get_doctores_disponibles, get_camas_disponibles
                from config import Config

                # Get available doctors
                doctores = get_doctores_disponibles(id_sala=self.bully_manager.node_id)
                self.available_doctors = [
                    (d.id_doctor, f"{d.nombre} - {d.especialidad}")
                    for d in doctores
                ]

                # Get available beds
                camas = get_camas_disponibles(id_sala=self.bully_manager.node_id)
                self.available_beds = [
                    (c.id_cama, f"Cama {c.numero} - Sala {c.id_sala}")
                    for c in camas
                ]

        except Exception as e:
            self.notify(f"Error loading resources: {str(e)}", severity="error")

    def watch_current_step(self, step: int) -> None:
        """React to step changes"""
        self.update_step_display()

    def update_step_display(self) -> None:
        """Update UI for current step"""
        # Update step indicator
        steps_text = Text()
        for i in range(1, self.total_steps + 1):
            if i == self.current_step:
                steps_text.append(f"● ", style="bold green")
            elif i < self.current_step:
                steps_text.append(f"✓ ", style="green")
            else:
                steps_text.append(f"○ ", style="dim")

        step_names = ["Paciente", "Recursos", "Síntomas", "Confirmar"]
        steps_text.append(f"{step_names[self.current_step - 1]} ({self.current_step}/{self.total_steps})")

        steps_widget = self.query_one("#wizard-steps", Static)
        steps_widget.update(steps_text)

        # Update step content
        step_container = self.query_one("#step-container", Static)

        if self.current_step == 1:
            step_container.update(self.render_step1_patient())
        elif self.current_step == 2:
            step_container.update(self.render_step2_resources())
        elif self.current_step == 3:
            step_container.update(self.render_step3_symptoms())
        elif self.current_step == 4:
            step_container.update(self.render_step4_confirmation())

        # Update buttons
        self.update_buttons()

        # Clear error message
        error_widget = self.query_one("#error-message", Static)
        error_widget.update("")

    def render_step1_patient(self) -> Text:
        """Render Step 1: Patient Information"""
        content = Text()
        content.append("DATOS DEL PACIENTE\n\n", style="bold cyan")
        content.append("Ingrese la información del paciente:\n\n", style="dim")

        # Note: Actual form inputs will be added in mount
        return content

    def render_step2_resources(self) -> Text:
        """Render Step 2: Medical Resources"""
        content = Text()
        content.append("RECURSOS MÉDICOS\n\n", style="bold cyan")
        content.append("Seleccione doctor y cama disponibles:\n\n", style="dim")

        if not self.available_doctors:
            content.append("⚠ No hay doctores disponibles\n", style="bold red")
        if not self.available_beds:
            content.append("⚠ No hay camas disponibles\n", style="bold red")

        return content

    def render_step3_symptoms(self) -> Text:
        """Render Step 3: Symptoms"""
        content = Text()
        content.append("SÍNTOMAS\n\n", style="bold cyan")
        content.append("Describa los síntomas del paciente:\n\n", style="dim")

        return content

    def render_step4_confirmation(self) -> Text:
        """Render Step 4: Confirmation"""
        content = Text()
        content.append("CONFIRMACIÓN\n\n", style="bold cyan")
        content.append("Revise los datos antes de crear la visita:\n\n", style="dim")

        # Summary
        content.append("Paciente: ", style="dim")
        content.append(f"{self.form_data.get('nombre', 'N/A')}\n", style="bold")

        content.append("Edad: ", style="dim")
        content.append(f"{self.form_data.get('edad', 'N/A')} años\n", style="bold")

        content.append("Sexo: ", style="dim")
        content.append(f"{self.form_data.get('sexo', 'N/A')}\n", style="bold")

        if self.form_data.get('curp'):
            content.append("CURP: ", style="dim")
            content.append(f"{self.form_data['curp']}\n", style="bold")

        content.append("\nSíntomas: ", style="dim")
        content.append(f"{self.form_data.get('sintomas', 'N/A')}\n\n", style="bold")

        return content

    def update_buttons(self) -> None:
        """Update button visibility and labels"""
        btn_back = self.query_one("#btn-back", Button)
        btn_next = self.query_one("#btn-next", Button)

        # Back button
        btn_back.disabled = (self.current_step == 1)

        # Next button
        if self.current_step == self.total_steps:
            btn_next.label = "✓ Crear Visita"
            btn_next.variant = "success"
        else:
            btn_next.label = "Siguiente →"
            btn_next.variant = "primary"

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button clicks"""
        if event.button.id == "btn-back":
            self.action_back()
        elif event.button.id == "btn-next":
            self.action_next()
        elif event.button.id == "btn-cancel":
            self.action_cancel()

    def action_back(self) -> None:
        """Go to previous step"""
        if self.current_step > 1:
            self.current_step -= 1

    def action_next(self) -> None:
        """Go to next step or create visit"""
        # Validate current step
        if not self.validate_current_step():
            return

        # Save current step data
        self.save_current_step_data()

        if self.current_step < self.total_steps:
            # Go to next step
            self.current_step += 1
        else:
            # Create visit
            self.create_visit()

    def validate_current_step(self) -> bool:
        """Validate current step data"""
        error_widget = self.query_one("#error-message", Static)

        if self.current_step == 1:
            # Validate patient data
            try:
                nombre_input = self.query_one("#input-nombre", Input)
                edad_input = self.query_one("#input-edad", Input)
                sexo_select = self.query_one("#select-sexo", Select)

                if not nombre_input.value.strip():
                    error_widget.update("❌ El nombre es requerido")
                    return False

                if not edad_input.value.strip():
                    error_widget.update("❌ La edad es requerida")
                    return False

                try:
                    edad = int(edad_input.value)
                    if edad < 0 or edad > 150:
                        error_widget.update("❌ Edad inválida (0-150)")
                        return False
                except ValueError:
                    error_widget.update("❌ La edad debe ser un número")
                    return False

                if not sexo_select.value:
                    error_widget.update("❌ El sexo es requerido")
                    return False

            except Exception:
                # Inputs not yet rendered
                pass

        elif self.current_step == 2:
            # Validate resources
            if not self.available_doctors:
                error_widget.update("❌ No hay doctores disponibles")
                return False

            if not self.available_beds:
                error_widget.update("❌ No hay camas disponibles")
                return False

            # Check selections
            try:
                doctor_select = self.query_one("#select-doctor", Select)
                bed_select = self.query_one("#select-bed", Select)

                if not doctor_select.value:
                    error_widget.update("❌ Debe seleccionar un doctor")
                    return False

                if not bed_select.value:
                    error_widget.update("❌ Debe seleccionar una cama")
                    return False
            except Exception:
                pass

        elif self.current_step == 3:
            # Validate symptoms
            try:
                sintomas_input = self.query_one("#input-sintomas", Input)

                if not sintomas_input.value.strip():
                    error_widget.update("❌ Los síntomas son requeridos")
                    return False

                if len(sintomas_input.value.strip()) < 10:
                    error_widget.update("❌ Describa los síntomas con más detalle (mín. 10 caracteres)")
                    return False
            except Exception:
                pass

        error_widget.update("")
        return True

    def save_current_step_data(self) -> None:
        """Save current step data to form_data"""
        # Implementation depends on actual input widgets
        # This is a placeholder
        pass

    @work(exclusive=True)
    async def create_visit(self) -> None:
        """Create the emergency visit"""
        self.notify("⏳ Creando visita...", severity="information")

        try:
            # Create visit in database
            result = await asyncio.to_thread(self._create_visit_in_db)

            if result['success']:
                self.notify(
                    f"✓ Visita creada: {result['folio']}",
                    title="Éxito",
                    severity="information",
                    timeout=5
                )
                self.dismiss(result)
            else:
                self.notify(
                    f"❌ Error: {result['error']}",
                    title="Error",
                    severity="error",
                    timeout=5
                )

        except Exception as e:
            self.notify(f"❌ Error inesperado: {str(e)}", severity="error")

    def _create_visit_in_db(self) -> Dict[str, Any]:
        """Create visit in database (runs in thread pool)"""
        with self.flask_app.app_context():
            from models import db, VisitaEmergencia, Paciente, Doctor, Cama

            try:
                # 1. Create or find patient
                curp = self.form_data.get('curp')
                paciente = None

                if curp:
                    paciente = Paciente.query.filter_by(curp=curp).first()

                if not paciente:
                    paciente = Paciente(
                        nombre=self.form_data['nombre'],
                        edad=int(self.form_data['edad']),
                        sexo=self.form_data['sexo'],
                        curp=curp if curp else None,
                        telefono=self.form_data.get('telefono'),
                        contacto_emergencia=self.form_data.get('contacto_emergencia'),
                        activo=1
                    )
                    db.session.add(paciente)
                    db.session.flush()

                # 2. Create visit
                visita = VisitaEmergencia(
                    id_paciente=paciente.id_paciente,
                    id_doctor=self.form_data['id_doctor'],
                    id_cama=self.form_data['id_cama'],
                    id_trabajador=1,  # TODO: Get from current user
                    id_sala=self.bully_manager.node_id,
                    sintomas=self.form_data['sintomas'],
                    estado='activa',
                    timestamp=datetime.utcnow()
                )

                db.session.add(visita)
                db.session.commit()

                # Refresh to get generated folio
                db.session.refresh(visita)

                return {
                    'success': True,
                    'folio': visita.folio,
                    'id_visita': visita.id_visita
                }

            except Exception as e:
                db.session.rollback()
                return {
                    'success': False,
                    'error': str(e)
                }

    def action_cancel(self) -> None:
        """Cancel wizard"""
        self.dismiss(None)


# Export
__all__ = ['CreateVisitWizard']
