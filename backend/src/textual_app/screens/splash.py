"""
Splash Screen - Animated loading screen with system checks
"""

from textual.app import ComposeResult
from textual.screen import Screen
from textual.widgets import Static, Label
from textual.containers import Container, Vertical, Center
from textual import work
from rich.text import Text
from rich.align import Align
from rich.panel import Panel
import asyncio
import time


# Hospital Logo ASCII Art
HOSPITAL_LOGO = """
    ██╗  ██╗ ██████╗ ███████╗██████╗ ██╗████████╗ █████╗ ██╗     
    ██║  ██║██╔═══██╗██╔════╝██╔══██╗██║╚══██╔══╝██╔══██╗██║     
    ███████║██║   ██║███████╗██████╔╝██║   ██║   ███████║██║     
    ██╔══██║██║   ██║╚════██║██╔═══╝ ██║   ██║   ██╔══██║██║     
    ██║  ██║╚██████╔╝███████║██║     ██║   ██║   ██║  ██║███████╗
    ╚═╝  ╚═╝ ╚═════╝ ╚══════╝╚═╝     ╚═╝   ╚═╝   ╚═╝  ╚═╝╚══════╝
"""

MEDICAL_CROSS = """
                              ███████
                              ███████
                              ███████
                    ███████████████████████████
                    ███████████████████████████
                    ███████████████████████████
                              ███████
                              ███████
                              ███████
"""


class SplashScreen(Screen):
    """
    Animated splash screen with system initialization checks
    """
    
    CSS = """
    SplashScreen {
        align: center middle;
        background: $surface;
    }
    
    #splash-container {
        width: 100%;
        height: 100%;
        align: center middle;
    }
    
    #logo-container {
        width: auto;
        height: auto;
        content-align: center middle;
        padding: 2;
    }
    
    #logo {
        color: $primary;
        text-style: bold;
        content-align: center middle;
    }
    
    #medical-cross {
        color: $error;
        content-align: center middle;
    }
    
    #title {
        color: $accent;
        text-style: bold;
        content-align: center middle;
        margin-top: 1;
    }
    
    #subtitle {
        color: $text-muted;
        text-style: italic;
        content-align: center middle;
    }
    
    #status {
        color: $success;
        content-align: center middle;
        margin-top: 2;
        min-height: 3;
    }
    
    #version {
        color: $text-muted;
        text-style: dim;
        content-align: center middle;
        margin-top: 1;
    }
    """
    
    def __init__(self, flask_app, bully_manager):
        super().__init__()
        self.flask_app = flask_app
        self.bully_manager = bully_manager
        self.checks_complete = False
    
    def compose(self) -> ComposeResult:
        """Compose the splash screen layout"""
        with Container(id="splash-container"):
            with Vertical(id="logo-container"):
                yield Static(MEDICAL_CROSS, id="medical-cross")
                yield Static(HOSPITAL_LOGO, id="logo")
                yield Label("SISTEMA MÉDICO DISTRIBUIDO", id="title")
                yield Label("Emergency Management & Distributed Consensus", id="subtitle")
                yield Static("", id="status")
                yield Label("v2.0.0 - Powered by Textual", id="version")
    
    def on_mount(self) -> None:
        """Called when screen is mounted - start animations"""
        self.run_startup_sequence()
    
    @work(exclusive=True)
    async def run_startup_sequence(self):
        """
        Run animated startup sequence with system checks
        Runs as async worker
        """
        status_widget = self.query_one("#status", Static)
        
        # Animation sequence
        checks = [
            ("Iniciando sistema", 0.3),
            ("Verificando base de datos", 0.5),
            ("Conectando al cluster Bully", 0.7),
            ("Descubriendo nodos en la red", 0.8),
            ("Cargando configuración", 0.4),
            ("Inicializando interfaz", 0.5),
        ]
        
        for message, delay in checks:
            # Show spinner with message
            for i in range(3):
                spinner = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"][i % 10]
                status_widget.update(f"{spinner} {message}...")
                await asyncio.sleep(0.1)
            
            # Simulate work
            await asyncio.sleep(delay)
            
            # Show success
            status_widget.update(f"✓ {message}")
            await asyncio.sleep(0.2)
        
        # Final message
        node_id = self.bully_manager.node_id
        state = self.bully_manager.state
        cluster_size = len(self.bully_manager.cluster_nodes) + 1  # +1 for self
        
        final_msg = Text()
        final_msg.append("✓ Sistema listo\n", style="bold green")
        final_msg.append(f"Nodo {node_id} | ", style="cyan")
        final_msg.append(f"{state.value.upper()} | ", style="yellow" if state.value == "follower" else "magenta")
        final_msg.append(f"{cluster_size} nodo(s) detectado(s)", style="blue")
        
        status_widget.update(final_msg)
        await asyncio.sleep(1.5)
        
        self.checks_complete = True
        
        # Transition to login screen
        self.app.push_screen("login")


class SimpleSplashScreen(Screen):
    """
    Simplified splash screen without heavy animations
    For faster startup or terminals with limited support
    """
    
    def __init__(self, flask_app, bully_manager):
        super().__init__()
        self.flask_app = flask_app
        self.bully_manager = bully_manager
    
    def compose(self) -> ComposeResult:
        """Compose simple splash"""
        content = Text()
        content.append("\n\n")
        content.append("    🏥 HOSPITAL\n", style="bold red")
        content.append("    ═══════════\n\n", style="bold white")
        content.append("    Sistema Médico Distribuido v2.0\n", style="bold cyan")
        content.append("    Emergency Management System\n\n", style="dim")
        content.append(f"    Nodo {self.bully_manager.node_id} | ", style="green")
        content.append(f"{self.bully_manager.state.value}\n\n", style="yellow")
        content.append("    Cargando", style="dim")
        
        yield Static(Align.center(content))
    
    def on_mount(self) -> None:
        """Auto-transition after brief delay"""
        self.set_timer(2, lambda: self.app.push_screen("login"))


# Export
__all__ = ['SplashScreen', 'SimpleSplashScreen']
