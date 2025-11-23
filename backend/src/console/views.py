"""
Console views using Rich tables for data display.
All read-only operations for viewing system data.
"""
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.layout import Layout
from models import VisitaEmergencia, Doctor, Paciente, Cama, TrabajadorSocial
from console.ui import (
    create_header, create_table, format_datetime, format_time,
    truncate_text, status_color, bool_icon, pause, clear_screen
)

console = Console()

def show_my_visits(app, user):
    """
    Show visits assigned to current doctor.

    Args:
        app: Flask application
        user: Current logged-in user
    """
    clear_screen()
    console.print(create_header("Mis Visitas Asignadas"))

    with app.app_context():
        visitas = VisitaEmergencia.query.filter_by(
            id_doctor=user.id_relacionado,
            estado='activa'
        ).order_by(VisitaEmergencia.timestamp.desc()).limit(50).all()

        if not visitas:
            console.print("\n[yellow]No tiene visitas asignadas actualmente[/yellow]")
            pause()
            return

        # Create table
        table = Table(show_header=True, header_style="bold magenta", title=f"Total: {len(visitas)} visitas")
        table.add_column("Folio", style="cyan", width=20)
        table.add_column("Paciente", style="green")
        table.add_column("Síntomas", style="white")
        table.add_column("Cama", justify="center", width=8)
        table.add_column("Hora Inicio", style="yellow", width=10)

        for v in visitas:
            table.add_row(
                v.folio,
                v.paciente.nombre,
                truncate_text(v.sintomas, 40),
                f"#{v.cama.numero}",
                format_time(v.timestamp)
            )

        console.print(table)
        pause()

def show_all_visits(app, estado_filter=None):
    """
    Show all visits with optional status filter.

    Args:
        app: Flask application
        estado_filter: Optional status filter ('activa', 'completada', None for all)
    """
    clear_screen()

    if estado_filter:
        title = f"Visitas - Estado: {estado_filter.upper()}"
    else:
        title = "Todas las Visitas"

    console.print(create_header(title))

    with app.app_context():
        query = VisitaEmergencia.query

        if estado_filter:
            query = query.filter_by(estado=estado_filter)

        visitas = query.order_by(VisitaEmergencia.timestamp.desc()).limit(100).all()

        if not visitas:
            console.print(f"\n[yellow]No hay visitas{' con ese estado' if estado_filter else ''}[/yellow]")
            pause()
            return

        # Create table
        table = Table(show_header=True, header_style="bold magenta", title=f"Total: {len(visitas)} visitas")
        table.add_column("Folio", style="cyan", width=18)
        table.add_column("Paciente", style="green", width=20)
        table.add_column("Doctor", style="blue", width=20)
        table.add_column("Estado", width=12)
        table.add_column("Sala", justify="center", width=6)
        table.add_column("Fecha", style="yellow", width=16)

        for v in visitas:
            color = status_color(v.estado)
            table.add_row(
                v.folio,
                truncate_text(v.paciente.nombre, 18),
                truncate_text(v.doctor.nombre, 18),
                f"[{color}]{v.estado}[/]",
                str(v.id_sala),
                format_datetime(v.timestamp)
            )

        console.print(table)
        pause()

