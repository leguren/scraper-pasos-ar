FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

ENV PORT=8080

EXPOSE 8080

CMD ["uvicorn", "scraper_pasos_ar:app", "--host", "0.0.0.0", "--port", "8080", "--workers", "1"]
