"""Base musical oscura generada (libre de derechos) para cuando no hay canción.

Re menor, ~88 BPM: drone de sub-bajo, pad oscuro, bombo, caja con reverb y
hi-hats tipo trap. Uso:  python musica_generada.py salida.wav 30
"""
import sys
import wave

import numpy as np

import estilo

SR = 44100


def _env(n, ataque, caida):
    t = np.arange(n) / SR
    return np.minimum(t / max(ataque, 1e-4), 1) * np.exp(-t / caida)


def paso_bajo(x, corte):
    a = np.exp(-2 * np.pi * corte / SR)
    try:
        from scipy.signal import lfilter
        return lfilter([1 - a], [1, -a], x)
    except ImportError:
        # Equivalente aproximado con media móvil exponencial por FFT.
        n = int(SR / corte)
        k = np.exp(-np.arange(n * 6) / n)
        k /= k.sum()
        return np.convolve(x, k)[: len(x)]


def nota(f, n, armonicos=6, desafinado=0.0):
    t = np.arange(n) / SR
    y = np.zeros(n)
    for d in (-desafinado, 0, desafinado):
        for k in range(1, armonicos + 1):
            y += np.sin(2 * np.pi * f * (1 + d) * k * t) / k
    return y / (3 * 1.6)


def generar(duracion, bpm=estilo.BPM_GENERADA, semilla=7):
    rng = np.random.default_rng(semilla)
    n = int(duracion * SR) + SR
    mezcla = np.zeros((n, 2))
    beat = 60 / bpm
    compas = 4 * beat

    # Progresión Dm - Bb - Gm - A (oscura, tensa).
    acordes = [(146.83, 174.61, 220.0), (116.54, 146.83, 174.61),
               (98.0, 116.54, 146.83), (110.0, 138.59, 164.81)]
    raices = [36.71, 29.14, 49.0, 55.0]
    t0, i = 0.0, 0
    while t0 < duracion + compas:
        a = int(t0 * SR)
        m = int(compas * SR)
        if a >= n:
            break
        m = min(m, n - a)
        pad = sum(nota(f, m, 5, 0.004) for f in acordes[i % 4])
        pad = paso_bajo(pad, 900) * np.minimum(np.arange(m) / (0.4 * SR), 1)
        pad *= np.minimum((m - np.arange(m)) / (0.3 * SR), 1)
        sub = np.sin(2 * np.pi * raices[i % 4] * 2 * np.arange(m) / SR)
        mezcla[a:a + m, 0] += 0.16 * pad + 0.22 * sub
        mezcla[a:a + m, 1] += 0.16 * np.roll(pad, 220) + 0.22 * sub
        t0 += compas
        i += 1

    # Batería.
    nk = int(0.5 * SR)
    tk = np.arange(nk) / SR
    bombo = np.sin(2 * np.pi * (45 + 90 * np.exp(-tk * 30)) * tk) * np.exp(-tk * 7)
    nc = int(0.35 * SR)
    caja = paso_bajo(rng.standard_normal(nc), 4000) * _env(nc, 0.001, 0.09)
    caja += 0.4 * np.sin(2 * np.pi * 190 * np.arange(nc) / SR) * _env(nc, 0.001, 0.05)
    nh = int(0.06 * SR)
    hat = rng.standard_normal(nh)
    hat = (hat - paso_bajo(hat, 7000)) * _env(nh, 0.0005, 0.015)

    def poner(muestra, t, vol, pan=0.0):
        a = int(t * SR)
        if a >= n:
            return
        m = min(len(muestra), n - a)
        mezcla[a:a + m, 0] += muestra[:m] * vol * (1 - pan)
        mezcla[a:a + m, 1] += muestra[:m] * vol * (1 + pan)

    total_beats = int(duracion / beat) + 4
    for b in range(total_beats):
        t = b * beat
        intro = b < 4                      # primer compás: solo ambiente
        if not intro:
            if b % 4 in (0,) or (b % 8 == 6):
                poner(bombo, t, 0.9)
            if b % 8 == 2 and rng.random() < 0.5:
                poner(bombo, t + beat * 0.75, 0.6)
            if b % 4 == 2:
                poner(caja, t, 0.45)
                cola = paso_bajo(rng.standard_normal(int(0.9 * SR)), 2500) * _env(int(0.9 * SR), 0.01, 0.3)
                poner(cola, t, 0.05, 0.3)
            sub_div = 4 if b % 8 == 7 else 2
            for s in range(sub_div):
                poner(hat, t + s * beat / sub_div, 0.18 + 0.06 * (s % 2), 0.25)

    mezcla = mezcla[: int(duracion * SR)]
    # Fundido de salida + limitador suave.
    f = int(1.2 * SR)
    mezcla[-f:] *= np.linspace(1, 0, f)[:, None]
    mezcla = np.tanh(mezcla * 1.3) / np.tanh(1.3)
    return mezcla / max(np.abs(mezcla).max(), 1e-6) * 0.89, bpm


def guardar(ruta, duracion, bpm=estilo.BPM_GENERADA):
    audio, bpm = generar(duracion, bpm)
    with wave.open(str(ruta), "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes((audio * 32767).astype("<i2").tobytes())
    return bpm


if __name__ == "__main__":
    guardar(sys.argv[1], float(sys.argv[2]) if len(sys.argv) > 2 else 30)
