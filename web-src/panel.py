"""Estadísticas de visitas: el script de seguimiento de Umami y el panel privado (/panel).

La importa build.py. El panel es estático; los datos los sirve web-src/estadisticas.js
(función de Vercel en /api/estadisticas), que guarda la clave de Umami y pide contraseña.
"""
from urllib.parse import urlparse

# Además de las visitas (que Umami cuenta solo), cada clic en un enlace se registra como evento:
#   descarga        ficheros .csv / .json o enlaces con atributo download
#   enlace-externo  cualquier enlace a otro dominio (vídeos, fuentes, GitHub…)
#   enlace-interno  enlaces dentro de la web, con la página de origen
# Todos llevan la propiedad «url», que es la que agrupa el panel.
_CLICS = """<script>
document.addEventListener("click", function (ev) {
  var a = ev.target.closest && ev.target.closest("a[href]");
  if (!a || !window.umami) return;
  try {
    var u = new URL(a.href, location.href), desde = location.pathname;
    if (u.protocol !== "http:" && u.protocol !== "https:") return;
    if (a.hasAttribute("download") || /\\.(csv|json)$/i.test(u.pathname))
      umami.track("descarga", { url: u.pathname, desde: desde });
    else if (u.host !== location.host)
      umami.track("enlace-externo", { url: (u.host + u.pathname + u.search).slice(0, 480), dominio: u.host, desde: desde });
    else if (u.pathname !== desde)
      umami.track("enlace-interno", { url: u.pathname, desde: desde });
  } catch (e) {}
}, true);
</script>"""


def seguimiento(umami_id, base):
    """Etiquetas para el <head>. Solo cuenta en el dominio de producción, no en local ni en previsualizaciones."""
    if not umami_id:
        return ""
    dominio = urlparse(base).hostname
    return (f'\n<script defer src="https://cloud.umami.is/script.js" data-website-id="{umami_id}" '
            f'data-domains="{dominio}"></script>\n' + _CLICS)


