#!/usr/bin/env python3
"""
Script de prueba para nodos Bully sin interfaz de consola interactiva.
Se usa para testing automatizado del sistema de descubrimiento dinámico.
"""
import signal
import sys
import logging
import logging.handlers
import os
import time
from app_factory import create_app
from bully import BullyNode
from config import Config

# Setup graceful shutdown
running = True

def signal_handler(signum, frame):
    global running
    print(f"\n[Node-{Config.NODE_ID}] Cerrando gracefully...")
    running = False

signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)

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


def main():
    """Main entry point"""
    global running

    # Initialize NODE_ID (auto-generate if not specified)
    from config import Config
    node_id = Config.initialize_node_id()

    # Create Flask app (for DB access, no web server)
    app = create_app()

    # Setup logging
    setup_logging(node_id)
    logger = logging.getLogger(__name__)

    # Mostrar si el ID fue auto-generado
    id_source = "auto-generado" if Config.is_node_id_auto_generated() else "manual"

    print(f"═══════════════════════════════════════════════════════════")
    print(f"  Nodo {node_id} ({id_source}) - Modo de Prueba")
    print(f"═══════════════════════════════════════════════════════════")

    # Initialize Bully system
    logger.info("Initializing Bully node")

    if Config.is_dynamic_mode():
        # MODO DINÁMICO: Auto-descubrimiento via multicast
        print(f"[Node-{node_id}] Modo dinámico: Auto-descubrimiento")
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
        print(f"[Node-{node_id}] ✓ Buscando otros nodos en la red...")

    else:
        # MODO ESTÁTICO: Lista fija de nodos
        print(f"[Node-{node_id}] Modo estático: Lista fija de nodos")
        logger.info("Using STATIC mode - fixed cluster_nodes")

        cluster_nodes = {}
        for nodo_info in Config.OTROS_NODOS:
            if nodo_info['id'] != node_id:
                cluster_nodes[nodo_info['id']] = (
                    'localhost',
                    nodo_info['tcp_port'],
                    6000 + nodo_info['id'] - 1
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

    print(f"[Node-{node_id}] ✓ Sistema iniciado")
    print(f"[Node-{node_id}] Presiona Ctrl+C para detener")
    print("")

    # Main loop - just keep alive
    try:
        while running:
            time.sleep(1)

            # Log status every 30 seconds
            if int(time.time()) % 30 == 0:
                state = bully_manager.get_state()
                leader = bully_manager.get_current_leader()
                nodes_count = len(bully_manager.cluster_nodes)
                print(f"[Node-{node_id}] Estado: {state} | Líder: Nodo {leader} | Nodos conocidos: {nodes_count}")

    except KeyboardInterrupt:
        pass
    finally:
        # Cleanup
        print(f"\n[Node-{node_id}] Deteniendo sistema Bully...")
        bully_manager.stop()
        logger.info("Bully system stopped")
        print(f"[Node-{node_id}] ✓ Sistema cerrado correctamente")


if __name__ == '__main__':
    main()
