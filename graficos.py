"""Grafismo de marca (PNG con transparencia) y su animación en ffmpeg."""
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

import estilo


def hex_rgb(c):
    c = c.lstrip("#")
    return tuple(int(c[i:i + 2], 16) for i in (0, 2, 4))


def _texto(d, xy, texto, fuente, color, espaciado):
    x, y = xy
    for ch in texto:
        d.text((x, y), ch, font=fuente, fill=color)
        x += fuente.getlength(ch) + espaciado


def _ancho(texto, fuente, espaciado):
    return int(sum(fuente.getlength(c) for c in texto) + espaciado * (len(texto) - 1))


def _fuente_que_cabe(texto, ruta, tamano, ancho_max, esp_rel):
    while tamano > 20:
        f = ImageFont.truetype(str(ruta), tamano)
        if _ancho(texto, f, round(tamano * esp_rel)) <= ancho_max:
            return f, round(tamano * esp_rel)
        tamano -= 4
    return f, round(tamano * esp_rel)


def texto_png(ruta, texto, ruta_fuente, tamano, color=estilo.BLANCO_ROTO,
              opacidad=1.0, esp_rel=0.04, sombra=True, ancho_max=estilo.ANCHO - 160):
    fuente, esp = _fuente_que_cabe(texto, ruta_fuente, tamano, ancho_max, esp_rel)
    asc, desc = fuente.getmetrics()
    pad = 10
    img = Image.new("RGBA", (_ancho(texto, fuente, esp) + 2 * pad, asc + desc + 2 * pad))
    d = ImageDraw.Draw(img)
    if sombra:
        _texto(d, (pad + 3, pad + 3), texto, fuente, (0, 0, 0, 150), esp)
    _texto(d, (pad, pad), texto, fuente, hex_rgb(color) + (round(255 * opacidad),), esp)
    img.save(ruta)
    return img.size


def rect_png(ruta, w, h, color=estilo.ROJO_SANGRE):
    Image.new("RGBA", (w, h), hex_rgb(color) + (255,)).save(ruta)
    return w, h


def marca_png(ruta):
    """Barra roja sangre + @siskko_tattoo (marca de agua fija)."""
    fuente = ImageFont.truetype(str(estilo.FUENTE), estilo.MARCA_TAMANO)
    esp = round(estilo.MARCA_TAMANO * 0.06)
    texto = estilo.USUARIO
    asc, desc = fuente.getmetrics()
    barra, hueco, pad = 6, 16, 8
    w = barra + hueco + _ancho(texto, fuente, esp) + 2 * pad
    h = asc + desc + 2 * pad
    img = Image.new("RGBA", (w, h))
    d = ImageDraw.Draw(img)
    d.rectangle([pad, pad + 4, pad + barra - 1, h - pad - 4], fill=hex_rgb(estilo.ROJO_SANGRE) + (255,))
    x0 = pad + barra + hueco
    _texto(d, (x0 + 2, pad + 2), texto, fuente, (0, 0, 0, 140), esp)
    _texto(d, (x0, pad), texto, fuente,
           hex_rgb(estilo.BLANCO_ROTO) + (round(255 * estilo.MARCA_OPACIDAD),), esp)
    img.save(ruta)
    return img.size


def rotulo_png(ruta, texto):
    """Etiqueta en caja rojo sangre con texto blanco roto en mayúsculas."""
    texto = texto.upper()
    fuente, esp = _fuente_que_cabe(texto, estilo.FUENTE_TITULO, estilo.ROTULO_TAMANO,
                                   estilo.ANCHO - 220, 0.08)
    asc, desc = fuente.getmetrics()
    px, py = 28, 14
    w = _ancho(texto, fuente, esp) + 2 * px
    h = asc + desc + 2 * py
    img = Image.new("RGBA", (w + 8, h + 8))
    d = ImageDraw.Draw(img)
    d.rectangle([8, 8, w + 7, h + 7], fill=(0, 0, 0, 120))           # sombra
    d.rectangle([0, 0, w - 1, h - 1], fill=hex_rgb(estilo.ROJO_SANGRE) + (240,))
    _texto(d, (px, py - 2), texto, fuente, hex_rgb(estilo.BLANCO_ROTO) + (255,), esp)
    img.save(ruta)
    return img.size


