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

    schema = schema.strip()

    # 24/7 off → no mostrar nada
    if "24/7" in schema and "off" in schema.lower():
        return None

    # 24/7 abierto
    if "24/7" in schema:
        return "Abierto todos los días las 24 horas."

    # eliminar aclaraciones entre comillas (schema impuro)
    schema = re.sub(r'"[^"]*"', '', schema)

    dias_map = {
        "Mo": "lunes",
        "Tu": "martes",
        "We": "miércoles",
        "Th": "jueves",
        "Fr": "viernes",
        "Sa": "sábado",
        "Su": "domingo"
    }

    incluye_feriados = "PH" in schema

    # ---- DÍAS ----
    texto_dias = ""

    # 1) lista separada por comas: Mo,We,Fr
    lista_dias = re.findall(r"(Mo|Tu|We|Th|Fr|Sa|Su)", schema)

    if lista_dias:
        # eliminar duplicados manteniendo orden
        vistos = []
        for d in lista_dias:
            if d not in vistos:
                vistos.append(d)

        # todos los días
        if set(vistos) == set(dias_map.keys()):
            texto_dias = "todos los días"
        # rango corrido Mo-Su, Mo-Fr, etc.
        elif "-" in schema:
            match_rango = re.search(
                r"(Mo|Tu|We|Th|Fr|Sa|Su)\s*-\s*(Mo|Tu|We|Th|Fr|Sa|Su)",
                schema
            )
            if match_rango:
                d1, d2 = match_rango.groups()
                texto_dias = f"de {dias_map[d1]} a {dias_map[d2]}"
        # lista no corrida
        else:
            nombres = [dias_map[d] for d in vistos]
            if len(nombres) == 1:
                texto_dias = f"los {nombres[0]}"
            elif len(nombres) == 2:
                texto_dias = f"{nombres[0]} y {nombres[1]}"
            else:
                texto_dias = ", ".join(nombres[:-1]) + " y " + nombres[-1]

    if incluye_feriados:
        texto_dias += " y feriados" if texto_dias else "feriados"

    # ---- HORARIOS ----
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

        resultado.append({
            "id": int(paso["id"]),
            "nombre": data.get("nombre_paso"),
            "estado": data.get("estado_prioridad"),
            "provincia": data.get("provincia"),
            "pais": data.get("pais"),
            "horario_schema_a": data.get("fecha_schema"),
            "horario_schema_b": data.get("fecha_schema_cancilleria"),
            "horario_texto": convertir_schema_a_texto(data.get("fecha_schema"))
        })

    resultado.sort(key=lambda x: x["nombre"])
    cache["data"] = resultado
    cache["timestamp"] = datetime.now()
    return JSONResponse(content=resultado)

