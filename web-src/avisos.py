"""Página /avisar: formulario para avisar de un error sin salir de la web.

Lo envía a la función de Vercel /api/avisar (web-src/avisar.js), que lo publica como incidencia en el
repositorio. La importa build.py.
"""

PAGINA = """<!doctype html>
<html lang="es">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex">
@@HEAD_MODO@@
@@CABECERA@@
<style>
:root { --serif:"Iowan Old Style","Palatino Linotype",Palatino,Georgia,serif; }
* { box-sizing:border-box; }
body { margin:0; background:var(--fondo); color:var(--tinta); font:16px/1.6 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif; }
a { color:var(--tinta); text-underline-offset:3px; }
main.ancho { padding-bottom:72px; }
/* Página de lectura: una columna centrada, como el método o una afirmación */
.columna { max-width:780px; margin:0 auto; padding-top:clamp(28px,5vw,56px); }
h1 { font:700 clamp(30px,5.2vw,58px)/1.05 var(--serif); letter-spacing:-0.02em; margin:0 0 14px; text-wrap:balance; }
.entrada { font-size:17px; max-width:62ch; margin:0 0 28px; color:var(--suave); }
.caja { border:2px solid var(--tinta); border-radius:var(--r-caja); padding:clamp(16px,2.4vw,24px); margin:0 0 22px; }
.rot { margin:0 0 4px; font-size:12px; font-weight:700; text-transform:uppercase; letter-spacing:.08em; color:var(--gris); }
#sobre p:not(.rot) { margin:0 0 6px; font:700 20px/1.3 var(--serif); }
form { display:grid; gap:20px; }
.campo { display:grid; gap:6px; font-weight:700; }
.campo .ayuda { font-weight:400; font-size:14.5px; color:var(--suave); max-width:68ch; }
.oblig { font-size:12px; font-weight:700; text-transform:uppercase; letter-spacing:.08em; color:var(--gris); margin-left:6px; }
input, textarea { font:inherit; font-weight:400; color:var(--tinta); background:var(--fondo); width:100%; min-height:46px;
  border:2px solid var(--tinta); border-radius:var(--r-boton); padding:10px 12px; }
textarea { resize:vertical; line-height:1.5; }
input:focus-visible, textarea:focus-visible { outline:3px solid var(--tinta); outline-offset:2px; }
[aria-invalid=true] { border-color:var(--v-falso); }
.error { margin:-10px 0 0; color:var(--v-falso); font-weight:600; font-size:15px; }
.trampa { position:absolute; left:-9999px; width:1px; height:1px; overflow:hidden; }
.enviar { justify-self:start; min-height:46px; padding:0 22px; font:inherit; font-weight:700; cursor:pointer;
  background:var(--tinta); color:var(--fondo); border:2px solid var(--tinta); border-radius:var(--r-boton); }
.enviar:hover { background:var(--fondo); color:var(--tinta); }
.enviar:disabled { opacity:.6; cursor:progress; }
.privacidad { margin:0; font-size:14px; color:var(--suave); max-width:68ch; }
.hecho h2 { font:700 clamp(24px,2.4vw,28px)/1.2 var(--serif); margin:0 0 8px; }
.hecho p { margin:0 0 10px; max-width:68ch; }
@media (max-width:560px) { .enviar { justify-self:stretch; } }
@@CSS_MENU@@
</style>
</head>
<body>
@@MENU@@
<main class="ancho"><div class="columna">
<h1>Avisar de un error</h1>
<p class="entrada">¿Crees que una afirmación está mal verificada? Mándanos el enlace a una web que muestre el dato correcto. Lo revisamos con el mismo criterio para todos los partidos.</p>

<div class="caja" id="sobre" hidden><p class="rot">Afirmación</p><p id="sobre-texto"></p><a id="sobre-enlace">Ver la afirmación y su verificación</a></div>

<form id="formulario" novalidate>
<label class="campo" id="campo-afirmacion">¿Qué afirmación?
<span class="ayuda">Quién lo dijo y el minuto, por ejemplo «Sánchez, 1:02:00».</span>
<input id="afirmacion" maxlength="300" autocomplete="off" aria-describedby="error-afirmacion"></label>
<p class="error" id="error-afirmacion" hidden></p>

<label class="campo"><span>Enlace a la fuente <span class="oblig">obligatorio</span></span>
<span class="ayuda">Una o varias webs que muestren lo que de verdad pasó. Mejor de organismos oficiales (INE, BOE, ministerios…) o de medios conocidos. Sin enlace no podemos revisarlo.</span>
<textarea id="fuentes" rows="4" maxlength="3000" required placeholder="https://…" aria-describedby="error-fuentes"></textarea></label>
<p class="error" id="error-fuentes" hidden></p>

<label class="campo">¿Qué está mal?
<span class="ayuda">Opcional. Cuéntalo en una frase.</span>
<textarea id="comentario" rows="3" maxlength="2000"></textarea></label>

<div class="trampa" aria-hidden="true"><label>No rellenes este campo <input id="web" tabindex="-1" autocomplete="off"></label></div>

<button type="submit" class="enviar" id="enviar">Enviar aviso</button>
<p class="error" id="error-envio" role="alert" hidden></p>
<p class="privacidad">No hace falta cuenta. Lo que escribas se publica tal cual en el registro público de correcciones del proyecto (en GitHub), para que cualquiera pueda ver cómo se resuelve: no pongas datos personales.</p>
</form>

<div class="caja hecho" id="hecho" hidden tabindex="-1">
<h2>Gracias, aviso recibido</h2>
<p>Lo revisaremos con el mismo criterio para todos los partidos. Si la fuente lo confirma, corregiremos la afirmación y el cambio quedará registrado.</p>
<p><a id="hecho-volver" hidden>Volver a la afirmación</a></p>
</div>
</div></main>
<footer class="pie-solo"><div class="ancho">@@PIE@@</div></footer>
<script>
(() => {
  const $ = id => document.getElementById(id);
  const q = new URLSearchParams(location.search);
  const ruta = /^\\/[a-z]+\\/m\\d+(?:-\\d+)?$/.test(q.get("ruta") || "") ? q.get("ruta") : "";
  const etiqueta = (q.get("a") || "").slice(0, 300);
  if (ruta) {
    $("sobre").hidden = false;
    $("sobre-texto").textContent = etiqueta || ruta;
    $("sobre-enlace").href = ruta;
    $("campo-afirmacion").hidden = true;
    $("hecho-volver").href = ruta; $("hecho-volver").hidden = false;
  }
  const t0 = Date.now();
  const hayEnlace = t => /https?:\\/\\/[^\\s<>"'()]+\\.[^\\s<>"'()]+/i.test(t);
  const marcar = (campo, idError, mensaje) => {
    $(campo).setAttribute("aria-invalid", mensaje ? "true" : "false");
    $(idError).textContent = mensaje || ""; $(idError).hidden = !mensaje;
  };
  $("fuentes").addEventListener("input", () => { if (hayEnlace($("fuentes").value)) marcar("fuentes", "error-fuentes", ""); });
  $("formulario").addEventListener("submit", async ev => {
    ev.preventDefault();
    const afirmacion = ruta ? etiqueta : $("afirmacion").value.trim();
    const fuentes = $("fuentes").value.trim();
    let mal = null;
    if (!ruta && !afirmacion) { marcar("afirmacion", "error-afirmacion", "Indica qué afirmación crees que está mal."); mal = mal || "afirmacion"; }
    else if (!ruta) marcar("afirmacion", "error-afirmacion", "");
    if (!hayEnlace(fuentes)) {
      marcar("fuentes", "error-fuentes", "Pon al menos un enlace a una web que muestre el dato correcto. Tiene que empezar por http:// o https://.");
      mal = mal || "fuentes";
    }
    if (mal) { $(mal).focus(); return; }
    const boton = $("enviar");
    boton.disabled = true; boton.textContent = "Enviando…"; $("error-envio").hidden = true;
    try {
      const r = await fetch("/api/avisar", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ ruta, afirmacion, fuentes, comentario: $("comentario").value, web: $("web").value, t: t0 }),
      });
      const d = await r.json().catch(() => ({}));
      if (!r.ok) throw new Error(d.error || "No se ha podido enviar el aviso. Prueba de nuevo en unos minutos.");
      $("formulario").hidden = true; $("hecho").hidden = false; $("hecho").focus();
    } catch (err) {
      $("error-envio").textContent = err.message; $("error-envio").hidden = false;
      boton.disabled = false; boton.textContent = "Enviar aviso";
    }
  });
})();
</script>
</body>
</html>
"""
