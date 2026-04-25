# ── HoFi Voice Auth Service — Deploy a Cloud Run ─────────────────────────────
# Ejecutar desde: C:\Users\54113\dev\hofi-protocol\packages\voice-auth-service
# Requisitos: gcloud CLI autenticado, proyecto hofi-v2-2026.
#
# Este servicio comparte DB, voice_auth.py y secrets con hofi-bot. Por eso
# el paso 1 copia los archivos Python comunes desde ../telegram-bot/ a este
# contexto antes de buildear. Si preferís mantenerlos como un paquete Python
# instalable, migrarlos a packages/shared en el futuro.

$PROJECT = "hofi-v2-2026"
$REGION  = "us-central1"
$SERVICE = "hofi-voice-api"
$REPO    = "hofi-repo"
$IMAGE   = "$REGION-docker.pkg.dev/$PROJECT/$REPO/$SERVICE`:latest"

Write-Host "=== HoFi Voice Auth Service Deploy ===" -ForegroundColor Cyan

# 1. Sync de código compartido desde ../telegram-bot
Write-Host "`n[1/6] Sync voice_auth.py/db.py desde ../telegram-bot/..." -ForegroundColor Yellow
Copy-Item -Path "..\telegram-bot\voice_auth.py" -Destination ".\voice_auth.py" -Force
Copy-Item -Path "..\telegram-bot\db.py"         -Destination ".\db.py"         -Force
if (Test-Path "..\telegram-bot\mock_profiles.json") {
    Copy-Item -Path "..\telegram-bot\mock_profiles.json" -Destination ".\mock_profiles.json" -Force
}
Write-Host "  archivos compartidos copiados OK" -ForegroundColor Green

# 2. Secret JWT_SECRET_KEY (compartido con Tenzo Agent)
Write-Host "`n[2/6] Verificando secret JWT_SECRET_KEY..." -ForegroundColor Yellow
$jwt_exists = gcloud secrets describe JWT_SECRET_KEY --project=$PROJECT 2>$null
if (-not $jwt_exists) {
    Write-Host "  ERROR: JWT_SECRET_KEY no existe en Secret Manager." -ForegroundColor Red
    Write-Host "         Este secret DEBE existir y coincidir con el del Tenzo." -ForegroundColor Red
    Write-Host "         Crealo primero con: gcloud secrets create JWT_SECRET_KEY --data-file=..." -ForegroundColor Red
    exit 1
} else {
    Write-Host "  JWT_SECRET_KEY OK (compartido con Tenzo Agent)" -ForegroundColor Green
}

# 3. Build + push
Write-Host "`n[3/6] Build y push de imagen Docker..." -ForegroundColor Yellow
gcloud builds submit . `
    --project=$PROJECT `
    --tag=$IMAGE `
    --timeout=20m

if ($LASTEXITCODE -ne 0) {
    Write-Host "ERROR en el build. Abortando." -ForegroundColor Red
    exit 1
}

# 4. Deploy en Cloud Run
Write-Host "`n[4/6] Desplegando en Cloud Run..." -ForegroundColor Yellow
$CLOUDSQL_INSTANCE = "project-a091a8d4-924d-46c7-a19:us-central1:hofi-tenzo"
$DB_SOCKET         = "/cloudsql/$CLOUDSQL_INSTANCE"

# CORS: incluir todos los orígenes del frontend (dev + prod).
# OJO: contiene comas, así que usamos delimiter custom "^##^" en --set-env-vars
# para que gcloud no interprete las comas internas como separadores de vars.
$CORS_ORIGINS = "http://localhost:3000,https://hofi.app,https://hofi-protocol.vercel.app"
$ENV_VARS = "^##^DB_MOCK=false##DB_HOST=$DB_SOCKET##DB_NAME=hofi##DB_USER=tenzo##CORS_ORIGINS=$CORS_ORIGINS##JWT_TTL_SECS=604800"

gcloud run deploy $SERVICE `
    --image=$IMAGE `
    --project=$PROJECT `
    --region=$REGION `
    --platform=managed `
    --allow-unauthenticated `
    --memory=1Gi `
    --cpu=1 `
    --cpu-boost `
    --min-instances=0 `
    --max-instances=3 `
    --timeout=120 `
    --add-cloudsql-instances="$CLOUDSQL_INSTANCE" `
    --set-env-vars="$ENV_VARS" `
    --set-secrets="JWT_SECRET_KEY=JWT_SECRET_KEY:latest,DEMO_API_KEY=DEMO_API_KEY:latest,DB_PASS=DB_PASS:latest" `
    --port=8080

if ($LASTEXITCODE -ne 0) {
    Write-Host "ERROR en el deploy. Revisá los logs." -ForegroundColor Red
    exit 1
}

# 5. Permisos del service account (secrets + Cloud SQL)
Write-Host "`n[5/6] Configurando permisos IAM..." -ForegroundColor Yellow
$PROJECT_NUMBER = (gcloud projects describe $PROJECT --format="value(projectNumber)")
$SA = "$PROJECT_NUMBER-compute@developer.gserviceaccount.com"
Write-Host "  Service Account: $SA" -ForegroundColor Green

gcloud secrets add-iam-policy-binding JWT_SECRET_KEY `
    --project=$PROJECT `
    --member="serviceAccount:$SA" `
    --role="roles/secretmanager.secretAccessor" 2>$null
gcloud secrets add-iam-policy-binding DEMO_API_KEY `
    --project=$PROJECT `
    --member="serviceAccount:$SA" `
    --role="roles/secretmanager.secretAccessor" 2>$null
gcloud secrets add-iam-policy-binding DB_PASS `
    --project=$PROJECT `
    --member="serviceAccount:$SA" `
    --role="roles/secretmanager.secretAccessor" 2>$null
gcloud projects add-iam-policy-binding $PROJECT `
    --member="serviceAccount:$SA" `
    --role="roles/cloudsql.client" 2>$null
# Permiso CROSS-PROJECT: la instancia hofi-tenzo vive en otro project
# (HoFi - Holonic Finances). Sin este binding el servicio falla con 403
# NOT_AUTHORIZED al conectar a Cloud SQL después de redeployar.
$DB_PROJECT = "project-a091a8d4-924d-46c7-a19"
gcloud projects add-iam-policy-binding $DB_PROJECT `
    --member="serviceAccount:$SA" `
    --role="roles/cloudsql.client" 2>$null
Write-Host "  Permisos OK" -ForegroundColor Green

# 6. URL final
Write-Host "`n[6/6] Obteniendo URL del servicio..." -ForegroundColor Yellow
$SERVICE_URL = (gcloud run services describe $SERVICE --project=$PROJECT --region=$REGION --format="value(status.url)")
Write-Host "`n=== Deploy completo ===" -ForegroundColor Cyan
Write-Host "Voice Auth URL: $SERVICE_URL" -ForegroundColor Green
Write-Host ""
Write-Host "Siguiente paso: configurar VOICE_AUTH_URL en el frontend Next.js:" -ForegroundColor Cyan
Write-Host "  VOICE_AUTH_URL=$SERVICE_URL/voice/authenticate" -ForegroundColor White
Write-Host ""
Write-Host "Health check:" -ForegroundColor Cyan
Write-Host "  curl $SERVICE_URL/health" -ForegroundColor White
