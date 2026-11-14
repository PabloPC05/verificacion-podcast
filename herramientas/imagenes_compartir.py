#!/usr/bin/env python3
"""Genera las imágenes para compartir la web en redes y el favicon, en web-src/compartir/.

  web-src/compartir/general.png        1200×630: portada, /verificalo y /api
  web-src/compartir/<slug>.png         1200×630: una por entrevista publicada ("publicar": true)
  web-src/compartir/afirmaciones/<slug>/<id>.png  1200×630: una por afirmación, con su veredicto y su texto
  web-src/compartir/favicon.svg        icono vectorial
  web-src/compartir/favicon-32.png     32×32
  web-src/compartir/apple-touch-icon.png  180×180

Las imágenes generales y las de cada entrevista NO llevan recuentos de veredictos: así no quedan viejas cuando se
corrige un veredicto. Las de cada afirmación sí llevan el suyo, así que hay que regenerarlas al corregir uno
(solo se reescriben las que cambian).
Necesita Pillow, que no es dependencia del proyecto (build.py solo copia estos ficheros), así que se ejecuta con:

    uv run --with pillow python herramientas/imagenes_compartir.py

Hay que volver a ejecutarlo al publicar una entrevista nueva (y subir los ficheros nuevos al repositorio).
Los logotipos de partido (web-src/logos/*.svg) se rasterizan con rsvg-convert o, si no está, con qlmanage (macOS);
sin ninguna de las dos herramientas la imagen sale sin logotipo.
"""
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "web-src"))
import build  # noqa: E402  (reutiliza TONO, LOGOS y BASE para no duplicarlos)

SALIDA = RAIZ / "web-src" / "compartir"
ANCHO, ALTO = 1200, 630
NEGRO, BLANCO, GRIS = "#000000", "#ffffff", "#444444"

FUENTES_SERIF = ["/System/Library/Fonts/Supplemental/Iowan Old Style.ttc", "/System/Library/Fonts/Palatino.ttc",
                 "/System/Library/Fonts/Supplemental/Georgia Bold.ttf", "/Library/Fonts/Georgia Bold.ttf",
                 "/usr/share/fonts/truetype/dejavu/DejaVuSerif-Bold.ttf"]
FUENTES_SANS = ["/System/Library/Fonts/Helvetica.ttc", "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
                "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"]


def fuente(rutas, tam, estilo):
    """Primera fuente disponible; en colecciones (.ttc) elige la cara cuyo estilo coincide con `estilo`."""
    for ruta in rutas:
        if not Path(ruta).exists():
            continue
        if not ruta.endswith(".ttc"):
            return ImageFont.truetype(ruta, tam)
        for i in range(12):
            try:
                f = ImageFont.truetype(ruta, tam, index=i)
            except OSError:
                break
            if f.getname()[1].lower() == estilo.lower():
                return f
    sys.exit("No encuentro una fuente adecuada; instala Iowan Old Style, Palatino o Georgia.")


def serif(tam, estilo="Bold"):
    return fuente(FUENTES_SERIF, tam, estilo)


def sans(tam):
    return fuente(FUENTES_SANS, tam, "Bold")


def ancho(d, texto, f, espacio=0):
    return d.textlength(texto, font=f) + espacio * max(0, len(texto) - 1)


def con_espaciado(d, xy, texto, f, relleno, espacio):
    x, y = xy
    for c in texto:
        d.text((x, y), c, font=f, fill=relleno)
        x += d.textlength(c, font=f) + espacio


def ajustar(d, texto, tam_max, tam_min, max_ancho, max_lineas, estilo="Bold"):
    """Mayor tamaño de letra con el que el texto cabe en `max_lineas` líneas de `max_ancho` px. Devuelve (fuente, líneas)."""
    for tam in range(tam_max, tam_min - 1, -2):
        f = serif(tam, estilo)
        lineas, actual = [], ""
        for palabra in texto.split():
            prueba = f"{actual} {palabra}".strip()
            if ancho(d, prueba, f) <= max_ancho:
                actual = prueba
            else:
                lineas.append(actual)
                actual = palabra
        lineas.append(actual)
        if len(lineas) <= max_lineas and all(ancho(d, l, f) <= max_ancho for l in lineas):
            return f, lineas
    sys.exit(f"El texto «{texto}» no cabe ni con la letra más pequeña")


