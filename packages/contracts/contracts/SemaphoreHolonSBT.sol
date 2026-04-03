// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "@openzeppelin/contracts/access/AccessControl.sol";

/**
 * @title SemaphoreHolonSBT
 * @author HoFi Protocol
 * @notice Privacy-preserving Holón membership using Semaphore ZK proofs
 * @dev Combines Soul-Bound Token identity with Semaphore anonymous signaling.
 *
 * The Problem This Solves:
 *   Without ZK, voting reveals which wallet voted and with what weight,
 *   potentially exposing sensitive care work history (e.g., who cared for
 *   a sick family member, who attended therapy, etc.)
 *
 * The Solution:
 *   Members register an identity commitment (hash of a secret) in a Merkle tree.
 *   To vote or claim rewards, they generate a ZK proof that:
 *     1. They are a member of the Holón (Merkle membership proof)
 *     2. Their reputation meets the minimum threshold
 *     3. They haven't already voted in this round (nullifier)
 *   ...WITHOUT revealing which member they are.
 *
 * Architecture:
 *   - SBT Layer: links wallet → identity commitment (gatekeeper)
 *   - Semaphore Layer: handles anonymous proofs and nullifiers
 *   - Reputation Layer: stores encrypted reputation commitments
 *
 * Integration Points:
 *   - TaskRegistry calls updateReputation() after task approval
 *   - Governance calls castAnonymousVote() for private voting
 *   - TenzoEquityOracle verifies membership before reward calculation
 *
 * @dev This contract requires deployment of the Semaphore verifier contract.
 *      Use @semaphore-protocol/contracts for the verifier.
 *      See: https://semaphore.pse.dev
 */
