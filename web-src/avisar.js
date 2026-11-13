// Función de Vercel (se publica en /api/avisar): recibe los formularios de la web y los publica como incidencias en
// el repositorio, sin que quien escribe tenga que salir de la web ni tener cuenta en GitHub.
//   - tipo «error» (página /avisar): una afirmación ya verificada que alguien cree que está mal. Etiqueta «corrección».
//   - tipo «propuesta» (página /proponer): algo que se dijo en una entrevista y que habría que verificar. Etiqueta «propuesta».
//
// Necesita la variable de entorno GITHUB_TOKEN_AVISOS: un token «fine-grained» de GitHub limitado a este
// repositorio, con el único permiso Issues: Read and write. Sin ella responde 503.
//
// Defensas: el enlace a una fuente es obligatorio (al menos uno http/https, como mucho 8), campo trampa para robots,
// tiempo mínimo para rellenar, límite de envíos por IP (en memoria, nada se guarda), la afirmación o la entrevista
// tiene que existir en la web y las menciones de GitHub se neutralizan.
const REPO = "PabloPC05/verificacion-podcast";
const BASE = "https://verificacion-podcast.vercel.app";
const ENLACE = /https?:\/\/[^\s<>"'()]+/gi;
const RUTA = /^\/[a-z]+\/m\d+(?:-\d+)?$/;
const SLUG = /^[a-z]+$/;
const MINUTO = /^(?:\d{1,2}:)?[0-5]?\d:[0-5]\d$/;
const recientes = new Map();

const texto = (v, max) => String(v ?? "").replace(/\r/g, "").trim().slice(0, max);
// Que nadie quede mencionado ni se enlacen otras incidencias por accidente
const neutro = t => t.replace(/@/g, "@​").replace(/#(\d)/g, "#​$1");
const cita = t => neutro(t).split("\n").map(l => `> ${l}`);

function enlacesValidos(fuentes) {
  const vistos = new Set();
  for (const bruto of fuentes.match(ENLACE) || []) {
    const limpio = bruto.replace(/[.,;:!?]+$/, "");
    try {
      const u = new URL(limpio);
      if ((u.protocol === "http:" || u.protocol === "https:") && u.hostname.includes(".")) vistos.add(u.href);
    } catch { /* no es un enlace */ }
  }
  return [...vistos];
}

// La página tiene que existir en la web (responde 200)
async function existe(ruta) {
  try { return (await fetch(BASE + ruta, { method: "HEAD", redirect: "manual" })).status === 200; } catch { return false; }
}

const fallo = (res, codigo, error) => res.status(codigo).json({ error });

async function preparar(d, tipo, enlaces, comentario) {
  const fuentes = ["", tipo === "propuesta" ? "**Enlaces para contrastarlo:**" : "**Fuentes que aporta quien avisa:**",
    ...enlaces.map(u => `- ${u}`)];
  const pie = ["", "_Enviado desde el formulario de la web. No se guardan datos de quien escribe._"];
  if (tipo === "propuesta") {
    const slug = SLUG.test(String(d.slug || "")) ? String(d.slug) : "";
    if (!slug || !(await existe(`/${slug}`))) return { error: "Elige de qué entrevista es." };
    const entrevista = texto(d.entrevista, 80) || slug;
    const minuto = texto(d.minuto, 8);
    if (minuto && !MINUTO.test(minuto)) return { error: "El minuto tiene que tener la forma 1:02:00 o 45:10." };
    const dicho = texto(d.cita, 600);
    if (dicho.length < 15) return { error: "Escribe qué se dijo (al menos una frase)." };
    const corto = dicho.replace(/\s+/g, " ").slice(0, 70) + (dicho.length > 70 ? "…" : "");
    return {
      etiqueta: "propuesta",
      titulo: `Propuesta: ${entrevista}${minuto ? `, ${minuto}` : ""} · «${corto}»`.slice(0, 140),
      cuerpo: [
        `**Entrevista:** ${neutro(entrevista)} · ${BASE}/${slug}/transcripcion${minuto ? ` (minuto ${minuto})` : ""}`,
        "", "**Lo que se dijo:**", ...cita(dicho), ...fuentes,
        ...(comentario ? ["", "**Por qué habría que verificarlo, según quien lo propone:**", ...cita(comentario)] : []),
        ...pie,
      ].join("\n"),
    };
  }
  let ruta = RUTA.test(String(d.ruta || "")) ? String(d.ruta) : "";
  if (ruta && !(await existe(ruta))) ruta = "";
  const afirmacion = texto(d.afirmacion, 300);
  if (!ruta && !afirmacion) return { error: "Indica qué afirmación crees que está mal." };
  const quien = afirmacion || ruta;
  return {
    etiqueta: "corrección",
    titulo: `Error en: ${quien}`.slice(0, 120),
    cuerpo: [
      `**Afirmación:** ${neutro(quien)}${ruta ? ` · ${BASE}${ruta}` : ""}`, ...fuentes,
      ...(comentario ? ["", "**Qué está mal, según quien avisa:**", ...cita(comentario)] : []),
      ...pie,
    ].join("\n"),
  };
}

module.exports = async (req, res) => {
  res.setHeader("Cache-Control", "no-store");
  if (req.method !== "POST") {
    res.setHeader("Allow", "POST");
    return fallo(res, 405, "Este enlace solo recibe los formularios de la web.");
  }
  const token = process.env.GITHUB_TOKEN_AVISOS;
  if (!token) return fallo(res, 503, "El envío todavía no está activado. Prueba más tarde.");

  let d = req.body;
  if (typeof d === "string") { try { d = JSON.parse(d); } catch { d = {}; } }
  d = d && typeof d === "object" ? d : {};

  if (texto(d.web, 200)) return res.status(200).json({ ok: true }); // campo trampa: un robot lo rellena
  const t = Number(d.t);
  if (!t || Date.now() - t < 3000) return fallo(res, 400, "Espera unos segundos y vuelve a enviarlo.");

  const tipo = d.tipo === "propuesta" ? "propuesta" : "error";
  const enlaces = enlacesValidos(texto(d.fuentes, 3000));
  if (!enlaces.length) {
    return fallo(res, 400, "Pon al menos un enlace a una web que sirva para contrastarlo (que empiece por http:// o https://).");
  }
  if (enlaces.length > 8) return fallo(res, 400, "Son demasiados enlaces: deja los más claros (como mucho 8).");

  const ip = String(req.headers["x-forwarded-for"] || "").split(",")[0].trim() || "desconocida";
  const ahora = Date.now();
  const suyos = (recientes.get(ip) || []).filter(x => ahora - x < 3600e3);
  if (suyos.length >= 5) return fallo(res, 429, "Has enviado varios formularios seguidos. Prueba dentro de un rato.");

  const p = await preparar(d, tipo, enlaces, texto(d.comentario, 2000));
  if (p.error) return fallo(res, 400, p.error);
  suyos.push(ahora);
  recientes.set(ip, suyos);

  try {
    const r = await fetch(`https://api.github.com/repos/${REPO}/issues`, {
      method: "POST",
      headers: {
        Authorization: `Bearer ${token}`,
        Accept: "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "verificacion-podcast-avisos",
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ title: p.titulo, body: p.cuerpo, labels: [p.etiqueta] }),
    });
    if (!r.ok) {
      console.error("GitHub respondió", r.status, (await r.text()).slice(0, 300));
      return fallo(res, 502, "No se ha podido enviar. Prueba de nuevo en unos minutos.");
    }
    const hecho = await r.json();
    return res.status(201).json({ ok: true, numero: hecho.number, url: hecho.html_url });
  } catch (err) {
    console.error("Fallo al crear la incidencia", err);
    return fallo(res, 502, "No se ha podido enviar. Prueba de nuevo en unos minutos.");
  }
};
