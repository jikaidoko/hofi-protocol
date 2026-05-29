# ===========================================================================
# HoFi - Crear secrets en hofi-v3-2026 (DB -> Neon, sin blockchain)
#
# - Los 3 secrets externos (DB_PASS, GEMINI_API_KEY, TELEGRAM_BOT_TOKEN) se
#   piden por prompt seguro: NO quedan en disco ni en el history de PowerShell.
# - JWT_SECRET_KEY y DEMO_API_KEY se generan con el RNG nativo de PowerShell.
# - ADMIN_PASSWORD_HASH necesita bcrypt -> usa Python (prueba 'py' primero
#   para esquivar el stub de la Microsoft Store).
# - Cada secret se escribe sin BOM ni trailing newline.
#
# IMPORTANTE: este archivo es ASCII puro a proposito. Windows PowerShell 5.1
# lee los .ps1 como CP1252; cualquier caracter no-ASCII (acentos, recuadros)
# corrompe el parseo. No agregar acentos aca.
#
# Uso:
#   cd C:\Users\54113\dev\hofi-protocol
#   .\packages\infra\create-secrets.ps1
# ===========================================================================

$ErrorActionPreference = "Continue"
$PROJECT = "hofi-v3-2026"

Write-Host "`n=== Creando secrets en $PROJECT ===`n" -ForegroundColor Cyan

