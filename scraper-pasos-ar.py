import os
import json
from flask import Flask, jsonify
import requests
from bs4 import BeautifulSoup
from concurrent.futures import ThreadPoolExecutor, as_completed

app = Flask(__name__)

# === CARGAR PASOS DESDE ARCHIVO LOCAL (en el contenedor) ===
PASOS_FILE = "9b4a7f2c.json"  # ← Debe estar en el mismo directorio que el script

def cargar_pasos():
    try:
        with open(PASOS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        print(f"Error: {PASOS_FILE} no encontrado en el contenedor")
        return []
    except json.JSONDecodeError as e:
        print(f"Error JSON: {e}")
        return []

# === FUNCIÓN DE SCRAPING ===
def obtener_estado(paso):
    url = paso["url"]
    try:
        resp = requests.get(url, timeout=15, headers={"User-Agent": "Mozilla/5.0"})
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")

        # Estado
        estado_span = soup.select_one("span.label.label-danger, span.label.label-success")
        estado = estado_span.get_text(strip=True) if estado_span else None

        # Última actualización
        actualizacion_div = soup.select_one("div.text-muted.m-t-3.lead")
        texto_actualizacion = actualizacion_div.get_text(strip=True) if actualizacion_div else None
        ultima_actualizacion = texto_actualizacion.replace(estado, "").strip() if texto_actualizacion and estado else texto_actualizacion

        # Localidades
        localidades = soup.select_one("h2 > small")
        localidades_text = localidades.get_text(strip=True) if localidades else None

        # Horario
        horario = None
        for p in soup.find_all("p"):
            strong = p.find("strong")
            if strong and "Horarios de atención" in strong.get_text():
                sibling = strong.next_sibling
                if sibling and isinstance(sibling, str):
                    horario = sibling.strip()
                break

        return {
            "nombre": paso["nombre"],
            "url": url,
            "estado": estado,
            "ultima_actualizacion": ultima_actualizacion,
            "localidades": localidades_text,
            "horario": horario
        }
    except Exception as e:
        return {
            "nombre": paso["nombre"],
            "url": url,
            "estado": None,
            "ultima_actualizacion": None,
            "localidades": None,
            "horario": None,
            "error": str(e)
        }

# === RUTA PRINCIPAL: devuelve todos los pasos scrapeados ===
@app.route("/scrapear", methods=["GET"])
def scrapear_todos():
    pasos = cargar_pasos()
    if not pasos:
        return jsonify({"error": "No se pudieron cargar los pasos"}), 500

    resultados = []
    with ThreadPoolExecutor(max_workers=20) as executor:
        futures = {executor.submit(obtener_estado, paso): paso for paso in pasos}
        for future in as_completed(futures):
            resultados.append(future.result())

    resultados.sort(key=lambda x: x["nombre"])

    return jsonify(resultados)  # ✅ Devuelve directamente el JSON

# === HEALTH CHECK ===
@app.route("/")
def health():
    return "OK", 200

# === INICIO ===
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)
