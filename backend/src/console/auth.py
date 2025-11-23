"""
Console authentication module using getpass for secure password input.
"""
from getpass import getpass
from rich.console import Console
from rich.panel import Panel
from models import Usuario

console = Console()

def login(app):
    """
    Display login prompt and authenticate user.

    Args:
        app: Flask application instance

    Returns:
        Usuario: Authenticated user object or None if failed
    """
    console.clear()

    # Header
    console.print(Panel(
        "[bold cyan]Sistema de Emergencias Médicas - Distribuido[/bold cyan]\n"
        f"[yellow]Nodo {app.config['NODE_ID']}[/yellow]",
        title="🏥 Login",
        border_style="blue"
    ))

    max_attempts = 3
    try:
        for attempt in range(max_attempts):
            username = console.input("\n[bold]Usuario:[/bold] ").strip().replace('\r', '')
            password = getpass("Contraseña: ").strip().replace('\r', '')

            # Use Flask app context for database query
            with app.app_context():
                user = Usuario.query.filter_by(
                    username=username,
                    activo=True
                ).first()

                if user and user.check_password(password):
                    console.print(f"\n[green]✓[/green] Sesión iniciada como [bold]{user.rol}[/bold]")
                    return user
                else:
                    remaining = max_attempts - attempt - 1
                    if remaining > 0:
                        console.print(f"[red]✗[/red] Credenciales inválidas. {remaining} intentos restantes.")
                    else:
                        console.print("[red]✗[/red] Acceso denegado.")

    except KeyboardInterrupt:
        # Don't print message here - let main.py handle it
        return None

    return None
