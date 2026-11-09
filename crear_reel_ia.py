"""Reels 100 % IA: guion -> voz IA -> imágenes IA animadas -> montaje.

    python crear_reel_ia.py guiones/historia_tradicional_americano.json
    python crear_reel_ia.py guiones/x.json --borrador      # render rápido
    python crear_reel_ia.py guiones/x.json --rehacer-imagenes 3 5

Todo se guarda en salida/<titulo_archivo>/ (voz, imágenes, proyecto.json,
reel y portada). Las imágenes ya generadas se reutilizan, así que se puede
retocar el guion o el texto y volver a montar sin esperar.

Voz: Piper (neuronal, local). Imágenes: SD-Turbo (local, CPU).
"""
import argparse
import difflib
import json
import os
import re
import subprocess
import sys
import wave
from pathlib import Path

import estilo
import montar
import subtitulos

os.environ.setdefault("HF_HUB_DISABLE_XET", "1")
MODELOS = estilo.RAIZ / "modelos"
VOCES_URL = "https://huggingface.co/rhasspy/piper-voices/resolve/main/"
MODELO_IMAGEN = "stabilityai/sd-turbo"
PAUSA = 0.28          # silencio entre frases (s)
INICIO_VOZ = 0.35     # la voz entra tras el golpe del gancho


# --------------------------------------------------------------------------- #
# Voz
# --------------------------------------------------------------------------- #

def ruta_voz(nombre):
    destino = MODELOS / "voces" / f"{nombre}.onnx"
    if not destino.exists():
        idioma, region, hablante, calidad = nombre.split("_")[0], nombre.split("-")[0], \
            nombre.split("-")[1], nombre.split("-")[2]
        url = f"{VOCES_URL}{idioma}/{region}/{hablante}/{calidad}/{nombre}"
        destino.parent.mkdir(parents=True, exist_ok=True)
        for ext in (".onnx", ".onnx.json"):
            subprocess.run(["curl", "-sSLf", "-o", str(destino.with_suffix(ext)), url + ext],
                           check=True)
    return destino


def sintetizar(texto, voz, locutor, ritmo, salida):
    subprocess.run([sys.executable, "-m", "piper", "-m", str(ruta_voz(voz)), "-s", str(locutor),
                    "--length-scale", str(ritmo), "-f", str(salida)],
                   input=texto, text=True, check=True, capture_output=True)
    with wave.open(str(salida)) as w:
        return w.getnframes() / w.getframerate()


def recortar_silencio(entrada, salida):
    """Quita el silencio inicial/final que deja el TTS."""
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", str(entrada), "-af",
                    "silenceremove=start_periods=1:start_threshold=-45dB,"
                    "areverse,silenceremove=start_periods=1:start_threshold=-45dB,areverse,"
                    "aresample=48000", "-ac", "1", str(salida)], check=True)
    with wave.open(str(salida)) as w:
        return w.getnframes() / w.getframerate()


# --------------------------------------------------------------------------- #
# Imágenes
# --------------------------------------------------------------------------- #

_pipe = None


def generar_imagen(prompt, salida, semilla):
    global _pipe
    import torch
    from diffusers import AutoPipelineForText2Image
    from PIL import Image, ImageFilter
    if _pipe is None:
        torch.set_num_threads(os.cpu_count() or 4)
        _pipe = AutoPipelineForText2Image.from_pretrained(MODELO_IMAGEN, torch_dtype=torch.float32)
        _pipe.set_progress_bar_config(disable=True)
    img = _pipe(prompt=prompt, num_inference_steps=4, guidance_scale=0.0,
                width=576, height=1024,
                generator=torch.Generator().manual_seed(semilla)).images[0]
    # Escalado a 1080x1920 con realce de detalle.
    img = img.resize((estilo.ANCHO, estilo.ALTO), Image.LANCZOS)
    img = img.filter(ImageFilter.UnsharpMask(radius=2, percent=70, threshold=2))
    img.save(salida, quality=95)


