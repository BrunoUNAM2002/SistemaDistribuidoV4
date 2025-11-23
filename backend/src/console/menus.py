"""
Interactive menu system using Questionary for arrow-key navigation.
Role-based menus integrating all views and actions.
"""
import questionary
from questionary import Style
from rich.console import Console
from rich.panel import Panel

from console.views import (
    show_my_visits, show_all_visits, show_dashboard, show_bully_status,
    show_available_resources, show_doctors, show_patients, show_beds,
    show_patient_visits
)
from console.actions import create_visit, close_visit, assign_doctor_to_patient
from console.ui import clear_screen, show_error

console = Console()

# Questionary custom style
custom_style = Style([
    ('qmark', 'fg:#00FF00 bold'),          # Green question mark
    ('question', 'bold'),                   # Question text
    ('answer', 'fg:#00FFFF bold'),         # Cyan answer
    ('pointer', 'fg:#00FF00 bold'),        # Green pointer
    ('highlighted', 'fg:#00FF00 bold'),    # Green highlighted choice
    ('selected', 'fg:#00FFFF'),            # Cyan selected
    ('separator', 'fg:#555555'),           # Gray separator
    ('instruction', 'fg:#888888'),         # Gray instructions
])


def show_menu_header(app, bully_manager, user):
    """
    Display menu header with node and user info.

    Args:
        app: Flask application
        bully_manager: BullyNode instance
        user: Current user
    """
    clear_screen()

    is_leader = bully_manager.is_leader()
    leader_id = bully_manager.get_current_leader()
    state = bully_manager.state.value

    header_text = f"""
[bold cyan]Sistema de Emergencias Médicas - Distribuido[/bold cyan]

[bold]Usuario:[/bold] [yellow]{user.username}[/yellow] ({user.rol})
[bold]Nodo:[/bold] [yellow]{app.config['NODE_ID']}[/yellow] | [bold]Estado:[/bold] [{'green' if is_leader else 'blue'}]{state}[/]
[bold]Líder:[/bold] [green]Nodo {leader_id}[/green] {'👑' if is_leader else ''}
    """

    console.print(Panel(header_text.strip(), border_style="cyan", title="🏥 Menú Principal"))
    console.print()


def main_menu(app, bully_manager, user):
    """
    Main menu dispatcher - routes to role-based menu.

    Args:
        app: Flask application
        bully_manager: BullyNode instance
        user: Current logged-in user

    Returns:
        bool: True to continue, False to logout
    """
    if user.rol == 'doctor':
        return doctor_menu(app, bully_manager, user)
    elif user.rol == 'trabajador_social':
        return trabajador_social_menu(app, bully_manager, user)
    elif user.rol == 'paciente':
        return paciente_menu(app, bully_manager, user)
    else:
        show_error(f"Rol desconocido: {user.rol}")
        return False


def doctor_menu(app, bully_manager, user):
    """
    Menu for doctors.

    Args:
        app: Flask application
        bully_manager: BullyNode instance
        user: Current user (doctor)

    Returns:
        bool: True to continue, False to logout
    """
    while True:
        show_menu_header(app, bully_manager, user)

        choices = [
            "📋 Ver mis visitas asignadas",
            "✅ Cerrar visita (completar con diagnóstico)",
            "🏥 Ver todas las visitas",
            "📊 Ver dashboard de métricas",
            "🌐 Ver estado del cluster Bully",
            "💼 Ver recursos disponibles (doctores y camas)",
            "🚪 Cerrar sesión"
        ]

        choice = questionary.select(
            "Seleccione una opción:",
            choices=choices,
            style=custom_style
        ).ask()

        if choice is None or choice == "🚪 Cerrar sesión":
            return False

        if choice == "📋 Ver mis visitas asignadas":
            show_my_visits(app, user)

        elif choice == "✅ Cerrar visita (completar con diagnóstico)":
            close_visit(app, user)

        elif choice == "🏥 Ver todas las visitas":
            visitas_submenu(app)

        elif choice == "📊 Ver dashboard de métricas":
            show_dashboard(app)

        elif choice == "🌐 Ver estado del cluster Bully":
            show_bully_status(app, bully_manager)

        elif choice == "💼 Ver recursos disponibles (doctores y camas)":
            show_available_resources(app, bully_manager)


