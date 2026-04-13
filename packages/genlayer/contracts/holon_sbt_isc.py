# v0.2.1
# { "Depends": "py-genlayer:1jb45aa8ynh2a9c9xn3b7qqh8sm5q93hwfp7jqmwsfhh8jpz09h6" }

"""
HoFi Protocol · HolonSBT ISC v0.2.1
Intelligent Smart Contract for GenLayer Testnet Bradbury / Asimov

Cambios respecto a v0.1.0:
  - eq_principle.strict_eq → eq_principle.prompt_comparative (Pattern 3)
    En v0.1.0 strict_eq requería que los 5 validadores produjesen JSON
    byte-a-byte idéntico, lo cual es frágil con LLMs (distintas APIs dan
    distintas justificaciones para el mismo veredicto).
    prompt_comparative tolera variaciones en justification/reasoning
    siempre que el veredicto (is_valid) y el impact_score sean equivalentes.

  - revoke_sbt(): nueva función de gobernanza para desactivar un SBT.
    Permite al owner marcar active=False sin borrar el historial del miembro.
    El miembro pierde acceso a validate_contribution y calculate_vote_weight
    hasta que se le emita un SBT nuevo.

  - update_sbt_role(): nueva función de gobernanza para cambiar el rol de
    un miembro (member → coordinator, tenzo, ambassador, guardian).
    El rol determina el peso base en calculate_vote_weight.

  - str(gl.message.sender_address).lower() — consistencia con TenzoEquityOracle.
    En v0.1.0 se comparaba gl.message.sender_address == self.owner directamente,
    pero dependiendo del contexto la dirección puede venir en distintos formatos.
    Normalizar con str().lower() elimina la posibilidad de falsos fallos de auth.

  - Manejo de errores robusto con _safe_json_loads().
    Los errores de JSON parsing ahora se imprimen en los logs del validador
    en lugar de propagar excepciones inesperadas.

  - NatSpec completo en todas las funciones públicas.

  - get_owner() y get_member_count() como vistas adicionales (paridad con
    TenzoEquityOracle para facilitar la integración desde genlayer_bridge.py).

  - Campos de SBT enriquecidos: se agrega join_block como referencia temporal
    y contribution_categories para registrar en qué categorías ha aportado
    el miembro (actualizado por validate_contribution cuando is_valid=True).

  - Nota sobre float: los parámetros que en el futuro requieran flotantes deben
    pasarse como str (ej: "1.5") y convertirse internamente con float(). El ABI
    de GenLayer no soporta float nativo (calldata encoder y get_schema lo rechazan).

Workflow de gobernanza:
  1. El owner llama issue_sbt() para dar membresía a un nuevo miembro del holón
  2. El miembro presenta una contribución → validate_contribution() via Tenzo Agent
  3. 5 validadores GenLayer evalúan la prueba con sus propios LLMs
  4. Si is_valid=True → Tenzo Agent llama update_reputation() para actualizar on-chain
  5. En governance → miembro puede pedir recalcular su peso: calculate_vote_weight()
  6. El owner puede upgrade roles con update_sbt_role() o revocar con revoke_sbt()
"""

import json
import typing
from genlayer import *


