import socket
import threading
from datetime import datetime
import sqlite3
import json
import os
import getpass
import time
import random

# ==========================================
# CONFIGURACIÓN DEL SISTEMA DISTRIBUIDO
# ==========================================

# Configuración de rutas y archivos
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SQL_SCHEMA_PATH = os.path.join(BASE_DIR, 'schema2.sql')
DB_PATH = os.path.join(BASE_DIR, 'emergencias.db')

# Configuración de red - puerto principal del sistema
SERVER_PORT = 5555

# Lista de nodos conocidos en el sistema distribuido
NODOS_REMOTOS = [
    # ('192.168.95.131', 5555),
    # ('192.168.95.132', 5555),
]

# Evento global para controlar el cierre ordenado del sistema
shutdown_event = threading.Event()

# ==========================================
# SISTEMA DE BLOQUEOS DISTRIBUIDOS
# ==========================================

# Diccionario global para tracking de bloqueos locales
bloqueos_locales = {}
lock_bloqueos = threading.Lock()

def verificar_recurso_local(recurso_tipo, recurso_id):
    """
    Verifica la disponibilidad de un recurso en la base de datos local.
    
    Args:
        recurso_tipo: Tipo de recurso ('DOCTOR' o 'CAMA')
        recurso_id: Identificador del recurso
    
    Returns:
        bool: True si el recurso está disponible, False en caso contrario
    """
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    try:
        if recurso_tipo == "DOCTOR":
            cursor.execute("SELECT disponible FROM DOCTORES WHERE id = ?", (recurso_id,))
            resultado = cursor.fetchone()
            return resultado and resultado[0] == 1
            
        elif recurso_tipo == "CAMA":
            cursor.execute("SELECT ocupada FROM CAMAS_ATENCION WHERE id = ?", (recurso_id,))
            resultado = cursor.fetchone()
            return resultado and resultado[0] == 0
    finally:
        conn.close()

def solicitar_bloqueo_distribuido(recurso_tipo, recurso_id):
    """
    Solicita un bloqueo distribuido para un recurso específico.
    Consulta a todos los nodos remotos para obtener consenso.
    
    Args:
        recurso_tipo: Tipo de recurso a bloquear
        recurso_id: Identificador del recurso
    
    Returns:
        bool: True si se obtuvo el bloqueo, False si fue rechazado
    """
    print(f"Solicitando bloqueo distribuido para {recurso_tipo} {recurso_id}...")
    
    # Verificación local inicial del recurso
    if not verificar_recurso_local(recurso_tipo, recurso_id):
        print(f"Recurso {recurso_tipo} {recurso_id} no disponible localmente")
        return False
    
    # Adquisición del bloqueo local
    with lock_bloqueos:
        clave = f"{recurso_tipo}_{recurso_id}"
        if clave in bloqueos_locales:
            print(f"Recurso {recurso_tipo} {recurso_id} ya está bloqueado localmente")
            return False
        bloqueos_locales[clave] = datetime.now()
    
    # Solicitud de bloqueo a nodos remotos
    confirmaciones = 0
    comando = {
        "accion": "SOLICITAR_BLOQUEO",
        "recurso_tipo": recurso_tipo,
        "recurso_id": recurso_id,
        "solicitante": SERVER_PORT
    }
    
    for (ip, puerto) in NODOS_REMOTOS:
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(3.0)
                s.connect((ip, puerto))
                s.sendall(json.dumps(comando).encode('utf-8'))
                respuesta = s.recv(1024).decode('utf-8')
                if respuesta == "BLOQUEO_OK":
                    confirmaciones += 1
                    print(f"Nodo {ip} aprobó el bloqueo")
                else:
                    print(f"Nodo {ip} rechazó el bloqueo")
        except Exception as e:
            print(f"Nodo {ip} no respondió: {e}")
    
    # Decisión basada en el consenso de mayoría
    if confirmaciones >= len(NODOS_REMOTOS) // 2 or not NODOS_REMOTOS:
        print(f"Bloqueo concedido para {recurso_tipo} {recurso_id}")
        return True
    else:
        print(f"Bloqueo rechazado para {recurso_tipo} {recurso_id}")
        # Liberar bloqueo local si no se obtuvo consenso
        with lock_bloqueos:
            clave = f"{recurso_tipo}_{recurso_id}"
            if clave in bloqueos_locales:
                del bloqueos_locales[clave]
        return False

