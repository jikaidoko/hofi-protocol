// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "@openzeppelin/contracts/token/ERC20/ERC20.sol";
import "@openzeppelin/contracts/access/AccessControl.sol";
import "@openzeppelin/contracts/utils/ReentrancyGuard.sol";

/**
 * @title HolonToken
 * @notice Token soberano de cada Holon. ERC-20 con roles mint/burn
 *         controlados por la gobernanza del holon.
 */
contract HolonToken is ERC20, AccessControl {
    bytes32 public constant MINTER_ROLE = keccak256("MINTER_ROLE");

    string public holonId;
    uint8 private _decimals;

    constructor(
        string memory name_,
        string memory symbol_,
        string memory holonId_,
        uint8 decimals_,
        address governance
    ) ERC20(name_, symbol_) {
        holonId = holonId_;
        _decimals = decimals_;
        _grantRole(DEFAULT_ADMIN_ROLE, governance);
        _grantRole(MINTER_ROLE, governance);
    }

    function decimals() public view override returns (uint8) {
        return _decimals;
    }

    function mint(address to, uint256 amount) external onlyRole(MINTER_ROLE) {
        _mint(to, amount);
    }

    function burn(uint256 amount) external {
        _burn(msg.sender, amount);
    }
}

enum StabilityMode { ALGORITHMIC, BASKET }

/**
 * @title HolonTokenFactory
 * @notice Permite a cada holon desplegar su token soberano con el modelo
 *         de estabilidad que elija: algoritmico (bonding curve) o basket.
 */
contract HolonTokenFactory is AccessControl, ReentrancyGuard {
    bytes32 public constant REGISTRAR_ROLE = keccak256("REGISTRAR_ROLE");

    struct BondingCurveParams {
        uint256 reserveRatio;   // En basis points (5000 = 50%)
        uint256 initialPrice;   // Precio inicial en wei del stablecoin base
        uint256 maxSupplyCap;   // 0 = ilimitado
    }

    struct BasketConfig {
        address[] collateralTokens;
        uint256[] collateralRatios;   // Suma debe ser 10000 (100%)
        uint256 collateralRatioMin;   // Minimo de colateralizacion (15000 = 150%)
    }

    struct HolonTokenInfo {
        address tokenAddress;
        string holonId;
        StabilityMode mode;
        address mmaPool;
        address governance;
        uint256 createdAt;
        bool active;
    }

    mapping(string => HolonTokenInfo) public holonTokens;
    mapping(address => string) public tokenToHolon;
    string[] public registeredHolons;

    mapping(string => BondingCurveParams) public bondingParams;
    mapping(string => BasketConfig) internal basketConfigs;

    address public immutable baseStablecoin;

    event HolonTokenCreated(string indexed holonId, address tokenAddress, StabilityMode mode, address governance);
    event MMAPoolLinked(string indexed holonId, address mmaPool);

    constructor(address _baseStablecoin) {
        baseStablecoin = _baseStablecoin;
        _grantRole(DEFAULT_ADMIN_ROLE, msg.sender);
        _grantRole(REGISTRAR_ROLE, msg.sender);
    }

    function createAlgorithmicToken(
        string calldata holonId,
        string calldata name,
        string calldata symbol,
        uint8 tokenDecimals,
        address governance,
        uint256 reserveRatio,
        uint256 initialPrice,
        uint256 maxSupplyCap
    ) external onlyRole(REGISTRAR_ROLE) nonReentrant returns (address) {
        require(holonTokens[holonId].tokenAddress == address(0), "Holon already has token");
        require(reserveRatio > 0 && reserveRatio <= 10000, "Invalid reserve ratio");

        HolonToken token = new HolonToken(name, symbol, holonId, tokenDecimals, governance);
        address tokenAddr = address(token);

        holonTokens[holonId] = HolonTokenInfo({
            tokenAddress: tokenAddr,
            holonId: holonId,
            mode: StabilityMode.ALGORITHMIC,
            mmaPool: address(0),
            governance: governance,
            createdAt: block.timestamp,
            active: true
        });
        bondingParams[holonId] = BondingCurveParams({ reserveRatio: reserveRatio, initialPrice: initialPrice, maxSupplyCap: maxSupplyCap });
        tokenToHolon[tokenAddr] = holonId;
        registeredHolons.push(holonId);

        emit HolonTokenCreated(holonId, tokenAddr, StabilityMode.ALGORITHMIC, governance);
        return tokenAddr;
    }

    function createBasketToken(
        string calldata holonId,
        string calldata name,
        string calldata symbol,
        uint8 tokenDecimals,
        address governance,
        address[] calldata collateralTokens,
        uint256[] calldata collateralRatios,
        uint256 collateralRatioMin
    ) external onlyRole(REGISTRAR_ROLE) nonReentrant returns (address) {
        require(holonTokens[holonId].tokenAddress == address(0), "Holon already has token");
        require(collateralTokens.length == collateralRatios.length, "Arrays mismatch");
        require(collateralRatioMin >= 10000, "Min ratio must be >= 100%");

        uint256 totalRatio;
        for (uint256 i = 0; i < collateralRatios.length; i++) totalRatio += collateralRatios[i];
        require(totalRatio == 10000, "Ratios must sum to 10000");

        HolonToken token = new HolonToken(name, symbol, holonId, tokenDecimals, governance);
        address tokenAddr = address(token);

        holonTokens[holonId] = HolonTokenInfo({
            tokenAddress: tokenAddr,
            holonId: holonId,
            mode: StabilityMode.BASKET,
            mmaPool: address(0),
            governance: governance,
            createdAt: block.timestamp,
            active: true
        });
        basketConfigs[holonId] = BasketConfig({ collateralTokens: collateralTokens, collateralRatios: collateralRatios, collateralRatioMin: collateralRatioMin });
        tokenToHolon[tokenAddr] = holonId;
        registeredHolons.push(holonId);

        emit HolonTokenCreated(holonId, tokenAddr, StabilityMode.BASKET, governance);
        return tokenAddr;
    }

    function linkMMAPool(string calldata holonId, address mmaPool) external onlyRole(REGISTRAR_ROLE) {
        require(holonTokens[holonId].tokenAddress != address(0), "Holon not registered");
        require(holonTokens[holonId].mmaPool == address(0), "Pool already linked");
        holonTokens[holonId].mmaPool = mmaPool;
        emit MMAPoolLinked(holonId, mmaPool);
    }

    function getHolonCount() external view returns (uint256) { return registeredHolons.length; }
    function getTokenAddress(string calldata holonId) external view returns (address) { return holonTokens[holonId].tokenAddress; }
    function isHolonActive(string calldata holonId) external view returns (bool) { return holonTokens[holonId].active; }

    function getBasketConfig(string calldata holonId)
        external view returns (address[] memory tokens, uint256[] memory ratios, uint256 minRatio)
    {
        BasketConfig storage cfg = basketConfigs[holonId];
        return (cfg.collateralTokens, cfg.collateralRatios, cfg.collateralRatioMin);
    }
}
