"""
Console actions for write operations (create/close visits).
All actions that modify data with proper validation.
"""
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from datetime import datetime
from models import (
    db, Paciente, Doctor, Cama, TrabajadorSocial, VisitaEmergencia,
    get_leader_flask_url, replicate_visit_to_cluster
)
import requests
from console.ui import (
    create_header, show_success, show_error, show_warning, show_info,
    get_text_input, get_int_input, confirm_action, pause, clear_screen
)

console = Console()


def create_visit(app, bully_manager, user):
    """
    Create a new emergency visit (DISTRIBUTED operation).

    Flow:
    - If node is LEADER: create locally + replicate to all nodes
    - If node is FOLLOWER: send request to leader, leader coordinates

    Args:
        app: Flask application
        bully_manager: BullyNode instance
        user: Current logged-in user

    Returns:
        bool: True if visit created successfully, False otherwise
    """
    clear_screen()
    console.print(create_header("Crear Nueva Visita de Emergencia"))

    # Check if we're the leader
    is_leader = bully_manager.is_leader()

    if is_leader:
        console.print("[green]✓[/green] Nodo líder - Procesando creación con exclusión mutua\n")
    else:
        leader_id = bully_manager.get_current_leader()
        console.print(f"[cyan]ℹ[/cyan] Nodo follower - Enviando solicitud al líder (Nodo {leader_id})\n")

    try:
        with app.app_context():
            # Step 1: Get or create patient
            console.print("[bold cyan]PASO 1: Datos del Paciente[/bold cyan]\n")

            curp = get_text_input("CURP del paciente (18 caracteres, ENTER para omitir)", default="").upper()

            paciente = None
            if curp and len(curp) == 18:
                # Search existing patient by CURP
                paciente = Paciente.query.filter_by(curp=curp, activo=1).first()

                if paciente:
                    console.print(f"\n[green]✓[/green] Paciente encontrado: [bold]{paciente.nombre}[/bold]")
                    console.print(f"   Edad: {paciente.edad or 'N/A'} | Sexo: {paciente.sexo or 'N/A'}")

                    if not confirm_action("¿Usar este paciente?", default=True):
                        paciente = None

            # Create new patient if not found
            if not paciente:
                console.print("\n[yellow]Registrando nuevo paciente...[/yellow]\n")

                nombre = get_text_input("Nombre completo")

                edad_str = get_text_input("Edad (ENTER para omitir)", default="")
                edad = int(edad_str) if edad_str.strip() else None

                sexo = get_text_input("Sexo (M/F, ENTER para omitir)", default="").upper()
                if sexo and sexo not in ['M', 'F']:
                    sexo = None

                telefono = get_text_input("Teléfono (ENTER para omitir)", default="")
                contacto_emergencia = get_text_input("Contacto de emergencia (ENTER para omitir)", default="")

                # Create patient record
                paciente = Paciente(
                    nombre=nombre,
                    edad=edad,
                    sexo=sexo or None,
                    curp=curp if curp else None,
                    telefono=telefono if telefono else None,
                    contacto_emergencia=contacto_emergencia if contacto_emergencia else None,
                    activo=1
                )
                db.session.add(paciente)
                db.session.flush()  # Get ID without committing

                console.print(f"\n[green]✓[/green] Paciente registrado: {paciente.nombre}")

            # Step 2: Get symptoms
            console.print("\n[bold cyan]PASO 2: Síntomas y Motivo de Consulta[/bold cyan]\n")
            sintomas = get_text_input("Describa los síntomas")

            # Step 3: Select available doctor
            console.print("\n[bold cyan]PASO 3: Asignación de Doctor[/bold cyan]\n")

            doctores = Doctor.query.filter_by(
                id_sala=app.config['NODE_ID'],
                disponible=True,
                activo=True
            ).all()

            if not doctores:
                show_error("No hay doctores disponibles en esta sala")
                db.session.rollback()
                pause()
                return False

            # Display available doctors
            table_doc = Table(show_header=True, header_style="bold magenta")
            table_doc.add_column("#", justify="center", width=6)
            table_doc.add_column("ID", justify="center", width=6)
            table_doc.add_column("Nombre", style="green", width=30)
            table_doc.add_column("Especialidad", style="cyan", width=25)

            for idx, doc in enumerate(doctores, 1):
                table_doc.add_row(
                    str(idx),
                    str(doc.id_doctor),
                    doc.nombre,
                    doc.especialidad or "General"
                )

            console.print(table_doc)

            doc_choice = get_int_input(
                f"\nSeleccione doctor (1-{len(doctores)})",
                choices=list(range(1, len(doctores) + 1))
            )
            doctor = doctores[doc_choice - 1]

            console.print(f"[green]✓[/green] Doctor asignado: {doctor.nombre}")

            # Step 4: Select available bed
            console.print("\n[bold cyan]PASO 4: Asignación de Cama[/bold cyan]\n")

            camas = Cama.query.filter_by(
                id_sala=app.config['NODE_ID'],
                ocupada=False
            ).all()

            if not camas:
                show_error("No hay camas disponibles en esta sala")
                db.session.rollback()
                pause()
                return False

            # Display available beds
            table_camas = Table(show_header=True, header_style="bold magenta")
            table_camas.add_column("#", justify="center", width=6)
            table_camas.add_column("Número de Cama", justify="center", width=20)
            table_camas.add_column("Estado", style="green", width=15)

            for idx, cama in enumerate(camas, 1):
                table_camas.add_row(
                    str(idx),
                    str(cama.numero),
                    "Libre"
                )

            console.print(table_camas)

            cama_choice = get_int_input(
                f"\nSeleccione cama (1-{len(camas)})",
                choices=list(range(1, len(camas) + 1))
            )
            cama = camas[cama_choice - 1]

            console.print(f"[green]✓[/green] Cama asignada: #{cama.numero}")

            # Step 5: Select trabajador social
            console.print("\n[bold cyan]PASO 5: Asignación de Trabajador Social[/bold cyan]\n")

            trabajadores = TrabajadorSocial.query.filter_by(
                id_sala=app.config['NODE_ID'],
                activo=True
            ).all()

            if not trabajadores:
                show_error("No hay trabajadores sociales disponibles en esta sala")
                db.session.rollback()
                pause()
                return False

            # Display trabajadores
            table_ts = Table(show_header=True, header_style="bold magenta")
            table_ts.add_column("#", justify="center", width=6)
            table_ts.add_column("ID", justify="center", width=6)
            table_ts.add_column("Nombre", style="green", width=30)

            for idx, ts in enumerate(trabajadores, 1):
                table_ts.add_row(
                    str(idx),
                    str(ts.id_trabajador),
                    ts.nombre
                )

            console.print(table_ts)

            ts_choice = get_int_input(
                f"\nSeleccione trabajador social (1-{len(trabajadores)})",
                choices=list(range(1, len(trabajadores) + 1))
            )
            trabajador = trabajadores[ts_choice - 1]

            console.print(f"[green]✓[/green] Trabajador social asignado: {trabajador.nombre}")

            # Step 6: Confirmation
            console.print("\n[bold cyan]RESUMEN DE LA VISITA[/bold cyan]\n")

            summary = f"""
[bold]Paciente:[/bold] {paciente.nombre}
[bold]CURP:[/bold] {paciente.curp or 'No registrado'}
[bold]Síntomas:[/bold] {sintomas}
[bold]Doctor:[/bold] {doctor.nombre} ({doctor.especialidad or 'General'})
[bold]Cama:[/bold] #{cama.numero}
[bold]Trabajador Social:[/bold] {trabajador.nombre}
[bold]Sala:[/bold] {app.config['NODE_ID']}
            """

            console.print(Panel(summary, border_style="cyan", title="Confirmar Datos"))

            if not confirm_action("\n¿Crear visita de emergencia?", default=True):
                console.print("[yellow]Operación cancelada[/yellow]")
                db.session.rollback()
                pause()
                return False

            # ============================================================
            # DISTRIBUTED LOGIC: Leader vs Follower
            # ============================================================

            if is_leader:
                # LEADER PATH: Create locally + replicate
                console.print("\n[cyan]→[/cyan] Creando visita en nodo líder...")

                visita = VisitaEmergencia(
                    id_paciente=paciente.id_paciente,
                    id_doctor=doctor.id_doctor,
                    id_cama=cama.id_cama,
                    id_trabajador=trabajador.id_trabajador,
                    id_sala=app.config['NODE_ID'],
                    sintomas=sintomas,
                    estado='activa',
                    timestamp=datetime.utcnow()
                )

                db.session.add(visita)

                # Update resources
                cama.ocupada = True
                cama.id_paciente = paciente.id_paciente
                doctor.disponible = False

                db.session.commit()
                db.session.refresh(visita)

                console.print(f"[green]✓[/green] Visita creada localmente: [cyan]{visita.folio}[/cyan]")

                # Replicate to all nodes
                console.print("[cyan]→[/cyan] Replicando a todos los nodos del cluster...")

                visita_data = {
                    'folio': visita.folio,
                    'id_paciente': visita.id_paciente,
                    'id_doctor': visita.id_doctor,
                    'id_cama': visita.id_cama,
                    'id_trabajador': visita.id_trabajador,
                    'id_sala': visita.id_sala,
                    'sintomas': visita.sintomas,
                    'diagnostico': visita.diagnostico,
                    'estado': visita.estado,
                    'timestamp': visita.timestamp.isoformat() if visita.timestamp else None,
                    'fecha_cierre': visita.fecha_cierre.isoformat() if visita.fecha_cierre else None
                }

                replication_result = replicate_visit_to_cluster(
                    bully_manager,
                    visita_data,
                    exclude_node_id=app.config['NODE_ID']
                )

                console.print(f"[green]✓[/green] Replicación: {replication_result['success_count']}/{replication_result['total_nodes']} nodos")

                # Show success
                console.print("\n")
                console.print(Panel(
                    f"[bold green]✓ VISITA CREADA Y REPLICADA EXITOSAMENTE[/bold green]\n\n"
                    f"[bold]Folio:[/bold] [cyan]{visita.folio}[/cyan]\n"
                    f"[bold]Paciente:[/bold] {paciente.nombre}\n"
                    f"[bold]Doctor:[/bold] {doctor.nombre}\n"
                    f"[bold]Cama:[/bold] #{cama.numero}\n"
                    f"[bold]Estado:[/bold] [green]Activa[/green]\n"
                    f"[bold]Replicado en:[/bold] {replication_result['success_count']} nodos",
                    border_style="green",
                    title="🏥 Visita Registrada (Líder)"
                ))

                pause()
                return True

            else:
                # FOLLOWER PATH: Send request to leader
                console.print("\n[cyan]→[/cyan] Enviando solicitud al nodo líder...")

                # Prepare request data
                request_data = {
                    'id_paciente': paciente.id_paciente,
                    'id_doctor': doctor.id_doctor,
                    'id_cama': cama.id_cama,
                    'id_trabajador': trabajador.id_trabajador,
                    'id_sala': app.config['NODE_ID'],
                    'sintomas': sintomas
                }

                # Get leader URL with retries
                max_retries = 3
                for attempt in range(max_retries):
                    try:
                        leader_id, leader_url = get_leader_flask_url(bully_manager)

                        if not leader_url:
                            show_error("No hay líder disponible")
                            db.session.rollback()
                            pause()
                            return False

                        # Send HTTP POST request to leader
                        endpoint = f"{leader_url}/api/cluster/create-visit"
                        response = requests.post(endpoint, json=request_data, timeout=10)

                        if response.ok:
                            result = response.json()

                            if result.get('success'):
                                folio = result.get('folio')

                                # Commit local paciente if it was created
                                db.session.commit()

                                # Show success
                                console.print("\n")
                                console.print(Panel(
                                    f"[bold green]✓ VISITA CREADA EXITOSAMENTE (VÍA LÍDER)[/bold green]\n\n"
                                    f"[bold]Folio:[/bold] [cyan]{folio}[/cyan]\n"
                                    f"[bold]Paciente:[/bold] {paciente.nombre}\n"
                                    f"[bold]Doctor:[/bold] {doctor.nombre}\n"
                                    f"[bold]Cama:[/bold] #{cama.numero}\n"
                                    f"[bold]Procesado por:[/bold] Nodo Líder {leader_id}\n"
                                    f"[bold]Estado:[/bold] [green]Activa y Replicada[/green]",
                                    border_style="green",
                                    title="🏥 Visita Registrada"
                                ))

                                pause()
                                return True
                            else:
                                error_msg = result.get('error', 'Unknown error')
                                show_error(f"El líder rechazó la solicitud: {error_msg}")
                                db.session.rollback()
                                pause()
                                return False

                        else:
                            # HTTP error
                            if attempt < max_retries - 1:
                                console.print(f"[yellow]⚠[/yellow] Error de conexión (intento {attempt + 1}/{max_retries}), reintentando...")
                                continue
                            else:
                                show_error(f"Error HTTP del líder: {response.status_code}")
                                db.session.rollback()
                                pause()
                                return False

                    except requests.exceptions.Timeout:
                        if attempt < max_retries - 1:
                            console.print(f"[yellow]⚠[/yellow] Timeout (intento {attempt + 1}/{max_retries}), reintentando...")
                            continue
                        else:
                            show_error("Timeout al conectar con el líder")
                            db.session.rollback()
                            pause()
                            return False

                    except requests.exceptions.ConnectionError:
                        if attempt < max_retries - 1:
                            console.print(f"[yellow]⚠[/yellow] Error de conexión (intento {attempt + 1}/{max_retries}), verificando líder...")
                            # Leader might have changed, get new leader in next iteration
                            continue
                        else:
                            show_error("No se pudo conectar con el nodo líder")
                            db.session.rollback()
                            pause()
                            return False

                    except Exception as e:
                        show_error(f"Error enviando solicitud al líder: {e}")
                        db.session.rollback()
                        pause()
                        return False

                # If we get here, all retries failed
                show_error("Falló después de múltiples intentos")
                db.session.rollback()
                pause()
                return False

    except ValueError as ve:
        show_error(f"Error en los datos ingresados: {ve}")
        db.session.rollback()
        pause()
        return False

    except Exception as e:
        show_error(f"Error al crear visita: {e}")
        db.session.rollback()
        pause()
        return False


