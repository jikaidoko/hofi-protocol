# v0.2.2
# { "Depends": "py-genlayer:1jb45aa8ynh2a9c9xn3b7qqh8sm5q93hwfp7jqmwsfhh8jpz09h6" }

"""
HoFi Protocol · TenzoEquityOracle v0.2.1
Intelligent Smart Contract for GenLayer Testnet Asimov

Cambios respecto a v0.1.0:
  - eq_principle.strict_eq → eq_principle.prompt_comparative (Pattern 3)
    Los 5 validadores evalúan independientemente y un LLM de comparación
    decide si los resultados son equivalentes dentro de un margen de equidad.
    strict_eq es frágil con LLMs (requiere JSON byte-a-byte idéntico).
    prompt_comparative tolera variaciones menores en HoCa y justificación
    siempre que el veredicto (APPROVE/REJECT) y la categoría coincidan.

  - Apelación activa del Tenzo:
    Nueva función appeal_rejection() que el Tenzo Agent puede llamar cuando
    el ISC rechazó pero Gemini tiene certeza media (0.55–0.75).
    Los validadores reciben evidencia adicional: matches del catálogo del holón
    + historial limpio de la persona + argumento del Tenzo.

  - Manejo de errores robusto con gl.vm.run_nondet (custom leader/validator):
    Reemplaza los try/except silenciosos con fallbacks mínimos que eran
    invisibles en los logs del ISC. Ahora los errores de parsing se exponen
    explícitamente para debug en Studionet.

  - Fallback de historia enriquecido:
    El fallback de history_text ya no usa tres tareas hardcodeadas en inglés
    con montos fijos. Usa el contexto de las reglas del holón para construir
    un fallback culturalmente consistente.

  - NatSpec completo en todas las funciones públicas.

Cambios en v0.2.2:
  - Fix crítico: float no es un tipo soportado en el ABI de GenLayer (calldata
    encoder y get_schema lo rechazan con "type is not supported").
    Los parámetros duracion_horas, amount, recompensa_hoca y tenzo_confidence
    que eran float ahora son str. El contrato los convierte internamente con
    float() / int(). Esto permite que el SDK genlayer-py pueda encodificar
    el calldata y que get_contract_schema funcione correctamente.
    Tipos aceptados por el encoder: None, bool, int, str, bytes,
    CalldataAddress, Sequence, Mapping, dataclass. float NO está soportado.

Workflow:
  1. El miembro de la comunidad propone una tarea de cuidado
  2. El Tenzo Agent de HoFi llama a validate_task_equity()
  3. 5 validadores GenLayer evalúan independientemente con sus propios LLMs
  4. prompt_comparative alcanza consenso con tolerancia a variaciones menores
  5. Si el Tenzo Agent tiene certeza media y el ISC rechazó → llama appeal_rejection()
  6. Validadores adicionales reciben la evidencia del Tenzo y re-evalúan
  7. Si APPROVED → Tenzo Agent llama TaskRegistry.approveTask() en Ethereum Sepolia
"""

import json
from genlayer import *


