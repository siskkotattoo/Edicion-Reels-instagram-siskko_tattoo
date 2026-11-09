"""Efectos de sonido sintéticos (sin derechos): whoosh de transición e impacto."""
import wave

import numpy as np

SR = 48000


def _paso_banda(x, centro):
    """Filtro de 2 polos cuyo centro varía muestra a muestra."""
    from scipy.signal import lfilter
    y = np.zeros_like(x)
    # Procesado por bloques cortos con centro constante en cada bloque.
    bloque = 256
    zi = np.zeros(2)
    for i in range(0, len(x), bloque):
        f = float(np.mean(centro[i:i + bloque]))
        r = 0.97
        w = 2 * np.pi * f / SR
        b = [1 - r, 0, -(1 - r)]
        a = [1, -2 * r * np.cos(w), r * r]
        y[i:i + bloque], zi = lfilter(b, a, x[i:i + bloque], zi=zi)
    return y


def whoosh(dur=0.5, semilla=1):
    n = int(dur * SR)
    t = np.linspace(0, 1, n)
    ruido = np.random.default_rng(semilla).standard_normal(n)
    centro = 300 + 3500 * np.sin(np.pi * t) ** 2
    y = _paso_banda(ruido, centro)
    env = np.sin(np.pi * t) ** 2
    y = y * env
    return y / (np.abs(y).max() + 1e-9)


def impacto(dur=0.9):
    n = int(dur * SR)
    t = np.arange(n) / SR
    boom = np.sin(2 * np.pi * (40 + 120 * np.exp(-t * 18)) * t) * np.exp(-t * 4.5)
    golpe = np.random.default_rng(3).standard_normal(n) * np.exp(-t * 45) * 0.5
    y = boom + golpe
    return y / (np.abs(y).max() + 1e-9)


def pista(ruta, total, whooshes=(), impactos=(), vol_whoosh=0.35, vol_impacto=0.55):
    n = int((total + 1) * SR)
    mezcla = np.zeros((n, 2))

    def poner(m, t, vol, pan=0.0):
        a = int(max(t, 0) * SR)
        if a >= n:
            return
        k = min(len(m), n - a)
        mezcla[a:a + k, 0] += m[:k] * vol * (1 - pan)
        mezcla[a:a + k, 1] += m[:k] * vol * (1 + pan)

    for i, t in enumerate(whooshes):
        w = whoosh(0.5, semilla=i)
        poner(w, t - 0.3, vol_whoosh, 0.25 if i % 2 else -0.25)
    for t in impactos:
        poner(impacto(), t, vol_impacto)
    mezcla = np.clip(mezcla[: int(total * SR)], -1, 1)
    with wave.open(str(ruta), "wb") as f:
        f.setnchannels(2)
        f.setsampwidth(2)
        f.setframerate(SR)
        f.writeframes((mezcla * 32767).astype("<i2").tobytes())
