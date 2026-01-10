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


def normalizar_nombre(nombre: str) -> str:
    return re.sub(r"\s+", " ", nombre.strip().lower())


def convertir_schema_a_texto(schema):
    if not schema:
        return None

    schema = schema.strip()

    # -------------------------------------------------
    # 1) TEXTO NO SCHEMA → copiar literal
    # -------------------------------------------------
    if not re.search(r"(Mo|Tu|We|Th|Fr|Sa|Su|PH|24/7)", schema):
        return schema

    # -------------------------------------------------
    # eliminar aclaraciones entre comillas
    # -------------------------------------------------
    schema = re.sub(r'"[^"]*"', '', schema).strip()

    # -------------------------------------------------
    # 24/7
    # -------------------------------------------------
    if "24/7" in schema:
        if "off" in schema.lower():
            return None
        return "Abierto todos los días las 24 horas."

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

    # -------------------------------------------------
    # dividir bloques por ; o coma seguida de espacio
    # -------------------------------------------------
    bloques = [b.strip() for b in re.split(r"[;,]", schema) if b.strip()]
    textos = []

    for bloque in bloques:
        dias_encontrados = re.findall(r"(Mo|Tu|We|Th|Fr|Sa|Su)", bloque)
        dias_encontrados = list(dict.fromkeys(dias_encontrados))

        # ---- DÍAS ----
        if set(dias_encontrados) == set(dias_map.keys()):
            texto_dias = "todos los días"
        elif "-" in bloque:
            m = re.search(r"(Mo|Tu|We|Th|Fr|Sa|Su)\s*-\s*(Mo|Tu|We|Th|Fr|Sa|Su)", bloque)
            if m:
                texto_dias = f"de {dias_map[m.group(1)]} a {dias_map[m.group(2)]}"
            else:
                nombres = [dias_map[d] for d in dias_encontrados]
                texto_dias = ", ".join(nombres[:-1]) + " y " + nombres[-1] if nombres else ""
        else:
            nombres = [dias_map[d] for d in dias_encontrados]
            if len(nombres) == 1:
                texto_dias = f"los {nombres[0]}"
            elif len(nombres) == 2:
                texto_dias = f"{nombres[0]} y {nombres[1]}"
            else:
                texto_dias = ", ".join(nombres[:-1]) + " y " + nombres[-1]

        if incluye_feriados:
            texto_dias += " y feriados"

        # ---- HORARIOS ----
        rangos = re.findall(r"(\d{2}:\d{2})-(\d{2}:\d{2})", bloque)
        if not rangos:
            continue

        partes = [f"de {h1} a {h2}" for h1, h2 in rangos]
        texto_horario = " y ".join(partes)

        textos.append(f"{texto_dias} {texto_horario}".strip())

    if not textos:
        return None

    if len(textos) == 1:
        return f"Abierto {textos[0]}."
    else:
        return "Abierto " + ". ".join(textos) + "."


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

    # ---- índice por nombre del paso ----
    index = {
        normalizar_nombre(p["nombre_paso"]): p
        for p in listado
        if p.get("nombre_paso")
    }

    resultado = []

    for paso in pasos_cache:
        nombre_norm = normalizar_nombre(paso["nombre"])
        data = index.get(nombre_norm)

        if not data:
            continue

        # ---- prioridad: cancillería primero, luego schema original ----
        hs_canc = data.get("fecha_schema_cancilleria")
        hs_a = data.get("fecha_schema")
        horario_texto = convertir_schema_a_texto(hs_canc or hs_a)

        resultado.append({
            "id": int(paso["id"]),
            "nombre": data.get("nombre_paso"),
            "estado": data.get("estado_prioridad"),
            "provincia": data.get("provincia"),
            "pais": data.get("pais"),
            "horario_schema_a": hs_a,
            "horario_schema_b": hs_canc,
            "horario_texto": horario_texto
        })

    resultado.sort(key=lambda x: x["nombre"])
    cache["data"] = resultado
    cache["timestamp"] = datetime.now()
    return JSONResponse(content=resultado)
