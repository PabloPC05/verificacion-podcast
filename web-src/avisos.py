"""Formularios de la web que no salen de ella: /avisar (un error en una afirmación verificada) y /proponer (algo que
se dijo y que habría que verificar). Los dos envían a la función de Vercel /api/avisar (web-src/avisar.js), que los
publica como incidencias en el repositorio. En los dos, el enlace a una fuente de contraste es obligatorio.
La importa build.py.
"""

ESTILO = """:root { --serif:"Iowan Old Style","Palatino Linotype",Palatino,Georgia,serif; }
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
.otro { margin:-12px 0 28px; font-size:15px; max-width:68ch; }
select { font:inherit; font-weight:400; color:var(--tinta); background:var(--fondo); width:100%; min-height:46px; border:2px solid var(--tinta); border-radius:var(--r-boton); padding:8px 12px; }
.dos { display:grid; grid-template-columns:repeat(auto-fit,minmax(min(100%,240px),1fr)); gap:20px; }
.dos > * { min-width:0; }
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
@@ESTILO_FORM@@
@@CSS_MENU@@
</style>
</head>
<body>
@@MENU@@
<main class="ancho"><div class="columna">
<h1>Avisar de un error</h1>
<p class="entrada">¿Crees que una afirmación está mal verificada? Mándanos el enlace a una web que muestre el dato correcto. Lo revisamos con el mismo criterio para todos los partidos.</p>
<p class="otro">¿Lo que quieres es que verifiquemos algo que todavía no está? <a href="/proponer">Propón un hecho para verificar</a>.</p>

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

PROPONER = """<!doctype html>
<html lang="es">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex">
@@HEAD_MODO@@
@@CABECERA@@
<style>
@@ESTILO_FORM@@
@@CSS_MENU@@
</style>
</head>
<body>
@@MENU@@
<main class="ancho"><div class="columna">
<h1>Proponer un hecho para verificar</h1>
<p class="entrada">¿Alguien dijo en una de las entrevistas algo que no hemos comprobado? Cuéntanos qué se dijo y pon el enlace a una web que sirva para contrastarlo. Lo revisaremos con el mismo método y la misma vara de medir para todos.</p>
<p class="otro">Si ya está verificado y crees que el veredicto es erróneo, <a href="/avisar">avisa de un error</a>.</p>

<form id="formulario" novalidate>
<div class="dos">
<label class="campo">¿De qué entrevista?
<select id="slug" aria-describedby="error-slug"><option value="">Elige una</option>@@OPCIONES@@</select></label>
<label class="campo">Minuto
<span class="ayuda">Opcional, si lo sabes. Por ejemplo, 1:02:00.</span>
<input id="minuto" maxlength="8" inputmode="numeric" placeholder="1:02:00" autocomplete="off" aria-describedby="error-minuto"></label>
</div>
<p class="error" id="error-slug" hidden></p>
<p class="error" id="error-minuto" hidden></p>

<label class="campo">¿Qué se dijo?
<span class="ayuda">Copia la frase o resúmela con tus palabras.</span>
<textarea id="cita" rows="3" maxlength="600" aria-describedby="error-cita"></textarea></label>
<p class="error" id="error-cita" hidden></p>

<label class="campo"><span>Enlace para contrastarlo <span class="oblig">obligatorio</span></span>
<span class="ayuda">Una o varias webs con datos sobre lo que se dijo. Mejor de organismos oficiales (INE, BOE, ministerios…) o de medios conocidos. Sin enlace no podemos revisarlo.</span>
<textarea id="fuentes" rows="4" maxlength="3000" placeholder="https://…" aria-describedby="error-fuentes"></textarea></label>
<p class="error" id="error-fuentes" hidden></p>

<label class="campo">¿Por qué habría que verificarlo?
<span class="ayuda">Opcional. En una frase.</span>
<textarea id="comentario" rows="2" maxlength="2000"></textarea></label>

<div class="trampa" aria-hidden="true"><label>No rellenes este campo <input id="web" tabindex="-1" autocomplete="off"></label></div>

<button type="submit" class="enviar" id="enviar">Enviar propuesta</button>
<p class="error" id="error-envio" role="alert" hidden></p>
<p class="privacidad">No hace falta cuenta. Lo que escribas se publica tal cual en el registro público del proyecto (en GitHub), para que cualquiera pueda ver cómo se resuelve: no pongas datos personales.</p>
</form>

