"""Estadísticas de visitas: el script de seguimiento de Umami.

La importa build.py. Las cifras se consultan en el panel de Umami Cloud (cloud.umami.is), no en la web.
"""
from urllib.parse import urlparse

# Además de las visitas (que Umami cuenta solo), cada clic en un enlace se registra como evento:
#   descarga        ficheros .csv / .json o enlaces con atributo download
#   enlace-externo  cualquier enlace a otro dominio (vídeos, fuentes, GitHub…)
#   enlace-interno  enlaces dentro de la web, con la página de origen
#   reproducir      lo registra el reproductor de vídeo de build.py (no este script) al pulsar un minuto: la página y el segundo
# Todos llevan la propiedad «url», con la que Umami los agrupa en su sección de eventos.
_CLICS = """<script>
document.addEventListener("click", function (ev) {
  var a = ev.target.closest && ev.target.closest("a[href]");
  if (!a || !window.umami || ev.defaultPrevented) return;  // si otro script ya gestionó el clic (el reproductor), no es una salida a otro dominio
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

