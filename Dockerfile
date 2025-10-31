# Imagen base ligera y compatible con Cloud Run
FROM python:3.12-slim

# Directorio de trabajo
WORKDIR /app

# Copiamos dependencias primero para cache de capas
COPY requirements.txt .

# Instalamos dependencias
RUN pip install --no-cache-dir -r requirements.txt

# Copiamos el proyecto completo
COPY . .

# Puerto para Cloud Run
ENV PORT=8080

# Exponemos el puerto
EXPOSE 8080

# Comando de arranque: usa la variable de entorno $PORT
CMD ["sh", "-c", "uvicorn scraper-pasos-ar:app --host 0.0.0.0 --port $PORT --workers 1"]
