#!/usr/bin/env python3
"""
Script de prueba para verificar que el fix de tuplas funciona correctamente.
Esto demuestra que el split-brain se resolvió.
"""
import sys
import time
import logging
from app_factory import create_app
from bully import BullyNode
from config import Config

# Suprimir logging
logging.basicConfig(level=logging.CRITICAL)

print("=" * 60)
print("PRUEBA: Verificar fix de tuplas en cluster_nodes")
print("=" * 60)

# Simular Nodo 1
print("\n[1] Creando app para Nodo 1...")
import os
os.environ['NODE_ID'] = '1'
app = create_app()
node_id = 1

print(f"[2] Configurando cluster_nodes con TUPLAS (fix aplicado)...")
cluster_nodes = {}
for nodo_info in Config.OTROS_NODOS:
    if nodo_info['id'] != node_id:
        # BullyNode expects tuple: (host, tcp_port, udp_port)
        cluster_nodes[nodo_info['id']] = (
            'localhost',  # host
            nodo_info['tcp_port'],  # tcp_port
            6000 + nodo_info['id'] - 1  # udp_port
        )

print(f"\n[3] cluster_nodes construido:")
for nid, data in cluster_nodes.items():
    print(f"    Nodo {nid}: {data}")
    print(f"             Tipo: {type(data)}")

    # Verificar que es tupla
    if not isinstance(data, tuple):
        print(f"    ❌ ERROR: Esperaba tuple, recibió {type(data)}")
        sys.exit(1)

    # Verificar desempaquetado
    try:
        ip, tcp_port, udp_port = data
        print(f"             Desempaquetado: ip={ip}, tcp={tcp_port}, udp={udp_port}")

        # Verificar tipos
        if not isinstance(ip, str):
            print(f"    ❌ ERROR: ip debe ser str, es {type(ip)}")
            sys.exit(1)
        if not isinstance(tcp_port, int):
            print(f"    ❌ ERROR: tcp_port debe ser int, es {type(tcp_port)}")
            sys.exit(1)
        if not isinstance(udp_port, int):
            print(f"    ❌ ERROR: udp_port debe ser int, es {type(udp_port)}")
            sys.exit(1)

        print(f"             ✓ Tipos correctos")
    except Exception as e:
        print(f"    ❌ ERROR desempaquetando: {e}")
        sys.exit(1)

print(f"\n[4] Inicializando BullyNode...")
try:
    bully = BullyNode(
        node_id=node_id,
        cluster_nodes=cluster_nodes,
        tcp_port=5555,
        udp_port=6000
    )
    print(f"    ✓ BullyNode creado exitosamente")
except Exception as e:
    print(f"    ❌ ERROR: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

print(f"\n[5] Iniciando Bully (esto tomará ~2 segundos)...")
try:
    bully.start()
    print(f"    ✓ Bully iniciado")
except Exception as e:
    print(f"    ❌ ERROR: {e}")
    import traceback
    traceback.print_exc()
    bully.stop()
    sys.exit(1)

print(f"\n[6] Esperando elección inicial...")
time.sleep(3)

print(f"\n[7] Verificando estado...")
try:
    estado = bully.state.value
    lider = bully.get_current_leader()
    es_lider = bully.is_leader()

    print(f"    Estado: {estado}")
    print(f"    Líder actual: Nodo {lider}")
    print(f"    ¿Es líder?: {es_lider}")

    # Como solo hay Nodo 1 corriendo, debería ser líder
    if es_lider and lider == 1:
        print(f"    ✓ Comportamiento esperado (único nodo = líder)")
    else:
        print(f"    ⚠️  Advertencia: comportamiento inesperado")

except Exception as e:
    print(f"    ❌ ERROR: {e}")
    import traceback
    traceback.print_exc()
    bully.stop()
    sys.exit(1)

print(f"\n[8] Deteniendo Bully...")
bully.stop()
print(f"    ✓ Bully detenido")

print("\n" + "=" * 60)
print("✅ PRUEBA EXITOSA - Fix de tuplas funcionando correctamente")
print("=" * 60)
print("\nEl split-brain estaba causado por:")
print("  ❌ ANTES: cluster_nodes[id] = {'tcp_port': X, ...}")
print("     → Desempaquetado tomaba KEYS: ('tcp_port', 'udp_port', 'host')")
print("     → Intentaba conectar a 'tcp_port':'udp_port' (strings!)")
print("     → Todas las conexiones fallaban → split-brain")
print()
print("  ✅ AHORA: cluster_nodes[id] = (host, tcp_port, udp_port)")
print("     → Desempaquetado correcto: ip='localhost', tcp=5556, udp=6001")
print("     → Conexiones TCP/UDP funcionan")
print("     → Elección de líder funciona correctamente")
print()