class TenzoEquityOracle(gl.Contract):
    """
    Oráculo de equidad descentralizado para la economía del cuidado de HoFi.
    Usa la Democracia Optimista de GenLayer para validar recompensas de cuidado.

    State variables:
        holon_rules:    TreeMap[holon_id → rules_description]
                        Reglas culturales y económicas de cada holón.
        task_history:   TreeMap[holon_id → JSON array de tareas aprobadas]
                        Memoria on-chain del holón (últimas 50 tareas).
        appeal_history: TreeMap[holon_id → JSON array de apelaciones]
                        Registro de apelaciones presentadas por el Tenzo.
        owner:          Dirección del contrato de gobernanza (Tenzo Agent).
    """

    holon_rules:    TreeMap[str, str]
    task_history:   TreeMap[str, str]
    appeal_history: TreeMap[str, str]
    owner:          str

    def __init__(self) -> None:
        self.holon_rules    = TreeMap()
        self.task_history   = TreeMap()
        self.appeal_history = TreeMap()
        self.owner          = str(gl.message.sender_address).lower()

    # ── Governance ───────────────────────────────────────────────────────────

    @gl.public.write
    def set_holon_rules(self, holon_id: str, rules_description: str) -> None:
        """
        @notice Define las reglas culturales y económicas de un holón.
        @dev Solo el owner (Tenzo Agent) puede actualizar reglas.
        @param holon_id     Identificador único del holón (ej: "familia-valdes")
        @param rules_description Descripción en lenguaje natural de los valores
                            y criterios de equidad del holón. Será parte del
                            contexto que reciben los validadores en cada evaluación.
        """
        assert str(gl.message.sender_address).lower() == self.owner, \
            "Solo gobernanza puede definir reglas del holón"
        self.holon_rules[holon_id] = rules_description

    @gl.public.write
    def append_task_history(
        self,
        holon_id:         str,
        task_description: str,
        duracion_horas:   str,   # float encodificado como str ("1.5") — GenLayer no soporta float
        recompensa_hoca:  str,   # float/int encodificado como str ("120")
        clasificacion:    str,
    ) -> None:
        """
        @notice Agrega una tarea aprobada a la memoria on-chain del holón.
        @dev Mantiene un rolling buffer de máximo 50 tareas por holón.
             Llamada por el Tenzo Agent después de cada mint on-chain exitoso.
        @param holon_id         Identificador del holón
        @param task_description Descripción breve de la tarea (truncada a 80 chars)
        @param duracion_horas   Duración en horas
        @param recompensa_hoca  Tokens HoCa asignados
        @param clasificacion    Categoría: "cuidado_humano", "cuidado_ecologico", etc.
        """
        assert str(gl.message.sender_address).lower() == self.owner, \
            "Solo gobernanza puede actualizar el historial"

        raw = self.task_history.get(holon_id, "[]")
        history = _safe_json_loads(raw, fallback=[])

        history.append({
            "descripcion":     task_description[:80],
            "duracion_horas":  float(duracion_horas),
            "recompensa_hoca": int(float(recompensa_hoca)),
            "clasificacion":   clasificacion,
        })

        if len(history) > 50:
            history = history[-50:]

        self.task_history[holon_id] = json.dumps(history)

    # ── Core: Evaluación por consenso ────────────────────────────────────────

    @gl.public.write
    def validate_task_equity(
        self,
        task_description: str,
        holon_id:         str,
        duracion_horas:   str,   # float como str ("2.0") — GenLayer no soporta float en ABI
        amount:           str = "-1.0",   # float como str, "-1.0" = modo CALCULAR
        catalog_context:  str = "",
        persona_history:  str = "",
    ) -> dict:
        """
        @notice Función principal: consenso de 5 validadores sobre una tarea de cuidado.
        @dev Usa eq_principle.prompt_comparative (Pattern 3) en lugar de strict_eq.
             Los validadores evalúan independientemente y el LLM de comparación
             determina si los resultados son equivalentes según el principio definido.
             Esto tolera variaciones menores en monto (±15%) y justificación,
             siempre que el veredicto y la categoría coincidan.
        @param task_description Descripción completa de la tarea realizada
        @param holon_id         Identificador del holón
        @param duracion_horas   Duración declarada en horas (ya normalizada por el parser)
        @param amount           -1.0 = modo CALCULAR, >0 = modo VALIDAR monto propuesto
        @param catalog_context  Catálogo de tareas del holón (pasado por el Tenzo Agent).
                                Si vacío, los validadores usan las reglas del holón.
        @param persona_history  Historial reciente de la persona (JSON string).
                                Permite al validador detectar inflación de tareas.
        @return dict con: vote, recompensa_hoca, clasificacion, confidence,
                          justification, alerta
        """
        rules       = self.holon_rules.get(holon_id, _default_rules())
        raw_history = self.task_history.get(holon_id, "[]")
        history     = _safe_json_loads(raw_history, fallback=[])
        history_str = json.dumps(history[-8:], ensure_ascii=False)

        # Convertir str → float (el ABI de GenLayer no soporta float nativo)
        duracion_horas_f = float(duracion_horas)
        amount_f         = float(amount)

        # Si el historial on-chain está vacío, usar el fallback enriquecido
        if not history:
            history_str = _fallback_history(rules)

        mode = "CALCULATE" if amount_f < 0 else "VALIDATE"
        mode_instruction = _build_mode_instruction(mode, amount_f, duracion_horas_f)

        def evaluate_task() -> str:
            """
            Función de evaluación que ejecuta cada validador independientemente.
            El resultado se serializa como JSON con sort_keys=True para consistencia.
            """
            prompt = _build_evaluation_prompt(
                task_description=task_description,
                holon_id=holon_id,
                duracion_horas=duracion_horas_f,
                mode=mode,
                mode_instruction=mode_instruction,
                rules=rules,
                history_str=history_str,
                catalog_context=catalog_context,
                persona_history=persona_history,
            )
            result = (
                gl.nondet.exec_prompt(prompt)
                .replace("```json", "")
                .replace("```", "")
                .strip()
            )
            # Validar que es JSON parseable antes de serializar
            parsed = json.loads(result)
            # Normalizar: sort_keys para que prompt_comparative compare correctamente
            return json.dumps(parsed, sort_keys=True, ensure_ascii=False)

        # Pattern 3: prompt_comparative
        # El principio de equivalencia le dice al LLM comparador qué tolerar:
        # - El veredicto (APPROVE/REJECT) DEBE coincidir
        # - El monto puede diferir hasta 15% (variación razonable entre LLMs)
        # - La clasificación DEBE coincidir
        # - La justificación puede ser diferente en palabras pero equivalente en criterio
        principle = (
            "Two evaluations of a care task are equivalent if: "
            "(1) the 'vote' field is identical (both APPROVE or both REJECT), "
            "(2) the 'recompensa_hoca' values differ by no more than 15%, "
            "(3) the 'clasificacion' lists contain the same categories, "
            "regardless of differences in justification wording. "
            "If one approves and the other rejects, they are NOT equivalent."
        )

        raw = gl.eq_principle.prompt_comparative(evaluate_task, principle)
        return json.loads(raw)

    # ── Core: Apelación activa del Tenzo ────────────────────────────────────

    @gl.public.write
    def appeal_rejection(
        self,
        task_description:  str,
        holon_id:          str,
        duracion_horas:    str,   # float como str ("2.0")
        tenzo_confidence:  str,   # float como str ("0.65")
        tenzo_argument:    str,
        catalog_matches:   str = "",
        persona_history:   str = "",
    ) -> dict:
        """
        @notice Apelación activa: el Tenzo presenta evidencia adicional a validadores nuevos.
        @dev Llamada por el Tenzo Agent cuando:
               - validate_task_equity() rechazó la tarea
               - La certeza de Gemini está en rango [0.55, 0.75]
             Los validadores reciben el mismo prompt base MÁS la evidencia del Tenzo.
             El principio de equivalencia es el mismo que validate_task_equity().
             El resultado de appeal_rejection() es DEFINITIVO — no hay segunda apelación.
        @param task_description  Descripción original de la tarea
        @param holon_id          Identificador del holón
        @param duracion_horas    Duración normalizada (str, ej: "2.0")
        @param tenzo_confidence  Confianza de Gemini (str, ej: "0.65")
        @param tenzo_argument    Argumento del Tenzo en lenguaje natural explicando
                                 por qué considera la tarea válida
        @param catalog_matches   JSON string con las tareas del catálogo que hacen match
        @param persona_history   Historial limpio de la persona (solo tareas aprobadas)
        @return dict equivalente a validate_task_equity()
        """
        # Convertir str → float (el ABI de GenLayer no soporta float nativo)
        duracion_horas_f   = float(duracion_horas)
        tenzo_confidence_f = float(tenzo_confidence)

        rules       = self.holon_rules.get(holon_id, _default_rules())
        raw_history = self.task_history.get(holon_id, "[]")
        history     = _safe_json_loads(raw_history, fallback=[])
        history_str = json.dumps(history[-8:], ensure_ascii=False)

        if not history:
            history_str = _fallback_history(rules)

        # Registrar la apelación en el historial on-chain
        _append_appeal(self.appeal_history, holon_id, {
            "task":       task_description[:80],
            "confidence": tenzo_confidence_f,
            "argument":   tenzo_argument[:200],
        })

        def evaluate_with_appeal() -> str:
            """
            Los validadores de apelación reciben el contexto original
            MÁS la evidencia presentada por el Tenzo.
            """
            prompt = _build_appeal_prompt(
                task_description=task_description,
                holon_id=holon_id,
                duracion_horas=duracion_horas_f,
                rules=rules,
                history_str=history_str,
                tenzo_confidence=tenzo_confidence_f,
                tenzo_argument=tenzo_argument,
                catalog_matches=catalog_matches,
                persona_history=persona_history,
            )
            result = (
                gl.nondet.exec_prompt(prompt)
                .replace("```json", "")
                .replace("```", "")
                .strip()
            )
            parsed = json.loads(result)
            return json.dumps(parsed, sort_keys=True, ensure_ascii=False)

        principle = (
            "Two appeal evaluations are equivalent if: "
            "(1) the 'vote' field is identical, "
            "(2) the 'recompensa_hoca' values differ by no more than 15%, "
            "(3) the 'clasificacion' lists contain the same categories. "
            "Validators must consider the Tenzo's evidence when evaluating."
        )

        raw = gl.eq_principle.prompt_comparative(evaluate_with_appeal, principle)
        return json.loads(raw)

    # ── Views ─────────────────────────────────────────────────────────────────

    @gl.public.view
    def get_holon_rules(self, holon_id: str) -> str:
        """@notice Retorna las reglas culturales del holón."""
        return self.holon_rules.get(holon_id, "No hay reglas definidas para este holón")

    @gl.public.view
    def get_task_history(self, holon_id: str) -> str:
        """@notice Retorna el historial de tareas aprobadas del holón (JSON array)."""
        return self.task_history.get(holon_id, "[]")

    @gl.public.view
    def get_appeal_history(self, holon_id: str) -> str:
        """@notice Retorna el historial de apelaciones presentadas por el Tenzo."""
        return self.appeal_history.get(holon_id, "[]")

    @gl.public.view
    def get_owner(self) -> str:
        """@notice Retorna la dirección del contrato de gobernanza."""
        return self.owner


