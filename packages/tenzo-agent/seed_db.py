"""
HoFi · GSD-012 — Seed de 40 tareas históricas en Cloud SQL
Hidrata la memoria del Agente Tenzo con datos reales de cuidado comunitario.
Ejecutar una sola vez contra Cloud SQL (DB_MOCK=false).

Uso:
    python seed_db.py --host 35.225.156.68 --db hofi --user tenzo --pass TU_PASSWORD
"""

import argparse
import psycopg2
from psycopg2.extras import execute_values
from datetime import datetime, timedelta
import random

# ── 40 tareas de cuidado comunitario ──────────────────────────────────────
TAREAS = [
    # Cuidado de personas
    ("Cuidado de niños menores de 5 años",        "cuidado_ninos",     2.0, 200.0, '["cuidado"]'),
    ("Cuidado de adultos mayores",                 "cuidado_ninos",     3.0, 300.0, '["cuidado"]'),
    ("Acompañamiento terapéutico",                 "salud_comunitaria", 1.5, 150.0, '["cuidado"]'),
    ("Asistencia en discapacidad",                 "salud_comunitaria", 2.0, 200.0, '["cuidado"]'),
    ("Lactancia y apoyo maternal",                 "cuidado_ninos",     1.0, 100.0, '["cuidado"]'),
    ("Apoyo psicológico comunitario",              "salud_comunitaria", 1.5, 180.0, '["cuidado", "comunitaria"]'),
    ("Primeros auxilios comunitarios",             "salud_comunitaria", 2.0, 200.0, '["cuidado", "comunitaria"]'),
    ("Visita a enfermos del holón",                "salud_comunitaria", 1.0, 100.0, '["cuidado"]'),

    # Alimentación
    ("Cocina comunal para almuerzo",               "cocina_comunal",    2.0, 160.0, '["cuidado", "comunitaria"]'),
    ("Preparación de conservas y fermentados",     "cocina_comunal",    3.0, 240.0, '["cuidado", "comunitaria"]'),
    ("Panadería comunitaria",                      "cocina_comunal",    2.5, 200.0, '["cuidado", "comunitaria"]'),
    ("Distribución de canasta alimentaria",        "cocina_comunal",    1.5, 120.0, '["cuidado", "comunitaria"]'),
    ("Cena comunitaria mensual",                   "cocina_comunal",    3.0, 240.0, '["cuidado", "comunitaria"]'),

    # Limpieza y mantenimiento
    ("Limpieza de espacios comunes",               "limpieza_espacios", 1.0,  80.0, '["comunitaria"]'),
    ("Limpieza profunda mensual",                  "limpieza_espacios", 3.0, 240.0, '["comunitaria"]'),
    ("Mantenimiento de baños comunitarios",        "limpieza_espacios", 1.5, 120.0, '["comunitaria"]'),
    ("Reparación de infraestructura básica",       "mantenimiento",     3.0, 270.0, '["comunitaria"]'),
    ("Mantenimiento eléctrico básico",             "mantenimiento",     2.0, 200.0, '["comunitaria"]'),
    ("Plomería y sanitarios",                      "mantenimiento",     2.0, 200.0, '["comunitaria"]'),
    ("Pintura y refacción de espacios",            "mantenimiento",     4.0, 320.0, '["comunitaria"]'),

    # Educación y cultura
    ("Taller educativo para niños",                "taller_educativo",  2.0, 180.0, '["cuidado", "comunitaria"]'),
    ("Clase de idiomas comunitaria",               "taller_educativo",  1.5, 135.0, '["comunitaria"]'),
    ("Taller de habilidades digitales",            "taller_educativo",  2.0, 180.0, '["comunitaria"]'),
    ("Círculo de lectura mensual",                 "taller_educativo",  1.5, 120.0, '["comunitaria"]'),
    ("Taller de arte y expresión",                 "taller_educativo",  2.0, 160.0, '["comunitaria"]'),
    ("Documentación y archivo comunitario",        "taller_educativo",  2.0, 160.0, '["comunitaria"]'),

    # Ecología y regeneración
    ("Huerta comunitaria — siembra",               "jardineria",        2.0, 160.0, '["regenerativa", "comunitaria"]'),
    ("Huerta comunitaria — cosecha",               "jardineria",        2.0, 160.0, '["regenerativa", "comunitaria"]'),
    ("Compostaje y gestión de residuos",           "jardineria",        1.5, 135.0, '["regenerativa", "comunitaria"]'),
    ("Reforestación y plantación de árboles",      "jardineria",        3.0, 270.0, '["regenerativa", "comunitaria"]'),
    ("Monitoreo de paneles solares",               "mantenimiento",     1.0,  90.0, '["regenerativa"]'),
    ("Instalación de sistema de agua de lluvia",   "mantenimiento",     4.0, 400.0, '["regenerativa", "comunitaria"]'),
    ("Biodigestor — operación y mantenimiento",    "mantenimiento",     2.0, 200.0, '["regenerativa"]'),

    # Gobernanza y administración
    ("Facilitación de asamblea holónica",          "taller_educativo",  2.0, 200.0, '["comunitaria"]'),
    ("Mediación de conflictos",                    "salud_comunitaria", 2.0, 220.0, '["cuidado", "comunitaria"]'),
    ("Administración y contabilidad comunitaria",  "taller_educativo",  2.0, 180.0, '["comunitaria"]'),
    ("Gestión de proveedores externos",            "mantenimiento",     1.5, 150.0, '["comunitaria"]'),
    ("Bienvenida e integración de nuevos miembros","taller_educativo",  1.5, 135.0, '["cuidado", "comunitaria"]'),
    ("Coordinación inter-holónica",                "taller_educativo",  2.0, 200.0, '["comunitaria"]'),
    ("Documentación de acuerdos y resoluciones",   "taller_educativo",  1.5, 135.0, '["comunitaria"]'),
]


