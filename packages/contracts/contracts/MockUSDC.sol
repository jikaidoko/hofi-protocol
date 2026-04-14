// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "@openzeppelin/contracts/token/ERC20/ERC20.sol";
import "@openzeppelin/contracts/access/Ownable.sol";

/**
 * @title MockUSDC
 * @notice USDC simulado para testnet. Faucet libre para testing.
 *         En produccion se reemplaza por el USDC real del bridge.
 */
contract MockUSDC is ERC20, Ownable {
    constructor() ERC20("Mock USDC", "USDC") Ownable(msg.sender) {
        _mint(msg.sender, 1_000_000 * 1e6);
    }

    function decimals() public pure override returns (uint8) {
        return 6;
    }

    function mint(address to, uint256 amount) external onlyOwner {
        _mint(to, amount);
    }

    /// @notice Faucet: cualquiera puede pedir hasta 10,000 USDC de prueba
    function faucet(uint256 amount) external {
        require(amount <= 10_000 * 1e6, "Max 10,000 USDC por faucet");
        _mint(msg.sender, amount);
    }
}