<div class="caja hecho" id="hecho" hidden tabindex="-1">
<h2>Gracias, propuesta recibida</h2>
<p>La revisaremos y, si es un dato que se puede comprobar, la verificaremos con el mismo método que el resto. Si sale, aparecerá en la línea temporal de la entrevista.</p>
<p><a href="/proponer">Proponer otro hecho</a></p>
</div>
</div></main>
<footer class="pie-solo"><div class="ancho">@@PIE@@</div></footer>
<script>
(() => {
  const $ = id => document.getElementById(id);
  const q = new URLSearchParams(location.search);
  const hms = s => { s = Math.max(0, Math.floor(s)); const h = Math.floor(s / 3600), m = Math.floor(s % 3600 / 60), x = s % 60;
    return (h ? h + ":" + String(m).padStart(2, "0") : m) + ":" + String(x).padStart(2, "0"); };
  if (q.get("e") && [...$("slug").options].some(o => o.value === q.get("e"))) $("slug").value = q.get("e");
  if (/^\\d+$/.test(q.get("t") || "")) $("minuto").value = hms(+q.get("t"));
  if (q.get("cita")) $("cita").value = q.get("cita").slice(0, 600);
  const t0 = Date.now();
  const hayEnlace = t => /https?:\\/\\/[^\\s<>"'()]+\\.[^\\s<>"'()]+/i.test(t);
  const MINUTO = /^(?:\\d{1,2}:)?[0-5]?\\d:[0-5]\\d$/;
  const marcar = (campo, mensaje) => {
    $(campo).setAttribute("aria-invalid", mensaje ? "true" : "false");
    $("error-" + campo).textContent = mensaje || ""; $("error-" + campo).hidden = !mensaje;
  };
  $("fuentes").addEventListener("input", () => { if (hayEnlace($("fuentes").value)) marcar("fuentes", ""); });
  $("formulario").addEventListener("submit", async ev => {
    ev.preventDefault();
    const datos = { slug: $("slug").value, minuto: $("minuto").value.trim(), cita: $("cita").value.trim(), fuentes: $("fuentes").value.trim() };
    const errores = [
      ["slug", datos.slug ? "" : "Elige de qué entrevista es."],
      ["minuto", !datos.minuto || MINUTO.test(datos.minuto) ? "" : "Escribe el minuto como 1:02:00 o 45:10, o déjalo en blanco."],
      ["cita", datos.cita.length >= 15 ? "" : "Escribe qué se dijo (al menos una frase)."],
      ["fuentes", hayEnlace(datos.fuentes) ? "" : "Pon al menos un enlace a una web que sirva para contrastarlo. Tiene que empezar por http:// o https://."],
    ];
    errores.forEach(([c, m]) => marcar(c, m));
    const primero = errores.find(([, m]) => m);
    if (primero) { $(primero[0]).focus(); return; }
    const boton = $("enviar");
    boton.disabled = true; boton.textContent = "Enviando…"; $("error-envio").hidden = true;
    try {
      const r = await fetch("/api/avisar", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ tipo: "propuesta", ...datos, entrevista: $("slug").selectedOptions[0].textContent,
          comentario: $("comentario").value, web: $("web").value, t: t0 }),
      });
      const d = await r.json().catch(() => ({}));
      if (!r.ok) throw new Error(d.error || "No se ha podido enviar. Prueba de nuevo en unos minutos.");
      $("formulario").hidden = true; $("hecho").hidden = false; $("hecho").focus();
    } catch (err) {
      $("error-envio").textContent = err.message; $("error-envio").hidden = false;
      boton.disabled = false; boton.textContent = "Enviar propuesta";
    }
  });
})();
</script>
</body>
</html>
"""



# Página /participa: el apartado propio de los dos formularios, enlazado desde el menú y la portada
PARTICIPA = """<!doctype html>
<html lang="es">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
@@HEAD_MODO@@
@@CABECERA@@
<style>
@@ESTILO_FORM@@
.cabeza { padding:clamp(28px,5vw,56px) 0 clamp(24px,3vw,36px); }
.cabeza h1 { margin:0 0 14px; }
.cabeza .entrada { margin:0; }
@media (min-width:1000px) { .cabeza { display:grid; grid-template-columns:minmax(0,1.2fr) minmax(0,1fr); gap:0 clamp(32px,5vw,80px); align-items:end; }
  .cabeza h1 { margin:0; } }
