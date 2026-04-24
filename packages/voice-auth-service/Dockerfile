FROM python:3.11-slim

WORKDIR /app

# ffmpeg — librosa lo usa para decodificar webm/oga/mp4.
RUN apt-get update && \
    apt-get install -y --no-install-recommends ffmpeg && \
    rm -rf /var/lib/apt/lists/*

# ── Dependencias Python ──────────────────────────────────────────────────────
COPY requirements.txt .
RUN pip install --upgrade pip --no-cache-dir && \
    pip install --no-cache-dir -r requirements.txt

# Sanity check de librosa en build-time (falla rápido si algo se rompió).
RUN python -c "import librosa; print('librosa OK:', librosa.__version__)"

# ── Código fuente ────────────────────────────────────────────────────────────
# Reutilizamos voice_auth.py y db.py del paquete telegram-bot. El script de
# deploy copia estos archivos desde ../telegram-bot a este contexto antes de
# invocar gcloud builds submit. Si existe mock_profiles.json también lo
# copiamos para tener un estado inicial consistente con el bot en dev.
COPY main.py .
COPY voice_auth.py .
COPY db.py .
COPY mock_profiles.json* ./

EXPOSE 8080

CMD ["python", "main.py"]
