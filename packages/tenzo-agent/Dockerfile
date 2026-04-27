FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY tenzo_agent.py .
COPY onchain_bridge.py .
COPY task_parser.py .
COPY genlayer_bridge.py .
ENV PORT=8080
EXPOSE 8080
CMD ["python", "tenzo_agent.py"]
