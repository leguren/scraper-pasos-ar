import os
import json
import asyncio
from datetime import datetime, timedelta
from fastapi import FastAPI
from fastapi.responses import JSONResponse
import httpx
from bs4 import BeautifulSoup
from contextlib import asynccontextmanager

PASOS_FILE = "9b4a7f2c.json"

CACHE_TTL = timedelta(minutes=15)
cache = {"data": None, "timestamp": None}

pasos_cache = []

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

async def obtener_estado(paso):
    url = paso["url"]
    async with httpx.AsyncClient(
        timeout=httpx.Timeout(30.0),
        headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
            "Accept-Language": "es-AR,es;q=0.9",
            "Connection": "keep-alive",
        },
        follow_redirects=True
    ) as client:
        try:
            resp = await client.get(url)
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, "html.parser")

            # estado
            estado_div = soup.select_one("#estado")
            estado = estado_div.get_text(strip=True) if estado_div else None

            # última actualización
            ultima_actualizacion = None
            for li in soup.find_all("li"):
                texto = li.get_text(strip=True)
                if "última actualización" in texto:
                    ultima_actualizacion = texto
                    break

            # localidades
            localidades = soup.select_one("h3 small")
            localidades_text = localidades.get_text(" ", strip=True) if localidades else None

            # horario (pendiente)
            horario = None

            # provincia y país limítrofe
            provincia = None
            pais = None
            lado_p = soup.select_one("p.lado")
            if lado_p:
                texto = lado_p.get_text(" ", strip=True)
                if "Lado argentino:" in texto:
                    provincia = texto.split("Lado argentino:")[1].split("|")[0].strip()
                if "País limítrofe:" in texto:
                    pais = texto.split("País limítrofe:")[1].strip()

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

@asynccontextmanager
async def lifespan(app: FastAPI):
    global pasos_cache
    pasos_cache = cargar_pasos()
    if not pasos_cache:
        print("[WARNING] No se cargaron pasos. El endpoint /scrapear devolverá error.")
    yield

    pasos_cache.clear()
    cache["data"] = None
    cache["timestamp"] = None

app = FastAPI(
    title="Scraper Pasos AR",
    description="API para obtener el estado de los pasos internacionales de Argentina",
    version="1.0.0",
    lifespan=lifespan
)

@app.get("/", response_model=dict)
async def health():
    return {
        "status": "healthy",
        "pasos_cargados": len(pasos_cache),
        "cache_ttl_minutes": 15,
        "timestamp": datetime.now().isoformat()
    }

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

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8080))
    uvicorn.run("scraper_pasos_ar:app", host="0.0.0.0", port=port, log_level="info")