def seed(host: str, db: str, user: str, password: str, port: int = 5432):
    print(f"\nConectando a {host}:{port}/{db} como {user}...")

    conn = psycopg2.connect(
        host=host, port=port, dbname=db, user=user, password=password
    )
    cur = conn.cursor()

    # Crear tabla si no existe
    cur.execute("""
        CREATE TABLE IF NOT EXISTS historical_tasks (
            id              SERIAL PRIMARY KEY,
            titulo          TEXT NOT NULL,
            categoria       TEXT NOT NULL,
            duracion_horas  FLOAT NOT NULL,
            recompensa_hoca FLOAT NOT NULL,
            clasificacion   JSONB DEFAULT '[]',
            holon_id        TEXT DEFAULT 'holon-piloto',
            aprobada        BOOLEAN DEFAULT TRUE,
            created_at      TIMESTAMP DEFAULT NOW()
        );
    """)
    conn.commit()
    print("✓ Tabla historical_tasks verificada")

    # Verificar si ya hay datos
    cur.execute("SELECT COUNT(*) FROM historical_tasks")
    count = cur.fetchone()[0]
    if count > 0:
        print(f"  Ya existen {count} tareas. Agregando las nuevas...")

    # Insertar las 40 tareas con fechas distribuidas en los últimos 6 meses
    ahora = datetime.now()
    rows = []
    for i, (titulo, categoria, duracion, recompensa, clasificacion) in enumerate(TAREAS):
        # Distribuir fechas aleatoriamente en los últimos 6 meses
        dias_atras = random.randint(1, 180)
        fecha = ahora - timedelta(days=dias_atras)
        rows.append((titulo, categoria, duracion, recompensa, clasificacion, fecha))

    execute_values(
        cur,
        """
        INSERT INTO historical_tasks
            (titulo, categoria, duracion_horas, recompensa_hoca, clasificacion, created_at)
        VALUES %s
        """,
        rows,
        template="(%s, %s, %s, %s, %s::jsonb, %s)"
    )
    conn.commit()

    # Verificar resultado
    cur.execute("SELECT COUNT(*) FROM historical_tasks")
    total = cur.fetchone()[0]
    print(f"✓ {len(rows)} tareas insertadas — total en DB: {total}")

    # Mostrar resumen por categoría
    cur.execute("""
        SELECT categoria, COUNT(*), ROUND(AVG(recompensa_hoca)::numeric, 1) as avg_hoca
        FROM historical_tasks
        GROUP BY categoria
        ORDER BY avg_hoca DESC
    """)
    print("\n  Resumen por categoría:")
    print(f"  {'Categoría':<28} {'Tareas':>6} {'HoCa/tarea':>10}")
    print(f"  {'-'*46}")
    for row in cur.fetchall():
        print(f"  {row[0]:<28} {row[1]:>6} {row[2]:>10}")

    cur.close()
    conn.close()
    print("\n✓ GSD-012 completado — Tenzo tiene memoria histórica real\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="HoFi — Seed Cloud SQL")
    parser.add_argument("--host",     required=True)
    parser.add_argument("--db",       default="hofi")
    parser.add_argument("--user",     default="tenzo")
    parser.add_argument("--pass",     dest="password", required=True)
    parser.add_argument("--port",     type=int, default=5432)
    args = parser.parse_args()

    seed(args.host, args.db, args.user, args.password, args.port)
