#!/usr/bin/env python3
"""
Script para inicializar base de datos de prueba
con datos de ejemplo para testing del frontend
"""

import os
import sys
from datetime import datetime, timedelta

# Agregar el directorio src al path para importar módulos
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

# Configurar el nodo antes de importar
os.environ['NODE_ID'] = '1'

from app import app, db
from models import Sala, Doctor, TrabajadorSocial, Paciente, Cama, VisitaEmergencia, Consecutivo, Usuario
import random

def init_test_database():
    """Inicializa la base de datos con datos de prueba"""

    with app.app_context():
        # Crear todas las tablas
        print("Creando tablas...")
        db.create_all()

        # Limpiar datos existentes
        print("Limpiando datos existentes...")
        db.session.query(VisitaEmergencia).delete()
        db.session.query(Consecutivo).delete()
        db.session.query(Cama).delete()
        db.session.query(TrabajadorSocial).delete()
        db.session.query(Doctor).delete()
        db.session.query(Paciente).delete()
        db.session.query(Sala).delete()
        db.session.query(Usuario).delete()

        # 1. Crear Salas
        print("Creando salas...")
        salas = [
            Sala(id_sala=1, numero=1, ip_address='localhost', puerto=5555, es_maestro=True, activa=True),
            Sala(id_sala=2, numero=2, ip_address='localhost', puerto=5556, es_maestro=False, activa=True),
            Sala(id_sala=3, numero=3, ip_address='localhost', puerto=5557, es_maestro=False, activa=True),
            Sala(id_sala=4, numero=4, ip_address='localhost', puerto=5558, es_maestro=False, activa=True),
        ]
        for sala in salas:
            db.session.add(sala)

        # 2. Crear Doctores
        print("Creando doctores...")
        especialidades = ['Cardiología', 'Pediatría', 'Traumatología', 'Medicina General', 'Neurología']
        nombres_doctores = [
            'Dr. Juan Pérez', 'Dra. María García', 'Dr. Carlos López', 'Dra. Ana Martínez',
            'Dr. Luis Rodríguez', 'Dra. Carmen Fernández', 'Dr. Miguel Sánchez', 'Dra. Laura Torres'
        ]

        doctores = []
        for i, nombre in enumerate(nombres_doctores, 1):
            sala_id = ((i - 1) % 4) + 1
            doctor = Doctor(
                id_doctor=i,
                nombre=nombre,
                especialidad=random.choice(especialidades),
                id_sala=sala_id,
                disponible=random.choice([True, True, False]),  # 66% disponibles
                activo=True
            )
            doctores.append(doctor)
            db.session.add(doctor)

        # 3. Crear Trabajadores Sociales
        print("Creando trabajadores sociales...")
        nombres_trabajadores = ['Ana López', 'Pedro Ramírez', 'Sofia Morales', 'Diego Castro']

        trabajadores = []
        for i, nombre in enumerate(nombres_trabajadores, 1):
            trabajador = TrabajadorSocial(
                id_trabajador=i,
                nombre=nombre,
                id_sala=i,
                activo=True
            )
            trabajadores.append(trabajador)
            db.session.add(trabajador)

        # 4. Crear Pacientes
        print("Creando pacientes...")
        nombres_pacientes = [
            'Juan Hernández', 'María González', 'Pedro Jiménez', 'Laura Díaz',
            'Carlos Ruiz', 'Ana Torres', 'Miguel Vargas', 'Carmen Castro',
            'Luis Ortiz', 'Sofia Moreno', 'Diego Romero', 'Elena Navarro',
            'Fernando Cruz', 'Patricia Ramos', 'Roberto Silva'
        ]

        pacientes = []
        for i, nombre in enumerate(nombres_pacientes, 1):
            paciente = Paciente(
                id_paciente=i,
                nombre=nombre,
                edad=random.randint(18, 85),
                sexo=random.choice(['M', 'F']),
                curp=f'TEST{i:012d}XXXXX',
                telefono=f'555-{random.randint(1000, 9999)}',
                contacto_emergencia=f'Familiar: 555-{random.randint(1000, 9999)}',
                activo=1
            )
            pacientes.append(paciente)
            db.session.add(paciente)

        # 5. Crear Camas
        print("Creando camas...")
        camas = []
        for sala_id in range(1, 5):
            for num_cama in range(1, 11):  # 10 camas por sala
                cama = Cama(
                    numero=num_cama,
                    id_sala=sala_id,
                    ocupada=False,
                    id_paciente=None
                )
                camas.append(cama)
                db.session.add(cama)

        db.session.commit()
        print(f"✓ Creadas {len(camas)} camas")

        # 6. Crear Visitas de Emergencia
        print("Creando visitas de emergencia...")
        sintomas_ejemplos = [
            'Dolor de pecho intenso, dificultad para respirar',
            'Fractura en brazo derecho, accidente de tráfico',
            'Fiebre alta (39°C), dolor abdominal severo',
            'Desmayo, mareos constantes',
            'Dolor de cabeza intenso, visión borrosa',
            'Dificultad para respirar, tos persistente',
            'Dolor en pierna izquierda, imposibilidad de caminar',
            'Náuseas, vómito, deshidratación',
            'Herida profunda en mano, sangrado abundante',
            'Crisis de ansiedad, palpitaciones'
        ]

        # Crear algunas visitas activas
        for i in range(5):
            # Buscar doctor y cama disponibles
            doctor = Doctor.query.filter_by(disponible=True).first()
            cama = Cama.query.filter_by(ocupada=False).first()

            if doctor and cama:
                paciente = random.choice(pacientes)
                trabajador = random.choice(trabajadores)

                visita = VisitaEmergencia(
                    folio=f'{datetime.now().strftime("%Y%m%d")}-{i+1}-{doctor.id_sala}-{i+1:03d}',
                    id_paciente=paciente.id_paciente,
                    id_doctor=doctor.id_doctor,
                    id_cama=cama.id_cama,
                    id_trabajador=trabajador.id_trabajador,
                    id_sala=doctor.id_sala,
                    sintomas=random.choice(sintomas_ejemplos),
                    estado='activa',
                    timestamp=datetime.utcnow() - timedelta(hours=random.randint(0, 5))
                )
                db.session.add(visita)

                # Marcar recursos como ocupados
                doctor.disponible = False
                cama.ocupada = True
                cama.id_paciente = paciente.id_paciente

        # Crear algunas visitas completadas
        for i in range(10):
            doctor = random.choice(doctores)
            cama = random.choice([c for c in camas if c.id_sala == doctor.id_sala])
            paciente = random.choice(pacientes)
            trabajador = trabajadores[(doctor.id_sala - 1) % len(trabajadores)]

            fecha_inicio = datetime.utcnow() - timedelta(days=random.randint(1, 7), hours=random.randint(0, 23))
            fecha_cierre = fecha_inicio + timedelta(hours=random.randint(1, 6))

            visita = VisitaEmergencia(
                folio=f'{fecha_inicio.strftime("%Y%m%d")}-{i+10}-{doctor.id_sala}-{i+10:03d}',
                id_paciente=paciente.id_paciente,
                id_doctor=doctor.id_doctor,
                id_cama=cama.id_cama,
                id_trabajador=trabajador.id_trabajador,
                id_sala=doctor.id_sala,
                sintomas=random.choice(sintomas_ejemplos),
                diagnostico=f'Diagnóstico para visita {i+10}. Tratamiento exitoso.',
                estado='completada',
                timestamp=fecha_inicio,
                fecha_cierre=fecha_cierre
            )
            db.session.add(visita)

        # 7. Crear Usuarios
        print("Creando usuarios de autenticación...")

        # Doctores (uno por cada doctor)
        for i in range(1, 5):
            user = Usuario(username=f'doctor{i}', rol='doctor', id_relacionado=i, activo=True)
            user.set_password('doc123')
            db.session.add(user)

        # Trabajadores sociales
        for i in range(1, 5):
            user = Usuario(username=f'trabajador{i}', rol='trabajador_social', id_relacionado=i, activo=True)
            user.set_password('trab123')
            db.session.add(user)

        # Pacientes (algunos pacientes de prueba)
        for i in range(1, 6):  # Primeros 5 pacientes pueden autenticarse
            user = Usuario(username=f'paciente{i}', rol='paciente', id_relacionado=i, activo=True)
            user.set_password('pac123')
            db.session.add(user)

        db.session.commit()

        # Resumen
        print("\n" + "="*60)
        print("✅ Base de datos inicializada correctamente")
        print("="*60)
        print(f"Salas:               {Sala.query.count()}")
        print(f"Doctores:            {Doctor.query.count()}")
        print(f"Trabajadores:        {TrabajadorSocial.query.count()}")
        print(f"Pacientes:           {Paciente.query.count()}")
        print(f"Camas:               {Cama.query.count()}")
        print(f"Visitas activas:     {VisitaEmergencia.query.filter_by(estado='activa').count()}")
        print(f"Visitas completadas: {VisitaEmergencia.query.filter_by(estado='completada').count()}")
        print(f"Usuarios:            {Usuario.query.count()}")
        print("="*60)
        print("\nUsuarios de prueba:")
        print("  DOCTORES:")
        print("    doctor1, doctor2, doctor3, doctor4 / doc123")
        print("  TRABAJADORES SOCIALES:")
        print("    trabajador1, trabajador2, trabajador3, trabajador4 / trab123")
        print("  PACIENTES:")
        print("    paciente1, paciente2, paciente3, paciente4, paciente5 / pac123")
        print("="*60)

if __name__ == '__main__':
    print("🏥 Inicializando base de datos de prueba...")
    print()
    init_test_database()
    print("\n✓ Listo! Ahora puedes iniciar el servidor con: python app.py")
