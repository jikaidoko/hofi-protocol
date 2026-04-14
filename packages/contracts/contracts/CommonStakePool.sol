// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "@openzeppelin/contracts/token/ERC20/IERC20.sol";
import "@openzeppelin/contracts/token/ERC20/utils/SafeERC20.sol";
import "@openzeppelin/contracts/access/AccessControl.sol";
import "@openzeppelin/contracts/utils/ReentrancyGuard.sol";

/**
 * @title CommonStakePool
 * @notice Pool Comun Inter-Holonico — mutual financiera de la red HoFi.
 *
 * Agrega liquidez de multiples holones. Cada holon aporta via:
 *   1. Fees automaticas desde sus MMA Pools (0.1% por swap)
 *   2. Stake voluntario (gobernanza local decide cuanto)
 *   3. Rendimientos de inversiones ReFi
 *
 * Servicios:
 *   - Credito mutual basado en reputacion SBT
 *   - Flash loans mutualistas (0.05% fee)
 *   - Ejecucion de inversiones ReFi aprobadas por el ISC GenLayer
 */
contract CommonStakePool is AccessControl, ReentrancyGuard {
    using SafeERC20 for IERC20;

    bytes32 public constant GOVERNANCE_ROLE = keccak256("GOVERNANCE_ROLE");
    bytes32 public constant MMA_POOL_ROLE   = keccak256("MMA_POOL_ROLE");
    bytes32 public constant REFI_EXECUTOR_ROLE = keccak256("REFI_EXECUTOR_ROLE");

    IERC20 public immutable stablecoin;

    struct HolonStake {
        uint256 staked;
        uint256 fees;
        uint256 creditUsed;
        uint256 creditLimit;
        uint256 lastStakeTime;
        bool active;
    }

    struct ReFiInvestment {
        string proposalId;
        address targetProtocol;
        uint256 amount;
        uint256 expectedYield;
        uint256 investedAt;
        uint256 maturity;
        string impactCategory;
        bool active;
    }

    mapping(string => HolonStake) public holonStakes;
    string[] public activeHolons;

    ReFiInvestment[] public investments;
    uint256 public totalStaked;
    uint256 public totalFees;
    uint256 public totalInvested;
    uint256 public totalYieldEarned;

    uint256 public cooldownPeriod      = 7 days;
    uint256 public maxCreditMultiplier = 20000;  // 2x del stake
    uint256 public maxInvestmentRatio  = 6000;   // 60% max invertido
    uint256 public flashLoanFeeBps     = 5;      // 0.05%

    event StakeDeposited(string indexed holonId, uint256 amount);
    event FeesDeposited(string indexed holonId, uint256 amount);
    event StakeWithdrawn(string indexed holonId, uint256 amount);
    event CreditIssued(string indexed holonId, uint256 amount);
    event CreditRepaid(string indexed holonId, uint256 amount);
    event ReFiInvestmentMade(uint256 indexed id, string proposalId, address target, uint256 amount);
    event ReFiYieldCollected(uint256 indexed id, uint256 yield_);
    event FlashLoanExecuted(address indexed borrower, uint256 amount, uint256 fee);

    constructor(address _stablecoin, address _uniswapRouter) {
        stablecoin = IERC20(_stablecoin);
        _grantRole(DEFAULT_ADMIN_ROLE, msg.sender);
        _grantRole(GOVERNANCE_ROLE, msg.sender);
    }

    // ══ ENTRADAS ════════════════════════════════════════════════════════

    function depositFees(string calldata holonId, uint256 amount) external onlyRole(MMA_POOL_ROLE) {
        stablecoin.safeTransferFrom(msg.sender, address(this), amount);
        holonStakes[holonId].fees += amount;
        totalFees += amount;
        _ensureActive(holonId);
        emit FeesDeposited(holonId, amount);
    }

    function depositStake(string calldata holonId, uint256 amount) external onlyRole(MMA_POOL_ROLE) {
        stablecoin.safeTransferFrom(msg.sender, address(this), amount);
        holonStakes[holonId].staked += amount;
        holonStakes[holonId].lastStakeTime = block.timestamp;
        totalStaked += amount;
        _ensureActive(holonId);
        _recalculateCreditLimit(holonId);
        emit StakeDeposited(holonId, amount);
    }

    function withdrawStake(string calldata holonId, uint256 amount, address recipient)
        external onlyRole(GOVERNANCE_ROLE) nonReentrant
    {
        HolonStake storage hs = holonStakes[holonId];
        require(hs.staked >= amount, "Insufficient stake");
        require(block.timestamp >= hs.lastStakeTime + cooldownPeriod, "Cooldown active");
        require(hs.creditUsed == 0, "Must repay credit first");
        hs.staked -= amount;
        totalStaked -= amount;
        _recalculateCreditLimit(holonId);
        stablecoin.safeTransfer(recipient, amount);
        emit StakeWithdrawn(holonId, amount);
    }

    // ══ CREDITO MUTUAL ═══════════════════════════════════════════════════

    function issueMutualCredit(string calldata holonId, uint256 amount, address recipient)
        external onlyRole(GOVERNANCE_ROLE) nonReentrant
    {
        HolonStake storage hs = holonStakes[holonId];
        require(hs.active, "Holon not active");
        require(hs.creditUsed + amount <= hs.creditLimit, "Exceeds credit limit");
        require(amount <= _availableLiquidity(), "Pool liquidity insufficient");
        hs.creditUsed += amount;
        stablecoin.safeTransfer(recipient, amount);
        emit CreditIssued(holonId, amount);
    }

    function repayCredit(string calldata holonId, uint256 amount) external nonReentrant {
        require(holonStakes[holonId].creditUsed >= amount, "Overpayment");
        stablecoin.safeTransferFrom(msg.sender, address(this), amount);
        holonStakes[holonId].creditUsed -= amount;
        emit CreditRepaid(holonId, amount);
    }

    // ══ INVERSIONES ReFi ════════════════════════════════════════════════

    function executeReFiInvestment(
        string calldata proposalId,
        address targetProtocol,
        uint256 amount,
        uint256 expectedYield,
        uint256 maturity,
        string calldata impactCategory
    ) external onlyRole(REFI_EXECUTOR_ROLE) nonReentrant {
        require(amount <= _availableLiquidity(), "Insufficient liquidity");
        require(totalInvested + amount <= (totalStaked * maxInvestmentRatio) / 10000, "Exceeds max investment ratio");

        investments.push(ReFiInvestment({
            proposalId: proposalId, targetProtocol: targetProtocol, amount: amount,
            expectedYield: expectedYield, investedAt: block.timestamp,
            maturity: maturity, impactCategory: impactCategory, active: true
        }));
        totalInvested += amount;
        stablecoin.safeTransfer(targetProtocol, amount);
        emit ReFiInvestmentMade(investments.length - 1, proposalId, targetProtocol, amount);
    }

    function collectReFiYield(uint256 investmentId, uint256 yieldAmount) external nonReentrant {
        require(investments[investmentId].active, "Investment not active");
        stablecoin.safeTransferFrom(msg.sender, address(this), yieldAmount);
        totalYieldEarned += yieldAmount;
        emit ReFiYieldCollected(investmentId, yieldAmount);
    }

    function liquidateInvestment(uint256 investmentId) external onlyRole(REFI_EXECUTOR_ROLE) {
        require(investments[investmentId].active, "Not active");
        investments[investmentId].active = false;
        totalInvested -= investments[investmentId].amount;
    }

    // ══ FLASH LOAN MUTUALISTA ════════════════════════════════════════════

    function flashLoan(uint256 amount, bytes calldata data) external nonReentrant {
        uint256 balanceBefore = stablecoin.balanceOf(address(this));
        require(balanceBefore >= amount, "Insufficient liquidity");
        uint256 fee = (amount * flashLoanFeeBps) / 10000;
        stablecoin.safeTransfer(msg.sender, amount);
        (bool success,) = msg.sender.call(data);
        require(success, "Flash loan callback failed");
        require(stablecoin.balanceOf(address(this)) >= balanceBefore + fee, "Repayment insufficient");
        totalFees += fee;
        emit FlashLoanExecuted(msg.sender, amount, fee);
    }

    // ══ VISTAS ══════════════════════════════════════════════════════════

    function getAvailableLiquidity() external view returns (uint256) { return _availableLiquidity(); }
    function getTotalTVL() external view returns (uint256) { return stablecoin.balanceOf(address(this)) + totalInvested; }
    function getHolonCount() external view returns (uint256) { return activeHolons.length; }

    function getHolonStakeInfo(string calldata holonId)
        external view returns (uint256 staked, uint256 fees, uint256 creditUsed, uint256 creditLimit, bool active)
    {
        HolonStake storage hs = holonStakes[holonId];
        return (hs.staked, hs.fees, hs.creditUsed, hs.creditLimit, hs.active);
    }

    // ══ GOBERNANZA ═══════════════════════════════════════════════════════

    function registerMMAPool(address pool) external onlyRole(GOVERNANCE_ROLE) { _grantRole(MMA_POOL_ROLE, pool); }
    function registerReFiExecutor(address executor) external onlyRole(GOVERNANCE_ROLE) { _grantRole(REFI_EXECUTOR_ROLE, executor); }
    function setCooldownPeriod(uint256 _p) external onlyRole(GOVERNANCE_ROLE) { cooldownPeriod = _p; }
    function setMaxCreditMultiplier(uint256 _m) external onlyRole(GOVERNANCE_ROLE) { maxCreditMultiplier = _m; }
    function setMaxInvestmentRatio(uint256 _r) external onlyRole(GOVERNANCE_ROLE) { require(_r <= 8000, "Max 80%"); maxInvestmentRatio = _r; }

    // ══ INTERNALS ════════════════════════════════════════════════════════

    function _availableLiquidity() internal view returns (uint256) {
        uint256 balance = stablecoin.balanceOf(address(this));
        uint256 outstanding;
        for (uint256 i = 0; i < activeHolons.length; i++)
            outstanding += holonStakes[activeHolons[i]].creditUsed;
        return balance > outstanding ? balance - outstanding : 0;
    }

    function _recalculateCreditLimit(string memory holonId) internal {
        holonStakes[holonId].creditLimit = (holonStakes[holonId].staked * maxCreditMultiplier) / 10000;
    }

    function _ensureActive(string calldata holonId) internal {
        if (!holonStakes[holonId].active) {
            holonStakes[holonId].active = true;
            activeHolons.push(holonId);
        }
    }
}
