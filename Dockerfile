# Imagen base con Python
FROM python:3.12-slim

# Directorio de trabajo en el contenedor
WORKDIR /app

# Copiamos el archivo de dependencias y lo instalamos
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copiamos todo el proyecto al contenedor
COPY . .

# Variable de entorno para Cloud Run
ENV PORT=8080

# Comando para ejecutar tu app
CMD ["python", "scraper-pasos-ar.py"]
