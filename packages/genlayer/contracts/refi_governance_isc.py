# v1.1.0
# { "Depends": "py-genlayer:1jb45aa8ynh2a9c9xn3b7qqh8sm5q93hwfp7jqmwsfhh8jpz09h6" }

"""
HoFi Protocol · ReFiGovernanceISC v1.1.0
Intelligent Smart Contract para GenLayer Testnet Bradbury

Cambios respecto a v1.0.0:
  - Estado de proposals y evaluations: dict[str, Dataclass] → TreeMap[str, str] (JSON)
    GenLayer requiere TreeMap para mappings on-chain eficientes.
    Los objetos se serializan/deserializan con json.dumps/json.loads.
  - governance: CalldataAddress → str (CalldataAddress no soportado como argumento constructor)
    El owner se almacena como str y se compara con str(gl.message.sender_address).lower()
  - forbidden_sectors: list[str] → str (JSON serializado)
    Los tipos list[] en estado son inestables en algunas versiones del runtime.
  - Decoradores @gl.public.write / @gl.public.view en todos los métodos públicos.
    Sin estos decoradores GenLayer no registra el ABI y el contrato no se puede llamar.
  - LLM: gl.get_webpage(url_fake) → gl.nondet.exec_prompt(prompt)
    El patrón correcto para evaluaciones LLM puras en GenLayer ISCs.
  - eq_principle: strict_eq → prompt_comparative
    strict_eq exige JSON byte-a-byte idéntico entre 5 validadores LLM independientes,
    lo cual es imposible para respuestas de texto libre (reasoning).
    prompt_comparative tolera variaciones en texto siempre que el veredicto coincida.

Propósito:
  Evalúa propuestas de inversión regenerativa para el CommonStakePool
  usando consenso de 5 validadores LLM con prompt_comparative.

  El CommonStakePool puede invertir hasta el 60% de su capital total en
  proyectos que pasen esta evaluación. El relayer off-chain (Cloud Run)
  con REFI_EXECUTOR_ROLE lee el resultado y llama
  CommonStakePool.executeReFiInvestment() en Sepolia / HolonChain.

Workflow:
  1. Governance propone una inversión llamando propose_investment()
  2. Cualquier participante llama evaluate_investment(proposal_id)
  3. 5 validadores LLM evalúan independientemente contra criterios ReFi
  4. prompt_comparative verifica que el veredicto (approved) sea equivalente
  5. Relayer lee approved=true y ejecuta la tx on-chain

Criterios de evaluación (configurables por governance):
  - min_impact_score   : 0.60  (30% yield / 70% impacto)
  - max_risk_score     : 0.40
  - yield_vs_impact_weight : 0.30 (yield), 0.70 (impacto)
  - local_priority_bonus   : 0.15 (bonus para proyectos locales del holón)

Sectores prohibidos (hardcoded, no modificables por governance):
  fossil_fuels · weapons · gambling · speculative_derivatives · extractive_mining
"""

import json
import typing
from genlayer import *


# ── Sectores prohibidos ────────────────────────────────────────────────────────

_FORBIDDEN = [
    "fossil_fuels",
    "weapons",
    "gambling",
    "speculative_derivatives",
    "extractive_mining",
]


# ── Helpers ────────────────────────────────────────────────────────────────────

def _safe_json_loads(raw: str, fallback=None):
    try:
        return json.loads(raw)
    except Exception:
        return fallback


