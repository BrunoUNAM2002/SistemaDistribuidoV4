"""
Módulo para generación automática de IDs únicos para nodos en el cluster.

Utiliza un enfoque híbrido timestamp + random para generar IDs numéricos
únicos sin necesidad de coordinación central.
"""
import time
import random
import os
import json
import logging

logger = logging.getLogger(__name__)


def _is_port_available(port: int, host: str = '0.0.0.0') -> bool:
    """
    Verifica si un puerto está disponible intentando bind temporal.

    Args:
        port: Puerto a verificar
        host: Dirección IP para bind (default: 0.0.0.0)

    Returns:
        bool: True si el puerto está libre, False si está ocupado
    """
    import socket

    # Probar TCP
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind((host, port))
        sock.close()
    except OSError:
        return False

    # Probar UDP
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind((host, port))
        sock.close()
    except OSError:
        return False

    return True


def generate_node_id(start_id: int = 1, max_attempts: int = 100) -> int:
    """
    Genera un ID de nodo secuencial usando port scanning.

    Intenta IDs secuenciales (1, 2, 3...) y verifica disponibilidad
    mediante port binding. Esto garantiza IDs simples sin colisiones.

    Estrategia:
    1. Intentar ID candidato (empezando desde start_id)
    2. Calcular puertos TCP y UDP basados en ese ID
    3. Verificar que ambos puertos estén libres (atomic OS-level check)
    4. Si están libres, usar ese ID
    5. Si no, incrementar ID y reintentar

    Args:
        start_id: ID inicial para comenzar búsqueda (default: 1)
        max_attempts: Máximo número de intentos (default: 100)

    Returns:
        int: ID único disponible (rango: 1-100+)

    Raises:
        RuntimeError: Si no se encuentra ID libre después de max_attempts

    Examples:
        >>> # Cluster vacío
        >>> id1 = generate_node_id()  # Retorna 1
        >>> # Con nodo 1 corriendo
        >>> id2 = generate_node_id()  # Retorna 2
        >>> # Con nodos 1,2,3 corriendo
        >>> id4 = generate_node_id()  # Retorna 4
    """
    for attempt in range(max_attempts):
        candidate_id = start_id + attempt

        # Calcular puertos basados en el ID candidato
        # (Misma lógica que en config.py)
        tcp_port = 5555 + (candidate_id % 1000)
        udp_port = 6000 + (candidate_id % 1000)

        # Verificar disponibilidad de puertos
        if _is_port_available(tcp_port) and _is_port_available(udp_port):
            logger.info(f"Found available node ID: {candidate_id} (TCP:{tcp_port}, UDP:{udp_port})")
            return candidate_id
        else:
            logger.debug(f"ID {candidate_id} not available (ports {tcp_port}/{udp_port} in use)")

    # No se encontró ID libre
    raise RuntimeError(
        f"No available node ID found after {max_attempts} attempts. "
        f"Cluster may be full or ports are blocked."
    )


def get_persistent_id_file(use_process_unique: bool = True) -> str:
    """
    Retorna la ruta al archivo donde se persiste el node ID.

    Args:
        use_process_unique: Si True, usa un archivo único por proceso (PID-based)
                           para evitar colisiones en clusters dinámicos.
                           Si False, usa un archivo compartido (solo para nodo único).

    El archivo se guarda en ../data/node_ids/ para mantener
    el mismo ID entre reinicios del nodo.

    Returns:
        str: Ruta absoluta al archivo de persistencia
    """
    # Directorio del módulo actual
    current_dir = os.path.dirname(os.path.abspath(__file__))

    # Subir dos niveles y entrar a data/node_ids/
    data_dir = os.path.join(current_dir, '..', '..', 'data', 'node_ids')

    # Crear directorio si no existe
    os.makedirs(data_dir, exist_ok=True)

    if use_process_unique:
        # Archivo único por proceso usando PID
        # Esto previene colisiones cuando múltiples nodos inician simultáneamente
        pid = os.getpid()
        return os.path.join(data_dir, f'node_pid_{pid}.json')
    else:
        # Archivo compartido (solo para un único nodo persistente)
        return os.path.join(data_dir, 'node_id.json')