class HolonSBT(gl.Contract):
    """
    Soul-Bound Token registry con validación de contribuciones por consenso LLM
    y cálculo contextual de peso de voto para la gobernanza del holón.

    State variables:
        members:      TreeMap[address → SBT JSON]
                      Mapa de membresías activas e inactivas del holón.
        holon_name:   str
                      Nombre del holón (inmutable post-deploy).
        owner:        str
                      Dirección del contrato de gobernanza (Tenzo Agent).
        member_count: u32
                      Contador de SBTs emitidos (incluye revocados).
                      u32 requerido por GenVM Studionet (Asimov) — int nativo
                      ya no es aceptado como campo de storage (v0.2.1).
    """

    members:      TreeMap[str, str]
    holon_name:   str
    owner:        str
    member_count: u32

    def __init__(self, holon_name: str) -> None:
        self.members      = TreeMap()
        self.holon_name   = holon_name
        self.owner        = str(gl.message.sender_address).lower()
        self.member_count = 0

    # ── Membership ─────────────────────────────────────────────────────────────

    @gl.public.write
    def issue_sbt(
        self,
        member_address: str,
        role:           str = "member",
    ) -> None:
        """
        @notice Emite un Soul-Bound Token a un nuevo miembro del holón.
        @dev Solo el owner (Tenzo Agent / gobernanza) puede emitir SBTs.
             Un miembro no puede recibir un segundo SBT activo.
             Si tuvo un SBT revocado previamente, debe usarse revoke_sbt()
             + issue_sbt() en secuencia para re-incorporar al miembro.
        @param member_address Dirección del miembro (lowercase recomendado)
        @param role           Rol inicial: member | coordinator | tenzo |
                              ambassador | guardian (default: "member")
        """
        assert str(gl.message.sender_address).lower() == self.owner, \
            "Solo gobernanza puede emitir SBTs"

        existing = self.members.get(member_address)
        if existing:
            sbt = _safe_json_loads(existing, fallback={})
            assert not sbt.get("active", False), \
                "El miembro ya tiene un SBT activo"

        valid_roles = {"member", "coordinator", "tenzo", "ambassador", "guardian"}
        assert role in valid_roles, f"Rol inválido: {role}"

        sbt = {
            "address":                 member_address,
            "holon_name":              self.holon_name,
            "role":                    role,
            "active":                  True,
            "reputation":              0,
            "tasks_completed":         0,
            "contribution_categories": [],
            "join_block":              "genesis",
        }
        self.members[member_address] = json.dumps(sbt, ensure_ascii=False)
        self.member_count += 1

    @gl.public.write
    def revoke_sbt(self, member_address: str) -> None:
        """
        @notice Revoca el SBT de un miembro, marcándolo como inactivo.
        @dev El historial (reputation, tasks_completed) se preserva en el estado.
             El miembro pierde acceso a validate_contribution y calculate_vote_weight.
             Solo el owner puede revocar SBTs.
        @param member_address Dirección del miembro a revocar
        """
        assert str(gl.message.sender_address).lower() == self.owner, \
            "Solo gobernanza puede revocar SBTs"

        raw = self.members.get(member_address)
        assert raw, "Miembro no encontrado"

        sbt = _safe_json_loads(raw, fallback={})
        assert sbt.get("active", False), "El SBT ya está inactivo"

        sbt["active"] = False
        self.members[member_address] = json.dumps(sbt, ensure_ascii=False)

    @gl.public.write
    def update_sbt_role(self, member_address: str, new_role: str) -> None:
        """
        @notice Actualiza el rol de un miembro existente.
        @dev Permite promociones y cambios de responsabilidad dentro del holón.
             Solo el owner puede modificar roles.
        @param member_address Dirección del miembro
        @param new_role       Nuevo rol: member | coordinator | tenzo |
                              ambassador | guardian
        """
        assert str(gl.message.sender_address).lower() == self.owner, \
            "Solo gobernanza puede actualizar roles"

        raw = self.members.get(member_address)
        assert raw, "Miembro no encontrado"

        valid_roles = {"member", "coordinator", "tenzo", "ambassador", "guardian"}
        assert new_role in valid_roles, f"Rol inválido: {new_role}"

        sbt = _safe_json_loads(raw, fallback={})
        assert sbt.get("active", False), "No se puede cambiar el rol de un SBT inactivo"

        sbt["role"] = new_role
        self.members[member_address] = json.dumps(sbt, ensure_ascii=False)

    @gl.public.write
    def update_reputation(
        self,
        member_address:  str,
        tasks_completed: int,
        reputation:      int = -1,
    ) -> None:
        """
        @notice Actualiza la reputación de un miembro tras una tarea aprobada.
        @dev Llamada por el Tenzo Agent después de cada mint on-chain exitoso.
             Si reputation=-1 (default), se usa tasks_completed como reputación.
             Para un esquema de reputación más fino, pasar reputation explícito.
             Solo el owner puede actualizar reputación.
        @param member_address  Dirección del miembro
        @param tasks_completed Número total de tareas completadas (acumulativo)
        @param reputation      Puntuación de reputación explícita, o -1 para auto
        """
        assert str(gl.message.sender_address).lower() == self.owner, \
            "Solo gobernanza puede actualizar reputación"

        raw = self.members.get(member_address)
        assert raw, "Miembro no encontrado"

        sbt = _safe_json_loads(raw, fallback={})
        sbt["tasks_completed"] = tasks_completed
        sbt["reputation"]      = tasks_completed if reputation < 0 else reputation
        self.members[member_address] = json.dumps(sbt, ensure_ascii=False)

    # ── AI: Validación de contribuciones ───────────────────────────────────────

    @gl.public.write
    def validate_contribution(
        self,
        member_address:    str,
        proof_description: str,
        category:          str,
    ) -> typing.Any:
        """
        @notice Valida una contribución comunitaria usando consenso LLM de GenLayer.
        @dev Usa eq_principle.prompt_comparative (Pattern 3).
             Los 5 validadores evalúan independientemente y el LLM comparador
             determina si los resultados son equivalentes según el principio definido.
             strict_eq era frágil porque distintos LLMs dan distintas justificaciones
             para el mismo veredicto — prompt_comparative tolera esa variación.
             La función requiere SBT activo — revoke_sbt() bloquea el acceso.
        @param member_address    Dirección del miembro que contribuyó
        @param proof_description Evidencia de la contribución (texto, URL de foto, etc.)
        @param category          eco | social | tech | cuidado
        @return dict con is_valid, impact_score (0-10), justification, confidence
        """
        raw = self.members.get(member_address)
        assert raw, "Miembro no encontrado"
        sbt = _safe_json_loads(raw, fallback={})
        assert sbt.get("active", False), "El SBT está inactivo"

        valid_categories = {"eco", "social", "tech", "cuidado"}
        assert category in valid_categories, f"Categoría inválida: {category}"

        holon       = self.holon_name
        member_role = sbt.get("role", "member")
        member_rep  = sbt.get("reputation", 0)

        def get_validation_result() -> str:
            prompt = _build_contribution_prompt(
                holon=holon,
                member_address=member_address,
                member_role=member_role,
                member_rep=member_rep,
                category=category,
                proof_description=proof_description,
            )
            result = (
                gl.nondet.exec_prompt(prompt)
                .replace("```json", "")
                .replace("```", "")
                .strip()
            )
            parsed = json.loads(result)
            return json.dumps(parsed, sort_keys=True, ensure_ascii=False)

        # Principio de equivalencia para validate_contribution:
        # El veredicto (is_valid) DEBE coincidir entre validadores.
        # El impact_score puede diferir hasta 2 puntos (variación razonable entre LLMs).
        # La justificación puede diferir en palabras pero deben apuntar al mismo criterio.
        principle = (
            "Two contribution validations are equivalent if: "
            "(1) the 'is_valid' field is identical (both true or both false), "
            "(2) the 'impact_score' values differ by no more than 2 points (out of 10), "
            "regardless of differences in justification wording or confidence value. "
            "If one marks is_valid=true and the other is_valid=false, they are NOT equivalent."
        )

        raw_result = gl.eq_principle.prompt_comparative(get_validation_result, principle)
        result_dict = json.loads(raw_result)

        # Si la contribución fue válida, registrar la categoría en el SBT
        if result_dict.get("is_valid") is True:
            _append_contribution_category(self.members, member_address, category)

        return result_dict

    # ── AI: Peso de voto contextual ────────────────────────────────────────────

    @gl.public.write
    def calculate_vote_weight(
        self,
        member_address:    str,
        proposal_category: str,
        proposal_summary:  str,
    ) -> typing.Any:
        """
        @notice Calcula el peso de voto contextual de un miembro para una propuesta.
        @dev Usa eq_principle.prompt_comparative (Pattern 3).
             El peso depende del rol del miembro, su reputación y la relevancia
             de su historial de contribuciones para la categoría de la propuesta.
             Máximo: 5.0 (límite antitiranía de veteranos).
             Mínimo: 1.0 (todo miembro activo tiene voz).
             La función requiere SBT activo.
        @param member_address    Dirección del votante
        @param proposal_category economica | ambiental | tecnologica | cuidado
        @param proposal_summary  Resumen breve de lo que se está votando
        @return dict con weight (float max 5.0), reasoning
        """
        raw = self.members.get(member_address)
        assert raw, "Miembro no encontrado"
        sbt = _safe_json_loads(raw, fallback={})
        assert sbt.get("active", False), "El SBT está inactivo"

        role       = sbt.get("role", "member")
        rep        = sbt.get("reputation", 0)
        tasks      = sbt.get("tasks_completed", 0)
        categories = sbt.get("contribution_categories", [])
        holon      = self.holon_name

        base_weight = _role_base_weight(role)

        def get_weight_result() -> str:
            prompt = _build_vote_weight_prompt(
                holon=holon,
                role=role,
                rep=rep,
                tasks=tasks,
                base_weight=base_weight,
                categories=categories,
                proposal_category=proposal_category,
                proposal_summary=proposal_summary,
            )
            result = (
                gl.nondet.exec_prompt(prompt)
                .replace("```json", "")
                .replace("```", "")
                .strip()
            )
            parsed = json.loads(result)
            return json.dumps(parsed, sort_keys=True, ensure_ascii=False)

        # Principio de equivalencia para calculate_vote_weight:
        # El weight puede diferir hasta 0.5 puntos (variación razonable entre LLMs).
        # El reasoning puede diferir en palabras — lo importante es el valor numérico.
        principle = (
            "Two voting weight calculations are equivalent if: "
            "the 'weight' values differ by no more than 0.5 (on a 1.0 to 5.0 scale), "
            "regardless of differences in reasoning text. "
            "Both weights must be within the valid range of 1.0 to 5.0."
        )

        raw_result = gl.eq_principle.prompt_comparative(get_weight_result, principle)
        return json.loads(raw_result)

    # ── Views ──────────────────────────────────────────────────────────────────

    @gl.public.view
    def get_member(self, member_address: str) -> str:
        """@notice Retorna los datos del SBT de un miembro en JSON (o '{}' si no existe)."""
        return self.members.get(member_address, "{}")

    @gl.public.view
    def is_member(self, member_address: str) -> bool:
        """@notice Retorna True si la dirección tiene un SBT activo en este holón."""
        raw = self.members.get(member_address)
        if not raw:
            return False
        sbt = _safe_json_loads(raw, fallback={})
        return sbt.get("active", False)

    @gl.public.view
    def get_holon_name(self) -> str:
        """@notice Retorna el nombre del holón."""
        return self.holon_name

    @gl.public.view
    def get_owner(self) -> str:
        """@notice Retorna la dirección del contrato de gobernanza (owner)."""
        return self.owner

    @gl.public.view
    def get_member_count(self) -> int:
        """@notice Retorna el número total de SBTs emitidos (incluye revocados)."""
        return self.member_count