def liberar_bloqueo_distribuido(recurso_tipo, recurso_id):
    """
    Libera un bloqueo distribuido previamente adquirido.
    
    Args:
        recurso_tipo: Tipo de recurso a liberar
        recurso_id: Identificador del recurso
    """
    # Liberación del bloqueo local
    with lock_bloqueos:
        clave = f"{recurso_tipo}_{recurso_id}"
        if clave in bloqueos_locales:
            del bloqueos_locales[clave]
    
    # Notificación de liberación a nodos remotos
    comando = {
        "accion": "LIBERAR_BLOQUEO",
        "recurso_tipo": recurso_tipo,
        "recurso_id": recurso_id
    }
    
    for (ip, puerto) in NODOS_REMOTOS:
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(2.0)
                s.connect((ip, puerto))
                s.sendall(json.dumps(comando).encode('utf-8'))
        except:
            # Silenciar errores en liberación para no interrumpir el flujo
            continue
    
    print(f"Bloqueo liberado para {recurso_tipo} {recurso_id}")

# ==========================================
# GESTIÓN DE BASE DE DATOS LOCAL
# ==========================================

def init_db():
    """
    Inicializa la base de datos local.
    Crea las tablas necesarias si no existen y configura las restricciones.
    """
    print(f"Verificando base de datos en: {DB_PATH}")
    conn = None
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("PRAGMA foreign_keys = ON;")

        # Crear tabla de usuarios del sistema si no existe
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS USUARIOS_SISTEMA (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password TEXT NOT NULL,
                rol TEXT NOT NULL,
                id_personal INTEGER
            )
        """)

        # Crear tabla de control de consecutivos
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS CONSECUTIVOS_VISITAS (
                sala_id INTEGER PRIMARY KEY,
                ultimo_consecutivo INTEGER DEFAULT 0
            )
        """)

        # Cargar schema completo si la base de datos está vacía
        if not os.path.exists(DB_PATH) or os.path.getsize(DB_PATH) < 100:
            if os.path.exists(SQL_SCHEMA_PATH):
                with open(SQL_SCHEMA_PATH, 'r') as f:
                    sql_script = f.read()
                cursor.executescript(sql_script)

        conn.commit()
    except Exception as e:
        print(f"Nota durante inicialización de BD: {e}")
    finally:
        if conn:
            conn.close()

