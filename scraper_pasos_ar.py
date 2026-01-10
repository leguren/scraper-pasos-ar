from typing import Optional
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


def convertir_schema_a_texto(schema: Optional[str]) -> Optional[str]:
    if not schema:
        return None
    schema = schema.strip()
    if not schema:
        return None

    # ---- 24/7 OFF / OPEN ----
    if "24/7" in schema:
        if "off" in schema.lower():
            aclaraciones = re.findall(r'"([^"]+)"', schema)
            return ". ".join(aclaraciones) + ". Feriados cerrado." if aclaraciones else "Cerrado"
        texto = "Abierto todos los días las 24 horas."
        aclaraciones = re.findall(r'"([^"]+)"', schema)
        if aclaraciones:
            texto += " " + " ".join(aclaraciones)
        return texto

    dias_map = {
        "Mo": "lunes", "Tu": "martes", "We": "miércoles",
        "Th": "jueves", "Fr": "viernes", "Sa": "sábado", "Su": "domingo"
    }

    bloques = [b.strip() for b in schema.split(";") if b.strip()]
    textos = []

    for bloque in bloques:
        # separar aclaraciones entre comillas
        aclaraciones = re.findall(r'"([^"]+)"', bloque)
        bloque_sin_aclaraciones = re.sub(r'"[^"]*"', '', bloque).strip()
        if not bloque_sin_aclaraciones and not aclaraciones:
            continue

        # detectar si incluye feriados
        incluye_feriados = "PH" in bloque_sin_aclaraciones or "PH" in bloque

        # separar días y horarios
        partes = bloque_sin_aclaraciones.split()
        dias_raw = []
        rangos = []

        for p in partes:
            if re.match(r"(Mo|Tu|We|Th|Fr|Sa|Su|PH)", p):
                dias_raw.extend(p.split(","))
            elif re.match(r"\d{2}:\d{2}-\d{2}:\d{2}", p):
                rangos.append(p)

        dias_raw = [d for d in dias_raw if d in dias_map or d == "PH"]
        texto_dias = ""
        if dias_raw:
            dias_trad = []
            for d in dias_raw:
                if d == "PH":
                    continue
                dias_trad.append(dias_map[d])
            if len(dias_trad) == 1:
                texto_dias = dias_trad[0]
            elif len(dias_trad) == 2:
                texto_dias = dias_trad[0] + " y " + dias_trad[1]
            else:
                texto_dias = ", ".join(dias_trad[:-1]) + " y " + dias_trad[-1]

        if incluye_feriados:
            if texto_dias:
                texto_dias += " y feriados"
            else:
                texto_dias = "Feriados"

        # convertir horarios
        texto_horario = " y ".join(["de {} a {}".format(*h.split("-")) for h in rangos]) if rangos else ""

        # construir bloque final
        bloque_final = ""
        if texto_dias and texto_horario:
            bloque_final = "{} de {}".format(texto_dias, texto_horario)
        elif texto_horario:
            bloque_final = texto_horario
        elif texto_dias:
            bloque_final = texto_dias

        # añadir aclaraciones literales
        if aclaraciones:
            if bloque_final:
                bloque_final += ". "
            bloque_final += " ".join(aclaraciones)

        # si PH estaba solo y off
        if re.search(r'PH\s*off', bloque, re.IGNORECASE):
            if bloque_final:
                bloque_final += ". "
            bloque_final += "Feriados cerrado."

        textos.append(bloque_final.strip())

    if not textos:
        return None

    return "Abierto " + ". ".join(textos) + "."

async def obtener_datos_listado():
    try:
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
    except Exception as e:
        print(f"[ERROR] No se pudieron obtener los datos del listado: {e}")
        return []


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
    index = {normalizar_nombre(p["nombre_paso"]): p for p in listado if p.get("nombre_paso")}

    resultado = []

    for paso in pasos_cache:
        nombre_norm = normalizar_nombre(paso["nombre"])
        data = index.get(nombre_norm)
        if not data:
            continue

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
            "horario_texto": convertir_schema_a_texto(hs_canc)  # usamos cancillería
        })

    resultado.sort(key=lambda x: x["nombre"])
    cache["data"] = resultado
    cache["timestamp"] = datetime.now()
    return JSONResponse(content=resultado)