def _build_evaluation_prompt(
    proposal_id:     str,
    holon_id:        str,
    project_name:    str,
    description:     str,
    amount_usdc:     str,
    expected_yield:  str,
    impact_evidence: str,
    ods_goals:       str,
    sector:          str,
    is_local:        bool,
    min_impact:      float,
    max_risk:        float,
    yld_weight:      float,
    imp_weight:      float,
    local_bonus:     float,
) -> str:
    return f"""Eres un evaluador experto en finanzas regenerativas (ReFi) y economía del cuidado.

Evalúa la siguiente propuesta de inversión para el CommonStakePool del protocolo HoFi.
HoFi es un protocolo de economía regenerativa que recompensa el trabajo de cuidado comunitario.

## PROPUESTA
- ID: {proposal_id}
- Holón: {holon_id}
- Proyecto: {project_name}
- Descripción: {description}
- Monto solicitado: {amount_usdc} USDC
- Rendimiento anual esperado: {float(expected_yield)*100:.1f}%
- Sector: {sector}
- Proyecto local (dentro del holón): {"SÍ" if is_local else "NO"}
- ODS relevantes: {ods_goals}
- Evidencia de impacto: {impact_evidence}

## CRITERIOS DE EVALUACIÓN
- Peso impacto / yield: {imp_weight*100:.0f}% impacto, {yld_weight*100:.0f}% yield
- Impact score mínimo requerido: {min_impact}
- Risk score máximo permitido: {max_risk}
- Bonus por proyecto local: {local_bonus} (se suma al composite_score si aplica)

## SECTORES PROHIBIDOS (rechazo automático)
{', '.join(_FORBIDDEN)}

## TAREA
Evalúa en estas 5 dimensiones (cada una entre 0.00 y 1.00):

1. impact_score: Impacto ambiental/social real y verificable.
   - 0.8-1.0: Impacto transformador, evidencia sólida, métricas claras
   - 0.6-0.8: Impacto significativo, evidencia moderada
   - 0.4-0.6: Impacto moderado o evidencia débil
   - 0.0-0.4: Impacto dudoso, sin evidencia

2. yield_score: Realismo del rendimiento financiero esperado.
   - 1.0: Conservador y bien fundamentado
   - 0.5: Plausible pero optimista
   - 0.0: Irreal o especulativo

3. risk_score: Riesgo de pérdida (MENOR = mejor).
   - 0.0-0.2: Riesgo muy bajo
   - 0.2-0.4: Riesgo bajo-moderado (aceptable)
   - 0.4-0.7: Riesgo alto
   - 0.7-1.0: Riesgo crítico

4. feasibility: Viabilidad de ejecución (0.0-1.0).

5. alignment: Alineación con valores ReFi y espíritu HoFi (0.0-1.0).

Calcula:
- composite_score = ({imp_weight:.2f} x impact_score) + ({yld_weight:.2f} x yield_score) + (0.10 x feasibility) + (0.10 x alignment) - (0.10 x risk_score)
- Si proyecto local, suma {local_bonus} al composite_score (máximo 1.0)
- approved = true SOLO SI: impact_score >= {min_impact} AND risk_score <= {max_risk} AND composite_score >= 0.55 AND sector NO en prohibidos

Responde ÚNICAMENTE con este JSON (sin texto adicional, sin markdown):
{{
  "proposal_id": "{proposal_id}",
  "approved": true_o_false,
  "impact_score": "X.XX",
  "yield_score": "X.XX",
  "risk_score": "X.XX",
  "composite_score": "X.XX",
  "reasoning": "Explicación concisa en español (máx 150 palabras). Usa solo comillas simples dentro del reasoning."
}}

IMPORTANTE: todos los scores con exactamente 2 decimales (ej: "0.72", no "0.7" ni "0.720").
"""


# ── Contrato principal ────────────────────────────────────────────────────────

