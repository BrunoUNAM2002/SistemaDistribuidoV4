from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
from flask_login import login_user, logout_user, login_required, current_user
from flask_socketio import SocketIO, emit
from config import Config
from models import db, Usuario, get_metricas_dashboard
from auth import login_manager, init_default_users, get_user_info
import logging
import logging.handlers
import os
import time

# Importar sistema Bully simplificado
from bully import BullyNode

# Crear aplicación Flask con rutas correctas a templates y static
app = Flask(__name__,
            template_folder='../frontend/templates',
            static_folder='../frontend/static')
app.config.from_object(Config)

# Inicializar extensiones
db.init_app(app)
login_manager.init_app(app)
socketio = SocketIO(app, async_mode=app.config['SOCKETIO_ASYNC_MODE'])

# ============================================================================
# CONFIGURACIÓN AVANZADA DE LOGGING
# ============================================================================

def setup_logging():
    """
    Configura sistema de logging con rotación de archivos y formato estructurado.

    Features:
    - Logs rotativos (10MB max, 5 backups)
    - Formato estructurado con timestamps, niveles, componentes
    - Salida dual: consola (INFO+) y archivo (DEBUG+)
    - Identificación de nodo para correlación en sistema distribuido
    """
    # Crear directorio de logs si no existe
    log_dir = '../logs'
    if not os.path.exists(log_dir):
        os.makedirs(log_dir)

    # Formato de logs: [2025-01-19 10:30:45] [Node-1] [INFO] [bully.node] Message
    log_format = logging.Formatter(
        fmt='[%(asctime)s] [Node-%(node_id)s] [%(levelname)s] [%(name)s] %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )

    # Root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG)  # Capturar TODO a nivel raíz

    # Handler 1: Archivo rotativo (DEBUG y superior)
    file_handler = logging.handlers.RotatingFileHandler(
        filename=f'{log_dir}/node_{Config.NODE_ID}.log',
        maxBytes=10 * 1024 * 1024,  # 10MB
        backupCount=5,
        encoding='utf-8'
    )
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(log_format)

    # Handler 2: Consola (INFO y superior)
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(log_format)

    # Agregar handlers al root logger
    root_logger.addHandler(file_handler)
    root_logger.addHandler(console_handler)

    # Configurar filtros para inyectar node_id en todos los logs
    class NodeIdFilter(logging.Filter):
        def filter(self, record):
            record.node_id = Config.NODE_ID
            return True

    node_filter = NodeIdFilter()
    for handler in root_logger.handlers:
        handler.addFilter(node_filter)

    # Silenciar logs ruidosos de librerías externas
    logging.getLogger('werkzeug').setLevel(logging.WARNING)
    logging.getLogger('socketio').setLevel(logging.WARNING)
    logging.getLogger('engineio').setLevel(logging.WARNING)

    return logging.getLogger(__name__)

# Configurar logging
logger = setup_logging()

# ============================================================================
# SISTEMA BULLY SIMPLIFICADO (Variable global, se inicializa en main)
# ============================================================================
bully_manager: BullyNode = None


# ============================================================================
# CONTEXT PROCESSORS (Variables disponibles en todos los templates)
# ============================================================================

@app.context_processor
def inject_global_vars():
    """Inyecta variables globales en todos los templates"""
    return {
        'node_id': Config.NODE_ID,
        'flask_port': Config.FLASK_PORT,
        'user_info': get_user_info(current_user) if current_user.is_authenticated else None
    }


# ============================================================================
# RUTAS DE AUTENTICACIÓN
# ============================================================================

@app.route('/login', methods=['GET', 'POST'])
def login():
    """Página de login"""
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))

    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')

        user = Usuario.query.filter_by(username=username, activo=True).first()

        if user and user.check_password(password):
            login_user(user, remember=True)
            flash(f'Bienvenido, {username}!', 'success')
            logger.info(f'Usuario {username} ({user.rol}) inició sesión en nodo {Config.NODE_ID}')

            next_page = request.args.get('next')
            return redirect(next_page or url_for('dashboard'))
        else:
            flash('Usuario o contraseña incorrectos', 'danger')
            logger.warning(f'Intento de login fallido para usuario: {username}')

    return render_template('login.html')