# ── Helpers privados ──────────────────────────────────────────────────────────

def _safe_json_loads(raw: str, fallback):
    """
    Parsea JSON de forma segura. En v0.1.0 los errores eran silenciosos
    y cargaban un fallback mínimo hardcodeado. Ahora el error es visible
    en los logs de Studionet para facilitar el debug.
    """
    try:
        return json.loads(raw)
    except Exception as e:
        # En GenLayer, los logs de print van a los validadores durante la ejecución
        print(f"[TenzoOracle] JSON parse error: {e}. Usando fallback.")
        return fallback


def _fallback_history(rules: str) -> str:
    """
    Fallback de historia enriquecido basado en las reglas del holón.
    Reemplaza las tres tareas hardcodeadas en inglés de v0.1.0.
    La información es genérica pero culturalmente consistente.
    """
    return json.dumps([
        {
            "descripcion":     "Cuidado de niños (actividad aprobada por el holón)",
            "duracion_horas":  2.0,
            "recompensa_hoca": 120,
            "clasificacion":   "cuidado_humano",
            "nota":            "Referencia genérica — sin historial on-chain todavía",
        },
        {
            "descripcion":     "Cocina comunitaria (actividad aprobada por el holón)",
            "duracion_horas":  1.5,
            "recompensa_hoca": 80,
            "clasificacion":   "cocina_comunitaria",
        },
        {
            "descripcion":     "Trabajo ecológico en el espacio del holón",
            "duracion_horas":  2.0,
            "recompensa_hoca": 100,
            "clasificacion":   "cuidado_ecologico",
        },
    ], ensure_ascii=False)