class ReFiGovernanceISC(gl.Contract):
    """
    Gobernanza de inversiones ReFi para el CommonStakePool de HoFi.

    Cualquier dirección puede proponer. Solo governance puede cambiar criterios.
    Las evaluaciones usan 5 validadores LLM con prompt_comparative para determinismo.
    """

    # ── Estado persistente ────────────────────────────────────────────────────
    # Todos los mappings como TreeMap[str, str] con serialización JSON.
    # Los objetos complejos (propuestas, evaluaciones) se almacenan como JSON strings.

    proposals:    TreeMap[str, str]   # proposal_id → JSON(InvestmentProposal)
    evaluations:  TreeMap[str, str]   # proposal_id → JSON(EvaluationResult)
    governance:   str                 # dirección del governance (str, lowercase)

    # Criterios configurables (governance puede modificarlos)
    min_impact_score:        str      # default "0.60"
    max_risk_score:          str      # default "0.40"
    yield_vs_impact_weight:  str      # default "0.30" (30% yield, 70% impacto)
    local_priority_bonus:    str      # default "0.15"

    def __init__(self, governance_address: str) -> None:
        self.proposals   = TreeMap()
        self.evaluations = TreeMap()
        self.governance  = governance_address.lower()

        # Criterios default
        self.min_impact_score       = "0.60"
        self.max_risk_score         = "0.40"
        self.yield_vs_impact_weight = "0.30"
        self.local_priority_bonus   = "0.15"

    # ── Escritura ─────────────────────────────────────────────────────────────

    @gl.public.write
    def propose_investment(
        self,
        proposal_id:     str,
        holon_id:        str,
        project_name:    str,
        description:     str,
        amount_usdc:     str,
        expected_yield:  str,
        impact_evidence: str,
        ods_goals:       str,
        sector:          str,
        is_local:        bool,
    ) -> None:
        """
        Registra una nueva propuesta de inversión ReFi.

        Cualquier dirección puede proponer. La evaluación es independiente
        del proposer — son los validadores LLM quienes aprueban o rechazan.
        """
        assert self.proposals.get(proposal_id) is None, "proposal_id ya existe"
        assert sector not in _FORBIDDEN, (
            f"Sector prohibido: {sector}. "
            f"Sectores no permitidos: {', '.join(_FORBIDDEN)}"
        )
        assert float(amount_usdc) > 0, "amount_usdc debe ser positivo"
        assert 0 <= float(expected_yield) <= 5, "expected_yield entre 0 y 5 (500%)"

        proposal = {
            "proposal_id":    proposal_id,
            "holon_id":       holon_id,
            "proposer":       str(gl.message.sender_address).lower(),
            "project_name":   project_name,
            "description":    description,
            "amount_usdc":    amount_usdc,
            "expected_yield": expected_yield,
            "impact_evidence": impact_evidence,
            "ods_goals":      ods_goals,
            "sector":         sector,
            "is_local":       is_local,
            "proposed_at":    gl.message.timestamp,
            "status":         "pending",
        }
        self.proposals[proposal_id] = json.dumps(proposal, ensure_ascii=False)

    @gl.public.write
    def evaluate_investment(self, proposal_id: str) -> None:
        """
        Ejecuta la evaluación LLM de una propuesta (no-determinista → 5 validadores).

        Evalúa la propuesta contra los criterios ReFi configurados y registra
        el resultado. Si es aprobada, cambia el status a "approved".
        El relayer off-chain escucha este cambio y ejecuta la tx on-chain.
        """
        raw_proposal = self.proposals.get(proposal_id)
        assert raw_proposal is not None, "Propuesta no encontrada"
        proposal = _safe_json_loads(raw_proposal, fallback={})
        assert proposal.get("status") == "pending", (
            f"La propuesta ya fue evaluada: {proposal.get('status')}"
        )

        min_impact  = float(self.min_impact_score)
        max_risk    = float(self.max_risk_score)
        yld_weight  = float(self.yield_vs_impact_weight)
        imp_weight  = 1.0 - yld_weight
        local_bonus = float(self.local_priority_bonus)

        def _evaluate() -> str:
            prompt = _build_evaluation_prompt(
                proposal_id     = proposal_id,
                holon_id        = proposal["holon_id"],
                project_name    = proposal["project_name"],
                description     = proposal["description"],
                amount_usdc     = proposal["amount_usdc"],
                expected_yield  = proposal["expected_yield"],
                impact_evidence = proposal["impact_evidence"],
                ods_goals       = proposal["ods_goals"],
                sector          = proposal["sector"],
                is_local        = proposal["is_local"],
                min_impact      = min_impact,
                max_risk        = max_risk,
                yld_weight      = yld_weight,
                imp_weight      = imp_weight,
                local_bonus     = local_bonus,
            )
            raw = (
                gl.nondet.exec_prompt(prompt)
                .replace("```json", "")
                .replace("```", "")
                .strip()
            )
            try:
                start = raw.find("{")
                end   = raw.rfind("}") + 1
                if start == -1 or end == 0:
                    raise ValueError("No JSON en respuesta")
                result = json.loads(raw[start:end])

                # Normalizar scores a 2 decimales para determinismo
                for field in ["impact_score", "yield_score", "risk_score", "composite_score"]:
                    result[field] = f"{float(result[field]):.2f}"

                # Asegurar bool
                if isinstance(result.get("approved"), str):
                    result["approved"] = result["approved"].lower() == "true"

                # Verificar sector prohibido (guardia adicional)
                if proposal["sector"] in _FORBIDDEN:
                    result["approved"] = False
                    result["reasoning"] = (
                        f"Rechazo automático: sector '{proposal['sector']}' "
                        "está en la lista de sectores prohibidos."
                    )

                result["evaluated_at"] = gl.message.timestamp
                return json.dumps(result, sort_keys=True, ensure_ascii=False)

            except Exception as e:
                fallback = {
                    "proposal_id":    proposal_id,
                    "approved":       False,
                    "impact_score":   "0.00",
                    "yield_score":    "0.00",
                    "risk_score":     "1.00",
                    "composite_score":"0.00",
                    "reasoning":      f"Error de evaluación: {str(e)[:100]}",
                    "evaluated_at":   gl.message.timestamp,
                }
                return json.dumps(fallback, sort_keys=True, ensure_ascii=False)

        # Principio de equivalencia:
        # El veredicto (approved) DEBE coincidir entre todos los validadores.
        # Los scores numéricos pueden diferir ±0.05 (precisión razonable entre LLMs).
        # El reasoning puede diferir en palabras.
        principle = (
            "Dos evaluaciones son equivalentes si 'approved' coincide exactamente "
            "y los scores numéricos difieren en a lo sumo 0.05. "
            "El campo 'reasoning' puede diferir en redacción."
        )
        result_json = gl.eq_principle.prompt_comparative(_evaluate, principle)
        result = _safe_json_loads(result_json, fallback={})

        # Guardar resultado
        self.evaluations[proposal_id] = result_json

        # Actualizar status de la propuesta
        proposal["status"] = "approved" if result.get("approved") else "rejected"
        self.proposals[proposal_id] = json.dumps(proposal, ensure_ascii=False)

    @gl.public.write
    def update_criteria(
        self,
        min_impact_score:       str,
        max_risk_score:         str,
        yield_vs_impact_weight: str,
        local_priority_bonus:   str,
    ) -> None:
        """
        Actualiza los criterios de evaluación. Solo governance puede llamar esto.
        """
        assert str(gl.message.sender_address).lower() == self.governance, "Solo governance"
        assert 0 <= float(min_impact_score) <= 1
        assert 0 <= float(max_risk_score) <= 1
        assert 0 <= float(yield_vs_impact_weight) <= 1
        assert 0 <= float(local_priority_bonus) <= 1

        self.min_impact_score       = min_impact_score
        self.max_risk_score         = max_risk_score
        self.yield_vs_impact_weight = yield_vs_impact_weight
        self.local_priority_bonus   = local_priority_bonus

    # ── Lectura ───────────────────────────────────────────────────────────────

    @gl.public.view
    def get_proposal(self, proposal_id: str) -> str:
        """Retorna los datos de una propuesta como JSON string."""
        raw = self.proposals.get(proposal_id)
        assert raw is not None, "Propuesta no encontrada"
        return raw

    @gl.public.view
    def get_evaluation(self, proposal_id: str) -> str:
        """Retorna el resultado de evaluación como JSON string."""
        raw = self.evaluations.get(proposal_id)
        assert raw is not None, "Propuesta aún no evaluada"
        return raw

    @gl.public.view
    def is_approved(self, proposal_id: str) -> bool:
        """Retorna True si la propuesta fue aprobada. Usado por el relayer."""
        raw = self.evaluations.get(proposal_id)
        if raw is None:
            return False
        result = _safe_json_loads(raw, fallback={})
        return bool(result.get("approved", False))

    @gl.public.view
    def get_criteria(self) -> str:
        """Retorna los criterios actuales de evaluación como JSON string."""
        criteria = {
            "min_impact_score":       self.min_impact_score,
            "max_risk_score":         self.max_risk_score,
            "yield_vs_impact_weight": self.yield_vs_impact_weight,
            "local_priority_bonus":   self.local_priority_bonus,
            "forbidden_sectors":      _FORBIDDEN,
        }
        return json.dumps(criteria, ensure_ascii=False)

    @gl.public.view
    def get_governance(self) -> str:
        """Retorna la dirección del governance."""
        return self.governance

    @gl.public.view
    def get_pending_proposals(self) -> str:
        """Lista los IDs de propuestas pendientes como JSON array."""
        pending = [pid for pid, raw in self.proposals.items()
                   if _safe_json_loads(raw, {}).get("status") == "pending"]
        return json.dumps(pending, ensure_ascii=False)

    @gl.public.view
    def calculate_yield_distribution(
        self,
        stakes:       str,   # JSON: {"holon_id": stake_usdc_str, ...}
        reputations:  str,   # JSON: {"holon_id": reputation_0_to_1_str, ...}
        total_yield:  str,   # USDC total a distribuir
    ) -> str:
        """
        Calcula la distribución de rendimientos ReFi usando sqrt(stake) x (1 + rep x 0.5).
        Favorece participación amplia sobre concentración de poder.
        Retorna JSON: {"holon_id": yield_usdc_str, ...}
        """
        import math

        stakes_dict = json.loads(stakes)
        rep_dict    = json.loads(reputations)
        total       = float(total_yield)

        weights = {}
        for holon_id, stake_str in stakes_dict.items():
            stake = float(stake_str)
            rep   = float(rep_dict.get(holon_id, "0"))
            weights[holon_id] = math.sqrt(stake) * (1 + rep * 0.5)

        total_weight = sum(weights.values())
        if total_weight == 0:
            return json.dumps({})

        distribution = {
            hid: str(round(w / total_weight * total, 6))
            for hid, w in weights.items()
        }
        return json.dumps(distribution, ensure_ascii=False)
