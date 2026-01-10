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


def convertir_schema_a_texto(schema: str) -> str | None:
    """
    Convierte un horario en formato schema a texto legible.
    - Usa el campo horario_schema_b (cancillería)
    - Maneja 24/7, PH feriados, días corridos o separados por comas, rangos horarios múltiples.
    - Mantiene las aclaraciones entre comillas como notas.
    """
    if not schema:
        return None

    schema = schema.strip()

    # -------------------------------------------------
    # 24/7 OFF → cerrado
    # 24/7 OPEN → abierto todos los días las 24 hs
    # -------------------------------------------------
    if "24/7" in schema:
        if "off" in schema.lower():
            # extraemos texto entre comillas si existe
            aclaraciones = re.findall(r'"([^"]+)"', schema)
            if aclaraciones:
                return ". ".join(aclaraciones)
            return "Cerrado"
        # abierto todos los días las 24 horas
        texto = "Abierto todos los días las 24 horas."
        aclaraciones = re.findall(r'"([^"]+)"', schema)
        if aclaraciones:
            texto += " " + " ".join(aclaraciones)
        return texto

    # -------------------------------------------------
    # Dividir bloques por ";" (diferentes días) 
    # o por punto y coma
    # -------------------------------------------------
    bloques = [b.strip() for b in schema.split(";") if b.strip()]
    dias_map = {
        "Mo": "lunes",
        "Tu": "martes",
        "We": "miércoles",
        "Th": "jueves",
        "Fr": "viernes",
        "Sa": "sábado",
        "Su": "domingo"
    }

    textos = []

    for bloque in bloques:
        # extraemos aclaraciones entre comillas
        aclaraciones = re.findall(r'"([^"]+)"', bloque)
        bloque_sin_aclaraciones = re.sub(r'"[^"]*"', '', bloque).strip()

        # detectamos si PH está presente
        incluye_feriados = "PH" in bloque_sin_aclaraciones

        # extraemos días
        # soporta rangos (Mo-Fr) o separados por comas (Mo,We,Fr)
        dias_raw = re.findall(r"(Mo|Tu|We|Th|Fr|Sa|Su)", bloque_sin_aclaraciones)
        dias_raw = list(dict.fromkeys(dias_raw))  # elimina duplicados manteniendo orden

        # ---- convertir días a texto ----
        texto_dias = ""
        if set(dias_raw) == set(dias_map.keys()):
            texto_dias = "todos los días"
        elif "-" in bloque_sin_aclaraciones:
            m = re.search(r"(Mo|Tu|We|Th|Fr|Sa|Su)\s*-\s*(Mo|Tu|We|Th|Fr|Sa|Su)", bloque_sin_aclaraciones)
            if m:
                texto_dias = f"de {dias_map[m.group(1)]} a {dias_map[m.group(2)]}"
        elif dias_raw:
            nombres = [dias_map[d] for d in dias_raw]
            if len(nombres) == 1:
                texto_dias = f"{nombres[0]}"
            elif len(nombres) == 2:
                texto_dias = f"{nombres[0]} y {nombres[1]}"
            else:
                texto_dias = ", ".join(nombres[:-1]) + " y " + nombres[-1]

        if incluye_feriados:
            texto_dias += " y feriados" if texto_dias else "feriados"

        # ---- extraer horarios ----
        rangos = re.findall(r"(\d{2}:\d{2})-(\d{2}:\d{2})", bloque_sin_aclaraciones)
        texto_horario = ""
        if rangos:
            partes = [f"de {h1} a {h2}" for h1, h2 in rangos]
            texto_horario = " y ".join(partes)

        # armar bloque final
        bloque_final = ""
        if texto_dias and texto_horario:
            bloque_final = f"{texto_dias} {texto_horario}"
        elif texto_horario:
            bloque_final = texto_horario
        elif texto_dias:
            bloque_final = texto_dias

        # agregar aclaraciones literales si existen
        if aclaraciones:
            bloque_final += ". " + " ".join(aclaraciones)

        textos.append(bloque_final.strip())

    # unir todos los bloques
    if not textos:
        return None
    return "Abierto " + ". ".join(textos) + "."


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

        # ---- prioridad: cancillería primero
        hs_canc = data.get("fecha_schema_cancilleria")
        hs_a = data.get("fecha_schema")

        resultado.append({
            "id": int(paso["id"]),
            "nombre": data.get("nombre_paso"),
            "estado": data.get("estado_prioridad"),
            "provincia": data.get("provincia"),
            "pais": data.get("pais"),
            "horario_schema_a": hs_a,
            "horario_schema_b": hs_canc,
            "horario_texto": convertir_schema_a_texto(hs_canc)  # usamos horario_schema_b
        })

    resultado.sort(key=lambda x: x["nombre"])
    cache["data"] = resultado
    cache["timestamp"] = datetime.now()
    return JSONResponse(content=resultado)
