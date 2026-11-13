#!/usr/bin/env python3
"""Descarga el audio de una entrevista de YouTube y la transcribe en local con Whisper (MLX).

Uso:  .venv/bin/python herramientas/transcribir.py <slug> <url-de-youtube> "<Nombre del invitado>" ["glosario extra"]
Crea entrevistas/<slug>/ con: entrevista.m4a (no se sube al repo), info.txt, capitulos.json,
segmentos.json (texto con tiempos), transcripcion.txt (párrafos de ~1 min con marca [h:mm:ss]) y meta.json.
"""
import json
import subprocess
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
MODELO = "mlx-community/whisper-large-v3-turbo"


def hms(s):
    s = int(s)
    return f"{s // 3600}:{s % 3600 // 60:02d}:{s % 60:02d}"


def main():
    if len(sys.argv) < 4:
        sys.exit(__doc__)
    slug, url, invitado = sys.argv[1:4]
    glosario = sys.argv[4] if len(sys.argv) > 4 else ""
    carpeta = RAIZ / "entrevistas" / slug
    carpeta.mkdir(parents=True, exist_ok=True)

    info = json.loads(subprocess.run(["uvx", "-q", "yt-dlp", "--skip-download", "--dump-single-json", url],
                                     capture_output=True, text=True, check=True).stdout)
    (carpeta / "capitulos.json").write_text(json.dumps(info.get("chapters") or [], ensure_ascii=False, indent=1))
    (carpeta / "info.txt").write_text(f'{info["title"]} | {info.get("upload_date")} | {info.get("duration_string")} | '
                                      f'{info["webpage_url"]}\n{info.get("description", "")}\n')
    audio = carpeta / "entrevista.m4a"
    if not audio.exists():
        subprocess.run(["uvx", "-q", "yt-dlp", "-q", "-f", "bestaudio[ext=m4a]/bestaudio", "-o", str(audio), url], check=True)

    import mlx_whisper
    r = mlx_whisper.transcribe(
        str(audio), path_or_hf_repo=MODELO, language="es", condition_on_previous_text=False, verbose=None,
        initial_prompt=(f"Entrevista de Jordi Wild a {invitado} en The Wild Project. PSOE, PP, Vox, Sumar, Podemos, "
                        f"Junts, ERC, Bildu, PNV, Pedro Sánchez, Feijóo, Abascal, Ada Colau, Moncloa, Congreso. {glosario}"))
    segs = r["segments"]
    (carpeta / "segmentos.json").write_text(
        json.dumps([{"i": s["start"], "f": s["end"], "t": s["text"]} for s in segs], ensure_ascii=False))
    with open(carpeta / "transcripcion.txt", "w") as f:
        parrafo, ini = [], None
        for s in segs:
            if ini is None:
                ini = s["start"]
            parrafo.append(s["text"].strip())
            if s["end"] - ini >= 60:
                f.write(f"[{hms(ini)}] " + " ".join(parrafo) + "\n\n")
                parrafo, ini = [], None
        if parrafo:
            f.write(f"[{hms(ini)}] " + " ".join(parrafo) + "\n")

    d = int(info.get("duration") or 0)
    f = str(info.get("upload_date") or "")
    meses = "ene feb mar abr may jun jul ago sep oct nov dic".split()
    meta = {"slug": slug, "invitado": invitado, "programa": info["title"].split(" - ")[0], "video": info["id"],
            "fecha": f"{int(f[6:8])} {meses[int(f[4:6]) - 1]} {f[:4]}" if len(f) == 8 else "",
            "duracion": f"{d // 3600} h {d % 3600 // 60} min"}
    if not (carpeta / "meta.json").exists():
        (carpeta / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2) + "\n")
    print(f"Hecho: {carpeta} · {len(segs)} segmentos · {len(info.get('chapters') or [])} capítulos")


if __name__ == "__main__":
    main()
