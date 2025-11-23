# backend/bully_simple/bully_node.py

import time
import threading
import logging
from enum import Enum
from typing import Dict, Optional
from .communication import CommunicationManager, Message
from .discovery import NodeDiscovery

logger = logging.getLogger(__name__)

class NodeState(Enum):
    """Estados posibles del nodo"""
    FOLLOWER = "follower"
    LEADER = "leader"

class BullyNode:
    """
    Implementación simplificada del algoritmo Bully.
    
    Algoritmo:
    1. Cada nodo tiene un ID único
    2. Nodo con mayor ID es el líder
    3. Si líder falla (no heartbeat), iniciar elección
    4. En elección: enviar ELECTION a nodos con ID mayor
    5. Si alguien responde OK → esperar COORDINATOR
    6. Si nadie responde → declararse líder
    """
    
    def __init__(self, node_id: int, cluster_nodes: Dict[int, tuple] = None,
                 tcp_port: int = None, udp_port: int = None,
                 use_discovery: bool = False,
                 multicast_group: str = '224.0.0.100',
                 multicast_port: int = 5005):
        """
        Inicializa nodo Bully.

        Args:
            node_id: ID de este nodo
            cluster_nodes: {node_id: (ip, tcp_port, udp_port)} (DEPRECATED - modo estático)
            tcp_port: Puerto TCP local para elecciones
            udp_port: Puerto UDP local para heartbeats
            use_discovery: Si True, usa auto-descubrimiento dinámico
            multicast_group: Grupo multicast para descubrimiento
            multicast_port: Puerto multicast para descubrimiento
        """
        self.node_id = node_id
        self.use_discovery = use_discovery

        # Modo dinámico vs estático
        if use_discovery:
            # Modo dinámico: cluster_nodes se llena automáticamente
            self.cluster_nodes: Dict[int, tuple] = {}
            self.discovery: Optional[NodeDiscovery] = None
            logger.info(f"[Node-{node_id}] [BULLY] Dynamic mode - using auto-discovery")
        else:
            # Modo estático: usar cluster_nodes proporcionado
            self.cluster_nodes = cluster_nodes if cluster_nodes else {}
            self.discovery = None
            logger.info(f"[Node-{node_id}] [BULLY] Static mode - using fixed cluster_nodes")

        # Estado del nodo
        self.state = NodeState.FOLLOWER
        self.current_leader: Optional[int] = None

        # Election control (prevenir race conditions)
        self.election_in_progress = False
        self.current_term = 0  # Term number para invalidar mensajes obsoletos

        # Configuración de timeouts
        self.heartbeat_interval = 3   # Enviar heartbeat cada 3s
        self.election_timeout = 10     # Sin heartbeat por 10s → elección
        self.last_heartbeat_received = time.time()

        # Tracking de nodos activos (para validación inteligente)
        self.node_last_seen: Dict[int, float] = {}
        self.grace_period = 30  # Segundos antes de aceptar líder de menor prioridad

        # Inicializar tracking para nodos conocidos
        for nid in self.cluster_nodes.keys():
            if nid != node_id:
                self.node_last_seen[nid] = time.time()

        # Guardar configuración de puertos para discovery
        self.tcp_port = tcp_port
        self.udp_port = udp_port
        self.multicast_group = multicast_group
        self.multicast_port = multicast_port

        # Communication manager
        self.comm = CommunicationManager(node_id, tcp_port, udp_port)

        # Threads
        self.running = False
        self.heartbeat_thread: Optional[threading.Thread] = None
        self.monitor_thread: Optional[threading.Thread] = None

        # Lock para operaciones críticas
        self.lock = threading.Lock()

        logger.info(f"[Node-{node_id}] [BULLY] Node initialized (TCP:{tcp_port}, UDP:{udp_port})")
    
    def start(self):
        """Inicia el nodo Bully"""
        logger.info(f"[Node-{self.node_id}] [BULLY] Starting node...")

        self.running = True

        # Iniciar comunicación
        self.comm.start()

        # Registrar handlers de mensajes
        self.comm.register_tcp_handler('ELECTION', self._handle_election)
        self.comm.register_tcp_handler('COORDINATOR', self._handle_coordinator)
        self.comm.register_udp_handler('HEARTBEAT', self._handle_heartbeat)

        # Iniciar discovery si estamos en modo dinámico
        if self.use_discovery:
            self.discovery = NodeDiscovery(
                node_id=self.node_id,
                tcp_port=self.tcp_port,
                udp_port=self.udp_port,
                multicast_group=self.multicast_group,
                multicast_port=self.multicast_port,
                announce_interval=5,
                node_timeout=15
            )

            # Configurar callbacks para descubrimiento de nodos
            self.discovery.set_callbacks(
                on_discovered=self._on_node_discovered,
                on_lost=self._on_node_lost
            )

            self.discovery.start()
            logger.info(f"[Node-{self.node_id}] [BULLY] Discovery service started")

        # Iniciar thread de heartbeat
        self.heartbeat_thread = threading.Thread(
            target=self._heartbeat_loop,
            daemon=True,
            name=f"Heartbeat-{self.node_id}"
        )
        self.heartbeat_thread.start()

        # Iniciar thread de monitoreo de líder
        self.monitor_thread = threading.Thread(
            target=self._monitor_leader_loop,
            daemon=True,
            name=f"Monitor-{self.node_id}"
        )
        self.monitor_thread.start()

        logger.info(f"[Node-{self.node_id}] [BULLY] Node started successfully")

        # Iniciar primera elección en thread separado (no bloqueante)
        def delayed_election():
            # FASE DE DESCUBRIMIENTO: Esperar más tiempo para recibir heartbeats
            logger.info(f"[Node-{self.node_id}] [DISCOVERY] Starting discovery phase (10s)...")
            discovery_time = 10  # segundos para descubrir líder existente

            # Esperar y verificar si se descubre un líder
            start_time = time.time()
            while time.time() - start_time < discovery_time:
                if self.current_leader is not None:
                    logger.info(f"[Node-{self.node_id}] [DISCOVERY] Leader discovered: Node {self.current_leader}")

                    # Si mi ID es mayor que el líder actual, desafiar
                    if self.node_id > self.current_leader:
                        logger.info(f"[Node-{self.node_id}] [DISCOVERY] My ID ({self.node_id}) > current leader ({self.current_leader}), starting election")
                        time.sleep(1)  # Breve pausa antes de desafiar
                        self.start_election()
                    else:
                        logger.info(f"[Node-{self.node_id}] [DISCOVERY] Accepting current leader Node {self.current_leader}")
                    return

                time.sleep(0.5)  # Check cada 500ms

            # No se descubrió líder, iniciar elección
            logger.info(f"[Node-{self.node_id}] [DISCOVERY] No leader discovered, starting election")
            if self.current_leader is None:
                self.start_election()

        threading.Thread(
            target=delayed_election,
            daemon=True,
            name=f"InitialElection-{self.node_id}"
        ).start()
    
    def stop(self):
        """Detiene el nodo"""
        logger.info(f"[Node-{self.node_id}] [BULLY] Stopping node...")
        self.running = False

        # Detener discovery si está activo
        if self.use_discovery and self.discovery:
            self.discovery.stop()
            logger.info(f"[Node-{self.node_id}] [BULLY] Discovery service stopped")

        self.comm.stop()
    
    # ========================================================================
    # ALGORITMO BULLY - ELECCIÓN
    # ========================================================================
    
    def start_election(self):
        """
        Inicia proceso de elección.

        Algoritmo Bully:
        1. Enviar ELECTION a todos los nodos con ID mayor
        2. Si alguien responde OK → esperar COORDINATOR
        3. Si nadie responde → declararme líder
        """
        # Prevenir elecciones concurrentes y setup inicial
        with self.lock:
            if self.election_in_progress:
                logger.debug(f"[Node-{self.node_id}] [ELECTION] Election already in progress, skipping")
                return

            self.election_in_progress = True
            self.current_term += 1
            current_term = self.current_term

        logger.info(f"[Node-{self.node_id}] [ELECTION] Starting ELECTION process (term {current_term})")

        # Encontrar nodos con ID mayor
        higher_nodes = [
            nid for nid in self.cluster_nodes.keys()
            if nid > self.node_id
        ]

        if not higher_nodes:
            # Soy el nodo con mayor ID → declararme líder
            logger.info(f"[Node-{self.node_id}] [ELECTION] Has highest ID, becoming leader")
            self._become_leader()
            return

        # Enviar ELECTION a nodos con mayor ID
        ok_count = 0
        for target_id in higher_nodes:
            ip, tcp_port, udp_port = self.cluster_nodes[target_id]

            msg = Message(
                type='ELECTION',
                sender_id=self.node_id,
                timestamp=time.time()
            )

            logger.debug(f"[Node-{self.node_id}] [ELECTION] Sending ELECTION to node {target_id}")
            response = self.comm.send_tcp(ip, tcp_port, msg, timeout=5.0)  # Aumentado de 2.0s a 5.0s

            if response and response.type == 'OK':
                ok_count += 1
                logger.debug(f"[Node-{self.node_id}] [ELECTION] Received OK from node {target_id}")

        if ok_count > 0:
            # Hay nodos con mayor prioridad, esperar COORDINATOR
            logger.info(f"[Node-{self.node_id}] [ELECTION] Got {ok_count} OK responses, waiting for COORDINATOR...")
            with self.lock:
                self.state = NodeState.FOLLOWER

            # Esperar COORDINATOR con timeout
            wait_time = 10  # segundos
            start_wait = time.time()

            while time.time() - start_wait < wait_time:
                if self.current_leader is not None:
                    logger.info(f"[Node-{self.node_id}] [ELECTION] COORDINATOR received from node {self.current_leader}")
                    with self.lock:
                        self.election_in_progress = False
                    return
                time.sleep(0.5)

            # Si no llegó COORDINATOR, reiniciar elección
            logger.warning(f"[Node-{self.node_id}] [ELECTION] No COORDINATOR received, restarting election")
            with self.lock:
                self.election_in_progress = False  # Liberar para reiniciar
            threading.Thread(target=self.start_election, daemon=True).start()
        else:
            # Nadie respondió → soy el líder
            logger.info(f"[Node-{self.node_id}] [ELECTION] No OK responses, becoming leader")
            self._become_leader()
            with self.lock:
                self.election_in_progress = False
    
    def _become_leader(self):
        """Se convierte en líder y anuncia a todos"""
        with self.lock:
            self.state = NodeState.LEADER
            self.current_leader = self.node_id

        logger.warning(f"[Node-{self.node_id}] [LEADER] 🏆 NODE {self.node_id} IS NOW THE LEADER 🏆")

        # Anunciar COORDINATOR a todos los nodos con reintentos
        for target_id in self.cluster_nodes.keys():
            if target_id != self.node_id:
                ip, tcp_port, udp_port = self.cluster_nodes[target_id]

                msg = Message(
                    type='COORDINATOR',
                    sender_id=self.node_id,
                    timestamp=time.time()
                )

                # Función para enviar con reintentos
                def send_coordinator_with_retry(target_id, ip, tcp_port, msg):
                    max_attempts = 3
                    for attempt in range(max_attempts):
                        response = self.comm.send_tcp(ip, tcp_port, msg, timeout=2.0)  # Timeout más largo
                        if response is not None or not self.running:
                            logger.debug(f"[Node-{self.node_id}] [LEADER] COORDINATOR sent successfully to node {target_id}")
                            break
                        if attempt < max_attempts - 1:
                            logger.warning(f"[Node-{self.node_id}] [LEADER] COORDINATOR send failed to node {target_id}, retrying ({attempt+1}/{max_attempts})...")
                            time.sleep(0.5)  # Esperar antes de reintentar
                    else:
                        logger.error(f"[Node-{self.node_id}] [LEADER] Failed to send COORDINATOR to node {target_id} after {max_attempts} attempts")

                # Enviar en thread separado con reintentos
                threading.Thread(
                    target=send_coordinator_with_retry,
                    args=(target_id, ip, tcp_port, msg),
                    daemon=True
                ).start()

                logger.debug(f"[Node-{self.node_id}] [LEADER] Sending COORDINATOR to node {target_id}")

        # CRITICAL FIX: Limpiar flag de elección después de convertirse en líder
        with self.lock:
            self.election_in_progress = False
            logger.debug(f"[Node-{self.node_id}] [LEADER] Election flag cleared after becoming leader")
    
    # ========================================================================
    # HANDLERS DE MENSAJES
    # ========================================================================
    
    def _handle_election(self, message: Message) -> Optional[Message]:
        """
        Maneja mensaje ELECTION de otro nodo.

        Si mi ID es mayor, respondo OK e inicio mi propia elección.
        """
        sender_id = message.sender_id
        logger.debug(f"[Node-{self.node_id}] [ELECTION] Received ELECTION from node {sender_id}")

        # Actualizar actividad del nodo que envía ELECTION
        self._update_node_activity(sender_id)

        if self.node_id > sender_id:
            # Mi ID es mayor → responder OK e iniciar mi elección
            logger.debug(f"[Node-{self.node_id}] [ELECTION] My ID ({self.node_id}) > {sender_id}, responding OK")

            # Iniciar mi propia elección en thread separado
            threading.Thread(target=self.start_election, daemon=True).start()

            # Responder OK
            return Message(
                type='OK',
                sender_id=self.node_id,
                timestamp=time.time()
            )
        else:
            # Su ID es mayor → no responder
            logger.debug(f"[Node-{self.node_id}] [ELECTION] Their ID ({sender_id}) > mine ({self.node_id}), not responding")
            return None
    
    def _handle_coordinator(self, message: Message) -> Optional[Message]:
        """
        Maneja anuncio COORDINATOR de nuevo líder.

        VALIDACIÓN CRÍTICA: Solo acepta líderes con prioridad válida según Bully.
        """
        new_leader = message.sender_id
        logger.debug(f"[Node-{self.node_id}] [COORDINATOR] Received COORDINATOR from node {new_leader}")

        # Actualizar actividad del nodo que envía COORDINATOR
        self._update_node_activity(new_leader)

        # VALIDACIÓN INTELIGENTE: Usar el mismo criterio que en heartbeats
        if not self._should_accept_leader(new_leader):
            logger.warning(f"[Node-{self.node_id}] [COORDINATOR] REJECTED - Node {new_leader} not acceptable as leader")
            # Iniciar nuestra propia elección solo si no hay una en progreso
            if not self.election_in_progress:
                threading.Thread(target=self.start_election, daemon=True).start()
            return None

        # VALIDACIÓN 2: Verificar que sea el nodo con mayor ID en el cluster
        # (solo aceptar si nodos con mayor ID están potencialmente inactivos)
        max_node_id = max(self.cluster_nodes.keys())
        if new_leader < max_node_id:
            logger.info(f"[Node-{self.node_id}] [COORDINATOR] Accepting node {new_leader} (assuming nodes {new_leader+1}-{max_node_id} are down)")

        with self.lock:
            self.current_leader = new_leader
            self.state = NodeState.FOLLOWER
            self.last_heartbeat_received = time.time()

        logger.info(f"[Node-{self.node_id}] [COORDINATOR] Node {new_leader} is now the leader")
        return None
    
    def _handle_heartbeat(self, message: Message):
        """
        Maneja heartbeat del líder.

        VALIDACIÓN INTELIGENTE: Acepta líderes de menor prioridad si los nodos
        de mayor prioridad están inactivos por más del grace period.
        """
        leader_id = message.sender_id
        logger.info(f"[Node-{self.node_id}] [HEARTBEAT-RECV] 💓 Processing heartbeat from Node {leader_id}")

        # Actualizar timestamp de último heartbeat
        self.last_heartbeat_received = time.time()

        # Actualizar actividad del nodo que envía heartbeat
        self._update_node_activity(leader_id)

        # VALIDACIÓN INTELIGENTE: Usar el nuevo método para decidir si aceptar el líder
        logger.info(f"[Node-{self.node_id}] [VALIDATION] Evaluating leader {leader_id} (current_leader: {self.current_leader})")
        if not self._should_accept_leader(leader_id):
            logger.warning(f"[Node-{self.node_id}] [HEARTBEAT] ✗ Rejecting leader {leader_id} - higher priority nodes may be active")
            # Solo iniciar elección si no hay una en progreso
            if not self.election_in_progress:
                threading.Thread(target=self.start_election, daemon=True).start()
            return

        # Si el líder es diferente al actual, actualizar
        if self.current_leader != leader_id:
            with self.lock:
                old_leader = self.current_leader
                self.current_leader = leader_id
                self.state = NodeState.FOLLOWER

                if old_leader is None:
                    logger.info(f"[Node-{self.node_id}] [HEARTBEAT] ✓ Leader is node {leader_id} (discovered via heartbeat)")
                else:
                    logger.info(f"[Node-{self.node_id}] [HEARTBEAT] ✓ Leader changed from node {old_leader} to node {leader_id}")
        else:
            # Ensure we're FOLLOWER even when confirming same leader
            if self.state == NodeState.LEADER:
                with self.lock:
                    self.state = NodeState.FOLLOWER
                    logger.warning(f"[Node-{self.node_id}] [HEARTBEAT] 👑➡️💼 ABDICATION: I was LEADER but accepting higher-priority leader {leader_id}")
            else:
                logger.info(f"[Node-{self.node_id}] [HEARTBEAT] ✓ Confirmed leader {leader_id}")
    
    # ========================================================================
    # HEARTBEAT
    # ========================================================================
    
    def _heartbeat_loop(self):
        """
        Loop de heartbeat.

        Si soy líder: enviar heartbeat cada 5 segundos
        """
        while self.running:
            time.sleep(self.heartbeat_interval)

            if self.state == NodeState.LEADER:
                logger.info(f"[Node-{self.node_id}] [HEARTBEAT-LOOP] ⏰ Waking up (state=LEADER) - sending heartbeats")
                self._send_heartbeat()
            else:
                logger.debug(f"[Node-{self.node_id}] [HEARTBEAT-LOOP] ⏰ Waking up (state={self.state.value}) - not leader, skipping")
    
    def _send_heartbeat(self):
        """Envía heartbeat a todos los nodos (UDP)"""
        followers = [nid for nid in self.cluster_nodes.keys() if nid != self.node_id]
        logger.info(f"[Node-{self.node_id}] [HEARTBEAT-SEND] 📡 Sending heartbeats to {len(followers)} followers")

        msg = Message(
            type='HEARTBEAT',
            sender_id=self.node_id,
            timestamp=time.time()
        )

        for target_id in followers:
            ip, tcp_port, udp_port = self.cluster_nodes[target_id]
            logger.info(f"[Node-{self.node_id}] [HEARTBEAT-SEND] → Node {target_id} ({ip}:{udp_port})")
            self.comm.send_udp(ip, udp_port, msg)
    
    def _monitor_leader_loop(self):
        """
        Monitorea heartbeats del líder.

        Si no recibo heartbeat por 15 segundos, iniciar elección.
        """
        while self.running:
            time.sleep(1)

            if self.state == NodeState.FOLLOWER:
                time_since_heartbeat = time.time() - self.last_heartbeat_received

                # Log detallado del monitoreo
                if time_since_heartbeat > self.election_timeout:
                    logger.warning(f"[Node-{self.node_id}] [MONITOR] ⏱️ Leader timeout! No heartbeat for {time_since_heartbeat:.1f}s (expected leader: {self.current_leader})")
                    logger.info(f"[Node-{self.node_id}] [MONITOR] 🗳️ Starting election due to leader timeout")

                    # Iniciar elección
                    threading.Thread(target=self.start_election, daemon=True).start()

                    # Reset timer
                    self.last_heartbeat_received = time.time()
                elif time_since_heartbeat > 10:
                    # Warning si pasa más de 10s sin heartbeat
                    logger.info(f"[Node-{self.node_id}] [MONITOR] ⚠️ No heartbeat for {time_since_heartbeat:.1f}s (leader: {self.current_leader}, timeout in {self.election_timeout - time_since_heartbeat:.1f}s)")
            else:
                logger.debug(f"[Node-{self.node_id}] [MONITOR] Monitoring (state={self.state.value})")
    
    # ========================================================================
    # VALIDACIÓN INTELIGENTE
    # ========================================================================

    def _should_accept_leader(self, leader_id: int) -> bool:
        """
        Determina si debemos aceptar un nodo como líder.

        Lógica inteligente:
        1. Si el líder tiene mayor ID que nosotros → SIEMPRE aceptar
        2. Si el líder tiene menor ID → aceptar solo si:
           - Todos los nodos con mayor ID están inactivos (grace period expirado)
           - O no hemos visto actividad de ellos en más de grace_period segundos
        """
        # Si el líder tiene mayor ID que nosotros, siempre aceptar
        if leader_id > self.node_id:
            logger.info(f"[Node-{self.node_id}] [VALIDATION] ✓ Leader {leader_id} > My ID {self.node_id}: ACCEPT")
            return True

        # Si el líder tiene menor ID, verificar si nodos superiores están activos
        current_time = time.time()
        logger.info(f"[Node-{self.node_id}] [VALIDATION] Leader {leader_id} < My ID {self.node_id}: checking higher nodes...")

        # EXCEPCIÓN PARA NODOS NUEVOS: Si no tenemos líder actual y estamos en FOLLOWER,
        # somos un nodo nuevo descubriendo el cluster. Aceptar temporalmente cualquier líder.
        if self.current_leader is None and self.state == NodeState.FOLLOWER:
            logger.info(f"[Node-{self.node_id}] [VALIDATION] ✓ New node accepting initial leader {leader_id} during discovery")
            return True

        # CRÍTICO: Si YO soy LEADER con mayor ID, NUNCA aceptar líder de menor ID
        # Esto previene el split-brain donde múltiples nodos piensan ser líderes
        if self.state == NodeState.LEADER:
            logger.info(f"[Node-{self.node_id}] [VALIDATION] ✗ Rejecting leader {leader_id} "
                       f"because I am LEADER with higher ID {self.node_id}")
            return False

        # Buscar si hay nodos con mayor ID que el líder propuesto y que estén potencialmente activos
        for node_id in self.cluster_nodes.keys():
            if node_id > leader_id:  # Nodo con mayor prioridad que el líder propuesto
                if node_id in self.node_last_seen:
                    time_since_seen = current_time - self.node_last_seen[node_id]
                    logger.info(f"[Node-{self.node_id}] [VALIDATION]   Node {node_id}: last seen {time_since_seen:.1f}s ago (grace: {self.grace_period}s)")
                    if time_since_seen < self.grace_period:
                        # Hay un nodo con mayor prioridad que podría estar activo
                        logger.info(f"[Node-{self.node_id}] [VALIDATION] ✗ Rejecting leader {leader_id} "
                                   f"because node {node_id} might still be active")
                        return False

        # Si llegamos aquí, todos los nodos con mayor prioridad están inactivos
        logger.info(f"[Node-{self.node_id}] [VALIDATION] ✓ Accepting leader {leader_id} "
                   f"- all higher-priority nodes appear down")
        return True

    def _update_node_activity(self, node_id: int):
        """Actualiza el timestamp de última actividad de un nodo"""
        if node_id != self.node_id and node_id in self.node_last_seen:
            self.node_last_seen[node_id] = time.time()
            logger.debug(f"[Node-{self.node_id}] [TRACKING] Updated activity for node {node_id}")

    # ========================================================================
    # GESTIÓN DINÁMICA DE NODOS
    # ========================================================================

    def _on_node_discovered(self, node_id: int, host: str, tcp_port: int, udp_port: int):
        """
        Callback cuando NodeDiscovery descubre un nuevo nodo.

        Args:
            node_id: ID del nodo descubierto
            host: IP del nodo
            tcp_port: Puerto TCP del nodo
            udp_port: Puerto UDP del nodo
        """
        logger.info(f"[Node-{self.node_id}] [DYNAMIC] Callback: New node discovered - {node_id} at {host}:{tcp_port}")
        self.add_node(node_id, host, tcp_port, udp_port)

        # Si descubrimos un nodo con mayor ID y no hay líder, iniciar elección
        if node_id > self.node_id and self.current_leader is None:
            logger.info(f"[Node-{self.node_id}] [DYNAMIC] Discovered higher-ID node {node_id}, may need election")

    def _on_node_lost(self, node_id: int):
        """
        Callback cuando NodeDiscovery pierde contacto con un nodo.

        Args:
            node_id: ID del nodo perdido
        """
        logger.warning(f"[Node-{self.node_id}] [DYNAMIC] Callback: Node lost - {node_id}")
        self.remove_node(node_id)

        # Si era el líder, iniciar elección
        if self.current_leader == node_id:
            logger.warning(f"[Node-{self.node_id}] [DYNAMIC] Lost leader node {node_id}, starting election")
            if not self.election_in_progress:
                threading.Thread(target=self.start_election, daemon=True).start()

    def add_node(self, node_id: int, host: str, tcp_port: int, udp_port: int):
        """
        Agrega un nodo al cluster dinámicamente.

        Args:
            node_id: ID del nodo
            host: IP del nodo
            tcp_port: Puerto TCP del nodo
            udp_port: Puerto UDP del nodo
        """
        with self.lock:
            if node_id != self.node_id and node_id not in self.cluster_nodes:
                self.cluster_nodes[node_id] = (host, tcp_port, udp_port)
                self.node_last_seen[node_id] = time.time()
                logger.info(f"[Node-{self.node_id}] [DYNAMIC] ✓ Added node {node_id} ({host}:{tcp_port}) to cluster")
                logger.info(f"[Node-{self.node_id}] [DYNAMIC] Cluster now has {len(self.cluster_nodes)} nodes")

    def remove_node(self, node_id: int):
        """
        Remueve un nodo del cluster dinámicamente.

        Args:
            node_id: ID del nodo a remover
        """
        with self.lock:
            if node_id in self.cluster_nodes:
                node_info = self.cluster_nodes.pop(node_id)
                if node_id in self.node_last_seen:
                    del self.node_last_seen[node_id]
                logger.warning(f"[Node-{self.node_id}] [DYNAMIC] ✗ Removed node {node_id} ({node_info[0]}) from cluster")
                logger.info(f"[Node-{self.node_id}] [DYNAMIC] Cluster now has {len(self.cluster_nodes)} nodes")

    # ========================================================================
    # API PÚBLICA
    # ========================================================================
    
    def is_leader(self) -> bool:
        """Retorna True si este nodo es el líder"""
        return self.state == NodeState.LEADER
    
    def get_current_leader(self) -> Optional[int]:
        """Retorna ID del líder actual"""
        return self.current_leader

    def get_state(self) -> str:
        """Retorna el estado actual del nodo como string"""
        return self.state.value

    def get_status(self) -> dict:
        """Retorna estado completo del nodo"""
        return {
            'node_id': self.node_id,
            'state': self.state.value,
            'current_leader': self.current_leader,
            'is_leader': self.is_leader(),
            'time_since_last_heartbeat': time.time() - self.last_heartbeat_received
        }