# ── Helpers privados ────────────────────────────────────────────────────────────

def _safe_json_loads(raw: str, fallback):
    """
    Parsea JSON de forma segura. Los errores de parsing se imprimen en los logs
    del validador (visibles en Studionet) en lugar de propagarse silenciosamente.
    """
    try:
        return json.loads(raw)
    except Exception as e:
        print(f"[HolonSBT] JSON parse error: {e}. Usando fallback.")
        return fallback


def _role_base_weight(role: str) -> float:
    """
    Retorna el peso base de voto según el rol del miembro.
    El peso final puede ser mayor (hasta 5.0) si la reputación es alta
    y el rol es relevante para la categoría de la propuesta.
    """
    weights = {
        "member":      1.0,
        "coordinator": 1.5,
        "tenzo":       1.3,
        "ambassador":  1.2,
        "guardian":    1.4,
    }
    return weights.get(role, 1.0)


def _append_contribution_category(
    members_map,
    member_address: str,
    category: str,
) -> None:
    """
    Agrega una categoría de contribución al SBT del miembro si no estaba ya.
    Registrado on-chain para que calculate_vote_weight pueda usar el historial
    de categorías en las que el miembro ha contribuido activamente.
    """
    raw = members_map.get(member_address)
    if not raw:
        return
    sbt = _safe_json_loads(raw, fallback={})
    cats: list = sbt.get("contribution_categories", [])
    if category not in cats:
        cats.append(category)
        sbt["contribution_categories"] = cats
        members_map[member_address] = json.dumps(sbt, ensure_ascii=False)


