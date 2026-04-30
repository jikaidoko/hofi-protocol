FROM python:3.12-slim
WORKDIR /app

# ffmpeg necesario para que faster-whisper decodifique webm/oga del browser/Telegram
RUN apt-get update && \
    apt-get install -y --no-install-recommends ffmpeg && \
    rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Pre-descargar modelo faster-whisper base (~150MB) para evitar cold start
# en la primera request a /evaluar-voz.
RUN python -c "from faster_whisper import WhisperModel; WhisperModel('base', device='cpu', compute_type='int8'); print('faster-whisper base OK')"

COPY tenzo_agent.py .
COPY onchain_bridge.py .
COPY task_parser.py .
COPY genlayer_bridge.py .
ENV PORT=8080
EXPOSE 8080
CMD ["python", "tenzo_agent.py"]
