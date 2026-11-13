#!/usr/bin/env python3
"""Reconocimiento de hablantes de una entrevista, en local: Jordi Wild, el invitado u «otra voz».

Uso:  .venv/bin/python herramientas/hablantes.py <slug> [umbral_otra]

Necesita sherpa-onnx (uv pip install sherpa-onnx) y el modelo de huella de voz TitaNet-large en .modelos/:
  https://github.com/k2-fsa/sherpa-onnx/releases/download/speaker-recongition-models/nemo_en_titanet_large.onnx

Método:
1. Calcula la huella de voz de cada segmento de la transcripción (segmentos.json). Los segmentos de menos de
   1,2 s se amplían por los dos lados hasta 1,2 s.
2. Lo compara con dos muestras de referencia comprobadas a mano (MUESTRAS): Jordi presentando el programa y una
   respuesta larga del invitado. Se recalibra dos veces con los segmentos más claros.
3. Si un segmento no se parece a ninguna de las dos voces, queda como «otra voz» (verificadores, cortes, público).
4. Un segmento corto y dudoso entre dos del mismo hablante toma su etiqueta.

Con 125 segmentos etiquetados a mano de la entrevista de Sánchez, TitaNet acertó el 96,8 % sin recalibrar
(los fallos están en frases de menos de 1,5 s y en segmentos donde Whisper juntó a los dos hablantes).

Escribe entrevistas/<slug>/hablantes.json y entrevistas/<slug>/transcripcion-hablantes.txt.
"""
import json
import subprocess
import sys
from pathlib import Path

import numpy as np
import sherpa_onnx

RAIZ = Path(__file__).resolve().parent.parent
HUELLA = RAIZ / ".modelos" / "nemo_en_titanet_large.onnx"
FRECUENCIA = 16000
MINIMO = 1.2

# Fragmentos en los que habla una sola persona, comprobados en la transcripción (segundos).
MUESTRAS = {
    "sanchez": {"J": [(78, 107)], "G": [(271, 336)]},
    "feijoo": {"J": [(83, 116), (121, 141)], "G": [(318, 343), (359, 386)]},
    "colau": {"J": [(78, 126)], "G": [(203, 265)]},
}
# Los verificadores del programa (Iván Muñoz y Javier Collado) son los mismos en las tres entrevistas y hablan lejos
# del micrófono. Su muestra sale de la entrevista de Sánchez, cuando leen los datos de flujos migratorios.
MUESTRA_VERIFICADORES = ("sanchez", [(3512.4, 3517.7), (3526.5, 3536.5)])


def leer_audio(ruta, desde=None, hasta=None):
    tramo = ["-ss", str(desde), "-to", str(hasta)] if desde is not None else []
    crudo = subprocess.run(["ffmpeg", "-nostdin", "-loglevel", "error", *tramo, "-i", str(ruta), "-ac", "1",
                            "-ar", str(FRECUENCIA), "-f", "f32le", "-"], capture_output=True, check=True).stdout
    return np.frombuffer(crudo, dtype=np.float32).copy()


def hms(s):
    s = int(s)
    return f"{s // 3600}:{s % 3600 // 60:02d}:{s % 60:02d}"


def unitario(v):
    return v / (np.linalg.norm(v) + 1e-9)