def _build_contribution_prompt(
    holon:            str,
    member_address:   str,
    member_role:      str,
    member_rep:       int,
    category:         str,
    proof_description: str,
) -> str:
    return f"""Eres un validador en el HoFi Protocol sobre GenLayer.
Evaluás contribuciones comunitarias para el holón "{holon}" como parte de un
consenso de 5 validadores (Democracia Optimista de GenLayer).

INFORMACIÓN DEL MIEMBRO:
Dirección: {member_address[:12]}...
Rol en el holón: {member_role}
Reputación acumulada: {member_rep} puntos
Categoría de contribución: {category}

PRUEBA DE CONTRIBUCIÓN PRESENTADA:
{proof_description}

CRITERIOS DE EVALUACIÓN:
1. ¿La descripción es coherente y creíble para la categoría "{category}"?
2. ¿El impacto es proporcional al esfuerzo descripto?
3. ¿Hay señales de prueba real (lugares, personas, acciones concretas)?
4. ¿El rol del miembro es consistente con este tipo de contribución?

CRITERIOS DE RECHAZO INMEDIATO:
- La descripción es vaga, genérica o sin detalles verificables
- No describe una acción real de contribución comunitaria
- El impacto descripto es imposible o exagerado

Respondé EXCLUSIVAMENTE en JSON (sin markdown, sin texto fuera del JSON):
{{
    "is_valid": true o false,
    "impact_score": <entero 0 a 10>,
    "justification": "Breve explicación en español (máx 2 oraciones)",
    "confidence": <0.0 a 1.0>
}}"""