def ejecutar_transaccion_local(comando):
    """
    Ejecuta una transacción en la base de datos local.
    Maneja diferentes tipos de operaciones con verificación de duplicados.
    
    Args:
        comando: Diccionario con la acción y datos a ejecutar
    
    Returns:
        mixed: Resultado de la transacción o False en caso de error
    """
    print(f"Ejecutando transacción local: {comando['accion']}")
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    try:
        if comando['accion'] == "INSERTAR_PACIENTE":
            datos = comando['datos']
            cursor.execute(
                "INSERT INTO PACIENTES (nombre, edad, contacto) VALUES (?, ?, ?)",
                (datos['nombre'], datos['edad'], datos.get('contacto', ''))
            )
            paciente_id = cursor.lastrowid
            conn.commit()
            return paciente_id
            
        elif comando['accion'] == "ASIGNAR_RECURSOS":
            datos = comando['datos']
            
            # Verificación de folio duplicado antes de la inserción
            cursor.execute("SELECT COUNT(*) FROM VISITAS_EMERGENCIA WHERE folio = ?", (datos['folio'],))
            if cursor.fetchone()[0] > 0:
                print(f"Folio {datos['folio']} ya existe en el sistema")
                conn.rollback()
                return False
            
            # Actualización de estado del doctor
            cursor.execute("UPDATE DOCTORES SET disponible = 0 WHERE id = ?", (datos['doctor_id'],))
            
            # Actualización de estado de la cama
            cursor.execute(
                "UPDATE CAMAS_ATENCION SET ocupada = 1, paciente_id = ? WHERE id = ?", 
                (datos['paciente_id'], datos['cama_id'])
            )
            
            # Inserción del registro de visita
            cursor.execute("""
                INSERT INTO VISITAS_EMERGENCIA 
                (folio, paciente_id, doctor_id, cama_id, sala_id, timestamp, estado) 
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                datos['folio'], datos['paciente_id'], datos['doctor_id'], 
                datos['cama_id'], SERVER_PORT, datetime.now(), 'En tratamiento'
            ))
            
            conn.commit()
            return True
            
        elif comando['accion'] == "CERRAR_VISITA":
            datos = comando['datos']
            folio = datos['folio']
            
            # Obtención de información de la visita a cerrar
            cursor.execute(
                "SELECT doctor_id, cama_id FROM VISITAS_EMERGENCIA WHERE folio = ?", 
                (folio,)
            )
            visita = cursor.fetchone()
            
            if visita:
                doctor_id, cama_id = visita
                
                # Liberación del doctor asignado
                cursor.execute("UPDATE DOCTORES SET disponible = 1 WHERE id = ?", (doctor_id,))
                
                # Liberación de la cama ocupada
                cursor.execute(
                    "UPDATE CAMAS_ATENCION SET ocupada = 0, paciente_id = NULL WHERE id = ?", 
                    (cama_id,)
                )
                
                # Actualización del estado de la visita
                cursor.execute(
                    "UPDATE VISITAS_EMERGENCIA SET estado = 'Cerrada' WHERE folio = ?", 
                    (folio,)
                )
                
                conn.commit()
                print(f"Visita {folio} cerrada - Recursos liberados")
                return True
            else:
                print(f"Visita {folio} no encontrada en el sistema")
                return False
            
        elif comando['accion'] == "INCREMENTAR_CONSECUTIVO":
            # Gestión del número consecutivo para folios únicos
            cursor.execute(
                "SELECT ultimo_consecutivo FROM CONSECUTIVOS_VISITAS WHERE sala_id = ?", 
                (SERVER_PORT,)
            )
            resultado = cursor.fetchone()
            if resultado:
                nuevo_consecutivo = resultado[0] + 1
                cursor.execute(
                    "UPDATE CONSECUTIVOS_VISITAS SET ultimo_consecutivo = ? WHERE sala_id = ?", 
                    (nuevo_consecutivo, SERVER_PORT)
                )
                conn.commit()
                return nuevo_consecutivo
            else:
                cursor.execute(
                    "INSERT INTO CONSECUTIVOS_VISITAS (sala_id, ultimo_consecutivo) VALUES (?, 1)", 
                    (SERVER_PORT,)
                )
                conn.commit()
                return 1
            
        conn.commit()
    except Exception as e:
        print(f"Error durante ejecución de transacción local: {e}")
        conn.rollback()
        return False
    finally:
        conn.close()

# ==========================================
# SISTEMA DE CONSENSO DISTRIBUIDO
# ==========================================

def propagar_transaccion_con_consenso(comando):
    """
    Propaga una transacción a todos los nodos del sistema y espera consenso.
    
    Args:
        comando: Transacción a ejecutar en todos los nodos
    
    Returns:
        bool: True si se alcanzó consenso, False en caso contrario
    """
    # Caso especial: sistema de un solo nodo
    if not NODOS_REMOTOS:
        return ejecutar_transaccion_local(comando)

    comando_json = json.dumps(comando)
    confirmaciones = 0
    total_nodos = len(NODOS_REMOTOS)

    print(f"Iniciando proceso de consenso para: {comando['accion']}")

    # Fase de votación con todos los nodos remotos
    for (ip, puerto) in NODOS_REMOTOS:
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(3.0)
                s.connect((ip, puerto))
                s.sendall(comando_json.encode('utf-8'))
                respuesta = s.recv(1024).decode('utf-8')
                if respuesta == "CONSENSO_OK":
                    confirmaciones += 1
                    print(f"Nodo {ip}:{puerto} aprobó la transacción")
                else:
                    print(f"Nodo {ip}:{puerto} rechazó la transacción: {respuesta}")
        except Exception as e:
            print(f"Nodo {ip}:{puerto} no respondió: {e}")

    # Evaluación del resultado del consenso
    umbral_consenso = (total_nodos // 2) + 1
    if confirmaciones >= umbral_consenso:
        resultado = ejecutar_transaccion_local(comando)
        if resultado:
            print(f"Consenso alcanzado - {confirmaciones} de {total_nodos} nodos aprobaron")
            return True
        else:
            print("Error en ejecución local después de consenso aprobado")
            return False
    else:
        print(f"Consenso fallido - Solo {confirmaciones} de {total_nodos} nodos aprobaron")
        return False

# ==========================================
# GENERACIÓN DE FOLIOS ÚNICOS
# ==========================================

def obtener_siguiente_consecutivo():
    """
    Obtiene el siguiente número consecutivo garantizando unicidad.
    
    Returns:
        int: Siguiente número consecutivo disponible
    """
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    try:
        cursor.execute(
            "SELECT ultimo_consecutivo FROM CONSECUTIVOS_VISITAS WHERE sala_id = ?", 
            (SERVER_PORT,)
        )
        resultado = cursor.fetchone()
        
        if resultado:
            nuevo_consecutivo = resultado[0] + 1
            # Actualización local inmediata del consecutivo
            cursor.execute(
                "UPDATE CONSECUTIVOS_VISITAS SET ultimo_consecutivo = ? WHERE sala_id = ?", 
                (nuevo_consecutivo, SERVER_PORT)
            )
            conn.commit()
            
            # Propagación del incremento a otros nodos
            comando = {
                "accion": "INCREMENTAR_CONSECUTIVO",
                "datos": {}
            }
            propagar_transaccion_con_consenso(comando)
            
            return nuevo_consecutivo
        else:
            # Inicialización del sistema de consecutivos
            cursor.execute(
                "INSERT INTO CONSECUTIVOS_VISITAS (sala_id, ultimo_consecutivo) VALUES (?, 1)", 
                (SERVER_PORT,)
            )
            conn.commit()
            return 1
    finally:
        conn.close()

def generar_folio_exacto(paciente_id, doctor_id, sala_id):
    """
    Genera un folio único según el formato especificado.
    Implementa verificación anti-duplicados con reintentos.
    
    Args:
        paciente_id: Identificador del paciente
        doctor_id: Identificador del doctor
        sala_id: Identificador de la sala
    
    Returns:
        str: Folio único generado
    """
    max_intentos = 5
    
    for intento in range(max_intentos):
        consecutivo = obtener_siguiente_consecutivo()
        folio = f"{paciente_id}{doctor_id}{sala_id}{consecutivo}"
        
        # Verificación de unicidad del folio generado
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM VISITAS_EMERGENCIA WHERE folio = ?", (folio,))
        existe = cursor.fetchone()[0] > 0
        conn.close()
        
        if not existe:
            print(f"Folio único generado: {folio}")
            return folio
        else:
            print(f"Folio duplicado detectado, generando alternativa...")
    
    # Estrategia de fallback para casos extremos
    timestamp = int(datetime.now().timestamp())
    folio_emergencia = f"{paciente_id}{doctor_id}{sala_id}{timestamp}"
    print(f"Usando folio de contingencia: {folio_emergencia}")
    return folio_emergencia

# ==========================================
# DISTRIBUCIÓN AUTOMÁTICA DE RECURSOS
# ==========================================

def encontrar_doctor_disponible():
    """
    Encuentra el primer doctor disponible en el sistema local.
    
    Returns:
        tuple: (id, nombre) del doctor disponible o None
    """
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    try:
        cursor.execute("SELECT id, nombre FROM DOCTORES WHERE disponible = 1 ORDER BY id LIMIT 1")
        return cursor.fetchone()
    finally:
        conn.close()

def encontrar_cama_disponible():
    """
    Encuentra la primera cama disponible en el sistema local.
    
    Returns:
        tuple: (id, numero) de la cama disponible o None
    """
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    try:
        cursor.execute("SELECT id, numero FROM CAMAS_ATENCION WHERE ocupada = 0 ORDER BY id LIMIT 1")
        return cursor.fetchone()
    finally:
        conn.close()

def distribuir_visita_automaticamente(paciente_id):
    """
    Distribuye automáticamente una visita asignando recursos disponibles.
    
    Args:
        paciente_id: Identificador del paciente a asignar
    
    Returns:
        str: Folio de la visita asignada o None en caso de error
    """
    print("Iniciando distribución automática de recursos...")
    
    # Búsqueda de recursos disponibles
    doctor = encontrar_doctor_disponible()
    if not doctor:
        print("No hay doctores disponibles para asignación automática")
        return None
    
    cama = encontrar_cama_disponible()
    if not cama:
        print("No hay camas disponibles para asignación automática")
        return None
    
    doctor_id, doctor_nombre = doctor
    cama_id, cama_numero = cama
    
    print(f"Doctor asignado automáticamente: {doctor_nombre}")
    print(f"Cama asignada automáticamente: {cama_numero}")
    
    # Protocolo de bloqueo distribuido
    if not solicitar_bloqueo_distribuido("DOCTOR", doctor_id):
        print("No se pudo bloquear el doctor en distribución automática")
        return None
        
    if not solicitar_bloqueo_distribuido("CAMA", cama_id):
        print("No se pudo bloquear la cama en distribución automática")
        liberar_bloqueo_distribuido("DOCTOR", doctor_id)
        return None
    
    # Generación del folio único
    folio = generar_folio_exacto(paciente_id, doctor_id, SERVER_PORT)
    
    # Ejecución de la asignación con consenso
    comando = {
        "accion": "ASIGNAR_RECURSOS",
        "datos": {
            "folio": folio,
            "paciente_id": paciente_id,
            "doctor_id": doctor_id,
            "cama_id": cama_id
        }
    }
    
    if propagar_transaccion_con_consenso(comando):
        print(f"Distribución automática exitosa - Folio: {folio}")
        liberar_bloqueo_distribuido("DOCTOR", doctor_id)
        liberar_bloqueo_distribuido("CAMA", cama_id)
        return folio
    else:
        print("Error en distribución automática")
        liberar_bloqueo_distribuido("DOCTOR", doctor_id)
        liberar_bloqueo_distribuido("CAMA", cama_id)
        return None

# ==========================================
# SERVIDOR Y MANEJO DE CONEXIONES
# ==========================================

def handle_client(client_socket, client_address):
    """
    Maneja las conexiones entrantes de otros nodos del sistema.
    
    Args:
        client_socket: Socket del cliente conectado
        client_address: Dirección del cliente
    """
    try:
        message = client_socket.recv(1024).decode('utf-8')
        if message:
            comando = json.loads(message)
            
            # Manejo de solicitudes de bloqueo distribuido
            if comando.get('accion') == 'SOLICITAR_BLOQUEO':
                recurso_tipo = comando['recurso_tipo']
                recurso_id = comando['recurso_id']
                
                if verificar_recurso_local(recurso_tipo, recurso_id):
                    with lock_bloqueos:
                        clave = f"{recurso_tipo}_{recurso_id}"
                        bloqueos_locales[clave] = datetime.now()
                    client_socket.send("BLOQUEO_OK".encode('utf-8'))
                    print(f"Bloqueo aprobado para {recurso_tipo} {recurso_id}")
                else:
                    client_socket.send("BLOQUEO_RECHAZADO".encode('utf-8'))
                    print(f"Bloqueo rechazado para {recurso_tipo} {recurso_id}")
                    
            elif comando.get('accion') == 'LIBERAR_BLOQUEO':
                recurso_tipo = comando['recurso_tipo']
                recurso_id = comando['recurso_id']
                with lock_bloqueos:
                    clave = f"{recurso_tipo}_{recurso_id}"
                    if clave in bloqueos_locales:
                        del bloqueos_locales[clave]
                client_socket.send("BLOQUEO_LIBERADO".encode('utf-8'))
                
            # Manejo de transacciones con consenso
            elif comando.get('accion') in ['INSERTAR_PACIENTE', 'ASIGNAR_RECURSOS', 'CERRAR_VISITA', 'INCREMENTAR_CONSECUTIVO']:
                resultado = ejecutar_transaccion_local(comando)
                if resultado:
                    client_socket.send("CONSENSO_OK".encode('utf-8'))
                    print(f"Transacción aceptada: {comando['accion']}")
                else:
                    client_socket.send("CONSENSO_RECHAZADO".encode('utf-8'))
                    
    except Exception as e:
        print(f"Error en manejo de cliente: {e}")
        client_socket.send("ERROR".encode('utf-8'))
    finally:
        client_socket.close()

def server(server_port):
    """
    Inicia el servidor para aceptar conexiones de otros nodos.
    
    Args:
        server_port: Puerto en el que escuchar conexiones
    """
    server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server_socket.bind(('0.0.0.0', server_port))
    server_socket.listen(5)
    server_socket.settimeout(1.0)
    
    while not shutdown_event.is_set():
        try:
            client_socket, addr = server_socket.accept()
            thread = threading.Thread(target=handle_client, args=(client_socket, addr))
            thread.daemon = True
            thread.start()
        except socket.timeout:
            continue
        except Exception:
            pass
    
    server_socket.close()

# ==========================================
# INTERFAZ DE USUARIO Y FUNCIONALIDADES
# ==========================================

def ver_pacientes_locales():
    """Muestra la lista de pacientes registrados localmente."""
    print("\nLista de Pacientes Registrados")
    print("------------------------------")
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT id, nombre, edad FROM PACIENTES")
    rows = cursor.fetchall()
    conn.close()
    
    if not rows:
        print("No hay pacientes registrados")
    for r in rows:
        print(f"ID: {r[0]} | {r[1]} ({r[2]} años)")

def ver_doctores_locales():
    """Muestra la lista de doctores con su estado de disponibilidad."""
    print("\nPlantilla Médica")
    print("----------------")
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT id, nombre, disponible FROM DOCTORES")
    rows = cursor.fetchall()
    conn.close()
    
    for r in rows:
        estado = "Disponible" if r[2] == 1 else "Ocupado"
        print(f"ID: {r[0]} | {r[1]} - {estado}")

def ver_camas_locales():
    """Muestra el estado de las camas de atención."""
    print("\nEstado de Camas de Atención")
    print("---------------------------")
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT id, numero, ocupada FROM CAMAS_ATENCION")
    rows = cursor.fetchall()
    conn.close()
    
    for r in rows:
        estado = "Ocupada" if r[2] == 1 else "Libre"
        print(f"ID: {r[0]} | Cama {r[1]} - {estado}")

def ver_visitas_activas():
    """Muestra las visitas de emergencia activas en el sistema."""
    print("\nVisitas de Emergencia Activas")
    print("-----------------------------")
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT folio, paciente_id, doctor_id, cama_id, estado 
        FROM VISITAS_EMERGENCIA 
        WHERE estado != 'Cerrada'
    """)
    rows = cursor.fetchall()
    conn.close()
    
    if not rows:
        print("No hay visitas activas en este momento")
        return []
    
    for r in rows:
        print(f"Folio: {r[0]} | Paciente: {r[1]} | Doctor: {r[2]} | Cama: {r[3]} | Estado: {r[4]}")
    
    return [r[0] for r in rows]

