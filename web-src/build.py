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
from urllib.parse import quote, urlparse

import acceso
import api_publica
import avisos
import estadisticas
import transiciones

RAIZ = Path(__file__).resolve().parent.parent
ENTREVISTAS = RAIZ / "entrevistas"
SALIDA = RAIZ / "web"
# Datos estáticos de la API: se guardan en web/datos/ y vercel.json los publica en /api y /api/v1/*.
# En local (python3 -m http.server -d web) están en /datos/v1/.
DATOS = SALIDA / "datos"
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


def _glosario():
    """Correcciones de entrevistas/glosario.json (nombres que Whisper transcribe mal), ya compiladas."""
    ruta = ENTREVISTAS / "glosario.json"
    if not ruta.exists():
        return []
    return [(re.compile(c["buscar"]), c["poner"]) for c in json.loads(ruta.read_text(encoding="utf-8"))["correcciones"]]


GLOSARIO = _glosario()


def corregir(texto):
    """Aplica el glosario a un texto de la transcripción. Solo para mostrarlo: la búsqueda de citas usa el original."""
    for patron, poner in GLOSARIO:
        texto = patron.sub(poner, texto)
    return texto


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


# Visor de fuentes: al pulsar una fuente que se puede leer (web-src/acceso.json) se abre un diálogo con solo su
# texto, sacado con el lector gratuito r.jina.ai, y un botón a la original. No se incrusta la web. Las fuentes que
# no se pueden leer, y Cmd/Ctrl/clic central, abren pestaña nueva como siempre; sin JavaScript, igual.
VISOR_FUENTE = r"""<dialog id="visor" aria-labelledby="visor-titulo">
<div class="v-caja">
  <header class="v-cab">
    <div class="v-que"><p class="v-dom" id="visor-dom"></p><h2 id="visor-titulo"></h2></div>
    <button class="v-x" type="button" data-cerrar aria-label="Cerrar (Esc)"><svg viewBox="0 0 24 24" width="20" height="20" aria-hidden="true" focusable="false"><path d="M6 6l12 12M18 6L6 18" fill="none" stroke="currentColor" stroke-width="2.25" stroke-linecap="round"/></svg></button>
  </header>
  <div class="v-cuerpo" id="visor-cuerpo" tabindex="-1">
    <div class="v-estado" id="visor-estado" role="status"></div>
    <article class="v-texto" id="visor-texto"></article>
  </div>
  <footer class="v-pie">
    <p>Solo el texto de la página, sacado con <a href="https://jina.ai/reader" target="_blank" rel="noopener noreferrer">r.jina.ai</a>. Puede faltar alguna tabla o gráfico: ante la duda, abre la original.</p>
    <a class="v-ir" id="visor-ir" target="_blank" rel="noopener noreferrer">Ir a la fuente original ↗</a>
  </footer>
</div>
</dialog>
<style>
#visor { padding:0; border:0; background:transparent; max-width:none; max-height:none; width:100%; height:100%; margin:0; }
#visor::backdrop { background:rgba(0,0,0,.55); }
#visor[open] .v-caja { animation:v-entra .18s ease-out; }
@keyframes v-entra { from { opacity:0; transform:translateY(10px); } }
@media (prefers-reduced-motion:reduce) { #visor[open] .v-caja { animation:none; } }
.v-caja { position:absolute; inset:clamp(12px,3vw,32px); margin:0 auto; max-width:820px; display:flex; flex-direction:column;
  background:var(--fondo); color:var(--tinta); border:2px solid var(--tinta); border-radius:var(--r-caja,14px); box-shadow:var(--flota); overflow:hidden; }
.v-cab { display:flex; align-items:flex-start; gap:12px; padding:14px 12px 12px clamp(16px,3vw,24px); border-bottom:2px solid var(--tinta); }
.v-que { flex:1; min-width:0; }
.v-dom { margin:0 0 3px; font-size:12px; font-weight:700; text-transform:uppercase; letter-spacing:.08em; color:var(--gris); }
.v-cab h2 { font:700 clamp(18px,2.2vw,21px)/1.25 var(--serif,Georgia,serif); margin:0; text-wrap:balance;
  overflow:hidden; display:-webkit-box; -webkit-line-clamp:2; -webkit-box-orient:vertical; }
.v-x { flex:none; display:grid; place-items:center; width:44px; height:44px; padding:0; background:transparent; color:var(--tinta);
  border:1.5px solid transparent; border-radius:var(--r-boton,9px); cursor:pointer; }
.v-x svg { display:block; }
.v-x:hover { border-color:var(--tinta); }
.v-ir { display:inline-flex; align-items:center; flex:none; min-height:44px; padding:0 16px; background:var(--tinta); color:var(--fondo);
  font-size:14px; font-weight:600; text-decoration:none; border:2px solid var(--tinta); border-radius:var(--r-boton,9px); }
.v-ir:hover { background:var(--fondo); color:var(--tinta); }
.v-x:focus-visible, .v-ir:focus-visible { outline:3px solid var(--tinta); outline-offset:2px; }
.v-cuerpo { position:relative; flex:1; min-height:0; overflow:auto; overscroll-behavior:contain; outline:none; }
.v-estado:empty { display:none; }
.v-estado { padding:min(14vh,90px) 20px 28px; text-align:center; font-size:15px; }
.v-estado h3 { font:700 21px/1.25 var(--serif,Georgia,serif); margin:0 0 8px; }
.v-estado p { margin:0 auto; max-width:46ch; color:var(--suave); }
.v-estado .v-ir { margin-top:18px; }
.v-carga { max-width:68ch; margin:0 auto; text-align:left; }
.v-carga span { display:block; height:12px; margin:12px 0; border-radius:var(--r-mini,5px); background:var(--claro); animation:v-pulso 1.1s ease-in-out infinite alternate; }
.v-carga span:nth-child(3n) { width:70%; } .v-carga span:nth-child(4n) { width:85%; }
@keyframes v-pulso { to { opacity:.4; } }
@media (prefers-reduced-motion:reduce) { .v-carga span { animation:none; } }
.v-texto { max-width:68ch; margin:0 auto; padding:clamp(18px,3vw,28px) clamp(16px,3vw,24px) 40px;
  font:clamp(16px,1.6vw,17px)/1.65 var(--serif,Georgia,serif); overflow-wrap:anywhere; }
.v-texto:empty { display:none; }
.v-texto h1, .v-texto h2, .v-texto h3, .v-texto h4 { font-family:inherit; line-height:1.25; margin:1.4em 0 .5em; text-wrap:balance; }
.v-texto h1 { font-size:25px; } .v-texto h2 { font-size:22px; } .v-texto h3, .v-texto h4 { font-size:18px; }
.v-texto p, .v-texto ul, .v-texto ol, .v-texto blockquote, .v-texto pre, .v-texto table { margin:0 0 1em; }
.v-texto blockquote { border-left:3px solid var(--tinta); padding-left:14px; font-style:italic; }
.v-texto pre { white-space:pre-wrap; font:13px/1.5 ui-monospace,Menlo,monospace; background:var(--codigo); padding:10px 12px; border-radius:var(--r-mini,5px); }
.v-texto table { border-collapse:collapse; font:13.5px/1.4 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif; display:block; max-width:100%; overflow-x:auto; }
.v-texto td, .v-texto th { border:1px solid var(--claro); padding:4px 8px; vertical-align:top; }
.v-texto hr { border:0; border-top:1px solid var(--tinta); margin:1.5em 0; }
.v-texto a { color:var(--tinta); }
.v-texto .v-corte { font:14px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif; border-top:1px solid var(--tinta); padding-top:10px; }
.v-pie { display:flex; align-items:center; justify-content:space-between; gap:10px 16px; flex-wrap:wrap;
  padding:10px 12px 10px clamp(16px,3vw,24px); padding-bottom:max(10px, env(safe-area-inset-bottom)); border-top:2px solid var(--tinta); }
.v-pie p { flex:1 1 260px; margin:0; font-size:12.5px; color:var(--gris); }
.v-pie p a { color:inherit; }
@media (max-width:560px) {
  .v-caja { inset:0; border:0; border-radius:0; box-shadow:none; }
  .v-pie .v-ir { flex:1 1 100%; justify-content:center; }
}
</style>
<script>
(() => {
  const d = document.getElementById("visor");
  if (!d || typeof d.showModal !== "function") return;  // navegador antiguo: el enlace abre pestaña como antes
  const $ = id => document.getElementById(id);
  const titulo = $("visor-titulo"), dom = $("visor-dom"), ir = $("visor-ir"), cuerpo = $("visor-cuerpo"),
        estado = $("visor-estado"), texto = $("visor-texto");
  const LECTOR = "https://r.jina.ai/", MAX = 150000;
  const cache = new Map();
  let actual = null, empujado = false;

  // Si la web devuelve un error (403 de un CDN, «Just a moment…» de Cloudflare…), el lector lo trae como si fuera
  // el artículo: se descarta.
  const ERROR = /^(\d{3}\b|the request could not be satisfied|access denied|just a moment|attention required|forbidden|not found|página no encontrada|error)/i;
  const espera = ms => new Promise(r => setTimeout(r, ms));
  function pedir(url, intentos = 2) {
    return fetch(LECTOR + url, { headers: { "Accept": "application/json", "X-Retain-Images": "none",
        "X-Remove-Selector": "header, nav, footer, aside, form, [role=navigation], [aria-hidden=true]" } })
      .then(r => {
        if (r.status === 429 && intentos > 1)  // límite de 20 por minuto del lector gratuito
          return r.json().catch(() => ({})).then(j => espera(1000 * Math.min(8, (j.retryAfter || 3) + 1))).then(() => pedir(url, intentos - 1));
        return r.ok ? r.json().then(j => {
          const c = j && j.data;
          if (!c || !(c.content || "").trim() || c.httpStatus >= 400 || /error \d{3}/i.test(c.warning || "")
              || ERROR.test((c.title || "").trim()) || c.content.trim().length < 200) throw new Error("sin texto");
          return c;
        }) : Promise.reject(new Error("HTTP " + r.status));
      });
  }
  function leer(url) {
    if (!cache.has(url)) {
      const p = pedir(url);
      p.catch(() => cache.delete(url));
      cache.set(url, p);
    }
    return cache.get(url);
  }

  // Markdown -> DOM sin innerHTML: el contenido es de terceros.
  const seguro = u => { try { const x = new URL(u, actual); return /^https?:$/.test(x.protocol) ? x.href : null; } catch { return null; } };
  function enLinea(padre, s) {
    const re = /\[([^\]]*)\]\(([^)\s]+)(?:\s+"[^"]*")?\)|\*\*([^*]+)\*\*|__([^_]+)__|\*([^*\s][^*]*)\*|`([^`]+)`/g;
    let i = 0, m;
    while ((m = re.exec(s))) {
      if (m.index > i) padre.append(s.slice(i, m.index));
      if (m[2] !== undefined) {
        const t = m[1].trim(), h = seguro(m[2]);
        if (t) { if (h) { const a = document.createElement("a"); a.href = h; a.target = "_blank"; a.rel = "noopener noreferrer"; enLinea(a, t); padre.append(a); } else enLinea(padre, t); }
      } else if (m[3] || m[4]) { const b = document.createElement("strong"); enLinea(b, m[3] || m[4]); padre.append(b); }
      else if (m[5]) { const em = document.createElement("em"); enLinea(em, m[5]); padre.append(em); }
      else { const c = document.createElement("code"); c.textContent = m[6]; padre.append(c); }
      i = re.lastIndex;
    }
    if (i < s.length) padre.append(s.slice(i));
  }
  const el = (tag, txt) => { const n = document.createElement(tag); if (txt != null) enLinea(n, txt); return n; };
  function pintarMd(md, raiz) {
    const lineas = md.replace(/\r/g, "").split("\n");
    let parrafo = [], lista = null, tipo = "";
    const cerrar = () => {
      if (parrafo.length) { raiz.append(el("p", parrafo.join(" "))); parrafo = []; }
      lista = null; tipo = "";
    };
    for (let k = 0; k < lineas.length; k++) {
      const l = lineas[k], t = l.trim();
      if (!t) { cerrar(); continue; }
      if (/^```/.test(t)) {
        cerrar(); const pre = document.createElement("pre"), buf = [];
        while (++k < lineas.length && !/^```/.test(lineas[k].trim())) buf.push(lineas[k]);
        pre.textContent = buf.join("\n"); raiz.append(pre); continue;
      }
      let m;
      if ((m = t.match(/^(#{1,6})\s+(.*)$/))) { cerrar(); raiz.append(el("h" + Math.min(4, m[1].length + 1), m[2].replace(/#+$/, ""))); continue; }
      if (k + 1 < lineas.length && /^(=+|-+)$/.test(lineas[k + 1].trim()) && !parrafo.length) { cerrar(); raiz.append(el(lineas[k + 1].trim()[0] === "=" ? "h2" : "h3", t)); k++; continue; }
      if (/^([-*_])(\s*\1){2,}$/.test(t)) { cerrar(); raiz.append(document.createElement("hr")); continue; }
      if (t[0] === "|") {
        cerrar(); const tabla = document.createElement("table");
        for (; k < lineas.length && lineas[k].trim()[0] === "|"; k++) {
          const f = lineas[k].trim();
          if (/^\|[\s:|-]+\|$/.test(f)) continue;
          const tr = document.createElement("tr");
          f.replace(/^\||\|$/g, "").split("|").forEach(c => tr.append(el("td", c.trim())));
          tabla.append(tr);
        }
        k--; raiz.append(tabla); continue;
      }
      if (t[0] === ">") { cerrar(); raiz.append(el("blockquote", t.replace(/^>\s?/, ""))); continue; }
      if ((m = t.match(/^([-*+]|\d+[.)])\s+(.*)$/))) {
        const nuevo = /\d/.test(m[1][0]) ? "ol" : "ul";
        if (parrafo.length) { raiz.append(el("p", parrafo.join(" "))); parrafo = []; }
        if (!lista || tipo !== nuevo) { lista = document.createElement(nuevo); tipo = nuevo; raiz.append(lista); }
        if (m[2].replace(/\[\]\([^)]*\)/g, "").trim()) lista.append(el("li", m[2]));
        continue;
      }
      if (lista && /^\s{2,}/.test(l) && lista.lastChild) { lista.lastChild.append(" "); enLinea(lista.lastChild, t); continue; }
      lista = null; tipo = "";
      parrafo.push(t);
    }
    cerrar();
  }

  function cargando() {
    estado.innerHTML = '<div class="v-carga" aria-label="Cargando"><span></span><span></span><span></span><span></span><span></span><span></span><span></span><span></span></div>';
  }
  function fallo() {
    estado.textContent = "";
    const h = document.createElement("h3"), p = document.createElement("p");
    h.textContent = "Ahora mismo no se puede leer desde aquí";
    p.textContent = "El lector no ha podido sacar el texto de esta web. Ábrela en su web: es un clic.";
    const a = ir.cloneNode(true); a.removeAttribute("id");
    estado.append(h, p, a);
  }

  function abrir(a) {
    actual = a.href;
    const host = new URL(actual).hostname.replace(/^www\./, ""), propio = a.textContent.trim();
    dom.textContent = host;
    titulo.textContent = propio || host;
    ir.href = actual;
    document.documentElement.style.overflow = "hidden";
    if (!d.open) d.showModal();
    if (!empujado) { history.pushState({ visor: 1 }, ""); empujado = true; }
    texto.textContent = ""; cargando(); cuerpo.scrollTop = 0;
    cuerpo.focus({ preventScroll: true });  // el foco va al texto, no a la ×: sin anillo al abrir, y las flechas desplazan
    const url = actual;
    leer(url).then(c => {
      if (url !== actual) return;
      estado.textContent = "";
      if (!propio && c.title) titulo.textContent = c.title;
      let md = c.content;
      const corto = md.length > MAX;
      if (corto) md = md.slice(0, md.lastIndexOf("\n", MAX));
      pintarMd(md, texto);
      if (corto) { const p = document.createElement("p"); p.className = "v-corte"; p.textContent = "El documento sigue. Ábrelo en su web para leerlo entero."; texto.append(p); }
    }, () => { if (url === actual) fallo(); });
  }
  function cerrar() {
    if (!d.open) return;
    d.close();
    document.documentElement.style.overflow = "";
    actual = null;
    if (empujado) { empujado = false; history.back(); }
  }

  document.addEventListener("click", ev => {
    const a = ev.target.closest("a[data-lectura]");  // sin data-lectura: no se puede leer aquí, pestaña nueva
    if (!a || ev.defaultPrevented || ev.button !== 0 || ev.metaKey || ev.ctrlKey || ev.shiftKey || ev.altKey) return;
    ev.preventDefault();
    abrir(a);
  });
  // Precarga al pasar el ratón por encima, para que al pulsar ya esté.
  let reloj;
  document.addEventListener("pointerover", ev => {
    const a = ev.target.closest && ev.target.closest("a[data-lectura]");
    clearTimeout(reloj);
    if (a && ev.pointerType === "mouse") reloj = setTimeout(() => leer(a.href), 180);
  });
  d.addEventListener("click", ev => {
    if (ev.target.closest("[data-cerrar]")) return cerrar();
    if (ev.target === d) cerrar();  // clic en el fondo
  });
  d.addEventListener("cancel", ev => { ev.preventDefault(); cerrar(); });  // Esc
  addEventListener("popstate", () => { if (d.open) { empujado = false; cerrar(); } });
})();
</script>"""


def enlace_fuente(f):
    """Enlace a una fuente: abre el visor si se puede leer (data-lectura) y, si no, pestaña nueva."""
    lectura = " data-lectura" if acceso.se_puede_leer(f["url"], ACCESO) else ""
    return (f'<a href="{e(f["url"], quote=True)}" target="_blank" rel="noopener noreferrer"{lectura}>'
            f'{e(f.get("titulo") or f["url"])}</a>')


ACCESO = {}