def _build_vote_weight_prompt(
    holon:             str,
    role:              str,
    rep:               int,
    tasks:             int,
    base_weight:       float,
    categories:        list,
    proposal_category: str,
    proposal_summary:  str,
) -> str:
    cats_str = ", ".join(categories) if categories else "ninguna registrada aún"
    return f"""Eres un validador de gobernanza en el HoFi Protocol sobre GenLayer.
Calculás el peso de voto contextual de un miembro del holón "{holon}"
para una propuesta específica, como parte de un consenso de 5 validadores.

DATOS DEL MIEMBRO:
Rol: {role}
Reputación: {rep} puntos
Tareas completadas: {tasks}
Peso base por rol: {base_weight}
Categorías en las que contribuyó: {cats_str}

PROPUESTA A VOTAR:
Categoría: {proposal_category}
Resumen: {proposal_summary}

INSTRUCCIONES:
Calculá un peso de voto entre 1.0 y 5.0 teniendo en cuenta:
1. ¿El rol del miembro es relevante para esta categoría de propuesta?
2. ¿Su reputación y número de tareas sugieren compromiso genuino con la comunidad?
3. ¿Ha contribuido activamente en la categoría de esta propuesta?
4. Limitá el peso máximo a 5.0 para evitar la tiranía de los veteranos.
5. El peso mínimo es 1.0 — todo miembro activo tiene voz.

Respondé EXCLUSIVAMENTE en JSON (sin markdown, sin texto fuera del JSON):
{{
    "weight": <float entre 1.0 y 5.0>,
    "reasoning": "Breve explicación en español (máx 1 oración)"
}}"""
