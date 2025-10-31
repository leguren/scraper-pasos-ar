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

# --- Copiar JSON de pasos ---
COPY 9b4a7f2c.json .

# --- Puerto que Cloud Run espera ---
ENV PORT 8080
EXPOSE 8080

# --- Comando de inicio ---
CMD ["uvicorn", "scraper_pasos_ar:app", "--host", "0.0.0.0", "--port", "8080", "--workers", "1", "--log-level", "info"]
