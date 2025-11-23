"""
API REST para comunicación inter-nodos del cluster.
Permite que los nodos consulten datos de otros nodos para agregación distribuida.
"""
from flask import Blueprint, jsonify, request
from models import Doctor, Paciente, Cama, TrabajadorSocial, VisitaEmergencia, db, replicate_visit_to_cluster
from config import Config
import logging
import threading
from datetime import datetime

cluster_api_bp = Blueprint('cluster_api', __name__, url_prefix='/api/cluster')
logger = logging.getLogger(__name__)

# Lock para exclusión mutua en creación de visitas (solo usado por el líder)
visit_creation_lock = threading.Lock()


@cluster_api_bp.route('/health', methods=['GET'])
def health_check():
    """
    Health check endpoint para verificar que el nodo está disponible.

    Returns:
        JSON con status del nodo y NODE_ID
    """
    return jsonify({
        'status': 'ok',
        'node_id': Config.NODE_ID,
        'message': 'Node is healthy'
    }), 200


@cluster_api_bp.route('/doctors', methods=['GET'])
def get_doctors():
    """
    Retorna lista de doctores de ESTA sala.
    Otros nodos usan este endpoint para consultar doctores remotos.

    Query params:
        - disponible: (opcional) 'true' o 'false' para filtrar por disponibilidad
        - activo: (opcional) 'true' o 'false' para filtrar por estado activo

    Returns:
        JSON array con doctores
    """
    try:
        query = Doctor.query.filter_by(id_sala=Config.NODE_ID)

        # Filtros opcionales
        if request.args.get('disponible') == 'true':
            query = query.filter_by(disponible=True)
        elif request.args.get('disponible') == 'false':
            query = query.filter_by(disponible=False)

        if request.args.get('activo') == 'true':
            query = query.filter_by(activo=True)
        elif request.args.get('activo') == 'false':
            query = query.filter_by(activo=False)

        doctores = query.all()

        return jsonify({
            'node_id': Config.NODE_ID,
            'count': len(doctores),
            'doctors': [{
                'id_doctor': d.id_doctor,
                'nombre': d.nombre,
                'especialidad': d.especialidad,
                'disponible': d.disponible,
                'activo': d.activo,
                'id_sala': d.id_sala
            } for d in doctores]
        }), 200

    except Exception as e:
        logger.error(f"Error en /api/cluster/doctors: {e}")
        return jsonify({'error': str(e)}), 500


@cluster_api_bp.route('/beds', methods=['GET'])
def get_beds():
    """
    Retorna lista de camas de ESTA sala.

    Query params:
        - ocupada: (opcional) 'true' o 'false' para filtrar por ocupación

    Returns:
        JSON array con camas
    """
    try:
        query = Cama.query.filter_by(id_sala=Config.NODE_ID)

        # Filtros opcionales
        if request.args.get('ocupada') == 'true':
            query = query.filter_by(ocupada=True)
        elif request.args.get('ocupada') == 'false':
            query = query.filter_by(ocupada=False)

        camas = query.all()

        return jsonify({
            'node_id': Config.NODE_ID,
            'count': len(camas),
            'beds': [{
                'id_cama': c.id_cama,
                'numero': c.numero,
                'ocupada': c.ocupada,
                'id_sala': c.id_sala,
                'id_paciente': c.id_paciente,
                'paciente_nombre': c.paciente_actual.nombre if c.paciente_actual else None
            } for c in camas]
        }), 200

    except Exception as e:
        logger.error(f"Error en /api/cluster/beds: {e}")
        return jsonify({'error': str(e)}), 500