def main():
    slug = sys.argv[1]
    umbral_otra = float(sys.argv[2]) if len(sys.argv) > 2 else 0.25
    carpeta = RAIZ / "entrevistas" / slug
    meta = json.loads((carpeta / "meta.json").read_text(encoding="utf-8"))
    segmentos = json.loads((carpeta / "segmentos.json").read_text(encoding="utf-8"))
    audio = leer_audio(carpeta / "entrevista.m4a")
    extractor = sherpa_onnx.SpeakerEmbeddingExtractor(
        sherpa_onnx.SpeakerEmbeddingExtractorConfig(model=str(HUELLA), num_threads=4))

    def huella(a, b, senal=None):
        senal = audio if senal is None else senal
        if b - a < MINIMO:
            extra = (MINIMO - (b - a)) / 2
            a, b = max(0, a - extra), b + extra
        flujo = extractor.create_stream()
        flujo.accept_waveform(FRECUENCIA, senal[int(a * FRECUENCIA):int(b * FRECUENCIA)])
        flujo.input_finished()
        return unitario(np.array(extractor.compute(flujo), dtype=np.float32))

    W = np.stack([huella(s["i"], s["f"]) for s in segmentos])
    dur = np.array([s["f"] - s["i"] for s in segmentos])

    ref = {}
    for k, tramos in MUESTRAS[slug].items():
        vs = []
        for a, b in tramos:
            x = a
            while x + 1.5 <= b:
                vs.append(huella(x, x + 1.5))
                x += 0.75
        ref[k] = unitario(np.mean(vs, axis=0))
    origen, tramos_v = MUESTRA_VERIFICADORES
    vs = []
    for a, b in tramos_v:
        trozo = leer_audio(RAIZ / "entrevistas" / origen / "entrevista.m4a", a, b)
        x = 0.0
        while x + 1.5 <= b - a:
            vs.append(huella(x, x + 1.5, trozo))
            x += 0.75
    ref_v = unitario(np.mean(vs, axis=0))
    parecido = float(ref["J"] @ ref["G"])

    for _ in range(2):  # recalibrar con los segmentos largos y claros
        S = np.stack([W @ ref["J"], W @ ref["G"]], axis=1)
        mejor, margen = S.argmax(axis=1), np.abs(S[:, 0] - S[:, 1])
        for i, k in enumerate(["J", "G"]):
            claros = (mejor == i) & (dur >= 2) & (margen > 0.15) & (S.max(axis=1) > 0.4)
            if claros.sum() > 20:
                ref[k] = unitario((W[claros] * dur[claros, None]).sum(axis=0))

    S = np.stack([W @ ref["J"], W @ ref["G"]], axis=1)
    V = W @ ref_v
    voz = np.where(S.argmax(axis=1) == 0, "J", "G").astype(object)
    voz[(V > S.max(axis=1)) & (V > 0.45)] = "V"
    voz[np.maximum(S.max(axis=1), V) < umbral_otra] = "O"
    margen = np.abs(S[:, 0] - S[:, 1])
    for i in range(1, len(voz) - 1):
        if voz[i - 1] == voz[i + 1] != voz[i] and dur[i] < 1.5 and margen[i] < 0.1:
            voz[i] = voz[i - 1]

    nombres = {"J": "Jordi Wild", "G": meta["invitado"], "V": "Verificadores del programa", "O": "Voz sin identificar"}
    asignados = [{"i": s["i"], "f": s["f"], "voz": v, "jordi": round(float(a), 3), "invitado": round(float(b), 3),
                  "verificadores": round(float(c), 3)} for s, v, (a, b), c in zip(segmentos, voz, S, V)]
    minutos = {nombres[k]: round(sum(x["f"] - x["i"] for x in asignados if x["voz"] == k) / 60, 1) for k in nombres}
    (carpeta / "hablantes.json").write_text(json.dumps({
        "metodo": {
            "herramienta": "sherpa-onnx " + getattr(sherpa_onnx, "__version__", ""),
            "huella": "NVIDIA NeMo TitaNet-large (ONNX)",
            "procedimiento": "Cada segmento de la transcripción se compara con muestras de referencia de Jordi Wild y del invitado "
                             "(herramientas/hablantes.py, MUESTRAS) recalibradas con los segmentos más claros, y con una muestra de los "
                             "verificadores del programa; «otra voz» si no se parece lo bastante a ninguna "
                             f"(umbral {umbral_otra}).",
            "parecido_entre_muestras": round(parecido, 3),
            "acierto_medido": "96,8 % en 125 segmentos etiquetados a mano de la entrevista de Sánchez",
        },
        "nombres": nombres, "minutos": minutos, "segmentos": asignados,
    }, ensure_ascii=False) + "\n", encoding="utf-8")

    with open(carpeta / "transcripcion-hablantes.txt", "w", encoding="utf-8") as f:
        actual, ini, trozos = None, 0, []
        for s, a in zip(segmentos, asignados):
            if a["voz"] != actual and trozos:
                f.write(f"[{hms(ini)}] {nombres[actual]}: {' '.join(trozos)}\n\n")
                trozos = []
            if not trozos:
                actual, ini = a["voz"], s["i"]
            trozos.append(s["t"].strip())
        if trozos:
            f.write(f"[{hms(ini)}] {nombres[actual]}: {' '.join(trozos)}\n")
    print(f"{slug}: parecido entre muestras {parecido:.2f} · minutos {minutos}", flush=True)


if __name__ == "__main__":
    main()