@app.route('/logout')
@login_required
def logout():
    """Cerrar sesión"""
    username = current_user.username
    logout_user()
    flash('Sesión cerrada correctamente', 'info')
    logger.info(f'Usuario {username} cerró sesión')
    return redirect(url_for('login'))


# ============================================================================
# RUTA PRINCIPAL (DASHBOARD)
# ============================================================================

@app.route('/')
@app.route('/dashboard')
@login_required
def dashboard():
    """Dashboard principal con métricas (OPTIMIZADO)"""
    metricas = get_metricas_dashboard(id_sala=Config.NODE_ID)

    # Información del nodo actual
    nodo_info = Config.get_info_nodo_actual()

    return render_template(
        'dashboard_lite.html',  # OPTIMIZED: Usar versión lite sin Bootstrap
        metricas=metricas,
        nodo=nodo_info,
        otros_nodos=Config.get_otros_nodos_activos()
    )


# ============================================================================
# IMPORTAR BLUEPRINTS (rutas modulares)
# ============================================================================

# Importamos las rutas después de crear app para evitar imports circulares
from routes.visitas import visitas_bp
from routes.consultas import consultas_bp
from routes.api import api_bp
from routes.bully import bully_bp
from routes.cluster_api import cluster_api_bp

app.register_blueprint(visitas_bp, url_prefix='/visitas')
app.register_blueprint(consultas_bp, url_prefix='/consultas')
app.register_blueprint(api_bp, url_prefix='/api')
app.register_blueprint(bully_bp, url_prefix='/api/bully')
app.register_blueprint(cluster_api_bp)  # Ya tiene prefix /api/cluster definido


# ============================================================================
# EVENTOS WEBSOCKET
# ============================================================================

@socketio.on('connect')
def handle_connect():
    """Cliente conectado a WebSocket"""
    logger.info(f'Cliente WebSocket conectado - SID: {request.sid}')
    emit('connected', {'message': f'Conectado al nodo {Config.NODE_ID}'})


@socketio.on('disconnect')
def handle_disconnect():
    """Cliente desconectado"""
    logger.info(f'Cliente WebSocket desconectado - SID: {request.sid}')


@socketio.on('solicitar_metricas')
def handle_solicitar_metricas():
    """Cliente solicita métricas actualizadas"""
    metricas = get_metricas_dashboard(id_sala=Config.NODE_ID)
    emit('metricas_actualizadas', metricas)


@socketio.on('solicitar_bully_status')
def handle_solicitar_bully_status():
    """Cliente solicita estado del sistema Bully"""
    if bully_manager:
        status = bully_manager.get_status()
        emit('bully_status', status)
    else:
        emit('bully_status', {'error': 'Bully system not initialized'})


# Evento global: emitir cuando se crea una visita
def notificar_visita_creada(visita_data):
    """Notifica a todos los clientes conectados que se creó una visita"""
    socketio.emit('visita_creada', visita_data, broadcast=True)
    logger.info(f'Notificación broadcast: Visita creada - {visita_data.get("folio")}')


# Evento global: emitir cuando se cierra una visita
def notificar_visita_cerrada(visita_data):
    """Notifica a todos los clientes conectados que se cerró una visita"""
    socketio.emit('visita_cerrada', visita_data, broadcast=True)
    logger.info(f'Notificación broadcast: Visita cerrada - {visita_data.get("folio")}')


# Exportar funciones de notificación para usarlas en otros módulos
app.notificar_visita_creada = notificar_visita_creada
app.notificar_visita_cerrada = notificar_visita_cerrada


# Función para notificar cambios de líder
def notificar_cambio_lider(nuevo_lider_id, term):
    """Notifica a todos los clientes que cambió el líder"""
    socketio.emit('lider_cambio', {
        'nuevo_lider': nuevo_lider_id,
        'term': term,
        'timestamp': time.time()
    }, broadcast=True)
    logger.info(f'Notificación broadcast: Nuevo líder #{nuevo_lider_id} (term {term})')


