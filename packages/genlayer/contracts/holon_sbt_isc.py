# v0.1.0
# { "Depends": "py-genlayer:1jb45aa8ynh2a9c9xn3b7qqh8sm5q93hwfp7jqmwsfhh8jpz09h6" }

"""
HoFi Protocol · HolonSBT ISC
Intelligent Smart Contract for GenLayer Studionet / Testnet Asimov

Manages Holón membership, reputation, and governance with LLM consensus.
AI validators evaluate contribution proofs and weighted voting legitimacy.

Integration with TenzoEquityOracle:
- Members verified here before TaskRegistry mints HOCA
- Reputation updated after each approved task
- Voting weight calculated contextually by LLM consensus
"""

import json
import typing
from genlayer import *


class HolonSBT(gl.Contract):
    """
    Soul-Bound Token registry with AI-powered contribution validation
    and contextual voting weight calculation.
    """

    members:    TreeMap[str, str]   # address → SBT JSON
    holon_name: str
    owner:      str

    def __init__(self, holon_name: str) -> None:
        self.members    = TreeMap()
        self.holon_name = holon_name
        self.owner      = gl.message.sender_address

    # ── Membership ────────────────────────────────────────────────────────

    @gl.public.write
    def issue_sbt(
        self,
        member_address: str,
        role:           str = "member",
    ) -> None:
        """
        Issues a Soul-Bound Token to a new Holón member.
        Only governance can issue SBTs.
        """
        assert gl.message.sender_address == self.owner, \
            "Only governance can issue SBTs"
        assert not self.members.get(member_address), \
            "Member already has an active SBT"

        sbt = {
            "address":    member_address,
            "holon_name": self.holon_name,
            "role":       role,
            "active":     True,
            "reputation": 0,
            "tasks_completed": 0,
        }
        self.members[member_address] = json.dumps(sbt)

    @gl.public.write
    def update_reputation(
        self,
        member_address:   str,
        tasks_completed:  int,
    ) -> None:
        """Updates reputation after a care task is approved on-chain."""
        assert gl.message.sender_address == self.owner, \
            "Only governance can update reputation"

        raw = self.members.get(member_address)
        assert raw, "Member not found"

        sbt = json.loads(raw)
        sbt["tasks_completed"] = tasks_completed
        sbt["reputation"]      = tasks_completed
        self.members[member_address] = json.dumps(sbt)

    # ── AI Contribution Validation ────────────────────────────────────────

    @gl.public.write
    def validate_contribution(
        self,
        member_address:    str,
        proof_description: str,
        category:          str,
    ) -> typing.Any:
        """
        Validates a community contribution using GenLayer LLM consensus.
        5 validators evaluate if the proof is credible and impactful.

        Args:
            member_address: Address of the contributing member
            proof_description: Evidence of contribution (text, photo URL, etc.)
            category: eco | social | tech | cuidado

        Returns:
            dict with is_valid, impact_score, justification, confidence
        """
        raw = self.members.get(member_address)
        assert raw, "Member not found"

        holon = self.holon_name
        valid_categories = ["eco", "social", "tech", "cuidado"]
        assert category in valid_categories, f"Invalid category: {category}"

        def get_validation_result() -> typing.Any:
            task = f"""
You are a validator node in the HoFi Protocol on GenLayer.
Evaluate a community contribution submitted by a Holón member.

HOLÓN: {holon}
MEMBER: {member_address[:10]}...
CATEGORY: {category}
PROOF: {proof_description}

Determine:
1. Is the description coherent and credible for this category?
2. Is the impact proportional to the described effort?
3. Are there signs of real proof (specific places, people, actions)?

Respond EXCLUSIVELY in JSON (no markdown):
{{
    "is_valid": true or false,
    "impact_score": <integer 0 to 10>,
    "justification": "Brief explanation (max 2 sentences)",
    "confidence": <0.0 to 1.0>
}}
"""
            result = (
                gl.nondet.exec_prompt(task)
                .replace("```json", "")
                .replace("```", "")
            )
            return json.loads(result)

        return gl.eq_principle.strict_eq(get_validation_result)

    # ── AI Voting Weight ──────────────────────────────────────────────────

    @gl.public.write
    def calculate_vote_weight(
        self,
        member_address:    str,
        proposal_category: str,
        proposal_summary:  str,
    ) -> typing.Any:
        """
        Calculates contextual voting weight using LLM consensus.
        A member's weight depends on their reputation in the relevant category.

        Args:
            member_address: Voter's address
            proposal_category: economica | ambiental | tecnologica | cuidado
            proposal_summary: Brief description of what's being voted on

        Returns:
            dict with weight (float, max 5.0), reasoning
        """
        raw = self.members.get(member_address)
        assert raw, "Member not found"

        sbt      = json.loads(raw)
        role     = sbt.get("role", "member")
        rep      = sbt.get("reputation", 0)
        tasks    = sbt.get("tasks_completed", 0)
        holon    = self.holon_name

        role_weights = {
            "member":      1.0,
            "coordinator": 1.5,
            "tenzo":       1.3,
            "ambassador":  1.2,
            "guardian":    1.4,
        }
        base_weight = role_weights.get(role, 1.0)

        def get_weight_result() -> typing.Any:
            task = f"""
You are a governance validator in the HoFi Protocol on GenLayer.
Calculate the contextual voting weight for a Holón member.

HOLÓN: {holon}
MEMBER ROLE: {role}
REPUTATION SCORE: {rep}
TASKS COMPLETED: {tasks}
BASE WEIGHT BY ROLE: {base_weight}

PROPOSAL CATEGORY: {proposal_category}
PROPOSAL SUMMARY: {proposal_summary}

Consider:
1. Is the member's role relevant to this proposal category?
2. Does their reputation suggest genuine community commitment?
3. Cap the weight at 5.0 to prevent tyranny of veterans

Respond EXCLUSIVELY in JSON (no markdown):
{{
    "weight": <float between 1.0 and 5.0>,
    "reasoning": "Brief explanation (max 1 sentence)"
}}
"""
            result = (
                gl.nondet.exec_prompt(task)
                .replace("```json", "")
                .replace("```", "")
            )
            return json.loads(result)

        return gl.eq_principle.strict_eq(get_weight_result)

    # ── Views ─────────────────────────────────────────────────────────────

    @gl.public.view
    def get_member(self, member_address: str) -> str:
        """Returns the SBT data for a member."""
        return self.members.get(member_address, "{}")

    @gl.public.view
    def is_member(self, member_address: str) -> bool:
        """Returns True if the address has an active SBT."""
        raw = self.members.get(member_address)
        if not raw:
            return False
        try:
            sbt = json.loads(raw)
            return sbt.get("active", False)
        except Exception:
            return False

    @gl.public.view
    def get_holon_name(self) -> str:
        """Returns the Holón name."""
        return self.holon_name
