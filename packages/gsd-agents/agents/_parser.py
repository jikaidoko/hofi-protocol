"""
Utilidad compartida para parsear respuestas JSON de Claude.
Maneja: JSON puro, ```json bloques, texto antes del JSON, respuesta vacía.
"""
import json
import re


def parse_json_response(texto: str, fallback: dict = None) -> dict:
    """
    Intenta extraer JSON válido de la respuesta de Claude.
    Estrategias en orden:
    1. JSON directo
    2. Bloque ```json...```
    3. Primer { ... } en el texto
    4. Fallback si se provee
    """
    if not texto or not texto.strip():
        if fallback is not None:
            return fallback
        raise ValueError("Respuesta vacía del modelo")

    texto = texto.strip()

    # Estrategia 1: JSON directo
    try:
        return json.loads(texto)
    except json.JSONDecodeError:
        pass

    # Estrategia 2: bloque ```json
    match = re.search(r'```(?:json)?\s*([\s\S]*?)```', texto)
    if match:
        try:
            return json.loads(match.group(1).strip())
        except json.JSONDecodeError:
            pass

    # Estrategia 3: primer objeto JSON en el texto
    match = re.search(r'\{[\s\S]*\}', texto)
    if match:
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            pass

    # Estrategia 4: fallback
    if fallback is not None:
        return fallback

    raise ValueError(f"No se pudo parsear JSON de la respuesta: {texto[:200]}")
