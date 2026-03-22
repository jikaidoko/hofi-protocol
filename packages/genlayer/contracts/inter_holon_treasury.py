# v0.1.0
# { "Depends": "py-genlayer:1jb45aa8ynh2a9c9xn3b7qqh8sm5q93hwfp7jqmwsfhh8jpz09h6" }

"""
HoFi Protocol · InterHolonTreasury ISC
Intelligent Smart Contract for GenLayer Studionet / Testnet Asimov

Manages inter-holonic economic agreements using LLM consensus.
When two Holóns want to collaborate (shared solar, joint childcare,
environmental monitoring), this ISC evaluates if the proposed
resource-sharing agreement is fair for both parties.

This is the Ambassador Agent on-chain.

Workflow:
1. Holón A proposes a collaboration to Holón B
2. Both Holóns submit their staking and contribution data
3. 5 GenLayer validators evaluate the fairness of the agreement
4. Consensus determines if the collaboration is approved
5. If APPROVED, the proportional HOCA allocation is locked
"""

import json
import typing
from genlayer import *


class InterHolonTreasury(gl.Contract):
    """
    Inter-holonic treasury and collaboration oracle.
    Uses GenLayer's Optimistic Democracy to validate resource-sharing
    agreements between Holóns.
    """

    proposals:   TreeMap[str, str]   # proposal_id → proposal JSON
    holon_data:  TreeMap[str, str]   # holon_id → staking/stats JSON
    owner:       str
    proposal_counter: u256

    def __init__(self) -> None:
        self.proposals        = TreeMap()
        self.holon_data       = TreeMap()
        self.owner            = gl.message.sender_address
        self.proposal_counter = u256(0)

    # ── Holón Registration ────────────────────────────────────────────────

    @gl.public.write
    def register_holon(
        self,
        holon_id:      str,
        holon_name:    str,
        staking_hoca:  float,
        members_count: int,
        specialties:   str,
    ) -> None:
        """
        Registers a Holón's economic profile for inter-holonic evaluation.
        """
        assert gl.message.sender_address == self.owner, \
            "Only governance can register Holóns"

        data = {
            "holon_id":      holon_id,
            "holon_name":    holon_name,
            "staking_hoca":  staking_hoca,
            "members_count": members_count,
            "specialties":   specialties,
            "collaborations_completed": 0,
        }
        self.holon_data[holon_id] = json.dumps(data)

    # ── Collaboration Proposal ────────────────────────────────────────────

    @gl.public.write
    def propose_collaboration(
        self,
        holon_a_id:          str,
        holon_b_id:          str,
        collaboration_type:  str,
        description:         str,
        hoca_a_contribution: float,
        hoca_b_contribution: float,
    ) -> str:
        """
        Proposes a collaboration between two Holóns.
        Returns the proposal ID.
        """
        self.proposal_counter = u256(int(self.proposal_counter) + 1)
        proposal_id = f"collab_{holon_a_id}_{holon_b_id}_{int(self.proposal_counter)}"

        proposal = {
            "id":                   proposal_id,
            "holon_a":              holon_a_id,
            "holon_b":              holon_b_id,
            "type":                 collaboration_type,
            "description":          description,
            "hoca_a_contribution":  hoca_a_contribution,
            "hoca_b_contribution":  hoca_b_contribution,
            "status":               "pending",
        }
        self.proposals[proposal_id] = json.dumps(proposal)
        return proposal_id

    # ── LLM Consensus — Collaboration Validation ─────────────────────────

    @gl.public.write
    def evaluate_collaboration(self, proposal_id: str) -> typing.Any:
        """
        Evaluates a collaboration proposal using GenLayer LLM consensus.
        5 validators assess if the resource-sharing agreement is fair.

        Returns:
            dict with approved, fairness_score, adjustments, justification
        """
        raw_proposal = self.proposals.get(proposal_id)
        assert raw_proposal, "Proposal not found"

        proposal = json.loads(raw_proposal)

        raw_a = self.holon_data.get(proposal["holon_a"], "{}")
        raw_b = self.holon_data.get(proposal["holon_b"], "{}")

        holon_a_str   = raw_a
        holon_b_str   = raw_b
        proposal_str  = json.dumps(proposal, ensure_ascii=False)

        def get_evaluation_result() -> typing.Any:
            task = f"""
You are a validator node in the HoFi Protocol on GenLayer.
Evaluate a collaboration proposal between two Holóns.

Your role is to ensure fairness and regenerative value in
inter-community economic agreements.

PROPOSAL:
{proposal_str}

HOLÓN A PROFILE:
{holon_a_str}

HOLÓN B PROFILE:
{holon_b_str}

Evaluate:
1. Is the HOCA contribution ratio proportional to each Holón's capacity?
2. Does the collaboration type match both Holóns' specialties?
3. Is the described benefit mutual and regenerative?
4. Are there signs of exploitation or imbalance?

Respond EXCLUSIVELY in JSON (no markdown):
{{
    "approved": true or false,
    "fairness_score": <0.0 to 1.0>,
    "hoca_a_recommended": <float — suggested contribution for Holón A>,
    "hoca_b_recommended": <float — suggested contribution for Holón B>,
    "justification": "Brief explanation (max 2 sentences)",
    "adjustments": null or "Suggested adjustment if not approved"
}}
"""
            result = (
                gl.nondet.exec_prompt(task)
                .replace("```json", "")
                .replace("```", "")
            )
            return json.loads(result)

        evaluation = gl.eq_principle.strict_eq(get_evaluation_result)

        # Update proposal status
        proposal["status"]     = "approved" if evaluation.get("approved") else "rejected"
        proposal["evaluation"] = evaluation
        self.proposals[proposal_id] = json.dumps(proposal)

        return evaluation

    # ── Views ─────────────────────────────────────────────────────────────

    @gl.public.view
    def get_proposal(self, proposal_id: str) -> str:
        """Returns the full proposal data."""
        return self.proposals.get(proposal_id, "{}")

    @gl.public.view
    def get_holon_data(self, holon_id: str) -> str:
        """Returns the economic profile of a Holón."""
        return self.holon_data.get(holon_id, "{}")

    @gl.public.view
    def get_owner(self) -> str:
        """Returns the contract owner address."""
        return self.owner
