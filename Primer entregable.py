import socket
import threading
from datetime import datetime
import sqlite3
import json
import os
import getpass # Para ocultar la contraseña al escribir

# --- Configuración de Rutas ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SQL_SCHEMA_PATH = os.path.join(BASE_DIR, 'schema2.sql')
DB_PATH = os.path.join(BASE_DIR, 'emergencias.db')

# --- Configuración de Red ---
SERVER_PORT = 5555 
NODOS_REMOTOS = [
    # ('192.168.X.X', 5555), 
]

# --- Flag de Cierre ---
shutdown_event = threading.Event()

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
        
        # Lógica original de carga de schema si BD está vacía
        if not os.path.exists(DB_PATH) or os.path.getsize(DB_PATH) < 100:
             if os.path.exists(SQL_SCHEMA_PATH):
                 with open(SQL_SCHEMA_PATH, 'r') as f:
                    sql_script = f.read()
                 cursor.executescript(sql_script)
        
        conn.commit()
    except Exception as e:
        print(f"Nota DB: {e}")
    finally:
        if conn: conn.close()

def ejecutar_transaccion(comando):
    """ Ejecuta SQL recibido local o por red """
    print(f"[BD Local] Ejecutando: {comando['accion']} en {comando['tabla']}")
    # Placeholder para lógica de replicación real

# ==========================================
#      MIDDLEWARE DE RED
# ==========================================

def propagar_transaccion(comando_json):
    if not NODOS_REMOTOS: return
    for (ip, puerto) in NODOS_REMOTOS:
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(2.0)
                s.connect((ip, puerto))
                s.sendall(comando_json.encode('utf-8'))
                s.recv(1024)
        except Exception: pass

def handle_client(client_socket, client_address):
    try:
        message = client_socket.recv(1024).decode('utf-8')
        if message:
            comando = json.loads(message)
            # Si recibimos una ASIGNACION, imprimimos aviso especial
            if comando.get("accion") == "ASIGNAR_DOCTOR":
                print(f"\n📢 NOTIFICACIÓN: Doctor asignado en otro nodo.")
            else:
                print(f"Transacción recibida de {client_address}: {comando}")
            ejecutar_transaccion(comando)
            client_socket.send("OK".encode('utf-8'))
    except Exception: pass
    finally: client_socket.close()

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
        except socket.timeout: continue
        except Exception: pass
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
    if not rows: print("   (Sin registros)")
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
    for r in rows:
        estado = "🟢 Disp" if r[2] == 1 else "🔴 Ocup"
        print(f"   ID: {r[0]} | {r[1]} [{estado}]")

def ver_camas_locales():
    print("\n--- 🛏️ CAMAS ---")
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    query = "SELECT c.numero, c.ocupada, p.nombre FROM CAMAS_ATENCION c LEFT JOIN PACIENTES p ON c.paciente_id = p.id"
    cursor.execute(query)
    rows = cursor.fetchall()
    conn.close()
    for r in rows:
        estado = f"🔴 {r[2]}" if r[1] == 1 else "🟢 LIBRE"
        print(f"   {r[0]}: {estado}")

def ver_trabajadores_sociales():
    print("\n--- 📋 TRABAJO SOCIAL ---")
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT id, nombre FROM TRABAJADORES_SOCIALES")
    rows = cursor.fetchall()
    conn.close()
    for r in rows: print(f"   ID: {r[0]} | {r[1]}")

def ver_visitas_emergencia():
    print("\n--- 🚨 BITÁCORA ---")
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT folio, estado, timestamp, paciente_id FROM VISITAS_EMERGENCIA")
    rows = cursor.fetchall()
    conn.close()
    for r in rows: print(f"   📄 {r[0]} ({r[1]}) - {r[2]}")

# ==========================================
#      FUNCIONES OPERATIVAS (ESCRITURA)
# ==========================================

def registrar_nuevo_paciente():
    print("\n[Nuevo Ingreso]")
    try:
        nombre = input("Nombre: ")
        edad = int(input("Edad: "))
        contacto = input("Contacto: ")
        comando = {"accion": "INSERTAR", "tabla": "PACIENTES", "datos": {"nombre": nombre, "edad": edad}}
        ejecutar_transaccion(comando)
        print("✅ Paciente registrado.")
        propagar_transaccion(json.dumps(comando))
    except ValueError: print("Error: Datos inválidos.")