def show_dashboard(app):
    """
    Show dashboard with system metrics.

    Args:
        app: Flask application
    """
    clear_screen()
    console.print(create_header("Dashboard de Métricas", f"Nodo {app.config['NODE_ID']}"))

    with app.app_context():
        # Get metrics
        total_visitas_activas = VisitaEmergencia.query.filter_by(estado='activa').count()
        total_visitas_hoy = VisitaEmergencia.query.filter(
            VisitaEmergencia.timestamp >= db.func.date('now')
        ).count() if hasattr(db, 'func') else 0

        doctores_disponibles = Doctor.query.filter_by(
            id_sala=app.config['NODE_ID'],
            disponible=True,
            activo=True
        ).count()

        camas_disponibles = Cama.query.filter_by(
            id_sala=app.config['NODE_ID'],
            ocupada=False
        ).count()

        total_doctores = Doctor.query.filter_by(
            id_sala=app.config['NODE_ID'],
            activo=True
        ).count()

        total_camas = Cama.query.filter_by(
            id_sala=app.config['NODE_ID']
        ).count()

        # Create layout
        layout = Layout()
        layout.split_column(
            Layout(name="metrics", size=12),
            Layout(name="details", size=10)
        )

        # Metrics panel
        metrics_text = f"""
[bold cyan]Visitas Activas:[/bold cyan] [green]{total_visitas_activas}[/green]
[bold cyan]Visitas Hoy:[/bold cyan] [yellow]{total_visitas_hoy}[/yellow]
[bold cyan]Doctores Disponibles:[/bold cyan] [{'green' if doctores_disponibles > 0 else 'red'}]{doctores_disponibles}/{total_doctores}[/]
[bold cyan]Camas Disponibles:[/bold cyan] [{'green' if camas_disponibles > 0 else 'red'}]{camas_disponibles}/{total_camas}[/]
        """
        layout["metrics"].update(Panel(metrics_text, title="Métricas del Sistema", border_style="green"))

        # Recent visits
        visitas_recientes = VisitaEmergencia.query.filter_by(
            id_sala=app.config['NODE_ID']
        ).order_by(VisitaEmergencia.timestamp.desc()).limit(5).all()

        if visitas_recientes:
            recent_text = "\n".join([
                f"[cyan]{v.folio}[/cyan] - {truncate_text(v.paciente.nombre, 20)} - [{status_color(v.estado)}]{v.estado}[/]"
                for v in visitas_recientes
            ])
        else:
            recent_text = "[yellow]No hay visitas recientes[/yellow]"

        layout["details"].update(Panel(recent_text, title="Últimas 5 Visitas", border_style="blue"))

        console.print(layout)
        pause()

def show_bully_status(app, bully_manager):
    """
    Show Bully cluster status with detailed information.

    Args:
        app: Flask application
        bully_manager: BullyNode instance
    """
    clear_screen()
    console.print(create_header("Estado del Cluster Bully"))

    # Current node info
    is_leader = bully_manager.is_leader()
    leader_id = bully_manager.get_current_leader()
    current_state = bully_manager.state.value

    # Header info
    header_text = f"""
[bold cyan]Nodo Actual:[/bold cyan] [yellow]{app.config['NODE_ID']}[/yellow]
[bold cyan]Estado:[/bold cyan] [{'green' if is_leader else 'blue'}]{current_state}[/]
[bold cyan]Líder Actual:[/bold cyan] [green]Nodo {leader_id}[/green] {'👑' if is_leader else ''}
    """
    console.print(Panel(header_text, border_style="cyan"))

    # Cluster nodes info
    try:
        console.print("\n")

        # Get basic cluster info
        nodes_info = []
        for nodo_id in [1, 2, 3, 4]:
            is_current = (nodo_id == app.config['NODE_ID'])
            is_node_leader = (nodo_id == leader_id)

            if is_current:
                role = current_state
            elif is_node_leader:
                role = "LEADER"
            else:
                role = "FOLLOWER"

            nodes_info.append({
                'id': nodo_id,
                'role': role,
                'is_current': is_current
            })

        # Display nodes table
        table = Table(title="Nodos del Cluster", show_header=True, header_style="bold magenta")
        table.add_column("Nodo", justify="center", style="cyan", width=12)
        table.add_column("Estado", style="magenta", width=15)
        table.add_column("Icono", justify="center", width=8)

        for node in nodes_info:
            node_display = f"Nodo {node['id']}"
            if node['is_current']:
                node_display = f"[bold]{node_display} (YO)[/bold]"

            icon = "👑" if node['role'] == "LEADER" else "🔵"

            table.add_row(
                node_display,
                node['role'],
                icon
            )

        console.print(table)

    except Exception as e:
        console.print(f"\n[red]Error mostrando cluster: {e}[/red]")

    pause()