def registrar_nuevo_paciente():
    """Registra un nuevo paciente en el sistema."""
    print("\nRegistro de Nuevo Paciente")
    print("--------------------------")
    try:
        nombre = input("Nombre completo del paciente: ")
        edad = int(input("Edad del paciente: "))
        contacto = input("Información de contacto: ")
        
        comando = {
            "accion": "INSERTAR_PACIENTE",
            "datos": {
                "nombre": nombre, 
                "edad": edad, 
                "contacto": contacto
            }
        }
        
        paciente_id = ejecutar_transaccion_local(comando)
        if paciente_id:
            print(f"Paciente registrado exitosamente con ID: {paciente_id}")
            
            distribuir = input("¿Desea distribuir recursos automáticamente? (s/n): ").lower()
            if distribuir == 's':
                folio = distribuir_visita_automaticamente(paciente_id)
                if folio:
                    print(f"Distribución automática completada - Folio: {folio}")
                else:
                    print("No se pudo completar la distribución automática")
                    
            return paciente_id
        else:
            print("Error en el registro del paciente")
            return None
            
    except ValueError:
        print("Error: La edad debe ser un número válido")
        return None

def asignar_doctor_y_cama():
    """Asigna un doctor y cama específicos a un paciente con exclusión mutua."""
    print("\nAsignación Manual de Recursos")
    print("-----------------------------")
    try:
        ver_pacientes_locales()
        pid = input("\nID del paciente a asignar: ")
        if not pid: return

        ver_doctores_locales()
        did = input("ID del doctor a asignar: ")
        if not did: return

        ver_camas_locales()
        cid = input("ID de la cama a asignar: ")
        if not cid: return

        print("\nActivando protocolo de exclusión mutua...")
        
        # Bloqueo distribuido del doctor
        if not solicitar_bloqueo_distribuido("DOCTOR", did):
            print("El doctor seleccionado no está disponible")
            return
            
        # Bloqueo distribuido de la cama
        if not solicitar_bloqueo_distribuido("CAMA", cid):
            print("La cama seleccionada no está disponible")
            liberar_bloqueo_distribuido("DOCTOR", did)
            return

        # Verificación final de disponibilidad
        conn = sqlite3.connect(DB_PATH)
        cur = conn.cursor()
        
        cur.execute("SELECT disponible, nombre FROM DOCTORES WHERE id=?", (did,))
        doc = cur.fetchone()
        if not doc or doc[0] == 0:
            print(f"El doctor {did} no está disponible")
            liberar_bloqueo_distribuido("DOCTOR", did)
            liberar_bloqueo_distribuido("CAMA", cid)
            conn.close()
            return
            
        cur.execute("SELECT ocupada, numero FROM CAMAS_ATENCION WHERE id=?", (cid,))
        cama = cur.fetchone()
        if not cama or cama[0] == 1:
            print(f"La cama {cid} no está disponible")
            liberar_bloqueo_distribuido("DOCTOR", did)
            liberar_bloqueo_distribuido("CAMA", cid)
            conn.close()
            return

        conn.close()

        # Ejecución de la asignación
        folio = generar_folio_exacto(pid, did, SERVER_PORT)
        comando = {
            "accion": "ASIGNAR_RECURSOS",
            "datos": {
                "folio": folio,
                "paciente_id": pid,
                "doctor_id": did,
                "cama_id": cid
            }
        }
        
        if propagar_transaccion_con_consenso(comando):
            print(f"Asignación manual exitosa - Folio: {folio}")
            print(f"Doctor asignado: {doc[1]}")
            print(f"Cama asignada: {cama[1]}")
        else:
            print("Error en el proceso de asignación")

        # Liberación de bloqueos
        liberar_bloqueo_distribuido("DOCTOR", did)
        liberar_bloqueo_distribuido("CAMA", cid)

    except Exception as e:
        print(f"Error durante la asignación: {e}")
        # Limpieza de bloqueos en caso de error
        try:
            liberar_bloqueo_distribuido("DOCTOR", did)
            liberar_bloqueo_distribuido("CAMA", cid)
        except:
            pass