def close_visit(app, user):
    """
    Close an active visit by adding diagnosis (Doctor only).

    Args:
        app: Flask application
        user: Current logged-in user

    Returns:
        bool: True if visit closed successfully, False otherwise
    """
    clear_screen()
    console.print(create_header("Cerrar Visita de Emergencia"))

    # Verify user is a doctor
    if user.rol != 'doctor':
        show_error("Solo los doctores pueden cerrar visitas")
        pause()
        return False

    try:
        with app.app_context():
            # Step 1: Show doctor's active visits
            visitas_activas = VisitaEmergencia.query.filter_by(
                id_doctor=user.id_relacionado,
                estado='activa'
            ).order_by(VisitaEmergencia.timestamp.desc()).all()

            if not visitas_activas:
                show_warning("No tiene visitas activas asignadas")
                pause()
                return False

            console.print(f"\n[bold]Sus visitas activas:[/bold] ({len(visitas_activas)})\n")

            # Display active visits
            table = Table(show_header=True, header_style="bold magenta")
            table.add_column("#", justify="center", width=6)
            table.add_column("Folio", style="cyan", width=20)
            table.add_column("Paciente", style="green", width=25)
            table.add_column("Síntomas", style="white", width=35)
            table.add_column("Cama", justify="center", width=8)

            for idx, v in enumerate(visitas_activas, 1):
                sintomas_short = v.sintomas[:32] + "..." if len(v.sintomas) > 35 else v.sintomas
                table.add_row(
                    str(idx),
                    v.folio,
                    v.paciente.nombre,
                    sintomas_short,
                    f"#{v.cama.numero}"
                )

            console.print(table)

            # Step 2: Select visit to close
            visit_choice = get_int_input(
                f"\n¿Qué visita desea cerrar? (1-{len(visitas_activas)})",
                choices=list(range(1, len(visitas_activas) + 1))
            )

            visita = visitas_activas[visit_choice - 1]

            # Step 3: Show visit details
            console.print("\n[bold cyan]DETALLES DE LA VISITA[/bold cyan]\n")

            details = f"""
[bold]Folio:[/bold] {visita.folio}
[bold]Paciente:[/bold] {visita.paciente.nombre}
[bold]CURP:[/bold] {visita.paciente.curp or 'No registrado'}
[bold]Edad:[/bold] {visita.paciente.edad or 'N/A'}
[bold]Síntomas:[/bold] {visita.sintomas}
[bold]Cama:[/bold] #{visita.cama.numero}
[bold]Hora Inicio:[/bold] {visita.timestamp.strftime('%Y-%m-%d %H:%M:%S')}
            """

            console.print(Panel(details, border_style="cyan"))

            # Step 4: Get diagnosis
            console.print("\n[bold cyan]DIAGNÓSTICO Y CIERRE[/bold cyan]\n")

            diagnostico = get_text_input("Ingrese el diagnóstico final")

            if not diagnostico.strip():
                show_error("El diagnóstico no puede estar vacío")
                pause()
                return False

            # Step 5: Confirmation
            if not confirm_action("\n¿Confirmar cierre de visita?", default=True):
                console.print("[yellow]Operación cancelada[/yellow]")
                pause()
                return False

            # Step 6: Update visit
            visita.diagnostico = diagnostico
            visita.estado = 'completada'
            visita.fecha_cierre = datetime.utcnow()

            # Free resources (doctor and bed)
            visita.doctor.disponible = True
            visita.cama.ocupada = False
            visita.cama.id_paciente = None

            # Commit transaction
            db.session.commit()

            # Success message
            console.print("\n")
            console.print(Panel(
                f"[bold green]✓ VISITA CERRADA EXITOSAMENTE[/bold green]\n\n"
                f"[bold]Folio:[/bold] [cyan]{visita.folio}[/cyan]\n"
                f"[bold]Paciente:[/bold] {visita.paciente.nombre}\n"
                f"[bold]Diagnóstico:[/bold] {diagnostico}\n"
                f"[bold]Duración:[/bold] {(visita.fecha_cierre - visita.timestamp).seconds // 60} minutos\n\n"
                f"[dim]Recursos liberados: Doctor disponible | Cama libre[/dim]",
                border_style="green",
                title="✅ Visita Completada"
            ))

            pause()
            return True

    except ValueError as ve:
        show_error(f"Error en los datos ingresados: {ve}")
        db.session.rollback()
        pause()
        return False

    except Exception as e:
        show_error(f"Error al cerrar visita: {e}")
        db.session.rollback()
        pause()
        return False


