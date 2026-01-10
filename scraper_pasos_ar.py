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

def convertir_schema_a_texto(schema: str) -> str:
    if not schema or not schema.strip():
        return None

    schema = schema.strip()

    # -------------------------------------------------
    # 24/7
    # -------------------------------------------------
    if "24/7" in schema:
        if re.search(r'24/7\s*off', schema, re.IGNORECASE):
            aclaraciones = re.findall(r'"([^"]+)"', schema)
            texto = ". ".join(aclaraciones) + ". Feriados cerrado." if aclaraciones else "Cerrado"
            return texto
        else:
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
        # separar aclaraciones
        aclaraciones = re.findall(r'"([^"]+)"', bloque)
        bloque_sin_aclaraciones = re.sub(r'"[^"]*"', '', bloque).strip()

        if not bloque_sin_aclaraciones and not aclaraciones:
            continue

        # PH off
        ph_off = bool(re.search(r'PH\s*off', bloque, re.IGNORECASE))

        # dividir por espacios
        tokens = bloque_sin_aclaraciones.split()
        dias_tokens = []
        horarios_tokens = []

        for t in tokens:
            if re.match(r"(Mo|Tu|We|Th|Fr|Sa|Su|PH)(-[Mo|Tu|We|Th|Fr|Sa|Su])?", t) or ',' in t:
                dias_tokens.append(t)
            elif re.match(r"\d{2}:\d{2}-\d{2}:\d{2}", t):
                horarios_tokens.append(t)

        # construir texto de días
        dias = []
        for d in dias_tokens:
            if '-' in d:  # rango Mo-Fr
                m = re.match(r"(Mo|Tu|We|Th|Fr|Sa|Su)-(Mo|Tu|We|Th|Fr|Sa|Su)", d)
                if m:
                    dias.append(f"de {dias_map[m.group(1)]} a {dias_map[m.group(2)]}")
            elif ',' in d:  # Mo,We,Fr
                subdias = d.split(',')
                nombres = [dias_map[s] for s in subdias if s in dias_map]
                if len(nombres) == 1:
                    dias.append(nombres[0])
                elif len(nombres) == 2:
                    dias.append(f"{nombres[0]} y {nombres[1]}")
                else:
                    dias.append(", ".join(nombres[:-1]) + " y " + nombres[-1])
            elif d in dias_map:  # día suelto
                dias.append(dias_map[d])
            elif d == "PH":
                continue

        # PH en texto
        texto_ph = "Feriados" if "PH" in bloque_sin_aclaraciones and not ph_off else ""
        if ph_off:
            texto_ph += " cerrado"

        # construir texto de horarios
        texto_horarios = []
        for h in horarios_tokens:
            hi, hf = h.split("-")
            texto_horarios.append(f"de {hi} a {hf}")
        texto_horarios = " y ".join(texto_horarios)

        # unir días + horarios
        bloque_texto = ""
        if dias:
            bloque_texto += " de ".join(dias) if len(dias)==1 else " y ".join(dias)
            if texto_horarios:
                bloque_texto += f" {texto_horarios}"
        else:
            bloque_texto += texto_horarios

        # agregar aclaraciones
        if aclaraciones:
            if bloque_texto:
                bloque_texto += ". "
            bloque_texto += " ".join(aclaraciones)

        # agregar PH off si corresponde
        if ph_off:
            if bloque_texto:
                bloque_texto += ". "
            bloque_texto += "Feriados cerrado."

        textos.append(bloque_texto.strip())

    if not textos:
        return None

    # unir todos los bloques
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