def cerrar_visita():
    """Cierra una visita activa y libera los recursos asignados."""
    print("\nCierre de Visita de Emergencia")
    print("------------------------------")
    
    folios = ver_visitas_activas()
    if not folios:
        return
    
    try:
        folio = input("\nFolio de la visita a cerrar: ")
        if not folio:
            return
        
        # Validación de la visita
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT estado FROM VISITAS_EMERGENCIA WHERE folio = ?", (folio,))
        visita = cursor.fetchone()
        conn.close()
        
        if not visita:
            print("El folio especificado no existe")
            return
            
        if visita[0] == 'Cerrada':
            print("Esta visita ya se encuentra cerrada")
            return
        
        # Ejecución del cierre
        comando = {
            "accion": "CERRAR_VISITA",
            "datos": {
                "folio": folio
            }
        }
        
        if propagar_transaccion_con_consenso(comando):
            print("Visita cerrada exitosamente")
            print("Recursos liberados para nuevas asignaciones")
        else:
            print("Error durante el cierre de la visita")
            
    except Exception as e:
        print(f"Error: {e}")

# ==========================================
# SISTEMA DE AUTENTICACIÓN Y MENÚS
# ==========================================

def login():
    """
    Maneja el proceso de autenticación de usuarios.
    
    Returns:
        tuple: (autenticado, rol, usuario) o (False, None, None) en caso de fallo
    """
    print("\nSistema de Autenticación")
    print("========================")

    intentos = 0
    while intentos < 3:
        user = input("Usuario: ")
        pwd = getpass.getpass("Contraseña: ")

        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute(
            "SELECT rol, id_personal FROM USUARIOS_SISTEMA WHERE username=? AND password=?", 
            (user, pwd)
        )
        resultado = cursor.fetchone()
        conn.close()

        if resultado:
            rol_encontrado = resultado[0]
            print(f"Autenticación exitosa - Rol: {rol_encontrado}")
            return True, rol_encontrado, user
        else:
            print("Credenciales incorrectas")
            intentos += 1

    print("Límite de intentos excedido - Cerrando sistema")
    return False, None, None

