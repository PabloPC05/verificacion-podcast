"""Parte pública de la API: descargas en CSV y la sección «API abierta» de la página «Verifícalo tú».

La importa build.py. Sin dependencias.
"""
import csv
import io

COLUMNAS = ["id", "entrevista", "invitado", "tema", "minuto", "segundo", "veredicto", "confianza",
            "cita", "afirmacion", "resumen", "explicacion", "fuentes", "video_url", "web_url"]


def _fila(a):
    fila = {k: a.get(k, "") for k in COLUMNAS}
    fila["fuentes"] = " | ".join(f["url"] for f in a.get("fuentes", []))
    return fila


def escribir_csv(ruta, afirmaciones):
    """CSV en UTF-8 con BOM (para que Excel muestre bien las tildes), una fila por afirmación."""
    ruta.parent.mkdir(parents=True, exist_ok=True)
    salida = io.StringIO()
    w = csv.DictWriter(salida, fieldnames=COLUMNAS, lineterminator="\n")
    w.writeheader()
    for a in afirmaciones:
        w.writerow(_fila(a))
    ruta.write_text(salida.getvalue(), encoding="utf-8-sig")


SECCION_API = """<h2 id="api">API abierta</h2>
<p>Todos los datos de la web están en una API pública de solo lectura, en JSON y CSV, sin registro ni clave y con CORS abierto. Se puede consultar desde el navegador, una hoja de cálculo, la terminal o cualquier programa.</p>

<div class="tabla-api"><table>
<thead><tr><th>Recurso</th><th>Dirección</th></tr></thead>
<tbody>
<tr><td>Entrevistas, recuentos por veredicto y temas</td><td><a href="/api/v1/entrevistas.json">/api/v1/entrevistas.json</a></td></tr>
<tr><td>Todas las afirmaciones</td><td><a href="/api/v1/afirmaciones.json">/api/v1/afirmaciones.json</a> · <a href="/api/v1/afirmaciones.csv">.csv</a></td></tr>
<tr><td>Afirmaciones de una entrevista</td><td><a href="/api/v1/@@EJ@@.json">/api/v1/{entrevista}.json</a> · <a href="/api/v1/@@EJ@@.csv">.csv</a></td></tr>
<tr><td>Transcripción con tiempos</td><td><a href="/api/v1/@@EJ@@/transcripcion.json">/api/v1/{entrevista}/transcripcion.json</a> · <a href="/api/v1/@@EJ@@/transcripcion.txt">.txt</a></td></tr>
<tr><td>Referencia completa (cada ruta y cada campo) y prompt para agentes de IA</td><td><a href="/api">/api</a></td></tr>
<tr><td>Especificación OpenAPI 3.1</td><td><a href="/api/v1/openapi.json">/api/v1/openapi.json</a></td></tr>
</tbody></table></div>
<p class="nota">Base: <code>@@BASE@@/api/v1</code>. Entrevistas disponibles: @@SLUGS@@. Descripción de cada campo en la <a href="/api">referencia completa de la API</a>.</p>

<h3 class="sub">Pruébala</h3>
<div class="explorador">
<div class="opciones">
<label>Entrevista<select id="api-cual">@@OPCIONES@@<option value="">Todas</option></select></label>
<label>Veredicto<select id="api-ver">
<option value="">Todos</option><option value="falso">Falso</option><option value="enganoso">Engañoso</option>
<option value="mayormente_verdadero">Casi cierto</option><option value="verdadero">Verdadero</option><option value="no_verificable">No verificable</option>
</select></label>
<button id="api-ir" type="button">Consultar</button>
</div>
<p class="peticion"><span>GET</span> <a id="api-url" target="_blank" rel="noopener noreferrer"></a></p>
<p class="nota" id="api-estado"></p>
<div class="tabla-api" id="api-res"></div>
<p class="botones"><a id="api-json" target="_blank" rel="noopener noreferrer">Ver JSON completo</a><a id="api-csv">Descargar CSV</a></p>
</div>

<h3 class="sub">Ejemplos</h3>
<p><b>Hoja de cálculo.</b> En Google Sheets, pega esto en una celda para cargar todas las afirmaciones:</p>
<pre>=IMPORTDATA("@@BASE@@/api/v1/afirmaciones.csv")</pre>
<p>En Excel: <i>Datos → Obtener datos → Desde la web</i> y pega la dirección del CSV.</p>
<p><b>Terminal.</b> Las afirmaciones falsas de una entrevista, con sus fuentes:</p>
<pre>curl -s @@BASE@@/api/v1/@@EJ@@.json \\
  | jq '.afirmaciones[] | select(.veredicto == "falso") | {minuto, cita, resumen, fuentes}'</pre>
<p><b>Python.</b></p>
<pre>import json, urllib.request

url = "@@BASE@@/api/v1/afirmaciones.json"
datos = json.load(urllib.request.urlopen(url))
for a in datos["afirmaciones"]:
    if a["veredicto"] in ("falso", "enganoso"):
        print(a["invitado"], a["minuto"], a["veredicto"], a["afirmacion"])</pre>
<p><b>JavaScript.</b></p>
<pre>const r = await fetch("@@BASE@@/api/v1/entrevistas.json");
const { entrevistas } = await r.json();
entrevistas.forEach(e =&gt; console.log(e.invitado, e.por_veredicto));</pre>
"""