app.notificar_cambio_lider = notificar_cambio_lider


# ============================================================================
# INICIALIZACIÓN DE LA BASE DE DATOS
# ============================================================================

def init_db():
    """Inicializa la base de datos y usuarios por defecto"""
    with app.app_context():
        db.create_all()
        init_default_users()
        logger.info('Base de datos inicializada correctamente')


def init_bully():
    """Inicializa y arranca el sistema Bully simplificado"""
    global bully_manager

    # Calcular puertos basados en NODE_ID
    tcp_port = 5555 + (Config.NODE_ID - 1)
    udp_port = 6000 + (Config.NODE_ID - 1)

    # Construir diccionario de cluster_nodes en formato {node_id: (ip, tcp_port, udp_port)}
    # BullyNode espera TODOS los nodos del cluster (incluido él mismo)
    cluster_nodes = {}
    for nodo in Config.OTROS_NODOS:
        node_id = nodo['id']
        ip = 'localhost'  # Todos en localhost para desarrollo
        tcp = 5555 + (node_id - 1)
        udp = 6000 + (node_id - 1)
        cluster_nodes[node_id] = (ip, tcp, udp)

    logger.info('='*60)
    logger.info('🚀 Inicializando Sistema Bully Simplificado')
    logger.info(f'   Node ID: {Config.NODE_ID}')
    logger.info(f'   TCP Port: {tcp_port}')
    logger.info(f'   UDP Port: {udp_port}')
    logger.info(f'   Cluster: {len(cluster_nodes)} nodes')
    logger.info('='*60)

    # Crear instancia del Bully Node
    bully_manager = BullyNode(
        node_id=Config.NODE_ID,
        cluster_nodes=cluster_nodes,
        tcp_port=tcp_port,
        udp_port=udp_port
    )

    # Iniciar el sistema Bully
    bully_manager.start()

    # Hacer accesible globalmente en app
    app.bully_manager = bully_manager

    logger.info('✅ Sistema Bully iniciado correctamente')

    return bully_manager


# ============================================================================
# MANEJO DE ERRORES
# ============================================================================

@app.errorhandler(404)
def not_found(error):
    """Página no encontrada"""
    return render_template('404.html'), 404


@app.errorhandler(403)
def forbidden(error):
    """Acceso prohibido"""
    return render_template('403.html'), 403


@app.errorhandler(500)
def internal_error(error):
    """Error interno del servidor"""
    db.session.rollback()
    logger.error(f'Error 500: {error}')
    return render_template('500.html'), 500


# ============================================================================
# PUNTO DE ENTRADA
# ============================================================================

if __name__ == '__main__':
    # Inicializar BD si no existe
    init_db()

    # Inicializar sistema Bully
    bully_manager = init_bully()

    # Información de inicio
    logger.info('='*60)
    logger.info(f'🏥 Sistema de Emergencias Médicas - Nodo {Config.NODE_ID}')
    logger.info(f'🌐 Flask corriendo en http://localhost:{Config.FLASK_PORT}')
    logger.info(f'📡 Puerto TCP (Bully): {5555 + (Config.NODE_ID - 1)}')
    logger.info(f'📡 Puerto UDP (Heartbeat): {6000 + (Config.NODE_ID - 1)}')
    logger.info(f'💾 Base de datos: {Config.SQLALCHEMY_DATABASE_URI}')
    logger.info(f'👑 Bully Status: {bully_manager.get_status()["state"]}')
    logger.info('='*60)

    try:
        # Iniciar servidor Flask con SocketIO
        socketio.run(
            app,
            host='0.0.0.0',
            port=Config.FLASK_PORT,
            debug=True,
            use_reloader=False,  # Desactivar reloader para evitar doble inicio del Bully
            allow_unsafe_werkzeug=True  # Para desarrollo
        )
    finally:
        # Detener Bully al salir
        if bully_manager:
            logger.info('Deteniendo sistema Bully...')
            bully_manager.stop()
            logger.info('Sistema Bully detenido')