def menu_trabajador_social(usuario):
    """
    Menú principal para usuarios con rol de trabajador social.
    
    Args:
        usuario: Nombre del usuario autenticado
    """
    while True:
        print(f"\nPanel de Trabajo Social - Usuario: {usuario}")
        print("==============================================")
        print("1. Registrar nuevo paciente")
        print("2. Consultar lista de pacientes")
        print("3. Consultar plantilla médica")
        print("4. Consultar estado de camas")
        print("5. Ver visitas activas")
        print("6. Asignación manual de recursos")
        print("7. Distribución automática")
        print("9. Cerrar sesión")
        print("----------------------------------------------")

        opcion = input("Seleccione una opción: ")

        if opcion == '1': 
            registrar_nuevo_paciente()
        elif opcion == '2': 
            ver_pacientes_locales()
        elif opcion == '3': 
            ver_doctores_locales()
        elif opcion == '4': 
            ver_camas_locales()
        elif opcion == '5': 
            ver_visitas_activas()
        elif opcion == '6': 
            asignar_doctor_y_cama()
        elif opcion == '7':
            ver_pacientes_locales()
            pid = input("ID del paciente para distribución automática: ")
            if pid:
                folio = distribuir_visita_automaticamente(int(pid))
                if folio:
                    print(f"Distribución automática completada - Folio: {folio}")
        elif opcion == '9': 
            print("Cerrando sesión de trabajo social...")
            shutdown_event.set()
            break
        else: 
            print("Opción no válida")