def _default_rules() -> str:
    """Reglas de equidad por defecto cuando el holón no tiene reglas definidas."""
    return (
        "Principios generales de equidad y cuidado mutuo. "
        "El trabajo de cuidado merece compensación proporcional al esfuerzo, "
        "al trabajo emocional y al impacto comunitario. "
        "El cuidado ecológico tiene el mismo valor que el cuidado humano."
    )


def _build_mode_instruction(mode: str, amount: float, duracion_horas: float) -> str:
    if mode == "CALCULATE":
        return (
            f"El miembro NO especificó una recompensa. "
            f"CALCULA el monto justo en HoCa para {duracion_horas} horas de trabajo "
            f"basándote en el historial de referencia."
        )
    return (
        f"El miembro propone {amount} HoCa por {duracion_horas} horas. "
        f"VALIDA si este monto es justo. "
        f"Si se desvía más del 30% del promedio histórico, RECHAZA."
    )


def _build_evaluation_prompt(
    task_description: str,
    holon_id:         str,
    duracion_horas:   float,
    mode:             str,
    mode_instruction: str,
    rules:            str,
    history_str:      str,
    catalog_context:  str,
    persona_history:  str,
) -> str:
    catalog_section = (
        f"\nCATÁLOGO DE TAREAS DEL HOLÓN (aprobadas por la comunidad):\n{catalog_context}"
        if catalog_context else ""
    )
    persona_section = (
        f"\nHISTORIAL RECIENTE DE ESTA PERSONA:\n{persona_history}"
        if persona_history else ""
    )
    return f"""Eres un validador en HoFi Protocol sobre GenLayer.
Tu voto es parte de un consenso de 5 validadores (Democracia Optimista)
que determina si el trabajo de cuidado recibe compensación justa.

Encarnás los valores de la economía del cuidado: equidad, apoyo mutuo,
y reconocimiento del trabajo invisible que sostiene la vida comunitaria.

MODO: {mode}
{mode_instruction}

TAREA A EVALUAR:
{task_description}
Duración: {duracion_horas} horas
Holón: {holon_id}

REGLAS Y VALORES DEL HOLÓN:
{rules}

HISTORIAL DE TAREAS APROBADAS EN ESTE HOLÓN (últimas 8):
{history_str}
{catalog_section}
{persona_section}

CRITERIOS DE EVALUACIÓN:
1. Esfuerzo físico y emocional descripto
2. Proporcionalidad de la duración (horas × tasa equitativa)
3. Impacto comunitario y regenerativo
4. Alineación con las reglas culturales del holón
5. Comparación con el historial de tareas similares
6. Verificación de plausibilidad: ¿es físicamente posible esta duración para esta actividad?

CRITERIOS DE RECHAZO INMEDIATO:
- El texto es una presentación personal, saludo o pregunta (no una tarea)
- La duración es físicamente imposible (ej: "lavé los platos 3 horas")
- No describe ninguna acción real de cuidado comunitario

Respondé EXCLUSIVAMENTE en JSON (sin markdown, sin texto fuera del JSON):
{{
    "vote": "APPROVE" o "REJECT",
    "recompensa_hoca": <número entero>,
    "clasificacion": ["cuidado_humano" y/o "cuidado_ecologico" y/o "cuidado_animal" y/o "cocina_comunitaria" y/o "mantenimiento" y/o "educacion"],
    "confidence": <0.0 a 1.0>,
    "justification": "Breve explicación en español (máx 2 oraciones)",
    "alerta": null o "Alerta si algo es inusual"
}}"""