def show_available_resources(app, bully_manager):
    """
    Show available doctors and beds from ALL cluster nodes (DISTRIBUTED).

    Args:
        app: Flask application
        bully_manager: BullyNode instance for cluster queries
    """
    clear_screen()
    console.print(create_header("Recursos Disponibles - TODO EL CLUSTER"))

    with app.app_context():
        # DISTRIBUTED QUERY: Get all doctors from cluster
        from models import get_all_cluster_doctors, get_all_cluster_beds
        doctores = get_all_cluster_doctors(bully_manager, activo=True)

        console.print("\n[bold cyan]Doctores (todas las salas):[/bold cyan]")
        if doctores:
            table_doc = Table(show_header=True, header_style="bold magenta")
            table_doc.add_column("ID", justify="center", width=6)
            table_doc.add_column("Nombre", style="green", width=25)
            table_doc.add_column("Especialidad", style="cyan", width=18)
            table_doc.add_column("Sala", justify="center", width=6)
            table_doc.add_column("Disponible", justify="center", width=12)

            for doc in doctores:
                disp_color = "green" if doc['disponible'] else "red"
                table_doc.add_row(
                    str(doc['id_doctor']),
                    doc['nombre'],
                    doc['especialidad'] or "General",
                    str(doc['id_sala']),
                    f"[{disp_color}]{bool_icon(doc['disponible'])}[/]"
                )

            console.print(table_doc)
        else:
            console.print("[yellow]No hay doctores en el cluster[/yellow]")

        # DISTRIBUTED QUERY: Get all beds from cluster
        camas = get_all_cluster_beds(bully_manager)

        console.print("\n[bold cyan]Camas (todas las salas):[/bold cyan]")
        if camas:
            table_camas = Table(show_header=True, header_style="bold magenta")
            table_camas.add_column("Número", justify="center", width=10)
            table_camas.add_column("Sala", justify="center", width=6)
            table_camas.add_column("Estado", justify="center", width=15)
            table_camas.add_column("Paciente Actual", style="yellow", width=30)

            for cama in camas:
                estado = "Ocupada" if cama['ocupada'] else "Libre"
                estado_color = "red" if cama['ocupada'] else "green"
                paciente_nombre = cama['paciente_nombre'] if cama['paciente_nombre'] else "-"

                table_camas.add_row(
                    str(cama['numero']),
                    str(cama['id_sala']),
                    f"[{estado_color}]{estado}[/]",
                    paciente_nombre
                )

            console.print(table_camas)
        else:
            console.print("[yellow]No hay camas registradas en el cluster[/yellow]")

        pause()

def show_doctors(app, bully_manager):
    """
    Show all doctors in the system from ALL nodes (DISTRIBUTED).

    Args:
        app: Flask application
        bully_manager: BullyNode instance for cluster queries
    """
    clear_screen()
    console.print(create_header("Lista de Doctores - TODAS LAS SALAS"))

    with app.app_context():
        # DISTRIBUTED QUERY: Get doctors from all cluster nodes
        from models import get_all_cluster_doctors
        doctores = get_all_cluster_doctors(bully_manager, activo=True)

        if not doctores:
            console.print("\n[yellow]No hay doctores registrados en el cluster[/yellow]")
            pause()
            return

        table = Table(show_header=True, header_style="bold magenta", title=f"Total: {len(doctores)} doctores (cluster)")
        table.add_column("ID", justify="center", width=6)
        table.add_column("Nombre", style="green", width=25)
        table.add_column("Especialidad", style="cyan", width=20)
        table.add_column("Sala", justify="center", width=6)
        table.add_column("Disponible", justify="center", width=12)

        for doc in doctores:
            disp_color = "green" if doc['disponible'] else "red"
            table.add_row(
                str(doc['id_doctor']),
                doc['nombre'],
                doc['especialidad'] or "General",
                str(doc['id_sala']),
                f"[{disp_color}]{bool_icon(doc['disponible'])}[/]"
            )

        console.print(table)
        pause()

def show_patients(app):
    """
    Show all patients in the system (Admin only).

    Args:
        app: Flask application
    """
    clear_screen()
    console.print(create_header("Lista de Pacientes"))

    with app.app_context():
        pacientes = Paciente.query.filter_by(activo=1).limit(100).all()

        if not pacientes:
            console.print("\n[yellow]No hay pacientes registrados[/yellow]")
            pause()
            return

        table = Table(show_header=True, header_style="bold magenta", title=f"Total: {len(pacientes)} pacientes")
        table.add_column("ID", justify="center", width=6)
        table.add_column("Nombre", style="green", width=25)
        table.add_column("Edad", justify="center", width=6)
        table.add_column("Sexo", justify="center", width=6)
        table.add_column("CURP", style="cyan", width=20)
        table.add_column("Teléfono", style="yellow", width=15)

        for pac in pacientes:
            table.add_row(
                str(pac.id_paciente),
                pac.nombre,
                str(pac.edad) if pac.edad else "-",
                pac.sexo or "-",
                pac.curp or "-",
                pac.telefono or "-"
            )

        console.print(table)
        pause()

