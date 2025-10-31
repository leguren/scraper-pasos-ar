import os
import json
import asyncio
from datetime import datetime, timedelta
from fastapi import FastAPI
from fastapi.responses import JSONResponse
import httpx
from bs4 import BeautifulSoup
from contextlib import asynccontextmanager

# --- Archivo de pasos ---
PASOS_FILE = "9b4a7f2c.json"

# --- CACHE ---
CACHE_TTL = timedelta(minutes=15)
cache = {"data": None, "timestamp": None}

# --- Variable global para pasos precargados ---
pasos_cache = []

# --- Cargar pasos locales ---
def cargar_pasos():
    try:
        with open(PASOS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            print(f"[Startup] Cargados {len(data)} pasos desde {PASOS_FILE}")
            return data
    except FileNotFoundError:
        print(f"[ERROR] Archivo {PASOS_FILE} no encontrado.")
        return []
    except json.JSONDecodeError as e:
        print(f"[ERROR] JSON inválido en {PASOS_FILE}: {e}")
        return []
    except Exception as e:
        print(f"[ERROR] Error cargando pasos: {e}")
        return []

# --- Función de scraping asincrónica ---
async def obtener_estado(paso):
    url = paso["url"]
    async with httpx.AsyncClient(timeout=15, headers={"User-Agent": "Mozilla/5.0"}) as client:
        try:
            resp = await client.get(url)
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
            for p_tag in soup.find_all("p"):
                strong = p_tag.find("strong")
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
                "provincia": None,
                "pais": None,
                "estado": None,
                "ultima_actualizacion": None,
                "localidades": None,
                "horario": None,
                "error": str(e)
            }

# --- Lifespan: carga inicial ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    global pasos_cache
    pasos_cache = cargar_pasos()
    if not pasos_cache:
        print("[WARNING] No se cargaron pasos. El endpoint /scrapear devolverá error.")
    yield
    # Limpieza al apagar
    pasos_cache.clear()
    cache["data"] = None
    cache["timestamp"] = None

# --- App con lifespan ---
app = FastAPI(
    title="Scraper Pasos AR",
    description="API para obtener estado de pasos fronterizos",
    version="1.0.0",
    lifespan=lifespan
)

# --- Health check rápido ---
@app.get("/", response_model=dict)
async def health():
    return {
        "status": "healthy",
        "pasos_cargados": len(pasos_cache),
        "cache_ttl_minutes": 15,
        "timestamp": datetime.now().isoformat()
    }

# --- Endpoint principal ---
@app.get("/scrapear")
async def scrapear_todos():
    # Revisar cache
    if cache["data"] and cache["timestamp"] and datetime.now() - cache["timestamp"] < CACHE_TTL:
        return JSONResponse(content=cache["data"])

    if not pasos_cache:
        return JSONResponse(
            content={"error": "No se pudieron cargar los pasos base. Revisa logs."},
            status_code=500
        )

    print(f"[Scraping] Iniciando scraping de {len(pasos_cache)} pasos...")
    resultados = await asyncio.gather(*(obtener_estado(p) for p in pasos_cache))
    resultados.sort(key=lambda x: x["nombre"])

    # Actualizar cache
    cache["data"] = resultados
    cache["timestamp"] = datetime.now()

    print(f"[Scraping] Completado. {len(resultados)} resultados.")
    return JSONResponse(content=resultados)

# --- Bloque para ejecución local ---
if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8080))
    uvicorn.run("scraper_pasos_ar:app", host="0.0.0.0", port=port, log_level="info")