def prompt_escena(guion, escena):
    if escena.get("tipo") == "foto":
        return f"{escena['imagen']}, {guion['estilo_foto']}"
    return f"{escena['imagen']}, {guion['estilo_imagen']}"


# --------------------------------------------------------------------------- #
# Subtítulos: tiempos de Whisper + texto exacto del guion
# --------------------------------------------------------------------------- #

def _norm(p):
    return re.sub(r"[^\wáéíóúüñ]", "", p.lower())


def alinear(texto, palabras_whisper, ini, fin):
    """Asigna a cada palabra del guion el tiempo de la palabra que dijo la voz."""
    mostrar = texto.split()
    if not palabras_whisper:
        paso = (fin - ini) / max(len(mostrar), 1)
        return [(ini + i * paso, ini + (i + 1) * paso, w) for i, w in enumerate(mostrar)]
    a = [_norm(w) for w in mostrar]
    b = [_norm(w[2]) for w in palabras_whisper]
    tiempos = [None] * len(mostrar)
    for bloque in difflib.SequenceMatcher(None, a, b, autojunk=False).get_matching_blocks():
        for k in range(bloque.size):
            pw = palabras_whisper[bloque.b + k]
            tiempos[bloque.a + k] = (pw[0], pw[1])
    # Interpola las que no coinciden (números, nombres propios escritos distinto).
    conocidos = [i for i, t in enumerate(tiempos) if t]
    for i in range(len(tiempos)):
        if tiempos[i]:
            continue
        prev = max([j for j in conocidos if j < i], default=None)
        nxt = min([j for j in conocidos if j > i], default=None)
        t0 = tiempos[prev][1] if prev is not None else ini
        t1 = tiempos[nxt][0] if nxt is not None else fin
        huecos = (nxt if nxt is not None else len(tiempos)) - (prev if prev is not None else -1) - 1
        pos = i - (prev if prev is not None else -1) - 1
        paso = (t1 - t0) / max(huecos, 1)
        tiempos[i] = (t0 + pos * paso, t0 + (pos + 1) * paso)
    # Garantiza tiempos crecientes (por si el emparejamiento se cruza).
    salida, ultimo = [], ini
    for t, w in zip(tiempos, mostrar):
        t0 = max(t[0], ultimo)
        t1 = max(t[1], t0 + 0.05)
        salida.append((t0, t1, w))
        ultimo = t0
    return salida


# --------------------------------------------------------------------------- #
# Proceso completo
# --------------------------------------------------------------------------- #