def trabajador_social_menu(app, bully_manager, user):
    """
    Menu for social workers.

    Args:
        app: Flask application
        bully_manager: BullyNode instance
        user: Current user (trabajador social)

    Returns:
        bool: True to continue, False to logout
    """
    while True:
        show_menu_header(app, bully_manager, user)

        choices = [
            "➕ Crear nueva visita de emergencia",
            "🩺 Asignar Doctor a Paciente",
            "🏥 Ver todas las visitas",
            "📊 Ver dashboard de métricas",
            "🌐 Ver estado del cluster Bully",
            "💼 Ver recursos disponibles (doctores y camas)",
            "🚪 Cerrar sesión"
        ]

        choice = questionary.select(
            "Seleccione una opción:",
            choices=choices,
            style=custom_style
        ).ask()

        if choice is None or choice == "🚪 Cerrar sesión":
            return False

        if choice == "➕ Crear nueva visita de emergencia":
            create_visit(app, bully_manager, user)

        elif choice == "🩺 Asignar Doctor a Paciente":
            assign_doctor_to_patient(app, bully_manager, user)

        elif choice == "🏥 Ver todas las visitas":
            visitas_submenu(app)

        elif choice == "📊 Ver dashboard de métricas":
            show_dashboard(app)

        elif choice == "🌐 Ver estado del cluster Bully":
            show_bully_status(app, bully_manager)

        elif choice == "💼 Ver recursos disponibles (doctores y camas)":
            show_available_resources(app, bully_manager)


def visitas_submenu(app, is_admin=False, bully_manager=None, user=None):
    """
    Submenu for visit management.

    Args:
        app: Flask application
        is_admin: Whether user is admin (enables cancel option)
        bully_manager: BullyNode instance (for admin operations)
        user: Current user (for admin operations)
    """
    while True:
        clear_screen()
        console.print(Panel(
            "[bold cyan]Gestión de Visitas[/bold cyan]",
            border_style="cyan"
        ))
        console.print()

        choices = [
            "📋 Ver todas las visitas",
            "✅ Ver visitas activas",
            "🏁 Ver visitas completadas",
            "⬅️  Volver al menú principal"
        ]

        choice = questionary.select(
            "Seleccione una opción:",
            choices=choices,
            style=custom_style
        ).ask()

        if choice is None or choice == "⬅️  Volver al menú principal":
            return

        if choice == "📋 Ver todas las visitas":
            show_all_visits(app, estado_filter=None)

        elif choice == "✅ Ver visitas activas":
            show_all_visits(app, estado_filter='activa')

        elif choice == "🏁 Ver visitas completadas":
            show_all_visits(app, estado_filter='completada')


def consultas_menu(app, bully_manager):
    """
    Submenu for queries and reports.

    Args:
        app: Flask application
        bully_manager: BullyNode instance
    """
    while True:
        clear_screen()
        console.print(Panel(
            "[bold cyan]Consultas y Reportes[/bold cyan]",
            border_style="cyan"
        ))
        console.print()

        choices = [
            "👨‍⚕️ Ver todos los doctores",
            "🏥 Ver todos los pacientes",
            "🛏️  Ver estado de camas",
            "💼 Ver recursos disponibles",
            "⬅️  Volver al menú principal"
        ]

        choice = questionary.select(
            "Seleccione una opción:",
            choices=choices,
            style=custom_style
        ).ask()

        if choice is None or choice == "⬅️  Volver al menú principal":
            return

        if choice == "👨‍⚕️ Ver todos los doctores":
            show_doctors(app, bully_manager)

        elif choice == "🏥 Ver todos los pacientes":
            show_patients(app)

        elif choice == "🛏️  Ver estado de camas":
            show_beds(app)

        elif choice == "💼 Ver recursos disponibles":
            show_available_resources(app, bully_manager)


def paciente_menu(app, bully_manager, user):
    """
    Menu for patients.

    Args:
        app: Flask application
        bully_manager: BullyNode instance
        user: Current user (paciente)

    Returns:
        bool: True to continue, False to logout
    """
    while True:
        show_menu_header(app, bully_manager, user)

        choices = [
            "📋 Ver mis visitas de emergencia",
            "📊 Ver dashboard de métricas",
            "🌐 Ver estado del cluster Bully",
            "🚪 Cerrar sesión"
        ]

        choice = questionary.select(
            "Seleccione una opción:",
            choices=choices,
            style=custom_style
        ).ask()

        if choice is None or choice == "🚪 Cerrar sesión":
            return False

        if choice == "📋 Ver mis visitas de emergencia":
            show_patient_visits(app, user)

        elif choice == "📊 Ver dashboard de métricas":
            show_dashboard(app)

        elif choice == "🌐 Ver estado del cluster Bully":
            show_bully_status(app, bully_manager)
