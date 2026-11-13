#!/usr/bin/env python3
"""Genera la web estática (web/) a partir de entrevistas/<slug>/.

Cada entrevista necesita meta.json, segmentos.json, capitulos.json, resultados/*.json
y, opcionalmente, resumenes/*.json (un resumen por afirmación, en el mismo orden).

Uso: python3 web-src/build.py
"""
import datetime as dt
import html
import json
import re
import unicodedata
from pathlib import Path
from urllib.parse import urlparse

RAIZ = Path(__file__).resolve().parent.parent
ENTREVISTAS = RAIZ / "entrevistas"
SALIDA = RAIZ / "web"
REPO = "https://github.com/PabloPC05/verificacion-podcast"

ORDEN = ["falso", "enganoso", "mayormente_verdadero", "verdadero", "no_verificable"]
NOMBRE = {"falso": "Falso", "enganoso": "Engañoso", "mayormente_verdadero": "Casi cierto",
          "verdadero": "Verdadero", "no_verificable": "No verificable"}
e = html.escape


def segundos(marca):
    try:
        p = [int(x) for x in str(marca).strip().split(":")]
        while len(p) < 3:
            p.insert(0, 0)
        return p[0] * 3600 + p[1] * 60 + p[2]
    except ValueError:
        return 0


def hms(s):
    return f"{s // 3600}:{s % 3600 // 60:02d}:{s % 60:02d}"


def _norm(t):
    t = unicodedata.normalize("NFD", t.lower())
    return re.sub(r"[^a-z0-9]+", " ", "".join(c for c in t if unicodedata.category(c) != "Mn")).strip()


def indice_segmentos(carpeta):
    texto, pos = "", []
    for s in json.loads((carpeta / "segmentos.json").read_text(encoding="utf-8")):
        pos.append((len(texto), s["i"]))
        texto += _norm(s["t"]) + " "
    return texto, pos


def momento_exacto(a, indice):
    """Segundo del vídeo en que empieza la cita, buscándola en la transcripción por segmentos."""
    texto, posiciones = indice
    aprox = segundos(a.get("minuto", ""))
    palabras = _norm(a.get("cita", "")).split()
    for ini in range(0, max(1, len(palabras) - 5), 3):
        trozo = " ".join(palabras[ini:ini + 6])
        if len(trozo) < 15:
            continue
        sitios = [m.start() for m in re.finditer(re.escape(trozo), texto)]
        if not sitios:
            continue
        tiempos = [max(t for p, t in posiciones if p <= pos) for pos in sitios]
        t = min(tiempos, key=lambda x: abs(x - aprox))
        if abs(t - aprox) <= 240 or len(sitios) == 1:
            return max(0, int(t) - 2)
    return aprox


def dominio(url):
    d = urlparse(url).netloc.lower()
    return d[4:] if d.startswith("www.") else d


def panel(a):
    v = a["veredicto"]
    s = a["_t"]
    fuentes = [f for f in a.get("fuentes", []) if isinstance(f, dict)
               and str(f.get("url", "")).startswith(("http://", "https://"))]
    lista = "".join(
        f'<li><a href="{e(f["url"], quote=True)}" target="_blank" rel="noopener noreferrer">'
        f'{e(f.get("titulo") or f["url"])}</a> <span>{e(dominio(f["url"]))}</span></li>' for f in fuentes)
    cita = a.get("cita", "").strip("«»\" ")
    resumen = a.get("_resumen") or a.get("explicacion", "")
    detalle = (f'<details><summary>Explicación completa</summary><p>{e(a["explicacion"])}</p></details>'
               if a.get("_resumen") and a.get("explicacion") else "")
    enlace = f"https://www.youtube.com/watch?v={a['_video']}&t={s}s"
    return (
        f'<li class="hito" data-v="{v}" id="{a["_id"]}">'
        f'<div class="dicho"><a class="minuto" href="{enlace}" target="_blank" rel="noopener noreferrer" '
        f'title="Abrir el vídeo en este momento">{hms(s)}</a>'
        + (f'<blockquote>«{e(cita)}»</blockquote>' if cita else "") + "</div>"
        f'<span class="punto" aria-hidden="true"></span><span class="flecha" aria-hidden="true"></span>'
        f'<article class="panel"><p class="ficha">{NOMBRE[v]}</p>'
        + (f'<blockquote class="movil">«{e(cita)}»</blockquote>' if cita else "")
        + f'<p class="que">{e(a.get("afirmacion", ""))}</p>'
        f'<p class="porque"><b>Por qué:</b> {e(resumen)}</p>'
        + (f'<p class="rotulo">Fuentes</p><ol class="fuentes">{lista}</ol>' if lista else "")
        + detalle + '<p class="contrasta"><button class="copiar" type="button">Copiar encargo para contrastarlo con una IA</button></p>'
        + "</article></li>"
    )


def cargar(carpeta, meta):
    indice = indice_segmentos(carpeta)
    todas = []
    for ruta in sorted((carpeta / "resultados").glob("*.json")):
        datos = [a for a in json.loads(ruta.read_text(encoding="utf-8")) if isinstance(a, dict)]
        ruta_res = carpeta / "resumenes" / ruta.name
        resumenes = json.loads(ruta_res.read_text(encoding="utf-8")) if ruta_res.exists() else []
        if len(resumenes) != len(datos):
            if resumenes:
                print(f"AVISO: {ruta.name}: {len(resumenes)} resúmenes para {len(datos)} afirmaciones; se ignoran")
            resumenes = [None] * len(datos)
        for a, r in zip(datos, resumenes):
            if a.get("veredicto") not in NOMBRE:
                a["veredicto"] = "no_verificable"
            a["_resumen"] = r.strip() if isinstance(r, str) and r.strip() else None
            a["_t"] = momento_exacto(a, indice)
            a["_video"] = meta["video"]
        todas += datos
    todas.sort(key=lambda a: a["_t"])
    return todas


TONO = {"falso": "#c0271e", "enganoso": "#c26a00", "mayormente_verdadero": "#5a7d10",
        "verdadero": "#1c7c45", "no_verificable": "#777"}
PLURAL = {"falso": "Falsas", "enganoso": "Engañosas", "mayormente_verdadero": "Casi ciertas",
          "verdadero": "Verdaderas", "no_verificable": "No verificables"}


BASE = "https://verificacion-podcast.vercel.app"
DEFINICIONES = {
    "verdadero": "Los datos lo confirman.",
    "mayormente_verdadero": "Cierto en lo esencial, con una imprecisión menor.",
    "enganoso": "Se apoya en algo real pero omite contexto, mezcla periodos o lleva a una conclusión que no se sigue.",
    "falso": "Los datos lo contradicen. No implica intención de mentir: incluye errores y lapsus.",
    "no_verificable": "No se encontró prueba pública suficiente, o la búsqueda automática se quedó corta.",
}


def rellenar(plantilla, **valores):
    for k, v in valores.items():
        plantilla = plantilla.replace(f"@@{k}@@", str(v))
    return plantilla


def preparar(meta):
    """Carga una entrevista y reparte sus afirmaciones por temas (capítulos del vídeo)."""
    carpeta = ENTREVISTAS / meta["slug"]
    todas = cargar(carpeta, meta)
    capitulos = json.loads((carpeta / "capitulos.json").read_text(encoding="utf-8"))
    if not capitulos:
        capitulos = [{"start_time": 0, "end_time": 10 ** 9, "title": "Entrevista completa"}]
    vistos = {}
    for a in todas:
        n = vistos[a["_t"]] = vistos.get(a["_t"], 0) + 1
        a["_id"] = f'm{a["_t"]}' if n == 1 else f'm{a["_t"]}-{n}'
    temas = []
    for n, c in enumerate(capitulos, 1):
        ini, fin = int(c["start_time"]), int(c["end_time"])
        suyas = [a for a in todas if ini <= a["_t"] < fin or (c is capitulos[-1] and a["_t"] >= fin)]
        for a in suyas:
            a["_tema"] = n
        temas.append({"n": n, "titulo": c["title"], "ini": ini, "fin": fin, "suyas": suyas, "total": len(suyas),
                      "malas": sum(a["veredicto"] in ("falso", "enganoso") for a in suyas)})
    total = {k: sum(a["veredicto"] == k for a in todas) for k in ORDEN}
    return dict(meta, carpeta=carpeta, todas=todas, temas=temas, capitulos=capitulos, total=total,
                suma=len(todas), malas=total["falso"] + total["enganoso"])


