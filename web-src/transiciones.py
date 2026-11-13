"""Transición al expandir una afirmación: la tarjeta de la línea temporal crece hasta convertirse en su página,
y al volver a la línea temporal la página se encoge hasta la tarjeta.

Usa las transiciones entre documentos del navegador (View Transitions con `@view-transition`). Donde no existen, la
página se abre sin animación, como antes. Con «reducir movimiento» no se anima nada. Solo se anima el paso entre la
línea temporal de una entrevista (/<slug>) y una de sus afirmaciones (/<slug>/<id>); el resto de navegaciones no.

build.py lo mete en el <head> de todas las páginas desde rellenar().
"""

HEAD = """<style>
@view-transition { navigation: auto; }
::view-transition-group(afirmacion) { animation-duration:280ms; animation-timing-function:cubic-bezier(.2,.7,.2,1); }
/* La tarjeta se desvanece enseguida y es la página nueva la que crece desde su tamaño, recortada por arriba */
::view-transition-old(afirmacion) { animation-duration:80ms; }
::view-transition-new(afirmacion) { animation-duration:120ms; height:100%; object-fit:cover; object-position:top; }
@media (prefers-reduced-motion: reduce) { @view-transition { navigation: none; } }
</style>
<script>
(() => {
  const AFIRMACION = /^\\/([a-z]+)\\/(m\\d+(?:-\\d+)?)\\/?$/, LINEA = /^\\/([a-z]+)\\/?$/;
  const ruta = u => { try { return new URL(u).pathname; } catch (e) { return ""; } };
  const visible = el => { const r = el.getBoundingClientRect(); return r.bottom > 0 && r.top < innerHeight; };
  const nombrar = (el, vt) => {
    el.style.viewTransitionName = "afirmacion";
    vt.ready.catch(() => {});
    vt.finished.finally(() => { el.style.viewTransitionName = ""; }).catch(() => {});
  };
  // Saltar sin dejar promesas rechazadas sin atender (darían un error en la consola)
  const saltar = vt => { vt.ready.catch(() => {}); vt.updateCallbackDone.catch(() => {}); vt.skipTransition(); };
  // Qué se anima entre dos rutas: «ida» de la línea temporal a una afirmación de la misma entrevista, o «vuelta»
  const paso = (de, a) => {
    const l = LINEA.exec(de), f = AFIRMACION.exec(a);
    if (l && f && l[1] === f[1]) return { tipo: "ida", id: f[2] };
    const f2 = AFIRMACION.exec(de), l2 = LINEA.exec(a);
    if (f2 && l2 && f2[1] === l2[1]) return { tipo: "vuelta", id: f2[2] };
    return null;
  };
  const tarjeta = id => document.getElementById(id) && document.getElementById(id).querySelector(".panel");
  const pagina = () => document.querySelector("main[data-v]");
  // La página que se va marca lo que va a crecer (la tarjeta) o a encogerse (la página de la afirmación)
  addEventListener("pageswap", ev => {
    const vt = ev.viewTransition; if (!vt) return;
    const p = paso(ruta(location.href), ruta(ev.activation && ev.activation.entry ? ev.activation.entry.url : ""));
    const el = p && (p.tipo === "ida" ? tarjeta(p.id) : pagina());
    if (el && visible(el)) nombrar(el, vt); else saltar(vt);
  });
  // La que llega marca el destino
  addEventListener("pagereveal", ev => {
    const vt = ev.viewTransition; if (!vt) return;
    const desde = window.navigation && navigation.activation && navigation.activation.from ? navigation.activation.from.url : "";
    const p = paso(ruta(desde), ruta(location.href));
    const el = p && (p.tipo === "ida" ? pagina() : tarjeta(p.id));
    if (el && visible(el)) nombrar(el, vt); else saltar(vt);
  });
})();
</script>"""
