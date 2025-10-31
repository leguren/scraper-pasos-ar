# Imagen base ligera
FROM python:3.12-slim

# Directorio de trabajo
WORKDIR /app

# Copiamos dependencias primero para cache de capas
COPY requirements.txt .

# Instalamos dependencias
RUN pip install --no-cache-dir -r requirements.txt

# Copiamos todo el proyecto
COPY . .

# Variable de entorno para Cloud Run
ENV PORT=8080

# Exponer puerto
EXPOSE 8080

# Comando para arrancar FastAPI con uvicorn, puerto dinámico
CMD ["sh", "-c", "uvicorn scraper-pasos-ar:app --host 0.0.0.0 --port $PORT --loop asyncio --http h11 --workers 1"]