def main():
    ap = argparse.ArgumentParser(description="Reel 100 % IA para @siskko_tattoo")
    ap.add_argument("guion", type=Path)
    ap.add_argument("--borrador", action="store_true")
    ap.add_argument("--rehacer-imagenes", nargs="*", type=int, default=None,
                    help="números de escena (1..n) a regenerar; sin números = todas")
    ap.add_argument("--semilla", type=int, default=7)
    a = ap.parse_args()

    guion = json.loads(a.guion.read_text())
    nombre = guion.get("titulo_archivo", a.guion.stem)
    carpeta = Path("salida") / nombre
    (carpeta / "voz").mkdir(parents=True, exist_ok=True)
    (carpeta / "imagenes").mkdir(parents=True, exist_ok=True)
    escenas = guion["escenas"]

    # 1) Voz por escena.
    print("Voz IA…")
    duraciones = []
    for i, e in enumerate(escenas):
        crudo = carpeta / "voz" / f"crudo_{i:02d}.wav"
        limpio = carpeta / "voz" / f"escena_{i:02d}.wav"
        sintetizar(e["voz"], guion["voz"], guion.get("locutor", 0),
                   guion.get("ritmo_voz", 1.0), crudo)
        duraciones.append(recortar_silencio(crudo, limpio))
        crudo.unlink()
    # Pista completa con pausas.
    lista = carpeta / "voz" / "lista.txt"
    silencio = carpeta / "voz" / "pausa.wav"
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-t", str(PAUSA), "-i",
                    "anullsrc=r=48000:cl=mono", str(silencio)], check=True)
    lineas = []
    for i in range(len(escenas)):
        lineas.append(f"file 'escena_{i:02d}.wav'")
        if i < len(escenas) - 1:
            lineas.append("file 'pausa.wav'")
    lista.write_text("\n".join(lineas))
    locucion = carpeta / "voz" / "locucion.wav"
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "concat", "-safe", "0", "-i", str(lista),
                    "-af", "highpass=f=70,acompressor=threshold=-20dB:ratio=3:attack=5:release=80,"
                    "equalizer=f=3500:t=q:w=1:g=2", str(locucion)], check=True)
    inicios = []
    t = 0.0
    for d in duraciones:
        inicios.append(t)
        t += d + PAUSA
    fin_voz = t - PAUSA

    # 2) Subtítulos: Whisper da los tiempos, el guion da el texto.
    print("Alineando subtítulos…")
    palabras = []
    for i, e in enumerate(escenas):
        pw = subtitulos.transcribir(carpeta / "voz" / f"escena_{i:02d}.wav")
        pw = [(p[0] + inicios[i], p[1] + inicios[i], p[2]) for p in pw]
        palabras += alinear(e["texto"], pw, inicios[i], inicios[i] + duraciones[i])

    # 3) Imágenes IA.
    print("Imágenes IA…")
    for i, e in enumerate(escenas):
        ruta = carpeta / "imagenes" / f"escena_{i:02d}.jpg"
        rehacer = a.rehacer_imagenes is not None and (not a.rehacer_imagenes or i + 1 in a.rehacer_imagenes)
        if ruta.exists() and not rehacer:
            continue
        print(f"  · escena {i + 1}/{len(escenas)}: {e['imagen'][:60]}…")
        generar_imagen(prompt_escena(guion, e), ruta, a.semilla + i)

    # 4) Proyecto de montaje: cada imagen entra justo cuando empieza su frase.
    T = estilo.DURACION_TRANSICION
    clips = []
    offsets = [0.0] + [INICIO_VOZ + s - T / 2 for s in inicios[1:]]
    for i, e in enumerate(escenas):
        if i + 1 < len(escenas):
            dur = offsets[i + 1] - offsets[i] + T
        else:
            dur = INICIO_VOZ + fin_voz + 0.7 - offsets[i]
        clip = {"foto": str((carpeta / "imagenes" / f"escena_{i:02d}.jpg").resolve()),
                "duracion": round(dur, 3), "zoom": 0.12 if i % 2 == 0 else 0.08,
                "transicion": e.get("transicion", estilo.TRANSICIONES[i % 2 * 2])}
        if "color" in e:
            clip["color"] = e["color"]
        if e.get("rotulo"):
            clip["texto"] = e["rotulo"]
        clips.append(clip)
    # Todas las transiciones duran T salvo "flash"/"corte": recalcula esas.
    proyecto = {
        "salida": str(carpeta / f"{nombre}.mp4"),
        "gancho": guion.get("gancho"),
        "destacar": guion.get("destacar", []),
        "musica": guion.get("musica", "generada"),
        "musica_volumen": guion.get("musica_volumen", 0.55),
        "sincronizar_ritmo": False,
        "duracion_transicion": T,
        "clips": clips,
        "locucion": {"audio": str(locucion.resolve()), "inicio": INICIO_VOZ,
                     "palabras": [list(p) for p in palabras]},
        "cierre": guion.get("cierre", {"texto": estilo.USUARIO, "subtexto": "Sígueme para más"}),
    }
    (carpeta / "proyecto.json").write_text(json.dumps(proyecto, indent=1, ensure_ascii=False))
    print("Montando…")
    montar.montar(proyecto, Path("."), a.borrador)


if __name__ == "__main__":
    main()
