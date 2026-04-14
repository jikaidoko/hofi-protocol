// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "@openzeppelin/contracts/access/AccessControl.sol";

/**
 * @title TenzoAgentRegistry
 * @author HoFi Protocol
 * @notice ERC-8004 compliant registry for the Tenzo Autonomous Agent
 * @dev Implements the three ERC-8004 registries adapted for HoFi's care economy.
 *      ERC-8004 went live on Ethereum mainnet January 29, 2026.
 *      This contract registers the Tenzo Agent as a trustless autonomous entity.
 *
 * ERC-8004 Reference: https://eips.ethereum.org/EIPS/eip-8004
 * Authors: MetaMask, Ethereum Foundation, Google, Coinbase
 *
 * Integration:
 * - Tenzo Agent (Cloud Run) registers here on first deployment
 * - HoCaToken funds the Tenzo's sub-treasury for x402 payments
 * - Reputation is updated after each task evaluation cycle
 * - Other agents (Ambassador, Treasurer) discover Tenzo via Identity Registry
 */
contract TenzoAgentRegistry is AccessControl {

    bytes32 public constant TENZO_ROLE    = keccak256("TENZO_ROLE");
    bytes32 public constant HOLON_ROLE    = keccak256("HOLON_ROLE");

    // ── Identity Registry (ERC-8004 Section 4.1) ─────────────────────────

    /**
     * @notice Tenzo Agent's on-chain identity (ERC-8004 AgentCard)
     * @dev The AgentCard points to the off-chain endpoint where the full
     *      capability description lives. On-chain we store only the essentials.
     */
    struct TenzoIdentity {
        uint256 agentId;
        string  name;
        string  description;
        string  endpoint;          // Cloud Run URL
        string  agentCardURI;      // IPFS/HTTPS AgentCard JSON
        bool    x402Support;       // supports micropayments
        bool    active;
        uint256 registeredAt;
    }

    TenzoIdentity public identity;

    /**
     * @notice Tenzo's sub-treasury for autonomous x402 payments
     * @dev Funded by the community via HoCa tokens.
     *      Used to pay for: Gemini API, satellite imagery, extra compute.
     */
    uint256 public subTreasury;

    // ── Reputation Registry (ERC-8004 Section 4.2) ───────────────────────

    /**
     * @notice Attestation from a Holón about a Tenzo evaluation
     * @dev Holóns rate the Tenzo after each task cycle.
     *      Score range: 1-10 (10 = perfectly fair, 1 = disputed)
     */
    struct Attestation {
        address holon;
        uint256 taskId;
        uint8   score;        // 1-10
        string  feedback;     // brief description
        uint256 timestamp;
    }

    Attestation[] public attestations;

    /// @notice Running reputation score (weighted average × 100 for precision)
    uint256 public reputationScore;

    /// @notice Total evaluations completed
    uint256 public totalEvaluations;

    /// @notice Total HOCA distributed through Tenzo evaluations
    uint256 public totalHocaDistributed;

    // ── Validation Registry (ERC-8004 Section 4.3) ───────────────────────

    /**
     * @notice Proof of completed task evaluation
     * @dev Cryptographic proof that the Tenzo evaluated a specific task
     *      and the community reached consensus on the outcome.
     */
    struct ValidationProof {
        bytes32 taskHash;          // hash of task parameters
        address executor;          // who completed the care task
        uint256 recompensaHoca;    // HOCA amount validated
        string  clasificacion;     // cuidado | regenerativa | comunitaria
        bytes32 genlayerTxHash;    // GenLayer consensus transaction
        uint256 validatedAt;
        bool    disputed;
    }

    mapping(bytes32 => ValidationProof) public validations;
    bytes32[] public validationIndex;

    // ── Events ────────────────────────────────────────────────────────────

    event TenzoRegistered(uint256 agentId, string endpoint);
    event AttestationSubmitted(address indexed holon, uint256 taskId, uint8 score);
    event ValidationRecorded(bytes32 indexed taskHash, address executor, uint256 recompensaHoca);
    event TreasuryFunded(address indexed funder, uint256 amount);
    event TreasuryWithdrawn(uint256 amount, string purpose);
    event ValidationDisputed(bytes32 indexed taskHash, address disputer);

    constructor() {
        _grantRole(DEFAULT_ADMIN_ROLE, msg.sender);
        _grantRole(TENZO_ROLE, msg.sender);
    }

    // ── Identity Registry ─────────────────────────────────────────────────

    /**
     * @notice Registers the Tenzo Agent on-chain (ERC-8004 Identity)
     * @dev Called once on initial deployment. Tenzo is now discoverable
     *      by other agents across the ERC-8004 ecosystem.
     */
    function registerTenzo(
        uint256 agentId,
        string calldata endpoint,
        string calldata agentCardURI,
        bool    x402Support
    ) external onlyRole(DEFAULT_ADMIN_ROLE) {
        identity = TenzoIdentity({
            agentId:      agentId,
            name:         "Tenzo Agent",
            description:  "Autonomous care economy oracle for HoFi Protocol. "
                          "Evaluates care tasks, calculates fair HOCA rewards, "
                          "and coordinates with GenLayer LLM consensus for "
                          "tamper-proof equity validation.",
            endpoint:     endpoint,
            agentCardURI: agentCardURI,
            x402Support:  x402Support,
            active:       true,
            registeredAt: block.timestamp
        });

        emit TenzoRegistered(agentId, endpoint);
    }

    /**
     * @notice Updates the Tenzo's endpoint (e.g., new Cloud Run revision)
     */
    function updateEndpoint(string calldata newEndpoint)
        external onlyRole(TENZO_ROLE)
    {
        identity.endpoint = newEndpoint;
    }

    // ── Reputation Registry ───────────────────────────────────────────────

    /**
     * @notice Submits a reputation attestation from a Holón
     * @dev Only active Holón members (HOLON_ROLE) can submit attestations.
     *      Reputation is calculated as an exponential moving average.
     */
    function submitAttestation(
        uint256 taskId,
        uint8   score,
        string calldata feedback
    ) external onlyRole(HOLON_ROLE) {
        require(score >= 1 && score <= 10, "Score must be 1-10");

        attestations.push(Attestation({
            holon:     msg.sender,
            taskId:    taskId,
            score:     score,
            feedback:  feedback,
            timestamp: block.timestamp
        }));

        // Exponential moving average (α = 0.1 for stability)
        // reputationScore is scaled × 100 (e.g., 850 = 8.50/10)
        if (reputationScore == 0) {
            reputationScore = uint256(score) * 100;
        } else {
            reputationScore = (reputationScore * 90 + uint256(score) * 100 * 10) / 100;
        }

        emit AttestationSubmitted(msg.sender, taskId, score);
    }

    /**
     * @notice Returns the current reputation as a human-readable score
     * @return score Reputation out of 10.00 (e.g., 850 → "8.50")
     */
    function getReputationScore() external view returns (uint256) {
        return reputationScore; // divide by 100 for decimal
    }

    // ── Validation Registry ───────────────────────────────────────────────

    /**
     * @notice Records cryptographic proof of a completed task evaluation
     * @dev Called by the Tenzo Agent after successful GenLayer consensus.
     *      This is the on-chain audit trail of every HOCA distribution.
     */
    function recordValidation(
        bytes32 taskHash,
        address executor,
        uint256 recompensaHoca,
        string calldata clasificacion,
        bytes32 genlayerTxHash
    ) external onlyRole(TENZO_ROLE) {
        require(validations[taskHash].validatedAt == 0, "Already validated");

        validations[taskHash] = ValidationProof({
            taskHash:       taskHash,
            executor:       executor,
            recompensaHoca: recompensaHoca,
            clasificacion:  clasificacion,
            genlayerTxHash: genlayerTxHash,
            validatedAt:    block.timestamp,
            disputed:       false
        });

        validationIndex.push(taskHash);
        totalEvaluations++;
        totalHocaDistributed += recompensaHoca;

        emit ValidationRecorded(taskHash, executor, recompensaHoca);
    }

    /**
     * @notice Disputes a validation (triggers human review)
     * @dev Any Holón member can dispute. Disputed validations are
     *      escalated to the InterHolonTreasury for resolution.
     */
    function disputeValidation(bytes32 taskHash)
        external onlyRole(HOLON_ROLE)
    {
        require(validations[taskHash].validatedAt > 0, "Validation not found");
        require(!validations[taskHash].disputed, "Already disputed");

        validations[taskHash].disputed = true;
        emit ValidationDisputed(taskHash, msg.sender);
    }

    // ── Sub-Treasury (x402 support) ───────────────────────────────────────

    /**
     * @notice Fund the Tenzo's autonomous sub-treasury
     * @dev Community members fund the Tenzo so it can pay for:
     *      - Gemini API calls (via x402)
     *      - Satellite imagery for environmental verification
     *      - Additional compute for complex disputes
     */
    function fundTreasury() external payable {
        subTreasury += msg.value;
        emit TreasuryFunded(msg.sender, msg.value);
    }

    /**
     * @notice Tenzo withdraws from treasury for autonomous operations
     * @dev Only the Tenzo Agent can withdraw. Amount is logged for transparency.
     */
    function withdrawForOperations(
        uint256 amount,
        string calldata purpose
    ) external onlyRole(TENZO_ROLE) {
        require(amount <= subTreasury, "Insufficient treasury");
        subTreasury -= amount;
        payable(msg.sender).transfer(amount);
        emit TreasuryWithdrawn(amount, purpose);
    }

    // ── Views ─────────────────────────────────────────────────────────────

    function getIdentity() external view returns (TenzoIdentity memory) {
        return identity;
    }

    function getAttestationCount() external view returns (uint256) {
        return attestations.length;
    }

    function getValidationCount() external view returns (uint256) {
        return validationIndex.length;
    }

    function getStats() external view returns (
        uint256 _totalEvaluations,
        uint256 _totalHocaDistributed,
        uint256 _reputationScore,
        uint256 _subTreasury
    ) {
        return (totalEvaluations, totalHocaDistributed, reputationScore, subTreasury);
    }
}
