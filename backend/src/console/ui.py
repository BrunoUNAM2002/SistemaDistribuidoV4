"""
Rich UI helpers and utilities for console interface.
Provides reusable components for formatting and display.
"""
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.prompt import Prompt, IntPrompt, Confirm
from rich.layout import Layout
from rich.text import Text
from datetime import datetime

console = Console()

def create_header(title, subtitle=None, border_style="cyan"):
    """
    Create a styled header panel.

    Args:
        title: Main title text
        subtitle: Optional subtitle
        border_style: Border color

    Returns:
        Panel: Formatted header panel
    """
    if subtitle:
        content = f"[bold cyan]{title}[/bold cyan]\n{subtitle}"
    else:
        content = f"[bold cyan]{title}[/bold cyan]"

    return Panel(content, border_style=border_style)

def create_table(title, columns, rows=None, show_header=True):
    """
    Create a Rich table with specified columns and rows.

    Args:
        title: Table title
        columns: List of tuples (name, style, justify)
        rows: List of row data (optional)
        show_header: Whether to show column headers

    Returns:
        Table: Configured Rich table
    """
    table = Table(title=title, show_header=show_header, header_style="bold magenta")

    # Add columns
    for col in columns:
        if len(col) == 1:
            table.add_column(col[0])
        elif len(col) == 2:
            table.add_column(col[0], style=col[1])
        else:
            table.add_column(col[0], style=col[1], justify=col[2])

    # Add rows if provided
    if rows:
        for row in rows:
            table.add_row(*[str(cell) for cell in row])

    return table

def format_datetime(dt):
    """Format datetime for display"""
    if dt is None:
        return "N/A"
    if isinstance(dt, str):
        return dt
    return dt.strftime("%Y-%m-%d %H:%M:%S")

def format_time(dt):
    """Format time only for display"""
    if dt is None:
        return "N/A"
    if isinstance(dt, str):
        return dt
    return dt.strftime("%H:%M:%S")

def format_date(dt):
    """Format date only for display"""
    if dt is None:
        return "N/A"
    if isinstance(dt, str):
        return dt
    return dt.strftime("%Y-%m-%d")

def truncate_text(text, max_length=50):
    """Truncate text with ellipsis if too long"""
    if not text:
        return ""
    text = str(text)
    if len(text) <= max_length:
        return text
    return text[:max_length-3] + "..."

def status_color(status):
    """Return color for visit status"""
    status_colors = {
        'activa': 'green',
        'completada': 'blue',
        'cancelada': 'red',
        'en_espera': 'yellow'
    }
    return status_colors.get(status.lower(), 'white')

def priority_color(priority):
    """Return color for priority level"""
    priority_colors = {
        'ALTA': 'red',
        'MEDIA': 'yellow',
        'BAJA': 'green'
    }
    return priority_colors.get(priority.upper(), 'white')

def bool_icon(value):
    """Return icon for boolean value"""
    return "✓" if value else "✗"

def bool_color(value):
    """Return color for boolean value"""
    return "green" if value else "red"

def confirm_action(message, default=False):
    """
    Ask for user confirmation.

    Args:
        message: Confirmation message
        default: Default value

    Returns:
        bool: User's choice
    """
    return Confirm.ask(message, default=default)

def get_text_input(prompt_text, default=None):
    """
    Get text input from user with Rich prompt.

    Args:
        prompt_text: Prompt message
        default: Default value

    Returns:
        str: User input (cleaned of CR/LF characters)
    """
    if default:
        result = Prompt.ask(prompt_text, default=default)
    else:
        result = Prompt.ask(prompt_text)

    # Remove any CR (\r) or trailing whitespace
    return result.strip().replace('\r', '')

def get_int_input(prompt_text, choices=None):
    """
    Get integer input from user.

    Args:
        prompt_text: Prompt message
        choices: Optional list of valid choices

    Returns:
        int: User input
    """
    if choices:
        return IntPrompt.ask(prompt_text, choices=[str(c) for c in choices])
    return IntPrompt.ask(prompt_text)

def get_choice(prompt_text, choices):
    """
    Get choice from list using Prompt.

    Args:
        prompt_text: Prompt message
        choices: List of valid choices

    Returns:
        str: Selected choice
    """
    return Prompt.ask(prompt_text, choices=choices)

def show_success(message):
    """Display success message"""
    console.print(f"[green]✓[/green] {message}")

def show_error(message):
    """Display error message"""
    console.print(f"[red]✗[/red] {message}")

def show_warning(message):
    """Display warning message"""
    console.print(f"[yellow]⚠[/yellow] {message}")

def show_info(message):
    """Display info message"""
    console.print(f"[cyan]ℹ[/cyan] {message}")

def pause():
    """Pause and wait for Enter key"""
    _ = console.input("\n[dim]Presione Enter para continuar...[/dim]")

def clear_screen():
    """Clear the console screen"""
    console.clear()

def create_status_layout(node_id, role, leader_id, last_heartbeat=None):
    """
    Create a layout showing node status.

    Args:
        node_id: Current node ID
        role: Node role (LEADER, FOLLOWER, CANDIDATE)
        leader_id: Current leader ID
        last_heartbeat: Last heartbeat timestamp

    Returns:
        str: Formatted status text
    """
    is_leader = (node_id == leader_id)
    role_color = "green" if is_leader else "blue"

    status_text = f"Nodo: [yellow]{node_id}[/yellow] | "
    status_text += f"Estado: [{role_color}]{role}[/] "
    if is_leader:
        status_text += "👑"

    if not is_leader and last_heartbeat is not None:
        status_text += f" | Último heartbeat: {last_heartbeat:.1f}s"

    return status_text

def create_metrics_panel(metrics):
    """
    Create a panel displaying system metrics.

    Args:
        metrics: Dictionary of metrics

    Returns:
        Panel: Formatted metrics panel
    """
    content = []
    for key, value in metrics.items():
        content.append(f"[bold]{key}:[/bold] [cyan]{value}[/cyan]")

    return Panel(
        "\n".join(content),
        title="Métricas del Sistema",
        border_style="green"
    )

def display_list_numbered(items, title=None):
    """
    Display a numbered list of items.

    Args:
        items: List of items to display
        title: Optional title
    """
    if title:
        console.print(f"\n[bold cyan]{title}[/bold cyan]")

    for i, item in enumerate(items, 1):
        console.print(f"  [{i}] {item}")

def create_two_column_layout(left_content, right_content, left_title="", right_title=""):
    """
    Create a two-column layout.

    Args:
        left_content: Content for left column
        right_content: Content for right column
        left_title: Title for left column
        right_title: Title for right column

    Returns:
        Layout: Two-column layout
    """
    layout = Layout()
    layout.split_row(
        Layout(Panel(left_content, title=left_title), name="left"),
        Layout(Panel(right_content, title=right_title), name="right")
    )
    return layout