# --- Helper: hex aleatorio criptografico (PowerShell nativo, sin Python) ---
function New-RandomHex([int]$numBytes) {
    $b = New-Object 'System.Byte[]' $numBytes
    [System.Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($b)
    return (($b | ForEach-Object { $_.ToString('x2') }) -join '')
}

# --- Helper: crea secret (o agrega version si ya existe) sin BOM ni newline ---
function Set-Secret {
    param([string]$Name, [string]$Value)
    if ([string]::IsNullOrWhiteSpace($Value)) {
        Write-Host "  ! $Name VACIO - no se crea (revisar input)" -ForegroundColor Red
        return
    }
    $tmp = [IO.Path]::GetTempFileName()
    try {
        [IO.File]::WriteAllText($tmp, $Value, [System.Text.UTF8Encoding]::new($false))
        gcloud secrets describe $Name --project=$PROJECT 2>$null | Out-Null
        if ($LASTEXITCODE -eq 0) {
            gcloud secrets versions add $Name --data-file=$tmp --project=$PROJECT | Out-Null
            if ($LASTEXITCODE -eq 0) { Write-Host "  ~ $Name (nueva version)" -ForegroundColor Yellow }
            else { Write-Host "  ! $Name FALLO al agregar version" -ForegroundColor Red }
        } else {
            gcloud secrets create $Name --data-file=$tmp --project=$PROJECT | Out-Null
            if ($LASTEXITCODE -eq 0) { Write-Host "  + $Name (creado)" -ForegroundColor Green }
            else { Write-Host "  ! $Name FALLO al crear" -ForegroundColor Red }
        }
    } finally {
        Remove-Item $tmp -Force -ErrorAction SilentlyContinue
    }
}

# --- Helper: SecureString -> texto plano (solo en memoria) ---
function Read-Secret([string]$Prompt) {
    $sec = Read-Host -Prompt $Prompt -AsSecureString
    $bstr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($sec)
    try { return [Runtime.InteropServices.Marshal]::PtrToStringAuto($bstr) }
    finally { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($bstr) }
}

# --- Detectar un Python 3 real (esquiva el stub de la Microsoft Store) ---
$PY = $null
foreach ($cand in @("py", "python", "python3")) {
    if (Get-Command $cand -ErrorAction SilentlyContinue) {
        $ver = & $cand --version 2>&1 | Out-String
        if ($ver -match "Python 3") { $PY = $cand; break }
    }
}
if (-not $PY) {
    Write-Host "ERROR: no encontre un Python 3 real (probe py, python, python3)." -ForegroundColor Red
    Write-Host "Instala Python desde https://www.python.org/downloads/ marcando" -ForegroundColor Red
    Write-Host "'Add python.exe to PATH', cerra y reabri PowerShell, y re-corre." -ForegroundColor Red
    exit 1
}
Write-Host "Python detectado: $PY" -ForegroundColor DarkGray

# --- 1) Secrets EXTERNOS (prompt seguro) ---
Write-Host "`nPega los valores externos (no se muestran en pantalla):`n"
$DB_PASS            = Read-Secret "DB_PASS (password de Neon)"
$GEMINI_API_KEY     = Read-Secret "GEMINI_API_KEY (la nueva, NO la del proyecto viejo)"
$TELEGRAM_BOT_TOKEN = Read-Secret "TELEGRAM_BOT_TOKEN (el nuevo, post-revoke)"

# --- 2) Secrets INTERNOS ---
Write-Host "`nGenerando secrets internos..." -ForegroundColor Cyan
$JWT_SECRET_KEY = New-RandomHex 32
$DEMO_API_KEY   = New-RandomHex 32
$ADMIN_PASSWORD = New-RandomHex 12

Write-Host "Asegurando bcrypt local (para el hash del admin)..." -ForegroundColor Yellow
& $PY -m pip install bcrypt --quiet 2>&1 | Out-Null

$pyCode = 'import bcrypt,sys; print(bcrypt.hashpw(sys.argv[1].encode(), bcrypt.gensalt()).decode())'
$ADMIN_PASSWORD_HASH = (& $PY -c $pyCode $ADMIN_PASSWORD | Out-String).Trim()

if ([string]::IsNullOrWhiteSpace($ADMIN_PASSWORD_HASH) -or -not $ADMIN_PASSWORD_HASH.StartsWith('$2')) {
    Write-Host "ERROR: no se pudo generar el hash bcrypt (output: '$ADMIN_PASSWORD_HASH')." -ForegroundColor Red
    Write-Host "Verifica que '$PY -m pip install bcrypt' funcione y re-corre." -ForegroundColor Red
    exit 1
}

# --- 3) Crear todos los secrets ---
Write-Host "`nEscribiendo secrets en Secret Manager...`n" -ForegroundColor Cyan
Set-Secret "DB_PASS"             $DB_PASS
Set-Secret "GEMINI_API_KEY"      $GEMINI_API_KEY
Set-Secret "TELEGRAM_BOT_TOKEN"  $TELEGRAM_BOT_TOKEN
Set-Secret "JWT_SECRET_KEY"      $JWT_SECRET_KEY
Set-Secret "DEMO_API_KEY"        $DEMO_API_KEY
Set-Secret "ADMIN_PASSWORD_HASH" $ADMIN_PASSWORD_HASH

# --- 4) Mostrar lo que necesitas guardar (UNA vez) ---
Write-Host "`n===========================================================" -ForegroundColor Magenta
Write-Host "GUARDA ESTO EN TU GESTOR DE PASSWORDS (no se vuelve a mostrar):" -ForegroundColor Magenta
Write-Host "  ADMIN_USERNAME = tenzo-admin"
Write-Host "  ADMIN_PASSWORD = $ADMIN_PASSWORD"
Write-Host "  JWT_SECRET_KEY = $JWT_SECRET_KEY"
Write-Host "  DEMO_API_KEY   = $DEMO_API_KEY"
Write-Host "===========================================================`n" -ForegroundColor Magenta
Write-Host "JWT_SECRET_KEY y DEMO_API_KEY tambien van en Vercel (frontend)." -ForegroundColor Cyan
Write-Host "DEMO_API_KEY es lo que el frontend usa para autenticarse al Tenzo.`n" -ForegroundColor Cyan

# --- 5) Listar lo creado ---
gcloud secrets list --project=$PROJECT --format="table(name,createTime)"
