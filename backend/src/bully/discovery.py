"""
Módulo de descubrimiento dinámico de nodos via multicast UDP.

Permite que los nodos se descubran automáticamente en la red sin
configuración previa. Ideal para clusters dinámicos donde los nodos
pueden unirse/salir en cualquier momento.
"""
import socket
import struct
import threading
import time
import json
import logging
from typing import Dict, Callable, Tuple, Optional

logger = logging.getLogger(__name__)


class NodeDiscovery:
    """
    Maneja el descubrimiento automático de nodos usando multicast UDP.

    Protocolo:
    - ANNOUNCE: Nodo anuncia su presencia periódicamente
    - NODE_INFO: Respuesta con información del nodo (IP, puertos, ID)
    - HEARTBEAT: Confirmación de que el nodo sigue activo
    """

    def __init__(
        self,
        node_id: int,
        tcp_port: int,
        udp_port: int,
        multicast_group: str = '224.0.0.100',
        multicast_port: int = 5005,
        announce_interval: int = 5,
        node_timeout: int = 15
    ):
        """
        Inicializa el módulo de descubrimiento.

        Args:
            node_id: ID único del nodo
            tcp_port: Puerto TCP para mensajes Bully
            udp_port: Puerto UDP para heartbeats
            multicast_group: Grupo multicast para descubrimiento
            multicast_port: Puerto multicast
            announce_interval: Intervalo entre anuncios (segundos)
            node_timeout: Tiempo para considerar nodo muerto (segundos)
        """
        self.node_id = node_id
        self.tcp_port = tcp_port
        self.udp_port = udp_port
        self.multicast_group = multicast_group
        self.multicast_port = multicast_port
        self.announce_interval = announce_interval
        self.node_timeout = node_timeout

        # Diccionario de nodos descubiertos: {node_id: {'host': ip, 'tcp_port': ..., 'udp_port': ..., 'last_seen': timestamp}}
        self.discovered_nodes: Dict[int, dict] = {}
        self.lock = threading.Lock()

        # Sockets
        self.send_socket: Optional[socket.socket] = None
        self.recv_socket: Optional[socket.socket] = None

        # Control de threads
        self.running = False
        self.announce_thread: Optional[threading.Thread] = None
        self.listen_thread: Optional[threading.Thread] = None
        self.cleanup_thread: Optional[threading.Thread] = None

        # Callbacks
        self.on_node_discovered: Optional[Callable] = None
        self.on_node_lost: Optional[Callable] = None
        self.on_id_collision: Optional[Callable] = None  # Callback para colisión de IDs

        logger.info(f"[Node-{self.node_id}] [DISCOVERY] Initialized (multicast: {multicast_group}:{multicast_port})")

    def start(self):
        """Inicia el servicio de descubrimiento."""
        if self.running:
            logger.warning(f"[Node-{self.node_id}] [DISCOVERY] Already running")
            return

        self.running = True

        # Crear socket de envío (multicast)
        self.send_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
        self.send_socket.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 2)

        # Crear socket de recepción (multicast)
        self.recv_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
        self.recv_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

        # En macOS/BSD, también necesitamos SO_REUSEPORT para multicast
        try:
            self.recv_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
        except AttributeError:
            # SO_REUSEPORT no está disponible en todos los sistemas
            pass

        # Bind al puerto multicast
        self.recv_socket.bind(('', self.multicast_port))

        # Unirse al grupo multicast
        mreq = struct.pack("4sl", socket.inet_aton(self.multicast_group), socket.INADDR_ANY)
        self.recv_socket.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, mreq)

        # Iniciar threads
        self.announce_thread = threading.Thread(target=self._announce_loop, daemon=True)
        self.listen_thread = threading.Thread(target=self._listen_loop, daemon=True)
        self.cleanup_thread = threading.Thread(target=self._cleanup_loop, daemon=True)

        self.announce_thread.start()
        self.listen_thread.start()
        self.cleanup_thread.start()

        logger.info(f"[Node-{self.node_id}] [DISCOVERY] Service started")

    def stop(self):
        """Detiene el servicio de descubrimiento."""
        if not self.running:
            return

        logger.info(f"[Node-{self.node_id}] [DISCOVERY] Stopping service...")
        self.running = False

        # Enviar mensaje de salida
        self._send_leave_message()

        # Cerrar sockets
        if self.send_socket:
            self.send_socket.close()
        if self.recv_socket:
            self.recv_socket.close()

        logger.info(f"[Node-{self.node_id}] [DISCOVERY] Service stopped")

    def _announce_loop(self):
        """Thread que anuncia presencia periódicamente."""
        logger.info(f"[Node-{self.node_id}] [DISCOVERY] Announce thread started")

        while self.running:
            try:
                self._send_announce()
                time.sleep(self.announce_interval)
            except Exception as e:
                logger.error(f"[Node-{self.node_id}] [DISCOVERY] Error in announce loop: {e}")

    def _listen_loop(self):
        """Thread que escucha mensajes multicast."""
        logger.info(f"[Node-{self.node_id}] [DISCOVERY] Listen thread started")
        self.recv_socket.settimeout(1.0)  # Timeout para poder verificar self.running

        while self.running:
            try:
                data, addr = self.recv_socket.recvfrom(1024)
                self._handle_message(data, addr)
            except socket.timeout:
                continue
            except Exception as e:
                if self.running:
                    logger.error(f"[Node-{self.node_id}] [DISCOVERY] Error in listen loop: {e}")

    def _cleanup_loop(self):
        """Thread que limpia nodos inactivos."""
        logger.info(f"[Node-{self.node_id}] [DISCOVERY] Cleanup thread started")

        while self.running:
            try:
                current_time = time.time()
                nodes_to_remove = []

                with self.lock:
                    for node_id, info in self.discovered_nodes.items():
                        time_since_seen = current_time - info['last_seen']
                        if time_since_seen > self.node_timeout:
                            nodes_to_remove.append(node_id)
                            logger.warning(f"[Node-{self.node_id}] [DISCOVERY] Node {node_id} timeout ({time_since_seen:.1f}s)")

                # Remover nodos muertos
                for node_id in nodes_to_remove:
                    self._remove_node(node_id)

                time.sleep(self.announce_interval)
            except Exception as e:
                logger.error(f"[Node-{self.node_id}] [DISCOVERY] Error in cleanup loop: {e}")

    def _send_announce(self):
        """Envía mensaje ANNOUNCE por multicast."""
        message = {
            'type': 'ANNOUNCE',
            'node_id': self.node_id,
            'tcp_port': self.tcp_port,
            'udp_port': self.udp_port,
            'timestamp': time.time()
        }

        data = json.dumps(message).encode('utf-8')
        self.send_socket.sendto(data, (self.multicast_group, self.multicast_port))
        logger.debug(f"[Node-{self.node_id}] [DISCOVERY] Sent ANNOUNCE")

    def _send_leave_message(self):
        """Envía mensaje LEAVE al salir."""
        message = {
            'type': 'LEAVE',
            'node_id': self.node_id,
            'timestamp': time.time()
        }

        try:
            data = json.dumps(message).encode('utf-8')
            self.send_socket.sendto(data, (self.multicast_group, self.multicast_port))
            logger.info(f"[Node-{self.node_id}] [DISCOVERY] Sent LEAVE message")
        except Exception as e:
            logger.error(f"[Node-{self.node_id}] [DISCOVERY] Error sending LEAVE: {e}")

    def _handle_message(self, data: bytes, addr: Tuple[str, int]):
        """Procesa mensaje recibido."""
        try:
            message = json.loads(data.decode('utf-8'))
            msg_type = message.get('type')
            sender_id = message.get('node_id')

            # Detectar colisión de ID: otro nodo con mi mismo ID
            if sender_id == self.node_id:
                sender_ip = addr[0]

                # Verificar si no es un mensaje de loopback (mismo host)
                import socket as sock
                my_ip = sock.gethostbyname(sock.gethostname())

                # Si es diferente IP o puerto, hay colisión
                if sender_ip != my_ip and sender_ip != '127.0.0.1':
                    logger.warning(f"[Node-{self.node_id}] [DISCOVERY] ⚠️  ID COLLISION detected! Node {sender_id} at {sender_ip}")

                    # Notificar callback de colisión
                    if self.on_id_collision:
                        threading.Thread(
                            target=self.on_id_collision,
                            args=(sender_id, sender_ip),
                            daemon=True
                        ).start()

                # Ignorar el mensaje (no procesarlo como nodo diferente)
                return

            if msg_type == 'ANNOUNCE':
                self._handle_announce(message, addr)
            elif msg_type == 'LEAVE':
                self._handle_leave(message)
            else:
                logger.debug(f"[Node-{self.node_id}] [DISCOVERY] Unknown message type: {msg_type}")

        except Exception as e:
            logger.error(f"[Node-{self.node_id}] [DISCOVERY] Error handling message: {e}")

    def _handle_announce(self, message: dict, addr: Tuple[str, int]):
        """Maneja mensaje ANNOUNCE de otro nodo."""
        sender_id = message['node_id']
        tcp_port = message['tcp_port']
        udp_port = message['udp_port']
        sender_ip = addr[0]

        with self.lock:
            is_new = sender_id not in self.discovered_nodes

            self.discovered_nodes[sender_id] = {
                'host': sender_ip,
                'tcp_port': tcp_port,
                'udp_port': udp_port,
                'last_seen': time.time()
            }

            if is_new:
                logger.info(f"[Node-{self.node_id}] [DISCOVERY] ✓ Discovered new node {sender_id} at {sender_ip}:{tcp_port}")

                # Notificar callback
                if self.on_node_discovered:
                    threading.Thread(
                        target=self.on_node_discovered,
                        args=(sender_id, sender_ip, tcp_port, udp_port),
                        daemon=True
                    ).start()
            else:
                logger.debug(f"[Node-{self.node_id}] [DISCOVERY] Updated node {sender_id}")

    def _handle_leave(self, message: dict):
        """Maneja mensaje LEAVE de nodo que sale gracefully."""
        sender_id = message['node_id']
        logger.info(f"[Node-{self.node_id}] [DISCOVERY] Node {sender_id} left gracefully")
        self._remove_node(sender_id)

    def _remove_node(self, node_id: int):
        """Remueve nodo de la lista de descubiertos."""
        with self.lock:
            if node_id in self.discovered_nodes:
                node_info = self.discovered_nodes.pop(node_id)
                logger.warning(f"[Node-{self.node_id}] [DISCOVERY] ✗ Removed node {node_id} (was at {node_info['host']})")

                # Notificar callback
                if self.on_node_lost:
                    threading.Thread(
                        target=self.on_node_lost,
                        args=(node_id,),
                        daemon=True
                    ).start()

    def get_discovered_nodes(self) -> Dict[int, Tuple[str, int, int]]:
        """
        Retorna nodos descubiertos en formato compatible con BullyNode.

        Returns:
            Dict con formato: {node_id: (host, tcp_port, udp_port)}
        """
        with self.lock:
            return {
                node_id: (info['host'], info['tcp_port'], info['udp_port'])
                for node_id, info in self.discovered_nodes.items()
            }

    def get_node_count(self) -> int:
        """Retorna número de nodos descubiertos (excluyendo este nodo)."""
        with self.lock:
            return len(self.discovered_nodes)

    def set_callbacks(self, on_discovered: Callable = None, on_lost: Callable = None, on_collision: Callable = None):
        """
        Configura callbacks para eventos de descubrimiento.

        Args:
            on_discovered: Callback cuando se descubre nuevo nodo (node_id, host, tcp_port, udp_port)
            on_lost: Callback cuando se pierde un nodo (node_id)
            on_collision: Callback cuando se detecta colisión de ID (conflicting_node_id, conflicting_host)
        """
        self.on_node_discovered = on_discovered
        self.on_node_lost = on_lost
        self.on_id_collision = on_collision