def show_beds(app):
    """
    Show all beds in current sala.

    Args:
        app: Flask application
    """
    clear_screen()
    console.print(create_header("Estado de Camas", f"Sala {app.config['NODE_ID']}"))

    with app.app_context():
        camas = Cama.query.filter_by(id_sala=app.config['NODE_ID']).all()

        if not camas:
            console.print("\n[yellow]No hay camas registradas[/yellow]")
            pause()
            return

        table = Table(show_header=True, header_style="bold magenta", title=f"Total: {len(camas)} camas")
        table.add_column("Número", justify="center", width=10)
        table.add_column("Estado", justify="center", width=12)
        table.add_column("Paciente", style="yellow", width=30)
        table.add_column("ID Paciente", justify="center", width=12)

        for cama in camas:
            estado = "Ocupada" if cama.ocupada else "Libre"
            estado_color = "red" if cama.ocupada else "green"
            paciente_nombre = cama.paciente_actual.nombre if cama.paciente_actual else "-"
            id_pac = str(cama.id_paciente) if cama.id_paciente else "-"

            table.add_row(
                str(cama.numero),
                f"[{estado_color}]{estado}[/]",
                paciente_nombre,
                id_pac
            )

        console.print(table)
        pause()

def show_social_workers(app):
    """
    Show all social workers in the system.
    Migrated from 'Primer entregable.py' ver_trabajadores_sociales().

    Args:
        app: Flask application
    """
    clear_screen()
    console.print(create_header("Lista de Trabajadores Sociales"))

    with app.app_context():
        trabajadores = TrabajadorSocial.query.filter_by(activo=True).all()

        if not trabajadores:
            console.print("\n[yellow]No hay trabajadores sociales registrados[/yellow]")
            pause()
            return

        table = Table(show_header=True, header_style="bold magenta", title=f"Total: {len(trabajadores)} trabajadores")
        table.add_column("ID", justify="center", width=6)
        table.add_column("Nombre", style="green", width=30)
        table.add_column("Sala", justify="center", width=8)
        table.add_column("Estado", justify="center", width=12)

        for ts in trabajadores:
            estado = "Activo" if ts.activo else "Inactivo"
            estado_color = "green" if ts.activo else "red"
            table.add_row(
                str(ts.id_trabajador),
                ts.nombre,
                str(ts.id_sala),
                f"[{estado_color}]{estado}[/]"
            )

        console.print(table)
        pause()


def show_patient_visits(app, user):
    """
    Show visits for current patient (all states).

    Args:
        app: Flask application
        user: Current logged-in user (paciente)
    """
    clear_screen()
    console.print(create_header("Mis Visitas de Emergencia"))

    with app.app_context():
        visitas = VisitaEmergencia.query.filter_by(
            id_paciente=user.id_relacionado
        ).order_by(VisitaEmergencia.timestamp.desc()).limit(50).all()

        if not visitas:
            console.print("\n[yellow]No tiene visitas registradas[/yellow]")
            pause()
            return

        # Create table
        table = Table(show_header=True, header_style="bold magenta", title=f"Total: {len(visitas)} visitas")
        table.add_column("Folio", style="cyan", width=20)
        table.add_column("Doctor", style="blue", width=25)
        table.add_column("Síntomas", style="white", width=35)
        table.add_column("Estado", width=12)
        table.add_column("Fecha", style="yellow", width=16)

        for v in visitas:
            color = status_color(v.estado)
            table.add_row(
                v.folio,
                truncate_text(v.doctor.nombre, 23),
                truncate_text(v.sintomas, 33),
                f"[{color}]{v.estado}[/]",
                format_datetime(v.timestamp)
            )

        console.print(table)
        pause()
