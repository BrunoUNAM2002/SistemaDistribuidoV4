#!/usr/bin/env python3
"""
Script de prueba para verificar el descubrimiento dinámico de nodos.
No requiere login interactivo.
"""
import sys
import time
import logging
import threading
import os
from app_factory import create_app
from bully import BullyNode
from config import Config
from rich.console import Console

console = Console()

def run_node(node_id, duration=60):
    """Ejecuta un nodo por un tiempo determinado sin login."""

    # Configurar entorno
    os.environ['NODE_ID'] = str(node_id)

    # Crear app Flask
    app = create_app()

    # Setup logging
    logging.basicConfig(
        level=logging.INFO,
        format=f'[Node-{node_id}] [%(levelname)s] %(message)s'
    )
    logger = logging.getLogger(__name__)

    console.print(f"\n[bold cyan]═══ Nodo {node_id} Iniciando ═══[/bold cyan]")

    # Get cluster configuration
    cluster_nodes = {}
    for nodo_info in Config.OTROS_NODOS:
        if nodo_info['id'] != node_id:
            cluster_nodes[nodo_info['id']] = (
                'localhost',
                nodo_info['tcp_port'],
                6000 + nodo_info['id'] - 1
            )

    # Iniciar Bully
    bully_manager = BullyNode(
        node_id=node_id,
        cluster_nodes=cluster_nodes,
        tcp_port=5555 + node_id - 1,
        udp_port=6000 + node_id - 1
    )
    bully_manager.start()

    console.print(f"[green]✓[/green] Nodo {node_id} iniciado (TCP:{5555 + node_id - 1}, UDP:{6000 + node_id - 1})")

    # Esperar y monitorear
    start_time = time.time()
    last_status_time = 0

    while time.time() - start_time < duration:
        # Imprimir estado cada 5 segundos
        if time.time() - last_status_time > 5:
            is_leader = bully_manager.is_leader()
            current_leader = bully_manager.get_current_leader()
            state = bully_manager.state.value

            if is_leader:
                console.print(f"[bold green]Nodo {node_id}: LÍDER 👑[/bold green]")
            else:
                console.print(f"[yellow]Nodo {node_id}: {state}, Líder actual: Nodo {current_leader}[/yellow]")

            last_status_time = time.time()

        time.sleep(1)

    # Cleanup
    console.print(f"[dim]Deteniendo Nodo {node_id}...[/dim]")
    bully_manager.stop()
    console.print(f"[green]✓[/green] Nodo {node_id} detenido")

    return bully_manager.get_current_leader()

def test_scenario_1():
    """Escenario 1: Iniciar 3 nodos, luego agregar el 4to."""
    console.print("\n[bold magenta]═════════════════════════════════════════════[/bold magenta]")
    console.print("[bold magenta] ESCENARIO 1: DESCUBRIMIENTO DINÁMICO[/bold magenta]")
    console.print("[bold magenta]═════════════════════════════════════════════[/bold magenta]\n")

    console.print("📍 [bold]PASO 1:[/bold] Iniciando nodos 1, 2 y 3...")

    # Iniciar nodos 1, 2, 3 en threads
    threads = []
    for node_id in [1, 2, 3]:
        t = threading.Thread(target=run_node, args=(node_id, 30))
        t.daemon = True
        t.start()
        threads.append(t)
        time.sleep(0.5)  # Pequeña pausa entre inicios

    # Esperar a que se estabilice
    console.print("\n⏳ Esperando 15 segundos para que el cluster se estabilice...")
    time.sleep(15)

    console.print("\n[bold cyan]El Nodo 3 debería ser el líder ahora.[/bold cyan]")

    console.print("\n📍 [bold]PASO 2:[/bold] Agregando Nodo 4 (ID más alto)...")

    # Iniciar nodo 4
    t4 = threading.Thread(target=run_node, args=(4, 15))
    t4.daemon = True
    t4.start()

    console.print("\n⏳ Esperando 15 segundos para observar el descubrimiento...")
    time.sleep(15)

    console.print("\n[bold green]═══ RESULTADO ESPERADO ═══[/bold green]")
    console.print("✓ Nodo 4 debería descubrir que Nodo 3 es líder")
    console.print("✓ Nodo 4 debería iniciar elección porque tiene ID mayor")
    console.print("✓ Nodo 4 debería convertirse en el nuevo líder")
    console.print("✓ Todos los nodos deberían reconocer a Nodo 4 como líder\n")

def test_scenario_2():
    """Escenario 2: Iniciar todos juntos."""
    console.print("\n[bold magenta]═════════════════════════════════════════════[/bold magenta]")
    console.print("[bold magenta] ESCENARIO 2: INICIO SIMULTÁNEO[/bold magenta]")
    console.print("[bold magenta]═════════════════════════════════════════════[/bold magenta]\n")

    console.print("📍 Iniciando todos los nodos simultáneamente...")

    threads = []
    for node_id in [1, 2, 3, 4]:
        t = threading.Thread(target=run_node, args=(node_id, 20))
        t.daemon = True
        t.start()
        threads.append(t)
        time.sleep(0.1)  # Muy pequeña pausa

    console.print("\n⏳ Esperando 20 segundos...")
    time.sleep(20)

    console.print("\n[bold green]═══ RESULTADO ESPERADO ═══[/bold green]")
    console.print("✓ Solo el Nodo 4 debería ser líder")
    console.print("✓ No debería haber split-brain\n")

if __name__ == "__main__":
    # Limpiar primero
    os.system("pkill -9 -f 'python3.*main.py' 2>/dev/null")
    time.sleep(1)

    if len(sys.argv) > 1 and sys.argv[1] == "2":
        test_scenario_2()
    else:
        test_scenario_1()

    console.print("\n[bold green]✅ Prueba completada[/bold green]\n")