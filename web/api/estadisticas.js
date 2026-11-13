// Función de Vercel que sirve los datos del panel privado (/panel).
// build.py la copia a web/api/estadisticas.js; edítala aquí, no en web/.
//
// Variables de entorno en Vercel:
//   UMAMI_API_KEY     clave de la API de Umami Cloud (Settings → API keys)
//   UMAMI_WEBSITE_ID  ID del sitio en Umami
//   PANEL_CLAVE       contraseña para entrar al panel (larga: no hay límite de intentos)
//
// GET /api/estadisticas?dias=7   con cabecera  Authorization: Bearer <PANEL_CLAVE>
const crypto = require("crypto");

const UMAMI = "https://api.umami.is/v1";
const ZONA = "Europe/Madrid";
const PERIODOS = { 1: "hour", 7: "day", 30: "day", 90: "day", 365: "month" };

function claveCorrecta(recibida, esperada) {
  const a = crypto.createHash("sha256").update(String(recibida)).digest();
  const b = crypto.createHash("sha256").update(String(esperada)).digest();
  return crypto.timingSafeEqual(a, b);
}

module.exports = async (req, res) => {
  res.setHeader("Cache-Control", "no-store");
  res.setHeader("X-Robots-Tag", "noindex");
  const { UMAMI_API_KEY: clave, UMAMI_WEBSITE_ID: sitio, PANEL_CLAVE: panel } = process.env;
  if (!clave || !sitio || !panel) {
    return res.status(503).json({ error: "Faltan variables de entorno en Vercel: UMAMI_API_KEY, UMAMI_WEBSITE_ID y PANEL_CLAVE." });
  }
  const enviada = (req.headers.authorization || "").replace(/^Bearer\s+/i, "");
  if (!enviada || !claveCorrecta(enviada, panel)) return res.status(401).json({ error: "Contraseña incorrecta." });

  const dias = PERIODOS[req.query.dias] ? Number(req.query.dias) : 7;
  const endAt = Date.now(), startAt = endAt - dias * 864e5;
  const rango = { startAt, endAt };

  // Cada llamada falla por su cuenta: si Umami cambia un endpoint, el resto del panel sigue saliendo.
  async function umami(ruta, params = {}) {
    const url = new URL(`${UMAMI}/websites/${sitio}${ruta}`);
    for (const [k, v] of Object.entries(params)) url.searchParams.set(k, v);
    const r = await fetch(url, { headers: { "x-umami-api-key": clave, accept: "application/json" } });
    if (!r.ok) throw new Error(`${r.status} en ${ruta}`);
    return r.json();
  }
  const seguro = (p) => p.catch((e) => ({ error: e.message }));
  // Las versiones nuevas de Umami llaman «path» a lo que antes era «url».
  const metrica = (type, limit = 50) =>
    umami("/metrics", { ...rango, type, limit }).catch(() =>
      type === "path" ? umami("/metrics", { ...rango, type: "url", limit }) : Promise.reject(new Error(`métrica ${type}`)));
  const valores = (evento) =>
    umami("/event-data/values", { ...rango, event: evento, eventName: evento, propertyName: "url" });

  const [resumen, serie, activos, paginas, referentes, eventos, externos, descargas, internos, paises, dispositivos, navegadores] =
    await Promise.all([
      seguro(umami("/stats", rango)),
      seguro(umami("/pageviews", { ...rango, unit: PERIODOS[dias], timezone: ZONA })),
      seguro(umami("/active")),
      seguro(metrica("path")),
      seguro(metrica("referrer")),
      seguro(metrica("event")),
      seguro(valores("enlace-externo")),
      seguro(valores("descarga")),
      seguro(valores("enlace-interno")),
      seguro(metrica("country", 20)),
      seguro(metrica("device", 10)),
      seguro(metrica("browser", 10)),
    ]);

  res.status(200).json({
    dias, unidad: PERIODOS[dias], startAt, endAt,
    resumen, serie, activos, paginas, referentes, eventos, externos, descargas, internos, paises, dispositivos, navegadores,
  });
};
