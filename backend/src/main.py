#!/usr/bin/env python3
"""
Entry point for console-based distributed medical emergency system.
No web server - pure terminal interface.
"""
import signal
import sys
import logging
import logging.handlers
import os
import termios
import tty
from rich.console import Console
from rich.panel import Panel

from app_factory import create_app
from bully import BullyNode
from console.auth import login
from console.menus import main_menu
from console.notifications import create_notification_monitor
from config import Config

console = Console()

class GracefulKiller:
    """Handle SIGINT and SIGTERM for graceful shutdown"""
    def __init__(self):
        self.kill_now = False
        signal.signal(signal.SIGINT, self._exit_gracefully)
        signal.signal(signal.SIGTERM, self._exit_gracefully)

    def _exit_gracefully(self, signum, frame):
        # Don't print here - let the exception handler print the message
        self.kill_now = True
        # Re-raise KeyboardInterrupt to trigger normal exception handling
        raise KeyboardInterrupt

def setup_logging(node_id):
    """Setup rotating file logger"""
    log_dir = '../logs'
    if not os.path.exists(log_dir):
        os.makedirs(log_dir)

    log_format = logging.Formatter(
        fmt='[%(asctime)s] [Node-%(node_id)s] [%(levelname)s] [%(name)s] %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )

    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)

    # File handler
    file_handler = logging.handlers.RotatingFileHandler(
        filename=f'{log_dir}/node_{node_id}.log',
        maxBytes=10 * 1024 * 1024,  # 10MB
        backupCount=5,
        encoding='utf-8'
    )
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(log_format)

    # Add node_id filter
    class NodeIdFilter(logging.Filter):
        def filter(self, record):
            record.node_id = node_id
            return True

    file_handler.addFilter(NodeIdFilter())
    root_logger.addHandler(file_handler)

    # Silence noisy libraries
    logging.getLogger('werkzeug').setLevel(logging.WARNING)


def setup_terminal():
    """Configure terminal for proper line endings"""
    if sys.stdin.isatty():
        try:
            # Get current terminal settings
            fd = sys.stdin.fileno()
            old_settings = termios.tcgetattr(fd)
            new_settings = termios.tcgetattr(fd)

            # Enable ICRNL (map CR to NL on input)
            # This ensures Enter key sends \n instead of \r
            new_settings[0] |= termios.ICRNL

            # Apply settings
            termios.tcsetattr(fd, termios.TCSADRAIN, new_settings)

            return old_settings
        except Exception as e:
            # If terminal setup fails, continue anyway
            logging.getLogger(__name__).warning(f"Could not setup terminal: {e}")
            return None
    return None


def main():
    """Main entry point"""
    # Setup terminal for proper input handling
    old_terminal_settings = setup_terminal()

    try:
        # Initialize NODE_ID (auto-generate if not specified)
        from config import Config
        node_id = Config.initialize_node_id()

        # Create Flask app (no web server)
        app = create_app()

        # Setup logging
        setup_logging(node_id)
        logger = logging.getLogger(__name__)

        # Mostrar si el ID fue auto-generado
        id_source = "auto-generado" if Config.is_node_id_auto_generated() else "manual"

        console.print(Panel(
            f"[bold cyan]Sistema de Emergencias Médicas Distribuido[/bold cyan]\n"
            f"Nodo: [yellow]{node_id}[/yellow] ([dim]{id_source}[/dim])",
            title="🏥 Inicializando",
            border_style="cyan"
        ))

        # Initialize Bully system
        console.print("[dim]Iniciando sistema Bully...[/dim]")
        logger.info("Initializing Bully node")

        # Configurar según modo (dinámico vs estático)
        if Config.is_dynamic_mode():
            # MODO DINÁMICO: Auto-descubrimiento via multicast
            console.print(f"[cyan]Modo dinámico:[/cyan] Usando auto-descubrimiento")
            logger.info("Using DYNAMIC mode - auto-discovery enabled")

            bully_manager = BullyNode(
                node_id=node_id,
                tcp_port=Config.TCP_PORT,
                udp_port=Config.UDP_PORT,
                use_discovery=True,
                multicast_group=Config.MULTICAST_GROUP,
                multicast_port=Config.MULTICAST_PORT
            )
            bully_manager.start()
            logger.info(f"Bully system started (DYNAMIC) - TCP:{Config.TCP_PORT}, UDP:{Config.UDP_PORT}")
            console.print(f"[green]✓[/green] Nodo {node_id} buscando otros nodos en la red...")

        else:
            # MODO ESTÁTICO: Lista fija de nodos (retrocompatibilidad)
            console.print(f"[yellow]Modo estático:[/yellow] Usando lista fija de nodos")
            logger.info("Using STATIC mode - fixed cluster_nodes")

            cluster_nodes = {}
            for nodo_info in Config.OTROS_NODOS:
                if nodo_info['id'] != node_id:
                    # BullyNode expects tuple: (host, tcp_port, udp_port)
                    cluster_nodes[nodo_info['id']] = (
                        'localhost',  # host
                        nodo_info['tcp_port'],  # tcp_port
                        6000 + nodo_info['id'] - 1  # udp_port
                    )

            bully_manager = BullyNode(
                node_id=node_id,
                cluster_nodes=cluster_nodes,
                tcp_port=Config.TCP_PORT,
                udp_port=Config.UDP_PORT,
                use_discovery=False
            )
            bully_manager.start()
            logger.info(f"Bully system started (STATIC) - TCP:{Config.TCP_PORT}, UDP:{Config.UDP_PORT}")

        # Initialize notification monitor
        console.print("[dim]Iniciando monitor de notificaciones...[/dim]")
        notification_monitor = create_notification_monitor(app, bully_manager, check_interval=10)
        notification_monitor.start()
        logger.info("Notification monitor started")

        # Setup graceful shutdown
        killer = GracefulKiller()

        console.print("[green]✓[/green] Sistema iniciado\n")

        # Login loop
        try:
            while not killer.kill_now:
                user = login(app)

                if user is None:
                    break

                # Run main menu (role-based)
                continue_session = True
                while continue_session and not killer.kill_now:
                    continue_session = main_menu(app, bully_manager, user)

                if killer.kill_now:
                    break

                console.print("\n[yellow]Sesión cerrada[/yellow]\n")

        except KeyboardInterrupt:
            console.print("\n[yellow]Cerrando sistema...[/yellow]")

        finally:
            # Cleanup - do this quickly to avoid hanging
            try:
                notification_monitor.stop()
                logger.info("Notification monitor stopped")
            except Exception as e:
                logger.error(f"Error stopping notification monitor: {e}")

            try:
                bully_manager.stop()
                logger.info("Bully system stopped")
            except Exception as e:
                logger.error(f"Error stopping bully system: {e}")

            console.print("[green]✓ Sistema cerrado[/green]")
            # Force exit to ensure we don't hang
            sys.exit(0)

    except Exception as e:
        console.print(f"[red]✗ Error fatal durante inicialización: {e}[/red]")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == '__main__':
    main()