def panel(a):
    v = a["veredicto"]
    s = a["_t"]
    fuentes = [f for f in a.get("fuentes", []) if isinstance(f, dict)
               and str(f.get("url", "")).startswith(("http://", "https://"))]
    lista = "".join(
        f'<li>{enlace_fuente(f)} <span>{e(dominio(f["url"]))}</span></li>' for f in fuentes)
    cita = a.get("cita", "").strip("«»\" ")
    resumen = a.get("_resumen") or a.get("explicacion", "")
    # «Explicación completa» lleva a la página de la afirmación; el texto se queda oculto en la tarjeta
    # porque lo usa el botón de copiar el encargo para una IA
    detalle = ((f'<p class="completa"><a href="/{a["_slug"]}/{a["_id"]}">Explicación completa →</a></p>'
                f'<p class="explicacion-completa" hidden>{e(a["explicacion"])}</p>')
               if a.get("_resumen") and a.get("explicacion") else "")
    enlace = f"https://www.youtube.com/watch?v={a['_video']}&t={s}s"
    return (
        f'<li class="hito" data-v="{v}" id="{a["_id"]}">'
        f'<div class="dicho"><a class="minuto" href="{enlace}" data-min target="_blank" rel="noopener noreferrer" '
        f'title="Ver el vídeo en este momento">{hms(s)}</a>'
        + (f'<blockquote>«{e(cita)}»</blockquote>' if cita else "") + "</div>"
        f'<span class="punto" aria-hidden="true"></span><span class="flecha" aria-hidden="true"></span>'
        f'<article class="panel"><p class="ficha">{NOMBRE[v]}</p>'
        f'<a class="expandir" href="/{a["_slug"]}/{a["_id"]}" title="Abrir en su propia página" '
        f'aria-label="Abrir esta afirmación en su propia página">{ICONO_EXPANDIR}</a>'
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
            a["_slug"] = meta["slug"]
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
# Umami Cloud (estadísticas de visitas, sin cookies). Vacío = la web sale sin seguimiento.
# El ID es público (va en el HTML). Las cifras se ven en el panel de Umami Cloud, no en la web.
UMAMI_ID = "83bf64a7-e92e-4617-80d2-bb6a92bb2b8e"
LOGOS = {"PSOE": "psoe.svg", "PP": "pp.svg", "Frente Amplio": "frente-amplio.svg"}
# Retratos de web-src/fotos: recortes cuadrados de 320 px, centrados en la cara, de las miniaturas de Wikimedia Commons.
FOTOS = {
    "sanchez": {"autor": "Pool Moncloa / Carlos Spottorno", "licencia": "uso libre citando la fuente",
                "url": "https://commons.wikimedia.org/wiki/File:Pedro_S%C3%A1nchez_in_2026.jpg"},
    "feijoo": {"autor": "Partido Popular", "licencia": "CC0",
               "url": "https://commons.wikimedia.org/wiki/File:ALBERTO_N%C3%9A%C3%91EZ_FEIJ%C3%93O.jpg"},
    "colau": {"autor": "Robo71", "licencia": "CC0",
              "url": "https://commons.wikimedia.org/wiki/File:Ada-Colau-Encuentro-2024.jpg"},
}


def insignia(m):
    """Logotipo del partido (o sus siglas si no hay fichero)."""
    partido = m.get("partido") or ""
    fichero = LOGOS.get(partido)
    if fichero:
        return f'<img src="/logos/{fichero}" alt="" width="40" height="40">'
    return f'<b>{e("".join(w[0] for w in partido.split()[:3]).upper() or "·")}</b>'


def retrato(m, extra="", *, decorativo=False, lazy=False, con_insignia=True):
    """Foto redonda del candidato con el logotipo de su partido como insignia; sin foto, None.

    «decorativo» deja el alt vacío (cuando el nombre ya va en texto al lado), «lazy» carga la foto al acercarse y
    «con_insignia» False la deja sin el logotipo (botones de filtro)."""
    f = FOTOS.get(m["slug"])
    if not f:
        return None
    alt = "" if decorativo else e(m["invitado"])
    carga = ' loading="lazy"' if lazy else ""
    ins = f'<span class="insignia" title="{e(m.get("partido") or "")}">{insignia(m)}</span>' if con_insignia else ""
    return (f'<span class="logo retrato{extra}"><img src="/fotos/{m["slug"]}.jpg" alt="{alt}" width="160" height="160" '
            f'decoding="async"{carga}>{ins}</span>')


def barra_reparto(m, clase="barra-reparto"):
    """Barra del 100 % de las afirmaciones de una entrevista, partida por veredicto (en el orden de la leyenda)."""
    total = m["suma"] or 1
    trozos = [(k, m["total"][k]) for k in ORDEN if m["total"][k]]
    pct = lambda n: f"{round(100 * n / total)} %"
    etiqueta = ", ".join(f"{n} {PLURAL[k].lower()} ({pct(n)})" for k, n in trozos)
    return (f'<div class="{clase}" role="img" aria-label="Reparto de las {m["suma"]} afirmaciones: {etiqueta}">'
            + "".join(f'<i class="tono-{k}" style="flex:{n}" title="{PLURAL[k]}: {n} ({pct(n)})"></i>' for k, n in trozos) + "</div>")


GSAP = "3.13.0"  # gsap y SplitText desde jsDelivr, versión fijada
# Huellas SRI de esa versión. Si cambias GSAP, recalcúlalas como las de Scalar:
#   curl -s https://cdn.jsdelivr.net/npm/gsap@<versión>/dist/<fichero>.min.js | openssl dgst -sha384 -binary | openssl base64 -A
GSAP_SRI = {"gsap": "sha384-HOvlOYPIs/zjoIkWUGXkVmXsjr8GuZLV+Q+rcPwmJOVZVpvTSXQChiN4t9Euv9Vc",
            "SplitText": "sha384-xb96EMJeax+NLXMC88ZBa1xAeAW+kn+horHh/zFlbMLG2UPWhMJJSlv7fi57hS+Q"}


def muestra_hero(hechas, por_veredicto=(("falso", "enganoso"), ("verdadero",), ("mayormente_verdadero",))):
    """Afirmaciones de muestra para el carrusel del hero: de cada candidato, una falsa o engañosa, una verdadera y una casi cierta,
    alternando candidatos para que ninguno acapare el arranque. Solo citas cortas y con confianza alta."""
    rondas = []
    for grupo in por_veredicto:
        ronda = []
        for m in hechas:
            aptas = [a for a in m["todas"] if a["veredicto"] in grupo and a.get("confianza") == "alta"
                     and 40 <= len(a.get("cita", "").strip("«»\" ")) <= 120]
            aptas.sort(key=lambda a: (grupo.index(a["veredicto"]), len(a["cita"])))
            if aptas:
                ronda.append((m, aptas[0]))
        rondas.append(ronda)
    elegidas = [x for ronda in rondas for x in ronda]
    if not elegidas:
        return ""
    def item(i, m, a):
        # Fuera de la f-string: Python 3.9 no admite en ella comillas del mismo tipo ni «\» (el python3 del Mac es 3.9)
        activa = " activa" if i == 0 else ""
        oculta = "" if i == 0 else ' aria-hidden="true" inert'
        cita = e(a["cita"].strip("«»\" "))
        return (f'<li class="muestra-item tono-{a["veredicto"]}{activa}"{oculta}>'
                f'<a href="/{e(m["slug"])}#{a["_id"]}"><span class="muestra-quien">{e(m["invitado"].rpartition(" ")[2])} · {hms(a["_t"])}</span>'
                f'<span class="muestra-cita">«{cita}»</span>'
                f'<span class="estampa"><span class="sr">Veredicto: </span>{NOMBRE[a["veredicto"]]}</span></a></li>')
    items = "".join(item(i, m, a) for i, (m, a) in enumerate(elegidas))
    return ('<section class="muestra" aria-roledescription="carrusel" aria-label="Afirmaciones verificadas, de muestra">'
            '<div class="muestra-cab"><p class="muestra-rot">Así se ve una afirmación comprobada</p><div class="muestra-barra">'
            '<button class="muestra-ant" type="button" aria-label="Afirmación anterior" title="Anterior">'
            '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M15 5l-7 7 7 7"/></svg></button>'
            '<button class="muestra-sig" type="button" aria-label="Afirmación siguiente" title="Siguiente">'
            '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M9 5l7 7-7 7"/></svg></button></div></div>'
            f'<ul class="muestra-lista" aria-live="off">{items}</ul></section>')


CUANTAS = {2: "dos", 3: "tres", 4: "cuatro", 5: "cinco"}


def mini_resumen(hechas, actual=None, suelto=True):
    """Resumen para el pie de cada página: de qué se habló (meta.json «resumen»), cuántas afirmaciones son falsas o
    engañosas y el reparto por veredicto. En las páginas de una entrevista (`actual`) solo sale la suya; en las
    generales, todas."""
    if actual:
        hechas = [m for m in hechas if m["slug"] == actual]
    if not hechas:
        return ""
    tarjetas = []
    for m in hechas:
        s = e(m["slug"])
        enlaces = (f'<p class="mini-acc"><a href="/{s}">Línea temporal{ICONO_SIGUE}</a>'
                   f'<a href="/{s}/transcripcion">Transcripción{ICONO_SIGUE}</a></p>')
        if not suelto:
            # En la cabecera de la entrevista la foto, el nombre y las cifras ya están justo encima: solo el texto y los enlaces
            tarjetas.append('<article class="mini-e">' + (f'<p class="mini-res">{e(m["resumen"])}</p>' if m.get("resumen") else "")
                            + enlaces + "</article>")
            continue
        tarjetas.append(
            f'<article class="mini-e"><div class="mini-cab">{retrato(m) or ""}<div>'
            f'<h3><a href="/{s}">{e(m["invitado"])}</a></h3>'
            f'<p class="mini-meta">{e(m.get("partido") or "")} · {e(m["programa"].replace("The Wild Project ", ""))} · {e(m["duracion"])}</p></div>'
            + "</div>"
            + (f'<p class="mini-res">{e(m["resumen"])}</p>' if m.get("resumen") else "")
            + f'<p class="mini-num"><b>{m["malas"]}</b> falsas o engañosas de {m["suma"]} comprobadas</p>'
            + barra_reparto(m, "barra-reparto mini-barra")
            + enlaces + "</article>")
    n = len(hechas)
    titulo = "Esta entrevista, en corto" if actual else (f'Las {CUANTAS.get(n, n)} entrevistas, en corto' if n > 1 else "La entrevista, en corto")
    # suelto: sección propia con su ancho; si no, va dentro de un contenedor que ya lo tiene (la cabecera de cada entrevista)
    dentro = f'<h2 class="mini-t" id="mini-t">{titulo}</h2><div class="mini-lista">{"".join(tarjetas)}</div>'
    if suelto:
        dentro = f'<div class="ancho">{dentro}</div>'
    clase = "resumenes" if suelto else "resumenes en-cabeza"
    return f'<section class="{clase}" aria-labelledby="mini-t">{dentro}</section>'


def creditos_fotos(entrevistas):
    partes = [f'<a href="{f["url"]}" target="_blank" rel="noopener noreferrer">{e(m["invitado"])}</a> ({e(f["autor"])}, {f["licencia"]})'
              for m in entrevistas if (f := FOTOS.get(m["slug"]))]
    return f'<span class="creditos">Fotos vía Wikimedia Commons: {" · ".join(partes)}.</span>' if partes else ""
DEFINICIONES = {
    "verdadero": "Los datos lo confirman.",
    "mayormente_verdadero": "Cierto en lo esencial, con una imprecisión menor.",
    "enganoso": "Se apoya en algo real pero omite contexto, mezcla periodos o lleva a una conclusión que no se sigue.",
    "falso": "Los datos lo contradicen. No implica intención de mentir: incluye errores y lapsus.",
    "no_verificable": "No se encontró prueba pública suficiente, o la búsqueda automática se quedó corta.",
}


PIE = ('<p class="pie-quien"><a href="/quien">Proyecto independiente de Pablo Pardo Cotos y Diego Cristóbal Andaluz, '
       'sin relación con The Wild Project ni con ningún partido.</a></p>')
REPO_PABLO = "https://github.com/PabloPC05"
# Ficha de Pablo en /quien. Solo datos públicos (su perfil de LinkedIn y lo publicado sobre Gara); sin foto.
BIO_PABLO = ("<p>Estudia el doble grado de Matemáticas e Ingeniería Informática en la Universidad Complutense de Madrid "
             "y este curso está de intercambio SICUE en la Universidade de Santiago de Compostela.</p>"
             "<p>Es uno de los creadores de Gara, una plataforma que lleva los modelos de inteligencia artificial que predicen "
             "la estructura de las proteínas al supercomputador del CESGA. Nació en el Impacthón 2026, donde su equipo ganó el "
             "reto de la Cátedra CAMELIA de Medicina Personalizada, y sigue adelante con el apoyo de esa cátedra y del CiTIUS.</p>"
             "<p>En esta web ha hecho la transcripción y la verificación de las entrevistas, el método y la propia web: la línea "
             "temporal, las transcripciones con quién habla, la página de cada afirmación y la API abierta. Mantiene los datos y "
             "decide qué cambios entran.</p>")
ENLACES_PABLO = (f'<li><a href="{REPO_PABLO}" target="_blank" rel="noopener noreferrer">GitHub</a></li>'
                 '<li><a href="https://www.linkedin.com/in/pablo-pardo-cotos" target="_blank" rel="noopener noreferrer">LinkedIn</a></li>'
                 '<li><a href="https://gara.bio" target="_blank" rel="noopener noreferrer">Gara</a></li>')
# Ficha de Diego en /quien. Solo datos con fuente pública; sin foto.
BIO_DIEGO = ("<p>Cofundador e ingeniero full stack de aplicaciones móviles en OSIX Tech Development, una empresa de software e "
             "inteligencia artificial de Santiago de Compostela, y secretario y organizador de GDG Santiago de Compostela. Su trabajo "
             "de fin de grado de Ingeniería Informática en la Universidade de Santiago de Compostela es MydIAgram, un agente que genera "
             "diagramas de software a partir de texto.</p><p>En esta web ha hecho el rediseño visual y responsive (esquinas, menú, "
             "desplegables y fotos de los candidatos), la leyenda flotante de veredictos, las estadísticas de visitas sin cookies, "
             "la referencia interactiva de la API y la maquetación de esta página.</p>")
ENLACES_DIEGO = ('<li><a href="https://github.com/2cristo7" target="_blank" rel="noopener noreferrer">GitHub</a></li>'
                 '<li><a href="https://www.linkedin.com/in/diego-cristobal-andaluz-3a5580304" target="_blank" rel="noopener noreferrer">LinkedIn</a></li>'
                 '<li><a href="https://osix.tech/nosotros/" target="_blank" rel="noopener noreferrer">OSIX</a></li>')


def rellenar(plantilla, **valores):
    plantilla = plantilla.replace("@@HEAD_MODO@@", HEAD_MODO + transiciones.HEAD + estadisticas.seguimiento(UMAMI_ID, BASE)).replace("@@PIE@@", PIE)
    plantilla = plantilla.replace("@@REPRODUCTOR@@", JS_REPRODUCTOR)
    for k, v in valores.items():
        plantilla = plantilla.replace(f"@@{k}@@", str(v))
    return plantilla


ICONOS = ("favicon.svg", "favicon-32.png", "apple-touch-icon.png")  # van a la raíz de web/; el resto de web-src/compartir/ a web/compartir/
IMAGEN_GENERAL = "general"
IMAGEN_ANCHO, IMAGEN_ALTO = 1200, 630
NOMBRE_SITIO = "Verificación de las entrevistas de The Wild Project"


def cabecera(ruta, titulo, descripcion, imagen=IMAGEN_GENERAL, titulo_social=None, alt=None):
    """Bloque del <head> de cada página: <title>, descripción, canonical, Open Graph, Twitter Card e iconos.

    `ruta` es la ruta de la página en el sitio ("/", "/sanchez"...); las URL salen absolutas con BASE.
    `imagen` es el nombre (sin .png) de una imagen de web/compartir/. Todo se escapa aquí."""
    url = BASE + ruta
    foto = f"{BASE}/compartir/{imagen}.png"
    social = titulo_social or titulo
    alt = alt or "Verificación dato a dato de las entrevistas electorales de The Wild Project"

    def meta(clave, valor, atributo="property"):
        return f'<meta {atributo}="{clave}" content="{e(str(valor), quote=True)}">'

    lineas = [
        f"<title>{e(titulo)}</title>",
        meta("description", descripcion, "name"),
        f'<link rel="canonical" href="{e(url, quote=True)}">',
        meta("og:type", "website"), meta("og:site_name", NOMBRE_SITIO), meta("og:locale", "es_ES"),
        meta("og:title", social), meta("og:description", descripcion), meta("og:url", url),
        meta("og:image", foto), meta("og:image:width", IMAGEN_ANCHO), meta("og:image:height", IMAGEN_ALTO),
        meta("og:image:alt", alt),
        meta("twitter:card", "summary_large_image", "name"), meta("twitter:title", social, "name"),
        meta("twitter:description", descripcion, "name"), meta("twitter:image", foto, "name"),
        meta("twitter:image:alt", alt, "name"),
        '<link rel="icon" href="/favicon.svg" type="image/svg+xml">',
        '<link rel="icon" href="/favicon-32.png" type="image/png" sizes="32x32">',
        '<link rel="apple-touch-icon" href="/apple-touch-icon.png">',
    ]
    return "\n".join(lineas)


def imagen_de(slug):
    """Imagen para compartir de una entrevista; si falta, la general (y se avisa)."""
    if (RAIZ / "web-src" / "compartir" / f"{slug}.png").exists():
        return slug
    print(f"AVISO: falta web-src/compartir/{slug}.png; se usa la imagen general. "
          "Ejecuta: uv run --with pillow python herramientas/imagenes_compartir.py")
    return IMAGEN_GENERAL


def copiar_compartir():
    """Copia a web/ las imágenes y los iconos generados por herramientas/imagenes_compartir.py."""
    origen = RAIZ / "web-src" / "compartir"
    (SALIDA / "compartir").mkdir(parents=True, exist_ok=True)
    for f in sorted(origen.glob("*")) if origen.is_dir() else []:
        shutil.copy(f, SALIDA / ("" if f.name in ICONOS else "compartir") / f.name)
    if not (SALIDA / "compartir" / f"{IMAGEN_GENERAL}.png").exists():
        print("AVISO: falta web-src/compartir/general.png: las páginas apuntarán a una imagen que no existe. "
              "Ejecuta: uv run --with pillow python herramientas/imagenes_compartir.py")


def indexacion(hechas):
    """robots.txt y sitemap.xml con las páginas publicadas."""
    rutas = (["/", "/buscar", "/participa", "/metodologia", "/quien", "/api"]
             + [r for m in hechas for r in (f'/{m["slug"]}', f'/{m["slug"]}/transcripcion')]
             + [f'/{m["slug"]}/{a["_id"]}' for m in hechas for a in m["todas"]])
    (SALIDA / "sitemap.xml").write_text(
        '<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        + "".join(f"  <url><loc>{e(BASE + r)}</loc></url>\n" for r in rutas) + "</urlset>\n", encoding="utf-8")
    (SALIDA / "robots.txt").write_text(f"User-agent: *\nAllow: /\n\nSitemap: {BASE}/sitemap.xml\n", encoding="utf-8")


# ───────────────────────── Markdown → HTML (solo lo que usa METODO.md) ─────────────────────────

_EN_LINEA = re.compile(r"`([^`]+)`|\*\*(.+?)\*\*|\[([^\]]+)\]\(([^)\s]+)\)")
_ITEM = re.compile(r"^(\s*)([-*]|\d+\.)\s+(.*)$")
_SEPARADOR = re.compile(r"^\s*\|?\s*:?-+:?\s*(\|\s*:?-+:?\s*)*\|?\s*$")


def md_enlace(url):
    """Dirección de un enlace de Markdown: los ficheros relativos (CONTRIBUTING.md) van al repositorio en GitHub.
    Devuelve (href, externo), o None si el esquema no es seguro (javascript:, data:...), y el enlace queda como texto."""
    if url.startswith(("http://", "https://")):
        return url, True
    if re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*:", url):
        return None
    if url.startswith(("#", "/")):
        return url, False
    return f"{REPO}/blob/main/{url[2:] if url.startswith('./') else url}", True


def md_en_linea(texto):
    """`código`, **negrita** y [enlaces](url) de un texto; todo lo demás se escapa."""
    partes, pos = [], 0
    for m in _EN_LINEA.finditer(texto):
        partes.append(e(texto[pos:m.start()]))
        if m.group(1) is not None:
            partes.append(f"<code>{e(m.group(1))}</code>")
        elif m.group(2) is not None:
            partes.append(f"<strong>{md_en_linea(m.group(2))}</strong>")
        else:
            destino = md_enlace(m.group(4))
            if destino is None:
                partes.append(md_en_linea(m.group(3)))
            else:
                href, externo = destino
                abre = ' target="_blank" rel="noopener noreferrer"' if externo else ""
                partes.append(f'<a href="{e(href, quote=True)}"{abre}>{md_en_linea(m.group(3))}</a>')
        pos = m.end()
    partes.append(e(texto[pos:]))
    return "".join(partes)


def md_celdas(linea):
    """Celdas de una fila de tabla: separa por | salvo dentro de `código` o si va escapada (\\|)."""
    linea = linea.strip()
    if linea.startswith("|"):
        linea = linea[1:]
    if linea.endswith("|") and not linea.endswith("\\|"):
        linea = linea[:-1]
    celdas, actual, en_codigo, i = [], "", False, 0
    while i < len(linea):
        c = linea[i]
        if c == "\\" and i + 1 < len(linea) and linea[i + 1] == "|":
            actual += "|"
            i += 2
            continue
        if c == "`":
            en_codigo = not en_codigo
        if c == "|" and not en_codigo:
            celdas.append(actual.strip())
            actual = ""
        else:
            actual += c
        i += 1
    celdas.append(actual.strip())
    return celdas


def md_tabla(filas, alineacion):
    def fila(celdas, etiqueta):
        celdas = (celdas + [""] * len(alineacion))[:len(alineacion)]
        return "<tr>" + "".join(
            f'<{etiqueta}{alineacion[k]}>{md_en_linea(c)}</{etiqueta}>' for k, c in enumerate(celdas)) + "</tr>"
    return ('<div class="tabla-md"><table><thead>' + fila(filas[0], "th") + "</thead><tbody>"
            + "".join(fila(f, "td") for f in filas[1:]) + "</tbody></table></div>")


def md_id(texto, usados):
    """Identificador estable de un título: su texto sin el número de paso, en minúsculas y sin tildes."""
    base = re.sub(r"^\d+( bis)?\.\s*", "", texto)
    base = unicodedata.normalize("NFD", base.lower())
    base = re.sub(r"[^a-z0-9]+", "-", "".join(c for c in base if not unicodedata.combining(c))).strip("-") or "seccion"
    ident, n = base, 2
    while ident in usados:
        ident, n = f"{base}-{n}", n + 1
    usados.add(ident)
    return ident


def md_lista(lineas, i):
    """Lista que empieza en lineas[i]: (html, índice de la primera línea que ya no es de la lista)."""
    ordenada = _ITEM.match(lineas[i]).group(2)[0].isdigit()
    sangria = len(_ITEM.match(lineas[i]).group(1))
    primero = int(_ITEM.match(lineas[i]).group(2)[:-1]) if ordenada else 1
    items = []
    while i < len(lineas):
        m = _ITEM.match(lineas[i])
        if not m or len(m.group(1)) != sangria or m.group(2)[0].isdigit() != ordenada:
            break
        cuerpo = [m.group(3)]
        i += 1
        while i < len(lineas) and lineas[i].strip() and not (_ITEM.match(lineas[i]) and len(_ITEM.match(lineas[i]).group(1)) <= sangria):
            cuerpo.append(lineas[i].strip() if not lineas[i].startswith(" " * (sangria + 2)) else lineas[i][sangria + 2:])
            i += 1
        items.append(cuerpo)
    html_items = []
    for cuerpo in items:
        donde = next((k for k, l in enumerate(cuerpo) if k and _ITEM.match(l)), len(cuerpo))
        texto = md_en_linea(" ".join(l.strip() for l in cuerpo[:donde]))
        anidada = md_a_html("\n".join(cuerpo[donde:]))[0] if donde < len(cuerpo) else ""
        html_items.append(f"<li>{texto}{anidada}</li>")
    etiqueta = "ol" if ordenada else "ul"
    inicio = f' start="{primero}"' if ordenada and primero != 1 else ""
    return f"<{etiqueta}{inicio}>" + "".join(html_items) + f"</{etiqueta}>", i


def md_a_html(texto, usados=None):
    """Convierte el Markdown de METODO.md en HTML. Devuelve (html, títulos), con títulos = [(nivel, id, texto)].

    Cubre solo lo que usa ese fichero: títulos #, ## y ### (los ## con id para enlazarlos), párrafos, bloques de código
    con ```, citas > de varios párrafos, tablas, listas con - y con 1. (con líneas de continuación sangradas) y, en línea,
    `código`, **negrita** y [enlaces](url). Todo el texto se escapa."""
    usados = set() if usados is None else usados
    lineas, salida, titulos, i = texto.splitlines(), [], [], 0

    def empieza_bloque(k):
        l = lineas[k]
        return (l.startswith("```") or l.startswith(">") or re.match(r"^#{1,3} ", l) or _ITEM.match(l)
                or (l.lstrip().startswith("|") and k + 1 < len(lineas) and _SEPARADOR.match(lineas[k + 1])))

    while i < len(lineas):
        linea = lineas[i]
        if not linea.strip():
            i += 1
        elif linea.startswith("```"):
            i += 1
            codigo = []
            while i < len(lineas) and not lineas[i].startswith("```"):
                codigo.append(lineas[i])
                i += 1
            i += 1
            salida.append(f"<pre><code>{e(chr(10).join(codigo))}</code></pre>")
        elif re.match(r"^#{1,3} ", linea):
            nivel, _, titulo = linea.partition(" ")
            nivel, titulo = len(nivel), titulo.strip()
            ident = md_id(titulo, usados) if nivel == 2 else None
            titulos.append((nivel, ident, titulo))
            atributo = f' id="{ident}"' if ident else ""
            salida.append(f"<h{nivel}{atributo}>{md_en_linea(titulo)}</h{nivel}>")
            i += 1
        elif linea.startswith(">"):
            cita = []
            while i < len(lineas) and lineas[i].startswith(">"):
                cita.append(re.sub(r"^> ?", "", lineas[i]))
                i += 1
            salida.append("<blockquote>" + md_a_html("\n".join(cita), usados)[0] + "</blockquote>")
        elif linea.lstrip().startswith("|") and i + 1 < len(lineas) and _SEPARADOR.match(lineas[i + 1]):
            alineacion = []
            for c in md_celdas(lineas[i + 1]):
                alineacion.append(' style="text-align:center"' if c.startswith(":") and c.endswith(":")
                                  else ' style="text-align:right"' if c.endswith(":") else "")
            filas = [md_celdas(linea)]
            i += 2
            while i < len(lineas) and lineas[i].lstrip().startswith("|"):
                filas.append(md_celdas(lineas[i]))
                i += 1
            salida.append(md_tabla(filas, alineacion))
        elif _ITEM.match(linea):
            html_lista, i = md_lista(lineas, i)
            salida.append(html_lista)
        else:
            parrafo = [linea.strip()]
            i += 1
            while i < len(lineas) and lineas[i].strip() and not empieza_bloque(i):
                parrafo.append(lineas[i].strip())
                i += 1
            salida.append(f"<p>{md_en_linea(' '.join(parrafo))}</p>")
    return "\n".join(salida), titulos


def pagina_metodologia(entrevistas):
    """/metodologia: el texto de METODO.md convertido a HTML, para que el método tenga una sola fuente."""
    fuente = (RAIZ / "METODO.md").read_text(encoding="utf-8")
    lineas = fuente.splitlines()
    k = next((n for n, l in enumerate(lineas) if l.startswith("# ")), None)  # el título de la página es el primer #
    titulo = lineas[k][2:].strip() if k is not None else "Método de verificación"
    resto = "\n".join(lineas[:k] + lineas[k + 1:] if k is not None else lineas)
    cuerpo, titulos = md_a_html(resto)
    def entrada_indice(t):
        # El número va en su propia columna para que los títulos queden alineados aunque partan de línea
        m = re.match(r"(\d+(?: bis)?\.)\s+(.*)", t[2])
        num, texto = (m.group(1), m.group(2)) if m else ("", t[2])
        return f'<li><a href="#{t[1]}"><span class="n">{e(num)}</span><span class="t">{md_en_linea(texto)}</span></a></li>'
    indice = "".join(entrada_indice(t) for t in titulos if t[0] == 2)
    (SALIDA / "metodologia").mkdir(exist_ok=True)
    (SALIDA / "metodologia" / "index.html").write_text(rellenar(
        METODOLOGIA, CABECERA=cabecera(
            "/metodologia", f"{titulo} · Verificación The Wild Project",
            "El procedimiento exacto con el que se verifica cada entrevista, el encargo que recibe cada agente de IA, "
            "los criterios de cada veredicto y los límites conocidos."),
        MENU=menu(entrevistas), CSS_MENU=CSS_MENU, REPO=REPO, TITULO=e(titulo), INDICE=indice, CUERPO=cuerpo), encoding="utf-8")


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


def nombre_menu(nombre):
    """En pantallas estrechas el menú solo enseña el apellido; el nombre completo queda para las anchas."""
    resto, _, apellido = nombre.rpartition(" ")
    return f'<span class="largo">{e(resto)} </span>{e(apellido)}' if resto else e(nombre)


def menu(entrevistas, actual=None):
    """Menú superior fijo: un desplegable por candidato (línea temporal, transcripción y temas)."""
    partes = []
    for m in entrevistas:
        if not m.get("publicar"):
            partes.append(f'<span class="off" title="Verificación en curso">{e(m["invitado"])}</span>')
            continue
        s = e(m["slug"])
        def malas(n):
            return "1 falsa o engañosa" if n == 1 else f"{n} falsas o engañosas"
        temas = "".join(
            f'<li><a href="/{s}#tema-{t["n"]}" data-tema="tema-{t["n"]}"><i aria-hidden="true">{t["n"]}</i><span>{e(t["titulo"])}</span>'
            + (f'<b title="{malas(t["malas"])}"><span class="sr">, </span>{t["malas"]}<span class="sr"> {malas(t["malas"]).split(" ", 1)[1]}</span></b>'
               if t["malas"] else "") + "</a></li>" for t in m["temas"] if t["total"])
        partes.append(
            f'<details class="desp{" actual" if m["slug"] == actual else ""}"><summary>{nombre_menu(m["invitado"])}</summary><div class="lista">'
            f'<div class="lista-cab">{retrato(m, " mini") or ""}<div><p class="nombre">{e(m["invitado"])}</p>'
            f'<p class="cuanto">{e(m.get("partido") or "")} · <b>{m["malas"]}</b> falsas o engañosas de {m["suma"]}</p></div></div>'
            f'<div class="lista-acc"><a class="principal" href="/{s}">{ICONO_LINEA}<span>Línea temporal</span></a>'
            f'<a href="/{s}/transcripcion">{ICONO_TEXTO}<span>Transcripción</span></a></div>'
            f'<p class="rot">Temas con afirmaciones <span>· en rojo, las falsas o engañosas</span></p><ol class="lista-temas">{temas}</ol></div></details>')
    aqui_buscar = ' aria-current="page"' if actual == "buscar" else ""
    aqui_participa = ' aria-current="page"' if actual == "participa" else ""
    enlaces = [("/api", "Verifícalo tú", "", ""), ("/participa", "Participa", aqui_participa, ""), ("/metodologia", "Método", "", ""),
               ("/quien", "Quién lo hace", "", ""), (REPO, "GitHub" + ICONO_EXTERNO, ' target="_blank" rel="noopener noreferrer"', " gh")]
    sueltos = "".join(f'<a class="sec{c}" href="{h}"{x}>{t}</a>' for h, t, x, c in enlaces)
    # En móvil no caben: van a un desplegable «Más» a la derecha, junto con el cambio de modo
    mas = ('<details class="desp mas"><summary aria-label="Más enlaces y modo oscuro" title="Más">'
           '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 7h16M4 12h16M4 17h16"/></svg></summary><div class="lista">'
           '<ul class="mas-lista">' + "".join(f'<li><a href="{h}"{x}>{t}</a></li>' for h, t, x, c in enlaces) + '</ul>'
           + BOTON_MODO.replace('class="modo"', 'class="modo-txt"').replace("</button>", '<span>Cambiar a modo oscuro</span></button>')
           + '</div></details>')
    return ('<header class="menu"><div class="ancho"><div class="m1"><a class="sello" href="/" title="Todas las entrevistas">Verificación</a>'
            + "".join(partes) + f'<a class="dcha buscar"{aqui_buscar} href="/buscar" title="Buscar una afirmación (tecla /)">{ICONO_LUPA}<span>Buscar</span></a>'
            + sueltos + BOTON_MODO + mas + '</div></div></header>' + JS_MENU)


JS_MENU = """<script>
document.addEventListener("click", ev => document.querySelectorAll("details.desp[open]").forEach(d => {
  if (!d.contains(ev.target) || ev.target.closest(".lista a")) d.open = false;
}));
document.addEventListener("keydown", ev => {
  const abierto = document.querySelector("details.desp[open]");
  if (ev.key === "Escape" && abierto) { abierto.open = false; abierto.querySelector("summary").focus(); return; }
  if (!abierto || !["ArrowDown", "ArrowUp"].includes(ev.key)) return;
  const enlaces = [...abierto.querySelectorAll(".lista a")], i = enlaces.indexOf(document.activeElement);
  ev.preventDefault();
  enlaces[ev.key === "ArrowDown" ? (i + 1) % enlaces.length : (i <= 0 ? enlaces.length - 1 : i - 1)].focus();
});
// El desplegable cuelga de la línea inferior del menú: se calcula dónde está esa línea respecto a su contenedor
const colgar = d => {
  const l = d.querySelector(".lista"), op = l.offsetParent; if (!op) return;
  l.style.top = (document.querySelector(".menu").getBoundingClientRect().bottom - op.getBoundingClientRect().top) + "px";
};
document.querySelectorAll("details.desp").forEach(d => d.addEventListener("toggle", () => {
  if (!d.open) return;
  document.querySelectorAll("details.desp[open]").forEach(o => { if (o !== d) o.open = false; });
  colgar(d);
}));
addEventListener("resize", () => document.querySelectorAll("details.desp[open]").forEach(colgar));
const rutaActual = location.pathname.replace(/\\/$/, "");
document.querySelectorAll(".lista-acc a").forEach(a => { if (a.pathname.replace(/\\/$/, "") === rutaActual) a.setAttribute("aria-current", "page"); });
// La tecla «/» lleva al buscador (o enfoca su campo si ya se está en él), salvo si se está escribiendo
document.addEventListener("keydown", ev => {
  if (ev.key !== "/" || ev.ctrlKey || ev.metaKey || ev.altKey || ev.isComposing) return;
  const t = ev.target;
  if (t && (t.isContentEditable || /^(INPUT|TEXTAREA|SELECT)$/.test(t.tagName))) return;
  ev.preventDefault();
  const campo = document.getElementById("q");
  if (campo) { campo.focus(); campo.select(); } else location.href = "/buscar";
});
const medirMenu = () => document.documentElement.style.setProperty("--menu", document.querySelector(".menu").offsetHeight + "px");
medirMenu(); addEventListener("resize", medirMenu);
// Las cifras del hero cuentan de 0 a su valor al cargar (salvo con movimiento reducido)
if (!matchMedia("(prefers-reduced-motion: reduce)").matches) addEventListener("DOMContentLoaded", () => window.gsap && document.documentElement.classList.contains("con-gsap") || document.querySelectorAll(".dato > b, .num > b").forEach((el, i) => {
  const fin = parseInt(el.textContent, 10); if (!(fin > 0)) return;
  el.style.minWidth = el.offsetWidth + "px"; el.style.display = "inline-block";
  const t0 = performance.now() + 250 + i * 100, dur = 900;
  const paso = t => { const x = Math.min(1, Math.max(0, (t - t0) / dur)); el.textContent = Math.round(fin * (1 - Math.pow(1 - x, 3))); if (x < 1) requestAnimationFrame(paso); };
  el.textContent = "0"; requestAnimationFrame(paso);
}));
// Aviso breve para confirmar acciones; role=status hace que también lo lean los lectores de pantalla.
const avisar = (texto, mal) => {
  let a = document.querySelector(".aviso");
  if (!a) { a = document.createElement("p"); a.className = "aviso"; a.setAttribute("role", "status"); document.body.append(a); }
  a.textContent = texto; a.classList.toggle("mal", !!mal);
  requestAnimationFrame(() => a.classList.add("ver"));
  clearTimeout(avisar.t); avisar.t = setTimeout(() => a.classList.remove("ver"), 3200);
};
// Copia al portapapeles con aviso; si el navegador no deja, se ofrece el texto para copiarlo a mano.
const copiarTexto = (texto, ok) => {
  const fallo = () => { avisar("No se ha podido copiar automáticamente: cópialo del cuadro.", true); prompt("Copia este texto:", texto); };
  if (navigator.clipboard) navigator.clipboard.writeText(texto).then(() => { avisar(ok); }, fallo); else fallo();
};
(() => {
  const b = document.createElement("button");
  b.className = "arriba"; b.type = "button";
  b.innerHTML = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 20V5M5 11l7-7 7 7"/></svg>'; b.setAttribute("aria-label", "Volver arriba"); b.title = "Volver arriba";
  b.onclick = () => { scrollTo({ top: 0 }); document.querySelector(".sello")?.focus({ preventScroll: true }); };
  document.body.append(b);
  const mirar = () => b.classList.toggle("ver", scrollY > innerHeight * 1.5 && document.documentElement.scrollHeight > innerHeight * 3);
  addEventListener("scroll", mirar, { passive: true }); mirar();
})();
// Modo claro/oscuro. Sin preferencia guardada manda el sistema (lo resuelve el CSS); al pulsar se guarda y manda sobre el sistema.
// Hay dos botones: el redondo del menú (pantallas anchas) y el de texto dentro de «Más» (móvil).
const RAIZ = document.documentElement, botonesModo = document.querySelectorAll(".modo, .modo-txt"), sistemaOscuro = matchMedia("(prefers-color-scheme: dark)");
const hayOscuro = () => (RAIZ.dataset.modo || (sistemaOscuro.matches ? "oscuro" : "claro")) === "oscuro";
function etiquetarModo() {
  const t = hayOscuro() ? "Cambiar a modo claro" : "Cambiar a modo oscuro";
  botonesModo.forEach(b => {
    if (b.classList.contains("modo-txt")) b.querySelector("span").textContent = t;
    else { b.setAttribute("aria-label", t); b.title = t; }
  });
}
// Revelado circular desde el botón (View Transitions API); sin la API o con poco movimiento, el cambio es instantáneo.
function revelarModo(cambiar, boton) {
  if (!document.startViewTransition || matchMedia("(prefers-reduced-motion: reduce)").matches) { cambiar(); return; }
  const c = boton.getBoundingClientRect(), x = c.left + c.width / 2, y = c.top + c.height / 2;
  const r = Math.hypot(Math.max(x, innerWidth - x), Math.max(y, innerHeight - y));
  document.startViewTransition(cambiar).ready.then(() => RAIZ.animate(
    { clipPath: [`circle(0px at ${x}px ${y}px)`, `circle(${r}px at ${x}px ${y}px)`] },
    { duration: 420, easing: "cubic-bezier(0.4, 0, 0.2, 1)", pseudoElement: "::view-transition-new(root)" })).catch(() => {});
}
botonesModo.forEach(b => b.onclick = () => {
  const nuevo = hayOscuro() ? "claro" : "oscuro";
  revelarModo(() => { RAIZ.dataset.modo = nuevo; etiquetarModo(); }, b);
  try { localStorage.setItem("modo", nuevo); } catch (e) {}
});
sistemaOscuro.addEventListener("change", etiquetarModo);
etiquetarModo();
</script>"""

# Se ejecuta en el <head>, antes de pintar: aplica la preferencia guardada para que no haya parpadeo.
HEAD_MODO = ('<meta name="color-scheme" content="light dark">\n'
             '<script>try{var m=localStorage.getItem("modo");if(m==="claro"||m==="oscuro")document.documentElement.dataset.modo=m}catch(e){}</script>')
# Iconos de los botones de las tarjetas de la portada (trazo, heredan el color del texto)
ICONO_LINEA = ('<svg class="ico" viewBox="0 0 24 24" aria-hidden="true"><path d="M6 3v18M10 6h9M10 12h6M10 18h8"/>'
               '<circle cx="6" cy="6" r="2" class="lleno"/><circle cx="6" cy="12" r="2" class="lleno"/><circle cx="6" cy="18" r="2" class="lleno"/></svg>')
ICONO_LUPA = '<svg class="ico" viewBox="0 0 24 24" aria-hidden="true"><circle cx="10.5" cy="10.5" r="6.5"/><path d="M15.5 15.5L21 21"/></svg>'
ICONO_TEXTO = '<svg class="ico" viewBox="0 0 24 24" aria-hidden="true"><path d="M6 3h9l4 4v14H6zM14 3v5h5M9 12h7M9 16h7"/></svg>'
ICONO_FLECHA = '<svg class="flecha" viewBox="0 0 24 24" aria-hidden="true"><path d="M5 12h14M13 6l6 6-6 6"/></svg>'
# Iconos pequeños que sustituyen a «↗» y «→» en el menú y en el resumen: un glifo de texto no queda centrado con la línea
ICONO_EXTERNO = '<svg class="ic" viewBox="0 0 24 24" aria-hidden="true"><path d="M7 17L17 7M8 7h9v9"/></svg>'
ICONO_SIGUE = '<svg class="ic" viewBox="0 0 24 24" aria-hidden="true"><path d="M5 12h14M13 6l6 6-6 6"/></svg>'
ICONO_EXPANDIR = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M14 4h6v6M10 20H4v-6M20 4l-7 7M4 20l7-7"/></svg>'
# Botón flotante (abajo a la izquierda) que despliega la leyenda de veredictos. Lo usan la portada y las páginas de cada entrevista.
FAB_LEYENDA = """<div class="fab" id="fab">
<div class="fab-panel" id="fab-panel" role="dialog" aria-modal="false" aria-labelledby="fab-titulo" hidden>
<p class="fab-titulo" id="fab-titulo" tabindex="-1">Qué significa cada color</p>
@@LEYENDA_FAB@@
</div>
<button class="fab-boton" type="button" aria-expanded="false" aria-controls="fab-panel" aria-label="Ver la leyenda de veredictos">
<span class="fab-ico" aria-hidden="true"><i class="tono-falso"></i><i class="tono-enganoso"></i><i class="tono-mayormente_verdadero"></i><i class="tono-verdadero"></i></span>
<svg class="fab-x" viewBox="0 0 24 24" aria-hidden="true"><path d="M6 6l12 12M18 6L6 18"/></svg>
<span class="fab-txt">Leyenda</span></button>
</div>
<script>
(() => {
  const fab = document.getElementById("fab"), boton = fab.querySelector(".fab-boton"), panel = document.getElementById("fab-panel");
  const abrir = si => {
    if (si === fab.classList.contains("abierto")) return;
    boton.setAttribute("aria-expanded", si); boton.setAttribute("aria-label", si ? "Cerrar la leyenda" : "Ver la leyenda de veredictos");
    if (si) { panel.hidden = false; requestAnimationFrame(() => { fab.classList.add("abierto"); panel.querySelector(".fab-titulo").focus({ preventScroll: true }); }); }
    else { fab.classList.remove("abierto"); setTimeout(() => { if (!fab.classList.contains("abierto")) panel.hidden = true; }, 260); }
  };
  boton.onclick = () => abrir(!fab.classList.contains("abierto"));
  document.addEventListener("keydown", ev => { if (ev.key === "Escape" && fab.classList.contains("abierto")) { abrir(false); boton.focus(); } });
  document.addEventListener("click", ev => { if (!fab.contains(ev.target)) abrir(false); });
})();
</script>"""
# Reproductor de vídeo dentro de la página (línea temporal, transcripción y página de cada afirmación; las plantillas lo
# inyectan con @@REPRODUCTOR@@). Un clic normal en un enlace con data-min (un minuto de este vídeo) abre un panel fijo con el
# vídeo de YouTube en ese segundo; Ctrl/Cmd+clic, botón central o sin JavaScript siguen yendo a YouTube porque el href no cambia.
# No se carga nada de YouTube hasta ese primer clic: el panel y el iframe se crean entonces.
# Primer minuto: se carga el iframe con ?start=. Minutos siguientes del mismo vídeo: seekTo por postMessage (enablejsapi=1) sin
# recargar, porque recargar vuelve a pedir el anuncio previo; si YouTube no confirma el salto (no responde o se ignora durante un
# anuncio), se recarga con ?start=, que siempre funciona. No se carga iframe_api, solo se habla con el iframe.
JS_REPRODUCTOR = r"""<script>
function hora(s) { return Math.floor(s / 3600) + ":" + String(Math.floor(s % 3600 / 60)).padStart(2, "0") + ":" + String(s % 60).padStart(2, "0"); }
(() => {
  const ORIGEN = "https://www.youtube-nocookie.com";
  let panel, visor, marco, etiqueta, enlace, botonMin, estado, abridor;
  let video = "", listo = false, minimizado = false, ultimo = null, latido = 0, vigia = 0;
  const icono = d => '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="' + d + '"/></svg>';
  const medir = () => document.documentElement.style.setProperty("--repro-h", (panel && !panel.hidden ? panel.offsetHeight : 0) + "px");

  function construir() {
    panel = document.createElement("section");
    panel.className = "repro"; panel.setAttribute("role", "region"); panel.setAttribute("aria-label", "Reproductor de vídeo");
    panel.tabIndex = -1; panel.hidden = true;
    panel.innerHTML = '<div class="repro-barra"><span class="repro-t"></span>'
      + '<a class="repro-yt" target="_blank" rel="noopener noreferrer">Abrir en YouTube ' + icono("M14 4h6v6M20 4l-9 9M18 14v5a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V7a1 1 0 0 1 1-1h5") + '</a>'
      + '<button class="repro-min" type="button" aria-expanded="true"></button>'
      + '<button class="repro-x" type="button" aria-label="Cerrar el reproductor" title="Cerrar (Esc)">' + icono("M6 6l12 12M18 6L6 18") + '</button></div>'
      + '<div class="repro-video"></div><p class="sr" role="status"></p>';
    visor = panel.querySelector(".repro-video"); etiqueta = panel.querySelector(".repro-t"); enlace = panel.querySelector(".repro-yt");
    botonMin = panel.querySelector(".repro-min"); estado = panel.querySelector("[role=status]");
    botonMin.onclick = () => minimizar(!minimizado);
    panel.querySelector(".repro-x").onclick = cerrar;
    enlace.addEventListener("click", () => orden("pauseVideo"));
    document.body.append(panel);
    if (window.ResizeObserver) new ResizeObserver(medir).observe(panel);
    addEventListener("resize", medir);
  }
  function enviar(obj) { try { marco.contentWindow.postMessage(JSON.stringify(Object.assign({ id: 1, channel: "widget" }, obj)), ORIGEN); } catch (e) {} }
  const orden = (func, args) => { if (marco && listo) enviar({ event: "command", func: func, args: args || [] }); };

  // Con enablejsapi=1 el reproductor contesta cuando se le avisa de que se le escucha; mientras no conteste no se le dan órdenes
  function saludar() {
    clearInterval(latido); let n = 0;
    const hola = () => { if (listo || ++n > 40) clearInterval(latido); else enviar({ event: "listening" }); };
    latido = setInterval(hola, 250); hola();
  }
  addEventListener("message", ev => {
    if (!marco || ev.source !== marco.contentWindow || ev.origin !== ORIGEN) return;
    let d; try { d = JSON.parse(ev.data); } catch (e) { return; }
    if (!d || typeof d !== "object") return;
    if (d.event === "onReady" || d.event === "initialDelivery" || d.event === "infoDelivery") listo = true;
    if (d.info && typeof d.info.currentTime === "number") ultimo = d.info.currentTime;
  });

  function cargar(v, s) {
    video = v; listo = false; ultimo = null; clearTimeout(vigia);
    if (!marco) {
      marco = document.createElement("iframe");
      marco.title = "Vídeo de la entrevista (YouTube)";
      marco.allow = "autoplay; encrypted-media; picture-in-picture; fullscreen"; marco.allowFullscreen = true;
      marco.referrerPolicy = "strict-origin-when-cross-origin";
      marco.addEventListener("load", saludar);
      visor.append(marco);
    }
    marco.src = ORIGEN + "/embed/" + v + "?start=" + s + "&autoplay=1&enablejsapi=1&rel=0&playsinline=1&origin=" + encodeURIComponent(location.origin);
  }
  function saltar(s) {
    orden("seekTo", [s, true]); orden("playVideo");
    ultimo = null; clearTimeout(vigia);
    vigia = setTimeout(() => { if (marco && (ultimo === null || Math.abs(ultimo - s) > 30)) cargar(video, s); }, 3000);
  }
  function minimizar(si) {
    minimizado = si; panel.classList.toggle("min", si);
    botonMin.setAttribute("aria-expanded", !si);
    const t = si ? "Ampliar el reproductor" : "Minimizar el reproductor (pausa el vídeo)";
    botonMin.setAttribute("aria-label", t); botonMin.title = t;
    botonMin.innerHTML = icono(si ? "M6 15l6-6 6 6" : "M6 9l6 6 6-6");
    orden(si ? "pauseVideo" : "playVideo"); medir();
  }
  function abrir(v, s, a, teclado) {
    if (!panel) construir();
    const nuevo = panel.hidden; abridor = a;
    panel.hidden = false; document.documentElement.classList.add("con-repro");
    if (nuevo) minimizar(false);
    else if (minimizado) minimizar(false);
    enlace.href = "https://www.youtube.com/watch?v=" + v + "&t=" + s + "s";
    etiqueta.textContent = "Desde " + hora(s);
    estado.textContent = "Reproduciendo el vídeo desde " + hora(s);
    if (marco && v === video && listo) saltar(s); else cargar(v, s);
    medir();
    if (teclado) panel.focus({ preventScroll: true });
  }
  function cerrar() {
    const dentro = panel.contains(document.activeElement);
    clearInterval(latido); clearTimeout(vigia);
    if (marco) { marco.remove(); marco = null; }
    video = ""; listo = false; panel.hidden = true; document.documentElement.classList.remove("con-repro"); medir();
    if (dentro && abridor && abridor.isConnected) abridor.focus({ preventScroll: true });
  }

  // En captura sobre window: se adelanta al contador de enlaces externos de estadísticas, que ve el clic ya gestionado (defaultPrevented)
  addEventListener("click", ev => {
    const a = ev.target.closest && ev.target.closest("a[data-min]");
    if (!a || ev.defaultPrevented || ev.button !== 0 || ev.ctrlKey || ev.metaKey || ev.shiftKey || ev.altKey) return;
    let u; try { u = new URL(a.href); } catch (e) { return; }
    const v = u.searchParams.get("v"), s = parseInt(u.searchParams.get("t"), 10);
    if (!/^[\w-]{11}$/.test(v || "") || !(s >= 0)) return;
    ev.preventDefault();
    if (window.umami) umami.track("reproducir", { pagina: location.pathname, segundo: s });
    abrir(v, s, a, ev.detail === 0);
  }, true);
  // Esc cierra el reproductor, salvo que haya un menú o la leyenda abiertos: a esos les toca primero
  addEventListener("keydown", ev => {
    if (ev.key !== "Escape" || !panel || panel.hidden || document.querySelector("details.desp[open], .fab.abierto")) return;
    cerrar();
  }, true);
})();
</script>"""

# Línea temporal: lo que había dicho Jordi antes de cada cita. Los textos no van en el HTML (se repetirían en cada tarjeta):
# se leen de /<slug>/preguntas.json y se pintan aquí. En escritorio van en la columna de la cita; en móvil, dentro de la tarjeta.
JS_PREGUNTAS = r"""fetch("/@@SLUG@@/preguntas.json").then(r => r.ok ? r.json() : null).then(d => {
  if (!d) return;
  const crear = (t, x) => {
    const div = document.createElement("div"); div.className = "pregunta";
    const cab = document.createElement("p"); cab.className = "pregunta-cab";
    const cara = document.createElement("span"); cara.className = "cara"; cara.setAttribute("aria-hidden", "true"); cara.textContent = "JW";
    const quien = document.createElement("span"); quien.textContent = "Jordi Wild";
    const min = document.createElement("a"); min.className = "min-p"; min.dataset.min = ""; min.target = "_blank"; min.rel = "noopener noreferrer";
    min.href = "https://www.youtube.com/watch?v=" + d.v + "&t=" + t + "s"; min.title = "Ver el vídeo en este momento"; min.textContent = hora(t);
    cab.append(cara, quien, min);
    const texto = document.createElement("p"); texto.className = "pregunta-txt"; texto.textContent = x;
    div.append(cab, texto);
    return div;
  };
  document.querySelectorAll(".hito").forEach(li => {
    const i = d.a[li.id]; if (i === undefined) return;
    const lado = li.querySelector(".dicho .minuto"), movil = li.querySelector(".panel blockquote.movil");
    if (!lado || !movil) return;
    lado.after(crear(d.p[i][0], d.p[i][1])); movil.before(crear(d.p[i][0], d.p[i][1]));
  });
  // la tarjeta a la que apunta la dirección puede haberse movido al crecer las de encima (Chrome y Firefox lo compensan solos; Safari no)
  const ancla = location.hash.length > 1 && document.getElementById(location.hash.slice(1));
  if (ancla && !ancla.hidden) { const y = ancla.getBoundingClientRect().top; if (y < 0 || y > innerHeight * 0.6) irAlAncla(); }
}).catch(() => {});"""

BOTON_MODO = ('<button class="modo" type="button" aria-label="Cambiar a modo oscuro" title="Cambiar a modo oscuro">'
              '<svg class="luna" viewBox="0 0 24 24" aria-hidden="true"><path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z"/></svg>'
              '<svg class="sol" viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="12" r="4"/>'
              '<path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"/></svg></button>')


def filtros(m, extra="", antes=""):
    return ('<div class="filtros"><div class="ancho"><div class="fila" id="filtros">' + antes + '<span class="rot">Filtros</span>'
            f'<button data-todas aria-pressed="false">Todas <b>{m["suma"]}</b></button>'
            + "".join(f'<button data-v="{k}" aria-pressed="false"><i></i>{PLURAL[k]} <b>{m["total"][k]}</b></button>'
                      for k in ORDEN) + extra + '<span class="cuenta" aria-live="polite"></span></div></div></div>')


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
        if t["total"]:
            n_afirm = "1 afirmación" if t["total"] == 1 else f'{t["total"]} afirmaciones'
            ver = "la afirmación" if t["total"] == 1 else f'sus {t["total"]} afirmaciones'
            recuento = (f'<p class="recuento">{n_afirm}: {recuento}</p><div class="barra-tema" aria-hidden="true">{barra}</div>'
                        # Solo se ve cuando el filtro deja el tema vacío: el tema se pliega en vez de desaparecer
                        f'<p class="sin-filtro">Ninguna con el filtro actual. <button type="button" class="ver-tema">'
                        f'Ver {ver}</button></p>')
        else:
            recuento = '<p class="recuento sin">Sin afirmaciones comprobables en este tema.</p>'
        filas.append(
            f'<li class="capitulo{"" if t["total"] else " vacio"}" id="tema-{t["n"]}" data-etiqueta="Tema {t["n"]} · {e(t["titulo"], quote=True)}">'
            f'<a class="minuto" href="https://www.youtube.com/watch?v={m["video"]}&t={t["ini"]}s" data-min target="_blank" '
            f'rel="noopener noreferrer">{hms(t["ini"])}</a><span class="marca" aria-hidden="true">{t["n"]}</span>'
            f'<div class="cab-tema"><p class="num-tema">Tema {t["n"]} de {n_temas} · {hms(t["ini"])} – {hms(fin)}</p>'
            f'<h2>{e(t["titulo"])}</h2>{recuento}</div></li>')
        filas += [panel(a) for a in t["suyas"]]
    excl = len(m["excluidas"])
    nota_excl = (f' Se han dejado fuera {excl} afirmaciones sin interés para el debate público (datos personales, anécdotas, '
                 f'duración de cargos); están en <a href="{REPO}/blob/main/entrevistas/{m["slug"]}/excluidas.json" target="_blank" '
                 f'rel="noopener noreferrer">esta lista</a>.') if excl else ""
    cab = cabecera(
        f'/{m["slug"]}', f'Verificación: {m["invitado"]} en The Wild Project',
        f'{m["malas"]} de {m["suma"]} afirmaciones de {m["invitado"]} en {m["programa"]} son falsas o engañosas. '
        'Cada una enlaza al minuto exacto del vídeo, con su justificación y sus fuentes.',
        imagen_de(m["slug"]), titulo_social=f'{m["invitado"]} en The Wild Project, minuto a minuto',
        alt=f'Verificación dato a dato: {m["invitado"]} ({m.get("partido") or "sin partido"}) en {m["programa"]}')
    n_preguntas = preguntas_jordi(m)
    pagina = rellenar(
        PLANTILLA, VISOR=VISOR_FUENTE, CABECERA=cab, PREGUNTAS=JS_PREGUNTAS if n_preguntas else "", FAB=FAB_LEYENDA, MINI=mini_resumen([x for x in entrevistas if x.get("publicar")], m["slug"], suelto=False), BARRA=barra_reparto(m, "barra-reparto grande"), RETRATO=retrato(m) or "", CREDITOS=creditos_fotos([m]), MENU=menu(entrevistas, m["slug"]), CSS_MENU=CSS_MENU, LEYENDA=LEYENDA, NOTA_EXCL=nota_excl,
        FILTROS=filtros(m, '<span class="tema-actual" id="tema-actual"></span>'), SUMA=m["suma"], MALAS=m["malas"],
        FALSAS=m["total"]["falso"], ENGANOSAS=m["total"]["enganoso"], CASI=m["total"]["mayormente_verdadero"],
        VERDADERAS=m["total"]["verdadero"], NV=m["total"]["no_verificable"], FILAS="".join(filas),
        INVITADO=e(m["invitado"]), PROGRAMA=e(m["programa"]), FECHA_VIDEO=e(m["fecha"]), DURACION=e(m["duracion"]),
        FECHA=dt.datetime.now().strftime("%d/%m/%Y"), VIDEO=m["video"], SLUG=m["slug"], REPO=REPO, BASE=BASE)
    destino = SALIDA / m["slug"]
    destino.mkdir(parents=True, exist_ok=True)
    (destino / "index.html").write_text(pagina, encoding="utf-8")
    print(f'{m["slug"]}: {m["suma"]} afirmaciones · {m["total"]} · {n_preguntas} con la pregunta de Jordi')


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


def ficha_voz(m, nombres, voz):
    """Quién habla al empezar una intervención: cara (foto o iniciales), nombre y a quién representa.
    La usan la transcripción y el contexto de cada página de afirmación (`nombres` sale de hablantes.json)."""
    nombre = nombres.get(voz, "")
    iniciales = "".join(w[0] for w in nombre.split()[:2]).upper()
    if voz == "G":
        cara = (f'<img class="cara" src="/fotos/{m["slug"]}.jpg" alt="" width="34" height="34" loading="lazy" decoding="async">'
                if FOTOS.get(m["slug"]) else f'<span class="cara">{e(iniciales)}</span>')
        detalle = m.get("partido") or ""
    elif voz == "J":
        cara, detalle = f'<span class="cara">{e(iniciales)}</span>', "The Wild Project"
    else:
        cara, detalle = f'<span class="cara">{"V" if voz == "V" else "?"}</span>', ""
    return (f'<div class="quien">{cara}<span class="nom"><b>{e(nombre)}</b>'
            + (f'<small>{e(detalle)}</small>' if detalle else "") + "</span></div>")


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
            texto = e(corregir(" ".join(segmentos[k]["t"].strip() for k in ks[k0:k1 + 1])))
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
            # con voces, tres columnas como en un guion: minuto · quién habla (solo al empezar la intervención) · texto
            celda = (ficha_voz(m, nombres, voz) if n == 0 else '<div class="quien"></div>') if voces else ""
            cuerpo.append(
                f'<div class="par" id="t{t}"><a class="minuto" href="https://www.youtube.com/watch?v={m["video"]}&t={t}s" '
                f'data-min target="_blank" rel="noopener noreferrer">{hms(t)}</a>{celda}<p>{texto_marcado(p)}</p></div>')
        cuerpo.append("</div>")
    nota_voces = ("Las intervenciones se han atribuido a cada voz con reconocimiento automático de hablantes "
                  "(acierto medido del 97 %; las frases muy cortas son las que más fallan). "
                  f"Cada intervención empieza con quién habla, y la raya vertical marca lo que dice {e(m['invitado'])}. "
                  if voces else "")
    solo = '<button data-solo aria-pressed="false">Solo párrafos con afirmaciones</button>'
    cab = cabecera(
        f'/{m["slug"]}/transcripcion', f'Transcripción completa: {m["invitado"]} en The Wild Project',
        f'Transcripción completa de la entrevista de Jordi Wild a {m["invitado"]} ({m["programa"]}), con marcas de tiempo '
        'enlazadas al vídeo y a cada afirmación verificada.', imagen_de(m["slug"]),
        alt=f'Verificación dato a dato: {m["invitado"]} ({m.get("partido") or "sin partido"}) en {m["programa"]}')
    con_titulo = [t for t in m["temas"] if any(d.startswith(f'<h2 id="tema-{t["n"]}"') for d in cuerpo)]
    indice_temas = "".join(
        f'<li><a href="#tema-{t["n"]}"><span>{e(t["titulo"])}</span><small>{hms(t["ini"])}</small></a></li>' for t in con_titulo)
    # En pantallas sin hueco para el índice lateral, un desplegable en la barra de filtros hace lo mismo
    ir_tema = ('<select class="ir-tema" id="ir-tema" aria-label="Ir a un tema de la entrevista"><option value="">Temas…</option>'
               + "".join(f'<option value="tema-{t["n"]}">{t["n"]}. {e(t["titulo"])}</option>' for t in con_titulo) + '</select>')
    pagina = rellenar(
        TRANSCRIPCION, CABECERA=cab, FAB=FAB_LEYENDA, MINI=mini_resumen([x for x in entrevistas if x.get("publicar")], m["slug"]), INDICE=indice_temas, RETRATO=retrato(m, " peque") or "", MENU=menu(entrevistas, m["slug"]),
        CSS_MENU=CSS_MENU, LEYENDA=LEYENDA, FILTROS=filtros(m, solo, ir_tema), NOTA_VOCES=nota_voces,
        CUERPO=f'<div class="dialogo{" con-voces" if voces else ""}">{"".join(cuerpo)}</div>',
        INVITADO=e(m["invitado"]), PROGRAMA=e(m["programa"]), FECHA_VIDEO=e(m["fecha"]), DURACION=e(m["duracion"]),
        VIDEO=m["video"], SLUG=m["slug"], REPO=REPO)
    destino = SALIDA / m["slug"] / "transcripcion"
    destino.mkdir(parents=True, exist_ok=True)
    (destino / "index.html").write_text(pagina, encoding="utf-8")


def recortar(texto, largo):
    """Recorta un texto a `largo` caracteres en un límite de palabra; si se corta, acaba en «…»."""
    texto = " ".join(str(texto or "").split())
    if len(texto) <= largo:
        return texto
    corte = texto.rfind(" ", 0, largo)
    return texto[: corte if corte > largo // 2 else largo].rstrip(" ,;:") + "…"


def preparar_contexto(m):
    """Lo que necesitan las páginas de afirmación de una entrevista. Se lee una vez por entrevista, no por afirmación."""
    segmentos = json.loads((m["carpeta"] / "segmentos.json").read_text(encoding="utf-8"))
    ruta_h = m["carpeta"] / "hablantes.json"
    h = json.loads(ruta_h.read_text(encoding="utf-8")) if ruta_h.exists() else None
    voces = [x["voz"] for x in h["segmentos"]] if h and len(h["segmentos"]) == len(segmentos) else None
    m["_contexto"] = {
        "segmentos": segmentos, "indice": indice_segmentos(m["carpeta"]),
        "inicios": [s["i"] for s in segmentos], "voces": voces, "nombres": h["nombres"] if voces else {},
    }


def tramo_seguro(m, a):
    """Segmentos de la cita (`tramo_cita`) o, si no se localiza, el segmento que contiene su minuto."""
    ctx = m["_contexto"]
    tramo = tramo_cita(a, ctx["indice"])
    if tramo is None:
        k = max(0, bisect.bisect_right(ctx["inicios"], a["_t"] + 2) - 1)
        tramo = (k, k)
    return tramo


def contexto_cita(m, a):
    """HTML de los segmentos alrededor de la cita: la cita en <mark> con el color del veredicto y, si hay hablantes, quién habla."""
    ctx = m["_contexto"]
    segmentos, voces = ctx["segmentos"], ctx["voces"]
    desde, hasta = tramo_seguro(m, a)
    lo, hi = max(0, desde - 4), min(len(segmentos) - 1, hasta + 4)
    # agrupa segmentos seguidos de la misma voz en un párrafo
    grupos = []
    for k in range(lo, hi + 1):
        voz = voces[k] if voces else None
        if not grupos or grupos[-1][0] != voz:
            grupos.append((voz, []))
        grupos[-1][1].append(k)
    parrafos = []
    for voz, ks in grupos:
        out, dentro = "", False
        for k in ks:
            en = desde <= k <= hasta
            t = e(segmentos[k]["t"].strip())
            if en and not dentro:
                out += (" " if out else "") + "<mark>" + t
            elif not en and dentro:
                out += "</mark> " + t
            else:
                out += (" " if out else "") + t
            dentro = en
        if dentro:
            out += "</mark>"
        t0 = int(segmentos[ks[0]]["i"])
        # mismo lenguaje visual que la transcripción: quién habla arriba, raya vertical en lo que dice el candidato
        parrafos.append(
            f'<div class="turno" data-voz="{voz or ""}"><div class="cab-turno">'
            + (ficha_voz(m, ctx["nombres"], voz) if voces else "")
            + f'<a class="minuto" href="https://www.youtube.com/watch?v={m["video"]}&t={t0}s" '
            f'data-min target="_blank" rel="noopener noreferrer">{hms(t0)}</a></div><p>{out}</p></div>')
    return "".join(parrafos)


PREGUNTA_MIN_PALABRAS = 6   # una intervención de Jordi más corta («claro», «ya», «vale») no sirve de contexto, salvo que sea una pregunta
PREGUNTA_BREVE = 12         # entre 6 y 11 palabras (y sin «?») suele ser un comentario suelto mientras el invitado habla: solo vale
PREGUNTA_INMEDIATA = 4      #   si el invitado empieza a responder en ≤ 4 s; si no, se busca la pregunta de verdad, más atrás
PREGUNTA_MAX_PALABRAS = 45  # si es más larga se queda el final, donde suele estar la pregunta
PREGUNTA_VENTANA = 600      # a más de 10 minutos de la cita ya no es la pregunta a la que responde


def pregunta_previa(m, a):
    """Lo que Jordi Wild había dicho o preguntado justo antes de la cita: (segundo, texto), o None.

    Es la última intervención de Jordi (segmentos seguidos con voz «J») anterior a la cita, saltando las muy cortas
    (menos de 6 palabras sin «?») y las breves que no son la respuesta inmediata (menos de 12 palabras sin «?», con la cita a más de 4 s).
    Si pasa de PREGUNTA_MAX_PALABRAS se queda el final, empezando en un inicio de frase si hay uno cerca, con «…» delante."""
    ctx = m["_contexto"]
    voces, segmentos = ctx["voces"], ctx["segmentos"]
    if not voces:
        return None
    desde = tramo_seguro(m, a)[0]
    k = desde - 1
    while True:
        while k >= 0 and voces[k] != "J":
            k -= 1
        if k < 0:
            return None
        fin = k
        while k >= 0 and voces[k] == "J":
            k -= 1
        hueco = segmentos[desde]["i"] - segmentos[fin]["f"]
        if hueco > PREGUNTA_VENTANA:
            return None
        palabras = [(w, j) for j in range(k + 1, fin + 1) for w in segmentos[j]["t"].split()]
        if (palabras[-1][0].endswith("?") or len(palabras) >= PREGUNTA_BREVE
                or (len(palabras) >= PREGUNTA_MIN_PALABRAS and hueco <= PREGUNTA_INMEDIATA)):
            break
    # La separación de voces a veces corta a Jordi a mitad de frase («en determinar qué pasó?»): si su intervención empieza
    # en minúscula y el segmento anterior no cierra frase, ese segmento es casi seguro el principio de la misma frase.
    inicio = k + 1
    for _ in range(2):
        primera = segmentos[inicio]["t"].strip().lstrip("¿¡«\"'(")
        previo = segmentos[inicio - 1]["t"].strip() if inicio > 0 else ""
        if not primera[:1].islower() or not previo or previo[-1] in ".?!…":
            break
        inicio -= 1
    palabras = [(w, j) for j in range(inicio, fin + 1) for w in segmentos[j]["t"].split()]
    n = len(palabras)
    corte = 0
    if n > PREGUNTA_MAX_PALABRAS:
        corte = n - PREGUNTA_MAX_PALABRAS
        # inicio de frase (la palabra anterior acaba en . ? ! …) que deje entre 25 y 60 palabras, lo más cerca de 45
        inicios = [i for i in range(1, n) if palabras[i - 1][0][-1] in ".?!…" and 25 <= n - i <= 60]
        if inicios:
            corte = min(inicios, key=lambda i: abs(n - i - PREGUNTA_MAX_PALABRAS))
    texto = " ".join(w for w, _ in palabras[corte:])
    a_medias = texto.lstrip("¿¡«\"'(")[:1].islower()  # sigue empezando a mitad de frase: que se note
    return int(segmentos[palabras[corte][1]]["i"]), ("…" + texto if corte or a_medias else texto)


def preguntas_jordi(m):
    """Escribe web/<slug>/preguntas.json con la pregunta previa de cada afirmación y devuelve cuántas hay.

    Va aparte del HTML de la línea temporal (muchas afirmaciones comparten pregunta y el texto pesaría en cada página) y se
    pinta con JavaScript. Formato: {"v": vídeo, "p": [[segundo, texto], …], "a": {id de afirmación: posición en "p"}}."""
    unicas, lugar, por_id = [], {}, {}
    for a in m["todas"]:
        q = pregunta_previa(m, a)
        if q:
            if q not in lugar:
                lugar[q] = len(unicas)
                unicas.append(list(q))
            por_id[a["_id"]] = lugar[q]
    ruta = SALIDA / m["slug"] / "preguntas.json"
    ruta.parent.mkdir(parents=True, exist_ok=True)
    if unicas:
        ruta.write_text(json.dumps({"v": m["video"], "p": unicas, "a": por_id}, ensure_ascii=False, separators=(",", ":")),
                        encoding="utf-8")
    elif ruta.exists():
        ruta.unlink()
    return len(por_id)


def pagina_afirmacion(m, a, entrevistas, anterior, siguiente):
    """Página propia de una afirmación (/<slug>/<id>): cita, veredicto, explicación, fuentes y contexto en la entrevista."""
    v, slug, idx = a["veredicto"], m["slug"], a["_id"]
    ruta = f"/{slug}/{idx}"
    afirmacion = " ".join(a.get("afirmacion", "").split())
    cita = a.get("cita", "").strip("«»\" ")
    minuto = hms(a["_t"])
    enlace_video = f"https://www.youtube.com/watch?v={a['_video']}&t={a['_t']}s"
    resumen = a.get("_resumen") or a.get("explicacion", "")
    tema = next((t for t in m["temas"] if t["n"] == a.get("_tema")), None)
    migas = (f'<a href="/{slug}">{e(m["invitado"])}</a> › '
             + (f'Tema {tema["n"]} · {e(tema["titulo"])} › ' if tema else "") + minuto)

    cita_html = (f'<blockquote>«{e(cita)}»</blockquote>' if cita else "") + (
        f'<p class="cita-pie">— {e(m["invitado"])}, <a href="{enlace_video}" data-min target="_blank" '
        f'rel="noopener noreferrer">{minuto}</a></p>')
    por_que = ""
    if a.get("_resumen"):
        por_que += f'<p class="resumen">{e(a["_resumen"])}</p>'
    if a.get("explicacion"):
        por_que += f'<p class="explicacion">{e(a["explicacion"])}</p>'
    if a.get("confianza"):
        por_que += f'<p class="confianza">Confianza: <b>{e(str(a["confianza"]))}</b></p>'

    fuentes = [f for f in a.get("fuentes", []) if isinstance(f, dict)
               and str(f.get("url", "")).startswith(("http://", "https://"))]
    fuentes_html = ""
    if fuentes:
        items = "".join(
            f'<li>{enlace_fuente(f)} <span>{e(dominio(f["url"]))}</span></li>' for f in fuentes)
        fuentes_html = f'<section class="seccion"><h2>Fuentes</h2><ol class="fuentes">{items}</ol></section>'

    ver_tema = f"/{slug}/transcripcion" + (f"#tema-{a['_tema']}" if a.get("_tema") else "")
    contexto = (f'<section class="seccion"><h2>Contexto en la entrevista</h2><div class="contexto">{contexto_cita(m, a)}</div>'
                f'<p class="mas"><a href="{ver_tema}">Leer la transcripción completa</a></p></section>')

    # formulario «Avisar de un error» de la propia web (/avisar) con la afirmación ya rellenada:
    # a quien avisa solo le queda pegar las fuentes. Lo publica como incidencia la función web-src/avisar.js
    url_error = f"/avisar?ruta={quote(ruta)}&a={quote(m['invitado'] + ', ' + minuto)}"

    def vecina(b, clase, rotulo):
        if not b:
            return "<span></span>"
        return (f'<a class="vecina {clase}" href="/{slug}/{b["_id"]}" rel="{"prev" if clase == "ant" else "next"}">'
                f'<span class="rot-v">{rotulo}</span>'
                f'<span class="tiempo">{hms(b["_t"])} · <b data-v="{b["veredicto"]}">{NOMBRE[b["veredicto"]]}</b></span>'
                f'<small>{e(recortar(b.get("afirmacion", ""), 80))}</small></a>')

    descripcion = recortar(resumen, 200) or f"Verificación de una afirmación de {m['invitado']} en The Wild Project."
    cab = cabecera(
        ruta, f'{NOMBRE[v]}: {recortar(afirmacion, 90)} · {m["invitado"]}', descripcion, imagen_de(slug),
        titulo_social=f'{NOMBRE[v]}: {afirmacion}',
        alt=f'Verificación dato a dato: {m["invitado"]} ({m.get("partido") or "sin partido"}) en {m["programa"]}')
    pagina = rellenar(
        AFIRMACION, VISOR=VISOR_FUENTE, CABECERA=cab, CSS_MENU=CSS_MENU, MENU=menu(entrevistas, slug), MIGAS=migas, V=v,
        VEREDICTO=NOMBRE[v], AFIRMACION=e(afirmacion), CITA=cita_html, POR_QUE=por_que, FUENTES=fuentes_html,
        CONTEXTO=contexto, VER_LINEA=f"/{slug}#{idx}", URL_PAGINA=e(BASE + ruta, quote=True), URL_ERROR=e(url_error, quote=True),
        ANTERIOR=vecina(anterior, "ant", "← Anterior"), SIGUIENTE=vecina(siguiente, "sig", "Siguiente →"))
    destino = SALIDA / slug / idx
    destino.mkdir(parents=True, exist_ok=True)
    (destino / "index.html").write_text(pagina, encoding="utf-8")


# ───────────────────────── Buscador (/buscar) ─────────────────────────

# Búsquedas de ejemplo del estado vacío de /buscar. Salen de verdad en los datos y están repartidas entre los tres candidatos
# (indice_busqueda() avisa si alguna deja de salir o si dejan de cubrirlos a todos).
EJEMPLOS_BUSQUEDA = ["vivienda", "inmigración", "pensiones", "Marruecos", "corrupción", "amnistía", "Trump", "deuda"]


def _plano(texto):
    """Minúsculas y sin tildes: la misma normalización que hace el buscador en el navegador."""
    t = unicodedata.normalize("NFD", str(texto).lower())
    return "".join(c for c in t if unicodedata.category(c) != "Mn")


def indice_busqueda(hechas):
    """web/buscar/indice.json: lo justo para buscar y pintar cada resultado, mucho más ligero que afirmaciones.json.

    Formato: {"c": [[slug, invitado, partido, retrato]], "t": [temas], "a": [[candidato, veredicto, segundo, id, tema, cita, afirmación,
    resumen, [títulos de las fuentes]]]}. «candidato» y «tema» son posiciones en "c" y "t"; «veredicto» es la posición en ORDEN.
    «retrato» es el HTML de retrato() (foto y logotipo del partido, o siglas), una sola vez por candidato; "" si no hay foto."""
    temas, filas, textos = [], [], []
    for n, m in enumerate(hechas):
        for a in m["todas"]:
            tema = next((t["titulo"] for t in m["temas"] if t["n"] == a.get("_tema")), "")
            if tema not in temas:
                temas.append(tema)
            fuentes = []
            for f in a.get("fuentes", []):
                if isinstance(f, dict) and str(f.get("url", "")).startswith(("http://", "https://")):
                    titulo = " ".join(str(f.get("titulo") or "").split())
                    if titulo and titulo not in fuentes:
                        fuentes.append(titulo)
            filas.append([n, ORDEN.index(a["veredicto"]), a["_t"], a["_id"], temas.index(tema),
                          " ".join(a.get("cita", "").strip("«»\" ").split()), " ".join(a.get("afirmacion", "").split()),
                          " ".join((a.get("_resumen") or a.get("explicacion", "")).split()), fuentes])
            textos.append((n, _plano(" ".join([m["invitado"], tema] + [str(x) for x in filas[-1][5:8]] + fuentes))))
    datos = {"c": [[m["slug"], m["invitado"], m.get("partido") or "", retrato(m, " res-foto", decorativo=True, lazy=True) or ""] for m in hechas], "t": temas, "a": filas}
    destino = SALIDA / "buscar"
    destino.mkdir(exist_ok=True)
    ruta = destino / "indice.json"
    ruta.write_text(json.dumps(datos, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
    # Comprobación de los ejemplos con la misma regla del navegador (la palabra aparece en algún campo de la afirmación)
    cubiertos = set()
    for ej in EJEMPLOS_BUSQUEDA:
        quien = {n for n, texto in textos if _plano(ej) in texto}
        if not quien:
            print(f'AVISO: la búsqueda de ejemplo «{ej}» de /buscar no sale en ninguna afirmación')
        cubiertos |= quien
    if len(cubiertos) < len(hechas):
        print("AVISO: las búsquedas de ejemplo de /buscar no cubren a todos los candidatos")
    return ruta.stat().st_size


def pagina_buscar(entrevistas, hechas):
    total = sum(m["suma"] for m in hechas)
    botones_c = "".join(
        f'<button type="button" data-c="{e(m["slug"])}" aria-pressed="false">'
        f'{retrato(m, " chica", decorativo=True, con_insignia=False) or ""}{e(m["invitado"])} <b></b></button>' for m in hechas)
    botones_v = "".join(f'<button type="button" data-v="{k}" aria-pressed="false"><i></i>{PLURAL[k]} <b></b></button>' for k in ORDEN)
    ejemplos = "".join(f'<button type="button" data-ej="{e(x, quote=True)}">{e(x)} <b></b></button>' for x in EJEMPLOS_BUSQUEDA)
    (SALIDA / "buscar").mkdir(exist_ok=True)
    (SALIDA / "buscar" / "index.html").write_text(rellenar(
        BUSCAR, CABECERA=cabecera(
            "/buscar", "Buscar una afirmación · Verificación The Wild Project",
            f"Busca entre las {total} afirmaciones comprobadas de las entrevistas de The Wild Project: por tema, palabra, cifra o nombre, "
            "y filtra por candidato y veredicto."),
        MENU=menu(entrevistas, "buscar"), CSS_MENU=CSS_MENU, TOTAL=total, BOTONES_C=botones_c, BOTONES_V=botones_v,
        EJEMPLOS=ejemplos, ICONO_LUPA=ICONO_LUPA, NOMBRES=json.dumps([NOMBRE[k] for k in ORDEN], ensure_ascii=False),
        CLAVES=json.dumps(ORDEN), REPO=REPO), encoding="utf-8")


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
        "video_url": f'https://www.youtube.com/watch?v={m["video"]}&t={a["_t"]}s', "web_url": f'{BASE}/{m["slug"]}#{a["_id"]}', "pagina_url": f'{BASE}/{m["slug"]}/{a["_id"]}',
        "cita": a.get("cita", ""), "afirmacion": a.get("afirmacion", ""), "veredicto": a["veredicto"],
        "resumen": a.get("_resumen"), "explicacion": a.get("explicacion", ""), "confianza": a.get("confianza"),
        "fuentes": [{"titulo": f.get("titulo", ""), "url": f["url"]} for f in a.get("fuentes", [])
                    if isinstance(f, dict) and str(f.get("url", "")).startswith(("http://", "https://"))],
    }


def escribir_json(ruta, datos):
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_text(json.dumps(datos, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")


def generar_api(hechas):
    # Restos de cuando los datos vivían en web/api/ y del panel privado de visitas, ya retirado.
    shutil.rmtree(SALIDA / "api", ignore_errors=True)
    shutil.rmtree(SALIDA / "panel", ignore_errors=True)
    api = DATOS / "v1"
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
            nota="Transcripción automática (Whisper), que puede tener errores en nombres y cifras. Los nombres mal transcritos "
                 f"más claros se corrigen con un glosario público ({REPO}/blob/main/entrevistas/glosario.json). El hablante de cada "
                 "segmento sale de un reconocimiento automático de voces (acierto medido del 97 %; falla sobre todo en frases muy cortas).",
            segmentos=[{"inicio_s": round(x["i"], 2), "fin_s": round(x["f"], 2), "hablante": v, "texto": corregir(x["t"].strip())}
                       for x, v in zip(segs, voces)]))
        (api / m["slug"] / "transcripcion.txt").write_text(
            corregir((m["carpeta"] / "transcripcion.txt").read_text(encoding="utf-8")), encoding="utf-8")
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
        "redirects": [{"source": "/api/referencia", "destination": "/api", "permanent": True},
                      {"source": "/verificalo", "destination": "/api#verificalo", "permanent": True},
                      {"source": "/verificalo/", "destination": "/api#verificalo", "permanent": True}],
        # Las URL públicas siguen siendo /api y /api/v1/*; los ficheros están en web/datos/ (ver DATOS).
        "rewrites": [{"source": "/api", "destination": "/datos/index.html"},
                     {"source": "/api/", "destination": "/datos/index.html"},
                     {"source": "/api/v1/:ruta*", "destination": "/datos/v1/:ruta*"}],
        "headers": [
        {"source": "/api/v1/(.*)", "headers": [{"key": "Access-Control-Allow-Origin", "value": "*"},
                                               {"key": "Cache-Control", "value": "public, max-age=300"}]},
        {"source": "/llms.txt", "headers": [{"key": "Access-Control-Allow-Origin", "value": "*"}]},
        # La ruta interna /datos/ no se indexa: la pública es /api.
        {"source": "/datos/(.*)", "headers": [{"key": "X-Robots-Tag", "value": "noindex"}]}]}, indent=1) + "\n")
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
    prompt = prompt_agente(hechas)
    encargo = encargo_auditoria()
    descripcion = f"""API estática de solo lectura con todas las afirmaciones verificadas de las entrevistas de Jordi Wild a los
candidatos a las elecciones generales del 29 de noviembre de 2026: la cita literal, el veredicto, la explicación, las fuentes y el
segundo exacto del vídeo. También publica las transcripciones completas.

> {aviso}

## Prompt para agentes de IA

Pega este prompt en un agente o asistente que pueda hacer peticiones web (Claude, ChatGPT, Gemini, Perplexity o tu propio
agente), como instrucciones de sistema o como primer mensaje, y escribe tu pregunta al final. Le explica estas rutas, qué trae
cada campo y cómo citar (id, minuto con su vídeo y fuentes).

**[Abrir en Claude](https://claude.ai/new?q={quote(prompt)})** · **[Abrir en ChatGPT](https://chatgpt.com/?q={quote(prompt)})** ·
[llms.txt]({BASE}/llms.txt)

```text
{prompt}
```

Para auditar los veredictos uno a uno hay otro encargo más abajo, en «Verifícalo tú».
Una IA también se equivoca: pídele siempre los enlaces y ábrelos.

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
Si encuentras un dato mal verificado, avísanos con el [formulario]({BASE}/avisar), y si echas en falta algo que se dijo, [propón un hecho para verificar]({BASE}/proponer). En los dos hace falta un enlace a una fuente.

## Verifícalo tú

No hace falta que te creas esta verificación: está hecha con IA y no la ha revisado un equipo de periodistas. Todo está
publicado para que lo compruebes a mano, con los datos de esta API o con tu propia IA.

1. **Mira el momento exacto.** En la [línea temporal]({BASE}/) de cada entrevista, el minuto de cada afirmación abre el vídeo
   en ese segundo. Escucha la frase y su contexto.
2. **Abre las fuentes.** Cada afirmación lista sus fuentes con su enlace, y su página explica qué dato sale de cada una.
3. **Pásaselo a una IA.** Cada afirmación tiene un botón que copia un encargo para revisarla. Para auditar entrevistas
   enteras, usa el encargo de abajo.
4. **Usa los datos.** Todo está en esta API, en JSON y CSV, sin clave. El [método]({BASE}/metodologia) explica cómo se hizo,
   y el código y los datos están en [GitHub]({REPO}).

### Encargo para auditar la verificación con una IA

Pégalo en un asistente que pueda navegar por internet (Claude, ChatGPT, Gemini, Perplexity…). Revisa las afirmaciones
falsas y engañosas de todas las entrevistas; para una sola, pídele que use `{{slug}}.json` (por ejemplo, `sanchez.json`).

**[Abrir en Claude](https://claude.ai/new?q={quote(encargo)})** · **[Abrir en ChatGPT](https://chatgpt.com/?q={quote(encargo)})**

```text
{encargo}
```

Una IA también se equivoca: pídele siempre los enlaces y ábrelos. Si su respuesta contradice un veredicto con una fuente
sólida, [avísanos]({BASE}/avisar) con esa fuente y lo revisamos. Si encuentras algo que se dijo y no está verificado,
[propónlo]({BASE}/proponer).

### Con una hoja de cálculo

En Google Sheets, pega esto en una celda para cargar todas las afirmaciones:

```text
=IMPORTDATA("{BASE}/api/v1/afirmaciones.csv")
```

En Excel: *Datos → Obtener datos → Desde la web*, y pega `{BASE}/api/v1/afirmaciones.csv`.

### Con la terminal, Python o JavaScript

Las afirmaciones falsas de una entrevista, con sus fuentes:

```bash
curl -s {BASE}/api/v1/{ejemplo}.json \\
  | jq '.afirmaciones[] | select(.veredicto == "falso") | {{minuto, cita, resumen, fuentes}}'
```

```python
import json, urllib.request

datos = json.load(urllib.request.urlopen("{BASE}/api/v1/afirmaciones.json"))
for a in datos["afirmaciones"]:
    if a["veredicto"] in ("falso", "enganoso"):
        print(a["invitado"], a["minuto"], a["veredicto"], a["afirmacion"])
```

```javascript
const r = await fetch("{BASE}/api/v1/entrevistas.json");
const {{ entrevistas }} = await r.json();
entrevistas.forEach(e => console.log(e.invitado, e.por_veredicto));
```
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
                                            "web_url", "pagina_url", "cita", "afirmacion", "veredicto", "resumen", "explicacion", "confianza", "fuentes"],
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
                                   "pagina_url": dict(url, description="Página propia de la afirmación, con la cita, la explicación, las fuentes y el contexto."),
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


def encargo_auditoria():
    """Encargo para que una IA audite los veredictos (antes en /verificalo). Va en la sección «Verifícalo tú» de /api."""
    return f"""Eres un verificador de datos independiente, riguroso e imparcial. Vas a auditar una verificación hecha con IA de las entrevistas de Jordi Wild (The Wild Project) a los candidatos a las elecciones generales españolas del 29 de noviembre de 2026.

DATOS (JSON público, sin clave)
- Guía de la API: {BASE}/llms.txt
- Afirmaciones verificadas: {BASE}/api/v1/afirmaciones.json (o una sola entrevista: {BASE}/api/v1/{{slug}}.json)
- Transcripción con marcas de tiempo: {BASE}/api/v1/{{entrevista}}/transcripcion.txt (el campo "entrevista" de cada afirmación da el nombre)
Cada afirmación trae: id, minuto, video_url, cita (literal), afirmacion, veredicto, explicacion, confianza y fuentes[{{titulo, url}}]. Las definiciones de los veredictos están en el campo "veredictos" del JSON.

TAREA
Descarga las afirmaciones y revisa las que tienen "veredicto" igual a "falso" o "enganoso". Para cada una:
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
4. Una frase final: cuántas has revisado, en cuántas coincides y cuánto te fías del conjunto."""


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
    buenas_v = [("mayormente_verdadero", "Casi ciertas"), ("verdadero", "Verdaderas")]

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
              for k, nombre in buenas_v]
    filas.append(("Verdaderas o casi ciertas", "".join(
        celda_n(m, m["total"]["verdadero"] + m["total"]["mayormente_verdadero"]) for m in hechas), ' class="fuerte"'))
    filas.append(('<i class="tono-no_verificable"></i>No verificables',
                  "".join(celda_n(m, m["total"]["no_verificable"]) for m in hechas), ' class="tono-no_verificable"'))
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
    # Qué fuentes se pueden leer en el visor. Al generar solo se usa la caché (web-src/acceso.json), sin red, para que
    # regenerar sea rápido y no dependa de r.jina.ai (tampoco en la comprobación de las PR). Las fuentes nuevas abren en
    # pestaña nueva hasta que alguien ejecute `python3 web-src/acceso.py`.
    ACCESO.update(acceso.cargar())
    sin_mirar = acceso.urls_de_las_entrevistas() - set(ACCESO)
    if sin_mirar:
        print(f"AVISO: {len(sin_mirar)} fuentes sin comprobar para el visor (abren en pestaña nueva). Ejecuta: python3 web-src/acceso.py")
    SALIDA.mkdir(exist_ok=True)
    for m in hechas:
        preparar_contexto(m)
        pagina_entrevista(m, entrevistas)
        pagina_transcripcion(m, entrevistas)
        for n, a in enumerate(m["todas"]):
            pagina_afirmacion(m, a, entrevistas,
                              m["todas"][n - 1] if n > 0 else None,
                              m["todas"][n + 1] if n + 1 < len(m["todas"]) else None)
    ejemplo, slugs = generar_api(hechas)
    indice_busqueda(hechas)
    pagina_buscar(entrevistas, hechas)
    copiar_compartir()
    indexacion(hechas)
    (SALIDA / "fotos").mkdir(exist_ok=True)
    for f in (RAIZ / "web-src" / "fotos").glob("*.jpg"):
        shutil.copy(f, SALIDA / "fotos" / f.name)
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
        f'<article class="entrevista">{retrato(m) or logo(m)}<div><h2><a href="/{e(m["slug"])}">{e(m["invitado"])}</a></h2>'
        f'<p class="partido">{e(m.get("partido") or "")}</p>'
        f'<p class="prog">{e(m["programa"])} · {e(m["fecha"])} · {e(m["duracion"])}</p>'
        f'<p class="num"><b>{m["malas"]}</b> falsas o engañosas de {m["suma"]} afirmaciones comprobadas</p>{barra_reparto(m)}'
        f'<p class="des">' + " · ".join(f'<span class="tono-{k}">{m["total"][k]} {PLURAL[k].lower()}</span>' for k in ORDEN) + "</p>"
        f'</div><p class="acc"><a class="btn principal" href="/{e(m["slug"])}">{ICONO_LINEA}<span>Línea temporal</span>{ICONO_FLECHA}</a>'
        f'<a class="btn" href="/{e(m["slug"])}/transcripcion">{ICONO_TEXTO}<span>Transcripción<span class="sr"> completa</span></span>{ICONO_FLECHA}</a></p></article>'
        for m in hechas)
    tarjetas += "".join(
        f'<article class="entrevista off">{logo(m)}<div><h2>{e(m["invitado"])}</h2><p class="partido">{e(m.get("partido") or "")}</p>'
        f'<p class="prog">{e(m.get("programa", ""))}</p><p class="des">Verificación en curso.</p></div></article>'
        for m in entrevistas if not m.get("publicar"))
    (SALIDA / "index.html").write_text(rellenar(
        PORTADA, LEYENDA_LINEA=LEYENDA_LINEA, MUESTRA=muestra_hero(hechas), GSAP=GSAP, GSAP_SRI=GSAP_SRI["gsap"], SPLIT_SRI=GSAP_SRI["SplitText"], CABECERA=cabecera(
            "/", "Verificación de las entrevistas electorales de The Wild Project",
            "Las entrevistas de Jordi Wild a los candidatos a las elecciones generales de 2026, comprobadas dato a dato "
            "con el mismo método. Código y datos abiertos."), CREDITOS=creditos_fotos(hechas), MENU=menu(entrevistas), CSS_MENU=CSS_MENU, LEYENDA=LEYENDA, COMPARATIVA=comparativa(hechas), TARJETAS=tarjetas, REPO=REPO,
        FECHA=dt.datetime.now().strftime("%d/%m/%Y")), encoding="utf-8")
    # «Verifícalo tú» vive ahora al final de la introducción de /api; /verificalo redirige allí (aquí y en vercel.json)
    opciones = "".join(f'<option value="{e(m["slug"])}">{e(m["invitado"])}</option>' for m in hechas)
    (SALIDA / "verificalo").mkdir(exist_ok=True)
    (SALIDA / "verificalo" / "index.html").write_text(
        '<!doctype html><html lang="es"><head><meta charset="utf-8"><meta http-equiv="refresh" content="0; url=/api#verificalo">'
        '<link rel="canonical" href="' + BASE + '/api"><meta name="robots" content="noindex"><title>Verifícalo tú</title></head>'
        '<body><p>«Verifícalo tú» está ahora en <a href="/api#verificalo">la página de la API</a>.</p></body></html>\n', encoding="utf-8")
    (SALIDA / "quien").mkdir(exist_ok=True)
    (SALIDA / "quien" / "index.html").write_text(rellenar(
        QUIEN, ANALITICA=ANALITICA_QUIEN if UMAMI_ID else SIN_ANALITICA_QUIEN, CABECERA=cabecera(
            "/quien", "Quién hace esto · Verificación The Wild Project",
            "Quién hace esta verificación, su independencia, quién la paga, cómo se hace y cómo se corrigen los errores."),
        MENU=menu(entrevistas), MINI=mini_resumen(hechas), CSS_MENU=CSS_MENU, REPO=REPO, REPO_PABLO=REPO_PABLO, BIO_PABLO=BIO_PABLO, ENLACES_PABLO=ENLACES_PABLO, BIO_DIEGO=BIO_DIEGO, ENLACES_DIEGO=ENLACES_DIEGO), encoding="utf-8")
    # formularios que no salen de la web (avisar de un error y proponer un hecho) y su función de Vercel
    for ruta_f, plantilla_f, titulo_f, desc_f in (
            ("avisar", avisos.PAGINA, "Avisar de un error",
             "Si crees que una afirmación está mal verificada, mándanos el enlace a una web que muestre el dato correcto."),
            ("proponer", avisos.PROPONER, "Proponer un hecho para verificar",
             "Cuéntanos algo que se dijo en una entrevista y no hemos comprobado, con un enlace para contrastarlo.")):
        (SALIDA / ruta_f).mkdir(exist_ok=True)
        (SALIDA / ruta_f / "index.html").write_text(rellenar(
            plantilla_f, ESTILO_FORM=avisos.ESTILO, CABECERA=cabecera(f"/{ruta_f}", f"{titulo_f} · Verificación The Wild Project", desc_f),
            MENU=menu(entrevistas), CSS_MENU=CSS_MENU, OPCIONES=opciones), encoding="utf-8")
    (SALIDA / "participa").mkdir(exist_ok=True)
    (SALIDA / "participa" / "index.html").write_text(rellenar(
        avisos.PARTICIPA, ESTILO_FORM=avisos.ESTILO, CABECERA=cabecera(
            "/participa", "Participa · Verificación The Wild Project",
            "Avísanos de un error en una verificación o propón algo que se dijo en una entrevista y falta por comprobar. "
            "Solo hace falta un enlace a una fuente."),
        MENU=menu(entrevistas, "participa"), CSS_MENU=CSS_MENU, REPO=REPO), encoding="utf-8")
    (SALIDA / "api").mkdir(exist_ok=True)  # web/api/ solo tiene funciones; los datos estáticos están en web/datos/
    shutil.copy(RAIZ / "web-src" / "avisar.js", SALIDA / "api" / "avisar.js")
    pagina_metodologia(entrevistas)
    DATOS.mkdir(exist_ok=True)
    (DATOS / "index.html").write_text(rellenar(
        PAGINA_API, CABECERA=cabecera(
            "/api", "Verifícalo tú · API abierta · Verificación The Wild Project",
            "Cómo comprobar por tu cuenta cada veredicto, con la API abierta en JSON y CSV (sin clave), un encargo para que "
            "cualquier IA audite la verificación y un prompt listo para agentes de IA."), PROMPT=e(prompt_agente(hechas)), MENU=menu(entrevistas), MINI=mini_resumen(hechas), CSS_MENU=CSS_MENU, BASE=BASE, REPO=REPO,
        SCALAR=SCALAR, SCALAR_SRI=SCALAR_SRI), encoding="utf-8")
    # La referencia vivió unas horas en /api/referencia: se redirige (aquí y en vercel.json).
    (DATOS / "referencia").mkdir(exist_ok=True)
    (DATOS / "referencia" / "index.html").write_text(rellenar(REDIRIGE_API, CABECERA=cabecera(
        "/api", "API abierta · Verificación The Wild Project", "La referencia de la API está en /api.")), encoding="utf-8")


ANALITICA_QUIEN = (
    'No hay publicidad.</p>\n<p>Las visitas se cuentan con <a href="https://umami.is/docs" target="_blank" rel="noopener noreferrer">Umami</a>, un servicio de estadísticas que no usa cookies y que, según su documentación, no recoge datos personales. También cuenta qué enlaces se pulsan (vídeos, fuentes y descargas), sin saber quién los pulsa. Esas cifras solo las ve Pablo.</p>')
SIN_ANALITICA_QUIEN = "No hay publicidad ni seguimiento de visitas.</p>"


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

# Leyenda en una línea de texto para la portada: el color, el nombre y qué significa, sin botón flotante.
LEYENDA_LINEA = ('<ul class="ley-linea" aria-label="Qué significa cada color">'
    '<li class="tono-falso"><i aria-hidden="true"></i><span><b>Falso:</b> los datos lo contradicen</span></li>'
    '<li class="tono-enganoso"><i aria-hidden="true"></i><span><b>Engañoso:</b> parte de un dato real, pero confunde</span></li>'
    '<li class="tono-mayormente_verdadero"><i aria-hidden="true"></i><span><b>Casi cierto:</b> con una imprecisión menor</span></li>'
    '<li class="tono-verdadero"><i aria-hidden="true"></i><span><b>Verdadero:</b> los datos lo confirman</span></li>'
    '<li class="tono-no_verificable"><i aria-hidden="true"></i><span><b>No verificable:</b> sin prueba pública suficiente</span></li>'
    '<li class="mas"><a href="/metodologia#que-significa-cada-veredicto">Criterios de cada veredicto</a></li></ul>')

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
/* Un solo contenedor para todas las páginas: el menú, los títulos y el contenido arrancan en el mismo borde */
.ancho { max-width:1360px; margin:0 auto; padding-left:clamp(16px,4vw,48px); padding-right:clamp(16px,4vw,48px); }
.menu { position:sticky; top:0; z-index:10; background:var(--fondo); border-bottom:2px solid var(--tinta); }
.menu .ancho { padding-top:9px; padding-bottom:9px; position:relative; }
.m1 { display:flex; flex-wrap:wrap; align-items:center; gap:4px 24px; font-size:14.5px; line-height:22px; }   /* alto de línea entero: así la fila mide píxeles enteros y el botón de modo queda centrado sin medio píxel */
.m1 a, .desp summary { color:var(--tinta); text-decoration:none; font-weight:600; padding:3px 0; border-bottom:2px solid transparent; }
/* Subrayado del menú: se dibuja de izquierda a derecha al pasar el ratón y se recoge hacia la derecha al salir */
.m1 > a:not(.sello), .desp summary { position:relative; border-bottom-color:transparent !important; }
.m1 > a:not(.sello)::after, .desp summary::after { content:""; position:absolute; left:0; right:0; bottom:-1px; height:2px; background:var(--tinta);
  transform:scaleX(0); transform-origin:right center; transition:transform .28s cubic-bezier(.4,0,.2,1); }
.m1 > a:not(.sello):hover::after, .m1 > a:not(.sello):focus-visible::after, .desp summary:hover::after, .desp summary:focus-visible::after,
.desp.actual summary::after, .desp[open] summary::after { transform:scaleX(1); transform-origin:left center; }
.m1 .sello { font:700 17px/22px "Iowan Old Style","Palatino Linotype",Palatino,Georgia,serif; }   /* alto entero: la fila del menú mide píxeles enteros y lo centrado cae en píxel exacto */
.m1 .off { color:var(--gris-claro); } .m1 .dcha { margin-left:auto; }
.modo { flex:none; display:inline-grid; place-items:center; width:26px; height:26px; padding:0; margin:0 0 0 -8px; cursor:pointer;
  color:var(--tinta); background:var(--fondo); border:1.5px solid var(--tinta); border-radius:50%; }
.modo:hover { background:var(--tinta); color:var(--fondo); }
.modo { line-height:0; font-size:0; }
.modo svg { display:block; width:16px; height:16px; fill:none; stroke:currentColor; stroke-width:2; stroke-linecap:round; stroke-linejoin:round; }
.modo .luna { display:var(--luna); } .modo .sol { display:var(--sol); }
.rot { font-size:10.5px; font-weight:700; text-transform:uppercase; letter-spacing:.09em; color:var(--gris); flex:none; }
.desp { position:relative; margin:0; padding:0; border:0; font-size:inherit; }
.desp summary { list-style:none; cursor:pointer; user-select:none; }
.desp summary::-webkit-details-marker { display:none; }

.desp .lista { position:absolute; top:calc(100% + 12px); left:-14px; z-index:20; background:var(--fondo); border:2px solid var(--tinta); box-shadow:var(--flota);
  width:max-content; min-width:260px; max-width:min(92vw,470px); max-height:74vh; overflow-y:auto; padding:6px 0; }
/* Desplegable de cada candidato: cabecera con su foto, dos accesos grandes y la lista de temas numerada como en la línea temporal */
.desp .lista a { border:0; padding:0; }
.lista-cab { display:flex; align-items:center; gap:12px; padding:6px 6px 12px; }
.lista-cab .retrato { width:46px; height:46px; } .lista-cab .retrato .insignia { display:none; }
.lista-cab p { margin:0; } .lista-cab .nombre { font:700 18px/1.2 "Iowan Old Style","Palatino Linotype",Palatino,Georgia,serif; }
.lista-cab .cuanto { font-size:12.5px; color:var(--gris); margin-top:2px; } .lista-cab .cuanto b { color:var(--v-falso); }
.lista-acc { display:grid; grid-template-columns:1fr 1fr; gap:8px; padding:0 0 12px; margin:0 0 4px; border-bottom:1px solid var(--claro); }
.desp .lista-acc a { display:flex; align-items:center; gap:9px; min-height:44px; padding:0 12px; border:1.5px solid var(--tinta); border-radius:var(--r-boton);
  font-size:14px; font-weight:700; color:var(--tinta); background:var(--fondo); transition:background-color .15s ease-out, color .15s ease-out; }
.desp .lista-acc a.principal { background:var(--tinta); color:var(--fondo); }
.desp .lista-acc a:hover, .desp .lista-acc a:focus-visible { background:var(--tinta); color:var(--fondo); }
.desp .lista-acc a.principal:hover, .desp .lista-acc a.principal:focus-visible { background:var(--fondo); color:var(--tinta); }
.desp .lista-acc a[aria-current] { box-shadow:inset 0 0 0 1.5px var(--fondo), 0 0 0 1.5px var(--tinta); }
.lista-acc svg { display:block; flex:none; width:17px; height:17px; fill:none; stroke:currentColor; stroke-width:2; stroke-linecap:round; stroke-linejoin:round; }
.lista-acc svg .lleno { fill:currentColor; stroke:none; }
.desp .lista .rot { margin:0; padding:10px 6px 6px; border:0; }
.desp .lista .rot span { text-transform:none; letter-spacing:0; font-weight:500; }
.lista-temas { list-style:none; margin:0; padding:0; }
.desp .lista-temas a { display:grid; grid-template-columns:24px minmax(0,1fr) auto; align-items:center; gap:10px; padding:7px 6px; border-radius:var(--r-boton);
  font-size:14.5px; font-weight:500; line-height:1.3; color:var(--tinta); transition:background-color .12s ease-out; }
.lista-temas i { width:24px; height:24px; border-radius:50%; border:1.5px solid var(--tinta); display:grid; place-items:center; line-height:0;
  font:700 11.5px/1 -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif; font-style:normal; font-variant-numeric:tabular-nums; transition:background-color .12s, color .12s; }
.lista-temas b { min-width:24px; height:22px; padding:0 7px; border-radius:999px; display:grid; place-items:center; line-height:0;
  background:var(--v-falso); color:var(--sobre-tono); font-size:12px; font-weight:700; font-variant-numeric:tabular-nums; }
.lista-temas b .sr { position:absolute; }
.desp .lista-temas a:hover, .desp .lista-temas a:focus-visible { background:var(--resalte); outline-offset:-2px; }
.desp .lista-temas a:hover i, .desp .lista-temas a:focus-visible i { background:var(--tinta); color:var(--fondo); }
.desp .lista-temas a.off { opacity:.4; }
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
.pie-solo { border-top:1px solid var(--tinta); padding:18px 0 44px; }
.pie-quien { margin:0; font-size:13.5px; color:var(--suave); max-width:none; }
footer .pie-quien { margin-top:18px; }
.pie-quien a { color:var(--suave); text-underline-offset:3px; }
.m1 > a, .desp summary, .fila button { white-space:nowrap; }
@media (max-width:1000px) { .m1 .largo { display:none; } }
.m1 .buscar { display:inline-flex; align-items:center; gap:6px; }
.m1 .buscar svg { display:block; flex:none; width:16px; height:16px; fill:none; stroke:currentColor; stroke-width:2.2; stroke-linecap:round; stroke-linejoin:round; }
.m1 > a[aria-current]::after { transform:scaleX(1); transform-origin:left center; }
@media (min-width:761px) and (max-width:1200px) { .m1 .buscar span { position:absolute; width:1px; height:1px; overflow:hidden; clip:rect(0 0 0 0); white-space:nowrap; } .m1 .buscar { gap:0; } }   /* con poco ancho, solo la lupa: así el menú no baja de línea */
/* Entre 761 y 1200 px el menú tiene que caber en una línea: menos hueco y letra un punto menor, y por debajo de 900 px
   sale «GitHub ↗», que sigue en el pie de cada página */
@media (min-width:761px) and (max-width:1200px) { .m1 { column-gap:14px; font-size:14px; } }
@media (min-width:761px) and (max-width:900px) { .m1 > a.gh { display:none; } }
@media (min-width:1001px) and (max-width:1060px) { .m1 { column-gap:12px; } }   /* ahí vuelven los nombres largos */
@media (max-width:760px) { .m1 .sello { order:-2; } .m1 .buscar { order:-1; } }   /* en móvil el menú se desliza: Buscar va junto al título para que se vea */
/* En móvil el menú y los filtros ocupan una sola fila que se desliza en horizontal; el botón de modo se queda fijo a la derecha */
@media (max-width:760px) {
  .menu .ancho, .filtros .ancho { padding-left:0; padding-right:0; }
  .filtros .ancho { position:relative; }
  .filtros .ancho::after { content:""; position:absolute; top:0; bottom:0; right:0; width:28px; pointer-events:none;
    background:linear-gradient(to right, transparent, var(--fondo) 85%); }
  .m1, .fila { flex-wrap:nowrap; overflow-x:auto; scrollbar-width:none; overscroll-behavior-x:contain; padding-left:16px; padding-right:16px; }
  .fila { padding-right:28px; }
  .m1::-webkit-scrollbar, .fila::-webkit-scrollbar { display:none; }
  .m1 { gap:0 18px; font-size:14px; } .m1 .dcha { margin-left:0; }
  .m1 > a, .desp summary { display:inline-flex; align-items:center; min-height:36px; }
  .m1 > a:not(.sello)::after, .desp summary::after { bottom:5px; }
  .m1 { padding-right:72px; }
  .modo { position:absolute; right:12px; top:calc(50% - 16px); margin:0; width:32px; height:32px; }
  .modo svg { width:18px; height:18px; }
  .menu .ancho::after { content:""; position:absolute; top:0; bottom:0; right:52px; width:28px; pointer-events:none;
    background:linear-gradient(to right, transparent, var(--fondo)); }
  .menu .ancho::before { content:""; position:absolute; top:0; bottom:0; right:0; width:52px; background:var(--fondo); pointer-events:none; z-index:1; }
  .menu .ancho::after { z-index:1; } .modo { z-index:2; }
  .menu .ancho { padding-top:4px; padding-bottom:4px; }
  .desp { position:static; } .desp .lista { left:12px; right:12px; top:calc(100% + 6px); width:auto; max-width:none; max-height:calc(100dvh - var(--menu, 48px) - 24px); }
  .filtros { padding:7px 0; }
  .fila .rot { display:none; } .fila button { flex:none; font-size:13px; padding:0 12px; min-height:34px; } .fila button[data-solo] { margin-left:0; } }
/* En móvil cada fila de tabla se apila (primero qué es, debajo su dirección o sus datos) en vez de obligar a deslizar en horizontal */
@media (max-width:640px) {
  .tabla table, .tabla-api table { min-width:0; } .tabla thead, .tabla-api thead { display:none; }
  .tabla table, .tabla tbody, .tabla tr, .tabla td, .tabla-api table, .tabla-api tbody, .tabla-api tr, .tabla-api td { display:block; width:100%; }
  .tabla tr, .tabla-api tr { padding:10px 0; border-bottom:1px solid var(--tinta); }
  .tabla tr:first-child, .tabla-api tr:first-child { border-top:2px solid var(--tinta); }
  .tabla td, .tabla-api td { border:0 !important; padding:2px 0 !important; } .tabla td:first-child, .tabla-api td:first-child { font-weight:600; }
  .tabla-api td[data-l]::before { content:attr(data-l) ": "; font-weight:500; color:var(--gris); } }
"""
CSS_MENU += """
/* ── Interacción: estados hover, foco, pulsación y avisos, iguales en todas las páginas */
html { -webkit-tap-highlight-color:transparent; }
:focus-visible { outline:3px solid var(--tinta); outline-offset:2px; }
/* Los campos de texto no llevan anillo de foco: el cursor ya dice dónde se escribe */
:is(input, textarea):focus, :is(input, textarea):focus-visible { outline:none; box-shadow:none; }
a { text-underline-offset:3px; text-decoration-thickness:1px; transition:text-decoration-thickness .15s ease-out, color .15s ease-out, background-color .15s ease-out; }
a:hover { text-decoration-thickness:2px; }
button, summary, select, .chip, .repo, .botones a, .minuto, .modo { transition:background-color .15s ease-out, color .15s ease-out, border-color .15s ease-out, box-shadow .18s ease-out, transform .12s ease-out; }
button:active, .repo:active, .botones a:active, .chip:active, .fila button:active { transform:translateY(1px) scale(.98); }
select { cursor:pointer; } select:hover { box-shadow:inset 0 0 0 1px var(--tinta); }
.m1 > a, .desp summary { transition:border-color .15s ease-out; }
.desp[open] .lista { animation:caer .2s cubic-bezier(.2,.7,.2,1); }
@keyframes caer { from { clip-path:inset(0 0 100% 0); } to { clip-path:inset(0 0 0 0); } }
.fila button:not([aria-pressed=true]):hover { background:color-mix(in srgb, var(--tono, var(--tinta)) 13%, var(--fondo)); }
.fila button[aria-pressed=true]:hover { box-shadow:0 0 0 2px var(--fondo), 0 0 0 3.5px var(--tono, var(--tinta)); }
.fila .cuenta { margin-left:auto; font-size:12.5px; color:var(--gris); font-variant-numeric:tabular-nums; white-space:nowrap; }
.fila button[data-solo] + .cuenta { margin-left:12px; }
.botones button:hover, #api-ir:hover { background:var(--fondo); color:var(--tinta); }
.botones button:disabled, #api-ir:disabled { opacity:.55; cursor:progress; }
.repo:hover { background:var(--fondo); color:var(--tinta); box-shadow:inset 0 0 0 2px var(--tinta); }
.repo.claro:hover { background:var(--tinta); color:var(--fondo); }
/* Aviso flotante: confirma una acción (copiar, descargar) y se va solo; lo leen también los lectores de pantalla */
.aviso { position:fixed; left:50%; bottom:calc(20px + env(safe-area-inset-bottom)); z-index:50; max-width:calc(100vw - 32px);
  transform:translate(-50%, 16px); opacity:0; pointer-events:none; background:var(--tinta); color:var(--fondo);
  border:2px solid var(--tinta); border-radius:var(--r-caja); box-shadow:var(--flota); padding:10px 16px; font-size:14.5px; font-weight:600;
  transition:opacity .2s ease-out, transform .2s ease-out; }
.aviso.ver { opacity:1; transform:translate(-50%, 0); }
.aviso.mal { background:var(--fondo); color:var(--tinta); }
/* Botón para volver arriba en las páginas largas */
.arriba { position:fixed; right:calc(16px + env(safe-area-inset-right)); bottom:calc(16px + env(safe-area-inset-bottom)); z-index:40;
  width:44px; height:44px; display:grid; place-items:center; padding:0; cursor:pointer; line-height:0; font-size:0;
  color:var(--tinta); background:var(--fondo); border:2px solid var(--tinta); border-radius:50%; box-shadow:var(--flota);
  opacity:0; transform:translateY(10px); pointer-events:none; transition:opacity .2s ease-out, transform .2s ease-out, background-color .15s, color .15s; }
.arriba svg { display:block; width:20px; height:20px; fill:none; stroke:currentColor; stroke-width:2.5; stroke-linecap:square; }
.arriba.ver { opacity:1; transform:none; pointer-events:auto; }
.arriba:hover { background:var(--tinta); color:var(--fondo); }
.sr { position:absolute; width:1px; height:1px; overflow:hidden; clip:rect(0 0 0 0); white-space:nowrap; }
@media (max-width:760px) { .fila .cuenta { position:absolute; width:1px; height:1px; overflow:hidden; clip:rect(0 0 0 0); } }
@media (prefers-reduced-motion:reduce) { *, ::before, ::after { transition-duration:0s !important; animation-duration:0s !important; } html { scroll-behavior:auto; } }
"""
CSS_MENU += """
/* ── Esquinas suaves y contenidas, para que sigan leyéndose como recuadros de periódico: 14 px en contenedores, 9 px en botones y cajas, 5 px en etiquetas */
:root { --r-caja:14px; --r-boton:9px; --r-mini:5px; --flota:0 10px 28px -8px rgba(0,0,0,.28); }
.panel, .entrevista, .explorador, .vias li, .desp .lista, .agentes { border-radius:var(--r-caja); }
.desp .lista { border-top:0 !important; border-radius:0 0 var(--r-caja) var(--r-caja) !important; overflow-x:hidden; overflow-y:auto; overscroll-behavior:contain; width:min(440px, calc(100vw - 24px)); min-width:0; max-width:none; max-height:min(78vh, 680px); padding:10px; }
.tu, .abrir, pre, .btn, .repo, .botones button, .botones a, #api-ir, .copiar, select, .opciones select, .logo.sin, #api-res .vacio { border-radius:var(--r-boton); }
.ficha, .leyenda-f dt, code, .chip-mini, .par:target, .indice a { border-radius:var(--r-mini); }
.hito:target .panel { outline-offset:4px; }
"""
CSS_MENU += """
/* Retrato: foto redonda con borde de tinta y el logotipo del partido en una insignia blanca abajo a la derecha */
.retrato { position:relative; display:block; flex:none; border-radius:50%; align-self:start; justify-self:start; }
.retrato > img { display:block; width:100%; height:100%; object-fit:cover; border-radius:50%; border:2px solid var(--tinta); background:var(--claro); }
.retrato .insignia { position:absolute; right:-4%; bottom:-4%; width:42%; aspect-ratio:1; border-radius:50%; overflow:hidden;
  display:grid; place-items:center; background:#fff; border:2px solid var(--tinta); line-height:0; font-size:0; }
.retrato .insignia img { display:block; width:72%; height:72%; object-fit:contain; }
.retrato .insignia b { font:700 11px/1 -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif; color:#000; }
.titular { display:flex; align-items:flex-start; gap:clamp(14px,2vw,24px); margin:0 0 18px; }
.titular .retrato { margin-top:.2em; }
.titular h1 { margin:0 !important; }
.titular .retrato { width:clamp(64px,8vw,104px); height:clamp(64px,8vw,104px); }
.titular .retrato.peque { width:clamp(52px,6vw,76px); height:clamp(52px,6vw,76px); }
/* Buscador: foto de cada resultado (con insignia) y foto pequeña, sin ella, en los botones de candidato */
.retrato.res-foto { width:clamp(44px,5.5vw,54px); height:clamp(44px,5.5vw,54px); align-self:center; }
.retrato.res-foto .insignia { animation:none; }
.retrato.chica { width:24px; height:24px; align-self:center; }
.retrato.chica > img { border-width:1.5px; }
.fila button[aria-pressed=true] .retrato > img { border-color:var(--fondo); }
.creditos { font-size:12.5px; color:var(--gris); }
.creditos a { color:inherit; }
"""
CSS_MENU += """
/* Botón flotante de la leyenda: círculo abajo a la izquierda que se ensancha al pasar el ratón y abre un panel con un revelado circular */
.fab { position:fixed; left:calc(16px + env(safe-area-inset-left)); bottom:calc(16px + env(safe-area-inset-bottom)); z-index:45; }
.fab-boton { position:relative; display:flex; align-items:center; gap:0; height:52px; min-width:52px; padding:0 14px; cursor:pointer;
  border-radius:999px; border:2px solid var(--tinta); background:var(--fondo); color:var(--tinta); box-shadow:var(--flota);
  font:700 14.5px/1 -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif; transition:background-color .15s ease-out, color .15s ease-out, gap .2s ease-out; }
.fab-ico { display:grid; grid-template-columns:repeat(2,8px); gap:4px; flex:none; width:20px; place-content:center; }
.fab-ico i { display:block; width:8px; height:8px; border-radius:50%; background:var(--tono); }
.fab-x { display:none; flex:none; width:20px; height:20px; fill:none; stroke:currentColor; stroke-width:2.4; stroke-linecap:round; }
.fab-txt { max-width:0; overflow:hidden; white-space:nowrap; opacity:0; transition:max-width .22s ease-out, opacity .15s ease-out; }
.fab-boton:hover, .fab-boton:focus-visible { gap:10px; }
.fab-boton:hover .fab-txt, .fab-boton:focus-visible .fab-txt { max-width:90px; opacity:1; }
.fab.abierto .fab-boton { background:var(--tinta); color:var(--fondo); gap:0; }
.fab.abierto .fab-ico { display:none; } .fab.abierto .fab-x { display:block; }
.fab.abierto .fab-txt { max-width:0; opacity:0; }
.fab-panel { position:absolute; left:0; bottom:64px; width:min(420px, calc(100vw - 32px)); max-height:calc(100dvh - var(--menu, 48px) - 100px); overflow-y:auto;
  overscroll-behavior:contain; padding:16px 16px 14px; background:var(--fondo); color:var(--tinta); border:2px solid var(--tinta); border-radius:var(--r-caja);
  box-shadow:var(--flota); clip-path:circle(0 at 26px calc(100% + 38px)); opacity:.4;
  transition:clip-path .32s cubic-bezier(.4,0,.2,1), opacity .2s ease-out; }
.fab.abierto .fab-panel { clip-path:circle(150% at 26px calc(100% + 38px)); opacity:1; }
.fab-titulo { margin:0 0 10px; font:700 19px/1.2 "Iowan Old Style","Palatino Linotype",Palatino,Georgia,serif; outline:none; }
.fab-panel .leyenda-f h2, .fab-panel .ley-intro { display:none; }
.fab-panel .leyenda-f dl { margin:0 0 12px; }
.fab-panel .leyenda-f dl div { grid-template-columns:104px minmax(0,1fr); gap:0 12px; padding:8px 0; }
.fab-panel .leyenda-f dt { justify-self:stretch; font-size:11px; padding:5px 6px; }
.fab-panel .leyenda-f dd { font-size:13.5px; line-height:1.38; }
.fab-panel .ley-notas { font-size:13px; gap:5px; }
@media (prefers-reduced-motion:reduce) { .fab-panel { clip-path:none !important; } }
"""
FAB_LEYENDA = FAB_LEYENDA.replace("@@LEYENDA_FAB@@", LEYENDA)
CSS_MENU += """
/* Barra de reparto: el 100 % de las afirmaciones, un tramo por veredicto con su color */
.barra-reparto { display:flex; gap:2px; height:10px; margin:8px 0 2px; border-radius:999px; overflow:hidden; background:var(--claro); }
.barra-reparto i { display:block; min-width:4px; background:var(--tono); transition:filter .15s ease-out; }
.barra-reparto i:hover { filter:brightness(1.15) saturate(1.1); }
.barra-reparto.grande { height:14px; margin:12px 0 0; }
"""
CSS_MENU += """
/* Entrada del hero: aparece por capas (título, texto, cifras, tarjetas), la barra de reparto se rellena y los números cuentan hacia arriba.
   «backwards» solo aplica el estado inicial durante la espera, así no pisa los hovers cuando termina. */
@keyframes subir { from { opacity:0; transform:translateY(16px); } }
@keyframes asomar { from { opacity:0; transform:scale(.82); } }
@keyframes rellenar { from { clip-path:inset(0 100% 0 0 round 999px); } to { clip-path:inset(0 0 0 0 round 999px); } }
.cabeza h1, .titular h1 { animation:subir .7s cubic-bezier(.2,.7,.2,1) backwards; }
.cabeza .entrada, .portada .intro { animation:subir .7s .1s cubic-bezier(.2,.7,.2,1) backwards; }
.cabeza .tu { animation:subir .7s .18s cubic-bezier(.2,.7,.2,1) backwards; }
.portada .cifras { animation:subir .7s .16s cubic-bezier(.2,.7,.2,1) backwards; }
.tarjetas .entrevista { animation:subir .7s cubic-bezier(.2,.7,.2,1) backwards; }
.tarjetas .entrevista:nth-child(1) { animation-delay:.22s; } .tarjetas .entrevista:nth-child(2) { animation-delay:.32s; } .tarjetas .entrevista:nth-child(3) { animation-delay:.42s; }
.titular .retrato, .tarjetas .retrato { animation:asomar .55s .05s cubic-bezier(.3,1.4,.5,1) backwards; }
.tarjetas .entrevista:nth-child(2) .retrato { animation-delay:.36s; } .tarjetas .entrevista:nth-child(3) .retrato { animation-delay:.46s; }
.tarjetas .entrevista:nth-child(1) .retrato { animation-delay:.26s; }
.retrato .insignia { animation:asomar .4s .5s cubic-bezier(.3,1.5,.5,1) backwards; }
.barra-reparto { animation:rellenar .9s .55s cubic-bezier(.4,0,.2,1) backwards; }
.tarjetas .entrevista:nth-child(2) .barra-reparto { animation-delay:.65s; } .tarjetas .entrevista:nth-child(3) .barra-reparto { animation-delay:.75s; }
.barra-reparto.grande { animation-delay:.4s; }
@media (prefers-reduced-motion:reduce) {
  .cabeza h1, .titular h1, .cabeza .entrada, .portada .intro, .cabeza .tu, .portada .cifras, .tarjetas .entrevista, .retrato, .retrato .insignia, .barra-reparto { animation:none !important; } }
"""
CSS_MENU += """
/* ── Reproductor de vídeo: panel fijo abajo a la derecha (400 px, 16:9) en escritorio y a todo el ancho abajo en móvil.
   El panel y su iframe solo existen tras pulsar un minuto. --repro-h (su alto) lo pone el script y aparta los botones flotantes. */
.repro { position:fixed; right:calc(16px + env(safe-area-inset-right)); bottom:calc(16px + env(safe-area-inset-bottom)); z-index:46;
  width:min(400px, calc(100vw - 32px)); background:var(--fondo); color:var(--tinta); border:2px solid var(--tinta);
  border-radius:var(--r-caja); box-shadow:var(--flota); overflow:hidden; animation:repro-sube .22s ease-out; }
@keyframes repro-sube { from { opacity:0; transform:translateY(14px); } }
.repro:focus-visible { outline:3px solid var(--tinta); outline-offset:3px; }
.repro-barra { display:flex; align-items:center; gap:2px; min-height:46px; padding:4px 5px 4px 13px; border-bottom:2px solid var(--tinta); }
.repro.min .repro-barra { border-bottom:0; }
.repro-t { flex:1; min-width:0; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; font-size:13px; font-weight:700; font-variant-numeric:tabular-nums; }
.repro-yt { flex:none; display:inline-flex; align-items:center; gap:5px; min-height:38px; padding:0 8px; font-size:13px; font-weight:600; white-space:nowrap; color:var(--tinta); }
.repro-yt svg, .repro button svg { display:block; fill:none; stroke:currentColor; stroke-width:2; stroke-linecap:round; stroke-linejoin:round; }
.repro-yt svg { width:14px; height:14px; }
.repro button { flex:none; display:grid; place-items:center; width:38px; height:38px; padding:0; cursor:pointer; line-height:0; font-size:0;
  color:var(--tinta); background:var(--fondo); border:0; border-radius:50%; }
.repro button svg { width:19px; height:19px; stroke-width:2.2; }
.repro button:hover, .repro button:focus-visible { background:var(--tinta); color:var(--fondo); }
.repro-yt:hover { background:var(--tinta); color:var(--fondo); text-decoration:none; border-radius:var(--r-boton); }
.repro-video { display:flex; justify-content:center; background:#000; }
.repro-video iframe { display:block; border:0; width:min(100%, calc(45vh * 16 / 9)); width:min(100%, calc(45dvh * 16 / 9)); height:auto; aspect-ratio:16 / 9; }
.repro.min .repro-video { display:none; }
html.con-repro .arriba { bottom:calc(var(--repro-h, 0px) + 28px + env(safe-area-inset-bottom)); }
@media (max-width:760px) {
  .repro { left:0; right:0; bottom:0; width:auto; padding-bottom:env(safe-area-inset-bottom); border-width:2px 0 0; border-radius:var(--r-caja) var(--r-caja) 0 0; }
  html.con-repro body { padding-bottom:var(--repro-h, 0px); }
  html.con-repro .fab, html.con-repro .arriba { bottom:calc(var(--repro-h, 0px) + 12px); }
  html.con-repro .aviso { bottom:calc(var(--repro-h, 0px) + 16px); }
  html.con-repro .fab-panel { max-height:calc(100dvh - var(--menu, 48px) - 100px - var(--repro-h, 0px)); } }
/* Menú «Más»: en pantallas anchas no existe (los enlaces van sueltos); en móvil recoge los enlaces secundarios y el cambio de modo */
.desp > summary { font-size:inherit; }
.mas { display:none; }
.mas-lista { list-style:none; margin:0; padding:0; }
.desp.mas .mas-lista a { display:flex; align-items:center; min-height:48px; padding:0 10px; font-size:16px; font-weight:600; color:var(--tinta);
  border-bottom:1px solid var(--claro); border-radius:0; text-decoration:none; }
.desp.mas .mas-lista a:hover, .desp.mas .mas-lista a:focus-visible { background:var(--resalte); }
.modo-txt { display:flex; align-items:center; gap:10px; width:100%; min-height:48px; padding:0 10px; margin:0; font:inherit; font-size:16px; font-weight:600;
  color:var(--tinta); background:none; border:0; cursor:pointer; text-align:left; border-radius:var(--r-boton); }
.modo-txt:hover { background:var(--resalte); }
.modo-txt svg { display:block; flex:none; width:18px; height:18px; fill:none; stroke:currentColor; stroke-width:2; stroke-linecap:round; stroke-linejoin:round; }
.modo-txt .luna { display:var(--luna); } .modo-txt .sol { display:var(--sol); }
@media (max-width:760px) {
  .m1 > .sec, .m1 > .modo { display:none; }
  .mas { display:block; }
  .desp.mas > summary { position:absolute; right:12px; top:calc(50% - 18px); z-index:2; display:grid; place-items:center; width:36px; height:36px;
    min-height:0; padding:0; border:1.5px solid var(--tinta) !important; border-radius:50%; background:var(--fondo); color:var(--tinta); }
  .desp.mas > summary::after { display:none; }
  .desp.mas[open] > summary { background:var(--tinta); color:var(--fondo); }
  .desp.mas > summary svg { display:block; width:18px; height:18px; fill:none; stroke:currentColor; stroke-width:2; stroke-linecap:round; }
  .m1 .buscar span { position:absolute; width:1px; height:1px; overflow:hidden; clip:rect(0 0 0 0); white-space:nowrap; } .m1 .buscar { gap:0; }   /* solo la lupa */
  .m1 { gap:0 14px; } }
"""
CSS_MENU += """
/* Resumen al pie de cada página: la entrevista de la página o, en las generales, una tarjeta por candidato */
.resumenes { border-top:3px solid var(--tinta); padding:26px 0 34px; margin-top:24px; }
.resumenes .mini-t { font:700 22px/1.2 "Iowan Old Style","Palatino Linotype",Palatino,Georgia,serif; margin:0 0 16px; padding:0; border:0; letter-spacing:0; }
.mini-lista { display:grid; gap:12px; grid-template-columns:repeat(auto-fit, minmax(min(100%, 280px), 1fr)); }
.mini-e { display:flex; flex-direction:column; gap:9px; border:1.5px solid var(--tinta); border-radius:var(--r-caja); padding:14px 16px 12px; background:var(--fondo); }
.mini-cab { display:flex; align-items:center; gap:12px; }
.mini-cab .retrato { width:44px; height:44px; } .mini-cab .retrato .insignia { display:none; }
.mini-cab h3 { margin:0; font:700 18px/1.2 "Iowan Old Style","Palatino Linotype",Palatino,Georgia,serif; }
.mini-cab h3 a { color:var(--tinta); text-decoration:none; } .mini-cab h3 a:hover { text-decoration:underline; }
.mini-meta { margin:2px 0 0; font-size:12.5px; color:var(--gris); }
.mini-res { margin:0; font-size:14.5px; line-height:1.5; max-width:none; }
.mini-num { margin:0; font-size:13.5px; } .mini-num b { font:700 21px/1 "Iowan Old Style","Palatino Linotype",Palatino,Georgia,serif; margin-right:2px; }
.barra-reparto.mini-barra { margin:0; height:8px; animation:none; }
.mini-acc { margin:auto 0 0; display:flex; flex-wrap:wrap; gap:0 18px; font-size:13.5px; font-weight:600; }
.mini-acc a { display:inline-flex; align-items:center; gap:4px; min-height:36px; color:var(--tinta); }
/* Iconos de «↗» y «→» (ICONO_EXTERNO, ICONO_SIGUE): trazo que hereda el color, a la altura de la letra */
.ic { display:block; flex:none; width:14px; height:14px; fill:none; stroke:currentColor; stroke-width:2.2; stroke-linecap:round; stroke-linejoin:round; }
.m1 > a.gh { display:inline-flex; align-items:center; gap:3px; }
.desp.mas .mas-lista a .ic { margin-left:4px; }
/* En la cabecera de cada entrevista: debajo del texto y de las cifras, ocupando las dos columnas */
.resumenes.en-cabeza { grid-column:1 / -1; margin-top:28px; padding:18px 0 0; }
"""
CSS_MENU = (CSS_MENU.replace("@@CLARO@@", _CLARO).replace("@@OSCURO@@", _OSCURO)
            .replace("@@CLASES_TONO@@", "\n".join(f"[data-v={k}], .tono-{k} {{ --tono:var(--v-{k}); }}" for k in ORDEN)))


QUIEN = """<!doctype html>
<html lang="es">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
@@HEAD_MODO@@
@@CABECERA@@
<style>
:root { --serif:"Iowan Old Style","Palatino Linotype",Palatino,Georgia,serif; }
* { box-sizing:border-box; }
body { margin:0; background:var(--fondo); color:var(--tinta); font:16px/1.6 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif; }
a { color:var(--tinta); text-underline-offset:3px; }
main.ancho { padding-bottom:72px; }
p, li { max-width:68ch; }
/* Cabecera: título y entrada apilados en móvil; en escritorio, el título a la izquierda y la entrada a la derecha */
.cabeza { padding:clamp(28px,5vw,56px) 0 clamp(28px,4vw,48px); }
h1 { font:700 clamp(30px,5.2vw,58px)/1.05 var(--serif); letter-spacing:-0.02em; margin:0 0 14px; text-wrap:balance; }
.entrada { font-size:17px; max-width:62ch; margin:0; }
@media (min-width:1000px) { .cabeza { display:grid; grid-template-columns:minmax(0,1.2fr) minmax(0,1fr); gap:0 clamp(32px,5vw,80px); align-items:end; }
  .cabeza h1 { margin:0; } }
/* Personas: una ficha por persona, en columnas en cuanto caben dos de 380 px */
.seccion-t { font:700 clamp(24px,2.4vw,28px)/1.2 var(--serif); margin:0 0 16px; padding-top:12px; border-top:3px solid var(--tinta); }
.personas { display:grid; grid-template-columns:repeat(auto-fit,minmax(min(100%,380px),1fr)); gap:clamp(14px,2vw,24px); margin:0 0 14px; }
.persona { border:2px solid var(--tinta); border-radius:var(--r-caja); padding:clamp(18px,2.4vw,28px); display:grid; grid-template-columns:auto minmax(0,1fr); grid-template-rows:auto auto 1fr auto; gap:4px clamp(14px,2vw,22px); }
.inicial { grid-row:1 / span 2; width:clamp(52px,5vw,64px); aspect-ratio:1; border-radius:50%; border:2px solid var(--tinta); display:grid; place-items:center;
  font:700 clamp(18px,1.8vw,22px)/1 var(--serif); letter-spacing:.02em; }
.persona h3 { font:700 clamp(24px,2.2vw,30px)/1.1 var(--serif); margin:0; align-self:end; text-wrap:balance; }
.rol { margin:0; font-size:12px; font-weight:700; text-transform:uppercase; letter-spacing:.08em; color:var(--gris); align-self:start; }
.persona .bio { grid-column:1 / -1; margin:14px 0 0; }
.persona .bio p { margin:0 0 10px; }
.enlaces { grid-column:1 / -1; align-self:end; display:flex; flex-wrap:wrap; gap:8px; margin:6px 0 0; padding:0; list-style:none; }
.enlaces a { display:inline-flex; align-items:center; min-height:40px; padding:0 14px; border:1.5px solid var(--tinta); border-radius:var(--r-boton);
  font-size:14px; font-weight:700; text-decoration:none; transition:background-color .15s ease-out, color .15s ease-out; }
.enlaces a:hover, .enlaces a:focus-visible { background:var(--tinta); color:var(--fondo); }
.nota { color:var(--suave); font-size:15px; }
/* Resto de apartados: rejilla de bloques, una columna en móvil y dos en cuanto caben de 440 px */
.bloques { display:grid; grid-template-columns:repeat(auto-fit,minmax(min(100%,440px),1fr)); gap:0 clamp(32px,5vw,80px); margin-top:clamp(28px,4vw,48px); }
.bloques section { min-width:0; }
.bloques h2 { font:700 24px/1.2 var(--serif); margin:32px 0 10px; padding-top:12px; border-top:3px solid var(--tinta); scroll-margin-top:calc(var(--menu, 48px) + 16px); }
.bloques ul { padding-left:22px; } .bloques li { margin:4px 0; }
@media (max-width:560px) { .persona { grid-template-columns:1fr; grid-template-rows:none; } .inicial { grid-row:auto; } .enlaces a { flex:1 1 auto; justify-content:center; } }
@@CSS_MENU@@
</style>
</head>
<body>
@@MENU@@
<main class="ancho">
<div class="cabeza">
<h1>Quién hace esto</h1>
<p class="entrada">Quién está detrás de esta web, de quién es independiente, quién la paga y cómo se corrigen los errores.</p>
</div>

<section aria-labelledby="quien">
<h2 class="seccion-t" id="quien">Quién lo hace</h2>
<div class="personas">
<article class="persona">
<span class="inicial" aria-hidden="true">PP</span>
<h3>Pablo Pardo Cotos</h3>
<p class="rol">Autor y mantenedor</p>
<div class="bio">@@BIO_PABLO@@</div>
<ul class="enlaces">@@ENLACES_PABLO@@</ul>
</article>
<article class="persona">
<span class="inicial" aria-hidden="true">DC</span>
<h3>Diego Cristóbal Andaluz</h3>
<p class="rol">Diseño y desarrollo web</p>
<div class="bio">@@BIO_DIEGO@@</div>
<ul class="enlaces">@@ENLACES_DIEGO@@</ul>
</article>
</div>
<p class="nota">Es un proyecto independiente. Cualquiera puede proponer cambios en el <a href="@@REPO@@" target="_blank" rel="noopener noreferrer">repositorio</a>, y los que se aceptan quedan en su <a href="@@REPO@@/commits/main" target="_blank" rel="noopener noreferrer">historial público</a>.</p>
</section>

<div class="bloques">
<section>
<h2 id="independencia">Independencia</h2>
<p>Ni Pablo ni Diego militan ni han militado en ningún partido. No han trabajado ni colaborado con ningún partido, ni con Jordi Wild, ni con The Wild Project. Nadie les ha encargado este trabajo.</p>
<p>The Wild Project y Jordi Wild no participan en esta web ni la respaldan.</p>
</section>

<section>
<h2 id="financiacion">Financiación</h2>
<p>Esta web no tiene financiación ni apoyo de nadie. Los únicos costes son las suscripciones de IA, y Pablo y Diego pagan cada uno las suyas; la web está alojada en el plan gratuito de Vercel. @@ANALITICA@@
<p>Los vídeos de las entrevistas se reproducen con el reproductor de YouTube (youtube-nocookie.com), que solo se carga cuando pulsas un minuto y puede mostrar su propia publicidad. A partir de ahí se aplica la <a href="https://policies.google.com/privacy" target="_blank" rel="noopener noreferrer">política de privacidad de Google</a>.</p>
<p>Al abrir una fuente en el visor, tu navegador le pide su texto a <a href="https://jina.ai/reader" target="_blank" rel="noopener noreferrer">r.jina.ai</a>, un servicio de Jina AI, que ve tu dirección IP y qué fuente abres. Si prefieres evitarlo, ábrela con Cmd o Ctrl y clic: irá directamente a la web original. La animación de la portada y la referencia de la API cargan su código de jsDelivr, un servicio público de distribución de librerías, que también ve tu dirección IP.</p>
</section>

<section>
<h2 id="como">Cómo se hace</h2>
<ul>
<li>El audio de cada entrevista se transcribe con Whisper, un programa de transcripción automática.</li>
<li>Modelos de IA de Claude (Sonnet), con búsqueda web, contrastan cada afirmación con fuentes públicas y le ponen un veredicto.</li>
<li>Ninguna persona periodista ha revisado los veredictos.</li>
</ul>
<p>El procedimiento completo está en el <a href="/metodologia">método</a>. En <a href="/api#verificalo">Verifícalo tú</a> puedes comprobar cada veredicto por tu cuenta.</p>
</section>

<section>
<h2 id="errores">Errores y correcciones</h2>
<p>Si ves un error, abre la afirmación y pulsa «Avisar de un error», o <a href="/avisar">usa el formulario</a>. Solo te pediremos un enlace a una web que muestre el dato correcto. No hace falta cuenta.</p>
<p>Si echas en falta algo que se dijo en una entrevista, <a href="/proponer">propón un hecho para verificar</a>, también con un enlace para contrastarlo.</p>
<p>Una corrección se acepta por la fuente, no por el partido. Se aplica la misma vara de medir a todos.</p>
<p>Los cambios en los datos quedan registrados y se pueden consultar públicamente en el <a href="@@REPO@@/commits/main/entrevistas" target="_blank" rel="noopener noreferrer">historial de cambios</a>.</p>
<p>Para cualquier otra cosa, el contacto es por GitHub.</p>
</section>
</div>
</main>
@@MINI@@
<footer class="pie-solo"><div class="ancho">@@PIE@@</div></footer>
</body>
</html>
"""

METODOLOGIA = """<!doctype html>
<html lang="es">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
@@HEAD_MODO@@
@@CABECERA@@
<style>
:root { --serif:"Iowan Old Style","Palatino Linotype",Palatino,Georgia,serif; }
* { box-sizing:border-box; }
body { margin:0; background:var(--fondo); color:var(--tinta); font:16px/1.6 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif; }
a { color:var(--tinta); text-underline-offset:3px; }
main.ancho { padding-bottom:72px; }
.lectura { min-width:0; }
/* El índice: plegable arriba en móvil y tableta; columna fija a la izquierda en cuanto hay sitio */
.indice { margin:clamp(20px,4vw,32px) 0 0; border:2px solid var(--tinta); border-radius:var(--r-caja,14px); }
.indice summary { list-style:none; cursor:pointer; display:flex; justify-content:space-between; align-items:center; gap:12px;
  min-height:44px; padding:8px 14px; font-size:12px; font-weight:700; text-transform:uppercase; letter-spacing:.09em; }
.indice summary::-webkit-details-marker { display:none; }
.indice summary::after { content:""; width:8px; height:8px; border:solid var(--tinta); border-width:0 2px 2px 0; transform:translateY(-2px) rotate(45deg); transition:transform .18s ease-out; }
.indice[open] summary::after { transform:translateY(2px) rotate(-135deg); }
.indice summary:focus-visible { outline:2px solid var(--tinta); outline-offset:2px; }
.indice ol { list-style:none; margin:0; padding:0 14px 6px; border-top:1px solid var(--claro); }
.indice a { display:grid; grid-template-columns:3.6em minmax(0,1fr); align-items:baseline; padding:10px 0; border-bottom:1px solid var(--claro);
  font-size:15px; line-height:1.35; text-decoration:none; }
.indice .n { color:var(--gris); font-variant-numeric:tabular-nums; }
.indice li:last-child a { border-bottom:0; }
.indice a:hover .t { text-decoration:underline; }
.indice a.aqui, .indice a.aqui .n { font-weight:700; color:var(--tinta); }
@media (min-width:1024px) {
  main.ancho { display:grid; grid-template-columns:minmax(220px,264px) minmax(0,1fr); gap:0; }
  /* Una raya a toda altura separa el índice de la lectura */
  .lectura { border-left:1px solid var(--claro); padding-left:clamp(36px,4.5vw,72px); margin-left:clamp(28px,3vw,48px); }
  .indice { position:sticky; top:calc(var(--menu, 48px) + 32px); align-self:start; margin-top:clamp(28px,5vw,44px); border:0; border-radius:0;
    max-height:calc(100vh - var(--menu, 48px) - 64px); overflow-y:auto; scrollbar-width:thin; }
  .indice summary { pointer-events:none; min-height:0; padding:0 0 10px; font-size:11px; color:var(--gris); }
  .indice summary::after { display:none; }
  .indice ol { padding:0; border-top:2px solid var(--tinta); }
  .indice a { grid-template-columns:3.4em minmax(0,1fr); padding:11px 12px; margin:0 -12px; font-size:14px; }
  .indice li:last-child a { border-bottom:1px solid var(--claro); }
  .indice a:hover { background:var(--resalte); }
  .indice a:hover .t { text-decoration:none; }
  .indice a.aqui { background:var(--resalte); box-shadow:inset 3px 0 0 var(--tinta); } }
h1 { font:700 clamp(30px,5.2vw,52px)/1.05 var(--serif); letter-spacing:-0.02em; margin:clamp(28px,5vw,44px) 0 14px; text-wrap:balance; }
.entrada { font-size:15px; color:var(--suave); max-width:none; margin:0 0 22px; padding:10px 14px; border:2px solid var(--tinta); border-radius:var(--r-caja,14px); }
.entrada a { font-weight:600; }
.texto > p:first-child { font-size:17px; }
.texto h2 { font:700 23px/1.2 var(--serif); margin:44px 0 14px; padding-top:12px; border-top:3px solid var(--tinta); text-wrap:balance; }
.texto h3 { font:700 18px/1.3 var(--serif); margin:28px 0 8px; }
.texto p, .texto li { max-width:82ch; }
.texto ul, .texto ol { padding-left:24px; margin:12px 0; }
.texto li { margin:6px 0; }
.texto li > ul, .texto li > ol { margin:6px 0; }
.texto code { font:13.5px/1.5 ui-monospace,SFMono-Regular,Menlo,monospace; background:var(--codigo); padding:1px 5px; overflow-wrap:anywhere; }
.texto pre { background:var(--pre-fondo); color:var(--pre-tinta); outline:1px solid var(--pre-borde); outline-offset:-1px; padding:16px 18px; white-space:pre-wrap; overflow-wrap:anywhere; font:13px/1.6 ui-monospace,SFMono-Regular,Menlo,monospace; margin:14px 0 18px; }
.texto pre code { background:none; padding:0; font:inherit; overflow-wrap:anywhere; }
/* El encargo a los subagentes: una cita larga, con una barra a la izquierda */
.texto blockquote { margin:18px 0; padding:6px 18px; border-left:4px solid var(--tinta); background:var(--resalte); font-size:15px; }
.texto blockquote p { max-width:none; }
.texto blockquote code { background:var(--fondo); }
/* Las tablas se desplazan dentro de su caja: nunca ensanchan la página */
.tabla-md { max-width:100%; overflow-x:auto; margin:16px 0 22px; -webkit-overflow-scrolling:touch; }
.tabla-md table { border-collapse:collapse; width:100%; font-size:15px; }
.tabla-md th { text-align:left; font-size:12px; text-transform:uppercase; letter-spacing:.07em; color:var(--gris); border-bottom:2px solid var(--tinta); }
.tabla-md th, .tabla-md td { padding:9px 14px 9px 0; vertical-align:top; }
.tabla-md td { border-bottom:1px solid var(--claro); }
.tabla-md td:first-child { font-weight:700; min-width:8.5em; }
.tabla-md td code { font-size:12.5px; }
@@CSS_MENU@@
</style>
</head>
<body>
@@MENU@@
<main class="ancho">
<details class="indice" aria-label="Secciones del método"><summary>Secciones</summary><ol>@@INDICE@@</ol></details>
<div class="lectura">
<h1>@@TITULO@@</h1>
<p class="entrada">Esta página es el texto de <a href="@@REPO@@/blob/main/METODO.md" target="_blank" rel="noopener noreferrer"><code>METODO.md</code></a> del repositorio, tal cual está hoy. Cada cambio queda en su <a href="@@REPO@@/commits/main/METODO.md" target="_blank" rel="noopener noreferrer">historial de cambios</a>.</p>
<div class="texto">
@@CUERPO@@
</div>
</div>
</main>
<footer class="pie-solo"><div class="ancho">@@PIE@@</div></footer>
<script>
const indice = document.querySelector("details.indice");
const ancho = matchMedia("(min-width:1024px)");
const fijarIndice = () => { indice.open = ancho.matches; indice.querySelector("summary").tabIndex = ancho.matches ? -1 : 0; };
fijarIndice(); ancho.addEventListener("change", fijarIndice);
indice.addEventListener("toggle", () => { if (ancho.matches && !indice.open) indice.open = true; });
indice.addEventListener("click", ev => { if (ev.target.closest("a") && !ancho.matches) indice.open = false; });
const enIndice = new Map([...document.querySelectorAll(".indice a")].map(a => [a.hash.slice(1), a]));
if (enIndice.size && "IntersectionObserver" in window) {
  const obs = new IntersectionObserver(es => es.forEach(x => {
    if (!x.isIntersecting) return;
    enIndice.forEach(a => a.classList.remove("aqui"));
    enIndice.get(x.target.id)?.classList.add("aqui");
  }), { rootMargin: "0px 0px -70% 0px" });
  enIndice.forEach((a, id) => { const h = document.getElementById(id); if (h) obs.observe(h); });
}
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
@@CABECERA@@
<style>
:root { --serif:"Iowan Old Style","Palatino Linotype",Palatino,Georgia,serif; --scalar-custom-header-height:var(--menu, 48px); }
* { box-sizing:border-box; }
body { margin:0; background:var(--fondo); color:var(--tinta); font:16px/1.6 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif; }
a { color:var(--tinta); }
.api-cab { padding:clamp(28px,5vw,48px) 0 30px; border-bottom:3px solid var(--tinta); }
.api-cab h1 { font:700 clamp(30px,5.2vw,56px)/1.05 var(--serif); letter-spacing:-0.02em; margin:0 0 12px; }
.api-cab > .ancho > p { font-size:17px; max-width:70ch; margin:0 0 10px; }
.api-cab code { font:14px/1.5 ui-monospace,SFMono-Regular,Menlo,monospace; background:var(--codigo); padding:1px 5px; }
.saltos { display:flex; flex-wrap:wrap; gap:8px 22px; margin:14px 0 26px; font-weight:700; font-size:15px; }
.agentes { border:2px solid var(--tinta); border-radius:var(--r-caja); padding:18px 20px; }
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
/* El prompt para agentes vive en la descripción OpenAPI que pinta Scalar: que no se corte y que tenga botón de copiar */
.introduction-description pre { max-height:440px; overflow-y:auto !important; overflow-x:hidden !important; }
.introduction-description pre, .introduction-description pre * { white-space:pre-wrap !important; overflow-wrap:anywhere !important; word-break:normal; }
.copiar-prompt { font:inherit; font-size:14px; font-weight:700; background:var(--tinta); color:var(--fondo); border:2px solid var(--tinta);
  border-radius:var(--r-boton, 9px); padding:7px 14px; margin:0 0 10px; cursor:pointer; }
.copiar-prompt:hover { background:var(--fondo); color:var(--tinta); }
noscript p { max-width:68ch; margin:24px 16px; }
/* Scalar con los colores, letras y esquinas del resto de la web. Los selectores con body ganan a los del tema por defecto de Scalar. */
body.light-mode, body.dark-mode, body .scalar-app {
  --scalar-custom-header-height:var(--menu, 48px);
  --scalar-font:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif; --scalar-font-code:ui-monospace,SFMono-Regular,Menlo,monospace;
  --scalar-radius:var(--r-mini); --scalar-radius-lg:var(--r-boton); --scalar-radius-xl:var(--r-caja);
  --scalar-background-1:var(--fondo); --scalar-background-2:var(--resalte); --scalar-background-3:var(--codigo);
  --scalar-color-1:var(--tinta); --scalar-color-2:var(--suave); --scalar-color-3:var(--gris);
  --scalar-color-accent:var(--tinta); --scalar-background-accent:color-mix(in srgb, var(--tinta) 8%, var(--fondo));
  --scalar-border-color:var(--claro);
  --scalar-sidebar-background-1:var(--fondo); --scalar-sidebar-color-1:var(--tinta); --scalar-sidebar-color-2:var(--suave);
  --scalar-sidebar-border-color:var(--tinta); --scalar-sidebar-item-hover-background:var(--resalte); --scalar-sidebar-item-hover-color:var(--tinta);
  --scalar-sidebar-item-active-background:var(--resalte); --scalar-sidebar-color-active:var(--tinta);
  --scalar-sidebar-search-background:var(--fondo); --scalar-sidebar-search-border-color:var(--tinta); --scalar-sidebar-search-color:var(--gris);
  --scalar-shadow-1:none; --scalar-shadow-2:var(--flota); }
/* Modales de Scalar (buscador): fondo velado, caja con el borde y el radio de las tarjetas */
.scalar-modal-layout { background:rgba(0,0,0,.42) !important; backdrop-filter:blur(2px); }
.scalar-modal { border:2px solid var(--tinta); border-radius:var(--r-caja) !important; box-shadow:var(--flota) !important; overflow:hidden; }
.scalar-modal-search label { height:auto !important; min-height:56px; padding:8px 8px 8px 16px !important; gap:10px !important; border-bottom:1px solid var(--claro); }
.scalar-modal-search input { font-size:17px; }
.scalar-app input:focus, .scalar-app input:focus-visible, .scalar-modal-search label:focus-within { outline:none !important; box-shadow:none !important; }
/* Botón de cerrar: redondo como el de tema, 40 px de diana, icono centrado sin depender de la altura de línea */
.scalar-modal-search .scalar-icon-button { flex:none; width:40px !important; height:40px !important; margin:0 !important; padding:0 !important;
  display:grid !important; place-items:center; line-height:0; font-size:0; border-radius:50% !important; border:1.5px solid var(--tinta);
  color:var(--tinta) !important; background:var(--fondo) !important; cursor:pointer; transition:background-color .15s ease-out, color .15s ease-out, transform .12s ease-out; }
.scalar-modal-search .scalar-icon-button svg { display:block; width:15px !important; height:15px !important; }
.scalar-modal-search .scalar-icon-button:hover { background:var(--tinta) !important; color:var(--fondo) !important; }
.scalar-modal-search .scalar-icon-button:active { transform:scale(.94); }
.scalar-modal-search .scalar-icon-button:focus-visible { outline:3px solid var(--tinta); outline-offset:2px; }
.ref-search-meta { border-top:1px solid var(--claro); }
@media (max-width:760px) { .scalar-modal-search { margin-top:12px !important; max-height:calc(100dvh - 24px) !important; } }
@@CSS_MENU@@
</style>
</head>
<body>
@@MENU@@
<header class="api-cab"><div class="ancho">
<h1>Verifícalo tú</h1>
<p>No hace falta que te creas esta verificación: todo está abierto para que lo compruebes tú. Afirmaciones, veredictos, fuentes y transcripciones, en una API pública en JSON y CSV, sin registro ni clave. Base: <code>@@BASE@@/api/v1</code>.</p>
<p class="saltos"><a href="#verificalo" data-ancla="verifícalo-tú">Cómo comprobarlo ↓</a><a href="#agentes" data-ancla="prompt-para-agentes-de-ia">Prompt para agentes de IA ↓</a><a href="#referencia">Referencia de la API ↓</a><a href="/api/v1/openapi.json">openapi.json</a><a href="/llms.txt">llms.txt</a></p>
</div></header>
<div id="referencia"></div>
@@MINI@@
<footer class="pie-solo"><div class="ancho">@@PIE@@</div></footer>
<noscript><p>La referencia interactiva necesita JavaScript. Tienes la misma información en <a href="/api/v1/openapi.json">openapi.json</a>.</p></noscript>
<script src="https://cdn.jsdelivr.net/npm/@scalar/api-reference@@@SCALAR@@/dist/browser/standalone.js" integrity="@@SCALAR_SRI@@" crossorigin="anonymous"></script>
<script>
(() => {
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
  // En el buscador de Scalar la X solo borra el texto aunque parece cerrar: la convertimos en «Cerrar», que es lo que se espera.
  new MutationObserver(() => document.querySelectorAll(".scalar-modal-search .scalar-icon-button:not([data-cerrar])").forEach(b => {
    b.dataset.cerrar = ""; b.setAttribute("aria-label", "Cerrar buscador"); b.title = "Cerrar (Esc)";
    b.querySelector(".sr-only")?.replaceChildren("Cerrar buscador");
    b.addEventListener("click", ev => {
      ev.preventDefault(); ev.stopImmediatePropagation();
      const campo = b.closest(".scalar-modal")?.querySelector("input") || document.activeElement;
      campo.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", code: "Escape", bubbles: true }));
    }, true);
  })).observe(document.body, { childList: true, subtree: true });
  // Botón de copiar encima de cada bloque de la descripción (prompt, encargo y ejemplos): Scalar no lo pone en ella
  const COPIAS = [["Tienes acceso", "Copiar prompt", "Prompt copiado. Pégalo en tu agente y escribe tu pregunta al final."],
                  ["Eres un verificador", "Copiar encargo", "Encargo copiado. Pégalo en una IA que pueda navegar por internet."]];
  const prepararCopias = () => document.querySelectorAll(".introduction-description pre:not([data-listo])").forEach(pre => {
    pre.dataset.listo = "1";
    const t = pre.textContent.trim(), [, rotulo, aviso] = COPIAS.find(([ini]) => t.startsWith(ini)) || [, "Copiar", "Copiado."];
    const b = document.createElement("button");
    b.type = "button"; b.className = "copiar-prompt"; b.textContent = rotulo;
    b.onclick = () => {
      if (typeof copiarTexto === "function") copiarTexto(t, aviso); else if (navigator.clipboard) navigator.clipboard.writeText(t);
      b.textContent = "Copiado ✓"; setTimeout(() => b.textContent = rotulo, 2200);
    };
    pre.before(b);
  });
  // Saltos a secciones de la descripción: #verificalo (adonde redirige /verificalo) y #agentes
  const ANCLAS = { verificalo: "verifícalo-tú", agentes: "prompt-para-agentes-de-ia" };  // Scalar conserva las tildes
  const destino = slug => document.getElementById("api-1/description/" + slug);
  let pendiente = ANCLAS[location.hash.slice(1)];
  const irPendiente = () => { const h = pendiente && destino(pendiente); if (h) { pendiente = null; h.scrollIntoView(); } };
  new MutationObserver(() => { prepararCopias(); irPendiente(); }).observe(document.getElementById("referencia"), { childList: true, subtree: true });
  document.querySelectorAll(".saltos a[data-ancla]").forEach(a => a.addEventListener("click", ev => {
    const h = destino(a.dataset.ancla);
    if (h) { ev.preventDefault(); h.scrollIntoView(); history.replaceState(null, "", a.hash); }
  }));
  // updateConfiguration no aplica forceDarkModeState en caliente; Scalar pinta el tema según la clase del <body>.
  const sincronizar = () => {
    const oscuro = tema() === "dark";
    document.body.classList.toggle("dark-mode", oscuro);
    document.body.classList.toggle("light-mode", !oscuro);
  };
  new MutationObserver(sincronizar).observe(raiz, { attributes: true, attributeFilter: ["data-modo"] });
  sistema.addEventListener("change", sincronizar);
  // En el buscador, la X de Scalar solo borra el texto aunque parece cerrar. La convertimos en «Cerrar», que es lo que se espera.
  new MutationObserver(() => document.querySelectorAll(".scalar-modal-search .scalar-icon-button:not([data-cerrar])").forEach(b => {
    b.dataset.cerrar = ""; b.setAttribute("aria-label", "Cerrar buscador"); b.title = "Cerrar (Esc)";
    b.querySelector(".sr-only")?.replaceChildren("Cerrar buscador");
    b.addEventListener("click", ev => {
      ev.preventDefault(); ev.stopImmediatePropagation();
      const campo = b.closest(".scalar-modal")?.querySelector("input") || document.activeElement;
      campo.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", code: "Escape", bubbles: true }));
    }, true);
  })).observe(document.body, { childList: true, subtree: true });
})();
</script>
</body>
</html>
"""

REDIRIGE_API = """<!doctype html>
<html lang="es"><head><meta charset="utf-8"><meta http-equiv="refresh" content="0; url=/api">
@@CABECERA@@
</head><body><p>La referencia de la API está ahora en <a href="/api">/api</a>.</p>@@PIE@@</body></html>
"""

PORTADA = """<!doctype html>
<html lang="es">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
@@HEAD_MODO@@
@@CABECERA@@
<script>if(!matchMedia("(prefers-reduced-motion: reduce)").matches){document.documentElement.classList.add("con-gsap");window.esperaGsap=setTimeout(function(){document.documentElement.classList.remove("con-gsap")},2500)}</script>
<script defer src="https://cdn.jsdelivr.net/npm/gsap@@@GSAP@@/dist/gsap.min.js" integrity="@@GSAP_SRI@@" crossorigin="anonymous"></script>
<script defer src="https://cdn.jsdelivr.net/npm/gsap@@@GSAP@@/dist/SplitText.min.js" integrity="@@SPLIT_SRI@@" crossorigin="anonymous"></script>
<style>
:root { --serif:"Iowan Old Style","Palatino Linotype",Palatino,Georgia,serif; }
* { box-sizing:border-box; }
body { margin:0; background:var(--fondo); color:var(--tinta); font:16px/1.55 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif; }
a { color:var(--tinta); }
.cabeza { padding:clamp(28px,5vw,56px) 0 clamp(24px,3vw,36px); }
h1 { font:700 clamp(30px,5.2vw,58px)/1.05 var(--serif); letter-spacing:-0.02em; margin:0 0 16px; text-wrap:balance; max-width:20ch; }
.entrada { font-size:17px; max-width:62ch; margin:0 0 20px; }
@media (min-width:1000px) {
  .cabeza { display:grid; grid-template-columns:minmax(0,1.5fr) minmax(280px,1fr); gap:0 clamp(32px,5vw,80px); align-items:end; }
  .cabeza h1 { grid-column:1 / -1; max-width:24ch; } .cabeza .entrada { margin:0; } }
.tarjetas { display:grid; gap:18px; }
.entrevista { position:relative; border:2px solid var(--tinta); padding:22px 24px; display:grid; grid-template-columns:76px minmax(0,1fr); gap:0 22px; align-items:start; }
.entrevista > div { min-width:0; }
/* En tres columnas la cabecera (logo, nombre, partido) va arriba y el resto aprovecha todo el ancho de la tarjeta */
@media (min-width:1000px) { .tarjetas { grid-template-columns:repeat(3,minmax(0,1fr)); }
  .tarjetas .entrevista { grid-template-columns:76px minmax(0,1fr); grid-template-rows:auto auto auto auto auto auto 1fr; gap:0 18px; }
  .tarjetas .entrevista > div { display:contents; } .tarjetas .entrevista > div > * { grid-column:1 / -1; }
  .tarjetas .entrevista .logo { grid-column:1; grid-row:1 / span 3; width:76px; height:76px; align-self:start; }
  .tarjetas .entrevista h2, .tarjetas .entrevista .partido { grid-column:2; }
  .tarjetas .entrevista h2 { font-size:clamp(26px,2.2vw,32px); align-self:end; text-wrap:balance; }
  .tarjetas .entrevista .prog { margin-top:8px; } .tarjetas .entrevista .acc { grid-column:1 / -1; align-self:end; } }
.logo { width:76px; height:76px; object-fit:contain; display:block; }
/* en oscuro, los logotipos llevan una placa clara detrás (el azul del PP casi desaparece sobre fondo oscuro); en claro no hay placa */
img.logo { background:var(--logo-fondo); box-shadow:0 0 0 6px var(--logo-fondo); border-radius:var(--logo-radio); }
.logo.sin { display:grid; place-items:center; border:2px solid var(--tinta); font:700 24px/1 var(--serif); }
.entrevista.off .logo { opacity:.45; }
.partido { margin:0 0 6px; font-size:15px; font-weight:700; }
.entrevista.off { border:1px dashed var(--gris-claro); color:var(--gris); }
.prog { margin:0 0 12px; font-size:12px; text-transform:uppercase; letter-spacing:.08em; color:var(--gris); }
.entrevista h2 { font:700 32px/1.1 var(--serif); margin:0 0 2px; } .entrevista h2 a { text-decoration:none; }
.entrevista h2 a::after { content:""; position:absolute; inset:0; }

.entrevista:not(.off) { transition:transform .18s ease-out, box-shadow .18s ease-out; }
@media (hover:hover) { .entrevista:not(.off):hover { transform:translateY(-3px); box-shadow:inset 0 0 0 1px var(--tinta); }
  .entrevista:not(.off):hover h2 a { text-decoration:underline; text-decoration-thickness:2px; } }
.entrevista:not(.off):active { transform:translateY(-1px); }
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
/* Botones de cada tarjeta: la línea temporal es la acción principal (rellena) y la transcripción la secundaria (con borde) */
/* Lado a lado si cada botón cabe en una línea (≥ 200 px); si no, uno debajo de otro a todo el ancho */
.acc { grid-column:2; margin:16px 0 0; display:grid; grid-template-columns:repeat(auto-fit,minmax(min(100%,200px),1fr)); gap:10px; max-width:520px; }
.btn span { white-space:nowrap; }
.btn { position:relative; z-index:1; display:flex; align-items:center; gap:10px; min-height:46px; padding:0 14px;
  border:2px solid var(--tinta); background:var(--fondo); color:var(--tinta); font-size:15px; font-weight:700; line-height:1.2; text-decoration:none;
  transition:background-color .15s ease-out, color .15s ease-out, box-shadow .18s ease-out, transform .12s ease-out; }
.btn.principal { background:var(--tinta); color:var(--fondo); }
.btn svg { display:block; flex:none; width:18px; height:18px; fill:none; stroke:currentColor; stroke-width:2; stroke-linecap:round; stroke-linejoin:round; }
.btn svg .lleno { fill:currentColor; stroke:none; }
.btn .flecha { margin-left:auto; transition:transform .18s ease-out; }
.btn:hover { background:var(--tinta); color:var(--fondo); }
.btn.principal:hover { background:var(--fondo); color:var(--tinta); }
.btn:hover .flecha, .btn:focus-visible .flecha { transform:translateX(3px); }
.btn:active { transform:translateY(1px) scale(.99); }
.sr { position:absolute; width:1px; height:1px; overflow:hidden; clip:rect(0 0 0 0); white-space:nowrap; }
@media (min-width:1000px) { .acc { max-width:none; margin-top:18px; } }
@media (max-width:560px) { .acc { grid-column:1 / -1; max-width:none; } }
footer { border-top:3px solid var(--tinta); margin-top:48px; padding:28px 0 64px; font-size:14.5px; }
.pie-corto p { margin:0 0 6px; max-width:none; font-size:12.5px; line-height:1.5; color:var(--suave); }
.pie-corto .final { color:var(--gris); }
.pie-corto { padding-bottom:40px; }
/* Escritorio: la portada cabe en una pantalla. El cuerpo es una columna de alto completo y los tamaños se atan al alto de la ventana. */
@media (min-width:1000px) and (min-height:640px) {
  .primera { min-height:calc(100dvh - var(--menu, 48px)); display:flex; flex-direction:column; justify-content:center; gap:clamp(10px,2.4vh,40px);
    padding-top:clamp(8px,2vh,32px); padding-bottom:clamp(4px,1vh,12px); }
  .primera .seguir { margin-top:0; }
  .cabeza { padding:0; grid-template-columns:minmax(0,1.25fr) minmax(0,1fr); grid-template-rows:auto auto; gap:10px clamp(32px,4vw,72px); align-items:end; }
  .cabeza h1 { grid-column:1; grid-row:1 / span 2; max-width:none; margin:0; font-size:clamp(32px, min(3.7vw, 6vh), 60px); }
  .cabeza .entrada { grid-column:2; grid-row:1; font-size:clamp(14px,1.95vh,17px); line-height:1.5; }
  .tarjetas .entrevista { padding:clamp(14px,2.2vh,22px) 20px; }
  .des { font-size:clamp(12.5px,1.75vh,13.5px); }
  .tarjetas .entrevista .prog { margin:clamp(6px,1.2vh,12px) 0 clamp(4px,1vh,10px); font-size:11px; letter-spacing:.05em; }
  .tarjetas .entrevista h2 { font-size:clamp(23px, min(2.1vw, 3.6vh), 32px); }
  .tarjetas .entrevista { grid-template-columns:clamp(60px,8vh,76px) minmax(0,1fr); }
  .tarjetas .entrevista .logo { width:clamp(60px,8vh,76px); height:clamp(60px,8vh,76px); }
  .des { margin-bottom:0; }
  .acc { grid-template-columns:repeat(auto-fit,minmax(min(100%,140px),1fr)); } .btn .flecha { display:none; } .btn { padding:0 12px; font-size:14.5px; }
  .num { font-size:16px; } .num b { font-size:30px; }
  .tarjetas .entrevista .acc { margin-top:clamp(10px,1.6vh,18px); gap:8px; }
  .btn { min-height:clamp(40px,5.2vh,46px); }
  .ancho.pie-corto { padding-bottom:0; line-height:1.45; }
  .pie-corto p { display:inline; margin:0; font-size:clamp(11px,1.6vh,12px); }
  .pie-corto .final::before { content:" "; } }
/* Entre 1000 y 1200 px de ancho las tarjetas son estrechas: botones sin icono para que vayan en una fila, y menos relleno */
@media (min-width:1000px) and (max-width:1199px) and (min-height:640px) {
  .tarjetas .entrevista { padding:14px 16px; gap:0 14px; }
  .tarjetas .entrevista .acc { grid-template-columns:1fr 1fr; } .btn .ico { display:none; } .btn { justify-content:center; padding:0 8px; font-size:14px; }
  .tarjetas .entrevista .prog { font-size:10.5px; letter-spacing:.03em; }
  .tarjetas .entrevista .num { font-size:15px; } .tarjetas .entrevista .num b { font-size:26px; }
  .tarjetas .entrevista { grid-template-columns:56px minmax(0,1fr); } .tarjetas .entrevista .logo { width:56px; height:56px; }
  .cabeza h1 { font-size:clamp(30px,3.4vw,40px); grid-row:1; } }
/* Leyenda en texto bajo las tarjetas: una fila que se parte en varias en pantallas estrechas */
.ley-linea { display:flex; flex-wrap:wrap; gap:6px clamp(14px,2vw,28px); margin:18px 0 0; padding:0; list-style:none; font-size:13.5px; line-height:1.4; color:var(--suave); }
.ley-linea li { display:flex; align-items:baseline; gap:7px; }
.ley-linea i { flex:none; width:10px; height:10px; border-radius:50%; background:var(--tono); transform:translateY(1px); }
.ley-linea b { color:var(--tinta); }
.ley-linea .mas { margin-left:auto; }
.ley-linea .mas a { color:var(--suave); text-underline-offset:3px; }
@media (max-width:760px) { .ley-linea { display:grid; grid-template-columns:repeat(auto-fit,minmax(min(100%,240px),1fr)); gap:8px 20px; } .ley-linea .mas { margin-left:0; } }
@media (min-width:1000px) and (min-height:640px) { .ley-linea { margin:0; font-size:clamp(12px,1.7vh,13.5px); } }
/* Enlace al final de la primera pantalla que invita a bajar a la comparativa */
.seguir { align-self:center; display:inline-flex; align-items:center; gap:8px; min-height:44px; padding:0 14px; margin:18px 0 0;
  font-size:14px; font-weight:700; text-decoration:none; color:var(--gris); }
.seguir:hover { color:var(--tinta); } .seguir svg { display:block; width:16px; height:16px; fill:none; stroke:currentColor; stroke-width:2.2; stroke-linecap:round; transition:transform .2s ease-out; }
.seguir:hover svg { transform:translateY(3px); }
.compara { scroll-margin-top:calc(var(--menu, 48px) + 16px); }
/* «Puedes verificarlo tú», después de la comparativa: tres vías cortas en fichas */
.verifica-entrada { margin:0 0 16px; max-width:62ch; font-size:17px; }
.verifica-vias { display:grid; grid-template-columns:repeat(auto-fit,minmax(min(100%,240px),1fr)); gap:clamp(14px,2vw,22px); margin:0; padding:0; list-style:none; }
.verifica-vias li { display:flex; flex-direction:column; gap:8px; min-width:0; padding:clamp(16px,2vw,22px); border:2px solid var(--tinta); border-radius:var(--r-caja); }
.verifica-vias h3 { margin:0; font:700 20px/1.25 var(--serif); text-wrap:balance; }
.verifica-vias p { margin:0; font-size:15px; color:var(--suave); max-width:62ch; }
.verifica-vias a { margin-top:auto; padding-top:4px; font-weight:700; text-underline-offset:3px; }
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
footer p { max-width:68ch; }
footer .leyenda-f { max-width:820px; }
@media (min-width:1080px) { .pie { display:grid; grid-template-columns:minmax(0,1.2fr) minmax(0,1fr); gap:0 clamp(40px,5vw,80px); align-items:start; }
  .pie > div > p:first-child { margin-top:0 !important; } }
@media (max-width:560px) { .entrevista { grid-template-columns:60px minmax(0,1fr); gap:0 14px; padding:16px; } .logo { width:60px; height:60px; } .entrevista h2 { font-size:26px; } }
@@CSS_MENU@@
/* ── Hero con GSAP: el titular sube por líneas y se subraya «dato a dato»; debajo, un carrusel de afirmaciones reales que reciben su veredicto como un sello */
.subraya { font-style:normal; background:linear-gradient(var(--tinta),var(--tinta)) no-repeat 0 96% / var(--subrayado,100%) .075em;
  -webkit-box-decoration-break:clone; box-decoration-break:clone; }
/* Sin marco: arriba el rótulo con las flechas a su derecha; debajo quién y cuándo, la cita y el sello del veredicto a la derecha */
.muestra { position:relative; margin-top:20px; max-width:62ch; }
.muestra-cab { display:flex; align-items:center; justify-content:space-between; gap:12px; margin:0 0 4px; }
.muestra-rot { margin:0; min-width:0; font-size:11px; font-weight:700; text-transform:uppercase; letter-spacing:.08em; color:var(--gris); }
.muestra-barra { display:flex; flex:none; gap:2px; margin:0 -8px 0 0; }
.muestra-barra button { display:grid; place-items:center; width:40px; height:40px; padding:0; cursor:pointer; border:0; border-radius:var(--r-boton);
  background:transparent; color:var(--tinta); transition:background-color .15s ease-out, transform .12s ease-out; }
.muestra-barra button:hover { background:var(--claro); }
.muestra-barra button:active { transform:scale(.92); }
.muestra-barra button:focus-visible { outline:2px solid var(--tinta); outline-offset:0; }
.muestra-barra svg { width:18px; height:18px; fill:none; stroke:currentColor; stroke-width:2.4; stroke-linecap:round; stroke-linejoin:round; }
.muestra-lista { list-style:none; margin:0; padding:0; display:grid; }
.muestra-item { grid-area:1 / 1; visibility:hidden; min-width:0; }
.muestra-item.activa { visibility:visible; }
.muestra-item a { display:grid; grid-template-columns:minmax(0,1fr) auto; gap:6px 20px; align-items:center; color:inherit; text-decoration:none; }
.muestra-quien { grid-column:1; font-size:12.5px; font-weight:700; line-height:24px; color:var(--suave); }
.muestra-cita { grid-column:1; font:italic 400 clamp(17px,1.55vw,21px)/1.3 var(--serif); text-wrap:pretty; }
.muestra-cita .palabra-mask { padding:0 .12em .08em; margin:0 -.12em -.08em; }
.muestra-item a:hover .muestra-cita { text-decoration:underline; text-decoration-thickness:1px; text-underline-offset:3px; }
.muestra-item a:focus-visible { outline:2px solid var(--tinta); outline-offset:4px; border-radius:var(--r-mini); }
.estampa { grid-column:2; grid-row:1 / span 2; justify-self:end; align-self:center; padding:8px 12px; border:2.5px solid currentColor; border-radius:var(--r-mini);
  color:var(--tono); background:color-mix(in srgb, var(--tono) 8%, var(--fondo)); transform:rotate(-4deg);
  font:800 14px/1 -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif; letter-spacing:.09em; text-transform:uppercase; white-space:nowrap; }
@media (max-width:560px) { .muestra-rot { letter-spacing:.05em; } .muestra-item a { column-gap:12px; } .estampa { padding:7px 9px; font-size:12px; } }
/* Escritorio: a la izquierda el titular con la entradilla debajo; a la derecha el carrusel, más grande y centrado en vertical */
@media (min-width:1000px) {
  .cabeza { grid-template-columns:minmax(0,1.3fr) minmax(0,1fr); }
  .cabeza h1 { grid-column:1; grid-row:1; align-self:end; }
  .cabeza .entrada { grid-column:1; grid-row:2; align-self:start; margin:14px 0 0; }
  .cabeza .muestra { grid-column:2; grid-row:1 / span 2; align-self:center; margin:0; max-width:none; }
  .muestra-cita { font-size:clamp(20px,1.9vw,27px); line-height:1.25; }
  .estampa { font-size:15px; padding:10px 14px; border-width:3px; } }
/* Escritorio a una pantalla: los tamaños se atan también al alto de la ventana */
@media (min-width:1000px) and (min-height:640px) {
  .cabeza { grid-template-rows:auto auto; row-gap:0; }
  .cabeza h1 { grid-row:1; font-size:clamp(30px, min(3.5vw, 5.4vh), 58px); }
  .cabeza .entrada { grid-column:1; grid-row:2; margin-top:clamp(8px,1.6vh,16px); }
  .cabeza .muestra { grid-column:2; grid-row:1 / span 2; }
  main.ancho { gap:clamp(8px,1.6vh,28px); }
  .muestra-cita { font-size:clamp(18px, min(1.9vw, 3.1vh), 27px); }
  .muestra-item a { min-height:64px; } }
@media (min-width:1000px) and (max-width:1199px) and (min-height:640px) { .muestra-cita { font-size:clamp(17px,1.8vw,20px); } .estampa { font-size:13.5px; padding:8px 11px; } }
/* Mientras carga GSAP (como mucho 2,5 s) lo que va a animar no se pinta; luego sus animaciones sustituyen a las de CSS */
.con-gsap .cabeza h1, .con-gsap .cabeza .entrada, .con-gsap .muestra, .con-gsap .tarjetas .entrevista { visibility:hidden; }
.gsap-listo .cabeza *, .gsap-listo .tarjetas .entrevista, .gsap-listo .tarjetas .entrevista * { animation:none !important; }
</style>
</head>
<body>
@@MENU@@
<main class="ancho">
<div class="primera">
<div class="cabeza">
<h1>Las entrevistas de The Wild Project, comprobadas<br> <em class="subraya">dato a dato</em></h1>
<p class="entrada">Jordi Wild ha entrevistado a los candidatos a las elecciones generales del 29 de noviembre. Comprobamos cada dato que dan con fuentes públicas, con el mismo método y la misma vara de medir para todos.</p>
@@MUESTRA@@
</div>
<div class="tarjetas">@@TARJETAS@@</div>
@@LEYENDA_LINEA@@
<a class="seguir" href="#compara-t">Comparativa de los candidatos<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 5v14M6 13l6 6 6-6"/></svg></a>
</div>
@@COMPARATIVA@@
<section class="verifica" aria-labelledby="verifica-t">
<h2 class="seccion-t" id="verifica-t">Puedes verificarlo tú</h2>
<p class="verifica-entrada">No hace falta que te fíes: todo está a la vista para que lo compruebes.</p>
<ul class="verifica-vias">
<li><h3>El vídeo y las fuentes</h3><p>Cada afirmación abre el vídeo en el segundo exacto y enlaza las fuentes con las que se comprobó.</p><a href="/metodologia">Cómo se verifica →</a></li>
<li><h3>Tu propia IA</h3><p>Hay un encargo listo para que cualquier IA revise la verificación por su cuenta, y todos los datos están en abierto.</p><a href="/api#verificalo">Copiar el encargo →</a></li>
<li><h3>¿Un error o algo que falta?</h3><p>Mándanos el enlace a una fuente y lo revisamos con el mismo criterio para todos.</p><a href="/participa">Participa →</a></li>
</ul>
</section>
</main>
<footer><div class="ancho pie-corto">
<p>Verificación asistida por IA (transcripción con Whisper, contraste con modelos Claude y búsqueda web), sin revisión de un equipo de periodistas. Cada afirmación enlaza el segundo exacto del vídeo y sus fuentes, y el código, las transcripciones y los datos están publicados en <a href="@@REPO@@" target="_blank" rel="noopener noreferrer">GitHub</a>. «Falso» no implica intención de mentir: incluye errores y lapsus. El número de afirmaciones falsas depende también de cuánto habla cada invitado y de cuántos datos da, así que las cifras no son un ranking. En rojo, junto a cada tema, cuántas afirmaciones falsas o engañosas contiene.</p>
<p class="final">Última actualización: @@FECHA@@. @@CREDITOS@@</p>
@@PIE@@
</div></footer>
<script>
// Hero: GSAP anima la entrada y mueve el carrusel. Sin GSAP (no cargó) o con poco movimiento, todo se ve quieto y el carrusel se pasa a mano.
addEventListener("DOMContentLoaded", () => {
  const raiz = document.documentElement, muestra = document.querySelector(".muestra");
  const conGsap = !!(window.gsap && window.SplitText) && raiz.classList.contains("con-gsap");
  clearTimeout(window.esperaGsap);
  if (conGsap) { raiz.classList.add("gsap-listo"); gsap.registerPlugin(SplitText); }
  raiz.classList.remove("con-gsap");
  if (!conGsap) { if (muestra) carrusel(muestra, false); return; }

  const h1 = document.querySelector(".cabeza h1");
  const tl = gsap.timeline({ defaults: { ease: "expo.out", duration: .9 } });
  const lineas = SplitText.create(h1, { type: "lines", mask: "lines" });
  tl.from(lineas.lines, { yPercent: 115, stagger: .09, onComplete: () => lineas.revert() })
    .fromTo(".subraya", { "--subrayado": "0%" }, { "--subrayado": "100%", duration: .7, ease: "power3.inOut" }, "-=.3")
    .from(".cabeza .entrada", { autoAlpha: 0, y: 18, duration: .8, ease: "power3.out", clearProps: "transform,opacity,visibility" }, .2);
  if (muestra) tl.from(muestra, { autoAlpha: 0, y: 18, duration: .8, ease: "power3.out", clearProps: "transform,opacity,visibility",
                                  onStart: () => carrusel(muestra, true) }, .35);
  tl.from(".tarjetas .entrevista", { autoAlpha: 0, y: 28, stagger: .1, duration: .85, ease: "power3.out", clearProps: "transform,opacity,visibility" }, .4)
    .from(".tarjetas .retrato", { autoAlpha: 0, scale: .8, stagger: .1, duration: .6, ease: "back.out(2)", clearProps: "transform,opacity,visibility" }, .5)
    .from(".tarjetas .insignia", { autoAlpha: 0, scale: .5, stagger: .1, duration: .45, ease: "back.out(2.5)", clearProps: "transform,opacity,visibility" }, .8)
    .fromTo(".tarjetas .barra-reparto", { clipPath: "inset(0 100% 0 0 round 999px)" },
            { clipPath: "inset(0 0% 0 0 round 999px)", stagger: .1, duration: 1.1, ease: "power2.inOut", clearProps: "clipPath" }, .7);
  document.querySelectorAll(".tarjetas .num > b").forEach((b, i) => {
    b.style.minWidth = b.offsetWidth + "px"; b.style.display = "inline-block";
    tl.from(b, { textContent: 0, snap: { textContent: 1 }, duration: 1.1, ease: "power2.out" }, .7 + i * .1);
  });
});

function carrusel(muestra, animado) {
  const items = [...muestra.querySelectorAll(".muestra-item")], lista = muestra.querySelector(".muestra-lista");
  const ESPERA = 5.5;
  let actual = 0, paso = null, espera = null, parado = !animado, encima = false;
  const partes = it => ["muestra-quien", "estampa"].map(c => it.querySelector("." + c));
  const activar = (viejo, nuevo) => {
    viejo.classList.remove("activa"); viejo.setAttribute("aria-hidden", "true"); viejo.inert = true;
    nuevo.classList.add("activa"); nuevo.removeAttribute("aria-hidden"); nuevo.inert = false;
  };
  // Empieza en una afirmación al azar: si no, cada visita abriría con el mismo candidato y el mismo veredicto
  const inicio = Math.floor(Math.random() * items.length);
  if (inicio) { activar(items[0], items[inicio]); actual = inicio; }
  // Cada cita se parte en palabras una sola vez y se queda partida: deshacer el corte al acabar recolocaba el texto un píxel
  if (animado) items.forEach(it => { it._palabras = SplitText.create(it.querySelector(".muestra-cita"), { type: "words", mask: "words", wordsClass: "palabra" }).words; });
  const entrar = it => {
    const [quien, estampa] = partes(it);
    return gsap.timeline()
      .fromTo(quien, { autoAlpha: 0, x: -10 }, { autoAlpha: 1, x: 0, duration: .35, ease: "power2.out" })
      .fromTo(it._palabras, { yPercent: 110 }, { yPercent: 0, duration: .55, stagger: .022, ease: "power3.out" }, "<.05")
      .fromTo(estampa, { autoAlpha: 0, scale: 2, rotation: -18 }, { autoAlpha: 1, scale: 1, rotation: -4, duration: .38, ease: "back.out(2.6)" }, ">-.15")
      .to(muestra, { keyframes: { x: [0, -3, 2.5, -1.5, 0] }, duration: .24, ease: "none", clearProps: "x" }, "<.22");
  };
  const salir = it => gsap.timeline()
    .to(it._palabras, { yPercent: -110, duration: .3, stagger: .01, ease: "power2.in" })
    .to(partes(it), { autoAlpha: 0, duration: .22, ease: "power1.in" }, "<");
  // Pasa sola cada ESPERA segundos y solo se para mientras el ratón o el foco del teclado están encima.
  // Las flechas cambian de afirmación y vuelven a empezar la cuenta. Lo que pasa solo no se anuncia al lector de pantalla.
  const esperar = () => {
    espera?.kill(); espera = null;
    if (parado) return;
    espera = gsap.delayedCall(ESPERA, () => { lista.setAttribute("aria-live", "off"); ir(actual + 1); });
    if (encima) espera.pause();
  };
  function ir(n) {
    n = (n + items.length) % items.length;
    if (n === actual) return;
    const viejo = items[actual], nuevo = items[n];
    actual = n;
    if (!animado) { activar(viejo, nuevo); return; }
    paso?.progress(1).kill(); espera?.kill();
    paso = gsap.timeline({ onComplete: esperar }).add(salir(viejo)).add(() => activar(viejo, nuevo)).add(entrar(nuevo));
  }
  const mano = d => { lista.setAttribute("aria-live", "polite"); ir(actual + d); };
  muestra.querySelector(".muestra-ant").onclick = () => mano(-1);
  muestra.querySelector(".muestra-sig").onclick = () => mano(1);
  if (!animado) return;
  const sobre = v => { encima = v; if (espera) v ? espera.pause() : espera.resume(); };
  muestra.addEventListener("pointerenter", e => e.pointerType === "mouse" && sobre(true));
  muestra.addEventListener("pointerleave", e => e.pointerType === "mouse" && sobre(false));
  const conTeclado = el => { try { return el.matches(":focus-visible"); } catch (e) { return true; } };
  muestra.addEventListener("focusin", e => conTeclado(e.target) && sobre(true));
  muestra.addEventListener("focusout", e => muestra.contains(e.relatedTarget) || sobre(false));
  paso = gsap.timeline({ onComplete: esperar }).add(entrar(items[actual]), .25);
}
</script>
</body>
</html>
"""

TRANSCRIPCION = """<!doctype html>
<html lang="es">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
@@HEAD_MODO@@
@@CABECERA@@
<style>
:root { --serif:"Iowan Old Style","Palatino Linotype",Palatino,Georgia,serif; }
* { box-sizing:border-box; }
body { margin:0; background:var(--fondo); color:var(--tinta); font:16px/1.6 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif; }
a { color:var(--tinta); }
main.ancho { padding-bottom:72px; }
.lectura { max-width:780px; min-width:0; }
.indice { display:none; }
/* En pantallas anchas, un índice de temas fijo a la izquierda acompaña la lectura y marca el tema en curso */
@media (min-width:1180px) {
  main.ancho { display:grid; grid-template-columns:minmax(220px,300px) minmax(0,780px); gap:0 clamp(40px,5vw,88px); }
  .indice { display:block; position:sticky; top:calc(var(--menu, 48px) + 64px); align-self:start; margin-top:44px;
    max-height:calc(100vh - var(--menu, 48px) - 96px); overflow-y:auto; scrollbar-width:thin; }
  .indice p { margin:0 0 8px; font-size:11px; font-weight:700; text-transform:uppercase; letter-spacing:.09em; color:var(--gris); }
  .indice ol { list-style:none; margin:0; padding:0; border-top:2px solid var(--tinta); }
  .indice a { display:flex; justify-content:space-between; gap:12px; padding:8px 10px; margin:0 -10px; border-bottom:1px solid var(--claro);
    font-size:14px; line-height:1.35; text-decoration:none; }
  .indice small { color:var(--gris); font-variant-numeric:tabular-nums; padding-top:1px; }
  .indice a:hover { background:var(--resalte); }
  .indice a.aqui { font-weight:700; box-shadow:inset 3px 0 0 var(--tinta); } }
h1 { font:700 clamp(28px,4.6vw,44px)/1.08 var(--serif); letter-spacing:-0.02em; margin:36px 0 12px; text-wrap:balance; }
.entrada { font-size:16px; color:var(--suave); max-width:64ch; margin:0 0 8px; }
h2 { font:700 23px/1.2 var(--serif); margin:44px 0 14px; padding-top:12px; border-top:3px solid var(--tinta); text-wrap:balance; }
.turno { margin:0 0 16px; }
.par { display:grid; grid-template-columns:74px minmax(0,1fr); gap:0 14px; }
.par:target { background:var(--resalte); }
.minuto { font-size:13px; font-weight:700; font-variant-numeric:tabular-nums; text-underline-offset:3px; padding-top:4px; align-self:start; justify-self:start; }
.minuto:hover { background:var(--tinta); color:var(--fondo); text-decoration:none; }
.par:target { animation:destello 1.6s ease-out; }
.par p { margin:0; padding-bottom:10px; font:17px/1.65 var(--serif); }
/* Con voces, tres columnas como en un guion: minuto · quién habla (al empezar cada intervención) · texto.
   Lo del candidato va en serif con una raya vertical continua; lo demás, en palo seco y más apagado. */
.con-voces .par { grid-template-columns:64px 168px minmax(0,1fr); gap:0 12px; }
.quien { display:flex; align-items:flex-start; gap:9px; padding-top:1px; min-width:0;
  font:700 13.5px/1.25 -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif; color:var(--tinta); }
.nom { display:flex; flex-direction:column; gap:2px; min-width:0; padding-top:1px; overflow-wrap:anywhere; }
.quien small { font-size:12px; font-weight:500; color:var(--gris); }
.cara { width:34px; height:34px; flex:none; border-radius:50%; display:grid; place-items:center; object-fit:cover;
  font:700 12px/1 -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif; letter-spacing:.02em; border:1.5px solid currentColor; }
img.cara { border:0; background:var(--claro); }
.turno[data-voz=G] .par p { border-left:3px solid var(--tinta); padding-left:16px; }
.turno:not([data-voz=G]) .par p { padding-left:19px; color:var(--suave); font:15.5px/1.65 -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif; padding-bottom:10px; }
.turno:not([data-voz=G]) .quien { color:var(--suave); }
.turno[data-voz=V] .par p, .turno[data-voz=O] .par p { font-style:italic; }
.turno[data-voz=""] .par p { padding-left:0; color:var(--tinta); font:17px/1.65 var(--serif); }
/* el tramo de cada afirmación analizada, subrayado con el color de su veredicto y enlazado a su tarjeta */
.subr { color:inherit; text-decoration:underline; text-decoration-color:var(--tono); text-decoration-thickness:3px;
  text-underline-offset:4px; text-decoration-skip-ink:none; }
.subr:hover { background:color-mix(in srgb, var(--tono) 18%, transparent); }
.et { font:700 10.5px/1 -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif; text-transform:uppercase; letter-spacing:.06em;
  color:var(--sobre-tono); background:var(--tono); padding:2px 6px 3px; border-radius:3px; text-decoration:none; white-space:nowrap;
  vertical-align:2px; margin-left:2px; }
.et:hover { filter:brightness(1.1); }
.apagada.subr { text-decoration:none; pointer-events:none; } .apagada.et { display:none; }
@media (max-width:600px) { .par { grid-template-columns:1fr; } .par p { font-size:16.5px; }
  /* en móvil, el minuto y quién habla comparten fila encima del texto */
  .con-voces .par { grid-template-columns:auto minmax(0,1fr); align-items:center; }
  .con-voces .par p { grid-column:1 / -1; margin-top:4px; }
  .quien { align-items:center; gap:8px; padding-top:0; } .nom { flex-direction:row; align-items:baseline; gap:6px; padding-top:0; }
  .cara { width:28px; height:28px; font-size:11px; }
  .turno[data-voz=G] .par p { padding-left:12px; } .turno:not([data-voz=G]) .par p { padding-left:0; } }
.ir-tema { flex:none; max-width:min(240px, 52vw); font:inherit; font-size:12.5px; font-weight:700; color:var(--fondo); background:var(--tinta);
  border:1.5px solid var(--tinta); border-radius:999px; padding:3px 26px 3px 11px; text-overflow:ellipsis; -webkit-appearance:none; appearance:none;
  background-image:linear-gradient(45deg, transparent 50%, var(--fondo) 50%), linear-gradient(135deg, var(--fondo) 50%, transparent 50%);
  background-position:calc(100% - 15px) 52%, calc(100% - 10px) 52%; background-size:5px 5px; background-repeat:no-repeat; }
@media (min-width:1180px) { .ir-tema { display:none; } }
@media (max-width:760px) { .ir-tema { font-size:13px; min-height:34px; } }
@@CSS_MENU@@
</style>
</head>
<body>
@@MENU@@
@@FILTROS@@
<main class="ancho">
<nav class="indice" aria-label="Temas de la entrevista"><p>Temas</p><ol>@@INDICE@@</ol></nav>
<div class="lectura">
<div class="titular">@@RETRATO@@<h1>Transcripción completa: @@INVITADO@@ con Jordi Wild</h1></div>
<p class="entrada">@@PROGRAMA@@ · @@FECHA_VIDEO@@ · @@DURACION@@. Transcripción automática (Whisper), que puede tener errores en nombres y cifras; los nombres mal transcritos más claros se corrigen con un <a href="@@REPO@@/blob/main/entrevistas/glosario.json" target="_blank" rel="noopener noreferrer">glosario público</a>. @@NOTA_VOCES@@Cada minuto abre el <a href="https://www.youtube.com/watch?v=@@VIDEO@@" target="_blank" rel="noopener noreferrer">vídeo</a> en ese punto. <b>Lo subrayado es una afirmación analizada</b>: el color es su veredicto, y al pulsarla vas a su tarjeta en la <a href="/@@SLUG@@">línea temporal</a>, con la justificación y las fuentes. Si ves algo sin subrayar que habría que comprobar, <a href="/proponer?e=@@SLUG@@">propónlo</a>.</p>
@@CUERPO@@
<div style="border-top:3px solid var(--tinta); margin-top:48px; padding-top:22px">@@LEYENDA@@</div>
</div>
</main>
@@MINI@@
<footer class="pie-solo"><div class="ancho">@@PIE@@</div></footer>
@@REPRODUCTOR@@
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
  document.querySelectorAll(".turno").forEach(t => {
    t.hidden = solo && !t.querySelector(".par:not([hidden])");
    // quién habla va en el primer párrafo visible de la intervención (al filtrar, el primero puede quedar oculto)
    const celdas = t.querySelectorAll(".par > .quien");
    if (!celdas.length) return;
    if (t.dataset.ficha === undefined) t.dataset.ficha = celdas[0].innerHTML;
    const visible = t.querySelector(".par:not([hidden])");
    celdas.forEach(c => { c.innerHTML = visible && c.parentNode === visible ? t.dataset.ficha : ""; });
  });
  const marcas = document.querySelectorAll(".par:not([hidden]) .et:not(.apagada)").length;
  document.querySelector("#filtros .cuenta").textContent = `${marcas} afirmaciones marcadas`;
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
const enIndice = new Map([...document.querySelectorAll(".indice a")].map(a => [a.hash.slice(1), a]));
const irTema = document.getElementById("ir-tema");
irTema.onchange = () => {
  const h = irTema.value && document.getElementById(irTema.value);
  if (!h) return;
  h.scrollIntoView(); history.replaceState(null, "", "#" + h.id);
};
if (enIndice.size && "IntersectionObserver" in window) {
  const obs = new IntersectionObserver(es => es.forEach(x => {
    if (!x.isIntersecting) return;
    enIndice.forEach(a => a.classList.remove("aqui"));
    enIndice.get(x.target.id)?.classList.add("aqui");
    irTema.value = x.target.id;
  }), { rootMargin: "0px 0px -70% 0px" });
  enIndice.forEach((a, id) => { const h = document.getElementById(id); if (h) obs.observe(h); });
}
</script>
@@FAB@@
</body>
</html>
"""

PLANTILLA = """<!doctype html>
<html lang="es">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
@@HEAD_MODO@@
@@CABECERA@@
<style>
:root { --col:40%; --hueco:56px;
  --serif:"Iowan Old Style","Palatino Linotype",Palatino,Georgia,serif; }
* { box-sizing:border-box; }
html { scroll-behavior:smooth; }
body { margin:0; background:var(--fondo); color:var(--tinta); font:16px/1.55 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif; -webkit-text-size-adjust:100%; }
a { color:var(--tinta); }
.cima { display:flex; justify-content:space-between; gap:12px; padding-top:18px; font-size:13px; }
.cima a { font-weight:600; white-space:nowrap; }
.portada { padding-top:clamp(28px,5vw,48px); padding-bottom:28px; }
h1 { font:700 clamp(30px,5.2vw,56px)/1.05 var(--serif); letter-spacing:-0.02em; margin:0 0 18px; text-wrap:balance; max-width:22ch; }
.entrada { font-size:17px; margin:0 0 20px; max-width:62ch; }
.intro .abrir { margin:0; }
.cifras { margin-top:28px; }
.dato { display:flex; align-items:center; gap:18px; border-top:3px solid var(--tinta); border-bottom:1px solid var(--tinta); padding:14px 0; }
.dato b { flex:none; font:700 clamp(64px,11vw,104px)/0.85 var(--serif); font-variant-numeric:tabular-nums; }
.dato span { font-size:clamp(16px,1.6vw,19px); max-width:26ch; line-height:1.3; }
@media (min-width:980px) {
  .portada { display:grid; grid-template-columns:minmax(0,1.35fr) minmax(300px,1fr); gap:0 clamp(32px,5vw,80px); align-items:end; }
  .portada .titular { grid-column:1 / -1; } .portada h1 { max-width:none; }
  .cifras { margin-top:0; } }
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
[data-v=falso] .panel { box-shadow:inset 5px 0 0 var(--tono); padding-left:23px; }
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
/* Tema plegado: sin afirmaciones (vacio) o sin ninguna que pase el filtro (plegado). Se queda en la línea, más pequeño y en gris */
.sin-filtro { display:none; margin:8px 0 0; font-size:13.5px; color:var(--gris); }
.capitulo.plegado .sin-filtro { display:block; }
.capitulo.plegado .barra-tema { display:none; }
.recuento.sin { color:var(--gris); font-weight:500; }
.ver-tema { font:inherit; font-size:13px; font-weight:600; color:var(--tinta); background:var(--fondo); border:1.5px solid var(--tinta);
  border-radius:var(--r-boton); padding:3px 10px; margin-left:4px; cursor:pointer; }
.ver-tema:hover { background:var(--tinta); color:var(--fondo); }
.capitulo.plegado, .capitulo.vacio { margin-top:28px; padding:16px 0 6px; border-top-width:1px; }
.capitulo.plegado .cab-tema h2, .capitulo.vacio .cab-tema h2 { font-size:21px; }
.capitulo.plegado .marca, .capitulo.vacio .marca { background:var(--fondo); color:var(--gris); border:1.5px solid var(--gris);
  width:30px; height:30px; left:calc(var(--col) - 14px); top:-16px; font-size:14px; }
@media (max-width:600px) { .ver-tema { min-height:36px; margin:6px 0 0; display:block; } .capitulo.plegado .cab-tema h2, .capitulo.vacio .cab-tema h2 { font-size:19px; } }
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
@media (min-width:1080px) { .pie { display:grid; grid-template-columns:minmax(0,1.2fr) minmax(0,1fr); gap:0 clamp(40px,5vw,80px); align-items:start; }
  footer .pie .leyenda-f { margin-bottom:0; } }
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
  .tema-actual { max-width:none; font-size:12.5px; } }
/* Por debajo de 600 px el minuto pasa encima del panel y el panel ocupa casi todo el ancho */
@media (max-width:600px) {
  :root { --col:7px; --hueco:16px; }
  .linea { padding-top:16px; }
  .hito { padding:10px 0 12px; }
  .dicho { grid-column:3; grid-row:1; text-align:left; padding:0 0 6px; }
  .minuto { justify-self:start; margin:0; font-size:14px; }
  .punto { top:15px; } [data-v=falso] .punto { top:13px; }
  .hito:not([data-v=falso]):not([data-v=enganoso]) .punto { top:17px; }
  .flecha { display:none; }
  .panel { grid-row:2; padding:14px 14px 12px; }
  [data-v=falso] .panel { padding-left:19px; }
  .capitulo .minuto { grid-column:3; grid-row:1; margin:0 0 4px; }
  .cab-tema { grid-column:3; grid-row:2; padding-left:0; }
  .marca { left:calc(var(--col) - 15px); }
  .copiar { min-height:36px; } }
.abrir { margin:14px 0 0; padding:12px 14px; border:1.5px solid var(--tinta); font-size:14.5px; max-width:68ch; }
.contrasta { margin:12px 0 0; }
.completa { margin:10px 0 0; padding-top:8px; border-top:1px solid var(--claro); font-size:13px; font-weight:600; }
.completa a { text-underline-offset:3px; } .completa a:hover { color:var(--tono); }
/* botón de expandir: abre la afirmación en su propia página (/<slug>/<id>) */
.panel { position:relative; }
.expandir { position:absolute; top:10px; right:10px; width:30px; height:30px; display:grid; place-items:center;
  color:var(--gris); background:var(--fondo); border:1.5px solid var(--claro); border-radius:var(--r-mini); }
.expandir svg { width:15px; height:15px; fill:none; stroke:currentColor; stroke-width:2; stroke-linecap:round; stroke-linejoin:round; }
@media (hover:hover) { .hito:hover .expandir { color:var(--tono); border-color:var(--tono); } }
.hito .expandir:hover, .hito .expandir:focus-visible { color:var(--fondo); background:var(--tinta); border-color:var(--tinta); }
@media (max-width:600px) { .expandir { top:8px; right:8px; width:34px; height:34px; } }
.copiar { font:inherit; font-size:12.5px; font-weight:600; background:var(--fondo); color:var(--tinta); border:1.5px solid var(--tinta); padding:4px 11px; cursor:pointer; }
.copiar:hover, .copiar.hecho { background:var(--tinta); color:var(--fondo); }
.hito:target .panel { outline:3px solid var(--tono); outline-offset:3px; animation:destello 1.6s ease-out; }
@keyframes destello { from { background:color-mix(in srgb, var(--tono, var(--tinta)) 16%, var(--fondo)); } }
.punto { transition:transform .18s ease-out; }
.panel { transition:border-color .18s ease-out, box-shadow .18s ease-out; }
@media (hover:hover) {
  .hito:hover .punto { transform:scale(1.4); }
  .hito:hover .panel { border-color:var(--tono); box-shadow:inset 0 0 0 1px var(--tono); }
  .hito[data-v=falso]:hover .panel { box-shadow:inset 5px 0 0 var(--tono), inset 0 0 0 1px var(--tono); }
  .hito:not([data-v=falso]):not([data-v=enganoso]):hover .panel { border-color:var(--tono); }
  .hito:hover .minuto { text-decoration-thickness:2px; } }
.copiar.hecho { background:var(--tinta); color:var(--fondo); }
/* lo que había dicho Jordi justo antes de la cita (lo pinta el script desde preguntas.json): más pequeño y gris, como sus intervenciones
   en la transcripción. En escritorio va en la columna de la cita, debajo del minuto; en móvil, dentro de la tarjeta, encima de la cita. */
.pregunta { margin:12px 0 14px; color:var(--suave); font:14px/1.45 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif; }
.pregunta-cab { display:flex; align-items:center; gap:7px; margin:0 0 4px; font-size:12.5px; font-weight:700; }
.dicho .pregunta-cab { justify-content:flex-end; }
.pregunta .cara { width:22px; height:22px; flex:none; display:grid; place-items:center; border:1.5px solid currentColor; border-radius:50%;
  font-size:8.5px; font-weight:700; letter-spacing:.02em; }
.pregunta .min-p { color:var(--gris); font-weight:600; font-variant-numeric:tabular-nums; }
.pregunta .min-p:hover { background:var(--tinta); color:var(--fondo); text-decoration:none; }
.pregunta-txt { margin:0; text-wrap:pretty; }
.panel .pregunta { display:none; }
@media (max-width:860px) { .dicho .pregunta { display:none; } .panel .pregunta { display:block; margin:0 0 12px; } }
@@CSS_MENU@@
</style>
</head>
<body>
@@MENU@@
<div class="ancho portada">
  <div class="titular">@@RETRATO@@<h1>@@INVITADO@@ con Jordi Wild, minuto a minuto</h1></div>
  <div class="intro">
  <p class="entrada">Hemos transcrito la <a href="https://www.youtube.com/watch?v=@@VIDEO@@" target="_blank" rel="noopener noreferrer">entrevista completa</a> (@@DURACION@@) y contrastado con fuentes públicas las @@SUMA@@ afirmaciones que se pueden comprobar. Esta es la línea temporal: pulsa cualquier minuto para ver ese momento del vídeo, o lee la <a href="/@@SLUG@@/transcripcion">transcripción completa</a>.</p>
  <p class="abrir"><b>Contrástalo tú mismo.</b> Cada panel enlaza el vídeo y sus fuentes, y trae un botón que copia un encargo listo para pegar en cualquier IA. También puedes descargar <a href="/api/v1/@@SLUG@@.json">todos los datos de esta entrevista (JSON)</a>, usar la <a href="/api">API abierta</a> o leer el <a href="/metodologia">método</a>. ¿Falta algo que se dijo? <a href="/proponer?e=@@SLUG@@">Propón un hecho para verificar</a>.</p>
  </div>
  <div class="cifras">
  <div class="dato"><b>@@MALAS@@</b><span>afirmaciones falsas (@@FALSAS@@) o engañosas (@@ENGANOSAS@@) de @@SUMA@@ comprobadas</span></div>
  @@BARRA@@
  <p class="resto">El resto: @@VERDADERAS@@ verdaderas, @@CASI@@ casi ciertas y @@NV@@ que no se han podido verificar.@@NOTA_EXCL@@</p>
  </div>
  @@MINI@@
</div>
@@FILTROS@@
<main class="ancho"><ol class="linea">@@FILAS@@</ol></main>
<footer><div class="ancho pie">
  @@LEYENDA@@
  <div class="como">
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
  <p>¿Ves un error? Abre la afirmación y pulsa «Avisar de un error»: solo te pediremos un enlace a una fuente. Última actualización: @@FECHA@@.</p>
  <p>@@CREDITOS@@</p>
  </div>
@@PIE@@
</div></footer>
@@REPRODUCTOR@@
<script>
const activos = new Set(["falso", "enganoso"]);
const botones = document.querySelectorAll("#filtros button[data-v]");
const todas = document.querySelector("#filtros [data-todas]");
const aqui = location.pathname.replace(/\\/$/, "");
function pintar() {
  botones.forEach(b => b.setAttribute("aria-pressed", activos.has(b.dataset.v)));
  todas.setAttribute("aria-pressed", activos.size === botones.length);
  // Un tema que el filtro deja sin afirmaciones no desaparece: se pliega y ofrece ver las suyas
  let cap = null, n = 0;
  const plegar = () => { if (cap) cap.classList.toggle("plegado", n === 0 && !cap.classList.contains("vacio")); };
  document.querySelectorAll(".linea > li").forEach(li => {
    if (li.classList.contains("capitulo")) { plegar(); cap = li; n = 0; }
    else { li.hidden = !activos.has(li.dataset.v); if (!li.hidden) n++; }
  });
  plegar();
  const vistas = document.querySelectorAll(".linea > .hito:not([hidden])").length;
  document.querySelector("#filtros .cuenta").textContent = `Mostrando ${vistas} de ${@@SUMA@@}`;
  document.querySelectorAll(".lista a[data-tema]").forEach(a => {
    if (a.pathname.replace(/\\/$/, "") === aqui) a.classList.toggle("off", document.getElementById(a.dataset.tema).classList.contains("plegado"));
  });
}
function verTodo() { botones.forEach(b => activos.add(b.dataset.v)); }
// Al filtrar desde abajo, vuelve al principio de la lista para que se vea el resultado y no un hueco
const alInicio = () => { const l = document.querySelector(".linea"); if (l.getBoundingClientRect().top < 0) l.scrollIntoView({ block: "start" }); };
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
  pintar(); alInicio(); marcarTema();
});
todas.onclick = () => {
  if (activos.size === botones.length) { activos.clear(); activos.add("falso"); activos.add("enganoso"); } else verTodo();
  pintar(); alInicio(); marcarTema();
};
function irAlAncla() {
  const d = location.hash.length > 1 && document.getElementById(location.hash.slice(1));
  if (!d) return;
  if (d.hidden) { activos.add(d.dataset.v); pintar(); }
  else if (d.classList.contains("plegado")) { verTodo(); pintar(); }
  d.scrollIntoView();
}
document.querySelectorAll(".ver-tema").forEach(b => b.onclick = () => {
  const cap = b.closest(".capitulo");
  verTodo(); pintar(); cap.scrollIntoView(); marcarTema();
  cap.querySelector("h2").setAttribute("tabindex", "-1"); cap.querySelector("h2").focus({ preventScroll: true });
});
pintar(); irAlAncla(); marcarTema();
addEventListener("hashchange", irAlAncla);
@@PREGUNTAS@@
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
${t(".explicacion-completa") || t(".porque")}

Fuentes que cita:
${fuentes || "(ninguna)"}

Datos completos en JSON: @@BASE@@/api/v1/@@SLUG@@.json (id "@@SLUG@@-${h.id}"). Transcripción para ver el contexto: @@BASE@@/api/v1/@@SLUG@@/transcripcion.txt

Haz esto:
1. Comprueba en la transcripción que la cita es literal, que la dice el entrevistado y que el contexto no le cambia el sentido.
2. Abre cada fuente y dime si existe y si de verdad dice lo que la justificación le atribuye.
3. Busca al menos dos fuentes independientes más, mejor primarias y oficiales. No te fíes de tu memoria para hechos de 2025 y 2026: búscalo.
4. Da tu propio veredicto (verdadero, casi cierto, engañoso, falso o no verificable) y di si coincide con el publicado, en qué discrepas y con qué enlaces lo sustentas.
No inventes enlaces. Si no puedes abrir una fuente o no hay pruebas suficientes, dilo.`;
  b.textContent = "Copiado ✓"; b.classList.add("hecho");
  setTimeout(() => { b.textContent = "Copiar encargo para contrastarlo con una IA"; b.classList.remove("hecho"); }, 2200);
  copiarTexto(texto, "Encargo copiado. Pégalo en Claude, ChatGPT o la IA que uses.");
});
</script>
@@FAB@@
@@VISOR@@
</body>
</html>
"""

AFIRMACION = """<!doctype html>
<html lang="es">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
@@HEAD_MODO@@
@@CABECERA@@
<style>
:root { --serif:"Iowan Old Style","Palatino Linotype",Palatino,Georgia,serif; }
* { box-sizing:border-box; }
body { margin:0; background:var(--fondo); color:var(--tinta); font:16px/1.6 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif; -webkit-text-size-adjust:100%; overflow-wrap:break-word; }
a { color:var(--tinta); text-underline-offset:3px; }
main.ancho { max-width:760px; padding-top:4px; padding-bottom:56px; }
.migas { font-size:14px; color:var(--gris); padding-top:18px; }
.migas a { font-weight:600; color:var(--suave); }
.migas a:hover { color:var(--tinta); }
.veredicto { display:inline-block; margin:22px 0 0; padding:9px 18px 10px; font:700 clamp(22px,4vw,28px)/1 var(--serif); background:var(--tono); color:var(--sobre-tono); }
h1 { font:700 clamp(28px,4.6vw,40px)/1.14 var(--serif); letter-spacing:-0.02em; margin:16px 0 0; text-wrap:balance; }
.seccion { margin:34px 0 0; padding-top:14px; border-top:2px solid var(--tinta); }
h2 { font:700 22px/1.2 var(--serif); margin:0 0 12px; }
blockquote { margin:0; padding-left:16px; border-left:4px solid var(--tono); font:italic 21px/1.45 var(--serif); text-wrap:pretty; }
.cita-pie { margin:10px 0 0 20px; font-size:15px; color:var(--suave); }
.cita-pie a { font-weight:700; color:var(--tono); }
.resumen { margin:0 0 12px; font-size:19px; font-weight:600; line-height:1.45; }
.explicacion { margin:0; font-size:17px; }
.confianza { margin:14px 0 0; font-size:14px; color:var(--suave); }
.fuentes { margin:0; padding-left:22px; font-size:15px; }
.fuentes li { margin:6px 0; overflow-wrap:anywhere; }
.fuentes span { color:var(--gris); font-size:13px; white-space:nowrap; }
/* contexto: el mismo lenguaje visual que la transcripción (quién habla, raya vertical en lo que dice el candidato) */
.contexto .turno { margin:0 0 18px; }
.cab-turno { display:flex; align-items:center; justify-content:space-between; gap:12px; margin:0 0 6px; }
.cab-turno .minuto { font:700 13px/1 -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif; font-variant-numeric:tabular-nums; color:var(--gris); }
.cab-turno .minuto:hover { background:var(--tinta); color:var(--fondo); text-decoration:none; }
.quien { display:flex; align-items:center; gap:9px; min-width:0; font:700 13.5px/1.25 -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif; color:var(--tinta); }
.nom { display:flex; flex-wrap:wrap; align-items:baseline; gap:2px 6px; min-width:0; }
.quien small { font-size:12px; font-weight:500; color:var(--gris); }
.cara { width:30px; height:30px; flex:none; border-radius:50%; display:grid; place-items:center; object-fit:cover;
  font:700 11px/1 -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif; border:1.5px solid currentColor; }
img.cara { border:0; background:var(--claro); }
.contexto p { margin:0; font:17px/1.6 var(--serif); }
.turno[data-voz=G] p { border-left:3px solid var(--tinta); padding-left:14px; }
.turno[data-voz=J] p, .turno[data-voz=V] p, .turno[data-voz=O] p { padding-left:17px; color:var(--suave);
  font:15.5px/1.6 -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif; }
.turno:not([data-voz=G]) .quien { color:var(--suave); }
mark { background:var(--tono); color:var(--sobre-tono); padding:1px 3px; -webkit-box-decoration-break:clone; box-decoration-break:clone; }
.mas { margin:12px 0 0; font-size:15px; font-weight:600; }
.acciones { display:flex; flex-wrap:wrap; gap:10px; margin-top:34px; padding-top:18px; border-top:2px solid var(--tinta); }
.corregir p { margin:0 0 12px; max-width:62ch; }
.corregir .btn { display:inline-block; background:var(--tinta); color:var(--fondo); }
.corregir .btn:hover { background:var(--fondo); color:var(--tinta); }
.nota-corregir { font-size:13.5px; color:var(--suave); }
.btn { font:inherit; font-size:14.5px; font-weight:600; color:var(--tinta); background:var(--fondo); border:2px solid var(--tinta); padding:7px 14px; cursor:pointer; text-decoration:none; line-height:1.4; }
.btn:hover { background:var(--tinta); color:var(--fondo); }
.vecinas { display:grid; grid-template-columns:1fr 1fr; gap:12px; margin-top:30px; }
.vecina { display:flex; flex-direction:column; gap:4px; min-width:0; border:2px solid var(--tinta); padding:12px 14px; text-decoration:none; }
.vecina:hover { background:var(--resalte); }
.vecina.sig { text-align:right; }
.vecina .rot-v { font-size:12px; font-weight:700; text-transform:uppercase; letter-spacing:.08em; color:var(--gris); }
.vecina .tiempo { font-size:15px; font-weight:600; font-variant-numeric:tabular-nums; }
.vecina .tiempo b { color:var(--tono); }
.vecina small { font-size:14px; line-height:1.4; color:var(--suave); }
footer { border-top:3px solid var(--tinta); margin-top:48px; padding:24px 0 72px; font-size:14.5px; }
@media (max-width:600px) {
  main.ancho { padding-top:0; }
  blockquote { font-size:19px; }
  .cita-pie { margin-left:20px; }
  .vecinas { grid-template-columns:1fr; }
  .vecina.sig { text-align:left; } }
@@CSS_MENU@@
</style>
</head>
<body>
@@MENU@@
<main class="ancho" data-v="@@V@@">
<nav class="migas" aria-label="Ruta">@@MIGAS@@</nav>
<p class="veredicto" data-v="@@V@@">@@VEREDICTO@@</p>
<h1>@@AFIRMACION@@</h1>
<section class="seccion"><h2>Lo que dijo</h2>@@CITA@@</section>
<section class="seccion"><h2>Por qué</h2>@@POR_QUE@@</section>
@@FUENTES@@
@@CONTEXTO@@
<div class="acciones">
<a class="btn" href="@@VER_LINEA@@">Ver en la línea temporal</a>
<button class="btn" type="button" data-copiar data-enlace="@@URL_PAGINA@@">Copiar enlace</button>
</div>
<section class="seccion corregir"><h2>¿Crees que está mal?</h2>
<p>Si tienes una fuente que dice otra cosa, mándanosla y lo revisamos con el mismo criterio para todos. Solo hace falta pegar el enlace.</p>
<p><a class="btn" href="@@URL_ERROR@@">Avisar de un error</a></p>
<p class="nota-corregir">Es un formulario de esta web: no hace falta cuenta. Solo te pedimos el enlace a la fuente.</p>
</section>
<nav class="vecinas" aria-label="Afirmaciones de la misma entrevista">@@ANTERIOR@@@@SIGUIENTE@@</nav>
</main>
<footer class="pie-solo"><div class="ancho">@@PIE@@</div></footer>
@@REPRODUCTOR@@
<script>
document.querySelector("[data-copiar]").addEventListener("click", ev => copiarTexto(ev.currentTarget.dataset.enlace, "Enlace copiado."));
</script>
@@VISOR@@
</body>
</html>
"""

BUSCAR = """<!doctype html>
<html lang="es">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
@@HEAD_MODO@@
@@CABECERA@@
<style>
:root { --serif:"Iowan Old Style","Palatino Linotype",Palatino,Georgia,serif; }
* { box-sizing:border-box; }
body { margin:0; background:var(--fondo); color:var(--tinta); font:16px/1.6 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif; -webkit-text-size-adjust:100%; overflow-wrap:break-word; }
a { color:var(--tinta); }
main.ancho { padding-bottom:72px; }
main > * { max-width:900px; }
h1 { font:700 clamp(30px,5.2vw,56px)/1.05 var(--serif); letter-spacing:-0.02em; margin:clamp(28px,5vw,48px) 0 12px; text-wrap:balance; }
.entrada { font-size:17px; max-width:62ch; margin:0 0 22px; }
.nota { font-size:14.5px; color:var(--suave); }
code { font:13.5px/1.5 ui-monospace,SFMono-Regular,Menlo,monospace; background:var(--codigo); padding:1px 5px; border-radius:var(--r-mini); }
/* Campo de búsqueda grande, con la lupa dentro */
.campo label { display:block; margin:0 0 6px; font-size:12px; font-weight:700; text-transform:uppercase; letter-spacing:.09em; color:var(--gris); }
.caja { position:relative; }
.caja svg { position:absolute; left:18px; top:50%; width:24px; height:24px; margin-top:-12px; fill:none; stroke:var(--tinta); stroke-width:2.2;
  stroke-linecap:round; stroke-linejoin:round; pointer-events:none; }
.caja input { display:block; width:100%; height:64px; padding:0 18px 0 56px; font:500 clamp(18px,3.4vw,24px)/1.2 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;
  color:var(--tinta); background:var(--fondo); border:2px solid var(--tinta); border-radius:var(--r-caja); -webkit-appearance:none; appearance:none; }
.caja input::placeholder { color:var(--gris-claro); opacity:1; }
.caja input::-webkit-search-cancel-button { -webkit-appearance:none; height:20px; width:20px; margin-left:8px; cursor:pointer;
  background:var(--tinta); -webkit-mask:url('data:image/svg+xml;utf8,<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"><path d="M5 5l14 14M19 5L5 19" stroke="black" stroke-width="2.6" stroke-linecap="round"/></svg>') center/contain no-repeat;
  mask:url('data:image/svg+xml;utf8,<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"><path d="M5 5l14 14M19 5L5 19" stroke="black" stroke-width="2.6" stroke-linecap="round"/></svg>') center/contain no-repeat; }
/* Filtros: los mismos botones que los de la línea temporal (una fila por grupo, que en móvil baja de línea en vez de deslizarse) */
.filtros-b { display:grid; gap:8px; margin:20px 0 0; }
.filtros-b .fila { flex-wrap:wrap; overflow:visible; padding:0; }
.filtros-b .fila .rot { display:inline-block; min-width:76px; }
.filtros-b .fila button { min-height:30px; }
.filtros-b .fila button:has(.retrato) { padding-left:4px; }
.fila button[data-n="0"]:not([aria-pressed=true]) { opacity:.45; }
.fila button[data-n="0"]:not([aria-pressed=true]):hover { opacity:.8; }
.fila b { min-width:1.6ch; }
/* Resultados */
#resultados { margin-top:22px; }
.cuenta-b { margin:0 0 14px; padding-top:12px; border-top:3px solid var(--tinta); font-size:15px; font-weight:600; font-variant-numeric:tabular-nums; }
.cuenta-b span { font-weight:400; color:var(--suave); }
.lista-res { list-style:none; margin:0; padding:0; display:grid; gap:14px; }
.res { position:relative; border:2px solid var(--tinta); border-radius:var(--r-caja); padding:16px 18px 16px; background:var(--fondo);
  transition:background-color .15s ease-out, box-shadow .15s ease-out; }
.res[data-v=falso] { box-shadow:inset 5px 0 0 var(--tono); padding-left:23px; }
.res:hover { background:var(--resalte); }
.res:focus-within { outline:3px solid var(--tinta); outline-offset:3px; }
.res-cab { display:flex; align-items:center; gap:10px 14px; margin:0 0 12px; }
.res-cab .quien { flex:1 1 0; min-width:0; }
.res-cab .nom { display:block; font:700 clamp(19px,2.4vw,23px)/1.15 var(--serif); color:var(--tinta); letter-spacing:-.005em; text-wrap:balance; }
.res-cab .partido { display:block; margin-top:3px; font-size:12px; font-weight:600; text-transform:uppercase; letter-spacing:.08em; line-height:1.3; color:var(--gris); }
.res-cab .dato { flex:none; display:grid; justify-items:end; gap:4px; text-align:right; }
.res-cab .min { font-size:13.5px; font-variant-numeric:tabular-nums; font-weight:700; color:var(--tono); white-space:nowrap; }
.res .tema { margin:0 0 10px; font-size:12px; font-weight:600; text-transform:uppercase; letter-spacing:.08em; line-height:1.4; color:var(--gris); }
.ficha { display:inline-block; font-size:11.5px; font-weight:700; text-transform:uppercase; letter-spacing:.09em; line-height:1.3;
  border:1.5px solid var(--tono); color:var(--tono); padding:2px 9px; border-radius:var(--r-mini); white-space:nowrap; }
.res[data-v=falso] .ficha { background:var(--tono); color:var(--sobre-tono); }
.res blockquote { margin:0 0 10px; padding-left:14px; border-left:4px solid var(--tono); font:italic 18px/1.4 var(--serif); text-wrap:pretty; }
.res h3 { margin:0 0 6px; font-size:16.5px; line-height:1.4; font-weight:700; }
.res h3 a { text-decoration:none; }
.res h3 a:hover { text-decoration:underline; text-decoration-thickness:2px; }
.res h3 a::after { content:""; position:absolute; inset:0; border-radius:var(--r-caja); }   /* toda la tarjeta es el enlace */
.res h3 a:focus-visible { outline:none; }
.res p { margin:0; font-size:14.5px; line-height:1.5; color:var(--suave); }
.res .fu { margin-top:6px; font-size:13px; color:var(--gris); }
mark { background:color-mix(in srgb, var(--tono, var(--tinta)) 24%, transparent); color:inherit; box-shadow:inset 0 -2px 0 var(--tono, var(--tinta));
  padding:0 1px; border-radius:2px; -webkit-box-decoration-break:clone; box-decoration-break:clone; }
.mas-b { margin:22px 0 0; }
.btn-b { font:inherit; font-size:15px; font-weight:600; color:var(--fondo); background:var(--tinta); border:2px solid var(--tinta); border-radius:var(--r-boton);
  padding:10px 20px; min-height:44px; cursor:pointer; }
.btn-b:hover { background:var(--fondo); color:var(--tinta); }
.btn-b.claro { background:var(--fondo); color:var(--tinta); }
.btn-b.claro:hover { background:var(--tinta); color:var(--fondo); }
/* Estados vacíos */
.ejemplos { margin:6px 0 22px; }
.ejemplos .rot { display:block; margin:0 0 8px; }
.ejemplos .fila { flex-wrap:wrap; overflow:visible; padding:0; }
.ejemplos .fila button { font-size:14.5px; padding:5px 14px; min-height:36px; }
.sin { border:2px solid var(--tinta); border-radius:var(--r-caja); padding:18px 20px; }
.sin h2 { font:700 22px/1.25 var(--serif); margin:0 0 6px; }
.sin p { margin:0 0 12px; max-width:62ch; }
.sin .acc { display:flex; flex-wrap:wrap; gap:8px; margin-top:4px; }
@media (max-width:560px) {
  .res-cab { flex-wrap:wrap; } .res-cab .quien { flex-basis:calc(100% - 44px - 14px); }
  .res-cab .dato { flex:1 0 100%; display:flex; justify-content:space-between; align-items:center; text-align:left; }
  .caja input { height:56px; padding-left:50px; } .caja svg { left:15px; width:22px; height:22px; margin-top:-11px; }
  .filtros-b .fila .rot { display:block; flex:0 0 100%; min-width:0; margin-bottom:-2px; }
  .res { padding:14px 14px 14px; } .res[data-v=falso] { padding-left:19px; }
  .res blockquote { font-size:17px; } }
footer { border-top:3px solid var(--tinta); margin-top:48px; padding:24px 0 72px; font-size:14.5px; }
@@CSS_MENU@@
</style>
</head>
<body>
@@MENU@@
<main class="ancho buscador">
<h1>Buscar una afirmación</h1>
<p class="entrada">Busca entre las @@TOTAL@@ afirmaciones comprobadas: por tema, palabra, cifra o nombre. Si escribes varias palabras, tienen que salir todas. Pulsa <code>/</code> en cualquier página para venir aquí.</p>
<noscript><p class="nota">El buscador necesita JavaScript. Sin él, tienes todas las afirmaciones en <a href="/api/v1/afirmaciones.csv">CSV</a> (se abre en cualquier hoja de cálculo) y en <a href="/api/v1/afirmaciones.json">JSON</a>; la <a href="/api">API</a> explica los campos.</p></noscript>
<div id="app" hidden>
<form class="campo" id="form" role="search" action="/buscar" method="get">
<label for="q">Qué quieres buscar</label>
<div class="caja">@@ICONO_LUPA@@<input id="q" name="q" type="search" autocomplete="off" autocapitalize="off" spellcheck="false" enterkeyhint="search" placeholder="Vivienda, una cifra, un nombre…"></div>
</form>
<div class="filtros-b" id="filtros">
<div class="fila" role="group" aria-label="Filtrar por candidato"><span class="rot">Candidato</span><button type="button" data-todas="c" aria-pressed="true">Todos <b></b></button>@@BOTONES_C@@</div>
<div class="fila" role="group" aria-label="Filtrar por veredicto"><span class="rot">Veredicto</span><button type="button" data-todas="v" aria-pressed="true">Todos <b></b></button>@@BOTONES_V@@</div>
</div>
<div id="ejemplos" class="ejemplos" hidden><span class="rot">Prueba con</span><div class="fila">@@EJEMPLOS@@</div></div>
<div id="resultados" aria-live="polite">
<p class="cuenta-b" id="cuenta"></p>
<div id="sin" class="sin" hidden></div>
<ol id="lista" class="lista-res" aria-live="off"></ol>
<p class="mas-b" id="mas-p" hidden><button type="button" class="btn-b" id="mas"></button></p>
</div>
</div>
<p class="nota" id="error" hidden>No se ha podido cargar el índice de búsqueda. Puedes descargar todas las afirmaciones en <a href="/api/v1/afirmaciones.csv">CSV</a> o <a href="/api/v1/afirmaciones.json">JSON</a>.</p>
</main>
<footer class="pie-solo"><div class="ancho">@@PIE@@</div></footer>
<script>
/* ── Núcleo de la búsqueda: sin DOM, se prueba por separado ── */
// Minúsculas y sin tildes, conservando la longitud del texto para poder resaltar sobre el original
const plano = s => s.replace(/[^\\x00-\\x7f]/g, ch => { const b = ch.normalize("NFD")[0].toLowerCase(); return b.length === 1 ? b : ch; }).toLowerCase();
const esAlfa = c => !!c && /[\\p{L}\\p{N}]/u.test(c);
const esc = s => s.replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const palabras = q => [...new Set(plano(q).split(/\\s+/).map(w => w.replace(/^[^\\p{L}\\p{N}]+|[^\\p{L}\\p{N}%€$]+$/gu, "")).filter(Boolean))];
// Una palabra de 3 letras o más vale como trozo de otra (migración casa con inmigración); una más corta, solo al principio de palabra
function hallar(texto, p, desde) {
  for (let i = texto.indexOf(p, desde); i >= 0; i = texto.indexOf(p, i + 1))
    if (p.length >= 3 || !esAlfa(texto[i - 1])) return i;
  return -1;
}
const tiene = (texto, p) => hallar(texto, p, 0) >= 0;
function preparar(datos) {
  return datos.a.map(([c, v, seg, id, t, cita, af, res, fu], i) => ({
    i, c, v, seg, id, t, cita, af, res, fu,
    n: { a: plano(af), c: plano(cita), r: plano(res), t: plano(datos.t[t]), k: plano(datos.c[c][1] + " " + datos.c[c][2]), f: plano(fu.join(" | ")) } }));
}
// Coincidencia de una afirmación con las palabras: puntuación (0 si falta alguna), con más peso en la afirmación y la cita
function puntuar(d, ps) {
  let total = 0;
  for (const p of ps) {
    const n = d.n, a = tiene(n.a, p), c = tiene(n.c, p), r = tiene(n.r, p), t = tiene(n.t, p), o = tiene(n.k, p) || tiene(n.f, p);
    if (!(a || c || r || t || o)) return 0;
    total += (a ? 10 : 0) + (c ? 8 : 0) + (r ? 3 : 0) + (t ? 2 : 0) + (o ? 1 : 0);
  }
  return total;
}
function buscar(docs, q) {
  const ps = palabras(q);
  // Sin palabras salen todas, alternando candidatos (la 1.ª de cada uno, luego la 2.ª…) para no empezar por uno solo
  if (!ps.length) { const k = {}; return docs.map(d => ({ d, p: 1, r: (k[d.c] = (k[d.c] || 0) + 1) })).sort((x, y) => x.r - y.r || x.d.c - y.d.c); }
  return docs.map(d => ({ d, p: puntuar(d, ps) })).filter(x => x.p).sort((x, y) => y.p - x.p);   // sort es estable: a igualdad, orden del índice
}
// Texto escapado con <mark> en cada trozo que coincide con alguna palabra
function resaltar(texto, norm, ps) {
  const trozos = [];
  for (const p of ps) for (let i = hallar(norm, p, 0); i >= 0; i = hallar(norm, p, i + p.length)) trozos.push([i, i + p.length]);
  if (!trozos.length) return esc(texto);
  trozos.sort((x, y) => x[0] - y[0] || y[1] - x[1]);
  let sal = "", pos = 0;
  for (let [a, b] of trozos) {
    if (b <= pos) continue;
    if (a < pos) a = pos;
    sal += esc(texto.slice(pos, a)) + "<mark>" + esc(texto.slice(a, b)) + "</mark>";
    pos = b;
  }
  return sal + esc(texto.slice(pos));
}
/* ── Fin del núcleo ── */

const TAM = 20, NOMBRES = @@NOMBRES@@, CLAVES = @@CLAVES@@;
const $ = id => document.getElementById(id);
const campo = $("q"), lista = $("lista"), botonMas = $("mas");
let datos = null, docs = [], hallados = [], pintados = 0, espera = 0;
const estado = { q: "", c: new Set(), v: new Set() };

const hms = s => Math.floor(s / 3600) + ":" + String(Math.floor(s % 3600 / 60)).padStart(2, "0") + ":" + String(s % 60).padStart(2, "0");
const plural = n => n === 1 ? "1 afirmación" : n.toLocaleString("es-ES") + " afirmaciones";

function leerURL() {
  const u = new URLSearchParams(location.search);
  estado.q = (u.get("q") || "").trim();
  const conj = (clave, validos) => new Set((u.get(clave) || "").split(",").filter(x => validos.includes(x)));
  estado.c = conj("c", datos.c.map(c => c[0]));
  estado.v = conj("v", CLAVES);
  campo.value = estado.q;
}
function escribirURL(extra) {
  const u = new URLSearchParams();
  if (estado.q) u.set("q", estado.q);
  if (estado.c.size) u.set("c", [...estado.c].join(","));
  if (estado.v.size) u.set("v", [...estado.v].join(","));
  const s = u.toString();
  history.replaceState(extra || history.state, "", location.pathname + (s ? "?" + s : ""));
}
const filtrar = (x, c, v) => (!c || !estado.c.size || estado.c.has(datos.c[x.d.c][0])) && (!v || !estado.v.size || estado.v.has(CLAVES[x.d.v]));

function tarjeta(x, ps) {
  const d = x.d, cand = datos.c[d.c], v = CLAVES[d.v], enlace = "/" + cand[0] + "/" + d.id;
  const tema = datos.t[d.t];
  // Si alguna palabra solo sale en el título de una fuente, se enseña esa fuente para que se vea por qué aparece
  let fuente = "";
  const sueltas = ps.filter(p => !["a", "c", "r", "t", "k"].some(k => tiene(d.n[k], p)));
  if (sueltas.length) {
    const i = d.fu.findIndex(t => sueltas.some(p => tiene(plano(t), p)));
    if (i >= 0) fuente = '<p class="fu">Fuente: ' + resaltar(d.fu[i], plano(d.fu[i]), ps) + "</p>";
  }
  return '<li class="res" data-v="' + v + '"><article><div class="res-cab">' + cand[3] +
    '<div class="quien"><b class="nom">' + resaltar(cand[1], plano(cand[1]), ps) + '</b><span class="partido">' + resaltar(cand[2], plano(cand[2]), ps) + "</span></div>" +
    '<div class="dato"><span class="ficha">' + NOMBRES[d.v] + '</span><span class="min">' + hms(d.seg) + "</span></div></div>" +
    (tema ? '<p class="tema">' + resaltar(tema, d.n.t, ps) + "</p>" : "") +
    (d.cita ? "<blockquote>«" + resaltar(d.cita, d.n.c, ps) + "»</blockquote>" : "") +
    '<h3><a href="' + enlace + '">' + resaltar(d.af, d.n.a, ps) + "</a></h3>" +
    "<p>" + resaltar(d.res, d.n.r, ps) + "</p>" + fuente + "</article></li>";
}
function pintarMas(n) {
  const ps = palabras(estado.q), ini = pintados;
  pintados = Math.min(hallados.length, pintados + n);
  lista.insertAdjacentHTML("beforeend", hallados.slice(ini, pintados).map(x => tarjeta(x, ps)).join(""));
  const quedan = hallados.length - pintados;
  $("mas-p").hidden = !quedan;
  botonMas.textContent = "Cargar más (quedan " + quedan.toLocaleString("es-ES") + ")";
  return ini;
}
function aplicar(mantener) {
  estado.q = campo.value.trim();
  const base = buscar(docs, estado.q);
  // Los números de cada botón cuentan lo que saldría al pulsarlo, con la búsqueda y el otro filtro actuales
  document.querySelectorAll("#filtros [data-c]").forEach(b => b.dataset.n = base.filter(x => datos.c[x.d.c][0] === b.dataset.c && filtrar(x, false, true)).length);
  document.querySelectorAll("#filtros [data-v]").forEach(b => b.dataset.n = base.filter(x => CLAVES[x.d.v] === b.dataset.v && filtrar(x, true, false)).length);
  document.querySelectorAll("#filtros [data-todas]").forEach(b => b.dataset.n = base.filter(x => filtrar(x, b.dataset.todas === "v", b.dataset.todas === "c")).length);
  document.querySelectorAll("#filtros button").forEach(b => {
    b.querySelector("b").textContent = Number(b.dataset.n).toLocaleString("es-ES");
    b.setAttribute("aria-pressed", b.dataset.todas ? !estado[b.dataset.todas].size : (b.dataset.c ? estado.c.has(b.dataset.c) : estado.v.has(b.dataset.v)));
  });
  hallados = base.filter(x => filtrar(x, true, true));
  lista.innerHTML = ""; pintados = 0;
  const vacio = !estado.q && !estado.c.size && !estado.v.size;
  $("ejemplos").hidden = !vacio;
  const sin = $("sin"); sin.hidden = true;
  const cuenta = $("cuenta");
  if (vacio) {
    // Sin búsqueda ni filtros se ven todas; los filtros solo se aplican cuando la persona los elige
    cuenta.innerHTML = "Todas las " + docs.length.toLocaleString("es-ES") + " afirmaciones <span>· escribe para buscar o filtra por candidato y veredicto</span>";
    pintarMas(mantener || TAM);
  } else if (!hallados.length) {
    cuenta.textContent = "0 afirmaciones";
    $("mas-p").hidden = true;
    const sinFiltros = base.length;
    sin.hidden = false;
    sin.innerHTML = "<h2>No hay ninguna afirmación que coincida</h2>" +
      (estado.q ? "<p>No sale nada para «" + esc(estado.q) + "»" + (sinFiltros && (estado.c.size || estado.v.size) ? " con los filtros puestos" : "") + ".</p>" : "<p>No hay nada con esos filtros.</p>") +
      (palabras(estado.q).length > 1 ? "<p>Con varias palabras tienen que salir todas: prueba con menos palabras o con una más corta.</p>" : "") +
      '<div class="acc">' +
      ((estado.c.size || estado.v.size) && sinFiltros ? '<button type="button" class="btn-b" data-accion="quitar">Quitar los filtros (' + plural(sinFiltros) + ")</button>" : "") +
      (estado.q ? '<button type="button" class="btn-b claro" data-accion="borrar">Borrar la búsqueda</button>' : "") + "</div>";
  } else {
    cuenta.innerHTML = plural(hallados.length) + (estado.q ? " <span>para «" + esc(estado.q) + "»</span>" : "");
    pintarMas(mantener || TAM);
  }
  escribirURL();
}
function ponerBusqueda(texto) { campo.value = texto; clearTimeout(espera); aplicar(); campo.focus(); }

function alternar(conjunto, valor) { conjunto.has(valor) ? conjunto.delete(valor) : conjunto.add(valor); }
$("filtros").addEventListener("click", ev => {
  const b = ev.target.closest("button"); if (!b) return;
  if (b.dataset.todas) estado[b.dataset.todas].clear();
  else {
    const conj = b.dataset.c ? estado.c : estado.v, total = b.dataset.c ? datos.c.length : CLAVES.length;
    alternar(conj, b.dataset.c || b.dataset.v);
    if (conj.size === total) conj.clear();
  }
  aplicar();
});
$("ejemplos").addEventListener("click", ev => { const b = ev.target.closest("button[data-ej]"); if (b) ponerBusqueda(b.dataset.ej); });
$("sin").addEventListener("click", ev => {
  const b = ev.target.closest("button[data-accion]"); if (!b) return;
  if (b.dataset.accion === "quitar") { estado.c.clear(); estado.v.clear(); aplicar(); campo.focus(); } else ponerBusqueda("");
});
botonMas.addEventListener("click", () => {
  const ini = pintarMas(TAM);
  lista.children[ini]?.querySelector("a").focus({ preventScroll: false });
});
campo.addEventListener("input", () => { clearTimeout(espera); espera = setTimeout(() => aplicar(), 180); });
$("form").addEventListener("submit", ev => { ev.preventDefault(); clearTimeout(espera); aplicar(); });
// Al volver atrás desde una afirmación se recupera cuántas había pintadas y dónde se estaba
const guardarPosicion = () => { if (datos) try { history.replaceState({ n: pintados, y: scrollY }, "", location.href); } catch (e) {} };
lista.addEventListener("click", guardarPosicion);
addEventListener("pagehide", guardarPosicion);
if ("scrollRestoration" in history) history.scrollRestoration = "manual";

fetch("/buscar/indice.json").then(r => { if (!r.ok) throw 0; return r.json(); }).then(j => {
  datos = j; docs = preparar(j);
  document.querySelectorAll("#ejemplos [data-ej]").forEach(b => b.querySelector("b").textContent = buscar(docs, b.dataset.ej).length);
  leerURL();
  $("app").hidden = false;
  const previo = history.state && history.state.n;
  aplicar(previo > TAM ? previo : TAM);
  if (previo) { if (history.state.y) scrollTo(0, history.state.y); } else campo.focus();
}).catch(() => { $("error").hidden = false; });
</script>
</body>
</html>
"""

if __name__ == "__main__":
    main()
