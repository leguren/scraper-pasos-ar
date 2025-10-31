# Imagen base ligera
FROM python:3.12-slim

# Instalar dependencias de sistema necesarias
RUN apt-get update && apt-get install -y build-essential libffi-dev libssl-dev && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copiar requirements e instalar
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copiar código
COPY . .

# Puerto
ENV PORT=8080
EXPOSE 8080

# CMD optimizado para Cloud Run
CMD ["uvicorn", "scraper-pasos-ar:app", "--host", "0.0.0.0", "--port", "8080", "--workers", "1"]
