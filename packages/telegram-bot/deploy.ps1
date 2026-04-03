# ── HoFi Bot — Deploy a Cloud Run ─────────────────────────────────────────────
# Ejecutar desde: C:\dev\hofi-protocol\packages\telegram-bot
# Requisitos: gcloud CLI autenticado, proyecto hofi-v2-2026

$PROJECT   = "hofi-v2-2026"
$REGION    = "us-central1"
$SERVICE   = "hofi-bot"
$REPO      = "hofi-repo"
$IMAGE     = "$REGION-docker.pkg.dev/$PROJECT/$REPO/hofi-bot:latest"
$BUCKET    = "hofi-bot-data"

Write-Host "=== HoFi Bot Deploy ===" -ForegroundColor Cyan

# 1. Crear bucket GCS para persistencia de perfiles (si no existe)
Write-Host "`n[1/7] Creando bucket GCS para perfiles..." -ForegroundColor Yellow
gcloud storage buckets create "gs://$BUCKET" --project=$PROJECT --location=$REGION 2>$null
if ($LASTEXITCODE -ne 0) { Write-Host "  Bucket ya existe, OK." -ForegroundColor Green }

# 1b. Crear repo Artifact Registry si no existe
$repo_exists = gcloud artifacts repositories describe $REPO --project=$PROJECT --location=$REGION 2>$null
if (-not $repo_exists) {
    Write-Host "  Creando Artifact Registry repo '$REPO'..." -ForegroundColor Yellow
    gcloud artifacts repositories create $REPO `
        --repository-format=docker `
        --location=$REGION `
        --project=$PROJECT
} else {
    Write-Host "  Repo Artifact Registry ya existe, OK." -ForegroundColor Green
}

# Configurar Docker para usar Artifact Registry
gcloud auth configure-docker "$REGION-docker.pkg.dev" --quiet

# 2. Agregar secret TELEGRAM_BOT_TOKEN (si no existe)
Write-Host "`n[2/7] Configurando secret TELEGRAM_BOT_TOKEN..." -ForegroundColor Yellow
$token_exists = gcloud secrets describe TELEGRAM_BOT_TOKEN --project=$PROJECT 2>$null
if (-not $token_exists) {
    $bot_token = Read-Host "Pegá el token del bot de Telegram"
    [System.IO.File]::WriteAllText("$env:TEMP\bot_token.tmp", $bot_token)
    gcloud secrets create TELEGRAM_BOT_TOKEN --project=$PROJECT --data-file="$env:TEMP\bot_token.tmp"
    Remove-Item "$env:TEMP\bot_token.tmp"
} else {
    Write-Host "  Secret ya existe, OK." -ForegroundColor Green
}

# 2b. Agregar secret DEMO_API_KEY (si no existe)
# Este es el API key para autenticarse contra el Tenzo Agent
Write-Host "`n[2b/7] Configurando secret DEMO_API_KEY..." -ForegroundColor Yellow
$demo_exists = gcloud secrets describe DEMO_API_KEY --project=$PROJECT 2>$null
if (-not $demo_exists) {
    $demo_key = Read-Host "Pegá el DEMO_API_KEY del Tenzo (o Enter para usar 'hofi-demo-2026')"
    if (-not $demo_key) { $demo_key = "hofi-demo-2026" }
    [System.IO.File]::WriteAllText("$env:TEMP\demo_key.tmp", $demo_key)
    gcloud secrets create DEMO_API_KEY --project=$PROJECT --data-file="$env:TEMP\demo_key.tmp"
    Remove-Item "$env:TEMP\demo_key.tmp"
} else {
    Write-Host "  Secret ya existe, OK." -ForegroundColor Green
}

# 3. Build y push de la imagen Docker
# NOTA: la imagen ya fue buildeada. Si no hay cambios, se puede saltar con -SkipBuild
Write-Host "`n[3/7] Build y push de imagen Docker..." -ForegroundColor Yellow
gcloud builds submit . `
    --project=$PROJECT `
    --tag=$IMAGE `
    --timeout=20m

if ($LASTEXITCODE -ne 0) {
    Write-Host "ERROR en el build. Abortando." -ForegroundColor Red
    exit 1
}

# 4. Deploy en Cloud Run
# IMPORTANTE: WEBHOOK_URL se pone como placeholder para que el bot arranque
# en modo webhook (escucha en PORT 8080) y pase el health check de Cloud Run.
# Se actualiza a la URL real en el paso 5.
# startup-probe-initial-delay=30: da tiempo a importar faster-whisper/librosa (~20s)
Write-Host "`n[4/7] Desplegando en Cloud Run..." -ForegroundColor Yellow
gcloud run deploy $SERVICE `
    --image=$IMAGE `
    --project=$PROJECT `
    --region=$REGION `
    --platform=managed `
    --allow-unauthenticated `
    --memory=1Gi `
    --cpu=1 `
    --cpu-boost `
    --min-instances=1 `
    --max-instances=3 `
    --timeout=300 `
    --set-env-vars="DB_MOCK=true,GCS_BUCKET=$BUCKET,TENZO_API_URL=https://hofi-tenzo-1080243330445.us-central1.run.app,VOICE_SIMILARITY_THRESHOLD=0.90,WEBHOOK_URL=https://placeholder.hofi.app,HF_HUB_OFFLINE=1,TRANSFORMERS_OFFLINE=1" `
    --set-secrets="TELEGRAM_BOT_TOKEN=TELEGRAM_BOT_TOKEN:latest,DEMO_API_KEY=DEMO_API_KEY:latest" `
    --port=8080

if ($LASTEXITCODE -ne 0) {
    Write-Host "ERROR en el deploy. Revisá los logs." -ForegroundColor Red
    exit 1
}

# 5. Obtener la URL real y actualizar WEBHOOK_URL
Write-Host "`n[5/7] Actualizando WEBHOOK_URL con la URL real..." -ForegroundColor Yellow
$SERVICE_URL = (gcloud run services describe $SERVICE --project=$PROJECT --region=$REGION --format="value(status.url)")
Write-Host "  URL del servicio: $SERVICE_URL" -ForegroundColor Green

gcloud run services update $SERVICE `
    --project=$PROJECT `
    --region=$REGION `
    --update-env-vars="WEBHOOK_URL=$SERVICE_URL"

if ($LASTEXITCODE -ne 0) {
    Write-Host "ERROR actualizando WEBHOOK_URL." -ForegroundColor Red
    exit 1
}

# 6. Dar permiso al service account para leer/escribir el bucket GCS
Write-Host "`n[6/7] Configurando permisos GCS..." -ForegroundColor Yellow
$SA = (gcloud run services describe $SERVICE --project=$PROJECT --region=$REGION --format="value(spec.template.spec.serviceAccountName)")
if (-not $SA) {
    $PROJECT_NUMBER = (gcloud projects describe $PROJECT --format="value(projectNumber)")
    $SA = "$PROJECT_NUMBER-compute@developer.gserviceaccount.com"
}
Write-Host "  Service Account: $SA" -ForegroundColor Green
gcloud storage buckets add-iam-policy-binding "gs://$BUCKET" `
    --member="serviceAccount:$SA" `
    --role="roles/storage.objectAdmin"

# 7. Dar permiso al service account para leer los secrets
Write-Host "`n[7/7] Configurando permisos Secret Manager..." -ForegroundColor Yellow
gcloud secrets add-iam-policy-binding TELEGRAM_BOT_TOKEN `
    --project=$PROJECT `
    --member="serviceAccount:$SA" `
    --role="roles/secretmanager.secretAccessor" 2>$null
gcloud secrets add-iam-policy-binding DEMO_API_KEY `
    --project=$PROJECT `
    --member="serviceAccount:$SA" `
    --role="roles/secretmanager.secretAccessor" 2>$null
Write-Host "  Permisos Secret Manager configurados, OK." -ForegroundColor Green

Write-Host "`n=== Deploy completo ===" -ForegroundColor Cyan
Write-Host "Bot URL:   $SERVICE_URL" -ForegroundColor Green
Write-Host "Webhook:   $SERVICE_URL (Telegram registra automáticamente)" -ForegroundColor Green
Write-Host "`nProbá mandando /start al bot en Telegram."
