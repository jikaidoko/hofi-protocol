FROM python:3.11-slim

WORKDIR /app

# ffmpeg necesario para que Whisper decodifique .oga de Telegram
RUN apt-get update && \
    apt-get install -y --no-install-recommends ffmpeg && \
    rm -rf /var/lib/apt/lists/*

# Instalar dependencias Python
COPY requirements.txt .
RUN pip install --upgrade pip --no-cache-dir && \
    pip install --no-cache-dir -r requirements.txt

# Pre-descargar el modelo faster-whisper base (~150MB) para evitar cold start
RUN python -c "from faster_whisper import WhisperModel; WhisperModel('base', device='cpu', compute_type='int8'); print('faster-whisper base OK')"

# Verificar librosa (pitch extraction para voice biometrics)
RUN python -c "import librosa; import numpy as np; print('librosa OK:', librosa.__version__)"

# Copiar código fuente
COPY bot.py .
COPY voice_auth.py .
COPY db.py .
COPY mock_profiles.json .

# Puerto que Cloud Run espera (webhook mode)
EXPOSE 8080

CMD ["python", "bot.py"]