FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# DIAGNÓSTICO
RUN echo "=== CONTENIDO DE /app ===" && ls -la /app

# Verificar que el archivo existe
RUN if [ ! -f /app/scraper_pasos_ar.py ]; then \
    echo "ERROR: scraper_pasos_ar.py NO ESTÁ EN /app"; exit 1; \
    fi

EXPOSE 8080

# CMD con logs completos
CMD ["sh", "-c", "\
    echo '=== INICIANDO APLICACIÓN ===' && \
    echo 'Archivos:' && ls -la /app && \
    echo 'Probando importación...' && \
    python -c 'import scraper_pasos_ar, sys; print(\"app:\", scraper_pasos_ar.app)' && \
    echo 'Iniciando uvicorn en puerto ${PORT}...' && \
    exec uvicorn scraper_pasos_ar:app --host 0.0.0.0 --port ${PORT} --workers 1 --log-level info\
"]