def menu(entrevistas, actual=None):
    """Menú superior fijo: un desplegable por candidato (línea temporal, transcripción y temas)."""
    partes = []
    for m in entrevistas:
        if not m.get("publicar"):
            partes.append(f'<span class="off" title="Verificación en curso">{e(m["invitado"])}</span>')
            continue
        s = e(m["slug"])
        temas = "".join(
            f'<a href="/{s}#tema-{t["n"]}" data-tema="tema-{t["n"]}"><span>{e(t["titulo"])}</span>'
            + (f'<b>{t["malas"]}</b>' if t["malas"] else "") + "</a>" for t in m["temas"] if t["total"])
        partes.append(
            f'<details class="desp{" actual" if m["slug"] == actual else ""}"><summary>{e(m["invitado"])}</summary><div class="lista">'
            f'<a class="fuerte" href="/{s}"><span>Línea temporal</span><small>{m["malas"]} falsas o engañosas de {m["suma"]}</small></a>'
            f'<a class="fuerte" href="/{s}/transcripcion"><span>Transcripción completa</span></a>'
            f'<p class="rot">Temas</p>{temas}</div></details>')
    return ('<header class="menu"><div class="ancho"><div class="m1"><a class="sello" href="/" title="Todas las entrevistas">Verificación</a>'
            + "".join(partes) + '<a class="dcha" href="/api">API</a>'
            f'<a href="{REPO}" target="_blank" rel="noopener noreferrer">GitHub ↗</a></div></div></header>' + JS_MENU)


JS_MENU = """<script>
document.addEventListener("click", ev => document.querySelectorAll("details.desp[open]").forEach(d => {
  if (!d.contains(ev.target) || ev.target.closest(".lista a")) d.open = false;
}));
document.addEventListener("keydown", ev => { if (ev.key === "Escape") document.querySelectorAll("details.desp[open]").forEach(d => d.open = false); });
const medirMenu = () => document.documentElement.style.setProperty("--menu", document.querySelector(".menu").offsetHeight + "px");
medirMenu(); addEventListener("resize", medirMenu);
</script>"""


def filtros(m, extra=""):
    return ('<div class="filtros"><div class="ancho"><div class="fila" id="filtros"><span class="rot">Filtros</span>'
            f'<button data-todas aria-pressed="false">Todas <b>{m["suma"]}</b></button>'
            + "".join(f'<button data-v="{k}" style="--tono:{TONO[k]}" aria-pressed="false"><i></i>{PLURAL[k]} <b>{m["total"][k]}</b></button>'
                      for k in ORDEN) + extra + "</div></div></div>")


def pagina_entrevista(m, entrevistas):
    filas = []
    for t in m["temas"]:
        nota = f'{t["malas"]} falsas o engañosas' if t["malas"] != 1 else "1 falsa o engañosa"
        filas.append(
            f'<li class="capitulo" id="tema-{t["n"]}">'
            f'<a class="minuto" href="https://www.youtube.com/watch?v={m["video"]}&t={t["ini"]}s" target="_blank" '
            f'rel="noopener noreferrer">{hms(t["ini"])}</a><span class="marca" aria-hidden="true"></span>'
            f'<div><h2>{e(t["titulo"])}</h2><p>{nota} · {t["total"]} afirmaciones comprobadas</p></div></li>')
        filas += [panel(a) for a in t["suyas"]]
    pagina = rellenar(
        PLANTILLA, MENU=menu(entrevistas, m["slug"]), CSS_MENU=CSS_MENU, FILTROS=filtros(m), SUMA=m["suma"], MALAS=m["malas"],
        FALSAS=m["total"]["falso"], ENGANOSAS=m["total"]["enganoso"], CASI=m["total"]["mayormente_verdadero"],
        VERDADERAS=m["total"]["verdadero"], NV=m["total"]["no_verificable"], FILAS="".join(filas),
        INVITADO=e(m["invitado"]), PROGRAMA=e(m["programa"]), FECHA_VIDEO=e(m["fecha"]), DURACION=e(m["duracion"]),
        FECHA=dt.datetime.now().strftime("%d/%m/%Y"), VIDEO=m["video"], SLUG=m["slug"], REPO=REPO, BASE=BASE)
    destino = SALIDA / m["slug"]
    destino.mkdir(parents=True, exist_ok=True)
    (destino / "index.html").write_text(pagina, encoding="utf-8")
    print(f'{m["slug"]}: {m["suma"]} afirmaciones · {m["total"]}')


def pagina_transcripcion(m, entrevistas):
    parrafos = []
    for linea in (m["carpeta"] / "transcripcion.txt").read_text(encoding="utf-8").splitlines():
        r = re.match(r"\[(\d+:\d\d:\d\d)\]\s*(.*)", linea)
        if r:
            parrafos.append((segundos(r.group(1)), r.group(2)))
    pendientes = list(m["temas"])
    cuerpo = []
    for k, (t, texto) in enumerate(parrafos):
        fin = parrafos[k + 1][0] if k + 1 < len(parrafos) else 10 ** 9
        while pendientes and pendientes[0]["ini"] < fin:
            tema = pendientes.pop(0)
            cuerpo.append(f'<h2 id="tema-{tema["n"]}">{e(tema["titulo"])}</h2>')
        marcas = "".join(
            f'<a class="chip" data-v="{a["veredicto"]}" style="--tono:{TONO[a["veredicto"]]}" href="/{m["slug"]}#{a["_id"]}" '
            f'title="{e(a.get("afirmacion", ""), quote=True)}">{hms(a["_t"])} · {NOMBRE[a["veredicto"]]}</a>'
            for a in m["todas"] if t <= a["_t"] < fin)
        cuerpo.append(
            f'<div class="par" id="t{t}"><a class="minuto" href="https://www.youtube.com/watch?v={m["video"]}&t={t}s" '
            f'target="_blank" rel="noopener noreferrer">{hms(t)}</a><div><p>{e(texto)}</p>'
            + (f'<p class="chips">{marcas}</p>' if marcas else "") + "</div></div>")
    solo = '<button data-solo aria-pressed="false">Solo párrafos con afirmaciones</button>'
    pagina = rellenar(
        TRANSCRIPCION, MENU=menu(entrevistas, m["slug"]), CSS_MENU=CSS_MENU, FILTROS=filtros(m, solo), CUERPO="".join(cuerpo),
        INVITADO=e(m["invitado"]), PROGRAMA=e(m["programa"]), FECHA_VIDEO=e(m["fecha"]), DURACION=e(m["duracion"]),
        VIDEO=m["video"], SLUG=m["slug"], REPO=REPO)
    destino = SALIDA / m["slug"] / "transcripcion"
    destino.mkdir(parents=True, exist_ok=True)
    (destino / "index.html").write_text(pagina, encoding="utf-8")


# ───────────────────────── API estática (JSON) ─────────────────────────

