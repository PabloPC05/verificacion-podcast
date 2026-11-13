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
        f'<li class="hito" data-v="{v}" id="m{s}">'
        f'<div class="dicho"><a class="minuto" href="{enlace}" target="_blank" rel="noopener noreferrer" '
        f'title="Abrir el vídeo en este momento">{hms(s)}</a>'
        + (f'<blockquote>«{e(cita)}»</blockquote>' if cita else "") + "</div>"
        f'<span class="punto" aria-hidden="true"></span><span class="flecha" aria-hidden="true"></span>'
        f'<article class="panel"><p class="ficha">{NOMBRE[v]}</p>'
        + (f'<blockquote class="movil">«{e(cita)}»</blockquote>' if cita else "")
        + f'<p class="que">{e(a.get("afirmacion", ""))}</p>'
        f'<p class="porque"><b>Por qué:</b> {e(resumen)}</p>'
        + (f'<p class="rotulo">Fuentes</p><ol class="fuentes">{lista}</ol>' if lista else "")
        + detalle + "</article></li>"
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


def menu(metas, actual=None, vista="", filas=""):
    """Menú superior fijo: entrevistas, transcripción, y (en la línea temporal) filtros y temas."""
    enlaces = "".join(
        (f'<a href="/{e(m["slug"])}"' + (' aria-current="page"' if m["slug"] == actual else "") + f'>{e(m["invitado"])}</a>')
        if m.get("publicar") else f'<span class="off" title="Verificación en curso">{e(m["invitado"])}</span>'
        for m in metas)
    vistas = ""
    if actual:
        vistas = (f'<a href="/{actual}"' + (' aria-current="page"' if vista == "linea" else "") + '>Línea temporal</a>'
                  f'<a href="/{actual}/transcripcion"' + (' aria-current="page"' if vista == "texto" else "")
                  + '>Transcripción completa</a>')
    return (f'<header class="menu"><div class="ancho"><div class="m1"><a class="sello" href="/" title="Todas las entrevistas">Verificación</a>'
            f'<nav aria-label="Entrevistas"><span class="rot">Entrevistas</span>{enlaces}</nav>'
            + (f'<nav aria-label="Vistas"><span class="rot">Ver</span>{vistas}</nav>' if vistas else "")
            + f'<a class="dcha" href="{REPO}" target="_blank" rel="noopener noreferrer">GitHub ↗</a></div>{filas}</div></header>')


def pagina_entrevista(carpeta, meta, metas):
    todas = cargar(carpeta, meta)
    capitulos = json.loads((carpeta / "capitulos.json").read_text(encoding="utf-8"))
    if not capitulos:
        capitulos = [{"start_time": 0, "end_time": 10 ** 9, "title": "Entrevista completa"}]
    total = {k: sum(a["veredicto"] == k for a in todas) for k in ORDEN}
    filas, temas = [], []
    for n, c in enumerate(capitulos, 1):
        ini, fin = int(c["start_time"]), int(c["end_time"])
        suyas = [a for a in todas if ini <= a["_t"] < fin or (c is capitulos[-1] and a["_t"] >= fin)]
        malas = sum(a["veredicto"] in ("falso", "enganoso") for a in suyas)
        temas.append({"n": n, "titulo": c["title"], "malas": malas, "total": len(suyas), "ini": ini})
        nota = f"{malas} falsas o engañosas" if malas != 1 else "1 falsa o engañosa"
        filas.append(
            f'<li class="capitulo" id="tema-{n}">'
            f'<a class="minuto" href="https://www.youtube.com/watch?v={meta["video"]}&t={ini}s" target="_blank" '
            f'rel="noopener noreferrer">{hms(ini)}</a><span class="marca" aria-hidden="true"></span>'
            f'<div><h2>{e(c["title"])}</h2><p>{nota} · {len(suyas)} afirmaciones comprobadas</p></div></li>')
        filas += [panel(a) for a in suyas]
    malas = total["falso"] + total["enganoso"]
    f_filtros = ('<div class="fila" id="filtros"><span class="rot">Filtros</span>'
                 f'<button data-todas aria-pressed="false">Todas <b>{len(todas)}</b></button>'
                 + "".join(f'<button data-v="{k}" style="--tono:{TONO[k]}" aria-pressed="false"><i></i>{PLURAL[k]} <b>{total[k]}</b></button>'
                           for k in ORDEN) + "</div>")
    f_temas = ('<nav class="fila" id="temas" aria-label="Temas"><span class="rot">Temas</span>'
               + "".join(f'<a href="#tema-{t["n"]}">{e(t["titulo"])}' + (f' <b>{t["malas"]}</b>' if t["malas"] else "") + "</a>"
                         for t in temas if t["total"]) + "</nav>")
    pagina = (PLANTILLA
              .replace("@@MENU@@", menu(metas, meta["slug"], "linea", f_filtros + f_temas)).replace("@@CSS_MENU@@", CSS_MENU)
              .replace("@@SUMA@@", str(len(todas))).replace("@@MALAS@@", str(malas))
              .replace("@@FALSAS@@", str(total["falso"])).replace("@@ENGANOSAS@@", str(total["enganoso"]))
              .replace("@@CASI@@", str(total["mayormente_verdadero"])).replace("@@VERDADERAS@@", str(total["verdadero"]))
              .replace("@@NV@@", str(total["no_verificable"])).replace("@@FILAS@@", "".join(filas))
              .replace("@@INVITADO@@", e(meta["invitado"])).replace("@@PROGRAMA@@", e(meta["programa"]))
              .replace("@@FECHA_VIDEO@@", e(meta["fecha"])).replace("@@DURACION@@", e(meta["duracion"]))
              .replace("@@FECHA@@", dt.datetime.now().strftime("%d/%m/%Y")).replace("@@VIDEO@@", meta["video"])
              .replace("@@SLUG@@", meta["slug"]).replace("@@REPO@@", REPO))
    destino = SALIDA / meta["slug"]
    destino.mkdir(parents=True, exist_ok=True)
    (destino / "index.html").write_text(pagina, encoding="utf-8")
    pagina_transcripcion(carpeta, meta, metas, todas, capitulos)
    print(f'{meta["slug"]}: {len(todas)} afirmaciones · {total}')
    return dict(meta, total=total, suma=len(todas), malas=malas, temas=temas)