PAGINA = """<!doctype html>
<html lang="es">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
@@HEAD_MODO@@
<meta name="robots" content="noindex, nofollow">
<title>Panel de visitas</title>
<style>
@@CSS_MENU@@
:root { --serif:"Iowan Old Style","Palatino Linotype",Palatino,Georgia,serif; }
* { box-sizing:border-box; }
body { margin:0; background:var(--fondo); color:var(--tinta); font:16px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif; }
a { color:var(--tinta); }
.ancho { max-width:1120px; margin:0 auto; padding:0 16px; }
.barra { position:sticky; top:0; z-index:10; background:var(--fondo); border-bottom:2px solid var(--tinta); }
.barra .ancho { display:flex; flex-wrap:wrap; align-items:center; gap:8px 20px; padding-top:10px; padding-bottom:10px; }
.barra h1 { font:700 19px/1.2 var(--serif); margin:0; }
.barra .fila { margin-left:auto; }
.barra .salir { font:inherit; font-size:13px; font-weight:600; background:none; border:0; padding:0; color:var(--gris); cursor:pointer; text-decoration:underline; }
.estado { font-size:13px; color:var(--gris); }
main { padding:24px 0 64px; }
form.entrar { max-width:380px; margin:12vh auto 0; border:2px solid var(--tinta); padding:24px; }
form.entrar h1 { font:700 26px/1.2 var(--serif); margin:0 0 6px; }
form.entrar p { margin:0 0 16px; font-size:14.5px; color:var(--suave); }
form.entrar input { width:100%; font:inherit; padding:9px 11px; border:1.5px solid var(--tinta); background:var(--fondo); color:var(--tinta); margin-bottom:12px; }
form.entrar button { font:inherit; font-weight:700; padding:9px 16px; background:var(--tinta); color:var(--fondo); border:0; cursor:pointer; width:100%; }
.error { color:var(--v-falso); font-weight:600; font-size:14px; }
.kpis { display:grid; grid-template-columns:repeat(auto-fit,minmax(150px,1fr)); border-top:2px solid var(--tinta); border-left:1px solid var(--tinta); margin-bottom:28px; }
.kpi { border-right:1px solid var(--tinta); border-bottom:1px solid var(--tinta); padding:14px 16px; }
.kpi .rot { display:block; margin-bottom:4px; }
.kpi b { font:700 30px/1.1 var(--serif); font-variant-numeric:tabular-nums; display:block; }
.kpi small { font-size:12.5px; color:var(--gris); }
.kpi small.sube { color:var(--v-verdadero); } .kpi small.baja { color:var(--v-falso); }
.kpi.vivo b::before { content:""; display:inline-block; width:9px; height:9px; border-radius:50%; background:var(--v-verdadero); margin:0 8px 5px 0; vertical-align:middle; }
section.bloque { margin-bottom:28px; }
section.bloque h2 { font:700 20px/1.2 var(--serif); margin:0 0 8px; padding-bottom:6px; border-bottom:2px solid var(--tinta); display:flex; justify-content:space-between; align-items:baseline; gap:12px; }
section.bloque h2 small { font:500 12.5px/1 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif; color:var(--gris); }
.grafica svg { width:100%; height:auto; display:block; overflow:visible; }
.grafica .barra-v { fill:var(--tinta); } .grafica .barra-v:hover { fill:var(--v-enganoso); }
.grafica .linea { fill:none; stroke:var(--v-falso); stroke-width:2; }
.grafica text { fill:var(--gris); font-size:11px; font-variant-numeric:tabular-nums; }
.grafica .eje { stroke:var(--claro); }
.leyenda-g { display:flex; gap:18px; font-size:12.5px; color:var(--suave); margin-top:6px; }
.leyenda-g i { display:inline-block; width:10px; height:10px; margin-right:6px; vertical-align:-1px; }
.rejilla { display:grid; grid-template-columns:repeat(auto-fit,minmax(min(100%,340px),1fr)); gap:0 32px; }
table { width:100%; border-collapse:collapse; font-size:14px; }
td { padding:6px 0; border-bottom:1px solid var(--claro); vertical-align:top; }
td.n { text-align:right; font-variant-numeric:tabular-nums; font-weight:700; width:64px; padding-left:12px; }
td .t { display:block; overflow-wrap:anywhere; }
td .t a { text-decoration:none; } td .t a:hover { text-decoration:underline; }
td .p { display:block; height:4px; background:var(--tinta); margin-top:4px; min-width:2px; opacity:.85; }
.vacio { font-size:14px; color:var(--gris); margin:6px 0 0; }
.mas { font:inherit; font-size:13px; font-weight:600; background:none; border:0; padding:8px 0 0; cursor:pointer; color:var(--tinta); text-decoration:underline; }
@media (max-width:560px) { .barra .fila { margin-left:0; } .kpi b { font-size:24px; } }
</style>
</head>
<body>
<header class="barra"><div class="ancho">
  <h1>Panel de visitas</h1>
  <span class="estado" id="estado"></span>
  <div class="fila" id="periodos" hidden>
    <button data-dias="1" aria-pressed="false">24 h</button>
    <button data-dias="7" aria-pressed="true">7 días</button>
    <button data-dias="30" aria-pressed="false">30 días</button>
    <button data-dias="90" aria-pressed="false">90 días</button>
    <button data-dias="365" aria-pressed="false">1 año</button>
  </div>
  <button class="salir" id="salir" hidden>Salir</button>
</div></header>
<main class="ancho">
<form class="entrar" id="entrar" hidden>
  <h1>Panel de visitas</h1>
  <p>Estadísticas privadas de la web. Escribe la contraseña del panel.</p>
  <input type="password" id="clave" autocomplete="current-password" aria-label="Contraseña" required>
  <p class="error" id="fallo" hidden></p>
  <button>Entrar</button>
</form>
<div id="datos" hidden>
  <div class="kpis" id="kpis"></div>
  <section class="bloque grafica"><h2>Evolución <small id="unidad"></small></h2><div id="serie"></div>
    <div class="leyenda-g"><span><i style="background:var(--tinta)"></i>Páginas vistas</span><span><i style="background:var(--v-falso)"></i>Visitantes</span></div></section>
  <div class="rejilla">
    <section class="bloque"><h2>Páginas más vistas <small>vistas</small></h2><div id="paginas"></div></section>
    <section class="bloque"><h2>De dónde llegan <small>visitantes</small></h2><div id="referentes"></div></section>
    <section class="bloque"><h2>Enlaces externos clicados <small>clics</small></h2><div id="externos"></div></section>
    <section class="bloque"><h2>Descargas <small>clics</small></h2><div id="descargas"></div></section>
    <section class="bloque"><h2>Clics por tipo <small>eventos</small></h2><div id="eventos"></div></section>
    <section class="bloque"><h2>Navegación interna <small>clics</small></h2><div id="internos"></div></section>
    <section class="bloque"><h2>Países <small>visitantes</small></h2><div id="paises"></div></section>
    <section class="bloque"><h2>Dispositivos y navegadores <small>visitantes</small></h2><div id="dispositivos"></div><div id="navegadores"></div></section>
  </div>
</div>
</main>
<script>
const $ = (id) => document.getElementById(id);
const fmt = new Intl.NumberFormat("es-ES");
const paisNombre = (() => { try { const d = new Intl.DisplayNames(["es"], { type: "region" }); return (c) => d.of(c) || c; } catch (e) { return (c) => c; } })();
const NOMBRES_EVENTO = { "enlace-externo": "Enlace a otra web", "descarga": "Descarga de datos", "enlace-interno": "Enlace dentro de la web" };
const DISPOSITIVO = { desktop: "Ordenador", laptop: "Portátil", mobile: "Móvil", tablet: "Tableta" };
let clave = "", dias = 7;
try { clave = sessionStorage.getItem("panel-clave") || ""; dias = Number(sessionStorage.getItem("panel-dias")) || 7; } catch (e) {}
const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[c]);

function mostrarEntrada(error) {
  $("datos").hidden = true; $("periodos").hidden = true; $("salir").hidden = true; $("entrar").hidden = false;
  $("fallo").hidden = !error; $("fallo").textContent = error || ""; $("estado").textContent = "";
  $("clave").focus();
}

async function cargar() {
  $("estado").textContent = "Cargando…";
  let r;
  try { r = await fetch("/api/estadisticas?dias=" + dias, { headers: { authorization: "Bearer " + clave } }); }
  catch (e) { $("estado").textContent = "No se pudo conectar."; return; }
  const d = await r.json().catch(() => ({}));
  if (r.status === 401) { try { sessionStorage.removeItem("panel-clave"); } catch (e) {} return mostrarEntrada(clave ? d.error : ""); }
  if (!r.ok) { $("entrar").hidden = true; $("estado").textContent = d.error || "Error " + r.status; return; }
  $("entrar").hidden = true; $("datos").hidden = false; $("periodos").hidden = false; $("salir").hidden = false;
  pintar(d);
  $("estado").textContent = "Actualizado " + new Date().toLocaleTimeString("es-ES", { hour: "2-digit", minute: "2-digit" });
}

// Umami ha devuelto las cifras en dos formatos: {pageviews:{value,prev}} y {pageviews:n, comparison:{pageviews:n}}.
function cifra(res, k) {
  const v = res?.[k];
  if (v && typeof v === "object") return { ahora: v.value ?? 0, antes: v.prev };
  return { ahora: v ?? 0, antes: res?.comparison?.[k] };
}
function variacion(ahora, antes, alReves) {
  if (antes == null || !isFinite(antes) || antes === 0) return "<small>&nbsp;</small>";
  const p = Math.round(((ahora - antes) / antes) * 100);
  const bien = alReves ? p < 0 : p > 0;
  return `<small class="${p === 0 ? "" : bien ? "sube" : "baja"}">${p > 0 ? "+" : ""}${p} % vs. periodo anterior</small>`;
}
function duracion(s) {
  s = Math.round(s); if (!isFinite(s) || s <= 0) return "0 s";
  const m = Math.floor(s / 60); return m ? `${m} min ${s % 60} s` : `${s} s`;
}

function pintar(d) {
  const res = d.resumen && !d.resumen.error ? d.resumen : null;
  const vis = cifra(res, "visitors"), vs = cifra(res, "visits"), pv = cifra(res, "pageviews"), bo = cifra(res, "bounces"), tt = cifra(res, "totaltime");
  const activos = d.activos?.error ? null : (d.activos?.visitors ?? d.activos?.x ?? (typeof d.activos === "number" ? d.activos : null));
  const pct = (a, b) => (b ? Math.round((a / b) * 100) : 0);
  const kpis = res ? [
    ["Visitantes", fmt.format(vis.ahora), variacion(vis.ahora, vis.antes)],
    ["Visitas", fmt.format(vs.ahora), variacion(vs.ahora, vs.antes)],
    ["Páginas vistas", fmt.format(pv.ahora), variacion(pv.ahora, pv.antes)],
    ["Páginas por visita", vs.ahora ? (pv.ahora / vs.ahora).toFixed(1).replace(".", ",") : "0", "<small>&nbsp;</small>"],
    ["Rebote", pct(bo.ahora, vs.ahora) + " %", "<small>visitas de una sola página</small>"],
    ["Tiempo por visita", duracion(vs.ahora ? tt.ahora / vs.ahora : 0), "<small>&nbsp;</small>"],
  ] : [["Resumen", "—", `<small>${esc(d.resumen?.error || "sin datos")}</small>`]];
  $("kpis").innerHTML = (activos != null ? `<div class="kpi vivo"><span class="rot">Ahora mismo</span><b>${fmt.format(activos)}</b><small>visitantes en los últimos 5 min</small></div>` : "")
    + kpis.map(([t, v, s]) => `<div class="kpi"><span class="rot">${t}</span><b>${v}</b>${s}</div>`).join("");
  $("unidad").textContent = { hour: "por hora", day: "por día", month: "por mes" }[d.unidad] || "";
  grafica(d.serie, d.unidad);

  const enlaceWeb = (p) => `<a href="${esc(p)}" target="_blank" rel="noopener">${esc(p)}</a>`;
  tabla("paginas", d.paginas, (k) => enlaceWeb(k));
  tabla("referentes", d.referentes, (k) => k ? esc(k) : "Directo o sin referente");
  tabla("externos", d.externos, (k) => `<a href="https://${esc(k)}" target="_blank" rel="noopener noreferrer">${esc(k)}</a>`);
  tabla("descargas", d.descargas, (k) => enlaceWeb(k));
  tabla("eventos", d.eventos, (k) => esc(NOMBRES_EVENTO[k] || k));
  tabla("internos", d.internos, (k) => enlaceWeb(k));
  tabla("paises", d.paises, (k) => esc(k ? paisNombre(k) : "Desconocido"));
  tabla("dispositivos", d.dispositivos, (k) => esc(DISPOSITIVO[k] || k || "Desconocido"));
  tabla("navegadores", d.navegadores, (k) => esc(k || "Desconocido"));
}

// Acepta las dos formas de Umami: métricas [{x, y}] y valores de evento [{value, total}].
function filas(lista) {
  if (!Array.isArray(lista)) return null;
  return lista.map((f) => ({ k: f.x ?? f.value ?? "", n: Number(f.y ?? f.total ?? 0) })).filter((f) => f.n > 0).sort((a, b) => b.n - a.n);
}
function tabla(id, lista, etiqueta, max = 10) {
  const el = $(id), datos = filas(lista);
  if (!datos) { el.innerHTML = `<p class="vacio">No disponible${lista?.error ? " (" + esc(lista.error) + ")" : ""}.</p>`; return; }
  if (!datos.length) { el.innerHTML = '<p class="vacio">Sin datos en este periodo.</p>'; return; }
  const tope = datos[0].n;
  const pinta = (n) => `<table>${datos.slice(0, n).map((f) =>
    `<tr><td><span class="t">${etiqueta(f.k)}</span><span class="p" style="width:${(f.n / tope) * 100}%"></span></td><td class="n">${fmt.format(f.n)}</td></tr>`).join("")}</table>`
    + (datos.length > n ? `<button class="mas">Ver las ${datos.length}</button>` : "");
  el.innerHTML = pinta(max);
  const boton = el.querySelector(".mas");
  if (boton) boton.onclick = () => { el.innerHTML = pinta(datos.length); };
}

function grafica(serie, unidad) {
  const el = $("serie");
  const pv = serie?.pageviews, se = serie?.sessions;
  if (!Array.isArray(pv) || !pv.length) { el.innerHTML = `<p class="vacio">${serie?.error ? "No disponible (" + esc(serie.error) + ")." : "Sin datos en este periodo."}</p>`; return; }
  const W = 1000, H = 240, M = { a: 10, d: 10, i: 44, b: 26 };
  const ancho = W - M.i - M.d, alto = H - M.a - M.b, n = pv.length;
  const visit = new Map((se || []).map((p) => [p.x, p.y]));
  const tope = Math.max(1, ...pv.map((p) => p.y), ...(se || []).map((p) => p.y));
  const paso = ancho / n, hueco = Math.min(6, paso * 0.25);
  const y = (v) => M.a + alto - (v / tope) * alto;
  const fecha = (x) => { const f = new Date(String(x).replace(" ", "T"));
    if (isNaN(f)) return String(x);
    return unidad === "hour" ? f.toLocaleTimeString("es-ES", { hour: "2-digit", minute: "2-digit" })
      : unidad === "month" ? f.toLocaleDateString("es-ES", { month: "short", year: "2-digit" })
      : f.toLocaleDateString("es-ES", { day: "numeric", month: "short" }); };
  const marcas = [0, 0.5, 1].map((t) => Math.round(tope * t));
  let svg = `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Páginas vistas y visitantes por periodo">`;
  svg += marcas.map((m) => `<line class="eje" x1="${M.i}" x2="${W - M.d}" y1="${y(m)}" y2="${y(m)}"/><text x="${M.i - 8}" y="${y(m) + 4}" text-anchor="end">${fmt.format(m)}</text>`).join("");
  svg += pv.map((p, i) => { const h = (p.y / tope) * alto;
    return `<rect class="barra-v" x="${M.i + i * paso + hueco / 2}" y="${M.a + alto - h}" width="${Math.max(1, paso - hueco)}" height="${h}"><title>${fecha(p.x)}: ${fmt.format(p.y)} páginas vistas, ${fmt.format(visit.get(p.x) ?? 0)} visitantes</title></rect>`; }).join("");
  if (se?.length) svg += `<polyline class="linea" points="${pv.map((p, i) => `${M.i + i * paso + paso / 2},${y(visit.get(p.x) ?? 0)}`).join(" ")}"/>`;
  const cada = Math.max(1, Math.ceil(n / 8));
  svg += pv.map((p, i) => i % cada ? "" : `<text x="${M.i + i * paso + paso / 2}" y="${H - 6}" text-anchor="middle">${fecha(p.x)}</text>`).join("");
  el.innerHTML = svg + "</svg>";
}

$("entrar").onsubmit = (ev) => {
  ev.preventDefault(); clave = $("clave").value;
  try { sessionStorage.setItem("panel-clave", clave); } catch (e) {}
  cargar();
};
$("salir").onclick = () => { clave = ""; try { sessionStorage.removeItem("panel-clave"); } catch (e) {} $("clave").value = ""; mostrarEntrada(); };
document.querySelectorAll("#periodos button").forEach((b) => {
  b.setAttribute("aria-pressed", String(Number(b.dataset.dias) === dias));
  b.onclick = () => {
    dias = Number(b.dataset.dias);
    try { sessionStorage.setItem("panel-dias", dias); } catch (e) {}
    document.querySelectorAll("#periodos button").forEach((o) => o.setAttribute("aria-pressed", String(o === b)));
    cargar();
  };
});
if (clave) cargar(); else mostrarEntrada();
setInterval(() => { if (clave && !document.hidden && !$("datos").hidden) cargar(); }, 5 * 60e3);
</script>
</body>
</html>
"""