def ficha_api(m):
    s = m["slug"]
    return {
        "slug": s, "invitado": m["invitado"], "partido": m.get("partido"), "programa": m["programa"], "fecha": m["fecha"],
        "duracion": m["duracion"], "video_url": f'https://www.youtube.com/watch?v={m["video"]}',
        "web_url": f"{BASE}/{s}", "afirmaciones_url": f"{BASE}/api/v1/{s}.json",
        "transcripcion_url": f"{BASE}/api/v1/{s}/transcripcion.json",
        "transcripcion_txt_url": f"{BASE}/api/v1/{s}/transcripcion.txt",
        "total_afirmaciones": m["suma"], "por_veredicto": m["total"],
        "temas": [{"n": t["n"], "titulo": t["titulo"], "inicio_s": t["ini"], "total": t["total"],
                   "por_veredicto": {k: sum(a["veredicto"] == k for a in t["suyas"]) for k in ORDEN}} for t in m["temas"]],
    }


def afirmacion_api(m, a):
    tema = next((t for t in m["temas"] if t["n"] == a.get("_tema")), None)
    return {
        "id": f'{m["slug"]}-{a["_id"]}', "entrevista": m["slug"], "invitado": m["invitado"],
        "tema_n": a.get("_tema"), "tema": tema["titulo"] if tema else None,
        "segundo": a["_t"], "minuto": hms(a["_t"]),
        "video_url": f'https://www.youtube.com/watch?v={m["video"]}&t={a["_t"]}s', "web_url": f'{BASE}/{m["slug"]}#{a["_id"]}',
        "cita": a.get("cita", ""), "afirmacion": a.get("afirmacion", ""), "veredicto": a["veredicto"],
        "resumen": a.get("_resumen"), "explicacion": a.get("explicacion", ""), "confianza": a.get("confianza"),
        "fuentes": [{"titulo": f.get("titulo", ""), "url": f["url"]} for f in a.get("fuentes", [])
                    if isinstance(f, dict) and str(f.get("url", "")).startswith(("http://", "https://"))],
    }


