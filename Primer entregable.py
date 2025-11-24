import socket
import threading
from datetime import datetime
import sqlite3
import json
import os
import getpass  # Para ocultar la contraseña al escribir
import time

# --- Configuración de Rutas ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SQL_SCHEMA_PATH = os.path.join(BASE_DIR, 'schema2.sql')
DB_PATH = os.path.join(BASE_DIR, 'emergencias.db')

# --- Configuración de Red (AJUSTA ESTO POR NODO) ---
SERVER_PORT = 5555  # PUERTO DE ESTE NODO (cámbialo en cada nodo)
NODOS_REMOTOS = [
    # EJEMPLO para 4 nodos en localhost:
    # En el nodo 5555:
    # ('localhost', 5556),
    # ('localhost', 5557),
    # ('localhost', 5558),
]

# --- Flag de Cierre ---
shutdown_event = threading.Event()

# ==========================================
#      ESTADO EXCLUSIÓN MUTUA (DISTRIBUIDA)
# ==========================================

# Usamos el puerto como ID de nodo para desempates
NODE_ID = SERVER_PORT
mutex_state_lock = threading.Lock()

want_cs = False          # Este nodo quiere entrar a sección crítica
in_cs = False            # Este nodo está en sección crítica
request_ts = 0.0         # Timestamp de nuestra solicitud
pending_replies = 0      # Respuestas que faltan
deferred_requests = []   # Puertos de nodos a los que responderemos después


def _now_ts():
    return time.time()


def enviar_mensaje_a(ip, puerto, obj):
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(2.0)
            s.connect((ip, puerto))
            s.sendall(json.dumps(obj).encode('utf-8'))
            # Para MUTEX no necesitamos respuesta
    except Exception:
        pass


def broadcast_mutex(msg):
    for (ip, puerto) in NODOS_REMOTOS:
        enviar_mensaje_a(ip, puerto, msg)


def pedir_mutex():
    """
    Algoritmo tipo Ricart–Agrawala simplificado:
    - Marcamos intención de entrar a SC.
    - Enviamos REQUEST a todos los nodos remotos.
    - Esperamos a recibir REPLY de todos.
    """
    global want_cs, in_cs, request_ts, pending_replies
    with mutex_state_lock:
        want_cs = True
        in_cs = False
        request_ts = _now_ts()
        pending_replies = len(NODOS_REMOTOS)

    if pending_replies > 0:
        msg = {
            "tipo": "MUTEX",
            "accion": "REQUEST",
            "from": NODE_ID,
            "ts": request_ts
        }
        broadcast_mutex(msg)

        # Esperar a que pending_replies sea 0
        while True:
            with mutex_state_lock:
                if pending_replies <= 0:
                    in_cs = True
                    break
            time.sleep(0.01)
    else:
        # Solo nodo -> entra directo
        with mutex_state_lock:
            in_cs = True


def liberar_mutex():
    """
    Salir de sección crítica:
    - Marcamos que ya no queremos estar en SC.
    - Enviamos RELEASE.
    - Enviamos REPLY a los que habíamos diferido.
    """
    global want_cs, in_cs, deferred_requests
    with mutex_state_lock:
        want_cs = False
        in_cs = False
        to_reply = deferred_requests[:]
        deferred_requests = []

    # Avisar RELEASE (informativo)
    msg_rel = {
        "tipo": "MUTEX",
        "accion": "RELEASE",
        "from": NODE_ID
    }
    broadcast_mutex(msg_rel)

    # Responder a los que teníamos diferidos
    for target_port in to_reply:
        enviar_mutex_reply(target_port)


def enviar_mutex_reply(target_port):
    msg = {
        "tipo": "MUTEX",
        "accion": "REPLY",
        "from": NODE_ID
    }
    enviar_mensaje_a('localhost', target_port)