.vias { display:grid; grid-template-columns:repeat(auto-fit,minmax(min(100%,380px),1fr)); gap:clamp(16px,2vw,24px); margin:0 0 clamp(36px,5vw,56px); }
.via { display:flex; flex-direction:column; gap:12px; min-width:0; margin:0; }
.via h2 { font:700 clamp(24px,2.4vw,28px)/1.2 var(--serif); margin:0; text-wrap:balance; }
.via p { margin:0; max-width:62ch; }
.via .atajo { font-size:14.5px; color:var(--suave); }
.via .boton { margin-top:auto; align-self:flex-start; display:inline-flex; align-items:center; min-height:46px; padding:0 22px; font-weight:700;
  text-decoration:none; background:var(--tinta); color:var(--fondo); border:2px solid var(--tinta); border-radius:var(--r-boton);
  transition:background-color .18s ease-out, color .18s ease-out; }
.via .boton:hover { background:var(--fondo); color:var(--tinta); }
@media (max-width:560px) { .via .boton { align-self:stretch; justify-content:center; } }
.despues { border-top:3px solid var(--tinta); padding-top:12px; }
.despues h2 { font:700 clamp(24px,2.4vw,28px)/1.2 var(--serif); margin:0 0 14px; }
.despues ul { margin:0 0 18px; padding-left:20px; max-width:68ch; }
.despues li { margin:0 0 8px; }
.despues .registro { margin:0; max-width:68ch; }
</style>
<style>@@CSS_MENU@@</style>
</head>
<body>
@@MENU@@
<main class="ancho">
<div class="cabeza">
<h1>Participa</h1>
<p class="entrada">Esta verificación la hace una IA y la mejoramos con lo que nos mandáis. Hay dos formas de ayudar y, en las dos, te pedimos un enlace a una fuente: así cualquiera puede comprobarlo. No hace falta cuenta.</p>
</div>

<div class="vias">
<section class="caja via" aria-labelledby="via-error">
<p class="rot">Corregir</p>
<h2 id="via-error">¿Hemos verificado algo mal?</h2>
<p>Si crees que un veredicto es incorrecto, mándanos el enlace a una web que muestre el dato correcto. Lo revisamos con el mismo criterio para todos los partidos.</p>
<p class="atajo">Atajo: en cada afirmación, el botón «Avisar de un error» abre el formulario con ella ya puesta.</p>
<a class="boton" href="/avisar">Avisar de un error</a>
</section>
<section class="caja via" aria-labelledby="via-propuesta">
<p class="rot">Añadir</p>
<h2 id="via-propuesta">¿Falta algo que se dijo?</h2>
<p>Si un candidato dijo algo comprobable que no está en la línea temporal, cuéntanos qué dijo y en qué minuto, con un enlace para contrastarlo.</p>
<p class="atajo">Atajo: desde la transcripción de cada entrevista llegas con la entrevista ya elegida.</p>
<a class="boton" href="/proponer">Proponer un hecho para verificar</a>
</section>
</div>

<section class="despues" aria-labelledby="despues">
<h2 id="despues">Qué pasa después</h2>
<ul>
<li>Tu envío se publica tal cual en el registro público del proyecto, en GitHub, sin ningún dato tuyo. No pongas datos personales.</li>
<li>Lo revisamos con el <a href="/metodologia">mismo método</a> y la misma vara de medir para todos los partidos.</li>
<li>Si la fuente lo confirma, corregimos el veredicto o añadimos la afirmación, y el cambio queda registrado.</li>
</ul>
<p class="registro">Puedes seguir cómo se resuelve cada uno: <a href="@@REPO@@/issues?q=is%3Aissue+label%3Acorrecci%C3%B3n" target="_blank" rel="noopener noreferrer">avisos de error</a> y <a href="@@REPO@@/issues?q=is%3Aissue+label%3Apropuesta" target="_blank" rel="noopener noreferrer">propuestas</a>.</p>
</section>
</main>
<footer class="pie-solo"><div class="ancho">@@PIE@@</div></footer>
</body>
</html>
"""
