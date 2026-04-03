"""
task_parser.py — Extracción estructurada de tareas

Antes de que Gemini evalúe, extraemos de forma determinista:
  - actividad: qué se hizo (verbo + objeto)
  - duracion_min: duración en minutos (número real, no lo que dice el usuario)
  - duracion_declarada_min: lo que el usuario dijo (para comparar)
  - categoria: categoría de cuidado
  - fecha_implicita: hoy / ayer / semana

Esto permite:
  1. Pasar datos estructurados al prompt de Gemini (más preciso)
  2. Comparar duración declarada vs duración plausible
  3. Aplicar topes por categoría ANTES de evaluar

Estrategia de parsing:
  - Regex primero (rápido, sin API)
  - Si falla, Gemini extrae con prompt minimalista (estructura forzada)
"""

import re
import json
import logging
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Topes máximos por categoría (minutos declarables por día)
# Configurable: eventualmente vendrán de la DB del holón
# ---------------------------------------------------------------------------
TOPES_CATEGORIA: dict[str, int] = {
    "cuidado_humano":      240,   # 4 horas/día
    "cuidado_animal":      180,
    "cuidado_ecologico":   360,   # trabajo físico de campo
    "cocina_comunitaria":  240,
    "mantenimiento":       480,   # puede ser jornada completa
    "educacion":           120,
    "gestion":             120,
    "logistica":           180,
    "default":             240,
}

# Palabras clave para detectar categoría sin LLM
KEYWORDS_CATEGORIA: list[tuple[list[str], str]] = [
    (["niño", "niña", "bebe", "bebé", "ancian", "enfermer", "acompañ", "cuid"], "cuidado_humano"),
    (["gallina", "pollo", "vaca", "cabra", "abeja", "colmen", "animal", "mascot", "pez", "peces"], "cuidado_animal"),
    (["huerta", "siembra", "compostar", "compost", "árbol", "arbol", "humedal",
      "semilla", "jardín", "jardin", "poda", "plantar", "agua", "riego"], "cuidado_ecologico"),
    (["cocin", "almuerzar", "cenar", "desayun", "comin", "preparar comida", "lavar platos"], "cocina_comunitaria"),
    (["repar", "arregl", "construir", "pintar", "mantenimiento", "limpiar", "barrer"], "mantenimiento"),
    (["enseñar", "clase", "taller", "reunión", "reunion", "asamblea", "transmitir"], "educacion"),
]

# Patrones de duración en español
DURATION_PATTERNS: list[tuple[re.Pattern, float]] = [
    (re.compile(r"(\d+(?:[.,]\d+)?)\s*hora(?:s)?"),         60.0),
    (re.compile(r"(\d+(?:[.,]\d+)?)\s*hs?\.?"),              60.0),
    (re.compile(r"(\d+)\s*minuto(?:s)?"),                      1.0),
    (re.compile(r"(\d+)\s*min\.?"),                             1.0),
    (re.compile(r"media\s+hora"),                             30.0),   # sin grupo
    (re.compile(r"un\s+cuarto\s+de\s+hora"),                 15.0),
    (re.compile(r"(\d+)\s*h\s*(\d+)\s*(?:min)?"),            None),   # "1h 30min"
    (re.compile(r"toda\s+la\s+(?:mañana|tarde|mañanita)"),  180.0),
    (re.compile(r"todo\s+el\s+día"),                         480.0),
    (re.compile(r"un\s+rato"),                                30.0),
    (re.compile(r"un\s+momento"),                             15.0),
]


@dataclass
class TareaEstructurada:
    descripcion_original: str
    actividad: str                       # "poda de jardín"
    duracion_declarada_min: int          # lo que dijo el usuario
    duracion_normalizada_min: int        # ajustada por tope de categoría
    categoria: str
    fecha_implicita: str                 # "hoy" | "ayer" | "esta_semana"
    confianza_parseo: float              # 0–1: qué tan seguro estamos del parse
    advertencias: list[str] = field(default_factory=list)


