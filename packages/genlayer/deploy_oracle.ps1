# deploy_oracle.ps1
# Deploya TenzoEquityOracle v0.2.0 en GenLayer Testnet Asimov
# Uso: cd packages\genlayer && .\deploy_oracle.ps1

# Forzar UTF-8 en consola (evita Ã¡ etc. en PowerShell 5.1)
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding          = [System.Text.Encoding]::UTF8

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

Write-Host ""
Write-Host "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" -ForegroundColor Cyan
Write-Host "  HoFi · TenzoEquityOracle v0.2.0 Deploy" -ForegroundColor Cyan
Write-Host "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" -ForegroundColor Cyan
Write-Host ""

# ── Paso 1: Verificar Node.js ──────────────────────────────────────────────────
Write-Host "[1/4] Verificando Node.js..."
$nodeVersion = node --version 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Host "❌  Node.js no encontrado. Instala desde https://nodejs.org" -ForegroundColor Red
    exit 1
}
Write-Host "     ✅ Node.js $nodeVersion"

# ── Paso 2: Instalar dependencias ─────────────────────────────────────────────
Write-Host "[2/4] Instalando dependencias npm..."
if (-not (Test-Path "node_modules\genlayer-js")) {
    npm install
    if ($LASTEXITCODE -ne 0) {
        Write-Host "❌  npm install falló." -ForegroundColor Red
        exit 1
    }
} else {
    Write-Host "     ✅ genlayer-js ya instalado"
}

# ── Paso 3: Clave privada ──────────────────────────────────────────────────────
Write-Host "[3/4] Verificando clave privada..."
if (-not $env:GENLAYER_PRIVATE_KEY) {
    Write-Host ""
    Write-Host "  ⚠️  Variable GENLAYER_PRIVATE_KEY no configurada." -ForegroundColor Yellow
    Write-Host "  Copia tu clave privada desde:" -ForegroundColor Yellow
    Write-Host "    GenLayer Studio -> panel izquierdo -> icono de billetera -> Export / Copy key" -ForegroundColor Yellow
    Write-Host ""
    $key = Read-Host "  Pegá tu clave privada (0x...)"
    if (-not $key.StartsWith("0x")) {
        $key = "0x" + $key
    }
    $env:GENLAYER_PRIVATE_KEY = $key
}
Write-Host "     ✅ Clave configurada"

# ── Paso 4: Deploy ────────────────────────────────────────────────────────────
Write-Host "[4/4] Ejecutando deploy..."
Write-Host ""
node deploy/deployTenzoOracle.mjs

if ($LASTEXITCODE -ne 0) {
    Write-Host ""
    Write-Host "❌  Deploy falló. Revisá el error arriba." -ForegroundColor Red
    exit 1
}

Write-Host ""
Write-Host "Recuerda actualizar tambien la linea 40 de genlayer_bridge.py si cambia la direccion:" -ForegroundColor DarkGray
Write-Host '  ORACLE_ADDRESS = os.getenv("TENZO_ORACLE_ADDRESS", "<nueva_direccion>")' -ForegroundColor DarkGray
