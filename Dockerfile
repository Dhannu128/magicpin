FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PORT=8080

WORKDIR /app

COPY requirements.txt /app/
RUN pip install --no-cache-dir -r requirements.txt

COPY bot /app/bot
COPY dataset /app/dataset
COPY judge_simulator.py /app/judge_simulator.py

EXPOSE 8080

CMD ["sh", "-c", "uvicorn bot.main:app --host 0.0.0.0 --port ${PORT:-8080}"]
