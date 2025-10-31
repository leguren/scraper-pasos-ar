# --- Base ---
FROM python:3.12-slim

# --- Configuración Python ---
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# --- Directorio de trabajo ---
WORKDIR /app

# --- Copiar requirements e instalar ---
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# --- Copiar todo el código ---
COPY . .

# --- Verificar contenido (diagnóstico) ---
RUN echo "=== CONTENIDO DE /app ===" && ls -la /app \
    && if [ ! -f /app/scraper_pasos_ar.py ]; then echo "ERROR: scraper_pasos_ar.py NO ESTÁ EN /app"; exit 1; fi

# --- Puerto que Cloud Run espera ---
ENV PORT 8080
EXPOSE 8080

# --- Comando de inicio ---
CMD ["sh", "-c", "\
    echo '=== INICIANDO APLICACIÓN ===' && \
    echo 'Archivos:' && ls -la /app && \
    echo 'Probando importación...' && python -c 'import scraper_pasos_ar, sys; print(\"app:\", scraper_pasos_ar.app)' && \
    echo 'Iniciando uvicorn en puerto ${PORT}...' && \
    exec uvicorn scraper_pasos_ar:app --host 0.0.0.0 --port ${PORT} --workers 1 --log-level info \
"]