def rasterizar_logo(svg, caja):
    """Logotipo SVG como imagen RGBA que cabe en `caja` (ancho, alto), o None si no hay con qué rasterizarlo."""
    caja_w, caja_h = caja
    with tempfile.TemporaryDirectory() as tmp:
        png = Path(tmp) / "logo.png"
        try:
            if shutil.which("rsvg-convert"):
                subprocess.run(["rsvg-convert", "-a", "-w", str(caja_w * 2), "-h", str(caja_h * 2), "-b", "none",
                                "-o", str(png), str(svg)], check=True, capture_output=True)
            elif shutil.which("qlmanage"):
                subprocess.run(["qlmanage", "-t", "-s", str(max(caja) * 2), "-o", tmp, str(svg)],
                               check=True, capture_output=True)
                png = Path(tmp) / (Path(svg).name + ".png")
            else:
                return None
            img = Image.open(png).convert("RGBA")
        except (subprocess.CalledProcessError, OSError):
            return None
    img.thumbnail((caja_w * 2, caja_h * 2), Image.LANCZOS)
    return img


def lienzo(rotulo, tono=None):
    """Fondo blanco con marco negro grueso, rótulo en una pastilla negra y banda inferior con los colores de veredicto."""
    img = Image.new("RGB", (ANCHO, ALTO), BLANCO)
    d = ImageDraw.Draw(img)
    d.rectangle([24, 24, ANCHO - 25, ALTO - 25], outline=NEGRO, width=10)
    f = sans(25)
    esp = 3
    w = ancho(d, rotulo, f, esp)
    d.rectangle([58, 58, 58 + w + 44, 58 + 54], fill=NEGRO)
    con_espaciado(d, (80, 71), rotulo, f, BLANCO, esp)
    # Banda de colores (como la barra de cada tema de la web); es solo un detalle, sin proporciones ni cifras.
    x0, x1, y0, y1 = 34, ANCHO - 34, ALTO - 34 - 22, ALTO - 34
    if tono:  # imagen de una afirmación: la banda entera en el color de su veredicto
        d.rectangle([x0, y0, x1, y1], fill=tono)
        return img, d
    paso = (x1 - x0) / len(build.ORDEN)
    for n, k in enumerate(build.ORDEN):
        d.rectangle([round(x0 + n * paso), y0, round(x0 + (n + 1) * paso) - 1, y1], fill=build.TONO[k])
    return img, d


ZONA = (128, 440)  # franja vertical donde se centra el bloque principal (entre el rótulo y el pie)


def imagen_general():
    img, d = lienzo("VERIFICACIÓN DATO A DATO")
    f, lineas = ajustar(d, "Las entrevistas electorales de The Wild Project, verificadas", 76, 50, 1040, 3)
    paso = int(f.size * 1.14)
    y = ZONA[0] + (ZONA[1] - ZONA[0] - paso * len(lineas)) // 2
    for l in lineas:
        d.text((80, y), l, font=f, fill=NEGRO)
        y += paso
    d.text((80, 462), "Elecciones generales del 29-N de 2026", font=serif(36, "Italic"), fill=GRIS)
    d.text((80, 512), build.BASE.replace("https://", ""), font=sans(26), fill=NEGRO)
    return img


