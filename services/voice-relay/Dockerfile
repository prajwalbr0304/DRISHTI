FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
WORKDIR /app
COPY services/voice-relay/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt && useradd --uid 10001 --create-home relay
COPY services/ml/app/sonic_stream.py ./sonic_stream.py
COPY services/voice-relay/relay.py ./relay.py
USER relay
EXPOSE 8080
CMD ["uvicorn", "relay:app", "--host", "0.0.0.0", "--port", "8080", "--no-access-log", "--ws-max-size", "16384", "--ws-max-queue", "16"]
