import socket
import threading
from datetime import datetime
import sqlite3
import json
import os

# --- Configuración de Rutas ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SQL_SCHEMA_PATH = os.path.join(BASE_DIR, 'schema2.sql')
DB_PATH = os.path.join(BASE_DIR, 'emergencias.db')

# --- Configuración de Red ---
# Puerto en el que este nodo escuchará
SERVER_PORT = 5555 
# Lista de otros nodos (Salas) a los que notificaremos cambios.
# NOTA: ¡Debes actualizar esto con las IPs y puertos de tus otros nodos!
NODOS_REMOTOS = [
    # ('IP_SALA_2', 5556),
    # ('IP_SALA_3', 5557),
]

# --- Flag de Cierre ---
shutdown_event = threading.Event()

# --- Funciones de Base de Datos ---

def init_db():
    """
    Usa los 'planos' (schema2.sql) para construir
    el 'edificio' (emergencias.db).
    """
    print(f"Inicializando la base de datos en: {DB_PATH}")
    conn = None
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("PRAGMA foreign_keys = ON;")
        
        print(f"Leyendo 'planos' desde: {SQL_SCHEMA_PATH}")
        with open(SQL_SCHEMA_PATH, 'r') as f:
            sql_script = f.read()
            
        cursor.executescript(sql_script)
        conn.commit()
        print(f"¡Éxito! Base de datos y tablas creadas en {DB_PATH}")

    except FileNotFoundError:
        print(f"ERROR: No se encontró el archivo de schema en: {SQL_SCHEMA_PATH}")
    except Exception as e:
        print(f"Error al inicializar la base de datos: {e}")
    finally:
        if conn:
            conn.close()

def ejecutar_transaccion(comando):
    """
    Ejecuta un comando de transacción (recibido por red o local)
    en la base de datos local.
    """
    # (Esta es una función placeholder. La lógica real es más compleja)
    print(f"[BD Local] Ejecutando transacción: {comando['accion']} en {comando['tabla']}")
    
    # --- Lógica futura ---
    # 1. Conectar a DB_PATH
    # 2. Construir el SQL (ej: INSERT INTO PACIENTES...)
    # 3. Ejecutar y comitear
    # 4. Manejar conflictos (ej. si dos nodos insertan el mismo folio)


# --- Funciones de Red (Middleware) ---

def propagar_transaccion(comando_json):
    """
    Envía un comando JSON a todos los otros nodos conocidos.
    (Reemplaza a 'send_message')
    """
    print(f"Propagando transacción a {len(NODOS_REMOTOS)} nodos...")
    for (ip, puerto) in NODOS_REMOTOS:
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(2.0) # Timeout corto
                s.connect((ip, puerto))
                s.sendall(comando_json.encode('utf-8'))
                respuesta = s.recv(1024).decode('utf-8')
                print(f"Respuesta de {ip}:{puerto}: {respuesta}")
        except Exception as e:
            print(f"Error al propagar a {ip}:{puerto}: {e}")

def handle_client(client_socket, client_address):
    """
    Maneja una conexión entrante de OTRO nodo.
    Espera recibir una transacción JSON.
    (Reemplaza la lógica de chat)
    """
    print(f"Recibiendo transacción de: {client_address}")
    try:
        # Esperamos recibir una transacción completa
        # (Para robustez, se necesitaría un búfer aquí)
        message = client_socket.recv(1024).decode('utf-8')
        if not message:
            return # Conexión vacía

        comando = json.loads(message)
        print(f"Comando JSON recibido: {comando}")
        
        # Ejecuta la transacción recibida en nuestra BD local
        ejecutar_transaccion(comando)
        
        # Enviar confirmación
        response = "TRANSACCION_OK"
        client_socket.send(response.encode('utf-8'))

    except json.JSONDecodeError:
        print(f"Error: Se recibió un mensaje no-JSON de {client_address}")
    except Exception as e:
        print(f"Error en handle_client: {e}")
    finally:
        client_socket.close()