def imagen_entrevista(m):
    img, d = lienzo("VERIFICACIÓN DATO A DATO")
    partido = m.get("partido") or ""
    svg = build.LOGOS.get(partido)
    logo = rasterizar_logo(RAIZ / "web-src" / "logos" / svg, (260, 170)) if svg else None
    tope = 1040 - (logo.width // 2 + 50 if logo else 0)
    f, lineas = ajustar(d, m["invitado"], 104, 56, tope, 2)
    paso = int(f.size * 1.12)
    f_partido = serif(46, "Regular")
    alto = paso * len(lineas) + 14 + 54
    y = ZONA[0] + (ZONA[1] - ZONA[0] - alto) // 2
    for l in lineas:
        d.text((80, y), l, font=f, fill=NEGRO)
        y += paso
    d.text((80, y + 14), partido, font=f_partido, fill=GRIS)
    if logo:
        w, h = logo.width // 2, logo.height // 2
        pequeno = logo.resize((w, h), Image.LANCZOS)
        img.paste(pequeno, (ANCHO - 90 - w, (ZONA[0] + ZONA[1]) // 2 - h // 2), pequeno)
    d.text((80, 462), f'Entrevista de Jordi Wild en {m["programa"]}', font=serif(36, "Italic"), fill=NEGRO)
    d.text((80, 512), build.BASE.replace("https://", ""), font=sans(26), fill=NEGRO)
    return img


def imagen_afirmacion(m, a):
    """Veredicto en su color, la afirmación en grande y, debajo, quién lo dijo y en qué minuto."""
    v = a["veredicto"]
    img, d = lienzo(f'VERIFICACIÓN · {m["invitado"].upper()}', build.TONO[v])
    f_v = sans(30)
    texto_v = build.NOMBRE[v].upper()
    w = ancho(d, texto_v, f_v, 2)
    d.rectangle([80, 140, 80 + w + 36, 140 + 50], fill=build.TONO[v])
    con_espaciado(d, (98, 150), texto_v, f_v, BLANCO, 2)
    afirmacion = " ".join(a.get("afirmacion", "").split())
    if len(afirmacion) > 230:
        afirmacion = afirmacion[:230].rsplit(" ", 1)[0].rstrip(",.;:") + "…"
    f, lineas = ajustar(d, afirmacion, 58, 34, 1040, 4)
    paso = int(f.size * 1.18)
    y = 210 + (426 - 210 - paso * len(lineas)) // 2
    for l in lineas:
        d.text((80, y), l, font=f, fill=NEGRO)
        y += paso
    d.text((80, 462), f'{m["invitado"]} en {m["programa"]}, minuto {build.hms(a["_t"])}', font=serif(34, "Italic"), fill=NEGRO)
    d.text((80, 512), f'{build.BASE.replace("https://", "")}/{m["slug"]}/{a["_id"]}', font=sans(26), fill=NEGRO)
    return img


def guardar_si_cambia(img, ruta):
    """PNG con paleta reducida (pesa la cuarta parte y el texto se ve igual); no reescribe si sale idéntico."""
    import io
    buf = io.BytesIO()
    img.quantize(colors=48, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE).save(buf, "PNG", optimize=True)
    datos = buf.getvalue()
    if ruta.exists() and ruta.read_bytes() == datos:
        return False
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_bytes(datos)
    return True


# Favicon: cuadrado negro con una marca de verificación blanca (vista 64×64).
MARCA = [(17, 34), (28, 45), (48, 20)]
FAVICON_SVG = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64">
<rect width="64" height="64" rx="10" fill="#000"/>
<path d="M17 34l11 11 20-25" fill="none" stroke="#fff" stroke-width="8" stroke-linecap="round" stroke-linejoin="round"/>
</svg>
"""


def icono(tam, redondeado):
    k, s = 8, tam * 8
    img = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    if redondeado:
        d.rounded_rectangle([0, 0, s - 1, s - 1], radius=round(s * 10 / 64), fill=NEGRO)
    else:
        d.rectangle([0, 0, s, s], fill=NEGRO)
    esc = s / 64 * (0.8 if not redondeado else 1)  # el icono de Apple ocupa todo el cuadrado: marca algo más pequeña
    desp = s / 2 - 32 * esc
    pts = [(desp + x * esc, desp + y * esc) for x, y in MARCA]
    ancho_linea = round(8 * esc)
    d.line(pts, fill=BLANCO, width=ancho_linea, joint="curve")
    for x, y in (pts[0], pts[-1]):
        r = ancho_linea / 2
        d.ellipse([x - r, y - r, x + r, y + r], fill=BLANCO)
    return img.resize((tam, tam), Image.LANCZOS)


def main():
    SALIDA.mkdir(parents=True, exist_ok=True)
    imagen_general().save(SALIDA / "general.png", optimize=True)
    publicadas = []
    for ruta in sorted((RAIZ / "entrevistas").glob("*/meta.json")):
        m = json.loads(ruta.read_text(encoding="utf-8"))
        if m.get("publicar"):
            imagen_entrevista(m).save(SALIDA / f'{m["slug"]}.png', optimize=True)
            publicadas.append(m["slug"])
            # una por afirmación publicada (las excluidas no tienen página); se borran las que ya no existen
            pm = build.preparar(m)
            carpeta = SALIDA / "afirmaciones" / m["slug"]
            nuevas = sum(guardar_si_cambia(imagen_afirmacion(pm, a), carpeta / f'{a["_id"]}.png') for a in pm["todas"])
            vivas = {f'{a["_id"]}.png' for a in pm["todas"]}
            for vieja in carpeta.glob("*.png"):
                if vieja.name not in vivas:
                    vieja.unlink()
            print(f'{m["slug"]}: {len(pm["todas"])} imágenes de afirmación ({nuevas} nuevas o cambiadas)')
    (SALIDA / "favicon.svg").write_text(FAVICON_SVG, encoding="utf-8")
    icono(32, True).save(SALIDA / "favicon-32.png", optimize=True)
    icono(180, False).convert("RGB").save(SALIDA / "apple-touch-icon.png", optimize=True)
    print(f'Escritas en {SALIDA}: general.png, {", ".join(s + ".png" for s in publicadas)}, favicon.svg, favicon-32.png, apple-touch-icon.png')


if __name__ == "__main__":
    main()