@cluster_api_bp.route('/social-workers', methods=['GET'])
def get_social_workers():
    """
    Retorna lista de trabajadores sociales de ESTA sala.

    Query params:
        - activo: (opcional) 'true' o 'false' para filtrar por estado activo

    Returns:
        JSON array con trabajadores sociales
    """
    try:
        query = TrabajadorSocial.query.filter_by(id_sala=Config.NODE_ID)

        # Filtros opcionales
        if request.args.get('activo') == 'true':
            query = query.filter_by(activo=True)
        elif request.args.get('activo') == 'false':
            query = query.filter_by(activo=False)

        trabajadores = query.all()

        return jsonify({
            'node_id': Config.NODE_ID,
            'count': len(trabajadores),
            'social_workers': [{
                'id_trabajador': ts.id_trabajador,
                'nombre': ts.nombre,
                'activo': ts.activo,
                'id_sala': ts.id_sala
            } for ts in trabajadores]
        }), 200

    except Exception as e:
        logger.error(f"Error en /api/cluster/social-workers: {e}")
        return jsonify({'error': str(e)}), 500


@cluster_api_bp.route('/visits', methods=['GET'])
def get_visits():
    """
    Retorna lista de visitas de emergencia de ESTA sala.

    Query params:
        - estado: (opcional) 'activa', 'completada', 'cancelada'
        - limit: (opcional) número máximo de resultados (default: 50)

    Returns:
        JSON array con visitas
    """
    try:
        query = VisitaEmergencia.query.filter_by(id_sala=Config.NODE_ID)

        # Filtro por estado
        estado = request.args.get('estado')
        if estado in ['activa', 'completada', 'cancelada']:
            query = query.filter_by(estado=estado)

        # Limit
        limit = request.args.get('limit', type=int, default=50)

        visitas = query.order_by(VisitaEmergencia.timestamp.desc()).limit(limit).all()

        return jsonify({
            'node_id': Config.NODE_ID,
            'count': len(visitas),
            'visits': [{
                'id_visita': v.id_visita,
                'folio': v.folio,
                'id_paciente': v.id_paciente,
                'paciente_nombre': v.paciente.nombre,
                'id_doctor': v.id_doctor,
                'doctor_nombre': v.doctor.nombre,
                'id_cama': v.id_cama,
                'cama_numero': v.cama.numero,
                'id_sala': v.id_sala,
                'sintomas': v.sintomas,
                'diagnostico': v.diagnostico,
                'estado': v.estado,
                'timestamp': v.timestamp.isoformat() if v.timestamp else None,
                'fecha_cierre': v.fecha_cierre.isoformat() if v.fecha_cierre else None
            } for v in visitas]
        }), 200

    except Exception as e:
        logger.error(f"Error en /api/cluster/visits: {e}")
        return jsonify({'error': str(e)}), 500


@cluster_api_bp.route('/patients', methods=['GET'])
def get_patients():
    """
    Retorna lista de pacientes registrados en el sistema.

    Query params:
        - limit: (opcional) número máximo de resultados (default: 100)
        - activo: (opcional) 'true' o 'false'

    Returns:
        JSON array con pacientes
    """
    try:
        query = Paciente.query

        # Filtro por activo
        if request.args.get('activo') == 'true':
            query = query.filter_by(activo=1)
        elif request.args.get('activo') == 'false':
            query = query.filter_by(activo=0)

        # Limit
        limit = request.args.get('limit', type=int, default=100)

        pacientes = query.limit(limit).all()

        return jsonify({
            'node_id': Config.NODE_ID,
            'count': len(pacientes),
            'patients': [{
                'id_paciente': p.id_paciente,
                'nombre': p.nombre,
                'edad': p.edad,
                'sexo': p.sexo,
                'curp': p.curp,
                'telefono': p.telefono,
                'contacto_emergencia': p.contacto_emergencia,
                'activo': p.activo
            } for p in pacientes]
        }), 200

    except Exception as e:
        logger.error(f"Error en /api/cluster/patients: {e}")
        return jsonify({'error': str(e)}), 500