def server(server_port):
    """
    Función del servidor que escucha conexiones entrantes
    y las delega a 'handle_client' en un nuevo hilo.
    (Actualizada para no usar 'messages')
    """
    server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server_socket.bind(('0.0.0.0', server_port))
    server_socket.listen(5)
    server_socket.settimeout(1.0)
    print(f"Servidor escuchando en el puerto {server_port}...")
    
    while not shutdown_event.is_set():
        try:
            client_socket, client_address = server_socket.accept()
            print(f"\nConexión entrante de {client_address}")
            
            thread = threading.Thread(target=handle_client, args=(client_socket, client_address))
            thread.daemon = True
            thread.start()
        except socket.timeout:
            continue
        except Exception as e:
            if not shutdown_event.is_set():
                print(f"Error en servidor: {e}")
    
    server_socket.close()
    print("Servidor cerrado correctamente")

# --- Funciones de la Aplicación (Menú) ---

def registrar_nuevo_paciente():
    """
    Lógica para la Opción 1 del menú.
    Registra un paciente localmente y propaga el cambio.
    """
    print("\n[Registrar Nuevo Paciente]")
    try:
        nombre = input("Nombre: ")
        edad = int(input("Edad: "))
        contacto = input("Contacto: ")
        
        # 1. Crear el comando de transacción
        comando = {
            "accion": "INSERTAR",
            "tabla": "PACIENTES",
            "datos": {
                "nombre": nombre,
                "edad": edad,
                "sexo": "N/D", # Placeholder
                "contacto": contacto
            }
        }
        
        # 2. Ejecutar la transacción en NUESTRA BD local
        ejecutar_transaccion(comando)
        print("Paciente registrado localmente.")

        # 3. Propagar la transacción a otros nodos
        comando_json = json.dumps(comando)
        propagar_transaccion(comando_json)

    except ValueError:
        print("Error: La edad debe ser un número.")
    except Exception as e:
        print(f"Error al registrar paciente: {e}")

def ver_pacientes_locales():
    """
    Lógica para la Opción 2 del menú.
    Se conecta a la BD local y muestra los pacientes.
    """
    print("\n[Pacientes Registrados Localmente]")
    conn = None
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT id, nombre, edad, contacto FROM PACIENTES")
        pacientes = cursor.fetchall()
        
        if not pacientes:
            print("No hay pacientes registrados.")
            return
            
        print(f"Mostrando {len(pacientes)} pacientes:")
        for p in pacientes:
            print(f"  ID: {p[0]}, Nombre: {p[1]}, Edad: {p[2]}, Contacto: {p[3]}")
            
    except Exception as e:
        print(f"Error al consultar la base de datos: {e}")
    finally:
        if conn:
            conn.close()

# --- Función Principal ---

def main():
    """
    Función principal que inicializa la BD,
    inicia el servidor y muestra el menú de usuario.
    (Reemplaza la lógica de chat)
    """
    # 1. Inicializa la base de datos
    init_db()  
    
    # 2. Inicia el servidor de escucha en su propio hilo
    server_thread = threading.Thread(target=server, args=(SERVER_PORT,))
    server_thread.daemon = True
    server_thread.start()
    
    print("\n" + "="*50)
    print("  SISTEMA DE GESTIÓN DE EMERGENCIAS - NODO SALA 1")
    print("="*50 + "\n")
    
    # 3. Bucle principal de la aplicación (Menú)
    try:
        while True:
            print("\n--- Menú Principal ---")
            print("1. Registrar Nuevo Paciente")
            print("2. Ver Pacientes Locales")
            print("9. Salir")
            opcion = input("Seleccione una opción: ")

            if opcion == '1':
                registrar_nuevo_paciente()
            elif opcion == '2':
                ver_pacientes_locales()
            elif opcion == '9':
                print("\nCerrando el programa...")
                shutdown_event.set() # Notifica al hilo servidor
                break
            else:
                print("Opción no válida. Intente de nuevo.")

    except KeyboardInterrupt:
        print("\n\nCerrando el programa con Ctrl+C...")
        shutdown_event.set()
    
    # Esperar un momento para que los threads terminen
    print("Esperando a que los threads terminen...")
    threading.Event().wait(2)
    print("Programa cerrado correctamente. ¡Hasta luego!")

if __name__ == "__main__":
    main()