def menu_doctor(usuario):
    """
    Menú principal para usuarios con rol de doctor.
    
    Args:
        usuario: Nombre del usuario autenticado
    """
    while True:
        print(f"\nPanel Médico - Usuario: {usuario}")
        print("==================================")
        print("1. Consultar visitas asignadas")
        print("2. Cerrar visita de emergencia")
        print("9. Cerrar sesión")
        print("----------------------------------")

        opcion = input("Seleccione una opción: ")

        if opcion == '1': 
            ver_visitas_activas()
        elif opcion == '2': 
            cerrar_visita()
        elif opcion == '9':
            print("Cerrando sesión médica...")
            shutdown_event.set()
            break
        else: 
            print("Opción no válida")

def main():
    """
    Función principal del sistema distribuido.
    Coordina la inicialización y el flujo principal de la aplicación.
    """
    # Inicialización del sistema
    init_db()
    
    # Inicio del servidor en segundo plano
    server_thread = threading.Thread(target=server, args=(SERVER_PORT,))
    server_thread.daemon = True
    server_thread.start()
    
    # Información del sistema
    print("\nSistema Distribuido de Gestión de Emergencias Médicas")
    print(f"Nodo activo en puerto: {SERVER_PORT}")
    print(f"Nodos remotos configurados: {len(NODOS_REMOTOS)}")
    
    # Proceso de autenticación
    autenticado, rol, usuario = login()
    
    if autenticado:
        try:
            if rol == 'SOCIAL':
                menu_trabajador_social(usuario)
            elif rol == 'DOCTOR':
                menu_doctor(usuario)
        except KeyboardInterrupt:
            print("\nInterrupción recibida - Cerrando sistema...")
            shutdown_event.set()
    else:
        shutdown_event.set()

    # Protocolo de cierre ordenado
    print("Finalizando servicios del sistema...")
    try:
        # Conexión local para liberar el puerto
        dummy = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        dummy.connect(('127.0.0.1', SERVER_PORT))
        dummy.close()
    except: 
        pass

    # Espera para finalización de hilos
    threading.Event().wait(1)
    print("Sistema finalizado correctamente")

if __name__ == "__main__":
    main()