@cluster_api_bp.route('/stats', methods=['GET'])
def get_stats():
    """
    Retorna estadísticas agregadas del nodo.
    Útil para determinar carga y capacidad disponible.

    Returns:
        JSON con estadísticas del nodo
    """
    try:
        stats = {
            'node_id': Config.NODE_ID,
            'doctors': {
                'total': Doctor.query.filter_by(id_sala=Config.NODE_ID, activo=True).count(),
                'available': Doctor.query.filter_by(id_sala=Config.NODE_ID, disponible=True, activo=True).count()
            },
            'beds': {
                'total': Cama.query.filter_by(id_sala=Config.NODE_ID).count(),
                'available': Cama.query.filter_by(id_sala=Config.NODE_ID, ocupada=False).count()
            },
            'visits': {
                'active': VisitaEmergencia.query.filter_by(id_sala=Config.NODE_ID, estado='activa').count(),
                'completed': VisitaEmergencia.query.filter_by(id_sala=Config.NODE_ID, estado='completada').count()
            },
            'social_workers': {
                'total': TrabajadorSocial.query.filter_by(id_sala=Config.NODE_ID, activo=True).count()
            }
        }

        # Calcular capacidad disponible
        stats['capacity'] = {
            'doctors_pct': (stats['doctors']['available'] / stats['doctors']['total'] * 100) if stats['doctors']['total'] > 0 else 0,
            'beds_pct': (stats['beds']['available'] / stats['beds']['total'] * 100) if stats['beds']['total'] > 0 else 0
        }

        return jsonify(stats), 200

    except Exception as e:
        logger.error(f"Error en /api/cluster/stats: {e}")
        return jsonify({'error': str(e)}), 500