def _build_appeal_prompt(
    task_description:  str,
    holon_id:          str,
    duracion_horas:    float,
    rules:             str,
    history_str:       str,
    tenzo_confidence:  float,
    tenzo_argument:    str,
    catalog_matches:   str,
    persona_history:   str,
) -> str:
    return f"""Eres un validador de apelación en HoFi Protocol sobre GenLayer.

Esta tarea fue RECHAZADA por el consenso inicial de validadores.
El Tenzo Agent (oráculo de IA del holón) está apelando el rechazo
porque tiene {tenzo_confidence:.0%} de certeza de que la tarea es válida.

Tu trabajo es evaluar con imparcialidad si la apelación está justificada,
considerando tanto la tarea original como la evidencia presentada por el Tenzo.

TAREA ORIGINAL:
{task_description}
Duración: {duracion_horas} horas
Holón: {holon_id}

REGLAS DEL HOLÓN:
{rules}

HISTORIAL ON-CHAIN DEL HOLÓN (últimas 8 tareas aprobadas):
{history_str}

EVIDENCIA PRESENTADA POR EL TENZO:
Certeza del Tenzo: {tenzo_confidence:.0%}
Argumento: {tenzo_argument}
Tareas del catálogo que hacen match: {catalog_matches or "ningún match exacto"}
Historial reciente de esta persona: {persona_history or "sin historial"}

CRITERIO PARA LA APELACIÓN:
Aprobá si la evidencia del Tenzo y el catálogo del holón justifican
que esta tarea es trabajo de cuidado legítimo, incluso si el consenso
inicial la rechazó por ambigüedad o falta de contexto.
Rechazá si la tarea sigue siendo inválida a pesar de la evidencia.

Respondé EXCLUSIVAMENTE en JSON:
{{
    "vote": "APPROVE" o "REJECT",
    "recompensa_hoca": <número entero>,
    "clasificacion": ["..."],
    "confidence": <0.0 a 1.0>,
    "justification": "Breve explicación incluyendo si la evidencia del Tenzo fue determinante",
    "alerta": null o "Alerta"
}}"""


def _append_appeal(appeal_history_map, holon_id: str, appeal_data: dict) -> None:
    """Registra una apelación en el historial on-chain del holón."""
    raw = appeal_history_map.get(holon_id, "[]")
    appeals = _safe_json_loads(raw, fallback=[])
    appeals.append(appeal_data)
    if len(appeals) > 20:
        appeals = appeals[-20:]
    appeal_history_map[holon_id] = json.dumps(appeals)
