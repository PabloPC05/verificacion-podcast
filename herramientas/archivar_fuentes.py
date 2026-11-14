#!/usr/bin/env python3
"""Guarda una copia de cada fuente en la Wayback Machine (archive.org) y apunta su dirección.

Las noticias cambian o desaparecen; la copia archivada deja comprobar qué decía la fuente cuando se usó.
El resultado va a entrevistas/archivo.json: {url: {"archivo": "https://web.archive.org/web/<fecha>/<url>", "fecha": "YYYY-MM-DD"}}.
build.py lo lee y pone el enlace «copia archivada» junto a cada fuente.

Para cada URL que aún no está en archivo.json:
  1. pregunta a la API de disponibilidad si ya hay una copia (vale cualquiera desde el día de la entrevista);
  2. si no la hay, pide a «Save Page Now» que la archive.
Es reanudable: guarda después de cada fuente y se salta las que ya tienen copia. Save Page Now sin cuenta admite
pocas peticiones por minuto, así que va despacio a propósito; para miles de fuentes, déjalo en segundo plano.

Se puede hacer en dos pasadas: primero recoger las copias que ya existen (unos 25 minutos para mil fuentes) y
después pedir las que faltan (alrededor de una por minuto):

    python3 herramientas/archivar_fuentes.py --solo-consultar
    python3 herramientas/archivar_fuentes.py

Uso: python3 herramientas/archivar_fuentes.py [--solo-consultar] [--max N]
Sin dependencias.
"""
import argparse
import http.client
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
ENTREVISTAS = RAIZ / "entrevistas"
ARCHIVO = ENTREVISTAS / "archivo.json"
AGENTE = "verificacion-podcast-archivador/1.0 (+https://github.com/PabloPC05/verificacion-podcast)"
DESDE = "20261101"  # una copia anterior a la campaña no sirve: puede no recoger lo que se citó
PAUSA_GUARDAR = 12   # segundos entre peticiones a Save Page Now
PAUSA_CONSULTA = 1.2


def fuentes():
    urls = []
    for ruta in sorted(ENTREVISTAS.glob("*/resultados/*.json")):
        for a in json.loads(ruta.read_text(encoding="utf-8")):
            for f in a.get("fuentes", []) if isinstance(a, dict) else []:
                u = str(f.get("url", "")) if isinstance(f, dict) else ""
                if u.startswith(("http://", "https://")) and u not in urls:
                    urls.append(u)
    return urls


def pedir(url, metodo="GET", espera=60):
    req = urllib.request.Request(url, method=metodo, headers={"User-Agent": AGENTE})
    with urllib.request.urlopen(req, timeout=espera) as r:
        return r.status, r.geturl(), r.read()


def copia_existente(url):
    q = "https://archive.org/wayback/available?" + urllib.parse.urlencode({"url": url, "timestamp": DESDE})
    _, _, cuerpo = pedir(q, espera=30)
    snap = json.loads(cuerpo).get("archived_snapshots", {}).get("closest") or {}
    if snap.get("available") and str(snap.get("status", "200")).startswith(("2", "3")) and snap.get("timestamp", "") >= DESDE:
        return snap["url"].replace("http://", "https://", 1), snap["timestamp"]
    return None


def archivar(url):
    _, final, _ = pedir("https://web.archive.org/save/" + url, espera=120)
    # Save Page Now redirige a la copia recién hecha: https://web.archive.org/web/<timestamp>/<url>
    partes = urllib.parse.urlparse(final).path.split("/")
    if len(partes) > 2 and partes[1] == "web" and partes[2][:8].isdigit():
        return final, partes[2]
    return None


def fecha(ts):
    return f"{ts[:4]}-{ts[4:6]}-{ts[6:8]}"


def main():
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--solo-consultar", action="store_true", help="no pide copias nuevas, solo busca las que ya existen")
    p.add_argument("--max", type=int, default=0, help="como mucho N fuentes en esta pasada")
    args = p.parse_args()
    hechas = json.loads(ARCHIVO.read_text(encoding="utf-8")) if ARCHIVO.exists() else {}
    pendientes = [u for u in fuentes() if u not in hechas]
    if args.max:
        pendientes = pendientes[:args.max]
    print(f"{len(hechas)} fuentes ya archivadas, {len(pendientes)} pendientes", flush=True)
    fallos = 0
    for n, url in enumerate(pendientes, 1):
        res, err = None, None
        for intento in range(4):  # archive.org responde 429 si se le pide demasiado: se espera cada vez más y se reintenta
            try:
                res = copia_existente(url)
                time.sleep(PAUSA_CONSULTA)
                if not res and not args.solo_consultar:
                    res = archivar(url)
                    time.sleep(PAUSA_GUARDAR)
                err = None
                break
            except (urllib.error.URLError, http.client.HTTPException, TimeoutError, ValueError, OSError) as e:
                err = e
                if not (isinstance(e, urllib.error.HTTPError) and e.code == 429):
                    break
                print(f"[{n}/{len(pendientes)}] archive.org pide esperar; reintento en {60 * (intento + 1)} s", flush=True)
                time.sleep(60 * (intento + 1))
        if err:
            fallos += 1
            print(f"[{n}/{len(pendientes)}] fallo {url}: {err}", flush=True)
            continue
        if res:
            hechas[url] = {"archivo": res[0], "fecha": fecha(res[1])}
            ARCHIVO.write_text(json.dumps(dict(sorted(hechas.items())), ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
            print(f"[{n}/{len(pendientes)}] ok {url}", flush=True)
        else:
            print(f"[{n}/{len(pendientes)}] sin copia {url}", flush=True)
    print(f"Hecho: {len(hechas)} archivadas, {fallos} fallos", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
