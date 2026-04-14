// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "@openzeppelin/contracts/token/ERC20/IERC20.sol";
import "@openzeppelin/contracts/token/ERC20/utils/SafeERC20.sol";
import "@openzeppelin/contracts/access/AccessControl.sol";
import "@openzeppelin/contracts/utils/ReentrancyGuard.sol";

interface IUniswapV3Router {
    struct ExactInputSingleParams {
        address tokenIn; address tokenOut; uint24 fee; address recipient;
        uint256 deadline; uint256 amountIn; uint256 amountOutMinimum; uint160 sqrtPriceLimitX96;
    }
    function exactInputSingle(ExactInputSingleParams calldata params) external payable returns (uint256 amountOut);
}

interface ICommonStakePool {
    function depositFees(string calldata holonId, uint256 amount) external;
    function depositStake(string calldata holonId, uint256 amount) external;
}

/**
 * @title HoFiMMAPool
 * @notice Pool MMA local de cada holon (x*y=k) con bridge a Uniswap V3
 *         y conexion al CommonStakePool inter-holonico.
 *
 * ARQUITECTURA:
 *   Capa 1 — AMM local x*y=k: swap HolonToken/USDC sin intermediarios
 *   Capa 2 — Bridge Uniswap V3: para swaps grandes o pares externos
 *   Capa 3 — CommonStakePool: 0.1% de fees + stake voluntario
 *
 * FEES (total 0.3%):
 *   feeLocalBps  = 20 bps (0.2%) — queda en el pool, aumenta K
 *   feeCommonBps = 10 bps (0.1%) — va al CommonStakePool
 */