JS_API = """<script>
(() => {
  const NOMBRE = { falso: "Falso", enganoso: "Engañoso", mayormente_verdadero: "Casi cierto", verdadero: "Verdadero", no_verificable: "No verificable" };
  const B = "@@BASE@@";
  const $ = id => document.getElementById(id);
  const esc = t => String(t ?? "").replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
  function ruta() { const s = $("api-cual").value; return "/api/v1/" + (s || "afirmaciones"); }
  function pintarUrl() {
    const r = ruta();
    $("api-url").textContent = B + r + ".json";
    $("api-url").href = r + ".json";
    $("api-json").href = r + ".json";
    $("api-csv").href = r + ".csv";
    $("api-csv").setAttribute("download", (($("api-cual").value) || "afirmaciones") + ".csv");
  }
  async function consultar() {
    pintarUrl();
    const ver = $("api-ver").value;
    $("api-estado").textContent = "Consultando…";
    $("api-res").innerHTML = "";
    try {
      const datos = await (await fetch(ruta() + ".json")).json();
      const lista = datos.afirmaciones.filter(a => !ver || a.veredicto === ver);
      $("api-estado").textContent = lista.length + " de " + datos.afirmaciones.length + " afirmaciones"
        + (ver ? " (filtradas por veredicto = \\"" + ver + "\\")" : "") + ". Se muestran las 25 primeras.";
      $("api-res").innerHTML = "<table><thead><tr><th>Invitado</th><th>Minuto</th><th>Veredicto</th><th>Afirmación</th><th>Fuentes</th></tr></thead><tbody>"
        + lista.slice(0, 25).map(a => "<tr><td>" + esc(a.invitado) + "</td><td><a href=\\"" + esc(a.web_url) + "\\">" + esc(a.minuto)
          + "</a></td><td data-v=\\"" + esc(a.veredicto) + "\\"><b>" + esc(NOMBRE[a.veredicto] || a.veredicto) + "</b></td><td>" + esc(a.afirmacion)
          + "</td><td>" + a.fuentes.length + "</td></tr>").join("") + "</tbody></table>";
    } catch (err) {
      $("api-estado").textContent = "No se ha podido consultar la API: " + err.message;
    }
  }
  $("api-cual").onchange = pintarUrl;
  $("api-ir").onclick = consultar;
  pintarUrl();
})();
</script>"""

CSS_API = """
h3.sub { font-size:17px; margin:26px 0 8px; }
.tabla-api { overflow-x:auto; margin:0 0 10px; }
.tabla-api table { border-collapse:collapse; width:100%; font-size:14.5px; min-width:560px; }
.tabla-api th, .tabla-api td { text-align:left; padding:7px 10px; border-bottom:1px solid var(--tinta); vertical-align:top; }
.tabla-api th { font-size:11px; text-transform:uppercase; letter-spacing:.08em; }
.tabla-api td a { overflow-wrap:anywhere; }
.explorador { border:2px solid var(--tinta); padding:14px 16px; }
.explorador .opciones { margin-top:0; align-items:center; }
#api-ir { font:inherit; font-size:14px; font-weight:600; background:var(--tinta); color:var(--fondo); border:2px solid var(--tinta); padding:5px 14px; cursor:pointer; }
.peticion { font:13.5px/1.5 ui-monospace,SFMono-Regular,Menlo,monospace; overflow-wrap:anywhere; margin:4px 0; }
.peticion span { font-weight:700; margin-right:4px; }
.explorador .botones { margin:10px 0 0; }
.explorador .tabla-api td { font-size:13.5px; }
#api-res td[data-v] { color:var(--tono, inherit); white-space:nowrap; }
"""
