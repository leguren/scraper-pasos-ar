FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Forzar copia del JSON
COPY 9b4a7f2c.json /app/9b4a7f2c.json

COPY . .

# Debug: listar archivos
RUN echo "=== CONTENIDO DE /app ===" && ls -la /app

EXPOSE 8080

CMD ["sh", "-c", "echo 'PUERTO: ${PORT}' && echo 'Iniciando uvicorn...' && exec uvicorn scraper_pasos_ar:app --host 0.0.0.0 --port ${PORT} --workers 1 --log-level info"]