@cluster_api_bp.route('/create-visit', methods=['POST'])
def create_visit_distributed():
    """
    Endpoint para crear una visita en el nodo LÍDER con exclusión mutua.

    Flujo:
    1. Nodo follower envía solicitud aquí
    2. Este endpoint (líder) aplica exclusión mutua
    3. Valida disponibilidad de recursos
    4. Crea visita localmente
    5. Replica a todos los nodos del cluster
    6. Retorna folio al solicitante

    Request JSON:
        {
            "id_paciente": int,
            "id_doctor": int,
            "id_cama": int,
            "id_trabajador": int,
            "id_sala": int,
            "sintomas": str
        }

    Returns:
        JSON: {'success': True, 'folio': str, 'visita': {...}} o {'success': False, 'error': str}
    """
    try:
        # Obtener datos de la solicitud
        data = request.get_json()

        if not data:
            return jsonify({'success': False, 'error': 'No data provided'}), 400

        # Validar campos requeridos
        required_fields = ['id_paciente', 'id_doctor', 'id_cama', 'id_trabajador', 'id_sala', 'sintomas']
        missing_fields = [field for field in required_fields if field not in data]

        if missing_fields:
            return jsonify({
                'success': False,
                'error': f'Missing required fields: {", ".join(missing_fields)}'
            }), 400

        # EXCLUSIÓN MUTUA: adquirir lock
        with visit_creation_lock:
            logger.info(f"Processing distributed visit creation request from sala {data['id_sala']}")

            # Validar que doctor existe y está disponible
            doctor = Doctor.query.get(data['id_doctor'])
            if not doctor:
                return jsonify({'success': False, 'error': f'Doctor {data["id_doctor"]} not found'}), 404

            if not doctor.disponible:
                return jsonify({'success': False, 'error': f'Doctor {doctor.nombre} is not available'}), 409

            # Validar que cama existe y está disponible
            cama = Cama.query.get(data['id_cama'])
            if not cama:
                return jsonify({'success': False, 'error': f'Bed {data["id_cama"]} not found'}), 404

            if cama.ocupada:
                return jsonify({'success': False, 'error': f'Bed {cama.numero} is occupied'}), 409

            # Validar que paciente existe
            paciente = Paciente.query.get(data['id_paciente'])
            if not paciente:
                return jsonify({'success': False, 'error': f'Patient {data["id_paciente"]} not found'}), 404

            # Validar que trabajador existe
            trabajador = TrabajadorSocial.query.get(data['id_trabajador'])
            if not trabajador:
                return jsonify({'success': False, 'error': f'Social worker {data["id_trabajador"]} not found'}), 404

            # Crear la visita (folio se genera automáticamente por el evento before_insert)
            visita = VisitaEmergencia(
                id_paciente=data['id_paciente'],
                id_doctor=data['id_doctor'],
                id_cama=data['id_cama'],
                id_trabajador=data['id_trabajador'],
                id_sala=data['id_sala'],
                sintomas=data['sintomas'],
                estado='activa',
                timestamp=datetime.utcnow()
            )

            # Marcar recursos como ocupados
            doctor.disponible = False
            cama.ocupada = True
            cama.id_paciente = data['id_paciente']

            # Guardar en BD
            db.session.add(visita)
            db.session.commit()

            # Refresh para obtener el folio auto-generado
            db.session.refresh(visita)

            logger.info(f"Visit created successfully in leader: folio={visita.folio}")

            # Preparar datos para replicación
            visita_data = {
                'folio': visita.folio,
                'id_paciente': visita.id_paciente,
                'id_doctor': visita.id_doctor,
                'id_cama': visita.id_cama,
                'id_trabajador': visita.id_trabajador,
                'id_sala': visita.id_sala,
                'sintomas': visita.sintomas,
                'diagnostico': visita.diagnostico,
                'estado': visita.estado,
                'timestamp': visita.timestamp.isoformat() if visita.timestamp else None,
                'fecha_cierre': visita.fecha_cierre.isoformat() if visita.fecha_cierre else None
            }

            # Replicar a todos los nodos del cluster
            # Necesitamos obtener bully_manager desde app
            from flask import current_app
            bully_manager = getattr(current_app, 'bully_manager', None)

            if bully_manager:
                replication_result = replicate_visit_to_cluster(
                    bully_manager,
                    visita_data,
                    exclude_node_id=Config.NODE_ID  # No replicar al líder mismo
                )
                logger.info(f"Replication result: {replication_result}")
            else:
                logger.warning("bully_manager not available, skipping replication")

            # Retornar respuesta exitosa
            return jsonify({
                'success': True,
                'folio': visita.folio,
                'visita': visita_data
            }), 201

    except Exception as e:
        db.session.rollback()
        logger.error(f"Error creating distributed visit: {e}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500


@cluster_api_bp.route('/replicate-visit', methods=['POST'])
def replicate_visit():
    """
    Endpoint para recibir una visita replicada desde el nodo LÍDER.

    Este endpoint se ejecuta en TODOS los nodos cuando el líder crea una visita.
    No valida disponibilidad de recursos (el líder ya lo hizo).

    Request JSON: Datos completos de la visita

    Returns:
        JSON: {'success': True} o {'success': False, 'error': str}
    """
    try:
        data = request.get_json()

        if not data:
            return jsonify({'success': False, 'error': 'No data provided'}), 400

        logger.info(f"Receiving replicated visit: folio={data.get('folio')}")

        # Verificar si la visita ya existe (evitar duplicados)
        existing_visit = VisitaEmergencia.query.filter_by(folio=data.get('folio')).first()
        if existing_visit:
            logger.warning(f"Visit {data.get('folio')} already exists, skipping replication")
            return jsonify({'success': True, 'message': 'Visit already exists'}), 200

        # Crear la visita localmente (sin validaciones, el líder ya las hizo)
        visita = VisitaEmergencia(
            folio=data['folio'],  # Usar el folio del líder
            id_paciente=data['id_paciente'],
            id_doctor=data['id_doctor'],
            id_cama=data['id_cama'],
            id_trabajador=data['id_trabajador'],
            id_sala=data['id_sala'],
            sintomas=data['sintomas'],
            diagnostico=data.get('diagnostico'),
            estado=data['estado'],
            timestamp=datetime.fromisoformat(data['timestamp']) if data.get('timestamp') else datetime.utcnow(),
            fecha_cierre=datetime.fromisoformat(data['fecha_cierre']) if data.get('fecha_cierre') else None
        )

        # Actualizar estado de recursos (doctor y cama)
        doctor = Doctor.query.get(data['id_doctor'])
        if doctor:
            doctor.disponible = False

        cama = Cama.query.get(data['id_cama'])
        if cama:
            cama.ocupada = True
            cama.id_paciente = data['id_paciente']

        # Guardar en BD
        db.session.add(visita)
        db.session.commit()

        logger.info(f"Visit replicated successfully: folio={visita.folio}")

        return jsonify({'success': True, 'message': 'Visit replicated successfully'}), 201

    except Exception as e:
        db.session.rollback()
        logger.error(f"Error replicating visit: {e}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500
