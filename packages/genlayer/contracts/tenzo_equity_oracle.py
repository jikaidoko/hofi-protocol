# v0.1.0
# { "Depends": "py-genlayer:1jb45aa8ynh2a9c9xn3b7qqh8sm5q93hwfp7jqmwsfhh8jpz09h6" }

"""
HoFi Protocol · TenzoEquityOracle
Intelligent Smart Contract for GenLayer Testnet Asimov

This ISC acts as the decentralized equity oracle for HoFi's care economy.
Instead of a single AI deciding task rewards, a jury of 5 GenLayer
validators — each running a different LLM — must reach consensus.

This is the bridge from "AI advises" to "AI consensus enforces".

Workflow:
1. Community member proposes a care task with optional reward
2. TenzoEquityOracle.validate_task_equity() is called
3. 5 GenLayer validators independently evaluate the task
4. Optimistic Democracy consensus is reached
5. If APPROVED, Tenzo Agent calls TaskRegistry.approveTask() on Ethereum Sepolia
"""

import json
import typing
from genlayer import *


class TenzoEquityOracle(gl.Contract):
    """
    Decentralized equity oracle for HoFi's care economy.
    Uses GenLayer's Optimistic Democracy to validate care task rewards.
    """

    holon_rules:  TreeMap[str, str]
    task_history: TreeMap[str, str]
    owner:        str

    def __init__(self) -> None:
        self.holon_rules  = TreeMap()
        self.task_history = TreeMap()
        self.owner        = gl.message.sender_address

    # ── Governance ───────────────────────────────────────────────────────

    @gl.public.write
    def set_holon_rules(self, holon_id: str, rules_description: str) -> None:
        """Define cultural and economic rules for a specific Holón."""
        assert gl.message.sender_address == self.owner, \
            "Only governance can define Holón rules"
        self.holon_rules[holon_id] = rules_description

    @gl.public.write
    def append_task_history(
        self,
        holon_id:         str,
        task_description: str,
        duracion_horas:   float,
        recompensa_hoca:  float,
        clasificacion:    str,
    ) -> None:
        """Appends an approved task to the Holón's on-chain memory."""
        assert gl.message.sender_address == self.owner, \
            "Only governance can update task history"

        raw = self.task_history.get(holon_id, "[]")
        try:
            history = json.loads(raw)
        except Exception:
            history = []

        history.append({
            "descripcion":    task_description[:80],
            "duracion_horas": duracion_horas,
            "recompensa_hoca": recompensa_hoca,
            "clasificacion":  clasificacion,
        })

        if len(history) > 50:
            history = history[-50:]

        self.task_history[holon_id] = json.dumps(history)

    # ── LLM Consensus — Core Function ────────────────────────────────────

    @gl.public.write
    def validate_task_equity(
        self,
        task_description: str,
        holon_id:         str,
        duracion_horas:   float,
        amount:           float = -1.0,
    ) -> typing.Any:
        """
        Core function: invokes GenLayer's Optimistic Democracy consensus.
        5 validators each run the prompt with their own LLM and must agree.

        Args:
            task_description: Full description of the care task
            holon_id: The Holón this task belongs to
            duracion_horas: Task duration in hours
            amount: Proposed reward (-1 = CALCULATE mode, >0 = VALIDATE mode)

        Returns:
            dict with vote, recompensa_hoca, clasificacion, confidence,
            justification, and alerta
        """
        rules = self.holon_rules.get(
            holon_id,
            "General principles of equity and mutual care. "
            "Care work deserves fair compensation proportional to "
            "effort, emotional labor, and community impact."
        )

        raw_history = self.task_history.get(holon_id, "[]")
        try:
            history      = json.loads(raw_history)
            history_text = json.dumps(history[-5:], ensure_ascii=False)
        except Exception:
            history_text = json.dumps([
                {"descripcion": "Childcare (2h)",         "recompensa_hoca": 200},
                {"descripcion": "Community cooking (1.5h)", "recompensa_hoca": 120},
                {"descripcion": "Space cleaning (1h)",    "recompensa_hoca":  80},
            ])

        mode = "CALCULATE" if amount < 0 else "VALIDATE"

        if mode == "CALCULATE":
            mode_instruction = (
                f"The member did NOT specify a reward. "
                f"CALCULATE the fair HOCA amount for {duracion_horas} hours of work "
                f"based on the historical reference below."
            )
        else:
            mode_instruction = (
                f"The member proposes {amount} HOCA for {duracion_horas} hours. "
                f"VALIDATE if this amount is fair. "
                f"If it deviates more than 30% from the historical average, REJECT."
            )

        holon_id_str    = holon_id
        duracion_str    = str(duracion_horas)
        rules_str       = rules
        history_str     = history_text

        def get_equity_result() -> typing.Any:
            task = f"""
You are a validator node in the HoFi Protocol on GenLayer.
Your vote is part of a 5-validator consensus (Optimistic Democracy)
that determines whether care work receives fair compensation.

You embody the values of the care economy: fairness, mutual support,
and recognition of invisible labor that sustains community life.

MODE: {mode}
{mode_instruction}

TASK TO EVALUATE:
{task_description}
Duration: {duracion_str} hours
Holón: {holon_id_str}

HOLÓN RULES AND VALUES:
{rules_str}

HISTORICAL REFERENCE (last approved tasks in this Holón):
{history_str}

Evaluation criteria:
1. Physical and emotional effort described
2. Duration proportionality (hours x fair hourly rate)
3. Community and regenerative impact
4. Alignment with Holón cultural rules
5. Comparison with historical tasks of similar type

Respond EXCLUSIVELY in JSON (no markdown, no text outside JSON):
{{
    "vote": "APPROVE" or "REJECT",
    "recompensa_hoca": <float>,
    "clasificacion": ["cuidado" and/or "regenerativa" and/or "comunitaria"],
    "confidence": <0.0 to 1.0>,
    "justification": "Brief explanation (max 2 sentences)",
    "alerta": null or "Alert if unusual"
}}
"""
            result = (
                gl.nondet.exec_prompt(task)
                .replace("```json", "")
                .replace("```", "")
            )
            return json.loads(result)

        # GenLayer's Optimistic Democracy: all 5 validators must reach consensus
        return gl.eq_principle.strict_eq(get_equity_result)

    # ── Views ─────────────────────────────────────────────────────────────

    @gl.public.view
    def get_holon_rules(self, holon_id: str) -> str:
        """Returns the cultural rules for a specific Holón."""
        return self.holon_rules.get(holon_id, "No rules defined for this Holón")

    @gl.public.view
    def get_task_history(self, holon_id: str) -> str:
        """Returns the task history for a specific Holón."""
        return self.task_history.get(holon_id, "[]")

    @gl.public.view
    def get_owner(self) -> str:
        """Returns the contract owner address."""
        return self.owner