def pagina_transcripcion(carpeta, meta, metas, todas, capitulos):
    parrafos = []
    for linea in (carpeta / "transcripcion.txt").read_text(encoding="utf-8").splitlines():
        m = re.match(r"\[(\d+:\d\d:\d\d)\]\s*(.*)", linea)
        if m:
            parrafos.append((segundos(m.group(1)), m.group(2)))
    pendientes = list(enumerate(capitulos, 1))
    cuerpo, indice = [], []
    for k, (t, texto) in enumerate(parrafos):
        fin = parrafos[k + 1][0] if k + 1 < len(parrafos) else 10 ** 9
        while pendientes and int(pendientes[0][1]["start_time"]) < fin:
            n, c = pendientes.pop(0)
            cuerpo.append(f'<h2 id="tema-{n}">{e(c["title"])}</h2>')
            indice.append(f'<a href="#tema-{n}">{e(c["title"])}</a>')
        marcas = "".join(
            f'<a class="chip" style="--tono:{TONO[a["veredicto"]]}" href="/{meta["slug"]}#m{a["_t"]}" '
            f'title="{e(a.get("afirmacion", ""), quote=True)}">{hms(a["_t"])} · {NOMBRE[a["veredicto"]]}</a>'
            for a in todas if t <= a["_t"] < fin)
        cuerpo.append(
            f'<div class="par" id="t{t}"><a class="minuto" href="https://www.youtube.com/watch?v={meta["video"]}&t={t}s" '
            f'target="_blank" rel="noopener noreferrer">{hms(t)}</a><div><p>{e(texto)}</p>'
            + (f'<p class="chips">{marcas}</p>' if marcas else "") + "</div></div>")
    f_temas = '<nav class="fila" id="temas" aria-label="Temas"><span class="rot">Temas</span>' + "".join(indice) + "</nav>"
    pagina = (TRANSCRIPCION
              .replace("@@MENU@@", menu(metas, meta["slug"], "texto", f_temas)).replace("@@CSS_MENU@@", CSS_MENU)
              .replace("@@CUERPO@@", "".join(cuerpo)).replace("@@INVITADO@@", e(meta["invitado"]))
              .replace("@@PROGRAMA@@", e(meta["programa"])).replace("@@FECHA_VIDEO@@", e(meta["fecha"]))
              .replace("@@DURACION@@", e(meta["duracion"])).replace("@@VIDEO@@", meta["video"])
              .replace("@@SLUG@@", meta["slug"]).replace("@@REPO@@", REPO))
    destino = SALIDA / meta["slug"] / "transcripcion"
    destino.mkdir(parents=True, exist_ok=True)
    (destino / "index.html").write_text(pagina, encoding="utf-8")


def main():
    metas = [json.loads(r.read_text(encoding="utf-8")) for r in sorted(ENTREVISTAS.glob("*/meta.json"))]
    metas.sort(key=lambda m: m.get("programa", ""), reverse=True)
    hechas = []
    for meta in metas:
        carpeta = ENTREVISTAS / meta["slug"]
        if not meta.get("publicar") or not any((carpeta / "resultados").glob("*.json")):
            meta["publicar"] = False
            print(f'{meta["slug"]}: verificación en curso (meta.json sin "publicar": true), se omite')
    for meta in metas:
        if meta.get("publicar"):
            hechas.append(pagina_entrevista(ENTREVISTAS / meta["slug"], meta, metas))
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
        f'<p class="des">Verificación en curso.</p></article>' for m in metas if not m.get("publicar"))
    portada = (PORTADA.replace("@@MENU@@", menu(metas)).replace("@@CSS_MENU@@", CSS_MENU)
               .replace("@@TARJETAS@@", tarjetas).replace("@@REPO@@", REPO)
               .replace("@@FECHA@@", dt.datetime.now().strftime("%d/%m/%Y")))
    SALIDA.mkdir(exist_ok=True)
    (SALIDA / "index.html").write_text(portada, encoding="utf-8")


