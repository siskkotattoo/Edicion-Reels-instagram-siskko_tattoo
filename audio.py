"""Análisis de audio: silencios a cortar y golpes (beats) de la música."""
import re
import subprocess

import numpy as np

import estilo


def tramos_con_sonido(video, inicio, fin, umbral=estilo.UMBRAL_SILENCIO,
                      minimo=estilo.SILENCIO_MIN, margen=estilo.MARGEN_SILENCIO):
    """Intervalos (relativos a `inicio`) que NO son silencio."""
    duracion = fin - inicio
    res = subprocess.run(
        ["ffmpeg", "-hide_banner", "-nostats", "-ss", str(inicio), "-t", str(duracion),
         "-i", str(video), "-vn", "-af", f"silencedetect=n={umbral}dB:d={minimo}",
         "-f", "null", "-"], capture_output=True, text=True)
    starts = [float(x) for x in re.findall(r"silence_start: (-?[\d.]+)", res.stderr)]
    ends = [float(x) for x in re.findall(r"silence_end: ([\d.]+)", res.stderr)]
    silencios = []
    for i, s in enumerate(starts):
        e = ends[i] if i < len(ends) else duracion
        s, e = max(s, 0) + margen, min(e, duracion) - margen
        if e - s > 0.15:
            silencios.append((s, e))
    tramos, t = [], 0.0
    for s, e in silencios:
        if s - t > 0.2:
            tramos.append((t, s))
        t = e
    if duracion - t > 0.2:
        tramos.append((t, duracion))
    return tramos or [(0.0, duracion)]


def _leer_mono(ruta, sr=11025, inicio=0.0):
    pcm = subprocess.run(
        ["ffmpeg", "-v", "error", "-ss", str(inicio), "-i", str(ruta), "-ac", "1",
         "-ar", str(sr), "-f", "f32le", "-"], capture_output=True, check=True).stdout
    return np.frombuffer(pcm, dtype=np.float32)


def golpes(ruta, inicio=0.0, sr=22050, hop=512):
    """Tiempos (s) de los golpes de la canción, estimando tempo y fase."""
    x = _leer_mono(ruta, sr, inicio)
    if len(x) < sr * 4:
        return [], None
    # Flujo espectral (aumentos de energía por banda) = curva de ataques.
    nfft = 2048
    n = 1 + (len(x) - nfft) // hop
    idx = np.arange(nfft)[None, :] + hop * np.arange(n)[:, None]
    espectro = np.abs(np.fft.rfft(x[idx] * np.hanning(nfft), axis=1))
    espectro = np.log1p(100 * espectro)
    env = np.maximum(np.diff(espectro, axis=0), 0).sum(1)
    env = (env - env.mean()) / (env.std() + 1e-9)
    fps = sr / hop
    # Tempo: autocorrelación ponderada hacia ~110 BPM (preferencia natural).
    ac = np.correlate(env, env, "full")[len(env) - 1:]
    lags = np.arange(1, int(fps * 60 / 60))
    bpm = 60 * fps / lags
    peso = np.exp(-0.5 * (np.log2(bpm / 110) / 0.9) ** 2)
    puntuacion = ac[lags] * peso
    ok = (bpm >= 60) & (bpm <= 180)
    lag = lags[ok][np.argmax(puntuacion[ok])]
    # Afinar el periodo con interpolación sobre el pico.
    if 1 <= lag < len(ac) - 1:
        a_, b_, c_ = ac[lag - 1], ac[lag], ac[lag + 1]
        den = a_ - 2 * b_ + c_
        periodo = lag + (0.5 * (a_ - c_) / den if den else 0)
    else:
        periodo = float(lag)
    # Fase: desplazamiento que más energía de ataque recoge.
    def recoger(f):
        pos = np.round(np.arange(f, len(env), periodo)).astype(int)
        return env[pos[pos < len(env)]].sum()
    fase = max(np.arange(0, periodo, 0.5), key=recoger)
    tiempos = (np.arange(fase, len(env), periodo) + 1) / fps
    return tiempos.tolist(), 60 * fps / periodo
