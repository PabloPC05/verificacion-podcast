#!/usr/bin/env python3
"""Genera la web estática (web/) a partir de entrevistas/<slug>/.

Cada entrevista necesita meta.json, segmentos.json, capitulos.json, resultados/*.json
y, opcionalmente, resumenes/*.json (un resumen por afirmación, en el mismo orden).

Uso: python3 web-src/build.py
"""
import bisect
import datetime as dt
import html
import json
import re
import shutil
import unicodedata
from pathlib import Path
from urllib.parse import urlparse

import api_publica

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
# En oscuro se usan tonos más claros (mismo matiz): sirven de texto sobre el fondo oscuro y, con tinta oscura encima, de relleno.
TONO_OSCURO = {"falso": "#ff6b5e", "enganoso": "#ff9a2e", "mayormente_verdadero": "#b8d63c",
               "verdadero": "#3fd083", "no_verificable": "#a4a4ac"}
PLURAL = {"falso": "Falsas", "enganoso": "Engañosas", "mayormente_verdadero": "Casi ciertas",
          "verdadero": "Verdaderas", "no_verificable": "No verificables"}


BASE = "https://verificacion-podcast.vercel.app"
SCALAR = "1.76.2"  # @scalar/api-reference, versión fijada: subirla a mano tras probar /api
# Huella SRI de dist/browser/standalone.js de esa versión. Si cambias SCALAR, recalcúlala:
#   curl -s https://cdn.jsdelivr.net/npm/@scalar/api-reference@<versión>/dist/browser/standalone.js \
#     | openssl dgst -sha384 -binary | openssl base64 -A
SCALAR_SRI = "sha384-mCh2A/B6vkfhiHyzwBZm7lbFmEK5fE/96Kbtk+RH1zei1P/XEt0I2MCiG6WfZdor"
LOGOS = {"PSOE": "psoe.svg", "PP": "pp.svg", "Frente Amplio": "frente-amplio.svg"}
DEFINICIONES = {
    "verdadero": "Los datos lo confirman.",
    "mayormente_verdadero": "Cierto en lo esencial, con una imprecisión menor.",
    "enganoso": "Se apoya en algo real pero omite contexto, mezcla periodos o lleva a una conclusión que no se sigue.",
    "falso": "Los datos lo contradicen. No implica intención de mentir: incluye errores y lapsus.",
    "no_verificable": "No se encontró prueba pública suficiente, o la búsqueda automática se quedó corta.",
}


def rellenar(plantilla, **valores):
    plantilla = plantilla.replace("@@HEAD_MODO@@", HEAD_MODO)
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
    # Afirmaciones irrelevantes para el debate público (criterio en excluidas.json y METODO.md): fuera de la web y
    # de los recuentos, pero se publican aparte. Se filtran después de dar los identificadores para que no cambien.
    ruta_excl = carpeta / "excluidas.json"
    excluidas = json.loads(ruta_excl.read_text(encoding="utf-8"))["excluidas"] if ruta_excl.exists() else []
    fuera = {x["id"] for x in excluidas}
    sobran = fuera - {a["_id"] for a in todas}
    if sobran:
        print(f'AVISO: {meta["slug"]}: excluidas.json cita identificadores que no existen: {sorted(sobran)}')
    todas = [a for a in todas if a["_id"] not in fuera]
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
                suma=len(todas), malas=total["falso"] + total["enganoso"], excluidas=excluidas)


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
            + "".join(partes) + '<a class="dcha" href="/verificalo">Verifícalo tú</a><a href="/api">API</a>'
            f'<a href="{REPO}" target="_blank" rel="noopener noreferrer">GitHub ↗</a>' + BOTON_MODO + '</div></div></header>' + JS_MENU)


JS_MENU = """<script>
document.addEventListener("click", ev => document.querySelectorAll("details.desp[open]").forEach(d => {
  if (!d.contains(ev.target) || ev.target.closest(".lista a")) d.open = false;
}));
document.addEventListener("keydown", ev => { if (ev.key === "Escape") document.querySelectorAll("details.desp[open]").forEach(d => d.open = false); });
const medirMenu = () => document.documentElement.style.setProperty("--menu", document.querySelector(".menu").offsetHeight + "px");
medirMenu(); addEventListener("resize", medirMenu);
// Modo claro/oscuro. Sin preferencia guardada manda el sistema (lo resuelve el CSS); al pulsar se guarda y manda sobre el sistema.
const RAIZ = document.documentElement, botonModo = document.querySelector(".modo"), sistemaOscuro = matchMedia("(prefers-color-scheme: dark)");
const hayOscuro = () => (RAIZ.dataset.modo || (sistemaOscuro.matches ? "oscuro" : "claro")) === "oscuro";
function etiquetarModo() {
  const t = hayOscuro() ? "Cambiar a modo claro" : "Cambiar a modo oscuro";
  botonModo.setAttribute("aria-label", t); botonModo.title = t;
}
// Revelado circular desde el botón (View Transitions API); sin la API o con poco movimiento, el cambio es instantáneo.
function revelarModo(cambiar) {
  if (!document.startViewTransition || matchMedia("(prefers-reduced-motion: reduce)").matches) { cambiar(); return; }
  const c = botonModo.getBoundingClientRect(), x = c.left + c.width / 2, y = c.top + c.height / 2;
  const r = Math.hypot(Math.max(x, innerWidth - x), Math.max(y, innerHeight - y));
  document.startViewTransition(cambiar).ready.then(() => RAIZ.animate(
    { clipPath: [`circle(0px at ${x}px ${y}px)`, `circle(${r}px at ${x}px ${y}px)`] },
    { duration: 420, easing: "cubic-bezier(0.4, 0, 0.2, 1)", pseudoElement: "::view-transition-new(root)" })).catch(() => {});
}
botonModo.onclick = () => {
  const nuevo = hayOscuro() ? "claro" : "oscuro";
  revelarModo(() => { RAIZ.dataset.modo = nuevo; etiquetarModo(); });
  try { localStorage.setItem("modo", nuevo); } catch (e) {}
};
sistemaOscuro.addEventListener("change", etiquetarModo);
etiquetarModo();
</script>"""

# Se ejecuta en el <head>, antes de pintar: aplica la preferencia guardada para que no haya parpadeo.
HEAD_MODO = ('<meta name="color-scheme" content="light dark">\n'
             '<script>try{var m=localStorage.getItem("modo");if(m==="claro"||m==="oscuro")document.documentElement.dataset.modo=m}catch(e){}</script>')
BOTON_MODO = ('<button class="modo" type="button" aria-label="Cambiar a modo oscuro" title="Cambiar a modo oscuro">'
              '<svg class="luna" viewBox="0 0 24 24" aria-hidden="true"><path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z"/></svg>'
              '<svg class="sol" viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="12" r="4"/>'
              '<path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"/></svg></button>')


def filtros(m, extra=""):
    return ('<div class="filtros"><div class="ancho"><div class="fila" id="filtros"><span class="rot">Filtros</span>'
            f'<button data-todas aria-pressed="false">Todas <b>{m["suma"]}</b></button>'
            + "".join(f'<button data-v="{k}" aria-pressed="false"><i></i>{PLURAL[k]} <b>{m["total"][k]}</b></button>'
                      for k in ORDEN) + extra + "</div></div></div>")


def pagina_entrevista(m, entrevistas):
    filas = []
    n_temas = len(m["temas"])
    singular = {"falso": "falsa", "enganoso": "engañosa", "mayormente_verdadero": "casi cierta",
                "verdadero": "verdadera", "no_verificable": "no verificable"}
    for t in m["temas"]:
        cuenta = {k: sum(a["veredicto"] == k for a in t["suyas"]) for k in ORDEN}
        recuento = " · ".join(
            f'<span class="tono-{k}">{cuenta[k]} {singular[k] if cuenta[k] == 1 else PLURAL[k].lower()}</span>'
            for k in ORDEN if cuenta[k])
        barra = "".join(f'<i class="tono-{k}" style="flex:{cuenta[k]}"></i>' for k in ORDEN if cuenta[k])
        fin = min(t["fin"], 10 ** 6)
        filas.append(
            f'<li class="capitulo" id="tema-{t["n"]}" data-etiqueta="Tema {t["n"]} · {e(t["titulo"], quote=True)}">'
            f'<a class="minuto" href="https://www.youtube.com/watch?v={m["video"]}&t={t["ini"]}s" target="_blank" '
            f'rel="noopener noreferrer">{hms(t["ini"])}</a><span class="marca" aria-hidden="true">{t["n"]}</span>'
            f'<div class="cab-tema"><p class="num-tema">Tema {t["n"]} de {n_temas} · {hms(t["ini"])} – {hms(fin)}</p>'
            f'<h2>{e(t["titulo"])}</h2><p class="recuento">{t["total"]} afirmaciones: {recuento}</p>'
            f'<div class="barra-tema" aria-hidden="true">{barra}</div></div></li>')
        filas += [panel(a) for a in t["suyas"]]
    excl = len(m["excluidas"])
    nota_excl = (f' Se han dejado fuera {excl} afirmaciones sin interés para el debate público (datos personales, anécdotas, '
                 f'duración de cargos); están en <a href="{REPO}/blob/main/entrevistas/{m["slug"]}/excluidas.json" target="_blank" '
                 f'rel="noopener noreferrer">esta lista</a>.') if excl else ""
    pagina = rellenar(
        PLANTILLA, MENU=menu(entrevistas, m["slug"]), CSS_MENU=CSS_MENU, LEYENDA=LEYENDA, NOTA_EXCL=nota_excl,
        FILTROS=filtros(m, '<span class="tema-actual" id="tema-actual"></span>'), SUMA=m["suma"], MALAS=m["malas"],
        FALSAS=m["total"]["falso"], ENGANOSAS=m["total"]["enganoso"], CASI=m["total"]["mayormente_verdadero"],
        VERDADERAS=m["total"]["verdadero"], NV=m["total"]["no_verificable"], FILAS="".join(filas),
        INVITADO=e(m["invitado"]), PROGRAMA=e(m["programa"]), FECHA_VIDEO=e(m["fecha"]), DURACION=e(m["duracion"]),
        FECHA=dt.datetime.now().strftime("%d/%m/%Y"), VIDEO=m["video"], SLUG=m["slug"], REPO=REPO, BASE=BASE)
    destino = SALIDA / m["slug"]
    destino.mkdir(parents=True, exist_ok=True)
    (destino / "index.html").write_text(pagina, encoding="utf-8")
    print(f'{m["slug"]}: {m["suma"]} afirmaciones · {m["total"]}')


def tramo_cita(a, indice):
    """Segmentos (índices de segmentos.json) que ocupa la cita de una afirmación, o None si no se encuentra."""
    texto, posiciones = indice
    inicios = [p for p, _ in posiciones]
    partes = [x for x in re.split(r"\[\s*(?:\.\.\.|…)\s*\]", a.get("cita", "")) if _norm(x)]
    if not partes:
        return None

    def ocurrencias(palabras, desde_el_final):
        for tam in (6, 5, 4, 3):
            if len(palabras) < tam:
                continue
            orden = range(len(palabras) - tam, -1, -1) if desde_el_final else range(len(palabras) - tam + 1)
            for k in orden:
                trozo = " ".join(palabras[k:k + tam])
                if len(trozo) < 10:
                    continue
                sitios = [mt.start() for mt in re.finditer(re.escape(trozo), texto)]
                if sitios:
                    return [(x, x + len(trozo)) for x in sitios]
        return []

    def segmento(pos):
        return max(0, bisect.bisect_right(inicios, pos) - 1)

    primeras = ocurrencias(_norm(partes[0]).split(), False)
    if not primeras:
        return None
    objetivo = a["_t"] + 2  # momento_exacto devuelve el inicio del segmento menos 2 s
    ini = min(primeras, key=lambda x: abs(posiciones[segmento(x[0])][1] - objetivo))[0]
    ultimas = [x for x in ocurrencias(_norm(partes[-1]).split(), True) if x[0] >= ini]
    fin = min(ultimas)[1] - 1 if ultimas else ini
    desde, hasta = segmento(ini), segmento(fin)
    return desde, min(hasta, desde + 25)


