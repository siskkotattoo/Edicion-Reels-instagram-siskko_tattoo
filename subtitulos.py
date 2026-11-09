"""Subtítulos dinámicos palabra a palabra (estilo reels virales) y gancho.

Transcribe con Whisper (faster-whisper, local) y genera un archivo ASS que
ffmpeg pinta con libass: grupos de 2-3 palabras en mayúsculas, la palabra que
se está diciendo en rojo sangre con un pequeño "pop", y los términos clave
siempre en rojo.
"""
import os
import re
import subprocess
from pathlib import Path

import estilo

os.environ.setdefault("HF_HUB_DISABLE_XET", "1")

_modelo = None


def _cargar_modelo():
    global _modelo
    if _modelo is None:
        from faster_whisper import WhisperModel
        _modelo = WhisperModel(estilo.MODELO_SUBTITULOS, device="cpu", compute_type="int8")
    return _modelo


def transcribir(ruta_media, tmp: Path = None):
    """Lista de palabras [(inicio, fin, texto)] en segundos."""
    import numpy as np
    pcm = subprocess.run(["ffmpeg", "-v", "error", "-i", str(ruta_media), "-vn", "-ac", "1",
                          "-ar", "16000", "-af", "loudnorm=I=-18", "-f", "f32le", "-"],
                         capture_output=True, check=True).stdout
    muestras = np.frombuffer(pcm, dtype=np.float32).copy()
    segmentos, _ = _cargar_modelo().transcribe(
        muestras, language=estilo.IDIOMA, word_timestamps=True, vad_filter=True,
        beam_size=5, initial_prompt=estilo.VOCABULARIO)
    palabras = []
    for s in segmentos:
        for w in s.words or []:
            texto = w.word.strip()
            if texto:
                palabras.append((w.start, w.end, texto))
    return palabras


def _limpiar(p):
    return re.sub(r"[^\wáéíóúüñÁÉÍÓÚÜÑ¿?¡!%#@'-]", "", p).upper()


def agrupar(palabras, max_palabras=3, max_chars=16, pausa=0.35):
    """Grupos cortos de palabras; corta en pausas y signos de puntuación."""
    grupos, actual, cortar = [], [], False
    for ini, fin, crudo in palabras:
        txt = _limpiar(crudo)
        if not txt:
            continue
        largo = sum(len(x[2]) + 1 for x in actual) + len(txt)
        if actual and (cortar or len(actual) >= max_palabras or largo > max_chars
                       or ini - actual[-1][1] > pausa):
            grupos.append(actual)
            actual = []
        actual.append((ini, fin, txt))
        cortar = crudo.strip().endswith((".", ",", "?", "!", ";", ":"))
    if actual:
        grupos.append(actual)
    return grupos


def _ass_color(hex_):
    h = hex_.lstrip("#")
    return f"&H00{h[4:6]}{h[2:4]}{h[0:2]}&".upper()


def _t(seg):
    seg = max(seg, 0)
    h, r = divmod(seg, 3600)
    m, s = divmod(r, 60)
    return f"{int(h)}:{int(m):02d}:{s:05.2f}"


def _partir_lineas(texto, max_chars=14):
    lineas, actual = [], ""
    for p in texto.split():
        if actual and len(actual) + 1 + len(p) > max_chars:
            lineas.append(actual)
            actual = p
        else:
            actual = f"{actual} {p}".strip()
    if actual:
        lineas.append(actual)
    return lineas


def escribir_ass(ruta, palabras, destacar=(), gancho=None, fin_total=None):
    rojo = _ass_color(estilo.ROJO_SANGRE)
    blanco = _ass_color(estilo.BLANCO_ROTO)
    margen_v = estilo.ALTO - estilo.SUBTITULO_Y
    clave = {_limpiar(d) for d in destacar}
    cab = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {estilo.ANCHO}
PlayResY: {estilo.ALTO}
WrapStyle: 2
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Sub,{estilo.FUENTE_SUBTITULO},{estilo.SUBTITULO_TAMANO},{blanco},&H000000FF&,&H00000000&,&H99000000&,0,0,0,0,100,100,1,0,1,7,4,2,70,70,{margen_v},1
Style: Gancho,{estilo.FUENTE_SUBTITULO},{estilo.GANCHO_TAMANO},{blanco},&H000000FF&,{rojo},&H00000000&,0,0,0,0,100,100,1,0,3,22,0,5,70,70,0,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    lineas = []
    if gancho:
        txt = r"\N".join(_partir_lineas(gancho.upper()))
        ini, fin = 0.08, estilo.GANCHO_DURACION
        lineas.append(
            f"Dialogue: 1,{_t(ini)},{_t(fin)},Gancho,,0,0,0,,"
            r"{\an5\pos(" f"{estilo.ANCHO // 2},{estilo.GANCHO_Y}" r")\fad(0,180)"
            r"\fscx60\fscy60\t(0,140,\fscx108\fscy108)\t(140,260,\fscx100\fscy100)}" + txt)
    grupos = agrupar(palabras)
    for n_g, g in enumerate(grupos):
        g_ini, g_fin = g[0][0], g[-1][1] + 0.25
        if n_g + 1 < len(grupos):   # nunca se pisa con el grupo siguiente
            g_fin = min(g_fin, grupos[n_g + 1][0][0])
        for k, (w_ini, w_fin, _) in enumerate(g):
            ini = g_ini if k == 0 else w_ini
            fin = g[k + 1][0] if k + 1 < len(g) else g_fin
            if fin_total:
                fin = min(fin, fin_total)
            if fin - ini < 0.04:
                continue
            partes = []
            for j, (_, _, txt) in enumerate(g):
                es_clave = txt.strip("?!.,¿¡") in clave
                if j == k:
                    partes.append(r"{\c" + rojo + r"\t(0,70,\fscx114\fscy114)\t(70,160,\fscx100\fscy100)}"
                                  + txt + r"{\r}")
                elif es_clave:
                    partes.append(r"{\c" + rojo + "}" + txt + r"{\r}")
                else:
                    partes.append(txt)
            entrada = r"{\fscx85\fscy85\t(0,90,\fscx100\fscy100)}" if k == 0 else ""
            lineas.append(f"Dialogue: 0,{_t(ini)},{_t(fin)},Sub,,0,0,0,,{entrada}{' '.join(partes)}")
    Path(ruta).write_text(cab + "\n".join(lineas) + "\n", encoding="utf-8")
