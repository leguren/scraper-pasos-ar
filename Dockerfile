# Imagen base ligera y compatible con Cloud Run
FROM python:3.12-slim

# Directorio de trabajo en el contenedor
WORKDIR /app

# Copiamos las dependencias primero (para aprovechar la cache de capas)
COPY requirements.txt .

# Instalamos dependencias
RUN pip install --no-cache-dir -r requirements.txt

# Copiamos el resto del proyecto
COPY . .

# Variable de entorno para Cloud Run
ENV PORT=8080

# Exponemos el puerto
EXPOSE 8080

# Comando para ejecutar tu app FastAPI
CMD ["uvicorn", "scraper-pasos-ar:app", "--host", "0.0.0.0", "--port", "8080"]