def save_node_id(node_id: int, persist_file: str = None, use_process_unique: bool = True) -> None:
    """
    Guarda el node ID en un archivo para persistencia.

    Args:
        node_id: ID del nodo a guardar
        persist_file: Ruta al archivo (opcional, usa default si no se proporciona)
        use_process_unique: Si True, usa archivo único por proceso
    """
    if persist_file is None:
        persist_file = get_persistent_id_file(use_process_unique=use_process_unique)

    try:
        data = {
            'node_id': node_id,
            'generated_at': time.time(),
            'timestamp': time.strftime('%Y-%m-%d %H:%M:%S')
        }

        with open(persist_file, 'w') as f:
            json.dump(data, f, indent=2)

        logger.info(f"Saved node ID {node_id} to {persist_file}")

    except Exception as e:
        logger.error(f"Failed to save node ID to file: {e}")
        # No es crítico, el nodo puede seguir funcionando sin persistencia


def load_node_id(persist_file: str = None, use_process_unique: bool = True) -> int:
    """
    Carga el node ID desde el archivo de persistencia.

    Args:
        persist_file: Ruta al archivo (opcional, usa default si no se proporciona)
        use_process_unique: Si True, usa archivo único por proceso

    Returns:
        int: Node ID guardado, o None si no existe o no se puede leer
    """
    if persist_file is None:
        persist_file = get_persistent_id_file(use_process_unique=use_process_unique)

    if not os.path.exists(persist_file):
        logger.debug(f"No persistent ID file found at {persist_file}")
        return None

    try:
        with open(persist_file, 'r') as f:
            data = json.load(f)

        node_id = data.get('node_id')

        if node_id is not None:
            logger.info(f"Loaded node ID {node_id} from {persist_file}")
            return int(node_id)
        else:
            logger.warning(f"Invalid data in persistent ID file: {persist_file}")
            return None

    except Exception as e:
        logger.error(f"Failed to load node ID from file: {e}")
        return None


def get_or_create_node_id(persist_file: str = None, force_new: bool = False, use_process_unique: bool = True) -> int:
    """
    Obtiene el node ID persistido o genera uno nuevo secuencial si no existe.

    Este es el método principal que deberían usar las aplicaciones.
    Genera IDs secuenciales (1, 2, 3...) verificando disponibilidad de puertos.

    Args:
        persist_file: Ruta al archivo de persistencia (opcional)
        force_new: Si True, siempre genera un nuevo ID ignorando el persistido
        use_process_unique: Si True, usa archivo único por proceso (recomendado para clusters dinámicos)

    Returns:
        int: Node ID (existente o nuevo secuencial 1-100+)

    Examples:
        >>> # Cluster vacío - primera ejecución
        >>> id1 = get_or_create_node_id()  # Retorna 1
        >>> # Segunda ejecución en MISMO proceso - usa el mismo ID
        >>> id2 = get_or_create_node_id()
        >>> id1 == id2  # True
        True
        >>> # Nuevo proceso con nodo 1 corriendo
        >>> # id3 = get_or_create_node_id()  # Retorna 2
        >>> # Nuevo proceso con nodos 1,2 corriendo
        >>> # id4 = get_or_create_node_id()  # Retorna 3
    """
    if not force_new:
        # Intentar cargar ID existente
        existing_id = load_node_id(persist_file, use_process_unique=use_process_unique)
        if existing_id is not None:
            return existing_id

    # Generar nuevo ID secuencial (1, 2, 3...)
    new_id = generate_node_id()

    # Guardar para próximas ejecuciones
    save_node_id(new_id, persist_file, use_process_unique=use_process_unique)

    return new_id


def validate_node_id(node_id: int) -> bool:
    """
    Valida que un node ID sea válido.

    Un ID válido debe ser:
    - Un entero positivo
    - Mayor que 0
    - Menor que 2^31 (límite práctico para evitar overflow)

    Args:
        node_id: ID a validar

    Returns:
        bool: True si el ID es válido, False en caso contrario
    """
    if not isinstance(node_id, int):
        return False

    if node_id <= 0:
        return False

    if node_id >= 2**31:  # ~2 billones
        return False

    return True


def clear_persistent_id(persist_file: str = None, use_process_unique: bool = True) -> bool:
    """
    Elimina el archivo de persistencia del node ID.

    Útil para testing o para forzar regeneración de ID.

    Args:
        persist_file: Ruta al archivo (opcional)
        use_process_unique: Si True, usa archivo único por proceso

    Returns:
        bool: True si se eliminó exitosamente, False en caso contrario
    """
    if persist_file is None:
        persist_file = get_persistent_id_file(use_process_unique=use_process_unique)

    try:
        if os.path.exists(persist_file):
            os.remove(persist_file)
            logger.info(f"Cleared persistent ID file: {persist_file}")
            return True
        else:
            logger.debug(f"No persistent ID file to clear at {persist_file}")
            return False

    except Exception as e:
        logger.error(f"Failed to clear persistent ID file: {e}")
        return False
