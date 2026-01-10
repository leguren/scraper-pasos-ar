import os
import json
import re
from datetime import datetime, timedelta
from fastapi import FastAPI
from fastapi.responses import JSONResponse
import httpx
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


def convertir_schema_a_texto(schema):
    if not schema:
        return None

    schema_original = schema
    schema = schema.strip()

    # 24/7 off → no mostrar nada
    if "24/7" in schema and "off" in schema.lower():
        return None

    # 24/7 abierto (con texto adicional)
    if "24/7" in schema:
        return "Abierto todos los días las 24 horas."

    # eliminar todo lo que esté entre comillas
    schema = re.sub(r'"[^"]*"', '', schema)

    dias = {
        "Mo": "lunes",
        "Tu": "martes",
        "We": "miércoles",
        "Th": "jueves",
        "Fr": "viernes",
        "Sa": "sábado",
        "Su": "domingo"
    }

    incluye_feriados = "PH" in schema
    texto_dias = ""

    match_dias = re.search(r"(Mo|Tu|We|Th|Fr|Sa|Su)(?:-(Mo|Tu|We|Th|Fr|Sa|Su))?", schema)
    if match_dias:
        d1, d2 = match_dias.groups()
        if d2:
            texto_dias = f"de {dias[d1]} a {dias[d2]}"
        else:
            texto_dias = f"los {dias[d1]}"

    if incluye_feriados:
        texto_dias += " y feriados" if texto_dias else "feriados"

    rangos = re.findall(r"(\d{2}:\d{2})-(\d{2}:\d{2})", schema)
    if not rangos:
        return None

    partes = [f"de {h1} a {h2}" for h1, h2 in rangos]
    texto_horario = " y ".join(partes)

    return f"Abierto {texto_dias} {texto_horario}."


async def obtener_datos_listado():
    async with httpx.AsyncClient(
        timeout=httpx.Timeout(30.0),
        headers={
            "User-Agent": "Mozilla/5.0",
            "Accept": "application/json",
            "Accept-Language": "es-AR,es;q=0.9"
        }
    ) as client:
        resp = await client.get(LISTADO_URL)
        resp.raise_for_status()
        return resp.json()


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
    version="2.1.0",
    lifespan=lifespan
)


@app.get("/scrapear")
async def scrapear():
    if cache["data"] and cache["timestamp"] and datetime.now() - cache["timestamp"] < CACHE_TTL:
        return JSONResponse(content=cache["data"])

    listado = await obtener_datos_listado()
    index = {int(p["id"]): p for p in listado if "id" in p}

    resultado = []

    for paso in pasos_cache:
        data = index.get(int(paso["id"]))
        if not data:
            continue

        hs_a = data.get("fecha_schema")
        hs_b = data.get("fecha_schema_cancilleria")

        resultado.append({
            "id": int(paso["id"]),
            "nombre": data.get("nombre_paso"),
            "estado": data.get("estado_prioridad"),
            "provincia": data.get("provincia"),
            "pais": data.get("pais"),
            "horario_schema_a": hs_a,
            "horario_schema_b": hs_b,
            "horario_texto": convertir_schema_a_texto(hs_a)
        })

    resultado.sort(key=lambda x: x["nombre"])
    cache["data"] = resultado
    cache["timestamp"] = datetime.now()
    return JSONResponse(content=resultado)

