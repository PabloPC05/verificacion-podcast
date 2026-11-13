#!/usr/bin/env python3
"""Valida los datos de entrevistas/ antes de generar la web. Lo usa la comprobación automática de las PR.

Uso: python3 herramientas/comprobar_datos.py
Sale con error (y anotaciones ::error para GitHub) si algo no cuadra.
"""
import datetime as dt
import json
import os
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
VEREDICTOS = {"verdadero", "mayormente_verdadero", "enganoso", "falso", "no_verificable"}
CONFIANZAS = {"alta", "media", "baja"}
OBLIGATORIOS = ["minuto", "cita", "afirmacion", "veredicto", "explicacion", "fuentes"]
EN_CI = os.environ.get("GITHUB_ACTIONS") == "true"
errores = 0


def error(ruta, mensaje):
    global errores
    errores += 1
    rel = ruta.relative_to(RAIZ)
    print(f"::error file={rel}::{mensaje}" if EN_CI else f"ERROR {rel}: {mensaje}")


def es_fecha(texto):
    try:
        dt.date.fromisoformat(str(texto))
        return True
    except ValueError:
        return False


def leer(ruta):
    try:
        return json.loads(ruta.read_text(encoding="utf-8"))
    except (ValueError, UnicodeDecodeError) as e:
        error(ruta, f"JSON no válido: {e}")
        return None


for carpeta in sorted(p for p in (RAIZ / "entrevistas").iterdir() if p.is_dir()):
    meta = leer(carpeta / "meta.json") if (carpeta / "meta.json").exists() else None
    if meta is None:
        error(carpeta, "falta meta.json o no es válido")
        continue
    for nombre in ("segmentos.json", "capitulos.json", "transcripcion.txt"):
        if not (carpeta / nombre).exists():
            error(carpeta, f"falta {nombre}")
    for ruta in sorted((carpeta / "resultados").glob("*.json")):
        datos = leer(ruta)
        if not isinstance(datos, list):
            if datos is not None:
                error(ruta, "debe ser una lista de afirmaciones")
            continue
        for i, a in enumerate(datos):
            donde = f"elemento {i} ({a.get('minuto', '?') if isinstance(a, dict) else '?'})"
            if not isinstance(a, dict):
                error(ruta, f"{donde}: no es un objeto")
                continue
            for campo in OBLIGATORIOS:
                if campo not in a:
                    error(ruta, f"{donde}: falta el campo «{campo}»")
            if a.get("veredicto") not in VEREDICTOS:
                error(ruta, f"{donde}: veredicto «{a.get('veredicto')}» no válido ({', '.join(sorted(VEREDICTOS))})")
            if a.get("confianza") not in CONFIANZAS | {None}:
                error(ruta, f"{donde}: confianza «{a.get('confianza')}» no válida")
            for f in a.get("fuentes", []):
                if not isinstance(f, dict) or not str(f.get("url", "")).startswith(("http://", "https://")):
                    error(ruta, f"{donde}: fuente sin URL http(s): {f}")
            if "verificado" in a and not es_fecha(a["verificado"]):
                error(ruta, f"{donde}: «verificado» debe ser una fecha AAAA-MM-DD")
            for c in a.get("correcciones", []):
                if not isinstance(c, dict) or not es_fecha(c.get("fecha")) or not c.get("motivo"):
                    error(ruta, f"{donde}: cada corrección necesita «fecha» (AAAA-MM-DD) y «motivo»")
                elif c.get("antes") not in VEREDICTOS | {None}:
                    error(ruta, f"{donde}: corrección con «antes» no válido: {c.get('antes')}")
        resumen = carpeta / "resumenes" / ruta.name
        if resumen.exists():
            r = leer(resumen)
            if isinstance(r, list) and len(r) != len(datos):
                error(resumen, f"tiene {len(r)} resúmenes y resultados/{ruta.name} tiene {len(datos)} afirmaciones: "
                               "deben coincidir en número y orden")
    if "verificado" in meta and not es_fecha(meta["verificado"]):
        error(carpeta / "meta.json", "«verificado» debe ser una fecha AAAA-MM-DD")
    es = carpeta / "esencial.json"
    if es.exists():
        d = leer(es)
        xs = d.get("afirmaciones", []) if isinstance(d, dict) else []
        if d is not None and not (3 <= len(xs) <= 5 and all(isinstance(x, dict) and x.get("id") and x.get("por_que") for x in xs)):
            error(es, "«afirmaciones» debe tener de 3 a 5 elementos, cada uno con «id» y «por_que»")
    ov = carpeta / "otros_verificadores.json"
    if ov.exists():
        d = leer(ov)
        for x in d.get("enlaces", []) if isinstance(d, dict) else []:
            if not (isinstance(x, dict) and x.get("id") and x.get("medio")
                    and str(x.get("url", "")).startswith(("http://", "https://"))):
                error(ov, f"cada enlace necesita «id», «medio» y una «url» http(s): {x}")
            elif x.get("alcance") not in ("misma_frase", "mismo_dato", None):
                error(ov, f"«alcance» debe ser misma_frase o mismo_dato: {x}")
    excl = carpeta / "excluidas.json"
    if excl.exists():
        d = leer(excl)
        if d is not None and not all(isinstance(x, dict) and x.get("id") and x.get("motivo") for x in d.get("excluidas", [])):
            error(excl, "cada excluida necesita «id» y «motivo»")

print(f"{errores} errores" if errores else "Datos correctos")
sys.exit(1 if errores else 0)