def asignar_doctor():
    print("\n--- ASIGNACIÓN DE MÉDICO ---")
    try:
        ver_pacientes_locales()
        pid = input("\nID Paciente: ")
        if not pid: return
        
        ver_doctores_locales()
        did = input("ID Doctor: ")
        if not did: return
        
        # Validaciones BD
        conn = sqlite3.connect(DB_PATH)
        cur = conn.cursor()
        
        # Chequear Doctor
        cur.execute("SELECT disponible, nombre FROM DOCTORES WHERE id=?", (did,))
        doc = cur.fetchone()
        if not doc: 
            print("❌ Doctor no existe"); conn.close(); return
        if doc[0] == 0: 
            print(f"❌ {doc[1]} está OCUPADO."); conn.close(); return
            
        # Ejecutar Asignación
        ts = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        
        # Buscar si ya tiene visita
        cur.execute("SELECT folio FROM VISITAS_EMERGENCIA WHERE paciente_id=?", (pid,))
        if cur.fetchone():
            cur.execute("UPDATE VISITAS_EMERGENCIA SET doctor_id=?, estado='En Consulta' WHERE paciente_id=?", (did, pid))
        else:
            folio = f"URG-{pid}-{did}"
            cur.execute("INSERT INTO VISITAS_EMERGENCIA (folio, paciente_id, doctor_id, sala_id, timestamp, estado) VALUES (?,?,?,1,?,'En Consulta')", (folio, pid, did, ts))
            
        cur.execute("UPDATE DOCTORES SET disponible=0 WHERE id=?", (did,))
        conn.commit()
        conn.close()
        
        print(f"✅ Asignación completada.")
        propagar_transaccion(json.dumps({"accion": "ASIGNAR_DOCTOR", "datos": {"p": pid, "d": did}}))
        
    except Exception as e: print(f"Error: {e}")

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
        # getpass oculta lo que escribes (ideal para contraseñas)
        pwd = getpass.getpass("Contraseña: ") 
        
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        # Buscamos el usuario y su rol
        cursor.execute("SELECT rol, id_personal FROM USUARIOS_SISTEMA WHERE username=? AND password=?", (user, pwd))
        resultado = cursor.fetchone()
        conn.close()
        
        if resultado:
            rol_encontrado = resultado[0] # 'SOCIAL' o 'DOCTOR'
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
        print("7. 🩺 Asignar Doctor a Paciente")
        print("9. 🚪 Cerrar Sesión / Salir")
        print("-" * 40)
        
        op = input("Opción > ")

        if op == '1': registrar_nuevo_paciente()
        elif op == '2': ver_pacientes_locales()
        elif op == '3': ver_doctores_locales()
        elif op == '4': ver_camas_locales()
        elif op == '5': ver_trabajadores_sociales()
        elif op == '6': ver_visitas_emergencia()
        elif op == '7': asignar_doctor()
        elif op == '9': 
            print("Cerrando sesión..."); shutdown_event.set(); break
        else: print("Opción no válida.")

def menu_doctor(usuario):
    """ Menú restringido para Doctores """
    while True:
        print("\n" + "="*40)
        print(f"   PANEL MÉDICO ({usuario})")
        print("="*40)
        print("1. 🤕 Ver Mis Pacientes (Pendiente)")
        print("2. 📝 Actualizar Historial Clínico (Pendiente)")
        print("9. 🚪 Cerrar Sesión / Salir")
        print("-" * 40)
        
        op = input("Opción > ")
        
        if op == '1': 
            print("Función no implementada por ahora.")
        elif op == '9':
            print("Cerrando sesión..."); shutdown_event.set(); break
        else: print("Opción no válida.")

def main():
    init_db()
    
    # Iniciar servidor en segundo plano
    t = threading.Thread(target=server, args=(SERVER_PORT,))
    t.daemon = True
    t.start()
    
    print(f"\n🖥️  SISTEMA DISTRIBUIDO HOSPITALARIO v2.0")
    print(f"📡 Nodo activo en puerto {SERVER_PORT}")
    
    # --- FLUJO DE LOGIN ---
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
    # Pequeño truco para cerrar sockets pendientes si el usuario forzó la salida
    try:
        dummy = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        dummy.connect(('127.0.0.1', SERVER_PORT))
        dummy.close()
    except: pass
    
    threading.Event().wait(1)
    print("Sistema apagado.")

if __name__ == "__main__":
    main()