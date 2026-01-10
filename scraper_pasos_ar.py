import os
import json
from datetime import datetime, timedelta
from fastapi import FastAPI
from fastapi.responses import JSONResponse
import httpx
from bs4 import BeautifulSoup
from contextlib import asynccontextmanager

PASOS_FILE = "9b4a7f2c.json"
LISTADO_URL = "https://www.argentina.gob.ar/seguridad/pasosinternacionales/listado"

CACHE_TTL = timedelta(minutes=15)
cache = {"data": None, "timestamp": None}

pasos_cache = []


def cargar_pasos():
    try:
        with open(PASOS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            print(f"[Startup] Cargados {len(data)} pasos desde {PASOS_FILE}")
            return data
    except Exception as e:
        print(f"[ERROR] No se pudieron cargar los pasos: {e}")
        return []


async def obtener_datos_listado():
    async with httpx.AsyncClient(
        timeout=httpx.Timeout(30.0),
        headers={
            "User-Agent": "Mozilla/5.0",
            "Accept-Language": "es-AR,es;q=0.9"
        }
    ) as client:
        resp = await client.get(LISTADO_URL)
        resp.raise_for_status()

        soup = BeautifulSoup(resp.text, "html.parser")

        script = soup.find("script", string=lambda t: t and "nombre_paso" in t)
        if not script:
            raise RuntimeError("No se encontró el dataset embebido en el listado")

        texto = script.string
        inicio = texto.find("[")
        fin = texto.rfind("]") + 1

        return json.loads(texto[inicio:fin])


@asynccontextmanager
async def lifespan(app: FastAPI):
    global pasos_cache
    pasos_cache = cargar_pasos()
    yield
    pasos_cache.clear()
    cache["data"] = None
    cache["timestamp"] = None


app = FastAPI(
    title="Pasos Internacionales AR",
    description="API basada en el listado oficial de pasos internacionales",
    version="2.0.0",
    lifespan=lifespan
)


@app.get("/")
async def health():
    return {
        "status": "healthy",
        "pasos_base": len(pasos_cache),
        "cache_ttl_minutes": 15,
        "timestamp": datetime.now().isoformat()
    }


@app.get("/scrapear")
async def scrapear():
    if cache["data"] and cache["timestamp"] and datetime.now() - cache["timestamp"] < CACHE_TTL:
        return JSONResponse(content=cache["data"])

    if not pasos_cache:
        return JSONResponse(
            content={"error": "No hay pasos base cargados"},
            status_code=500
        )

    try:
        listado = await obtener_datos_listado()
    except Exception as e:
        return JSONResponse(
            content={"error": f"Error obteniendo listado: {e}"},
            status_code=502
        )

    index = {int(p["id"]): p for p in listado}

    resultado = []

    for paso in pasos_cache:
        paso_id = int(paso["id"])
        data = index.get(paso_id)

        if not data:
            continue

        resultado.append({
            "id": paso_id,
            "nombre": data.get("nombre_paso"),
            "estado": data.get("estado_prioridad"),
            "provincia": data.get("provincia"),
            "pais_limitrofe": data.get("pais"),
            "horario": data.get("fecha_schema")
        })

    resultado.sort(key=lambda x: x["nombre"])

    cache["data"] = resultado
    cache["timestamp"] = datetime.now()

    return JSONResponse(content=resultado)


if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8080))
    uvicorn.run(
        "scraper_pasos_ar:app",
        host="0.0.0.0",
        port=port,
        log_level="info"
    )
