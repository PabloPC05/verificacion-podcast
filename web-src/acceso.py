#!/usr/bin/env python3
"""Mira qué fuentes se pueden leer en el visor de la web y lo guarda en web-src/acceso.json.

El visor enseña solo el texto de la fuente, sacado con el lector gratuito r.jina.ai, y un enlace a la original.
Por cada URL se comprueba una sola vez (queda en caché) si el lector devuelve texto de verdad y no una página de
error (un 403 de un CDN, el «Just a moment…» de Cloudflare). Las que no, abren en pestaña nueva como siempre.

Uso: python3 web-src/acceso.py            comprueba las fuentes que falten
     python3 web-src/acceso.py --repasar  vuelve a mirar las que no se pudieron leer
Sin dependencias. r.jina.ai sin clave admite 20 peticiones por minuto, así que muchas fuentes nuevas tardan.
"""
import concurrent.futures as cf
import datetime as dt
import json
import re
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
CACHE = RAIZ / "web-src" / "acceso.json"
# Lo mismo que descarta el visor: páginas de error que el lector trae como si fueran el artículo.
ERROR = re.compile(r"^(\d{3}\b|the request could not be satisfied|access denied|just a moment|attention required|"
                   r"forbidden|not found|página no encontrada|error)", re.I)


class Ritmo:
    """Deja pasar como mucho n peticiones por minuto, repartidas."""
    def __init__(self, por_minuto):
        self.hueco, self.siguiente, self.lock = 60 / por_minuto, 0.0, threading.Lock()

    def esperar(self):
        with self.lock:
            ahora = time.monotonic()
            t = max(ahora, self.siguiente)
            self.siguiente = t + self.hueco
        time.sleep(max(0, t - ahora))


JINA = Ritmo(19)


def se_lee(url):
    peticion = urllib.request.Request("https://r.jina.ai/" + urllib.parse.quote(url, safe=":/?&=%#+,;@!$'()*~"),
                                      headers={"Accept": "application/json", "X-Retain-Images": "none"})
    for _ in range(4):
        JINA.esperar()
        try:
            j = json.load(urllib.request.urlopen(peticion, timeout=90))
        except urllib.error.HTTPError as e:
            if e.code == 429:
                try:
                    time.sleep(float(json.loads(e.read()).get("retryAfter", 5)) + 1)
                except Exception:
                    time.sleep(5)
                continue
            return False
        except Exception:
            return None  # sin red o sin respuesta: no se sabe, y no se guarda
        d = j.get("data") or {}
        texto = (d.get("content") or "").strip()
        return len(texto) >= 200 and (d.get("httpStatus") or 200) < 400 \
            and not re.search(r"error \d{3}", d.get("warning") or "", re.I) and not ERROR.match((d.get("title") or "").strip())
    return None  # el lector siguió limitando (429): se vuelve a mirar la próxima vez


def cargar():
    return json.loads(CACHE.read_text(encoding="utf-8")) if CACHE.exists() else {}


def _escribir(datos):
    CACHE.write_text(json.dumps(dict(sorted(datos.items())), ensure_ascii=False, indent=0) + "\n", encoding="utf-8")


def asegurar(urls, repasar=False):
    datos = cargar()
    pendientes = sorted(u for u in set(urls) if u not in datos or (repasar and not datos[u]["lectura"]))
    if not pendientes:
        return datos
    print(f"Comprobando si se pueden leer {len(pendientes)} fuentes (unos {len(pendientes) / 19:.0f} min)…", flush=True)
    hoy = dt.date.today().isoformat()
    with cf.ThreadPoolExecutor(8) as ex:
        for n, (url, ok) in enumerate(zip(pendientes, ex.map(se_lee, pendientes)), 1):
            if ok is not None:  # None: fallo de red o límite agotado; se queda pendiente para la próxima vez
                datos[url] = {"lectura": ok, "comprobado": hoy}
            if n % 20 == 0 or n == len(pendientes):
                _escribir(datos)
                print(f"  {n}/{len(pendientes)}", flush=True)
    return datos


def se_puede_leer(url, datos):
    return bool((datos.get(url) or {}).get("lectura"))


def urls_de_las_entrevistas():
    urls = set()
    for f in (RAIZ / "entrevistas").glob("*/resultados/*.json"):
        d = json.loads(f.read_text(encoding="utf-8"))
        for a in d if isinstance(d, list) else d.get("afirmaciones", d.get("resultados", [])):
            for s in a.get("fuentes", []):
                if isinstance(s, dict) and str(s.get("url", "")).startswith(("http://", "https://")):
                    urls.add(s["url"])
    return urls


if __name__ == "__main__":
    datos = asegurar(urls_de_las_entrevistas(), repasar="--repasar" in sys.argv)
    print(f"{sum(f['lectura'] for f in datos.values())} de {len(datos)} fuentes se pueden leer en el visor")
