# Imagen base ligera
FROM python:3.12-slim

# Evita interacciones durante instalación
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Directorio de trabajo
WORKDIR /app

# Copia solo requirements primero (mejora caché de capas)
COPY requirements.txt .

# Instala dependencias
RUN pip install --no-cache-dir -r requirements.txt

# Copia el resto del código
COPY . .

# Expone el puerto (documentación)
EXPOSE 8080

# Usa la variable PORT inyectada por Cloud Run
# ${PORT} se expande en tiempo de ejecución
CMD exec uvicorn scraper_pasos_ar:app \
    --host 0.0.0.0 \
    --port ${PORT} \
    --workers 1 \
    --log-level info
    