def assign_doctor_to_patient(app, bully_manager, user):
    """
    Quick doctor assignment to patient (simplified from Primer entregable).

    This is a simplified version of create_visit() focused on doctor assignment.
    Migrated from 'Primer entregable.py' asignar_doctor() function.

    Args:
        app: Flask application
        bully_manager: BullyNode instance
        user: Current logged-in user

    Returns:
        bool: True if assignment successful, False otherwise
    """
    clear_screen()
    console.print(create_header("Asignar Doctor a Paciente"))

    # Leader validation
    if not bully_manager.is_leader():
        leader_id = bully_manager.get_current_leader()
        console.print(Panel(
            f"[bold red]⚠ OPERACIÓN DENEGADA[/bold red]\n\n"
            f"Solo el nodo líder puede asignar doctores.\n\n"
            f"[yellow]Nodo actual:[/yellow] {app.config['NODE_ID']}\n"
            f"[green]Líder actual:[/green] Nodo {leader_id}",
            border_style="red",
            title="🔒 Validación de Líder"
        ))
        pause()
        return False

    try:
        with app.app_context():
            # Step 1: Select patient
            console.print("[bold cyan]PASO 1: Seleccionar Paciente[/bold cyan]\n")

            # Show available patients (with existing visits)
            visitas = VisitaEmergencia.query.filter_by(estado='activa').all()

            if not visitas:
                show_warning("No hay visitas activas para asignar doctor")
                pause()
                return False

            table = Table(show_header=True, header_style="bold magenta")
            table.add_column("ID Visita", width=10)
            table.add_column("Paciente", style="green", width=25)
            table.add_column("Doctor Actual", style="cyan", width=25)
            table.add_column("Folio", width=20)

            for v in visitas:
                table.add_row(
                    str(v.id_visita),
                    v.paciente.nombre,
                    v.doctor.nombre if v.doctor else "SIN ASIGNAR",
                    v.folio
                )

            console.print(table)
            console.print()

            id_visita = get_int_input("ID de la visita")

            visita = VisitaEmergencia.query.get(id_visita)
            if not visita or visita.estado != 'activa':
                show_error("Visita no encontrada o no está activa")
                pause()
                return False

            # Step 2: Select doctor
            console.print(f"\n[bold cyan]PASO 2: Seleccionar Doctor[/bold cyan]\n")

            doctores = Doctor.query.filter_by(
                id_sala=app.config['NODE_ID'],
                activo=True
            ).all()

            if not doctores:
                show_error("No hay doctores en esta sala")
                pause()
                return False

            table_doc = Table(show_header=True, header_style="bold magenta")
            table_doc.add_column("ID", width=6)
            table_doc.add_column("Nombre", style="green", width=30)
            table_doc.add_column("Especialidad", style="cyan", width=20)
            table_doc.add_column("Disponible", justify="center", width=12)

            for doc in doctores:
                estado = "✅ Sí" if doc.disponible else "❌ No"
                estado_color = "green" if doc.disponible else "red"
                table_doc.add_row(
                    str(doc.id_doctor),
                    doc.nombre,
                    doc.especialidad or "General",
                    f"[{estado_color}]{estado}[/]"
                )

            console.print(table_doc)
            console.print()

            id_doctor = get_int_input("ID del doctor")

            doctor = Doctor.query.get(id_doctor)
            if not doctor or not doctor.activo:
                show_error("Doctor no encontrado o inactivo")
                pause()
                return False

            # Validation: Check doctor availability (like Primer entregable)
            if not doctor.disponible:
                show_warning(f"⚠️  {doctor.nombre} está OCUPADO")
                if not confirm_action("¿Asignar de todas formas?", default=False):
                    console.print("[yellow]Operación cancelada[/yellow]")
                    pause()
                    return False

            # Step 3: Confirm and assign
            console.print(f"\n[bold]Resumen:[/bold]")
            console.print(f"  Paciente: [green]{visita.paciente.nombre}[/green]")
            console.print(f"  Doctor: [cyan]{doctor.nombre}[/cyan] ({doctor.especialidad or 'General'})")
            console.print()

            if not confirm_action("¿Confirmar asignación?", default=True):
                console.print("[yellow]Operación cancelada[/yellow]")
                pause()
                return False

            # Perform assignment (free old doctor if exists, assign new one)
            if visita.doctor and visita.doctor.id_doctor != doctor.id_doctor:
                visita.doctor.disponible = True

            visita.id_doctor = doctor.id_doctor
            visita.estado = 'En Consulta'  # Like Primer entregable
            doctor.disponible = False

            db.session.commit()

            show_success(f"Doctor {doctor.nombre} asignado a {visita.paciente.nombre}")
            pause()
            return True

    except Exception as e:
        show_error(f"Error en asignación: {e}")
        db.session.rollback()
        pause()
        return False