def handle_mutex_message(msg):
    """
    Lógica básica:
    - Si estoy en SC -> difiero.
    - Si quiero entrar a SC y mi (ts, id) tiene prioridad -> difiero.
    - En caso contrario respondo REPLY inmediato.
    """
    global pending_replies, deferred_requests, request_ts, want_cs, in_cs

    accion = msg.get("accion")
    from_port = msg.get("from")

    if accion == "REQUEST":
        their_ts = msg.get("ts", 0.0)
        with mutex_state_lock:
            defer = False
            if in_cs:
                defer = True
            elif want_cs:
                # Prioridad: menor timestamp; si empate, menor NODE_ID
                if (request_ts, NODE_ID) < (their_ts, from_port):
                    defer = True

            if defer:
                if from_port not in deferred_requests:
                    deferred_requests.append(from_port)
            else:
                enviar_mutex_reply(from_port)

    elif accion == "REPLY":
        with mutex_state_lock:
            pending_replies -= 1

    elif accion == "RELEASE":
        # No necesitamos hacer nada extra aquí
        pass


# ==========================================
#      GESTIÓN DE BASE DE DATOS
# ==========================================

def init_db():
    print(f"Verificando base de datos en: {DB_PATH}")
    conn = None
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("PRAGMA foreign_keys = ON;")
        
        # Creamos la tabla de usuarios si no existe (por seguridad)
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS USUARIOS_SISTEMA (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            rol TEXT NOT NULL,
            id_personal INTEGER
        )
        """)
        
        # Cargar schema si la BD está vacía
        if not os.path.exists(DB_PATH) or os.path.getsize(DB_PATH) < 100:
            if os.path.exists(SQL_SCHEMA_PATH):
                with open(SQL_SCHEMA_PATH, 'r') as f:
                    sql_script = f.read()
                cursor.executescript(sql_script)
        
        conn.commit()
    except Exception as e:
        print(f"Nota DB: {e}")
    finally:
        if conn:
            conn.close()


def ejecutar_transaccion(comando):
    """ Ejecuta SQL recibido local o por red (aquí podrías meter lógica real). """
    print(f"[BD Local] Ejecutando: {comando.get('accion')} en {comando.get('tabla')}")
    # Aquí podrías mapear 'INSERTAR', 'UPDATE', etc. a SQL real.


# ==========================================
#      MIDDLEWARE DE RED
# ==========================================

def propagar_transaccion(comando_json):
    if not NODOS_REMOTOS:
        return
    for (ip, puerto) in NODOS_REMOTOS:
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(2.0)
                s.connect((ip, puerto))
                s.sendall(comando_json.encode('utf-8'))
                s.recv(1024)
        except Exception:
            pass


def handle_client(client_socket, client_address):
    try:
        message = client_socket.recv(4096).decode('utf-8')
        if not message:
            return
        comando = json.loads(message)

        # ¿Es mensaje de MUTEX?
        if comando.get("tipo") == "MUTEX":
            handle_mutex_message(comando)
            client_socket.send("OK".encode('utf-8'))
            return

        # Transacción "normal"
        if comando.get("accion") == "ASIGNAR_DOCTOR_Y_CAMA":
            print(f"\n📢 NOTIFICACIÓN: Asignación de doctor y cama en otro nodo.")
        else:
            print(f"Transacción recibida de {client_address}: {comando}")
        ejecutar_transaccion(comando)
        client_socket.send("OK".encode('utf-8'))

    except Exception as e:
        print(f"Error en handle_client: {e}")
    finally:
        client_socket.close()


def server(server_port):
    server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server_socket.bind(('0.0.0.0', server_port))
    server_socket.listen(5)
    server_socket.settimeout(1.0)
    while not shutdown_event.is_set():
        try:
            client_socket, addr = server_socket.accept()
            t = threading.Thread(target=handle_client, args=(client_socket, addr))
            t.daemon = True
            t.start()
        except socket.timeout:
            continue
        except Exception as e:
            print(f"Error en server: {e}")
    server_socket.close()


# ==========================================
#      FUNCIONES DEL SISTEMA (VISUALIZACIÓN)
# ==========================================

def ver_pacientes_locales():
    print("\n--- 🤕 PACIENTES Y MÉDICO ASIGNADO ---")
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    query = """
        SELECT p.id, p.nombre, p.edad, d.nombre
        FROM PACIENTES p
        LEFT JOIN VISITAS_EMERGENCIA v ON p.id = v.paciente_id
        LEFT JOIN DOCTORES d ON v.doctor_id = d.id
    """
    cursor.execute(query)
    rows = cursor.fetchall()
    conn.close()
    if not rows:
        print("   (Sin registros)")
        return
    for r in rows:
        medico = f"✅ {r[3]}" if r[3] else "⚠️  SIN ASIGNAR"
        print(f"   ID: {r[0]} | {r[1]} ({r[2]}a) -> {medico}")


def ver_doctores_locales():
    print("\n--- 👨‍⚕️ PLANTILLA MÉDICA ---")
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT id, nombre, disponible FROM DOCTORES")
    rows = cursor.fetchall()
    conn.close()
    if not rows:
        print("   (Sin registros)")
        return
    for r in rows:
        estado = "🟢 Disp" if r[2] == 1 else "🔴 Ocup"
        print(f"   ID: {r[0]} | {r[1]} [{estado}]")


def ver_camas_locales():
    print("\n--- 🛏️ CAMAS ---")
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    query = """
        SELECT c.id, c.numero, c.ocupada, p.nombre
        FROM CAMAS_ATENCION c
        LEFT JOIN PACIENTES p ON c.paciente_id = p.id
    """
    cursor.execute(query)
    rows = cursor.fetchall()
    conn.close()
    if not rows:
        print("   (Sin registros)")
        return
    for r in rows:
        estado = f"🔴 {r[3]}" if r[2] == 1 else "🟢 LIBRE"
        print(f"   ID {r[0]} | Cama {r[1]}: {estado}")


def ver_trabajadores_sociales():
    print("\n--- 📋 TRABAJO SOCIAL ---")
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT id, nombre FROM TRABAJADORES_SOCIALES")
    rows = cursor.fetchall()
    conn.close()
    if not rows:
        print("   (Sin registros)")
        return
    for r in rows:
        print(f"   ID: {r[0]} | {r[1]}")


def ver_visitas_emergencia():
    print("\n--- 🚨 BITÁCORA ---")
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT folio, estado, timestamp, paciente_id, doctor_id, cama_id, sala_id
        FROM VISITAS_EMERGENCIA
    """)
    rows = cursor.fetchall()
    conn.close()
    if not rows:
        print("   (Sin registros)")
        return
    for r in rows:
        print(f"   📄 {r[0]} | {r[1]} | {r[2]} | Paciente {r[3]} | Doctor {r[4]} | Cama {r[5]} | Sala {r[6]}")