def parsear_tarea(texto: str) -> TareaEstructurada:
    """
    Parsea de forma determinista. No requiere API externa.
    Devuelve TareaEstructurada con advertencias si hay anomalías.
    """
    texto_lower = texto.lower()
    advertencias = []

    # --- Duración ---
    duracion_min = _extraer_duracion(texto_lower)
    if duracion_min is None:
        duracion_min = 30   # default conservador
        advertencias.append("No se detectó duración explícita — se asumió 30 min")
        confianza = 0.4
    else:
        confianza = 0.8

    # --- Categoría ---
    categoria = _detectar_categoria(texto_lower)

    # --- Tope de categoría ---
    tope = TOPES_CATEGORIA.get(categoria, TOPES_CATEGORIA["default"])
    if duracion_min > tope:
        advertencias.append(
            f"Duración declarada ({duracion_min} min) supera el tope "
            f"de '{categoria}' ({tope} min/día) — se usa el tope"
        )
        duracion_normalizada = tope
        confianza = min(confianza, 0.5)
    else:
        duracion_normalizada = duracion_min

    # --- Fecha implícita ---
    fecha = _detectar_fecha(texto_lower)

    # --- Actividad (heurística: primero verbo + objeto) ---
    actividad = _extraer_actividad(texto)

    return TareaEstructurada(
        descripcion_original=texto,
        actividad=actividad,
        duracion_declarada_min=duracion_min,
        duracion_normalizada_min=duracion_normalizada,
        categoria=categoria,
        fecha_implicita=fecha,
        confianza_parseo=confianza,
        advertencias=advertencias,
    )


def _extraer_duracion(texto: str) -> Optional[int]:
    """Devuelve minutos o None si no encuentra duración."""
    for pattern, multiplicador in DURATION_PATTERNS:
        m = pattern.search(texto)
        if not m:
            continue

        if multiplicador is None:
            # Patrón "1h 30min"
            horas = int(m.group(1))
            mins = int(m.group(2)) if m.lastindex >= 2 else 0
            return horas * 60 + mins

        if multiplicador in (30.0, 15.0, 180.0, 480.0):
            # Patrones sin grupo numérico ("media hora", "todo el día")
            return int(multiplicador)

        try:
            valor = float(m.group(1).replace(",", "."))
            return int(valor * multiplicador)
        except (IndexError, ValueError):
            continue

    return None


def _detectar_categoria(texto: str) -> str:
    for keywords, categoria in KEYWORDS_CATEGORIA:
        if any(kw in texto for kw in keywords):
            return categoria
    return "default"


def _detectar_fecha(texto: str) -> str:
    if any(w in texto for w in ["hoy", "esta mañana", "esta tarde", "recién", "recien"]):
        return "hoy"
    if any(w in texto for w in ["ayer", "anoche", "la mañana de ayer"]):
        return "ayer"
    if any(w in texto for w in ["esta semana", "los últimos días", "hace unos días"]):
        return "esta_semana"
    return "hoy"  # default


def _extraer_actividad(texto: str) -> str:
    """
    Heurística simple: quita referencias temporales y de persona,
    devuelve el núcleo de la descripción (primeras 10 palabras útiles).
    """
    # Quitar frases de tiempo y persona comunes
    limpiadores = [
        r"hoy\s+", r"ayer\s+", r"esta (mañana|tarde|noche)\s+",
        r"estuve\s+", r"hice\s+", r"realicé\s+", r"dediqué\s+[^a]+a\s+",
        r"trabajé\s+[^e]+en\s+", r"pasé\s+[^e]+en\s+",
    ]
    resultado = texto
    for patron in limpiadores:
        resultado = re.sub(patron, "", resultado, flags=re.IGNORECASE).strip()

    palabras = resultado.split()[:12]
    return " ".join(palabras).strip(",. ")


def tarea_a_prompt_context(t: TareaEstructurada) -> str:
    """
    Formatea la tarea estructurada para incluirla en el prompt de Gemini.
    Gemini recibe datos ya procesados, no texto crudo.
    """
    lines = [
        f"Actividad detectada: {t.actividad}",
        f"Duración declarada: {t.duracion_declarada_min} minutos",
    ]
    if t.duracion_normalizada_min != t.duracion_declarada_min:
        lines.append(
            f"Duración a usar para el cálculo: {t.duracion_normalizada_min} min "
            f"(declarada supera el tope de categoría)"
        )
    lines += [
        f"Categoría inferida: {t.categoria}",
        f"Referencia temporal: {t.fecha_implicita}",
    ]
    if t.advertencias:
        lines.append("Advertencias del parser: " + "; ".join(t.advertencias))
    return "\n".join(lines)