def pagina_transcripcion(m, entrevistas):
    """Transcripción por intervenciones (quién habla) con el tramo de cada afirmación subrayado en su color."""
    segmentos = json.loads((m["carpeta"] / "segmentos.json").read_text(encoding="utf-8"))
    ruta_h = m["carpeta"] / "hablantes.json"
    hablantes = json.loads(ruta_h.read_text(encoding="utf-8")) if ruta_h.exists() else None
    voces = [x["voz"] for x in hablantes["segmentos"]] if hablantes and len(hablantes["segmentos"]) == len(segmentos) else None
    nombres = hablantes["nombres"] if voces else {}

    # qué afirmación subraya cada segmento (si se solapan, la de peor veredicto)
    indice = indice_segmentos(m["carpeta"])
    marca, cierre, sin_tramo = {}, {}, 0
    for a in sorted(m["todas"], key=lambda a: ORDEN.index(a["veredicto"]), reverse=True):
        tramo = tramo_cita(a, indice)
        if tramo is None:
            sin_tramo += 1
            k = max(0, bisect.bisect_right([x["i"] for x in segmentos], a["_t"] + 2) - 1)
            tramo = (k, k)
        for k in range(tramo[0], tramo[1] + 1):
            marca[k] = a
        cierre.setdefault(tramo[1], []).append(a)
    if sin_tramo:
        print(f'{m["slug"]}: {sin_tramo} citas sin localizar en la transcripción (se marca el segmento de su minuto)')

    def texto_marcado(ks):
        """HTML de unos segmentos seguidos, agrupando en un solo subrayado los que son de la misma afirmación."""
        trozos, k0 = [], 0
        while k0 < len(ks):
            a = marca.get(ks[k0])
            k1 = k0
            while k1 + 1 < len(ks) and marca.get(ks[k1 + 1]) is a:
                k1 += 1
            texto = e(" ".join(segmentos[k]["t"].strip() for k in ks[k0:k1 + 1]))
            if a is None:
                trozos.append(texto)
            else:
                titulo = e(f'{NOMBRE[a["veredicto"]]}: {a.get("afirmacion", "")}', quote=True)
                trozos.append(f'<a class="subr" data-v="{a["veredicto"]}" href="/{m["slug"]}#{a["_id"]}" title="{titulo}">{texto}</a>')
            # una etiqueta por cada afirmación que termina en estos segmentos (aunque compartan subrayado con otra)
            for k in ks[k0:k1 + 1]:
                for b in sorted(cierre.get(k, []), key=lambda b: ORDEN.index(b["veredicto"])):
                    tit = e(f'{NOMBRE[b["veredicto"]]}: {b.get("afirmacion", "")}', quote=True)
                    trozos.append(f'<a class="et" data-v="{b["veredicto"]}" href="/{m["slug"]}#{b["_id"]}" title="{tit}">'
                                  f'{NOMBRE[b["veredicto"]]} ↗</a>')
            k0 = k1 + 1
        return " ".join(trozos)

    # intervenciones: segmentos seguidos de la misma voz, partidas en párrafos de ~1 minuto
    bloques, actual = [], None
    for k, sg in enumerate(segmentos):
        v = voces[k] if voces else None
        if actual is None or (voces and v != actual["voz"]):
            actual = {"voz": v, "parrafos": [[k]]}
            bloques.append(actual)
            continue
        parrafo = actual["parrafos"][-1]
        if sg["i"] - segmentos[parrafo[0]]["i"] >= 60 and segmentos[k - 1]["t"].rstrip()[-1:] in ".?!":
            actual["parrafos"].append([k])
        else:
            parrafo.append(k)
    pendientes = list(m["temas"])
    cuerpo = []
    for b in bloques:
        while pendientes and pendientes[0]["ini"] <= segmentos[b["parrafos"][0][0]]["i"] + 0.5:
            tema = pendientes.pop(0)
            cuerpo.append(f'<h2 id="tema-{tema["n"]}">{e(tema["titulo"])}</h2>')
        voz = b["voz"] or ""
        cuerpo.append(f'<div class="turno" data-voz="{voz}">')
        for n, p in enumerate(b["parrafos"]):
            t = int(segmentos[p[0]]["i"])
            quien = (f'<span class="quien">{e(nombres.get(voz, ""))}</span> ' if voces and n == 0 else "")
            cuerpo.append(
                f'<div class="par" id="t{t}"><a class="minuto" href="https://www.youtube.com/watch?v={m["video"]}&t={t}s" '
                f'target="_blank" rel="noopener noreferrer">{hms(t)}</a><p>{quien}{texto_marcado(p)}</p></div>')
        cuerpo.append("</div>")
    nota_voces = ("Las intervenciones se han atribuido a cada voz con reconocimiento automático de hablantes "
                  "(acierto medido del 97 %; las frases muy cortas son las que más fallan). " if voces else "")
    solo = '<button data-solo aria-pressed="false">Solo párrafos con afirmaciones</button>'
    pagina = rellenar(
        TRANSCRIPCION, MENU=menu(entrevistas, m["slug"]), CSS_MENU=CSS_MENU, LEYENDA=LEYENDA, FILTROS=filtros(m, solo),
        NOTA_VOCES=nota_voces, CUERPO="".join(cuerpo),
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
        "total_afirmaciones": m["suma"], "por_veredicto": m["total"], "excluidas": len(m.get("excluidas", [])),
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
        escribir_json(api / f'{m["slug"]}.json', dict(
            comun, entrevista=ficha_api(m), afirmaciones=suyas,
            excluidas=[dict(x, id=f'{m["slug"]}-{x["id"]}') for x in m.get("excluidas", [])]))
        api_publica.escribir_csv(api / f'{m["slug"]}.csv', suyas)
        segs = json.loads((m["carpeta"] / "segmentos.json").read_text(encoding="utf-8"))
        ruta_h = m["carpeta"] / "hablantes.json"
        h = json.loads(ruta_h.read_text(encoding="utf-8")) if ruta_h.exists() else None
        voces = ([h["nombres"][x["voz"]] for x in h["segmentos"]] if h and len(h["segmentos"]) == len(segs)
                 else [None] * len(segs))
        escribir_json(api / m["slug"] / "transcripcion.json", dict(
            comun, entrevista=ficha_api(m),
            nota="Transcripción automática (Whisper), que puede tener errores en nombres y cifras. El hablante de cada segmento sale de un reconocimiento automático de voces (acierto medido del 97 %; falla sobre todo en frases muy cortas).",
            segmentos=[{"inicio_s": round(x["i"], 2), "fin_s": round(x["f"], 2), "hablante": v, "texto": x["t"].strip()}
                       for x, v in zip(segs, voces)]))
        (api / m["slug"] / "transcripcion.txt").write_text(
            (m["carpeta"] / "transcripcion.txt").read_text(encoding="utf-8"), encoding="utf-8")
    escribir_json(api / "afirmaciones.json", dict(comun, total=len(todas), afirmaciones=todas))
    api_publica.escribir_csv(api / "afirmaciones.csv", todas)
    slugs = [m["slug"] for m in hechas]
    ejemplo = slugs[0] if slugs else "sanchez"
    escribir_json(api / "openapi.json", especificacion_openapi(hechas, ejemplo, aviso, comun))
    (SALIDA / "llms.txt").write_text(f"""# Verificación de las entrevistas electorales de The Wild Project

> Afirmaciones comprobables de los candidatos a las elecciones generales españolas del 29-11-2026 en sus entrevistas
> con Jordi Wild, cada una con veredicto, explicación, fuentes y enlace al segundo exacto del vídeo. {aviso}

API de solo lectura, JSON estático, sin clave, CORS abierto. Base: {BASE}/api/v1

- [Entrevistas]({BASE}/api/v1/entrevistas.json): lista de entrevistas, recuentos por veredicto y temas. Empieza aquí.
- [Todas las afirmaciones]({BASE}/api/v1/afirmaciones.json): un solo fichero con todas las afirmaciones verificadas.
- [Afirmaciones de una entrevista]({BASE}/api/v1/{ejemplo}.json): sustituye el slug ({", ".join(slugs)}).
- [Transcripción con tiempos]({BASE}/api/v1/{ejemplo}/transcripcion.json) y [en texto]({BASE}/api/v1/{ejemplo}/transcripcion.txt).
- [Todas las afirmaciones en CSV]({BASE}/api/v1/afirmaciones.csv) y por entrevista: {BASE}/api/v1/{ejemplo}.csv
- [OpenAPI]({BASE}/api/v1/openapi.json): esquemas de cada respuesta y ejemplos. Referencia legible y prompt para agentes de IA: {BASE}/api
- [Método y criterios]({REPO}/blob/main/METODO.md)

Campos de cada afirmación: id, entrevista, invitado, tema, segundo, minuto, video_url, web_url, cita (literal de la
transcripción), afirmacion (reformulada), veredicto (verdadero | mayormente_verdadero | enganoso | falso | no_verificable),
resumen, explicacion, confianza (alta | media | baja), fuentes [{{titulo, url}}].

Para volver a comprobar una afirmación: lee `cita` y `afirmacion`, abre cada `fuentes[].url`, y contrasta con la `explicacion`.
Los errores se comunican en {REPO}/issues.
""", encoding="utf-8")
    (SALIDA / "vercel.json").write_text(json.dumps({
        "redirects": [{"source": "/api/referencia", "destination": "/api", "permanent": True}],
        "headers": [
        {"source": "/api/(.*)", "headers": [{"key": "Access-Control-Allow-Origin", "value": "*"},
                                            {"key": "Cache-Control", "value": "public, max-age=300"}]},
        {"source": "/llms.txt", "headers": [{"key": "Access-Control-Allow-Origin", "value": "*"}]}]}, indent=1) + "\n")
    return ejemplo, slugs


# ───────────────────────── Descripción OpenAPI (la que pinta Scalar en /api) ─────────────────────────

def especificacion_openapi(hechas, ejemplo, aviso, comun):
    slugs = [m["slug"] for m in hechas]
    m_ej = next((m for m in hechas if m["slug"] == ejemplo), None)
    ficha_ej = ficha_api(m_ej) if m_ej else {}
    if ficha_ej:
        ficha_ej = dict(ficha_ej, temas=ficha_ej["temas"][:2])
    afirm_ej = [afirmacion_api(m_ej, a) for a in m_ej["todas"][:1]] if m_ej else []
    excl_ej = [dict(x, id=f'{m_ej["slug"]}-{x["id"]}') for x in m_ej.get("excluidas", [])[:1]] if m_ej else []
    segs_ej = []
    if m_ej:
        segs = json.loads((m_ej["carpeta"] / "segmentos.json").read_text(encoding="utf-8"))[:2]
        segs_ej = [{"inicio_s": round(x["i"], 2), "fin_s": round(x["f"], 2), "hablante": "Jordi Wild", "texto": x["t"].strip()} for x in segs]
    comun_ej = dict(comun, generado="2026-11-13T20:00:00+01:00")
    ref = lambda n: {"$ref": f"#/components/schemas/{n}"}
    url = {"type": "string", "format": "uri"}
    por_veredicto = {"type": "object", "description": "Número de afirmaciones con cada veredicto. Trae siempre las cinco claves.",
                     "required": ORDEN, "additionalProperties": False,
                     "properties": {k: {"type": "integer", "minimum": 0, "description": DEFINICIONES[k]} for k in ORDEN},
                     "example": m_ej["total"] if m_ej else None}
    tabla_veredictos = "\n".join(f"| `{k}` | {DEFINICIONES[k]} |" for k in ORDEN)
    descripcion = f"""API estática de solo lectura con todas las afirmaciones verificadas de las entrevistas de Jordi Wild a los
candidatos a las elecciones generales del 29 de noviembre de 2026: la cita literal, el veredicto, la explicación, las fuentes y el
segundo exacto del vídeo. También publica las transcripciones completas.

> {aviso}

## Cómo se usa

- **Sin clave ni registro.** Son ficheros JSON y CSV servidos por una CDN: basta con un `GET`.
- **CORS abierto** (`Access-Control-Allow-Origin: *`), así que se puede llamar desde el navegador.
- **Caché de 5 minutos** (`Cache-Control: public, max-age=300`). El campo `generado` dice cuándo se regeneraron los datos.
- **Sin paginación ni filtros en el servidor.** Cada fichero trae la colección entera; filtra en tu lado (con `jq`, por ejemplo).
- **Versión en la ruta** (`/v1`). Los campos nuevos se añaden sin cambiar de versión; si alguno cambia de significado o
  desaparece, saldrá `/v2` y `/v1` se mantendrá.

## Por dónde empezar

1. `GET /entrevistas.json` da la lista de entrevistas con su `slug` y sus recuentos.
2. Con el `slug`, `GET /{{slug}}.json` da las afirmaciones de esa entrevista. `GET /afirmaciones.json` las da todas juntas.
3. Para comprobar una afirmación, lee `cita` y `afirmacion`, abre cada `fuentes[].url` y contrasta con `explicacion`.
   Si quieres el contexto de lo que se dijo, `segundo` te lleva al punto de la transcripción.

## Veredictos

| Valor | Significado |
|---|---|
{tabla_veredictos}

## Errores

Una ruta que no existe (por ejemplo, un `slug` desconocido) devuelve `404` con una página HTML, no con JSON.
Si encuentras un dato mal verificado, abre una incidencia en [GitHub]({REPO}/issues).

## Para agentes de IA

En [{BASE}/api#agentes]({BASE}/api#agentes) hay un prompt listo para pegar en un agente: le explica estas rutas, qué
trae cada campo y cómo citar (id, minuto con su vídeo y fuentes). La guía breve para modelos está en [llms.txt]({BASE}/llms.txt).
"""
    def respuesta(desc, esquema, ejemplo_json):
        return {"200": {"description": desc, "content": {"application/json": {"schema": ref(esquema), "example": ejemplo_json}}}}
    cols = ", ".join(f"`{c}`" for c in api_publica.COLUMNAS)
    csv_desc = (f"Las mismas afirmaciones que el JSON, una fila por afirmación, en UTF-8 con BOM para que Excel muestre bien las tildes. "
                f"Columnas: {cols}. `fuentes` junta las URL separadas por ` | `. Sirve para `IMPORTDATA` de Google Sheets.")
    csv_ej = ",".join(api_publica.COLUMNAS) + "\n" + (",".join(f'"{x}"' if ("," in x or '"' in x) else x for x in (
        str(api_publica._fila(afirm_ej[0])[c]).replace('"', '""') for c in api_publica.COLUMNAS)) if afirm_ej else "") + "\n"
    no_existe = {"404": {"$ref": "#/components/responses/NoExiste"}}
    par = [{"$ref": "#/components/parameters/slug"}]
    return {
        "openapi": "3.1.0",
        "info": {"title": "Verificación de las entrevistas electorales de The Wild Project", "version": "1.0.0",
                 "summary": "Afirmaciones verificadas, fuentes y transcripciones, en JSON abierto.",
                 "description": descripcion,
                 "contact": {"name": "Incidencias en GitHub", "url": f"{REPO}/issues"}},
        "externalDocs": {"description": "Método y criterios de verificación", "url": f"{REPO}/blob/main/METODO.md"},
        "servers": [{"url": f"{BASE}/api/v1", "description": "Producción"}],
        "security": [],
        "tags": [
            {"name": "Entrevistas", "description": "Qué entrevistas hay, con sus recuentos por veredicto y por tema."},
            {"name": "Afirmaciones", "description": "Cada afirmación comprobable con su veredicto, explicación y fuentes."},
            {"name": "Transcripciones", "description": "La transcripción automática completa (Whisper), con tiempos."},
        ],
        "paths": {
            "/entrevistas.json": {"get": {
                "tags": ["Entrevistas"], "operationId": "listarEntrevistas", "summary": "Lista de entrevistas",
                "description": "Todas las entrevistas publicadas, con su ficha, el recuento por veredicto y el desglose por tema. "
                               "Es el punto de entrada: de aquí salen los `slug` y las URL del resto de recursos.",
                "responses": respuesta("Entrevistas publicadas.", "ListaEntrevistas",
                                       dict(comun_ej, entrevistas=[ficha_ej] if ficha_ej else []))}},
            "/afirmaciones.json": {"get": {
                "tags": ["Afirmaciones"], "operationId": "listarAfirmaciones", "summary": "Todas las afirmaciones",
                "description": "Todas las afirmaciones verificadas de todas las entrevistas en un solo fichero, en el orden en "
                               "que se dijeron dentro de cada entrevista.",
                "responses": respuesta("Todas las afirmaciones.", "TodasAfirmaciones",
                                       dict(comun_ej, total=sum(m["suma"] for m in hechas), afirmaciones=afirm_ej))}},
            "/{slug}.json": {"parameters": par, "get": {
                "tags": ["Afirmaciones"], "operationId": "afirmacionesDeEntrevista", "summary": "Afirmaciones de una entrevista",
                "description": "La ficha de la entrevista y sus afirmaciones verificadas, en orden de aparición en el vídeo.",
                "responses": dict(respuesta("Ficha y afirmaciones de la entrevista.", "AfirmacionesEntrevista",
                                            dict(comun_ej, entrevista=ficha_ej, afirmaciones=afirm_ej, excluidas=excl_ej)), **no_existe)}},
            "/afirmaciones.csv": {"get": {
                "tags": ["Afirmaciones"], "operationId": "afirmacionesCsv", "summary": "Todas las afirmaciones en CSV",
                "description": csv_desc,
                "responses": {"200": {"description": "CSV en UTF-8 con BOM.", "content": {"text/csv": {"schema": {"type": "string"}, "example": csv_ej}}}}}},
            "/{slug}.csv": {"parameters": par, "get": {
                "tags": ["Afirmaciones"], "operationId": "afirmacionesDeEntrevistaCsv", "summary": "Afirmaciones de una entrevista en CSV",
                "description": csv_desc,
                "responses": dict({"200": {"description": "CSV en UTF-8 con BOM.", "content": {"text/csv": {"schema": {"type": "string"}, "example": csv_ej}}}}, **no_existe)}},
            "/{slug}/transcripcion.json": {"parameters": par, "get": {
                "tags": ["Transcripciones"], "operationId": "transcripcionSegmentos", "summary": "Transcripción por segmentos",
                "description": "La transcripción automática partida en segmentos con su segundo de inicio y de fin, "
                               "y quién habla en cada uno según el reconocimiento automático de voces.",
                "responses": dict(respuesta("Transcripción por segmentos.", "Transcripcion", dict(
                    comun_ej, entrevista=ficha_ej,
                    nota="Transcripción automática (Whisper), que puede tener errores en nombres y cifras. El hablante de cada segmento sale de un reconocimiento automático de voces (acierto medido del 97 %; falla sobre todo en frases muy cortas).",
                    segmentos=segs_ej)), **no_existe)}},
            "/{slug}/transcripcion.txt": {"parameters": par, "get": {
                "tags": ["Transcripciones"], "operationId": "transcripcionTexto", "summary": "Transcripción en texto plano",
                "description": "La misma transcripción en párrafos, cada uno precedido de su marca de tiempo `[h:mm:ss]`. "
                               "Útil para pasársela entera a un modelo de lenguaje.",
                "responses": dict({"200": {"description": "Texto plano en UTF-8.", "content": {"text/plain": {
                    "schema": {"type": "string"},
                    "example": "[0:00:00] ¿Qué tal mi gente? ¿Cómo estamos?…\n\n[0:01:17] Siempre digo día histórico en The Wild Project…\n"}}}},
                    **no_existe)}},
        },
        "components": {
            "parameters": {"slug": {"name": "slug", "in": "path", "required": True,
                                    "description": "Identificador de la entrevista. Sale del campo `slug` de `/entrevistas.json`.",
                                    "schema": {"type": "string", "enum": slugs}, "example": ejemplo}},
            "responses": {"NoExiste": {"description": "No hay ninguna entrevista publicada con ese `slug`. La respuesta es una página HTML.",
                                       "content": {"text/html": {"schema": {"type": "string"}}}}},
            "schemas": {
                "Veredicto": {"type": "string", "enum": ORDEN,
                              "description": "Resultado de la verificación.\n\n" + "\n".join(f"- `{k}`: {DEFINICIONES[k]}" for k in ORDEN)},
                "Confianza": {"type": "string", "enum": ["alta", "media", "baja"],
                              "description": "Seguridad del verificador en su veredicto, según la calidad y la concordancia de las fuentes."},
                "PorVeredicto": por_veredicto,
                "Comun": {"type": "object", "description": "Campos que traen todas las respuestas JSON.",
                          "required": ["generado", "aviso", "veredictos", "metodo_url", "repositorio", "documentacion"],
                          "properties": {
                              "generado": {"type": "string", "format": "date-time", "description": "Cuándo se generó el fichero."},
                              "aviso": {"type": "string", "description": "Límites de la verificación. Muéstralo si reutilizas los datos."},
                              "veredictos": {"type": "object", "description": "Definición de cada veredicto.",
                                             "required": ORDEN, "properties": {k: {"type": "string"} for k in ORDEN}},
                              "metodo_url": dict(url, description="Método y criterios completos."),
                              "repositorio": dict(url, description="Repositorio con los datos y el código."),
                              "documentacion": dict(url, description="Esta documentación."),
                          }},
                "Tema": {"type": "object", "description": "Un capítulo de la entrevista.",
                         "required": ["n", "titulo", "inicio_s", "total", "por_veredicto"],
                         "properties": {
                             "n": {"type": "integer", "minimum": 1, "description": "Número del capítulo, desde 1."},
                             "titulo": {"type": "string", "description": "Título del capítulo."},
                             "inicio_s": {"type": "integer", "minimum": 0, "description": "Segundo del vídeo en que empieza."},
                             "total": {"type": "integer", "minimum": 0, "description": "Afirmaciones verificadas en el capítulo."},
                             "por_veredicto": ref("PorVeredicto"),
                         }},
                "Entrevista": {"type": "object", "description": "Ficha de una entrevista.",
                               "required": ["slug", "invitado", "partido", "programa", "fecha", "duracion", "video_url", "web_url",
                                            "afirmaciones_url", "transcripcion_url", "transcripcion_txt_url",
                                            "total_afirmaciones", "por_veredicto", "excluidas", "temas"],
                               "properties": {
                                   "slug": {"type": "string", "description": "Identificador para las rutas `/{slug}…`."},
                                   "invitado": {"type": "string", "description": "Nombre del candidato."},
                                   "partido": {"type": ["string", "null"], "description": "Partido o coalición."},
                                   "programa": {"type": "string", "description": "Programa y número de episodio."},
                                   "fecha": {"type": "string", "description": "Fecha de publicación del vídeo, en texto (`13 nov 2026`)."},
                                   "duracion": {"type": "string", "description": "Duración del vídeo, en texto (`1 h 52 min`)."},
                                   "video_url": dict(url, description="Vídeo en YouTube."),
                                   "web_url": dict(url, description="Línea temporal en la web."),
                                   "afirmaciones_url": dict(url, description="URL de `/{slug}.json`."),
                                   "transcripcion_url": dict(url, description="URL de `/{slug}/transcripcion.json`."),
                                   "transcripcion_txt_url": dict(url, description="URL de `/{slug}/transcripcion.txt`."),
                                   "total_afirmaciones": {"type": "integer", "minimum": 0,
                                                          "description": "Afirmaciones publicadas (sin contar las excluidas)."},
                                   "por_veredicto": ref("PorVeredicto"),
                                   "excluidas": {"type": "integer", "minimum": 0,
                                                 "description": "Afirmaciones comprobables que se han dejado fuera por no tener interés "
                                                                "público. La lista está en el campo `excluidas` de `/{slug}.json`."},
                                   "temas": {"type": "array", "items": ref("Tema"), "description": "Capítulos en orden, incluidos los que no tienen afirmaciones."},
                               }},
                "Fuente": {"type": "object", "required": ["titulo", "url"],
                           "properties": {"titulo": {"type": "string", "description": "Medio o organismo y título del documento."},
                                          "url": dict(url, description="Siempre `http` o `https`.")}},
                "Afirmacion": {"type": "object", "description": "Una afirmación comprobable del invitado y su verificación.",
                               "required": ["id", "entrevista", "invitado", "tema_n", "tema", "segundo", "minuto", "video_url",
                                            "web_url", "cita", "afirmacion", "veredicto", "resumen", "explicacion", "confianza", "fuentes"],
                               "properties": {
                                   "id": {"type": "string", "description": "Identificador estable: `slug` de la entrevista y segundo del vídeo (`sanchez-m251`)."},
                                   "entrevista": {"type": "string", "description": "`slug` de la entrevista."},
                                   "invitado": {"type": "string"},
                                   "tema_n": {"type": ["integer", "null"], "description": "Número del capítulo (`Tema.n`)."},
                                   "tema": {"type": ["string", "null"], "description": "Título del capítulo."},
                                   "segundo": {"type": "integer", "minimum": 0, "description": "Segundo del vídeo en que se dice."},
                                   "minuto": {"type": "string", "pattern": "^\\d+:\\d{2}:\\d{2}$", "description": "El mismo momento en `h:mm:ss`."},
                                   "video_url": dict(url, description="Vídeo en YouTube, ya situado en ese segundo."),
                                   "web_url": dict(url, description="Tarjeta de la afirmación en la web."),
                                   "cita": {"type": "string", "description": "Lo que se dijo, literal de la transcripción automática."},
                                   "afirmacion": {"type": "string", "description": "La afirmación reformulada para que se entienda sin contexto."},
                                   "veredicto": ref("Veredicto"),
                                   "resumen": {"type": ["string", "null"], "description": "La justificación en una frase (la que muestra la web)."},
                                   "explicacion": {"type": "string", "description": "La justificación completa."},
                                   "confianza": {"anyOf": [ref("Confianza"), {"type": "null"}]},
                                   "fuentes": {"type": "array", "items": ref("Fuente"),
                                               "description": "Fuentes que sustentan el veredicto. Puede venir vacía, sobre todo con `no_verificable`."},
                               }},
                "Segmento": {"type": "object", "required": ["inicio_s", "fin_s", "texto"],
                             "properties": {"inicio_s": {"type": "number", "minimum": 0, "description": "Segundo de inicio, con dos decimales."},
                                            "fin_s": {"type": "number", "minimum": 0, "description": "Segundo de fin."},
                                            "hablante": {"type": ["string", "null"],
                                                         "description": "Quién habla según el reconocimiento automático de voces: "
                                                                        "«Jordi Wild», el nombre del invitado, «Verificadores del programa» "
                                                                        "o «Voz sin identificar». Acierto medido del 97 %."},
                                            "texto": {"type": "string"}}},
                "ListaEntrevistas": {"allOf": [ref("Comun"), {"type": "object", "required": ["entrevistas"],
                                     "properties": {"entrevistas": {"type": "array", "items": ref("Entrevista")}}}]},
                "TodasAfirmaciones": {"allOf": [ref("Comun"), {"type": "object", "required": ["total", "afirmaciones"],
                                      "properties": {"total": {"type": "integer", "minimum": 0, "description": "Número de afirmaciones."},
                                                     "afirmaciones": {"type": "array", "items": ref("Afirmacion")}}}]},
                "Excluida": {"type": "object", "description": "Afirmación comprobable que no se publica por no tener interés público. "
                                                              "Conserva su veredicto original por transparencia.",
                             "required": ["id", "minuto", "afirmacion", "veredicto", "motivo"],
                             "properties": {
                                 "id": {"type": "string", "description": "Mismo formato que `Afirmacion.id` (`sanchez-m251`)."},
                                 "minuto": {"type": "string", "pattern": "^\\d+:\\d{2}:\\d{2}$"},
                                 "afirmacion": {"type": "string"},
                                 "veredicto": ref("Veredicto"),
                                 "motivo": {"type": "string", "description": "Uno de los cinco motivos de exclusión del método "
                                                                             "(dato biográfico, anécdota privada, duración de un cargo, "
                                                                             "logística de la campaña o curiosidad)."},
                             }},
                "AfirmacionesEntrevista": {"allOf": [ref("Comun"), {"type": "object", "required": ["entrevista", "afirmaciones", "excluidas"],
                                           "properties": {"entrevista": ref("Entrevista"),
                                                          "afirmaciones": {"type": "array", "items": ref("Afirmacion")},
                                                          "excluidas": {"type": "array", "items": ref("Excluida"),
                                                                        "description": "Afirmaciones dejadas fuera de `afirmaciones` y de "
                                                                                       "los recuentos por no tener interés público."}}}]},
                "Transcripcion": {"allOf": [ref("Comun"), {"type": "object", "required": ["entrevista", "nota", "segmentos"],
                                  "properties": {"entrevista": ref("Entrevista"),
                                                 "nota": {"type": "string", "description": "Límites de la transcripción automática."},
                                                 "segmentos": {"type": "array", "items": ref("Segmento")}}}]},
            },
        },
    }


def prompt_agente(hechas):
    """Prompt listo para que un agente de IA use la API. Se muestra en /api y se copia tal cual."""
    invitados = ", ".join(f'{m["invitado"]} ({m.get("partido") or "sin partido"})' for m in hechas)
    slugs = ", ".join(m["slug"] for m in hechas)
    veredictos = "\n".join(f"- {k}: {DEFINICIONES[k]}" for k in ORDEN)
    return f"""Tienes acceso a una API pública, de solo lectura y sin clave, con la verificación de las entrevistas de Jordi Wild (The Wild Project) a los candidatos a las elecciones generales españolas del 29 de noviembre de 2026: {invitados}. Úsala para responder a mis preguntas.

CÓMO CONSULTARLA (peticiones GET; responden JSON salvo que se indique otra cosa)
- {BASE}/api/v1/entrevistas.json: entrevistas, su slug, recuentos por veredicto y temas. Empieza aquí.
- {BASE}/api/v1/{{slug}}.json: afirmaciones verificadas de una entrevista (slugs: {slugs}), más la lista de excluidas por irrelevantes.
- {BASE}/api/v1/afirmaciones.json: todas las afirmaciones de todas las entrevistas.
- {BASE}/api/v1/{{slug}}/transcripcion.txt: transcripción completa con marcas [h:mm:ss], para ver el contexto de una frase.
- {BASE}/api/v1/afirmaciones.csv y {BASE}/api/v1/{{slug}}.csv: lo mismo en CSV.
- {BASE}/api/v1/openapi.json: esquema completo.
No hay filtros ni búsqueda en el servidor: descarga el fichero y filtra tú.

QUÉ TRAE CADA AFIRMACIÓN
id, invitado, tema, minuto, video_url (el vídeo en ese segundo), cita (literal de la transcripción), afirmacion (reformulada), veredicto, resumen, explicacion, confianza (alta, media o baja) y fuentes [{{titulo, url}}].
Veredictos:
{veredictos}

CÓMO RESPONDER
1. Consulta la API antes de contestar; no respondas de memoria sobre estas entrevistas.
2. De cada afirmación que menciones, da el id, el minuto con su video_url y al menos una de sus fuentes.
3. Separa lo que dice la verificación publicada de tu propia valoración. Si revisas un veredicto, abre las fuentes y dilo explícitamente.
4. Para comparar candidatos usa proporciones (por ejemplo, falsas o engañosas sobre el total de cada uno), no solo números absolutos: las entrevistas duran distinto y cada invitado da más o menos datos.
5. La verificación está hecha con IA y no la ha revisado un equipo de periodistas; «falso» no implica intención de mentir. Recuérdalo cuando sea relevante.
6. Aplica la misma vara de medir a todos los candidatos. No inventes ids, cifras ni enlaces: si la API no tiene el dato, dilo.

MI PETICIÓN
[Escribe aquí lo que quieres saber. Por ejemplo: «¿Qué afirmaciones falsas hizo cada candidato sobre inmigración? Dame el minuto y una fuente de cada una.»]"""


def comparativa(hechas):
    """Cuadro comparativo de los candidatos para la portada."""
    if len(hechas) < 2:
        return ""
    filas_v = [("falso", "Falsas"), ("enganoso", "Engañosas")]
    resto_v = [("mayormente_verdadero", "Casi ciertas"), ("verdadero", "Verdaderas"), ("no_verificable", "No verificables")]

    def pct(n, total):
        return f"{round(100 * n / total)} %" if total else "—"

    def horas(m):
        segs = json.loads((m["carpeta"] / "segmentos.json").read_text(encoding="utf-8"))
        return max((x["f"] for x in segs), default=0) / 3600

    def celda_n(m, n):
        return f'<td><b>{n}</b> <span class="pc">{pct(n, m["suma"])}</span></td>'

    def tema_top(m):
        t = max(m["temas"], key=lambda t: (t["malas"], -t["n"]))
        if not t["malas"]:
            return "<td>—</td>"
        return f'<td><a href="/{e(m["slug"])}#tema-{t["n"]}">{e(t["titulo"])}</a> <span class="pc">({t["malas"]})</span></td>'

    cab = "".join(
        f'<th scope="col"><a href="/{e(m["slug"])}"><span class="cand">{e(m["invitado"])}</span></a>'
        f'<span class="par">{e(m.get("partido") or "")}</span></th>' for m in hechas)
    filas = [
        ("Duración de la entrevista", "".join(f'<td>{e(m["duracion"])}</td>' for m in hechas), ""),
        ("Afirmaciones comprobadas", "".join(f'<td><b>{m["suma"]}</b></td>' for m in hechas), ""),
        ("Comprobadas por hora", "".join(f'<td>{m["suma"] / horas(m):.0f}</td>' if horas(m) else "<td>—</td>" for m in hechas), ""),
    ]
    filas += [(f'<i class="tono-{k}"></i>{nombre}', "".join(celda_n(m, m["total"][k]) for m in hechas), f' class="tono-{k}"')
              for k, nombre in filas_v]
    filas.append(("Falsas o engañosas", "".join(celda_n(m, m["malas"]) for m in hechas), ' class="fuerte"'))
    filas += [(f'<i class="tono-{k}"></i>{nombre}', "".join(celda_n(m, m["total"][k]) for m in hechas), f' class="tono-{k}"')
              for k, nombre in resto_v]
    filas.append(("Reparto", "".join(
        '<td><div class="reparto">' + "".join(f'<i class="tono-{k}" style="flex:{m["total"][k]}"></i>' for k in ORDEN if m["total"][k])
        + "</div></td>" for m in hechas), ""))
    filas.append(("Tema con más falsas o engañosas", "".join(tema_top(m) for m in hechas), ""))
    filas.append(("Excluidas por irrelevantes", "".join(f'<td>{len(m.get("excluidas", []))}</td>' for m in hechas), ""))
    cuerpo = "".join(f'<tr{clase}><th scope="row">{etiqueta}</th>{celdas}</tr>' for etiqueta, celdas, clase in filas)
    return (f'<section class="compara" aria-labelledby="compara-t"><h2 id="compara-t">Los {len(hechas)} candidatos, comparados</h2>'
            f'<div class="tabla-c"><table><thead><tr><td></td>{cab}</tr></thead><tbody>{cuerpo}</tbody></table></div>'
            '<p class="nota-c">Los porcentajes son sobre las afirmaciones comprobadas de cada candidato. Cuántas se pueden comprobar '
            'depende de la duración de la entrevista, de las preguntas y de cuántos datos da cada invitado, así que esto no es un ranking: '
            'sirve para ver dónde mirar. Cada cifra lleva a su línea temporal.</p></section>')


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
    for carpeta_logos in [RAIZ / "web-src" / "logos"]:
        (SALIDA / "logos").mkdir(exist_ok=True)
        for f in carpeta_logos.glob("*.svg"):
            shutil.copy(f, SALIDA / "logos" / f.name)

    def logo(m):
        partido = m.get("partido") or ""
        fichero = LOGOS.get(partido)
        if fichero:
            return f'<img class="logo" src="/logos/{fichero}" alt="Logotipo de {e(partido)}" width="76" height="76">'
        siglas = "".join(w[0] for w in partido.split()[:3]).upper() or "·"
        return f'<span class="logo sin" aria-hidden="true">{e(siglas)}</span>'

    tarjetas = "".join(
        f'<article class="entrevista">{logo(m)}<div><h2><a href="/{e(m["slug"])}">{e(m["invitado"])}</a></h2>'
        f'<p class="partido">{e(m.get("partido") or "")}</p>'
        f'<p class="prog">{e(m["programa"])} · {e(m["fecha"])} · {e(m["duracion"])}</p>'
        f'<p class="num"><b>{m["malas"]}</b> falsas o engañosas de {m["suma"]} afirmaciones comprobadas</p>'
        f'<p class="des">' + " · ".join(f'<span class="tono-{k}">{m["total"][k]} {PLURAL[k].lower()}</span>' for k in ORDEN) + "</p>"
        f'<p class="acc"><a href="/{e(m["slug"])}">Línea temporal →</a>'
        f'<a href="/{e(m["slug"])}/transcripcion">Transcripción completa →</a></p></div></article>'
        for m in hechas)
    tarjetas += "".join(
        f'<article class="entrevista off">{logo(m)}<div><h2>{e(m["invitado"])}</h2><p class="partido">{e(m.get("partido") or "")}</p>'
        f'<p class="prog">{e(m.get("programa", ""))}</p><p class="des">Verificación en curso.</p></div></article>'
        for m in entrevistas if not m.get("publicar"))
    (SALIDA / "index.html").write_text(rellenar(
        PORTADA, MENU=menu(entrevistas), CSS_MENU=CSS_MENU, LEYENDA=LEYENDA, COMPARATIVA=comparativa(hechas), TARJETAS=tarjetas, REPO=REPO,
        FECHA=dt.datetime.now().strftime("%d/%m/%Y")), encoding="utf-8")
    (SALIDA / "verificalo").mkdir(exist_ok=True)
    opciones = "".join(f'<option value="{e(m["slug"])}">{e(m["invitado"])}</option>' for m in hechas)
    (SALIDA / "verificalo" / "index.html").write_text(rellenar(
        VERIFICALO, SECCION_API=api_publica.SECCION_API, JS_API=api_publica.JS_API, CSS_API=api_publica.CSS_API,
        MENU=menu(entrevistas), CSS_MENU=CSS_MENU, LEYENDA=LEYENDA, BASE=BASE, REPO=REPO, OPCIONES=opciones,
        EJ=ejemplo, SLUGS=", ".join(f"<code>{x}</code>" for x in slugs)), encoding="utf-8")
    (SALIDA / "api").mkdir(exist_ok=True)
    (SALIDA / "api" / "index.html").write_text(rellenar(
        PAGINA_API, PROMPT=e(prompt_agente(hechas)), MENU=menu(entrevistas), CSS_MENU=CSS_MENU, BASE=BASE, REPO=REPO,
        SCALAR=SCALAR, SCALAR_SRI=SCALAR_SRI), encoding="utf-8")
    # La referencia vivió unas horas en /api/referencia: se redirige (aquí y en vercel.json).
    (SALIDA / "api" / "referencia").mkdir(exist_ok=True)
    (SALIDA / "api" / "referencia" / "index.html").write_text(REDIRIGE_API, encoding="utf-8")


LEYENDA = """<section class="leyenda-f" aria-label="Leyenda de veredictos">
<h2>Leyenda</h2>
<p class="ley-intro">El color del minuto, del punto de la línea y de la etiqueta indica el veredicto de cada afirmación.</p>
<dl>
<div class="tono-falso"><dt>Falso</dt><dd><b>Los datos lo contradicen.</b> Incluye errores y lapsus: no implica intención de mentir.</dd></div>
<div class="tono-enganoso"><dt>Engañoso</dt><dd><b>Parte de un dato real, pero confunde.</b> Omite contexto, mezcla periodos o lleva a una conclusión que no se sigue.</dd></div>
<div class="tono-mayormente_verdadero"><dt>Casi cierto</dt><dd><b>Cierto en lo esencial.</b> Tiene una imprecisión menor, como un redondeo o una fecha aproximada.</dd></div>
<div class="tono-verdadero"><dt>Verdadero</dt><dd><b>Los datos lo confirman.</b></dd></div>
<div class="tono-no_verificable"><dt>No verificable</dt><dd><b>Sin prueba pública suficiente.</b> No se puede confirmar ni desmentir, o la búsqueda automática se quedó corta.</dd></div>
</dl>
<ul class="ley-notas">
<li><b>Se evalúa:</b> hechos comprobables que afirma el entrevistado (cifras, fechas, leyes, lo que dijo o hizo alguien).</li>
<li><b>No se evalúa:</b> opiniones, promesas, predicciones ni lo que dice el entrevistador.</li>
<li><b>Confianza</b> (alta, media, baja): cuánta prueba respalda el veredicto.</li>
</ul>
</section>"""

# Colores como variables: el tema claro (el de siempre) en :root y el oscuro redefinido una sola vez.
# Sin preferencia guardada manda prefers-color-scheme; si la persona pulsa el botón, <html data-modo="claro|oscuro"> manda sobre el sistema.
def _tonos(paleta):
    return " ".join(f"--v-{k}:{v};" for k, v in paleta.items())


_CLARO = ("--fondo:#fff; --tinta:#000; --suave:#444; --gris:#666; --gris-claro:#999; --claro:#d9d9d9; --codigo:#f2f2f2; --resalte:#f3f3f3; "
          "--pre-fondo:#000; --pre-tinta:#fff; --pre-borde:transparent; --sombra:#000; --inv-suave:#ccc; --sobre-tono:#fff; "
          "--logo-fondo:transparent; --logo-radio:0; --luna:block; --sol:none; color-scheme:light; " + _tonos(TONO))
_OSCURO = ("--fondo:#121214; --tinta:#ececee; --suave:#bdbdc4; --gris:#a3a3aa; --gris-claro:#7c7c84; --claro:#3a3a40; --codigo:#26262b; --resalte:#26262b; "
           "--pre-fondo:#1c1c20; --pre-tinta:#ececee; --pre-borde:#3a3a40; --sombra:#55555c; --inv-suave:#55555c; --sobre-tono:#121214; "
           "--logo-fondo:#fff; --logo-radio:4px; --luna:none; --sol:block; color-scheme:dark; " + _tonos(TONO_OSCURO))
CSS_MENU = """
:root { @@CLARO@@ }
@media (prefers-color-scheme:dark) { :root:not([data-modo=claro]) { @@OSCURO@@ } }
:root[data-modo=oscuro] { @@OSCURO@@ }
@@CLASES_TONO@@
::view-transition-old(root), ::view-transition-new(root) { animation:none; mix-blend-mode:normal; }
html { scroll-behavior:smooth; scroll-padding-top:calc(var(--menu, 48px) + 64px); }
[hidden] { display:none !important; }
.menu { position:sticky; top:0; z-index:10; background:var(--fondo); border-bottom:2px solid var(--tinta); }
.menu .ancho { padding-top:9px; padding-bottom:9px; position:relative; }
.m1 { display:flex; flex-wrap:wrap; align-items:center; gap:4px 24px; font-size:14.5px; }
.m1 a, .desp summary { color:var(--tinta); text-decoration:none; font-weight:600; padding:3px 0; border-bottom:2px solid transparent; }
.m1 > a:hover, .desp.actual summary, .desp[open] summary, .desp summary:hover { border-bottom-color:var(--tinta); }
.m1 .sello { font:700 17px/1.2 "Iowan Old Style","Palatino Linotype",Palatino,Georgia,serif; }
.m1 .off { color:var(--gris-claro); } .m1 .dcha { margin-left:auto; }
.modo { flex:none; display:inline-grid; place-items:center; width:26px; height:26px; padding:0; margin:0 0 0 -8px; cursor:pointer;
  color:var(--tinta); background:var(--fondo); border:1.5px solid var(--tinta); border-radius:50%; }
.modo:hover { background:var(--tinta); color:var(--fondo); }
.modo svg { width:15px; height:15px; fill:none; stroke:currentColor; stroke-width:2; stroke-linecap:round; stroke-linejoin:round; }
.modo .luna { display:var(--luna); } .modo .sol { display:var(--sol); }
.rot { font-size:10.5px; font-weight:700; text-transform:uppercase; letter-spacing:.09em; color:var(--gris); flex:none; }
.desp { position:relative; margin:0; padding:0; border:0; font-size:inherit; }
.desp summary { list-style:none; cursor:pointer; user-select:none; }
.desp summary::-webkit-details-marker { display:none; }
.desp summary::after { content:" ▾"; } .desp[open] summary::after { content:" ▴"; }
.desp .lista { position:absolute; top:calc(100% + 10px); left:0; z-index:20; background:var(--fondo); border:2px solid var(--tinta); box-shadow:5px 5px 0 var(--sombra);
  width:max-content; min-width:260px; max-width:min(92vw,470px); max-height:74vh; overflow-y:auto; padding:6px 0; }
.desp .lista a { display:flex; justify-content:space-between; align-items:baseline; gap:16px; padding:7px 16px;
  font-size:14.5px; font-weight:500; border:0; line-height:1.35; }
.desp .lista a.fuerte { font-weight:700; padding:9px 16px; }
.desp .lista a.fuerte small { font-weight:500; color:var(--gris); font-size:12px; white-space:nowrap; }
.desp .lista .rot { margin:8px 0 2px; padding:9px 16px 0; border-top:1px solid var(--tinta); }
.desp .lista a:hover { background:var(--tinta); color:var(--fondo); } .desp .lista a:hover small { color:var(--inv-suave); }
.desp .lista b { color:var(--v-falso); font-weight:700; font-variant-numeric:tabular-nums; }
.desp .lista a:hover b { color:var(--fondo); } .desp .lista a.off { opacity:.4; }
.leyenda-f h2 { font:700 22px/1.2 "Iowan Old Style","Palatino Linotype",Palatino,Georgia,serif; margin:0 0 4px; padding:0; border:0; }
.ley-intro { margin:0 0 14px; font-size:14.5px; color:var(--suave); }
.leyenda-f dl { margin:0 0 16px; border-top:2px solid var(--tinta); }
.leyenda-f dl div { display:grid; grid-template-columns:150px minmax(0,1fr); gap:0 16px; align-items:center; padding:9px 0; border-bottom:1px solid var(--tinta); }
.leyenda-f dt { background:var(--tono); color:var(--sobre-tono); font-size:12.5px; font-weight:700; text-transform:uppercase; letter-spacing:.07em;
  padding:7px 10px; text-align:center; }
.leyenda-f dd { margin:0; font-size:15px; line-height:1.4; }
.ley-notas { list-style:none; margin:0; padding:0; font-size:14.5px; display:grid; gap:4px; }
@media (max-width:560px) { .leyenda-f dl div { grid-template-columns:1fr; gap:6px; } .leyenda-f dt { justify-self:start; } }
.filtros { position:sticky; top:var(--menu, 48px); z-index:5; background:var(--fondo); border-bottom:1px solid var(--tinta); padding:9px 0; }
.fila { display:flex; flex-wrap:wrap; align-items:center; gap:6px 8px; }
.fila button { font:inherit; font-size:12.5px; font-weight:600; color:var(--tinta); background:var(--fondo); border:1.5px solid var(--tinta);
  border-radius:999px; padding:3px 11px; cursor:pointer; display:inline-flex; align-items:center; gap:6px; }
.fila b { font-weight:500; opacity:.7; font-variant-numeric:tabular-nums; }
.fila button[data-v] { color:var(--tono); border-color:var(--tono); }
.fila button[data-v] i { width:8px; height:8px; border-radius:50%; background:currentColor; }
.fila button[aria-pressed=true] { background:var(--tinta); color:var(--fondo); }
.fila button[data-v][aria-pressed=true] { background:var(--tono); color:var(--sobre-tono); }
.fila button[data-solo] { margin-left:auto; }
@media (max-width:700px) { .m1 { gap:4px 16px; font-size:14px; } .m1 .dcha { margin-left:0; }
  .desp { position:static; } .desp .lista { left:16px; right:16px; top:auto; margin-top:10px; width:auto; max-width:none; }
  .fila .rot { display:none; } .fila button { font-size:12px; padding:2px 9px; } .fila button[data-solo] { margin-left:0; } }
"""
CSS_MENU = (CSS_MENU.replace("@@CLARO@@", _CLARO).replace("@@OSCURO@@", _OSCURO)
            .replace("@@CLASES_TONO@@", "\n".join(f"[data-v={k}], .tono-{k} {{ --tono:var(--v-{k}); }}" for k in ORDEN)))

VERIFICALO = """<!doctype html>
<html lang="es">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
@@HEAD_MODO@@
<title>Verifícalo tú · Verificación The Wild Project</title>
<meta name="description" content="Cómo comprobar por tu cuenta cada veredicto: vídeo, fuentes, datos abiertos y un encargo listo para que cualquier IA audite la verificación.">
<style>
:root { --serif:"Iowan Old Style","Palatino Linotype",Palatino,Georgia,serif; }
* { box-sizing:border-box; }
body { margin:0; background:var(--fondo); color:var(--tinta); font:16px/1.6 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif; }
a { color:var(--tinta); }
.ancho { max-width:1120px; margin:0 auto; padding:0 16px; }
main.ancho { max-width:820px; padding-bottom:72px; }
h1 { font:700 clamp(30px,6vw,48px)/1.06 var(--serif); letter-spacing:-0.02em; margin:38px 0 12px; text-wrap:balance; }
.entrada { font-size:17px; max-width:62ch; }
main > h2 { font:700 24px/1.2 var(--serif); margin:44px 0 10px; padding-top:12px; border-top:3px solid var(--tinta); }
p, li { max-width:68ch; }
.vias { list-style:none; padding:0; margin:18px 0 0; display:grid; gap:12px; }
.vias li { border:2px solid var(--tinta); padding:14px 16px; max-width:none; display:grid; grid-template-columns:44px minmax(0,1fr); gap:0 14px; }
.vias li > b { font:700 34px/1 var(--serif); }
.vias h3 { margin:0 0 2px; font-size:17px; } .vias p { margin:0; font-size:15px; }
.opciones { display:flex; flex-wrap:wrap; gap:10px 18px; margin:14px 0; font-size:14.5px; font-weight:600; }
.opciones select { font:inherit; font-weight:500; color:var(--tinta); border:1.5px solid var(--tinta); background:var(--fondo); padding:5px 8px; margin-left:6px; border-radius:0; }
pre { background:var(--pre-fondo); color:var(--pre-tinta); outline:1px solid var(--pre-borde); outline-offset:-1px; padding:16px 18px; white-space:pre-wrap; overflow-wrap:anywhere; font:13px/1.6 ui-monospace,SFMono-Regular,Menlo,monospace; margin:0 0 12px; }
.botones { display:flex; flex-wrap:wrap; gap:8px; }
.botones button, .botones a { font:inherit; font-size:14px; font-weight:600; background:var(--fondo); color:var(--tinta); border:2px solid var(--tinta); padding:7px 14px; cursor:pointer; text-decoration:none; }
.botones button { background:var(--tinta); color:var(--fondo); }
.botones a:hover { background:var(--tinta); color:var(--fondo); }
.nota { font-size:14px; color:var(--suave); }
code { font:13.5px/1.5 ui-monospace,SFMono-Regular,Menlo,monospace; background:var(--codigo); padding:1px 5px; }
@@CSS_API@@
@@CSS_MENU@@
</style>
</head>
<body>
@@MENU@@
<main class="ancho">
<h1>Verifícalo tú</h1>
<p class="entrada">Esta verificación la han hecho modelos de IA y no la ha revisado un equipo de periodistas. No hace falta que te la creas: todo está publicado para que lo compruebes a mano, con los datos de la API o con tu propia IA.</p>

<ol class="vias">
<li><b>1</b><div><h3>Mira el momento exacto</h3><p>En la línea temporal, el minuto de cada afirmación abre el vídeo de YouTube en ese segundo. Escucha la frase y su contexto.</p></div></li>
<li><b>2</b><div><h3>Abre las fuentes</h3><p>Cada panel lista las fuentes con su enlace. «Explicación completa» detalla qué dato sale de cada una.</p></div></li>
<li><b>3</b><div><h3>Pásaselo a una IA</h3><p>Cada panel tiene un botón que copia un encargo para esa afirmación concreta. Para auditar una entrevista entera, usa el encargo de abajo.</p></div></li>
<li><b>4</b><div><h3>Consulta la API</h3><p>Afirmaciones, veredictos, fuentes y transcripciones, en JSON y CSV, sin clave. Está <a href="#api">aquí abajo</a>, con ejemplos para hoja de cálculo, terminal y programación. El método y los encargos originales, en <a href="@@REPO@@" target="_blank" rel="noopener noreferrer">GitHub</a>.</p></div></li>
</ol>

@@SECCION_API@@

<h2>Encargo para auditar una entrevista con una IA</h2>
<p>Elige qué quieres revisar, copia el texto y pégalo en un asistente que pueda navegar por internet (Claude, ChatGPT, Gemini, Perplexity…). Lee los datos directamente de la API.</p>
<div class="opciones">
<label>Entrevista<select id="cual">@@OPCIONES@@<option value="">Todas</option></select></label>
<label>Qué revisar<select id="alcance">
<option value="malas">Solo falsas y engañosas</option>
<option value="nv">Solo las no verificables</option>
<option value="todas">Todas las afirmaciones</option>
<option value="muestra">Una muestra al azar de 15</option>
</select></label>
</div>
<pre id="encargo"></pre>
<div class="botones"><button id="copiar" type="button">Copiar encargo</button><a id="claude" target="_blank" rel="noopener noreferrer">Abrir en Claude ↗</a><a id="chatgpt" target="_blank" rel="noopener noreferrer">Abrir en ChatGPT ↗</a></div>
<p class="nota">Una IA también se equivoca: pídele siempre los enlaces y ábrelos. Si su respuesta contradice un veredicto con una fuente sólida, <a href="@@REPO@@/issues" target="_blank" rel="noopener noreferrer">abre una incidencia</a> con el identificador de la afirmación y lo corregimos.</p>

<h2>Qué significa cada veredicto</h2>
@@LEYENDA@@
</main>
@@JS_API@@
<script>
const B = "@@BASE@@";
const ALCANCE = {
  malas: 'las que tienen "veredicto" igual a "falso" o "enganoso"',
  nv: 'las que tienen "veredicto" igual a "no_verificable" (intenta encontrar la prueba que faltó)',
  todas: "todas",
  muestra: "una muestra al azar de 15, con al menos 5 falsas o engañosas",
};
function encargo() {
  const slug = document.getElementById("cual").value, alcance = document.getElementById("alcance").value;
  const datos = slug ? `${B}/api/v1/${slug}.json` : `${B}/api/v1/afirmaciones.json`;
  const texto = slug ? `${B}/api/v1/${slug}/transcripcion.txt` : `${B}/api/v1/{entrevista}/transcripcion.txt (el campo "entrevista" de cada afirmación da el nombre)`;
  return `Eres un verificador de datos independiente, riguroso e imparcial. Vas a auditar una verificación hecha con IA de las entrevistas de Jordi Wild (The Wild Project) a los candidatos a las elecciones generales españolas del 29 de noviembre de 2026.

DATOS (JSON público, sin clave)
- Guía de la API: ${B}/llms.txt
- Afirmaciones verificadas: ${datos}
- Transcripción con marcas de tiempo: ${texto}
Cada afirmación trae: id, minuto, video_url, cita (literal), afirmacion, veredicto, explicacion, confianza y fuentes[{titulo, url}]. Las definiciones de los veredictos están en el campo "veredictos" del JSON.

TAREA
Descarga las afirmaciones y revisa ${ALCANCE[alcance]}. Para cada una:
1. Cita: localízala en la transcripción cerca de su minuto. Comprueba que es literal, que la dice el entrevistado y no Jordi Wild, y que el contexto no le cambia el sentido.
2. Fuentes: abre cada fuentes[].url. Anota si existe y si dice de verdad lo que la explicacion le atribuye.
3. Contraste: busca al menos dos fuentes independientes más. Prioriza las primarias y oficiales (INE, Eurostat, BOE, Banco de España, Congreso, ministerios, resoluciones judiciales) y prensa de distintas líneas editoriales.
4. Veredicto: decide el tuyo con las mismas definiciones y compáralo con el publicado.

REGLAS
- La misma vara de medir para todos los partidos.
- No te fíes de tu memoria para hechos de 2025 y 2026: búscalos.
- No inventes enlaces ni datos. Si no puedes abrir una fuente, dilo.
- Si no hay prueba suficiente, el veredicto es "no_verificable"; no fuerces ni "falso" ni "verdadero".
- Admite el redondeo normal del lenguaje oral. "Falso" no implica intención de mentir.

ENTREGA
1. Una tabla: id | minuto | veredicto publicado | tu veredicto | ¿coinciden? | motivo en una frase | enlaces.
2. Las discrepancias, de más a menos grave, con la fuente que las sustenta.
3. Las fuentes rotas, inaccesibles o mal atribuidas.
4. Una frase final: cuántas has revisado, en cuántas coincides y cuánto te fías del conjunto.
Si encuentras un error claro, redacta la incidencia para @@REPO@@/issues con el id, el minuto y la fuente.`;
}
function pintar() {
  const t = encargo();
  document.getElementById("encargo").textContent = t;
  document.getElementById("claude").href = "https://claude.ai/new?q=" + encodeURIComponent(t);
  document.getElementById("chatgpt").href = "https://chatgpt.com/?q=" + encodeURIComponent(t);
}
document.getElementById("cual").onchange = pintar;
document.getElementById("alcance").onchange = pintar;
document.getElementById("copiar").onclick = ev => {
  const b = ev.currentTarget, t = encargo();
  const hecho = () => { b.textContent = "Copiado: pégalo en tu IA"; setTimeout(() => b.textContent = "Copiar encargo", 2200); };
  if (navigator.clipboard) navigator.clipboard.writeText(t).then(hecho, () => prompt("Copia este texto:", t)); else prompt("Copia este texto:", t);
};
pintar();
</script>
</body>
</html>
"""

PAGINA_API = """<!doctype html>
<html lang="es">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
@@HEAD_MODO@@
<title>API abierta · Verificación The Wild Project</title>
<meta name="description" content="API JSON y CSV de solo lectura, sin clave y con CORS abierto: referencia completa de cada ruta y cada campo, y un prompt listo para agentes de IA.">
<style>
:root { --serif:"Iowan Old Style","Palatino Linotype",Palatino,Georgia,serif; --scalar-custom-header-height:var(--menu, 48px); }
* { box-sizing:border-box; }
body { margin:0; background:var(--fondo); color:var(--tinta); font:16px/1.6 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif; }
a { color:var(--tinta); }
.ancho { max-width:1120px; margin:0 auto; padding:0 16px; }
.api-cab { padding:34px 0 30px; border-bottom:3px solid var(--tinta); }
.api-cab h1 { font:700 clamp(30px,6vw,48px)/1.06 var(--serif); letter-spacing:-0.02em; margin:0 0 12px; }
.api-cab > .ancho > p { font-size:17px; max-width:70ch; margin:0 0 10px; }
.api-cab code { font:14px/1.5 ui-monospace,SFMono-Regular,Menlo,monospace; background:var(--codigo); padding:1px 5px; }
.saltos { display:flex; flex-wrap:wrap; gap:8px 22px; margin:14px 0 26px; font-weight:700; font-size:15px; }
.agentes { border:2px solid var(--tinta); padding:18px 20px; }
.agentes h2 { font:700 25px/1.2 var(--serif); margin:0 0 6px; }
.agentes > p { margin:0 0 12px; font-size:15px; max-width:76ch; }
.agentes pre { background:var(--pre-fondo); color:var(--pre-tinta); outline:1px solid var(--pre-borde); outline-offset:-1px; margin:0 0 12px;
  padding:16px 18px; white-space:pre-wrap; overflow-wrap:anywhere; font:13px/1.6 ui-monospace,SFMono-Regular,Menlo,monospace;
  max-height:360px; overflow-y:auto; }
.botones { display:flex; flex-wrap:wrap; gap:8px; }
.botones button, .botones a { font:inherit; font-size:14px; font-weight:600; background:var(--fondo); color:var(--tinta); border:2px solid var(--tinta);
  padding:7px 14px; cursor:pointer; text-decoration:none; }
.botones button { background:var(--tinta); color:var(--fondo); }
.botones a:hover { background:var(--tinta); color:var(--fondo); }
.nota { font-size:13.5px; color:var(--suave); margin:10px 0 0; }
#referencia { min-height:60vh; }
noscript p { max-width:68ch; margin:24px 16px; }
.scalar-app { --scalar-radius:0; --scalar-radius-lg:0; --scalar-radius-xl:0; }
.light-mode .scalar-app, .light-mode { --scalar-color-accent:#000; }
.dark-mode .scalar-app, .dark-mode { --scalar-color-accent:#ececee; --scalar-background-1:#121214; }
@@CSS_MENU@@
</style>
</head>
<body>
@@MENU@@
<header class="api-cab"><div class="ancho">
<h1>API abierta</h1>
<p>Todos los datos de la web en JSON y CSV: afirmaciones, veredictos, fuentes y transcripciones. Sin registro ni clave, con CORS abierto y de solo lectura. Base: <code>@@BASE@@/api/v1</code>.</p>
<p class="saltos"><a href="#agentes">Prompt para agentes de IA ↓</a><a href="#referencia">Referencia completa ↓</a><a href="/api/v1/openapi.json">openapi.json</a><a href="/llms.txt">llms.txt</a><a href="/verificalo#api">Ejemplos para hoja de cálculo y programación</a></p>
<section class="agentes" id="agentes">
<h2>Prompt para agentes de IA</h2>
<p>Pégalo en un agente o asistente que pueda hacer peticiones web (Claude, ChatGPT, Gemini, Perplexity o tu propio agente), como instrucciones de sistema o como primer mensaje, y escribe tu pregunta al final. Le explica la API, qué trae cada campo y cómo citar.</p>
<pre id="prompt-agente">@@PROMPT@@</pre>
<div class="botones"><button id="copiar-prompt" type="button">Copiar prompt</button><a id="abrir-claude" target="_blank" rel="noopener noreferrer">Abrir en Claude ↗</a><a id="abrir-chatgpt" target="_blank" rel="noopener noreferrer">Abrir en ChatGPT ↗</a></div>
<p class="nota">Para auditar los veredictos uno a uno hay otro encargo, configurable por entrevista, en <a href="/verificalo">Verifícalo tú</a>. Una IA también se equivoca: pídele siempre los enlaces y ábrelos.</p>
</section>
</div></header>
<div id="referencia"></div>
<noscript><p>La referencia interactiva necesita JavaScript. Tienes la misma información en <a href="/api/v1/openapi.json">openapi.json</a>.</p></noscript>
<script src="https://cdn.jsdelivr.net/npm/@scalar/api-reference@@@SCALAR@@/dist/browser/standalone.js" integrity="@@SCALAR_SRI@@" crossorigin="anonymous"></script>
<script>
(() => {
  const texto = document.getElementById("prompt-agente").textContent;
  document.getElementById("abrir-claude").href = "https://claude.ai/new?q=" + encodeURIComponent(texto);
  document.getElementById("abrir-chatgpt").href = "https://chatgpt.com/?q=" + encodeURIComponent(texto);
  document.getElementById("copiar-prompt").onclick = ev => {
    const b = ev.currentTarget;
    const hecho = () => { b.textContent = "Copiado: pégalo en tu agente"; setTimeout(() => b.textContent = "Copiar prompt", 2200); };
    if (navigator.clipboard) navigator.clipboard.writeText(texto).then(hecho, () => prompt("Copia este texto:", texto)); else prompt("Copia este texto:", texto);
  };
  if (!window.Scalar) return;
  // Mismo modo que el resto de la web (botón del menú o sistema), también si cambia con la página abierta.
  const raiz = document.documentElement, sistema = matchMedia("(prefers-color-scheme: dark)");
  const tema = () => (raiz.dataset.modo ? raiz.dataset.modo === "oscuro" : sistema.matches) ? "dark" : "light";
  const config = {
    url: "/api/v1/openapi.json",
    hideDarkModeToggle: true,
    hideClientButton: true,
    showDeveloperTools: "never",
    agent: { disabled: true },
    documentDownloadType: "json",
    defaultHttpClient: { targetKey: "shell", clientKey: "curl" },
    metaData: { title: "API abierta · Verificación The Wild Project" },
  };
  Scalar.createApiReference("#referencia", { ...config, forceDarkModeState: tema() });
  // updateConfiguration no aplica forceDarkModeState en caliente; Scalar pinta el tema según la clase del <body>.
  const sincronizar = () => {
    const oscuro = tema() === "dark";
    document.body.classList.toggle("dark-mode", oscuro);
    document.body.classList.toggle("light-mode", !oscuro);
  };
  new MutationObserver(sincronizar).observe(raiz, { attributes: true, attributeFilter: ["data-modo"] });
  sistema.addEventListener("change", sincronizar);
})();
</script>
</body>
</html>
"""

REDIRIGE_API = """<!doctype html>
<html lang="es"><head><meta charset="utf-8"><meta http-equiv="refresh" content="0; url=/api"><link rel="canonical" href="/api">
<title>API abierta</title></head><body><p>La referencia de la API está ahora en <a href="/api">/api</a>.</p></body></html>
"""

PORTADA = """<!doctype html>
<html lang="es">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
@@HEAD_MODO@@
<title>Verificación de las entrevistas electorales de The Wild Project</title>
<meta name="description" content="Las entrevistas de Jordi Wild a los candidatos a las elecciones generales de 2026, comprobadas dato a dato con el mismo método. Código y datos abiertos.">
<style>
:root { --serif:"Iowan Old Style","Palatino Linotype",Palatino,Georgia,serif; }
* { box-sizing:border-box; }
body { margin:0; background:var(--fondo); color:var(--tinta); font:16px/1.55 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif; }
a { color:var(--tinta); }
.ancho { max-width:1120px; margin:0 auto; padding:0 16px; }
main.ancho { max-width:860px; }
h1 { font:700 clamp(30px,6vw,48px)/1.06 var(--serif); letter-spacing:-0.02em; margin:40px 0 14px; text-wrap:balance; }
.entrada { font-size:17px; max-width:62ch; margin:0 0 30px; }
.tu { margin:-10px 0 30px; padding:12px 14px; border:1.5px solid var(--tinta); font-size:15px; max-width:62ch; }
.entrevista { border:2px solid var(--tinta); padding:22px 24px; margin-bottom:18px; display:grid; grid-template-columns:76px minmax(0,1fr); gap:0 22px; align-items:start; }
.logo { width:76px; height:76px; object-fit:contain; display:block; }
/* en oscuro, los logotipos llevan una placa clara detrás (el azul del PP casi desaparece sobre fondo oscuro); en claro no hay placa */
img.logo { background:var(--logo-fondo); box-shadow:0 0 0 6px var(--logo-fondo); border-radius:var(--logo-radio); }
.logo.sin { display:grid; place-items:center; border:2px solid var(--tinta); font:700 24px/1 var(--serif); }
.entrevista.off .logo { opacity:.45; }
.partido { margin:0 0 6px; font-size:15px; font-weight:700; }
.entrevista.off { border:1px dashed var(--gris-claro); color:var(--gris); }
.prog { margin:0 0 12px; font-size:12px; text-transform:uppercase; letter-spacing:.08em; color:var(--gris); }
.entrevista h2 { font:700 32px/1.1 var(--serif); margin:0 0 2px; } .entrevista h2 a { text-decoration:none; }
.num { margin:0; font-size:17px; } .num b { font:700 34px/1 var(--serif); margin-right:4px; }
.des { margin:4px 0 14px; font-size:13.5px; font-weight:600; } .des span { color:var(--tono); }
.entrevista ul { list-style:none; margin:6px 0 16px; padding:0; columns:2; column-gap:28px; font-size:14.5px; }
.entrevista li { margin:0 0 5px; break-inside:avoid; } .entrevista li b { color:var(--v-falso); }
.contrastar { border-top:3px solid var(--tinta); margin-top:40px; padding-top:6px; }
.contrastar h2 { font:700 26px/1.2 var(--serif); margin:18px 0 6px; }
.contrastar li { margin-bottom:8px; max-width:68ch; }
.contrastar pre { background:var(--pre-fondo); color:var(--pre-tinta); outline:1px solid var(--pre-borde); outline-offset:-1px; padding:14px 16px; overflow-x:auto; white-space:pre-wrap; font:13px/1.55 ui-monospace,SFMono-Regular,Menlo,monospace; margin:6px 0 10px; }
.copiar { font:inherit; font-size:13px; font-weight:600; background:var(--fondo); color:var(--tinta); border:1.5px solid var(--tinta); padding:5px 12px; cursor:pointer; }
.copiar:hover { background:var(--tinta); color:var(--fondo); }
.acc { margin:0; display:flex; flex-wrap:wrap; gap:8px 22px; } .acc a { font-weight:700; text-underline-offset:3px; }
.seccion-t, .compara h2 { font:700 27px/1.2 var(--serif); margin:44px 0 14px; padding-top:12px; border-top:3px solid var(--tinta); }
.compara { margin-bottom:8px; }
.tabla-c { overflow-x:auto; }
.compara table { border-collapse:collapse; width:100%; min-width:540px; font-size:15px; font-variant-numeric:tabular-nums; table-layout:fixed; }
.compara thead td { width:28%; }
.compara th, .compara td { text-align:left; padding:9px 10px; border-bottom:1px solid var(--claro); vertical-align:top; }
.compara thead th { border-bottom:2px solid var(--tinta); vertical-align:bottom; }
.compara thead a { text-decoration:none; }
.cand { display:block; font:700 20px/1.15 var(--serif); }
.par { display:block; font-size:12.5px; font-weight:600; color:var(--gris); margin-top:3px; }
.compara tbody th { font-weight:600; font-size:13.5px; }
.compara tbody th i { display:inline-block; width:9px; height:9px; border-radius:50%; background:var(--tono); margin-right:7px; }
.compara tr[class^="tono-"] td b { color:var(--tono); }
.compara tr.fuerte th, .compara tr.fuerte td { border-top:2px solid var(--tinta); border-bottom:2px solid var(--tinta); }
.compara tr.fuerte td b { font:700 24px/1 var(--serif); }
.compara .pc { color:var(--gris); font-size:13px; margin-left:3px; }
.compara td a { text-underline-offset:3px; }
.reparto { display:flex; gap:2px; height:12px; border-radius:3px; overflow:hidden; margin-top:4px; }
.reparto i { display:block; min-width:3px; background:var(--tono); }
.nota-c { font-size:13.5px; color:var(--suave); max-width:76ch; margin:10px 0 0; }
@media (max-width:560px) { .compara table { min-width:0; font-size:12.5px; } .compara thead td { width:27%; }
  .cand { font-size:15px; } .par { font-size:11px; } .compara th, .compara td { padding:7px 4px; } .compara tbody th { font-size:12px; }
  .compara .pc { display:block; margin-left:0; font-size:11.5px; } .compara tr.fuerte td b { font-size:20px; } }
footer { border-top:3px solid var(--tinta); margin-top:48px; padding:24px 0 64px; font-size:14.5px; }
footer p { max-width:68ch; }
@media (max-width:560px) { .entrevista { grid-template-columns:52px minmax(0,1fr); gap:0 14px; padding:16px; } .logo { width:52px; height:52px; } .entrevista h2 { font-size:26px; } }
@@CSS_MENU@@
</style>
</head>
<body>
@@MENU@@
<main class="ancho">
<h1>Las entrevistas de The Wild Project, comprobadas dato a dato</h1>
<p class="entrada">Jordi Wild ha entrevistado a los candidatos a la presidencia del Gobierno para las elecciones del 29 de noviembre de 2026. Transcribimos cada entrevista entera, separamos las afirmaciones que se pueden comprobar y las contrastamos con fuentes públicas, con el mismo método y la misma vara de medir para todos.</p>
<p class="tu"><a href="/verificalo"><b>Puedes verificarlo tú</b> →</a> Cada dato enlaza su fuente y el minuto del vídeo, y hay un encargo listo para que cualquier IA lo revise por su cuenta.</p>
@@COMPARATIVA@@
<h2 class="seccion-t">Las entrevistas</h2>
@@TARJETAS@@
</main>
<footer><div class="ancho">
@@LEYENDA@@
<p style="margin-top:22px">Verificación asistida por IA (transcripción con Whisper, contraste con modelos Claude y búsqueda web), sin revisión de un equipo de periodistas. Cada afirmación enlaza el segundo exacto del vídeo y sus fuentes, y el código, las transcripciones y los datos están publicados en <a href="@@REPO@@" target="_blank" rel="noopener noreferrer">GitHub</a>. «Falso» no implica intención de mentir: incluye errores y lapsus. El número de afirmaciones falsas depende también de cuánto habla cada invitado y de cuántos datos da, así que las cifras no son un ranking. En rojo, junto a cada tema, cuántas afirmaciones falsas o engañosas contiene.</p>
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
@@HEAD_MODO@@
<title>Transcripción completa: @@INVITADO@@ en The Wild Project</title>
<meta name="description" content="Transcripción completa de la entrevista de Jordi Wild a @@INVITADO@@ (@@PROGRAMA@@), con marcas de tiempo enlazadas al vídeo y a cada afirmación verificada.">
<style>
:root { --serif:"Iowan Old Style","Palatino Linotype",Palatino,Georgia,serif; }
* { box-sizing:border-box; }
body { margin:0; background:var(--fondo); color:var(--tinta); font:16px/1.6 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif; }
a { color:var(--tinta); }
.ancho { max-width:1120px; margin:0 auto; padding:0 16px; }
main.ancho { max-width:820px; padding-bottom:72px; }
h1 { font:700 clamp(28px,5.5vw,42px)/1.08 var(--serif); letter-spacing:-0.02em; margin:36px 0 12px; text-wrap:balance; }
.entrada { font-size:16px; color:var(--suave); max-width:64ch; margin:0 0 8px; }
h2 { font:700 23px/1.2 var(--serif); margin:44px 0 14px; padding-top:12px; border-top:3px solid var(--tinta); text-wrap:balance; }
.turno { margin:0 0 18px; }
.turno[data-voz=J] .par p { color:var(--suave); }
.par { display:grid; grid-template-columns:74px minmax(0,1fr); gap:0 14px; margin-bottom:8px; }
.par:target { background:var(--resalte); }
.minuto { font-size:13px; font-weight:700; font-variant-numeric:tabular-nums; text-underline-offset:3px; padding-top:4px; }
.par p { margin:0; font:17px/1.65 var(--serif); }
.quien { font:700 11.5px/1 -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif; text-transform:uppercase; letter-spacing:.07em;
  color:var(--tinta); margin-right:6px; vertical-align:2px; }
.turno[data-voz=J] .quien { color:var(--gris); }
.turno[data-voz=V] .quien, .turno[data-voz=O] .quien { color:var(--gris); font-style:italic; }
/* el tramo de cada afirmación analizada, subrayado con el color de su veredicto y enlazado a su tarjeta */
.subr { color:inherit; text-decoration:underline; text-decoration-color:var(--tono); text-decoration-thickness:3px;
  text-underline-offset:4px; text-decoration-skip-ink:none; }
.subr:hover { background:color-mix(in srgb, var(--tono) 18%, transparent); }
.et { font:700 10.5px/1 -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif; text-transform:uppercase; letter-spacing:.06em;
  color:var(--sobre-tono); background:var(--tono); padding:2px 6px 3px; border-radius:3px; text-decoration:none; white-space:nowrap;
  vertical-align:2px; margin-left:2px; }
.et:hover { filter:brightness(1.1); }
.apagada.subr { text-decoration:none; pointer-events:none; } .apagada.et { display:none; }
@media (max-width:600px) { .par { grid-template-columns:1fr; } .par p { font-size:16.5px; } }
@@CSS_MENU@@
</style>
</head>
<body>
@@MENU@@
@@FILTROS@@
<main class="ancho">
<h1>Transcripción completa: @@INVITADO@@ con Jordi Wild</h1>
<p class="entrada">@@PROGRAMA@@ · @@FECHA_VIDEO@@ · @@DURACION@@. Transcripción automática (Whisper), que puede tener errores en nombres y cifras. @@NOTA_VOCES@@Cada minuto abre el <a href="https://www.youtube.com/watch?v=@@VIDEO@@" target="_blank" rel="noopener noreferrer">vídeo</a> en ese punto. <b>Lo subrayado es una afirmación analizada</b>: el color es su veredicto, y al pulsarla vas a su tarjeta en la <a href="/@@SLUG@@">línea temporal</a>, con la justificación y las fuentes.</p>
@@CUERPO@@
<div style="border-top:3px solid var(--tinta); margin-top:48px; padding-top:22px">@@LEYENDA@@</div>
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
    p.querySelectorAll(".subr, .et").forEach(c => {
      const on = activos.has(c.dataset.v);
      c.classList.toggle("apagada", !on);
      if (on && c.classList.contains("subr")) n++;
    });
    p.hidden = solo && n === 0;
  });
  document.querySelectorAll(".turno").forEach(t => { t.hidden = solo && !t.querySelector(".par:not([hidden])"); });
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
@@HEAD_MODO@@
<title>Verificación: @@INVITADO@@ en The Wild Project</title>
<meta name="description" content="Línea temporal de la entrevista de Jordi Wild a @@INVITADO@@: @@MALAS@@ afirmaciones falsas o engañosas, cada una con su minuto, su justificación y sus fuentes.">
<meta property="og:title" content="@@INVITADO@@ en The Wild Project, minuto a minuto">
<meta property="og:description" content="@@MALAS@@ de @@SUMA@@ afirmaciones son falsas o engañosas. Cada una enlaza al segundo exacto del vídeo y a sus fuentes.">
<style>
:root { --col:330px; --hueco:56px;
  --serif:"Iowan Old Style","Palatino Linotype",Palatino,Georgia,serif; }
* { box-sizing:border-box; }
html { scroll-behavior:smooth; }
body { margin:0; background:var(--fondo); color:var(--tinta); font:16px/1.55 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif; -webkit-text-size-adjust:100%; }
a { color:var(--tinta); }
.ancho { max-width:1120px; margin:0 auto; padding:0 16px; }
.cima { display:flex; justify-content:space-between; gap:12px; padding-top:18px; font-size:13px; }
.cima a { font-weight:600; white-space:nowrap; }
.portada { padding-top:40px; padding-bottom:8px; }
h1 { font:700 clamp(30px,6vw,48px)/1.06 var(--serif); letter-spacing:-0.02em; margin:0 0 14px; text-wrap:balance; }
.entrada { font-size:17px; margin:0 0 28px; max-width:60ch; }
.dato { display:flex; align-items:baseline; gap:16px; flex-wrap:wrap; border-top:3px solid var(--tinta); border-bottom:1px solid var(--tinta); padding:14px 0; }
.dato b { font:700 clamp(60px,13vw,96px)/0.85 var(--serif); font-variant-numeric:tabular-nums; }
.dato span { font-size:18px; max-width:24ch; line-height:1.3; }
.resto { font-size:14px; color:var(--gris); margin:10px 0 0; }
.pegado { position:sticky; top:0; z-index:5; background:var(--fondo); border-bottom:1px solid var(--tinta); padding:10px 0; margin-top:22px; }
.fila { display:flex; gap:8px; overflow-x:auto; scrollbar-width:none; }
.fila::-webkit-scrollbar { display:none; }
.fila button { flex:none; font:inherit; font-size:13px; font-weight:600; color:var(--tinta); background:var(--fondo);
  border:1.5px solid var(--tinta); border-radius:999px; padding:5px 14px; cursor:pointer; }
.fila button[aria-pressed=true] { background:var(--tinta); color:var(--fondo); }
.fila b { font-weight:500; opacity:.65; font-variant-numeric:tabular-nums; }

.linea { list-style:none; margin:0; padding:28px 0 40px; position:relative; }
.linea::before { content:""; position:absolute; top:0; bottom:0; left:var(--col); width:2px; background:var(--tinta); }
.linea > li { position:relative; display:grid; grid-template-columns:var(--col) var(--hueco) minmax(0,1fr); align-items:start; }
.minuto { grid-column:1; justify-self:end; margin-right:22px; font-weight:700; font-size:17px; font-variant-numeric:tabular-nums;
  text-underline-offset:3px; white-space:nowrap; }
.hito { padding:14px 0; }
.dicho { grid-column:1; text-align:right; padding:15px 22px 0 0; }
.dicho .minuto { margin:0; }
.dicho blockquote { margin:8px 0 0; font-size:17px; }
.panel blockquote.movil { display:none; }
.minuto:hover { background:var(--tinta); color:var(--fondo); text-decoration:none; }
.punto { position:absolute; left:calc(var(--col) - 6px); top:36px; width:14px; height:14px; border-radius:50%;
  background:var(--fondo); border:2px solid var(--tinta); }
[data-v=falso] .punto { background:var(--tinta); width:18px; height:18px; left:calc(var(--col) - 8px); top:34px; }
.flecha { grid-column:2; height:2px; background:var(--tinta); margin:42px 9px 0 10px; position:relative; }
.flecha::after { content:""; position:absolute; right:-9px; top:-5px; border-left:10px solid var(--tinta);
  border-top:6px solid transparent; border-bottom:6px solid transparent; }
.panel { grid-column:3; border:2px solid var(--tinta); padding:16px 18px; background:var(--fondo); }
[data-v=falso] .panel { box-shadow:5px 5px 0 var(--sombra); }
.ficha { display:inline-block; margin:0 0 10px; font-size:11.5px; font-weight:700; text-transform:uppercase; letter-spacing:.09em;
  border:1.5px solid var(--tinta); padding:2px 9px; }
[data-v=falso] .ficha { background:var(--tinta); color:var(--fondo); }
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

/* cabecera de cada tema: franja que cruza la línea, número en un círculo, rango de tiempo, recuento y barra */
.capitulo { margin-top:46px; padding:22px 0 18px; border-top:3px solid var(--tinta); }
.linea > .capitulo:first-child { margin-top:0; }
.capitulo .minuto { font-weight:600; font-size:14px; margin-top:12px; color:var(--gris); }
.marca { position:absolute; left:calc(var(--col) - 17px); top:-19px; width:36px; height:36px; border-radius:50%;
  background:var(--tinta); color:var(--fondo); display:grid; place-items:center; font:700 16px/1 var(--serif);
  box-shadow:0 0 0 5px var(--fondo); font-variant-numeric:tabular-nums; }
.cab-tema { grid-column:2 / 4; padding-left:22px; }
.num-tema { margin:0 0 4px; font-size:11.5px; font-weight:700; text-transform:uppercase; letter-spacing:.09em; color:var(--gris); }
h2 { font:700 23px/1.2 var(--serif); margin:0; letter-spacing:-0.01em; text-wrap:balance; }
.cab-tema h2 { font-size:29px; line-height:1.12; }
.recuento { margin:8px 0 0; font-size:13.5px; font-weight:600; }
.recuento span { color:var(--tono); }
.barra-tema { display:flex; gap:2px; height:6px; max-width:420px; margin-top:8px; border-radius:3px; overflow:hidden; }
.barra-tema i { display:block; min-width:3px; background:var(--tono); }
.tema-actual { margin-left:auto; font-size:13px; font-weight:700; white-space:nowrap; overflow:hidden; text-overflow:ellipsis;
  max-width:46ch; padding-left:10px; }
.tema-actual:empty { display:none; }
[hidden] { display:none !important; }
/* color del minuto según el veredicto (el --tono de cada veredicto está en CSS_MENU) */
.hito .minuto { color:var(--tono); } .hito .minuto:hover { background:var(--tono); color:var(--sobre-tono); }
.hito .punto { border-color:var(--tono) !important; } .hito[data-v=falso] .punto { background:var(--tono); }
.hito .ficha { border-color:var(--tono) !important; color:var(--tono) !important; }
.hito[data-v=falso] .ficha { background:var(--tono); color:var(--sobre-tono) !important; }
.leyenda { display:flex; flex-wrap:wrap; gap:4px 16px; font-size:12.5px; margin-top:8px; }
.leyenda span { display:inline-flex; align-items:center; gap:6px; font-weight:600; }
.leyenda i { width:10px; height:10px; border-radius:50%; background:currentColor; }

footer { border-top:3px solid var(--tinta); padding:28px 0 72px; font-size:14.5px; }
footer h2 { font-size:20px; margin-bottom:10px; }
footer p { max-width:68ch; }
footer .leyenda-f { margin-bottom:34px; max-width:820px; }
.pasos { margin:0 0 12px; padding-left:22px; max-width:68ch; } .pasos li { margin:3px 0; }
.repo.claro { background:var(--fondo); color:var(--tinta); border:2px solid var(--tinta); padding:7px 14px; margin-left:8px; }
.repo { display:inline-block; margin:6px 0 14px; padding:9px 16px; background:var(--tinta); color:var(--fondo); text-decoration:none; font-weight:600; }
@media (max-width:860px) { :root { --col:72px; --hueco:26px; } .minuto { margin-right:10px; font-size:13px; }
  .dicho { padding-right:10px; } .dicho blockquote { display:none; } .panel blockquote.movil { display:block; }
  .flecha { margin-left:8px; margin-right:8px; } .panel { padding:13px 13px; } blockquote { font-size:17px; }
  .cab-tema { padding-left:16px; } h2 { font-size:20px; } .cab-tema h2 { font-size:23px; }
  .marca { left:calc(var(--col) - 15px); width:32px; height:32px; top:-17px; font-size:15px; }
  .tema-actual { flex-basis:100%; margin-left:0; padding-left:0; max-width:none; font-size:12.5px; } }
.abrir { margin:14px 0 0; padding:12px 14px; border:1.5px solid var(--tinta); font-size:14.5px; max-width:78ch; }
.contrasta { margin:12px 0 0; }
.copiar { font:inherit; font-size:12.5px; font-weight:600; background:var(--fondo); color:var(--tinta); border:1.5px solid var(--tinta); padding:4px 11px; cursor:pointer; }
.copiar:hover, .copiar.hecho { background:var(--tinta); color:var(--fondo); }
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
  <p class="resto">El resto: @@VERDADERAS@@ verdaderas, @@CASI@@ casi ciertas y @@NV@@ que no se han podido verificar.@@NOTA_EXCL@@</p>
  <p class="abrir"><b>Contrástalo tú mismo.</b> Cada panel enlaza el vídeo y sus fuentes, y trae un botón que copia un encargo listo para pegar en cualquier IA. También puedes descargar <a href="/api/v1/@@SLUG@@.json">todos los datos de esta entrevista (JSON)</a>, usar la <a href="/api">API abierta</a> o leer el <a href="@@REPO@@/blob/main/METODO.md" target="_blank" rel="noopener noreferrer">método</a>.</p>
</div>
@@FILTROS@@
<main class="ancho"><ol class="linea">@@FILAS@@</ol></main>
<footer><div class="ancho">
  @@LEYENDA@@
  <h2>Cómo se ha hecho</h2>
  <ol class="pasos">
    <li><b>Transcripción.</b> El audio completo, con Whisper.</li>
    <li><b>Extracción.</b> Se separan las afirmaciones comprobables del entrevistado.</li>
    <li><b>Contraste.</b> Un agente de IA (Claude) por tema las compara con fuentes públicas y asigna el veredicto.</li>
    <li><b>Publicación.</b> Cada afirmación enlaza el segundo exacto del vídeo y sus fuentes.</li>
  </ol>
  <p><b>Límite importante:</b> no lo ha revisado un equipo de periodistas. Es un punto de partida; por eso todo el material está publicado.</p>
  <a class="repo" href="@@REPO@@" target="_blank" rel="noopener noreferrer">Código, transcripción y datos en GitHub ↗</a>
  <a class="repo claro" href="/api">API abierta</a>
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
const capitulos = [...document.querySelectorAll(".capitulo")], temaActual = document.getElementById("tema-actual");
let pendienteTema = false;
function marcarTema() {
  pendienteTema = false;
  const limite = document.querySelector(".menu").offsetHeight + document.querySelector(".filtros").offsetHeight + 24;
  let c = null;
  for (const x of capitulos) { if (x.hidden) continue; if (x.getBoundingClientRect().top <= limite) c = x; else break; }
  temaActual.textContent = c ? c.dataset.etiqueta : "";
}
addEventListener("scroll", () => { if (!pendienteTema) { pendienteTema = true; requestAnimationFrame(marcarTema); } }, { passive: true });
botones.forEach(b => b.onclick = () => {
  const v = b.dataset.v;
  if (activos.has(v) && activos.size > 1) activos.delete(v); else activos.add(v);
  pintar(); marcarTema();
});
todas.onclick = () => {
  if (activos.size === botones.length) { activos.clear(); activos.add("falso"); activos.add("enganoso"); } else verTodo();
  pintar(); marcarTema();
};
function irAlAncla() {
  const d = location.hash.length > 1 && document.getElementById(location.hash.slice(1));
  if (!d) return;
  if (d.hidden) { if (d.dataset.v) activos.add(d.dataset.v); else verTodo(); pintar(); }
  d.scrollIntoView();
}
pintar(); irAlAncla(); marcarTema();
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

Datos completos en JSON: @@BASE@@/api/v1/@@SLUG@@.json (id "@@SLUG@@-${h.id}"). Transcripción para ver el contexto: @@BASE@@/api/v1/@@SLUG@@/transcripcion.txt

Haz esto:
1. Comprueba en la transcripción que la cita es literal, que la dice el entrevistado y que el contexto no le cambia el sentido.
2. Abre cada fuente y dime si existe y si de verdad dice lo que la justificación le atribuye.
3. Busca al menos dos fuentes independientes más, mejor primarias y oficiales. No te fíes de tu memoria para hechos de 2025 y 2026: búscalo.
4. Da tu propio veredicto (verdadero, casi cierto, engañoso, falso o no verificable) y di si coincide con el publicado, en qué discrepas y con qué enlaces lo sustentas.
No inventes enlaces. Si no puedes abrir una fuente o no hay pruebas suficientes, dilo.`;
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