CSS_MENU = """
html { scroll-behavior:smooth; scroll-padding-top:150px; }
.menu { position:sticky; top:0; z-index:10; background:#fff; border-bottom:2px solid #000; }
.menu .ancho { padding-top:8px; padding-bottom:8px; }
.m1, .menu .fila { display:flex; align-items:center; gap:8px; overflow-x:auto; scrollbar-width:none; white-space:nowrap; }
.m1::-webkit-scrollbar, .menu .fila::-webkit-scrollbar { display:none; }
.m1 { gap:22px; font-size:14px; padding-bottom:2px; }
.m1 nav { display:flex; align-items:center; gap:14px; }
.m1 a { color:#000; text-decoration:none; font-weight:600; padding:3px 0; border-bottom:2px solid transparent; }
.m1 a:hover, .m1 a[aria-current] { border-bottom-color:#000; }
.m1 .sello { font:700 16px/1.2 "Iowan Old Style","Palatino Linotype",Palatino,Georgia,serif; }
.m1 .off { color:#999; } .m1 .dcha { margin-left:auto; }
.rot { font-size:10.5px; font-weight:700; text-transform:uppercase; letter-spacing:.09em; color:#666; flex:none; }
.menu .fila { margin-top:7px; }
.menu .fila button, .menu .fila a { flex:none; font:inherit; font-size:12.5px; font-weight:600; color:#000; background:#fff;
  border:1.5px solid #000; border-radius:999px; padding:3px 11px; cursor:pointer; text-decoration:none;
  display:inline-flex; align-items:center; gap:6px; }
.menu .fila b { font-weight:500; opacity:.7; font-variant-numeric:tabular-nums; }
.menu .fila button[data-v] { color:var(--tono); border-color:var(--tono); }
.menu .fila button[data-v] i { width:8px; height:8px; border-radius:50%; background:currentColor; }
.menu .fila button[aria-pressed=true] { background:#000; color:#fff; }
.menu .fila button[data-v][aria-pressed=true] { background:var(--tono); color:#fff; }
#temas a { border-color:#ccc; font-weight:500; }
#temas a:hover { border-color:#000; }
#temas a b { color:#c0271e; opacity:1; font-weight:700; }
#temas a.off { opacity:.4; }
@media (max-width:860px) { html { scroll-padding-top:140px; } .m1 { gap:16px; font-size:13px; } }
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
<main class="ancho">
<h1>Transcripción completa: @@INVITADO@@ con Jordi Wild</h1>
<p class="entrada">@@PROGRAMA@@ · @@FECHA_VIDEO@@ · @@DURACION@@. Transcripción automática (Whisper): no distingue quién habla y puede tener errores en nombres y cifras. Cada minuto abre el <a href="https://www.youtube.com/watch?v=@@VIDEO@@" target="_blank" rel="noopener noreferrer">vídeo</a> en ese punto; las etiquetas de color llevan a la afirmación verificada en la <a href="/@@SLUG@@">línea temporal</a>.</p>
@@CUERPO@@
</main>
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
</div>
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
function pintar() {
  botones.forEach(b => b.setAttribute("aria-pressed", activos.has(b.dataset.v)));
  todas.setAttribute("aria-pressed", activos.size === botones.length);
  let cap = null, n = 0;
  document.querySelectorAll(".linea > li").forEach(li => {
    if (li.classList.contains("capitulo")) { if (cap) cap.hidden = n === 0; cap = li; n = 0; }
    else { li.hidden = !activos.has(li.dataset.v); if (!li.hidden) n++; }
  });
  if (cap) cap.hidden = n === 0;
  document.querySelectorAll("#temas a").forEach(a => a.classList.toggle("off", document.querySelector(a.getAttribute("href")).hidden));
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
document.querySelectorAll("#temas a").forEach(a => a.addEventListener("click", () => {
  if (a.classList.contains("off")) { verTodo(); pintar(); }
}));
const destino = location.hash.length > 1 && document.getElementById(location.hash.slice(1));
if (destino && destino.dataset.v) activos.add(destino.dataset.v);
if (destino && destino.classList.contains("capitulo")) verTodo();
pintar();
if (destino) destino.scrollIntoView();
</script>
</body>
</html>
"""

if __name__ == "__main__":
    main()