# ==========================================
#      FUNCIONES OPERATIVAS (ESCRITURA)
# ==========================================

def registrar_nuevo_paciente():
    print("\n[Nuevo Ingreso]")
    try:
        nombre = input("Nombre: ")
        edad = int(input("Edad: "))
        sexo = input("Sexo (M/F): ")
        contacto = input("Contacto: ")
        conn = sqlite3.connect(DB_PATH)
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO PACIENTES (nombre, edad, sexo, contacto)
            VALUES (?, ?, ?, ?)
        """, (nombre, edad, sexo, contacto))
        conn.commit()
        conn.close()
        print("✅ Paciente registrado localmente.")
        # Podrías propagar esta inserción como transacción si quieres
    except ValueError:
        print("Error: Datos inválidos.")
    except Exception as e:
        print(f"Error en registrar_nuevo_paciente: {e}")


def asignar_doctor():
    """
    Asignación de médico + cama con EXCLUSIÓN MUTUA distribuida.
    Cumple el requisito: antes de asignar doctor y cama se toma el mutex.
    """
    print("\n--- ASIGNACIÓN DE MÉDICO Y CAMA (con exclusión mutua) ---")
    try:
        ver_pacientes_locales()
        pid = input("\nID Paciente: ")
        if not pid:
            return

        ver_doctores_locales()
        did = input("ID Doctor (vacío para elegir automáticamente): ")

        # ==============================
        #   ENTRAR A SECCIÓN CRÍTICA
        # ==============================
        print("🔒 Solicitando permiso a otros nodos (mutex distribuido)...")
        pedir_mutex()
        print("✅ Permiso otorgado, entrando a sección crítica.")

        conn = sqlite3.connect(DB_PATH)
        cur = conn.cursor()

        # --- Elegir doctor ---
        if did:
            cur.execute("SELECT disponible, nombre, sala_id FROM DOCTORES WHERE id=?", (did,))
            doc = cur.fetchone()
            if not doc:
                print("❌ Doctor no existe")
                conn.close()
                return
            if doc[0] == 0:
                print(f"❌ {doc[1]} está OCUPADO.")
                conn.close()
                return
            sala_doctor = doc[2]
        else:
            cur.execute("SELECT id, nombre, sala_id FROM DOCTORES WHERE disponible=1 LIMIT 1")
            doc = cur.fetchone()
            if not doc:
                print("❌ No hay doctores disponibles.")
                conn.close()
                return
            did = doc[0]
            sala_doctor = doc[2]
            print(f"👨‍⚕️ Doctor asignado automáticamente: {doc[1]} (ID {did})")

        # --- Elegir cama disponible ---
        cur.execute("""
            SELECT id, numero
            FROM CAMAS_ATENCION
            WHERE ocupada=0
            LIMIT 1
        """)
        cama = cur.fetchone()
        if not cama:
            print("❌ No hay camas disponibles.")
            conn.close()
            return
        cama_id, cama_numero = cama
        print(f"🛏️ Cama asignada: {cama_numero} (ID {cama_id})")

        ts = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        # --- Crear o actualizar visita activa del paciente ---
        cur.execute("""
            SELECT folio FROM VISITAS_EMERGENCIA
            WHERE paciente_id=? AND estado!='Cerrada'
        """, (pid,))
        existe = cur.fetchone()

        if existe:
            folio = existe[0]
            cur.execute("""
                UPDATE VISITAS_EMERGENCIA
                SET doctor_id=?, cama_id=?, sala_id=?, estado='En Consulta', timestamp=?
                WHERE folio=?
            """, (did, cama_id, sala_doctor, ts, folio))
        else:
            # Consecutivo sencillo para la visita
            cur.execute("SELECT COUNT(*) FROM VISITAS_EMERGENCIA")
            consecutivo = cur.fetchone()[0] + 1
            # FOLIO = IDPACIENTE + IDDOCTOR + SALA + consecutivo
            folio = f"{pid}-{did}-{sala_doctor}-{consecutivo}"

            cur.execute("""
                INSERT INTO VISITAS_EMERGENCIA
                (folio, paciente_id, doctor_id, cama_id, trabajador_social_id, sala_id, timestamp, estado)
                VALUES (?, ?, ?, ?, NULL, ?, ?, 'En Consulta')
            """, (folio, pid, did, cama_id, sala_doctor, ts))

        # --- Marcar doctor y cama como ocupados ---
        cur.execute("UPDATE DOCTORES SET disponible=0 WHERE id=?", (did,))
        cur.execute("""
            UPDATE CAMAS_ATENCION
            SET ocupada=1, paciente_id=?
            WHERE id=?
        """, (pid, cama_id))

        conn.commit()
        conn.close()

        print(f"✅ Asignación completada.")
        print(f"   FOLIO: {folio}")
        print(f"   Doctor ID {did} | Cama ID {cama_id}")

        # Propagar a otros nodos como evento lógico de negocio
        propagar_transaccion(json.dumps({
            "accion": "ASIGNAR_DOCTOR_Y_CAMA",
            "tabla": "VISITAS_EMERGENCIA",
            "datos": {
                "folio": folio,
                "paciente_id": pid,
                "doctor_id": did,
                "cama_id": cama_id,
                "sala_id": sala_doctor,
                "timestamp": ts
            }
        }))

    except Exception as e:
        print(f"Error en asignar_doctor: {e}")
    finally:
        print("🔓 Liberando mutex distribuido...")
        liberar_mutex()


# ==========================================
#      SISTEMA DE LOGIN Y MENÚS
# ==========================================

def login():
    """
    Solicita credenciales y retorna (True, rol, nombre) si es exitoso.
    """
    print("\n🔐 INICIO DE SESIÓN REQUERIDO")
    print("-----------------------------")
    
    intentos = 0
    while intentos < 3:
        user = input("Usuario: ")
        pwd = getpass.getpass("Contraseña: ")
        
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("""
            SELECT rol, id_personal
            FROM USUARIOS_SISTEMA
            WHERE username=? AND password=?
        """, (user, pwd))
        resultado = cursor.fetchone()
        conn.close()
        
        if resultado:
            rol_encontrado = resultado[0]  # 'SOCIAL' o 'DOCTOR'
            print(f"\n✅ Bienvenido. Accediendo como: {rol_encontrado}")
            return True, rol_encontrado, user
        else:
            print("❌ Credenciales incorrectas. Intente de nuevo.")
            intentos += 1
            
    print("⛔ Demasiados intentos fallidos. Cerrando sistema.")
    return False, None, None


def menu_trabajador_social(usuario):
    """ Menú completo para Trabajo Social """
    while True:
        print("\n" + "="*40)
        print(f"   PANEL DE TRABAJO SOCIAL ({usuario})")
        print("="*40)
        print("1. ➕ Registrar Nuevo Paciente")
        print("2. 🤕 Ver Pacientes")
        print("3. 👨‍⚕️ Ver Doctores")
        print("4. 🛏️ Ver Camas")
        print("5. 📋 Ver Trabajadores Sociales")
        print("6. 🚨 Ver Bitácora de Visitas")
        print("7. 🩺 Asignar Doctor y Cama a Paciente")
        print("9. 🚪 Cerrar Sesión / Salir")
        print("-" * 40)
        
        op = input("Opción > ")

        if op == '1':
            registrar_nuevo_paciente()
        elif op == '2':
            ver_pacientes_locales()
        elif op == '3':
            ver_doctores_locales()
        elif op == '4':
            ver_camas_locales()
        elif op == '5':
            ver_trabajadores_sociales()
        elif op == '6':
            ver_visitas_emergencia()
        elif op == '7':
            asignar_doctor()
        elif op == '9':
            print("Cerrando sesión...")
            shutdown_event.set()
            break
        else:
            print("Opción no válida.")


def menu_doctor(usuario):
    """ Menú restringido para Doctores """
    while True:
        print("\n" + "="*40)
        print(f"   PANEL MÉDICO ({usuario})")
        print("="*40)
        print("1. 🤕 Ver Pacientes")
        print("6. 🚨 Ver Bitácora de Visitas")
        print("9. 🚪 Cerrar Sesión / Salir")
        print("-" * 40)
        
        op = input("Opción > ")
        
        if op == '1':
            ver_pacientes_locales()
        elif op == '6':
            ver_visitas_emergencia()
        elif op == '9':
            print("Cerrando sesión...")
            shutdown_event.set()
            break
        else:
            print("Opción no válida.")


def main():
    init_db()
    
    # Iniciar servidor en segundo plano
    t = threading.Thread(target=server, args=(SERVER_PORT,))
    t.daemon = True
    t.start()
    
    print(f"\n🖥️  SISTEMA DISTRIBUIDO HOSPITALARIO v2.0")
    print(f"📡 Nodo activo en puerto {SERVER_PORT}")
    
    autenticado, rol, usuario = login()
    
    if autenticado:
        try:
            if rol == 'SOCIAL':
                menu_trabajador_social(usuario)
            elif rol == 'DOCTOR':
                menu_doctor(usuario)
            else:
                print("Rol desconocido. Contacte al administrador.")
                shutdown_event.set()
        except KeyboardInterrupt:
            shutdown_event.set()
    else:
        shutdown_event.set()

    print("Esperando cierre de hilos...")
    try:
        dummy = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        dummy.connect(('127.0.0.1', SERVER_PORT))
        dummy.close()
    except:
        pass
    
    threading.Event().wait(1)
    print("Sistema apagado.")


if __name__ == "__main__":
    main()