contract HoFiMMAPool is AccessControl, ReentrancyGuard {
    using SafeERC20 for IERC20;

    bytes32 public constant GOVERNANCE_ROLE = keccak256("GOVERNANCE_ROLE");

    IERC20 public immutable holonToken;
    IERC20 public immutable stablecoin;
    string public holonId;

    uint256 public reserveHolon;
    uint256 public reserveStable;

    uint256 public feeLocalBps = 20;
    uint256 public feeCommonBps = 10;
    uint256 public accumulatedCommonFees;

    IUniswapV3Router public uniswapRouter;
    ICommonStakePool public commonStakePool;
    uint24 public uniswapPoolFee;

    uint256 public uniswapThreshold = 10_000 * 1e6; // 10,000 USDC
    uint256 public maxStakeRatio = 3000;             // 30% max al pool comun

    mapping(address => uint256) public lpShares;
    uint256 public totalLPShares;

    event LiquidityAdded(address indexed provider, uint256 holonAmount, uint256 stableAmount, uint256 shares);
    event LiquidityRemoved(address indexed provider, uint256 holonAmount, uint256 stableAmount, uint256 shares);
    event SwapLocal(address indexed trader, bool holonToStable, uint256 amountIn, uint256 amountOut);
    event SwapBridged(address indexed trader, address tokenIn, address tokenOut, uint256 amountIn, uint256 amountOut);
    event FeesForwarded(uint256 amount);
    event StakeDeposited(uint256 amount);

    constructor(
        address _holonToken, address _stablecoin, string memory _holonId,
        address _governance, address _uniswapRouter, address _commonStakePool, uint24 _uniswapPoolFee
    ) {
        holonToken = IERC20(_holonToken);
        stablecoin = IERC20(_stablecoin);
        holonId = _holonId;
        uniswapRouter = IUniswapV3Router(_uniswapRouter);
        commonStakePool = ICommonStakePool(_commonStakePool);
        uniswapPoolFee = _uniswapPoolFee;
        _grantRole(DEFAULT_ADMIN_ROLE, _governance);
        _grantRole(GOVERNANCE_ROLE, _governance);
    }

    // ══ CAPA 1: AMM LOCAL ════════════════════════════════════════════════

    function addLiquidity(uint256 holonAmount, uint256 stableAmount, uint256 holonMin, uint256 stableMin)
        external nonReentrant returns (uint256 shares)
    {
        if (totalLPShares == 0) {
            shares = _sqrt(holonAmount * stableAmount);
            require(shares > 0, "Insufficient initial liquidity");
        } else {
            uint256 stableOptimal = (holonAmount * reserveStable) / reserveHolon;
            if (stableOptimal <= stableAmount) {
                require(stableOptimal >= stableMin, "Slippage: stable");
                stableAmount = stableOptimal;
            } else {
                uint256 holonOptimal = (stableAmount * reserveHolon) / reserveStable;
                require(holonOptimal >= holonMin, "Slippage: holon");
                holonAmount = holonOptimal;
            }
            shares = _min((holonAmount * totalLPShares) / reserveHolon, (stableAmount * totalLPShares) / reserveStable);
        }
        require(shares > 0, "Zero shares");
        holonToken.safeTransferFrom(msg.sender, address(this), holonAmount);
        stablecoin.safeTransferFrom(msg.sender, address(this), stableAmount);
        reserveHolon += holonAmount;
        reserveStable += stableAmount;
        lpShares[msg.sender] += shares;
        totalLPShares += shares;
        emit LiquidityAdded(msg.sender, holonAmount, stableAmount, shares);
    }

    function removeLiquidity(uint256 shares, uint256 holonMin, uint256 stableMin)
        external nonReentrant returns (uint256 holonAmount, uint256 stableAmount)
    {
        require(lpShares[msg.sender] >= shares, "Insufficient shares");
        holonAmount = (shares * reserveHolon) / totalLPShares;
        stableAmount = (shares * reserveStable) / totalLPShares;
        require(holonAmount >= holonMin && stableAmount >= stableMin, "Slippage");
        lpShares[msg.sender] -= shares;
        totalLPShares -= shares;
        reserveHolon -= holonAmount;
        reserveStable -= stableAmount;
        holonToken.safeTransfer(msg.sender, holonAmount);
        stablecoin.safeTransfer(msg.sender, stableAmount);
        emit LiquidityRemoved(msg.sender, holonAmount, stableAmount, shares);
    }

    function swapHolonToStable(uint256 amountIn, uint256 amountOutMin, address to)
        external nonReentrant returns (uint256 amountOut)
    {
        require(amountIn > 0, "Zero input");
        if (amountIn > uniswapThreshold)
            return _bridgeSwap(address(holonToken), address(stablecoin), amountIn, amountOutMin, to);

        amountOut = _getAmountOut(amountIn, reserveHolon, reserveStable);
        require(amountOut >= amountOutMin, "Slippage exceeded");

        uint256 feeLocal = (amountOut * feeLocalBps) / 10000;
        uint256 feeCommon = (amountOut * feeCommonBps) / 10000;
        uint256 netOut = amountOut - feeLocal - feeCommon;

        holonToken.safeTransferFrom(msg.sender, address(this), amountIn);
        reserveHolon += amountIn;
        reserveStable -= amountOut;
        reserveStable += feeLocal;       // fee local aumenta K
        accumulatedCommonFees += feeCommon;

        stablecoin.safeTransfer(to, netOut);
        emit SwapLocal(msg.sender, true, amountIn, netOut);
    }

    function swapStableToHolon(uint256 amountIn, uint256 amountOutMin, address to)
        external nonReentrant returns (uint256 amountOut)
    {
        require(amountIn > 0, "Zero input");
        if (amountIn > uniswapThreshold)
            return _bridgeSwap(address(stablecoin), address(holonToken), amountIn, amountOutMin, to);

        // Fees se toman del amountIn (en stablecoin) para consistencia
        uint256 feeLocal = (amountIn * feeLocalBps) / 10000;
        uint256 feeCommon = (amountIn * feeCommonBps) / 10000;
        uint256 netIn = amountIn - feeLocal - feeCommon;

        amountOut = _getAmountOut(netIn, reserveStable, reserveHolon);
        require(amountOut >= amountOutMin, "Slippage exceeded");

        stablecoin.safeTransferFrom(msg.sender, address(this), amountIn);
        reserveStable += netIn + feeLocal;
        reserveHolon -= amountOut;
        accumulatedCommonFees += feeCommon;

        holonToken.safeTransfer(to, amountOut);
        emit SwapLocal(msg.sender, false, amountIn, amountOut);
    }

    // ══ CAPA 2: BRIDGE UNISWAP V3 ════════════════════════════════════════

    function _bridgeSwap(address tokenIn, address tokenOut, uint256 amountIn, uint256 amountOutMin, address recipient)
        internal returns (uint256 amountOut)
    {
        IERC20(tokenIn).safeTransferFrom(msg.sender, address(this), amountIn);
        IERC20(tokenIn).approve(address(uniswapRouter), amountIn);
        IUniswapV3Router.ExactInputSingleParams memory params = IUniswapV3Router.ExactInputSingleParams({
            tokenIn: tokenIn, tokenOut: tokenOut, fee: uniswapPoolFee, recipient: recipient,
            deadline: block.timestamp + 15 minutes, amountIn: amountIn,
            amountOutMinimum: amountOutMin, sqrtPriceLimitX96: 0
        });
        amountOut = uniswapRouter.exactInputSingle(params);
        emit SwapBridged(msg.sender, tokenIn, tokenOut, amountIn, amountOut);
    }

    // ══ CAPA 3: COMMON STAKE POOL ════════════════════════════════════════

    /**
     * @notice Envia fees acumuladas al CommonStakePool.
     * @dev Requiere que este contrato tenga MMA_POOL_ROLE en CommonStakePool
     *      (otorgado via commonStakePool.registerMMAPool(address(this))).
     */
    function forwardFeesToCommon() external onlyRole(GOVERNANCE_ROLE) {
        require(accumulatedCommonFees > 0, "No fees to forward");
        uint256 amount = accumulatedCommonFees;
        accumulatedCommonFees = 0;
        stablecoin.approve(address(commonStakePool), amount);
        commonStakePool.depositFees(holonId, amount);
        emit FeesForwarded(amount);
    }

    function stakeToCommonPool(uint256 amount) external onlyRole(GOVERNANCE_ROLE) nonReentrant {
        require(amount <= (reserveStable * maxStakeRatio) / 10000, "Exceeds max stake ratio");
        require(amount <= reserveStable, "Insufficient reserves");
        reserveStable -= amount;
        stablecoin.approve(address(commonStakePool), amount);
        commonStakePool.depositStake(holonId, amount);
        emit StakeDeposited(amount);
    }

    // ══ VISTAS (Frontend) ════════════════════════════════════════════════

    /// @notice Precio del HolonToken en stablecoin (precision 1e18)
    function getHolonPrice() external view returns (uint256) {
        if (reserveHolon == 0) return 0;
        return (reserveStable * 1e18) / reserveHolon;
    }

    /// @notice TVL total en stablecoin
    function getTVL() external view returns (uint256) { return reserveStable * 2; }

    /// @notice Constante K
    function getK() external view returns (uint256) { return reserveHolon * reserveStable; }

    /// @notice Simula un swap sin ejecutar
    function quoteSwap(uint256 amountIn, bool holonToStable) external view returns (uint256) {
        if (holonToStable) return _getAmountOut(amountIn, reserveHolon, reserveStable);
        return _getAmountOut(amountIn, reserveStable, reserveHolon);
    }

    // ══ GOBERNANZA ═══════════════════════════════════════════════════════

    function setFees(uint256 _local, uint256 _common) external onlyRole(GOVERNANCE_ROLE) {
        require(_local + _common <= 100, "Total fee > 1%");
        feeLocalBps = _local; feeCommonBps = _common;
    }
    function setUniswapThreshold(uint256 _t) external onlyRole(GOVERNANCE_ROLE) { uniswapThreshold = _t; }
    function setMaxStakeRatio(uint256 _r) external onlyRole(GOVERNANCE_ROLE) { require(_r <= 5000, "Max 50%"); maxStakeRatio = _r; }

    // ══ INTERNALS ════════════════════════════════════════════════════════

    function _getAmountOut(uint256 amountIn, uint256 reserveIn, uint256 reserveOut) internal pure returns (uint256) {
        require(amountIn > 0 && reserveIn > 0 && reserveOut > 0, "Invalid");
        return (amountIn * reserveOut) / (reserveIn + amountIn);
    }
    function _sqrt(uint256 x) internal pure returns (uint256 y) {
        if (x == 0) return 0; y = x; uint256 z = (x + 1) / 2;
        while (z < y) { y = z; z = (x / z + z) / 2; }
    }
    function _min(uint256 a, uint256 b) internal pure returns (uint256) { return a < b ? a : b; }
}
