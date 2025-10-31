# Imagen base ligera
FROM python:3.12-slim

# Directorio de trabajo
WORKDIR /app

# Copiamos dependencias primero para aprovechar cache de capas
COPY requirements.txt .

# Instalamos dependencias
RUN pip install --no-cache-dir -r requirements.txt

# Copiamos todo el proyecto
COPY . .

# Variable de entorno que usa Cloud Run
ENV PORT=8080

# Exponemos el puerto
EXPOSE 8080

# Comando de arranque con Uvicorn, leyendo el puerto desde $PORT
CMD ["uvicorn", "scraper-pasos-ar:app", "--host", "0.0.0.0", "--port", "8080", "--workers", "1"]