def escribir_json(ruta, datos):
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_text(json.dumps(datos, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")


def generar_api(hechas):
    api = SALIDA / "api" / "v1"
    ahora = dt.datetime.now().astimezone().isoformat(timespec="seconds")
    aviso = ("Verificación asistida por IA, sin revisión de un equipo de periodistas. «falso» no implica intención de mentir. "
             "Contrasta siempre con las fuentes enlazadas.")
    comun = {"generado": ahora, "aviso": aviso, "veredictos": DEFINICIONES, "metodo_url": f"{REPO}/blob/main/METODO.md",
             "repositorio": REPO, "documentacion": f"{BASE}/api"}
    escribir_json(api / "entrevistas.json", dict(comun, entrevistas=[ficha_api(m) for m in hechas]))
    todas = []
    for m in hechas:
        suyas = [afirmacion_api(m, a) for a in m["todas"]]
        todas += suyas
        escribir_json(api / f'{m["slug"]}.json', dict(comun, entrevista=ficha_api(m), afirmaciones=suyas))
        segs = json.loads((m["carpeta"] / "segmentos.json").read_text(encoding="utf-8"))
        escribir_json(api / m["slug"] / "transcripcion.json", dict(
            comun, entrevista=ficha_api(m),
            nota="Transcripción automática (Whisper): no distingue hablantes y puede tener errores en nombres y cifras.",
            segmentos=[{"inicio_s": round(x["i"], 2), "fin_s": round(x["f"], 2), "texto": x["t"].strip()} for x in segs]))
        (api / m["slug"] / "transcripcion.txt").write_text(
            (m["carpeta"] / "transcripcion.txt").read_text(encoding="utf-8"), encoding="utf-8")
    escribir_json(api / "afirmaciones.json", dict(comun, total=len(todas), afirmaciones=todas))
    slugs = [m["slug"] for m in hechas]
    def op(resumen):
        return {"get": {"summary": resumen, "responses": {"200": {"description": "JSON", "content": {"application/json": {}}}}}}
    par = [{"name": "slug", "in": "path", "required": True, "schema": {"type": "string", "enum": slugs}}]
    escribir_json(api / "openapi.json", {
        "openapi": "3.1.0",
        "info": {"title": "Verificación de entrevistas de The Wild Project", "version": "1",
                 "description": "API estática de solo lectura, sin clave y con CORS abierto. " + aviso},
        "servers": [{"url": f"{BASE}/api/v1"}],
        "paths": {
            "/entrevistas.json": op("Lista de entrevistas verificadas, con recuentos por veredicto y por tema"),
            "/afirmaciones.json": op("Todas las afirmaciones verificadas de todas las entrevistas"),
            "/{slug}.json": dict(op("Afirmaciones verificadas de una entrevista"), parameters=par),
            "/{slug}/transcripcion.json": dict(op("Transcripción por segmentos con tiempos"), parameters=par),
            "/{slug}/transcripcion.txt": dict(op("Transcripción en texto plano con marcas [h:mm:ss]"), parameters=par),
        }})
    ejemplo = slugs[0] if slugs else "sanchez"
    (SALIDA / "llms.txt").write_text(f"""# Verificación de las entrevistas electorales de The Wild Project

> Afirmaciones comprobables de los candidatos a las elecciones generales españolas del 29-11-2026 en sus entrevistas
> con Jordi Wild, cada una con veredicto, explicación, fuentes y enlace al segundo exacto del vídeo. {aviso}

API de solo lectura, JSON estático, sin clave, CORS abierto. Base: {BASE}/api/v1

- [Entrevistas]({BASE}/api/v1/entrevistas.json): lista de entrevistas, recuentos por veredicto y temas. Empieza aquí.
- [Todas las afirmaciones]({BASE}/api/v1/afirmaciones.json): un solo fichero con todas las afirmaciones verificadas.
- [Afirmaciones de una entrevista]({BASE}/api/v1/{ejemplo}.json): sustituye el slug ({", ".join(slugs)}).
- [Transcripción con tiempos]({BASE}/api/v1/{ejemplo}/transcripcion.json) y [en texto]({BASE}/api/v1/{ejemplo}/transcripcion.txt).
- [OpenAPI]({BASE}/api/v1/openapi.json)
- [Método y criterios]({REPO}/blob/main/METODO.md)

Campos de cada afirmación: id, entrevista, invitado, tema, segundo, minuto, video_url, web_url, cita (literal de la
transcripción), afirmacion (reformulada), veredicto (verdadero | mayormente_verdadero | enganoso | falso | no_verificable),
resumen, explicacion, confianza (alta | media | baja), fuentes [{{titulo, url}}].

Para volver a comprobar una afirmación: lee `cita` y `afirmacion`, abre cada `fuentes[].url`, y contrasta con la `explicacion`.
Los errores se comunican en {REPO}/issues.
""", encoding="utf-8")
    (SALIDA / "vercel.json").write_text(json.dumps({"headers": [
        {"source": "/api/(.*)", "headers": [{"key": "Access-Control-Allow-Origin", "value": "*"},
                                            {"key": "Cache-Control", "value": "public, max-age=300"}]},
        {"source": "/llms.txt", "headers": [{"key": "Access-Control-Allow-Origin", "value": "*"}]}]}, indent=1) + "\n")
    return ejemplo, slugs


def main():
    metas = [json.loads(r.read_text(encoding="utf-8")) for r in sorted(ENTREVISTAS.glob("*/meta.json"))]
    metas.sort(key=lambda m: m.get("programa", ""), reverse=True)
    entrevistas = []
    for meta in metas:
        if meta.get("publicar") and any((ENTREVISTAS / meta["slug"] / "resultados").glob("*.json")):
            entrevistas.append(preparar(meta))
        else:
            print(f'{meta["slug"]}: verificación en curso (meta.json sin "publicar": true), se omite')
            entrevistas.append(dict(meta, publicar=False))
    hechas = [m for m in entrevistas if m.get("publicar")]
    SALIDA.mkdir(exist_ok=True)
    for m in hechas:
        pagina_entrevista(m, entrevistas)
        pagina_transcripcion(m, entrevistas)
    ejemplo, slugs = generar_api(hechas)
    tarjetas = "".join(
        f'<article class="entrevista"><p class="prog">{e(m["programa"])} · {e(m["fecha"])} · {e(m["duracion"])}</p>'
        f'<h2><a href="/{e(m["slug"])}">{e(m["invitado"])}</a></h2>'
        f'<p class="num"><b>{m["malas"]}</b> falsas o engañosas de {m["suma"]} afirmaciones comprobadas</p>'
        f'<p class="des">' + " · ".join(f'<span style="color:{TONO[k]}">{m["total"][k]} {PLURAL[k].lower()}</span>' for k in ORDEN) + "</p>"
        f'<p class="rot">Temas de la entrevista</p><ul>'
        + "".join(f'<li><a href="/{e(m["slug"])}#tema-{t["n"]}">{e(t["titulo"])}</a>'
                  + (f' <b>{t["malas"]}</b>' if t["malas"] else "") + "</li>" for t in m["temas"] if t["total"])
        + f'</ul><p class="acc"><a href="/{e(m["slug"])}">Línea temporal →</a>'
        f'<a href="/{e(m["slug"])}/transcripcion">Transcripción completa →</a></p></article>'
        for m in hechas)
    tarjetas += "".join(
        f'<article class="entrevista off"><p class="prog">{e(m.get("programa", ""))}</p><h2>{e(m["invitado"])}</h2>'
        f'<p class="des">Verificación en curso.</p></article>' for m in entrevistas if not m.get("publicar"))
    (SALIDA / "index.html").write_text(rellenar(
        PORTADA, MENU=menu(entrevistas), CSS_MENU=CSS_MENU, TARJETAS=tarjetas, REPO=REPO,
        FECHA=dt.datetime.now().strftime("%d/%m/%Y")), encoding="utf-8")
    (SALIDA / "api").mkdir(exist_ok=True)
    (SALIDA / "api" / "index.html").write_text(rellenar(
        PAGINA_API, MENU=menu(entrevistas), CSS_MENU=CSS_MENU, BASE=BASE, REPO=REPO, EJ=ejemplo,
        SLUGS=", ".join(f"<code>{x}</code>" for x in slugs)), encoding="utf-8")


CSS_MENU = """
html { scroll-behavior:smooth; scroll-padding-top:calc(var(--menu, 48px) + 64px); }
[hidden] { display:none !important; }
.menu { position:sticky; top:0; z-index:10; background:#fff; border-bottom:2px solid #000; }
.menu .ancho { padding-top:9px; padding-bottom:9px; position:relative; }
.m1 { display:flex; flex-wrap:wrap; align-items:center; gap:4px 24px; font-size:14.5px; }
.m1 a, .desp summary { color:#000; text-decoration:none; font-weight:600; padding:3px 0; border-bottom:2px solid transparent; }
.m1 > a:hover, .desp.actual summary, .desp[open] summary, .desp summary:hover { border-bottom-color:#000; }
.m1 .sello { font:700 17px/1.2 "Iowan Old Style","Palatino Linotype",Palatino,Georgia,serif; }
.m1 .off { color:#999; } .m1 .dcha { margin-left:auto; }
.rot { font-size:10.5px; font-weight:700; text-transform:uppercase; letter-spacing:.09em; color:#666; flex:none; }
.desp { position:relative; margin:0; padding:0; border:0; font-size:inherit; }
.desp summary { list-style:none; cursor:pointer; user-select:none; }
.desp summary::-webkit-details-marker { display:none; }
.desp summary::after { content:" ▾"; } .desp[open] summary::after { content:" ▴"; }
.desp .lista { position:absolute; top:calc(100% + 10px); left:0; z-index:20; background:#fff; border:2px solid #000; box-shadow:5px 5px 0 #000;
  width:max-content; min-width:260px; max-width:min(92vw,470px); max-height:74vh; overflow-y:auto; padding:6px 0; }
.desp .lista a { display:flex; justify-content:space-between; align-items:baseline; gap:16px; padding:7px 16px;
  font-size:14.5px; font-weight:500; border:0; line-height:1.35; }
.desp .lista a.fuerte { font-weight:700; padding:9px 16px; }
.desp .lista a.fuerte small { font-weight:500; color:#666; font-size:12px; white-space:nowrap; }
.desp .lista .rot { margin:8px 0 2px; padding:9px 16px 0; border-top:1px solid #000; }
.desp .lista a:hover { background:#000; color:#fff; } .desp .lista a:hover small { color:#ccc; }
.desp .lista b { color:#c0271e; font-weight:700; font-variant-numeric:tabular-nums; }
.desp .lista a:hover b { color:#fff; } .desp .lista a.off { opacity:.4; }
.filtros { position:sticky; top:var(--menu, 48px); z-index:5; background:#fff; border-bottom:1px solid #000; padding:9px 0; }
.fila { display:flex; flex-wrap:wrap; align-items:center; gap:6px 8px; }
.fila button { font:inherit; font-size:12.5px; font-weight:600; color:#000; background:#fff; border:1.5px solid #000;
  border-radius:999px; padding:3px 11px; cursor:pointer; display:inline-flex; align-items:center; gap:6px; }
.fila b { font-weight:500; opacity:.7; font-variant-numeric:tabular-nums; }
.fila button[data-v] { color:var(--tono); border-color:var(--tono); }
.fila button[data-v] i { width:8px; height:8px; border-radius:50%; background:currentColor; }
.fila button[aria-pressed=true] { background:#000; color:#fff; }
.fila button[data-v][aria-pressed=true] { background:var(--tono); color:#fff; }
.fila button[data-solo] { margin-left:auto; }
@media (max-width:700px) { .m1 { gap:4px 16px; font-size:14px; } .m1 .dcha { margin-left:0; }
  .desp { position:static; } .desp .lista { left:16px; right:16px; top:auto; margin-top:10px; width:auto; max-width:none; }
  .fila .rot { display:none; } .fila button { font-size:12px; padding:2px 9px; } .fila button[data-solo] { margin-left:0; } }
"""

PAGINA_API = """<!doctype html>
<html lang="es">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="color-scheme" content="light only">
<title>API abierta · Verificación The Wild Project</title>
<meta name="description" content="API JSON de solo lectura, sin clave y con CORS abierto, con todas las afirmaciones verificadas, sus fuentes y las transcripciones. Pensada para agentes de IA y verificadores.">
<style>
:root { --serif:"Iowan Old Style","Palatino Linotype",Palatino,Georgia,serif; }
* { box-sizing:border-box; }
body { margin:0; background:#fff; color:#000; font:16px/1.6 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif; }
a { color:#000; }
.ancho { max-width:1120px; margin:0 auto; padding:0 16px; }
main.ancho { max-width:820px; padding-bottom:72px; }
h1 { font:700 clamp(28px,5.5vw,44px)/1.08 var(--serif); letter-spacing:-0.02em; margin:38px 0 12px; text-wrap:balance; }
h2 { font:700 23px/1.2 var(--serif); margin:40px 0 10px; padding-top:12px; border-top:3px solid #000; }
p, li { max-width:68ch; }
code { font:13.5px/1.5 ui-monospace,SFMono-Regular,Menlo,monospace; background:#f2f2f2; padding:1px 5px; }
pre { background:#000; color:#fff; padding:14px 16px; overflow-x:auto; font:13px/1.55 ui-monospace,SFMono-Regular,Menlo,monospace; }
pre code { background:none; padding:0; color:inherit; }
.tabla { overflow-x:auto; }
table { border-collapse:collapse; width:100%; font-size:14.5px; min-width:560px; }
th, td { text-align:left; padding:8px 10px; border-bottom:1px solid #000; vertical-align:top; }
th { font-size:11px; text-transform:uppercase; letter-spacing:.08em; }
td a { overflow-wrap:anywhere; }
@@CSS_MENU@@
</style>
</head>
<body>
@@MENU@@
<main class="ancho">
<h1>API abierta para comprobar la verificación</h1>
<p>Todos los datos de esta web están disponibles como JSON estático: sin clave, sin límite propio de uso y con CORS abierto. Está pensada para que periodistas, verificadores y agentes de IA puedan revisar cada veredicto contra sus fuentes mucho más rápido que leyendo la web.</p>

<h2>Direcciones</h2>
<div class="tabla"><table>
<thead><tr><th>Qué</th><th>Dirección</th></tr></thead>
<tbody>
<tr><td>Lista de entrevistas, recuentos y temas (empieza aquí)</td><td><a href="/api/v1/entrevistas.json">/api/v1/entrevistas.json</a></td></tr>
<tr><td>Todas las afirmaciones de todas las entrevistas</td><td><a href="/api/v1/afirmaciones.json">/api/v1/afirmaciones.json</a></td></tr>
<tr><td>Afirmaciones de una entrevista</td><td><a href="/api/v1/@@EJ@@.json">/api/v1/{slug}.json</a></td></tr>
<tr><td>Transcripción por segmentos con tiempos</td><td><a href="/api/v1/@@EJ@@/transcripcion.json">/api/v1/{slug}/transcripcion.json</a></td></tr>
<tr><td>Transcripción en texto plano</td><td><a href="/api/v1/@@EJ@@/transcripcion.txt">/api/v1/{slug}/transcripcion.txt</a></td></tr>
<tr><td>Descripción OpenAPI 3.1</td><td><a href="/api/v1/openapi.json">/api/v1/openapi.json</a></td></tr>
<tr><td>Guía para modelos de lenguaje</td><td><a href="/llms.txt">/llms.txt</a></td></tr>
</tbody></table></div>
<p>Entrevistas disponibles (<code>slug</code>): @@SLUGS@@.</p>

<h2>Qué trae cada afirmación</h2>
<div class="tabla"><table>
<thead><tr><th>Campo</th><th>Contenido</th></tr></thead>
<tbody>
<tr><td><code>id</code></td><td>Identificador estable: entrevista y segundo del vídeo.</td></tr>
<tr><td><code>cita</code></td><td>Lo que se dijo, literal de la transcripción.</td></tr>
<tr><td><code>afirmacion</code></td><td>La afirmación reformulada para que se entienda sola.</td></tr>
<tr><td><code>veredicto</code></td><td><code>verdadero</code>, <code>mayormente_verdadero</code>, <code>enganoso</code>, <code>falso</code> o <code>no_verificable</code>.</td></tr>
<tr><td><code>resumen</code>, <code>explicacion</code></td><td>La justificación, en una frase y completa.</td></tr>
<tr><td><code>confianza</code></td><td><code>alta</code>, <code>media</code> o <code>baja</code>.</td></tr>
<tr><td><code>fuentes</code></td><td>Lista de <code>{titulo, url}</code> que sustentan el veredicto.</td></tr>
<tr><td><code>segundo</code>, <code>minuto</code>, <code>video_url</code></td><td>El momento exacto del vídeo.</td></tr>
<tr><td><code>tema</code>, <code>tema_n</code></td><td>El capítulo de la entrevista.</td></tr>
<tr><td><code>web_url</code></td><td>Enlace a la tarjeta en esta web.</td></tr>
</tbody></table></div>

<h2>Ejemplos</h2>
<pre><code># Las afirmaciones falsas de una entrevista, con sus fuentes
curl -s @@BASE@@/api/v1/@@EJ@@.json \\
  | jq '.afirmaciones[] | select(.veredicto == "falso") | {minuto, cita, resumen, fuentes}'

# Recuento por veredicto de todas las entrevistas
curl -s @@BASE@@/api/v1/entrevistas.json | jq '.entrevistas[] | {invitado, por_veredicto}'</code></pre>

<h2>Encargo de ejemplo para un agente de IA</h2>
<pre><code>Descarga @@BASE@@/api/v1/@@EJ@@.json. Para cada afirmación con veredicto
"falso" o "enganoso": abre cada fuentes[].url, comprueba si de verdad respalda la
explicacion, busca al menos una fuente independiente más y dime en cuáles discrepas
del veredicto y por qué. Usa video_url para oír el contexto si la cita es ambigua.</code></pre>

<h2>Condiciones</h2>
<p>Los datos son una verificación asistida por IA, sin revisión de un equipo de periodistas: úsalos como punto de partida y contrasta con las fuentes. «Falso» no implica intención de mentir. Los ficheros se regeneran cuando cambia algún dato (campo <code>generado</code>). Si encuentras un error, abre una incidencia en <a href="@@REPO@@/issues" target="_blank" rel="noopener noreferrer">GitHub</a>; el método completo está en <a href="@@REPO@@/blob/main/METODO.md" target="_blank" rel="noopener noreferrer">METODO.md</a>.</p>
</main>
</body>
</html>
"""

PORTADA = """<!doctype html>
<html lang="es">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="color-scheme" content="light only">
<title>Verificación de las entrevistas electorales de The Wild Project</title>
<meta name="description" content="Las entrevistas de Jordi Wild a los candidatos a las elecciones generales de 2026, comprobadas dato a dato con el mismo método. Código y datos abiertos.">
<style>
:root { --serif:"Iowan Old Style","Palatino Linotype",Palatino,Georgia,serif; }
* { box-sizing:border-box; }
body { margin:0; background:#fff; color:#000; font:16px/1.55 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif; }
a { color:#000; }
.ancho { max-width:1120px; margin:0 auto; padding:0 16px; }
main.ancho { max-width:860px; }
h1 { font:700 clamp(30px,6vw,48px)/1.06 var(--serif); letter-spacing:-0.02em; margin:40px 0 14px; text-wrap:balance; }
.entrada { font-size:17px; max-width:62ch; margin:0 0 30px; }
.entrevista { border:2px solid #000; padding:20px 22px; margin-bottom:18px; }
.entrevista.off { border:1px dashed #999; color:#666; }
.prog { margin:0; font-size:12px; text-transform:uppercase; letter-spacing:.08em; color:#666; }
.entrevista h2 { font:700 30px/1.15 var(--serif); margin:4px 0 8px; } .entrevista h2 a { text-decoration:none; }
.num { margin:0; font-size:17px; } .num b { font:700 34px/1 var(--serif); margin-right:4px; }
.des { margin:4px 0 14px; font-size:13.5px; font-weight:600; }
.entrevista ul { list-style:none; margin:6px 0 16px; padding:0; columns:2; column-gap:28px; font-size:14.5px; }
.entrevista li { margin:0 0 5px; break-inside:avoid; } .entrevista li b { color:#c0271e; }
.contrastar { border-top:3px solid #000; margin-top:40px; padding-top:6px; }
.contrastar h2 { font:700 26px/1.2 var(--serif); margin:18px 0 6px; }
.contrastar li { margin-bottom:8px; max-width:68ch; }
.contrastar pre { background:#000; color:#fff; padding:14px 16px; overflow-x:auto; white-space:pre-wrap; font:13px/1.55 ui-monospace,SFMono-Regular,Menlo,monospace; margin:6px 0 10px; }
.copiar { font:inherit; font-size:13px; font-weight:600; background:#fff; color:#000; border:1.5px solid #000; padding:5px 12px; cursor:pointer; }
.copiar:hover { background:#000; color:#fff; }
.acc { margin:0; display:flex; flex-wrap:wrap; gap:8px 22px; } .acc a { font-weight:700; text-underline-offset:3px; }
footer { border-top:3px solid #000; margin-top:48px; padding:24px 0 64px; font-size:14.5px; }
footer p { max-width:68ch; }
@media (max-width:640px) { .entrevista ul { columns:1; } }
@@CSS_MENU@@
</style>
</head>
<body>
@@MENU@@
<main class="ancho">
<h1>Las entrevistas de The Wild Project, comprobadas dato a dato</h1>
<p class="entrada">Jordi Wild ha entrevistado a los candidatos a la presidencia del Gobierno para las elecciones del 29 de noviembre de 2026. Transcribimos cada entrevista entera, separamos las afirmaciones que se pueden comprobar y las contrastamos con fuentes públicas, con el mismo método y la misma vara de medir para todos.</p>
@@TARJETAS@@
<section class="contrastar">
<h2>Contrástalo tú mismo</h2>
<p>No te fíes de nosotros: todo lo que hay aquí se puede comprobar.</p>
<ol>
<li><b>En cada afirmación.</b> El minuto abre el vídeo en el segundo exacto, las fuentes están enlazadas una a una y un botón copia un encargo listo para pegar en cualquier IA y que la revise por su cuenta.</li>
<li><b>Con la API abierta.</b> Todas las afirmaciones, veredictos, fuentes y transcripciones en JSON, sin clave: <a href="/api">documentación</a> · <a href="/api/v1/afirmaciones.json">afirmaciones.json</a> · <a href="/llms.txt">llms.txt</a>.</li>
<li><b>Con el código.</b> El método, los encargos literales que recibieron los agentes de IA y los datos en bruto están en <a href="@@REPO@@" target="_blank" rel="noopener noreferrer">GitHub</a>. Si encuentras un error, <a href="@@REPO@@/issues" target="_blank" rel="noopener noreferrer">abre una incidencia</a>.</li>
</ol>
<p class="rot">Encargo para un agente de IA</p>
<pre id="encargo">Descarga https://verificacion-podcast.vercel.app/api/v1/afirmaciones.json.
Para cada afirmación con veredicto "falso" o "enganoso": abre cada fuentes[].url y
comprueba si de verdad respalda la explicacion, busca al menos una fuente independiente
más y dime en cuáles discrepas del veredicto y por qué, con enlaces. Usa video_url para
oír el contexto si la cita es ambigua. Aplica la misma vara de medir a todos los invitados.</pre>
<button class="copiar" type="button" onclick="navigator.clipboard.writeText(document.getElementById('encargo').textContent).then(()=>{this.textContent='Copiado'})">Copiar encargo</button>
</section>
</main>
<footer><div class="ancho">
<p>Verificación asistida por IA (transcripción con Whisper, contraste con modelos Claude y búsqueda web), sin revisión de un equipo de periodistas. Cada afirmación enlaza el segundo exacto del vídeo y sus fuentes, y el código, las transcripciones y los datos están publicados en <a href="@@REPO@@" target="_blank" rel="noopener noreferrer">GitHub</a>. «Falso» no implica intención de mentir: incluye errores y lapsus. El número de afirmaciones falsas depende también de cuánto habla cada invitado y de cuántos datos da, así que las cifras no son un ranking. En rojo, junto a cada tema, cuántas afirmaciones falsas o engañosas contiene.</p>
<p>Última actualización: @@FECHA@@.</p>
</div></footer>
</body>
</html>
"""

TRANSCRIPCION = """<!doctype html>
<html lang="es">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="color-scheme" content="light only">
<title>Transcripción completa: @@INVITADO@@ en The Wild Project</title>
<meta name="description" content="Transcripción completa de la entrevista de Jordi Wild a @@INVITADO@@ (@@PROGRAMA@@), con marcas de tiempo enlazadas al vídeo y a cada afirmación verificada.">
<style>
:root { --serif:"Iowan Old Style","Palatino Linotype",Palatino,Georgia,serif; }
* { box-sizing:border-box; }
body { margin:0; background:#fff; color:#000; font:16px/1.6 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif; }
a { color:#000; }
.ancho { max-width:1120px; margin:0 auto; padding:0 16px; }
main.ancho { max-width:820px; padding-bottom:72px; }
h1 { font:700 clamp(28px,5.5vw,42px)/1.08 var(--serif); letter-spacing:-0.02em; margin:36px 0 12px; text-wrap:balance; }
.entrada { font-size:16px; color:#444; max-width:64ch; margin:0 0 8px; }
h2 { font:700 23px/1.2 var(--serif); margin:44px 0 14px; padding-top:12px; border-top:3px solid #000; text-wrap:balance; }
.par { display:grid; grid-template-columns:74px minmax(0,1fr); gap:0 14px; margin-bottom:16px; }
.par:target { background:#f3f3f3; }
.minuto { font-size:13px; font-weight:700; font-variant-numeric:tabular-nums; text-underline-offset:3px; padding-top:3px; }
.par p { margin:0; font:17px/1.6 var(--serif); }
.par .chips { margin-top:6px; display:flex; flex-wrap:wrap; gap:6px; font:600 12px/1.4 -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif; }
.chip { color:var(--tono); border:1.5px solid var(--tono); border-radius:999px; padding:1px 9px; text-decoration:none; }
.chip:hover { background:var(--tono); color:#fff; }
@media (max-width:600px) { .par { grid-template-columns:1fr; } .par p { font-size:16.5px; } }
@@CSS_MENU@@
</style>
</head>
<body>
@@MENU@@
@@FILTROS@@
<main class="ancho">
<h1>Transcripción completa: @@INVITADO@@ con Jordi Wild</h1>
<p class="entrada">@@PROGRAMA@@ · @@FECHA_VIDEO@@ · @@DURACION@@. Transcripción automática (Whisper): no distingue quién habla y puede tener errores en nombres y cifras. Cada minuto abre el <a href="https://www.youtube.com/watch?v=@@VIDEO@@" target="_blank" rel="noopener noreferrer">vídeo</a> en ese punto; las etiquetas de color llevan a la afirmación verificada en la <a href="/@@SLUG@@">línea temporal</a>.</p>
@@CUERPO@@
</main>
<script>
const botones = document.querySelectorAll("#filtros button[data-v]");
const todas = document.querySelector("#filtros [data-todas]"), soloB = document.querySelector("#filtros [data-solo]");
const activos = new Set([...botones].map(b => b.dataset.v));
let solo = false;
function pintar() {
  botones.forEach(b => b.setAttribute("aria-pressed", activos.has(b.dataset.v)));
  todas.setAttribute("aria-pressed", activos.size === botones.length);
  soloB.setAttribute("aria-pressed", solo);
  document.querySelectorAll(".par").forEach(p => {
    let n = 0;
    p.querySelectorAll(".chip").forEach(c => { c.hidden = !activos.has(c.dataset.v); if (!c.hidden) n++; });
    p.hidden = solo && n === 0;
  });
}
botones.forEach(b => b.onclick = () => {
  const v = b.dataset.v;
  if (activos.size === botones.length) { activos.clear(); activos.add(v); }
  else if (activos.has(v) && activos.size > 1) activos.delete(v); else activos.add(v);
  pintar();
});
todas.onclick = () => { botones.forEach(b => activos.add(b.dataset.v)); pintar(); };
soloB.onclick = () => { solo = !solo; pintar(); };
pintar();
</script>
</body>
</html>
"""

PLANTILLA = """<!doctype html>
<html lang="es">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="color-scheme" content="light only">
<title>Verificación: @@INVITADO@@ en The Wild Project</title>
<meta name="description" content="Línea temporal de la entrevista de Jordi Wild a @@INVITADO@@: @@MALAS@@ afirmaciones falsas o engañosas, cada una con su minuto, su justificación y sus fuentes.">
<meta property="og:title" content="@@INVITADO@@ en The Wild Project, minuto a minuto">
<meta property="og:description" content="@@MALAS@@ de @@SUMA@@ afirmaciones son falsas o engañosas. Cada una enlaza al segundo exacto del vídeo y a sus fuentes.">
<style>
:root { --negro:#000; --blanco:#fff; --gris:#666; --claro:#d9d9d9; --col:330px; --hueco:56px;
  --serif:"Iowan Old Style","Palatino Linotype",Palatino,Georgia,serif; }
* { box-sizing:border-box; }
html { scroll-behavior:smooth; }
body { margin:0; background:var(--blanco); color:var(--negro); font:16px/1.55 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif; -webkit-text-size-adjust:100%; }
a { color:var(--negro); }
.ancho { max-width:1120px; margin:0 auto; padding:0 16px; }
.cima { display:flex; justify-content:space-between; gap:12px; padding-top:18px; font-size:13px; }
.cima a { font-weight:600; white-space:nowrap; }
.portada { padding-top:40px; padding-bottom:8px; }
h1 { font:700 clamp(30px,6vw,48px)/1.06 var(--serif); letter-spacing:-0.02em; margin:0 0 14px; text-wrap:balance; }
.entrada { font-size:17px; margin:0 0 28px; max-width:60ch; }
.dato { display:flex; align-items:baseline; gap:16px; flex-wrap:wrap; border-top:3px solid var(--negro); border-bottom:1px solid var(--negro); padding:14px 0; }
.dato b { font:700 clamp(60px,13vw,96px)/0.85 var(--serif); font-variant-numeric:tabular-nums; }
.dato span { font-size:18px; max-width:24ch; line-height:1.3; }
.resto { font-size:14px; color:var(--gris); margin:10px 0 0; }
.pegado { position:sticky; top:0; z-index:5; background:var(--blanco); border-bottom:1px solid var(--negro); padding:10px 0; margin-top:22px; }
.fila { display:flex; gap:8px; overflow-x:auto; scrollbar-width:none; }
.fila::-webkit-scrollbar { display:none; }
.fila button { flex:none; font:inherit; font-size:13px; font-weight:600; color:var(--negro); background:var(--blanco);
  border:1.5px solid var(--negro); border-radius:999px; padding:5px 14px; cursor:pointer; }
.fila button[aria-pressed=true] { background:var(--negro); color:var(--blanco); }
.fila b { font-weight:500; opacity:.65; font-variant-numeric:tabular-nums; }

.linea { list-style:none; margin:0; padding:28px 0 40px; position:relative; }
.linea::before { content:""; position:absolute; top:0; bottom:0; left:var(--col); width:2px; background:var(--negro); }
.linea > li { position:relative; display:grid; grid-template-columns:var(--col) var(--hueco) minmax(0,1fr); align-items:start; }
.minuto { grid-column:1; justify-self:end; margin-right:22px; font-weight:700; font-size:17px; font-variant-numeric:tabular-nums;
  text-underline-offset:3px; white-space:nowrap; }
.hito { padding:14px 0; }
.dicho { grid-column:1; text-align:right; padding:15px 22px 0 0; }
.dicho .minuto { margin:0; }
.dicho blockquote { margin:8px 0 0; font-size:17px; }
.panel blockquote.movil { display:none; }
.minuto:hover { background:var(--negro); color:var(--blanco); text-decoration:none; }
.punto { position:absolute; left:calc(var(--col) - 6px); top:36px; width:14px; height:14px; border-radius:50%;
  background:var(--blanco); border:2px solid var(--negro); }
[data-v=falso] .punto { background:var(--negro); width:18px; height:18px; left:calc(var(--col) - 8px); top:34px; }
.flecha { grid-column:2; height:2px; background:var(--negro); margin:42px 9px 0 10px; position:relative; }
.flecha::after { content:""; position:absolute; right:-9px; top:-5px; border-left:10px solid var(--negro);
  border-top:6px solid transparent; border-bottom:6px solid transparent; }
.panel { grid-column:3; border:2px solid var(--negro); padding:16px 18px; background:var(--blanco); }
[data-v=falso] .panel { box-shadow:5px 5px 0 var(--negro); }
.ficha { display:inline-block; margin:0 0 10px; font-size:11.5px; font-weight:700; text-transform:uppercase; letter-spacing:.09em;
  border:1.5px solid var(--negro); padding:2px 9px; }
[data-v=falso] .ficha { background:var(--negro); color:var(--blanco); }
blockquote { margin:0 0 8px; font:italic 19px/1.38 var(--serif); text-wrap:pretty; }
.que { margin:0 0 12px; font-size:14px; color:var(--gris); line-height:1.45; }
.porque { margin:0 0 12px; font-size:15.5px; }
.rotulo { margin:0 0 4px; font-size:11px; font-weight:700; text-transform:uppercase; letter-spacing:.09em; }
.fuentes { margin:0; padding-left:20px; font-size:13.5px; }
.fuentes li { margin:3px 0; overflow-wrap:anywhere; }
.fuentes span { color:var(--gris); font-size:12px; white-space:nowrap; }
details { margin-top:10px; font-size:14px; border-top:1px solid var(--claro); padding-top:8px; }
summary { cursor:pointer; font-size:13px; font-weight:600; }
details p { margin:8px 0 0; }
/* veredictos que no son falso ni engañoso: discretos */
.hito:not([data-v=falso]):not([data-v=enganoso]) .punto { width:10px; height:10px; left:calc(var(--col) - 4px); top:38px; border-color:var(--gris); }
.hito:not([data-v=falso]):not([data-v=enganoso]) .panel { border:1px solid var(--gris); }
.hito:not([data-v=falso]):not([data-v=enganoso]) .ficha { border-color:var(--gris); color:var(--gris); }
.hito:not([data-v=falso]):not([data-v=enganoso]) .flecha { background:var(--gris); height:1px; }
.hito:not([data-v=falso]):not([data-v=enganoso]) .flecha::after { border-left-color:var(--gris); }
.hito:not([data-v=falso]):not([data-v=enganoso]) .minuto { font-weight:500; }

.capitulo { padding:30px 0 8px; }
.capitulo .minuto { font-weight:500; font-size:13px; margin-top:5px; color:var(--gris); }
.marca { position:absolute; left:calc(var(--col) - 9px); top:38px; width:20px; height:4px; background:var(--negro); }
.capitulo > div { grid-column:2 / 4; padding-left:22px; }
h2 { font:700 23px/1.2 var(--serif); margin:0; letter-spacing:-0.01em; text-wrap:balance; }
.capitulo p { margin:3px 0 0; font-size:13px; color:var(--gris); }
[hidden] { display:none !important; }
/* color del minuto según el veredicto */
.hito { --tono:#777; } .hito[data-v=falso] { --tono:#c0271e; } .hito[data-v=enganoso] { --tono:#c26a00; }
.hito[data-v=mayormente_verdadero] { --tono:#5a7d10; } .hito[data-v=verdadero] { --tono:#1c7c45; }
.hito .minuto { color:var(--tono); } .hito .minuto:hover { background:var(--tono); color:#fff; }
.hito .punto { border-color:var(--tono) !important; } .hito[data-v=falso] .punto { background:var(--tono); }
.hito .ficha { border-color:var(--tono) !important; color:var(--tono) !important; }
.hito[data-v=falso] .ficha { background:var(--tono); color:#fff !important; }
.leyenda { display:flex; flex-wrap:wrap; gap:4px 16px; font-size:12.5px; margin-top:8px; }
.leyenda span { display:inline-flex; align-items:center; gap:6px; font-weight:600; }
.leyenda i { width:10px; height:10px; border-radius:50%; background:currentColor; }

footer { border-top:3px solid var(--negro); padding:28px 0 72px; font-size:14.5px; }
footer h2 { font-size:20px; margin-bottom:10px; }
footer p { max-width:68ch; }
.repo { display:inline-block; margin:6px 0 14px; padding:9px 16px; background:var(--negro); color:var(--blanco); text-decoration:none; font-weight:600; }
@media (max-width:860px) { :root { --col:72px; --hueco:26px; } .minuto { margin-right:10px; font-size:13px; }
  .dicho { padding-right:10px; } .dicho blockquote { display:none; } .panel blockquote.movil { display:block; }
  .flecha { margin-left:8px; margin-right:8px; } .panel { padding:13px 13px; } blockquote { font-size:17px; }
  .capitulo > div { padding-left:16px; } h2 { font-size:20px; } }
.abrir { margin:14px 0 0; padding:12px 14px; border:1.5px solid #000; font-size:14.5px; max-width:78ch; }
.contrasta { margin:12px 0 0; }
.copiar { font:inherit; font-size:12.5px; font-weight:600; background:#fff; color:#000; border:1.5px solid #000; padding:4px 11px; cursor:pointer; }
.copiar:hover, .copiar.hecho { background:#000; color:#fff; }
.hito:target .panel { outline:3px solid var(--tono); outline-offset:3px; }
@@CSS_MENU@@
</style>
</head>
<body>
@@MENU@@
<div class="ancho portada">
  <h1>@@INVITADO@@ con Jordi Wild, minuto a minuto</h1>
  <p class="entrada">Hemos transcrito la <a href="https://www.youtube.com/watch?v=@@VIDEO@@" target="_blank" rel="noopener noreferrer">entrevista completa</a> (@@DURACION@@) y contrastado con fuentes públicas las @@SUMA@@ afirmaciones que se pueden comprobar. Esta es la línea temporal: pulsa cualquier minuto para ver ese momento del vídeo, o lee la <a href="/@@SLUG@@/transcripcion">transcripción completa</a>.</p>
  <div class="dato"><b>@@MALAS@@</b><span>afirmaciones falsas (@@FALSAS@@) o engañosas (@@ENGANOSAS@@) de @@SUMA@@ comprobadas</span></div>
  <p class="resto">El resto: @@VERDADERAS@@ verdaderas, @@CASI@@ casi ciertas y @@NV@@ que no se han podido verificar.</p>
  <p class="abrir"><b>Contrástalo tú mismo.</b> Cada panel enlaza el vídeo y sus fuentes, y trae un botón que copia un encargo listo para pegar en cualquier IA. También puedes descargar <a href="/api/v1/@@SLUG@@.json">todos los datos de esta entrevista (JSON)</a>, usar la <a href="/api">API abierta</a> o leer el <a href="@@REPO@@/blob/main/METODO.md" target="_blank" rel="noopener noreferrer">método</a>.</p>
</div>
@@FILTROS@@
<main class="ancho"><ol class="linea">@@FILAS@@</ol></main>
<footer><div class="ancho">
  <h2>Cómo se ha hecho</h2>
  <p>El audio se transcribió con Whisper y las afirmaciones se extrajeron y contrastaron con modelos de IA (Claude) con búsqueda web, un bloque por cada tema del vídeo. No lo ha revisado un equipo de periodistas: es un punto de partida. Por eso cada panel enlaza el segundo exacto del vídeo y sus fuentes, y todo el material está publicado.</p>
  <a class="repo" href="@@REPO@@" target="_blank" rel="noopener noreferrer">Ver código, transcripción y datos en GitHub ↗</a>
  <p><b>Falso</b>: los datos lo contradicen. <b>Engañoso</b>: se apoya en algo real pero omite contexto o lleva a una conclusión que no se sigue. <b>No verificable</b>: no se encontró prueba pública suficiente; a veces porque la búsqueda se quedó corta, no porque el dato no exista. «Falso» no implica intención de mentir: incluye errores y lapsus. Solo se evalúan hechos, no opiniones ni promesas, y solo lo que dice el entrevistado.</p>
  <p>¿Ves un error? Abre una incidencia en el repositorio. Última actualización: @@FECHA@@.</p>
</div></footer>
<script>
const activos = new Set(["falso", "enganoso"]);
const botones = document.querySelectorAll("#filtros button[data-v]");
const todas = document.querySelector("#filtros [data-todas]");
const aqui = location.pathname.replace(/\\/$/, "");
function pintar() {
  botones.forEach(b => b.setAttribute("aria-pressed", activos.has(b.dataset.v)));
  todas.setAttribute("aria-pressed", activos.size === botones.length);
  let cap = null, n = 0;
  document.querySelectorAll(".linea > li").forEach(li => {
    if (li.classList.contains("capitulo")) { if (cap) cap.hidden = n === 0; cap = li; n = 0; }
    else { li.hidden = !activos.has(li.dataset.v); if (!li.hidden) n++; }
  });
  if (cap) cap.hidden = n === 0;
  document.querySelectorAll(".lista a[data-tema]").forEach(a => {
    if (a.pathname.replace(/\\/$/, "") === aqui) a.classList.toggle("off", document.getElementById(a.dataset.tema).hidden);
  });
}
function verTodo() { botones.forEach(b => activos.add(b.dataset.v)); }
botones.forEach(b => b.onclick = () => {
  const v = b.dataset.v;
  if (activos.has(v) && activos.size > 1) activos.delete(v); else activos.add(v);
  pintar();
});
todas.onclick = () => {
  if (activos.size === botones.length) { activos.clear(); activos.add("falso"); activos.add("enganoso"); } else verTodo();
  pintar();
};
function irAlAncla() {
  const d = location.hash.length > 1 && document.getElementById(location.hash.slice(1));
  if (!d) return;
  if (d.hidden) { if (d.dataset.v) activos.add(d.dataset.v); else verTodo(); pintar(); }
  d.scrollIntoView();
}
pintar(); irAlAncla();
addEventListener("hashchange", irAlAncla);
document.addEventListener("click", ev => {
  const b = ev.target.closest(".copiar");
  if (!b) return;
  const h = b.closest(".hito"), t = sel => (h.querySelector(sel)?.textContent || "").trim();
  const fuentes = [...h.querySelectorAll(".fuentes a")].map(a => "- " + a.textContent.trim() + ": " + a.href).join("\\n");
  const texto = `Actúa como verificador de datos riguroso e imparcial.

En la entrevista de Jordi Wild a @@INVITADO@@ (@@PROGRAMA@@, @@FECHA_VIDEO@@), en el minuto ${t(".minuto")} (${h.querySelector(".minuto").href}), se dijo literalmente:
${t(".dicho blockquote")}

Afirmación que se comprueba: ${t(".que")}

Una verificación automática (@@BASE@@/@@SLUG@@#${h.id}) la calificó como «${t(".ficha")}». Su justificación:
${t("details p") || t(".porque")}

Fuentes que cita:
${fuentes || "(ninguna)"}

Comprueba por tu cuenta si ese veredicto es correcto: abre esas fuentes y mira si de verdad dicen lo que se les atribuye, busca al menos dos fuentes independientes más (mejor primarias y oficiales) y ten en cuenta el contexto de la frase. Dime si estás de acuerdo con el veredicto, en qué discrepas y con qué enlaces lo sustentas. Si no hay pruebas suficientes, dilo.`;
  const hecho = () => { b.textContent = "Copiado: pégalo en tu IA"; b.classList.add("hecho");
    setTimeout(() => { b.textContent = "Copiar encargo para contrastarlo con una IA"; b.classList.remove("hecho"); }, 2200); };
  if (navigator.clipboard) navigator.clipboard.writeText(texto).then(hecho, () => prompt("Copia este texto:", texto));
  else prompt("Copia este texto:", texto);
});
</script>
</body>
</html>
"""

if __name__ == "__main__":
    main()
