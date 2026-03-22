// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "@openzeppelin/contracts/access/AccessControl.sol";
import "./HoCaToken.sol";
import "./HolonSBT.sol";

/**
 * @title TaskRegistry
 * @author HoFi Protocol
 * @notice On-chain registry for care tasks validated by the Tenzo Agent
 * @dev Acts as the bridge between off-chain AI evaluation (Tenzo Agent on Cloud Run)
 *      and on-chain token emission (HoCaToken minting).
 *
 * Workflow:
 * 1. Community member proposes a care task (off-chain, via HoFi app)
 * 2. Tenzo Agent (AI) evaluates the task and calculates fair HOCA reward
 * 3. Tenzo Agent calls `approveTask` with the validated parameters
 * 4. TaskRegistry verifies Holón membership via HolonSBT
 * 5. HoCaToken is minted and sent to the task executor
 * 6. Executor's reputation is updated in HolonSBT
 *
 * Security:
 * - Only addresses with TENZO_ROLE can approve tasks
 * - TENZO_ROLE should be granted to the Tenzo Agent's wallet or multisig
 * - Membership verification prevents non-members from receiving rewards
 *
 * Future Integration:
 * - GenLayer TenzoEquityOracle ISC for decentralized LLM consensus validation
 * - ERC-8004 autonomous agent capability for self-funded operations
 * - ZK-proof integration for private task verification
 */
contract TaskRegistry is AccessControl {

    /// @notice Role granted to the Tenzo Agent wallet authorized to approve tasks
    bytes32 public constant TENZO_ROLE = keccak256("TENZO_ROLE");

    /// @notice Reference to the HoCaToken contract for minting rewards
    HoCaToken public immutable hocaToken;

    /// @notice Reference to the HolonSBT contract for membership verification
    HolonSBT  public immutable holonSBT;

    /**
     * @notice Represents a validated care task stored on-chain
     * @param executor The community member who completed the task
     * @param holonId The Holón the task belongs to
     * @param categoria Task category (e.g., "cuidado_ninos", "cocina_comunal")
     * @param duracionHoras Duration of the task in hours
     * @param recompensaHoca HOCA reward amount in wei (18 decimals)
     * @param razonamiento AI-generated justification for the reward amount
     * @param createdAt Block timestamp when the task was registered
     */
    struct Task {
        address executor;
        string  holonId;
        string  categoria;
        uint256 duracionHoras;
        uint256 recompensaHoca;
        string  razonamiento;
        uint256 createdAt;
    }

    /// @dev Maps task ID to Task data
    mapping(bytes32 => Task) public tasks;

    /// @dev Maps executor address to their task IDs
    mapping(address => bytes32[]) public tasksByExecutor;

    /// @dev Maps Holón ID to task IDs within that Holón
    mapping(string  => bytes32[]) public tasksByHolon;

    /// @notice Total number of tasks approved across all Holóns
    uint256 public totalTasks;

    /// @notice Total HOCA minted across all approved tasks
    uint256 public totalHocaMinted;

    /**
     * @notice Emitted when a care task is approved and rewarded
     * @param taskId The unique on-chain identifier of the task
     * @param executor The community member rewarded
     * @param recompensaHoca The HOCA amount minted as reward
     */
    event TaskApproved(
        bytes32 indexed taskId,
        address indexed executor,
        uint256 recompensaHoca
    );

    /**
     * @notice Deploys the TaskRegistry linked to HoCaToken and HolonSBT
     * @dev Deployer must subsequently grant MINTER_ROLE on HoCaToken to this contract
     * @param _hocaToken Address of the deployed HoCaToken contract
     * @param _holonSBT Address of the deployed HolonSBT contract
     */
    constructor(address _hocaToken, address _holonSBT) {
        hocaToken = HoCaToken(_hocaToken);
        holonSBT  = HolonSBT(_holonSBT);
        _grantRole(DEFAULT_ADMIN_ROLE, msg.sender);
        _grantRole(TENZO_ROLE, msg.sender);
    }

    /**
     * @notice Approves a care task and mints HOCA reward to the executor
     * @dev Only callable by addresses with TENZO_ROLE (the Tenzo Agent wallet).
     *      Verifies Holón membership before minting.
     *      Updates executor reputation in HolonSBT after successful mint.
     * @param executor The community member who completed the care task
     * @param holonId The Holón the task was performed for
     * @param categoria Task category matching HoFi's taxonomy
     * @param duracionHoras Duration of the task in hours
     * @param recompensaHoca HOCA reward in wei (18 decimals), calculated by Tenzo Agent
     * @param razonamiento Tenzo Agent's justification for the reward amount
     * @return taskId The unique bytes32 identifier of the registered task
     */
    function approveTask(
        address executor,
        string calldata holonId,
        string calldata categoria,
        uint256 duracionHoras,
        uint256 recompensaHoca,
        string calldata razonamiento
    ) external onlyRole(TENZO_ROLE) returns (bytes32) {
        require(executor != address(0), "TaskRegistry: invalid executor address");
        require(recompensaHoca > 0, "TaskRegistry: reward must be greater than zero");
        require(
            holonSBT.isMember(executor, holonId),
            "TaskRegistry: executor is not a member of the Holon"
        );

        bytes32 taskId = keccak256(
            abi.encodePacked(executor, block.timestamp, totalTasks)
        );

        tasks[taskId] = Task({
            executor:       executor,
            holonId:        holonId,
            categoria:      categoria,
            duracionHoras:  duracionHoras,
            recompensaHoca: recompensaHoca,
            razonamiento:   razonamiento,
            createdAt:      block.timestamp
        });

        tasksByExecutor[executor].push(taskId);
        tasksByHolon[holonId].push(taskId);
        totalTasks++;
        totalHocaMinted += recompensaHoca;

        // Mint HOCA reward to executor
        hocaToken.mintReward(executor, address(this), recompensaHoca, taskId);

        // Update executor reputation (total tasks completed = reputation score)
        holonSBT.updateReputation(executor, tasksByExecutor[executor].length);

        emit TaskApproved(taskId, executor, recompensaHoca);
        return taskId;
    }

    /**
     * @notice Returns all task IDs associated with a specific executor
     * @param executor The address to query
     * @return Array of task IDs in chronological order
     */
    function getTasksByExecutor(address executor)
        external view returns (bytes32[] memory)
    {
        return tasksByExecutor[executor];
    }

    /**
     * @notice Returns all task IDs associated with a specific Holón
     * @param holonId The Holón to query
     * @return Array of task IDs in chronological order
     */
    function getTasksByHolon(string calldata holonId)
        external view returns (bytes32[] memory)
    {
        return tasksByHolon[holonId];
    }

    /**
     * @notice Returns global protocol statistics
     * @return _totalTasks Total number of approved care tasks
     * @return _totalHocaMinted Total HOCA minted across all tasks (in wei)
     */
    function getStats() external view returns (
        uint256 _totalTasks,
        uint256 _totalHocaMinted
    ) {
        return (totalTasks, totalHocaMinted);
    }
}