# --- Animación ---------------------------------------------------------------

def _progreso(t0, d):
    return f"min(max((t-{t0:.3f})/{d:.3f},0),1)"


def ease_out(t0, d):
    """0 -> 1 con frenada suave (cúbica)."""
    return f"(1-pow(1-{_progreso(t0, d)},3))"


class Capas:
    """Acumula entradas PNG y filtros overlay animados para un ffmpeg."""

    def __init__(self, primer_indice):
        self.indice = primer_indice
        self.entradas = []
        self.filtros = []

    def capa(self, base, png, x, y, inicio, duracion, *, desde=None,
             fundido_in=0.25, fundido_out=0.3, dur_mov=0.45):
        """Superpone `png` sobre la etiqueta de stream `base`.

        desde: None (solo fundido), "izq", "der", "abajo" (deslizamiento).
        Devuelve la nueva etiqueta de stream.
        """
        i = self.indice
        self.indice += 1
        self.entradas += ["-loop", "1", "-framerate", str(estilo.FPS),
                          "-t", f"{duracion:.3f}", "-i", str(png)]
        fo_st = max(duracion - fundido_out, 0)
        etiqueta = f"c{i}"
        self.filtros.append(
            f"[{i}:v]format=rgba,"
            f"fade=t=in:st=0:d={fundido_in}:alpha=1,"
            f"fade=t=out:st={fo_st:.3f}:d={fundido_out}:alpha=1,"
            f"setpts=PTS-STARTPTS+{inicio:.3f}/TB[p{i}]")
        e = ease_out(inicio, dur_mov)
        xe, ye = str(x), str(y)
        if desde == "izq":
            xe = f"({x})-(w+{x})*(1-{e})"
        elif desde == "der":
            xe = f"({x})+(W-{x})*(1-{e})"
        elif desde == "abajo":
            ye = f"({y})+60*(1-{e})"
        self.filtros.append(
            f"[{base}][p{i}]overlay=x='{xe}':y='{ye}':eval=frame:eof_action=pass:"
            f"enable='between(t,{inicio:.3f},{inicio + duracion:.3f})'[{etiqueta}]")
        return etiqueta


def titulo(capas, base, tmp: Path, texto, subtitulo=None, inicio=0.15,
           duracion=estilo.TITULO_DURACION):
    """Título de apertura: barra roja que entra, título y subtítulo."""
    e = estilo
    th = texto_png(tmp / "titulo.png", texto.upper(), e.FUENTE_TITULO, e.TITULO_TAMANO,
                   esp_rel=0.02)[1]
    alto_barra = th
    if subtitulo:
        sh = texto_png(tmp / "subtitulo.png", subtitulo.upper(), e.FUENTE, 42,
                       opacidad=0.9, esp_rel=0.18)[1]
        alto_barra += sh
    rect_png(tmp / "barra_titulo.png", 12, alto_barra - 20)
    x = 90
    base = capas.capa(base, tmp / "barra_titulo.png", 64, e.TITULO_Y + 10, inicio, duracion,
                      desde="abajo", fundido_in=0.15, dur_mov=0.35)
    base = capas.capa(base, tmp / "titulo.png", x, e.TITULO_Y, inicio + 0.1, duracion - 0.1,
                      desde="izq", dur_mov=0.55)
    if subtitulo:
        base = capas.capa(base, tmp / "subtitulo.png", x + 4, e.TITULO_Y + th - 6,
                          inicio + 0.35, duracion - 0.35, desde="abajo")
    return base
