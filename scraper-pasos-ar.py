import os
import json
import httpx
from fastapi import FastAPI
from bs4 import BeautifulSoup
from concurrent.futures import ThreadPoolExecutor, as_completed

app = FastAPI()

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


def obtener_estado(paso):
    url = paso["url"]
    try:
        resp = httpx.get(url, timeout=15)
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

        # Provincia
        provincia = None
        strong_prov = soup.find('strong', string=lambda t: t and 'Provincia:' in t)
        if strong_prov:
            p_padre = strong_prov.find_parent('p')
            if p_padre:
                provincia = p_padre.get_text(strip=True).replace('Provincia:', '').strip()

        # País limítrofe
        pais = None
        strong_pais = soup.find('strong', string=lambda t: t and 'País limítrofe:' in t)
        if strong_pais:
            p_padre = strong_pais.find_parent('p')
            if p_padre:
                pais = p_padre.get_text(strip=True).replace('País limítrofe:', '').strip()

        return {
            "nombre": paso["nombre"],
            "url": url,
            "provincia": provincia,
            "pais": pais,
            "estado": estado,
            "ultima_actualizacion": ultima_actualizacion,
            "localidades": localidades_text,
            "horario": horario
        }
    except Exception as e:
        return {
            "nombre": paso["nombre"],
            "url": url,
            "error": str(e)
        }


@app.get("/scrapear")
async def scrapear_todos():
    pasos = cargar_pasos()
    if not pasos:
        return {"error": "No se pudieron cargar los pasos"}

    resultados = []
    with ThreadPoolExecutor(max_workers=30) as executor:
        futures = {executor.submit(obtener_estado, paso): paso for paso in pasos}
        for future in as_completed(futures):
            resultados.append(future.result())

    resultados.sort(key=lambda x: x["nombre"])
    return resultados


@app.get("/")
async def health():
    return {"status": "ok"}
