// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "@openzeppelin/contracts/access/AccessControl.sol";

/**
 * @title HolonSBT
 * @author HoFi Protocol
 * @notice Soul-Bound Token (SBT) representing membership and reputation within a Holón
 * @dev Non-transferable identity token implemented as a mapping-based registry.
 *      Each address can hold exactly one active SBT per deployment.
 *      Reputation is updated by TaskRegistry as care tasks are completed.
 *
 * Soul-Bound Properties:
 * - Non-transferable: membership is personal, not tradeable
 * - Non-burnable by holder: only governance can deactivate
 * - Reputation-bearing: tracks community contributions over time
 *
 * Integration:
 * - Used by TaskRegistry to verify Holón membership before rewarding
 * - Designed for GenLayer LLM consensus governance (HolonSBT ISC)
 * - Future: ZK-proof compatible for private reputation verification
 */
contract HolonSBT is AccessControl {

    /// @notice Role granted to contracts authorized to issue SBTs and update reputation
    bytes32 public constant ISSUER_ROLE = keccak256("ISSUER_ROLE");

    /**
     * @notice Represents a member's soul-bound identity within a Holón
     * @param holonId The unique string identifier of the Holón
     * @param role The member's role: "member" | "coordinator" | "tenzo" | "ambassador" | "guardian"
     * @param issuedAt Block timestamp when the SBT was issued
     * @param active Whether the SBT is currently active (can be deactivated by governance)
     * @param reputation Accumulated reputation score from completed care tasks
     */
    struct SBT {
        string  holonId;
        string  role;
        uint256 issuedAt;
        bool    active;
        uint256 reputation;
    }

    /// @dev Maps each address to their SBT data
    mapping(address => SBT) private _sbts;

    /// @dev Maps each Holón ID to the list of its members
    mapping(string => address[]) private _holonMembers;

    /// @notice Total number of SBTs ever issued
    uint256 public totalIssued;

    /**
     * @notice Emitted when a new SBT is issued to a community member
     * @param to The address receiving the SBT
     * @param holonId The Holón the member is joining
     * @param role The role assigned to the member
     */
    event SBTIssued(address indexed to, string holonId, string role);

    /**
     * @notice Emitted when a member's SBT is deactivated by governance
     * @param holder The address whose SBT was deactivated
     * @param reason Human-readable reason for deactivation
     */
    event SBTDeactivated(address indexed holder, string reason);

    /**
     * @notice Emitted when a member's reputation is updated
     * @param holder The address whose reputation changed
     * @param newReputation The new reputation score
     */
    event ReputationUpdated(address indexed holder, uint256 newReputation);

    /**
     * @notice Deploys the HolonSBT registry
     * @dev Grants admin and issuer roles to the deployer
     */
    constructor() {
        _grantRole(DEFAULT_ADMIN_ROLE, msg.sender);
        _grantRole(ISSUER_ROLE, msg.sender);
    }

    /**
     * @notice Issues a Soul-Bound Token to a new Holón member
     * @dev Each address can only hold one active SBT. Reverts if already a member.
     * @param to The address receiving membership
     * @param holonId The unique identifier of the Holón
     * @param role The member's initial role within the Holón
     */
    function issue(
        address to,
        string calldata holonId,
        string calldata role
    ) external onlyRole(ISSUER_ROLE) {
        require(to != address(0), "HolonSBT: invalid address");
        require(!_sbts[to].active, "HolonSBT: address already has an active SBT");
        require(bytes(holonId).length > 0, "HolonSBT: holonId cannot be empty");

        _sbts[to] = SBT({
            holonId:    holonId,
            role:       role,
            issuedAt:   block.timestamp,
            active:     true,
            reputation: 0
        });

        _holonMembers[holonId].push(to);
        totalIssued++;

        emit SBTIssued(to, holonId, role);
    }

    /**
     * @notice Checks if an address is an active member of a specific Holón
     * @param holder The address to check
     * @param holonId The Holón to verify membership in
     * @return True if the address holds an active SBT for the given Holón
     */
    function isMember(address holder, string calldata holonId)
        external view returns (bool)
    {
        SBT memory sbt = _sbts[holder];
        return sbt.active &&
               keccak256(bytes(sbt.holonId)) == keccak256(bytes(holonId));
    }

    /**
     * @notice Returns the full SBT data for a given address
     * @param holder The address to query
     * @return The SBT struct containing membership details and reputation
     */
    function getSBT(address holder) external view returns (SBT memory) {
        return _sbts[holder];
    }

    /**
     * @notice Updates the reputation score of a Holón member
     * @dev Called by TaskRegistry after each approved care task
     * @param holder The member whose reputation is being updated
     * @param newReputation The new reputation score (typically total tasks completed)
     */
    function updateReputation(address holder, uint256 newReputation)
        external onlyRole(ISSUER_ROLE)
    {
        require(_sbts[holder].active, "HolonSBT: SBT is not active");
        _sbts[holder].reputation = newReputation;
        emit ReputationUpdated(holder, newReputation);
    }

    /**
     * @notice Deactivates a member's SBT (governance action only)
     * @dev Soul-bound tokens cannot be burned by the holder.
     *      Only governance (DEFAULT_ADMIN_ROLE) can deactivate.
     * @param holder The address to deactivate
     * @param reason Human-readable justification for deactivation
     */
    function deactivate(address holder, string calldata reason)
        external onlyRole(DEFAULT_ADMIN_ROLE)
    {
        require(_sbts[holder].active, "HolonSBT: SBT is already inactive");
        _sbts[holder].active = false;
        emit SBTDeactivated(holder, reason);
    }

    /**
     * @notice Returns all member addresses of a specific Holón
     * @param holonId The Holón to query
     * @return Array of member addresses
     */
    function getHolonMembers(string calldata holonId)
        external view returns (address[] memory)
    {
        return _holonMembers[holonId];
    }
}