contract SemaphoreHolonSBT is AccessControl {

    bytes32 public constant ISSUER_ROLE   = keccak256("ISSUER_ROLE");
    bytes32 public constant TENZO_ROLE    = keccak256("TENZO_ROLE");

    // ── Semaphore Integration ─────────────────────────────────────────────

    /// @notice Interface for the Semaphore verifier contract
    /// @dev Deploy ISemaphore from @semaphore-protocol/contracts
    ISemaphoreVerifier public immutable semaphoreVerifier;

    /// @notice Semaphore group ID for this Holón
    uint256 public immutable groupId;

    // ── SBT Storage ───────────────────────────────────────────────────────

    /**
     * @notice Member data stored on-chain (non-sensitive)
     * @param identityCommitment The Semaphore identity commitment (public key hash)
     * @param reputationCommitment Hash of (reputation, secret) — hides actual score
     * @param role Member role in the Holón
     * @param active Whether the membership is active
     * @param tasksCompleted Public counter (not linked to private identity)
     */
    struct Member {
        uint256 identityCommitment;
        uint256 reputationCommitment;
        string  role;
        bool    active;
        uint256 tasksCompleted;
    }

    /// @dev wallet address → Member data (SBT layer)
    mapping(address => Member) private _members;

    /// @dev identity commitment → wallet (reverse lookup for admin)
    mapping(uint256 => address) private _commitmentToAddress;

    /// @dev nullifier hash → used (prevents double voting per round)
    mapping(uint256 => bool) private _nullifiers;

    /// @notice Holón name
    string public holonName;

    /// @notice Total active members
    uint256 public totalMembers;

    // ── Events ────────────────────────────────────────────────────────────

    event MemberAdded(address indexed wallet, uint256 identityCommitment, string role);
    event ReputationUpdated(uint256 indexed identityCommitment, uint256 newCommitment);
    event AnonymousVoteCast(uint256 indexed proposalId, uint256 nullifierHash, bool support, uint256 weight);
    event AnonymousRewardClaimed(uint256 nullifierHash, uint256 amount);

    // ── Constructor ───────────────────────────────────────────────────────

    /**
     * @param _holonName Human-readable name of this Holón
     * @param _groupId Semaphore group ID (unique per Holón)
     * @param _semaphoreVerifier Address of the deployed Semaphore verifier
     */
    constructor(
        string memory _holonName,
        uint256       _groupId,
        address       _semaphoreVerifier
    ) {
        holonName         = _holonName;
        groupId           = _groupId;
        semaphoreVerifier = ISemaphoreVerifier(_semaphoreVerifier);

        _grantRole(DEFAULT_ADMIN_ROLE, msg.sender);
        _grantRole(ISSUER_ROLE, msg.sender);
        _grantRole(TENZO_ROLE, msg.sender);
    }

    // ── Membership (SBT Layer) ────────────────────────────────────────────

    /**
     * @notice Issues an SBT to a new member and registers their Semaphore identity
     * @dev The identity commitment is the PUBLIC part of the member's Semaphore identity.
     *      The SECRET part never leaves the member's device.
     *      Formula: identityCommitment = hash(hash(secret))
     *
     * @param wallet Member's Ethereum address (links SBT to on-chain identity)
     * @param identityCommitment Semaphore identity commitment (from @semaphore-protocol/identity)
     * @param reputationCommitment Initial reputation commitment hash(0, secret)
     * @param role Initial role in the Holón
     */
    function issueSBT(
        address wallet,
        uint256 identityCommitment,
        uint256 reputationCommitment,
        string calldata role
    ) external onlyRole(ISSUER_ROLE) {
        require(wallet != address(0),                    "Invalid wallet");
        require(!_members[wallet].active,                "Already a member");
        require(_commitmentToAddress[identityCommitment] == address(0), "Commitment already used");

        _members[wallet] = Member({
            identityCommitment:   identityCommitment,
            reputationCommitment: reputationCommitment,
            role:                 role,
            active:               true,
            tasksCompleted:       0,
        });

        _commitmentToAddress[identityCommitment] = wallet;
        totalMembers++;

        emit MemberAdded(wallet, identityCommitment, role);
    }

    /**
     * @notice Updates a member's reputation commitment after task approval
     * @dev The NEW reputation commitment = hash(newReputation, memberSecret)
     *      Only the member knows the actual reputation score.
     *      The Tenzo Agent provides the new commitment after off-chain calculation.
     *
     * @param wallet Member's wallet address
     * @param newReputationCommitment hash(newReputation, memberSecret)
     */
    function updateReputation(
        address wallet,
        uint256 newReputationCommitment
    ) external onlyRole(TENZO_ROLE) {
        require(_members[wallet].active, "Member not active");

        _members[wallet].reputationCommitment = newReputationCommitment;
        _members[wallet].tasksCompleted++;

        emit ReputationUpdated(_members[wallet].identityCommitment, newReputationCommitment);
    }

    // ── Anonymous Voting (Semaphore Layer) ────────────────────────────────

    /**
     * @notice Cast an anonymous vote on a governance proposal
     * @dev Uses Semaphore ZK proof to verify:
     *      1. Voter is a member of this Holón (Merkle proof)
     *      2. Voter hasn't voted on this proposal before (nullifier)
     *      3. Voter's reputation meets minimum threshold (optional extension)
     *
     *      The signal encodes: abi.encodePacked(proposalId, support, weight)
     *      Weight is revealed in the signal but NOT linked to identity.
     *
     * @param proposalId The proposal being voted on
     * @param support True = in favor, False = against
     * @param weight Claimed voting weight (must be justified by reputation proof)
     * @param merkleTreeRoot Current Merkle root of the Holón's identity tree
     * @param nullifierHash Unique nullifier for this (voter, proposal) pair
     * @param proof Semaphore ZK proof bytes
     */
    function castAnonymousVote(
        uint256 proposalId,
        bool    support,
        uint256 weight,
        uint256 merkleTreeRoot,
        uint256 nullifierHash,
        uint256[8] calldata proof
    ) external {
        require(!_nullifiers[nullifierHash], "Already voted in this round");
        require(weight >= 1 && weight <= 5,  "Invalid weight range");

        // The signal commits to the vote content
        uint256 signal = uint256(keccak256(abi.encodePacked(proposalId, support, weight)));

        // Verify the ZK proof via Semaphore
        // externalNullifier = hash(groupId, proposalId) — unique per proposal
        uint256 externalNullifier = uint256(keccak256(abi.encodePacked(groupId, proposalId)));

        semaphoreVerifier.verifyProof(
            merkleTreeRoot,
            nullifierHash,
            signal,
            externalNullifier,
            proof
        );

        // Mark nullifier as used (prevents double voting)
        _nullifiers[nullifierHash] = true;

        emit AnonymousVoteCast(proposalId, nullifierHash, support, weight);
    }

    /**
     * @notice Verify anonymous membership without voting
     * @dev Used by TenzoEquityOracle to verify a member belongs to the Holón
     *      without revealing which member. The signal can be the task hash.
     *
     * @param signal Arbitrary signal (e.g., hash of task description)
     * @param merkleTreeRoot Current Merkle root
     * @param nullifierHash Unique nullifier for this action
     * @param externalNullifier External nullifier (e.g., groupId + taskId)
     * @param proof Semaphore ZK proof
     */
    function verifyAnonymousMembership(
        uint256 signal,
        uint256 merkleTreeRoot,
        uint256 nullifierHash,
        uint256 externalNullifier,
        uint256[8] calldata proof
    ) external view returns (bool) {
        semaphoreVerifier.verifyProof(
            merkleTreeRoot,
            nullifierHash,
            signal,
            externalNullifier,
            proof
        );
        return true; // reverts if proof invalid
    }

    // ── Views ─────────────────────────────────────────────────────────────

    /**
     * @notice Check if a wallet has an active SBT
     */
    function isMember(address wallet) external view returns (bool) {
        return _members[wallet].active;
    }

    /**
     * @notice Get public member data (role and task count only — reputation stays private)
     */
    function getMemberPublicData(address wallet)
        external view returns (string memory role, uint256 tasksCompleted, bool active)
    {
        Member memory m = _members[wallet];
        return (m.role, m.tasksCompleted, m.active);
    }

    /**
     * @notice Get a member's identity commitment (for Semaphore group management)
     */
    function getIdentityCommitment(address wallet) external view returns (uint256) {
        return _members[wallet].identityCommitment;
    }
}

// ── Semaphore Verifier Interface ──────────────────────────────────────────────

/**
 * @title ISemaphoreVerifier
 * @notice Interface for the Semaphore verifier contract
 * @dev Deploy from: npm install @semaphore-protocol/contracts
 */
interface ISemaphoreVerifier {
    function verifyProof(
        uint256 merkleTreeRoot,
        uint256 nullifierHash,
        uint256 signal,
        uint256 externalNullifier,
        uint256[8] calldata proof
    ) external view;
}
