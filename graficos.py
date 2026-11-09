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


# --- Portada -----------------------------------------------------------------

def portada(ruta, video, texto):
    """Portada 1080x1920 para el feed: fotograma + texto grande en cajas rojas.

    El feed de perfil recorta la portada a 3:4 por el centro, así que el texto
    se coloca en la franja central.
    """
    import subprocess
    import tempfile

    from PIL import ImageEnhance

    dur = float(subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0",
         str(video)], capture_output=True, text=True, check=True).stdout)
    with tempfile.TemporaryDirectory() as td:
        png = Path(td) / "f.png"
        subprocess.run(["ffmpeg", "-y", "-v", "error", "-ss", f"{dur * 0.5:.2f}", "-i", str(video),
                        "-frames:v", "1", str(png)], check=True)
        img = Image.open(png).convert("RGB")
    img = ImageEnhance.Contrast(img).enhance(1.12)
    W_, H_ = img.size
    # Degradado oscuro de abajo a arriba para que el texto respire.
    sombra = Image.new("L", (1, H_))
    for y in range(H_):
        sombra.putpixel((0, y), int(170 * max(0, (y / H_ - 0.35) / 0.65) ** 1.4))
    negro = Image.new("RGB", img.size, hex_rgb(estilo.NEGRO))
    img = Image.composite(negro, img, sombra.resize(img.size))
    d = ImageDraw.Draw(img)
    if texto:
        palabras, lineas, actual = texto.upper().split(), [], ""
        for p in palabras:
            if actual and len(actual) + 1 + len(p) > 12:
                lineas.append(actual)
                actual = p
            else:
                actual = f"{actual} {p}".strip()
        lineas.append(actual)
        tam = 104
        fuente = ImageFont.truetype(str(estilo.FUENTE_TITULO), tam)
        while max(fuente.getlength(l) for l in lineas) > W_ - 200 and tam > 50:
            tam -= 6
            fuente = ImageFont.truetype(str(estilo.FUENTE_TITULO), tam)
        alto_l = int(tam * 1.32)
        y = H_ // 2 + 120 - alto_l * len(lineas) // 2
        for i, l in enumerate(lineas):
            w = fuente.getlength(l)
            x = (W_ - w) / 2
            fondo = estilo.ROJO_SANGRE if i % 2 == 0 else estilo.BLANCO_ROTO
            color = estilo.BLANCO_ROTO if i % 2 == 0 else estilo.NEGRO
            d.rectangle([x - 26, y - 8, x + w + 26, y + alto_l - 14], fill=hex_rgb(fondo))
            d.text((x, y - tam * 0.06), l, font=fuente, fill=hex_rgb(color))
            y += alto_l
    marca = ImageFont.truetype(str(estilo.FUENTE), 40)
    t = estilo.USUARIO
    w = marca.getlength(t)
    d.text(((W_ - w) / 2, H_ // 2 + 560), t, font=marca, fill=hex_rgb(estilo.BLANCO_ROTO))
    d.rectangle([(W_ - 120) / 2, H_ // 2 + 620, (W_ + 120) / 2, H_ // 2 + 626],
                fill=hex_rgb(estilo.ROJO_SANGRE))
    img.save(ruta, quality=92)


# --- Tarjetas tipográficas ---------------------------------------------------

def tarjeta_png(ruta, texto, subtexto=None, muestras=None):
    """Lienzo transparente 1080x1920 con tipografía grande de marca.

    texto: líneas separadas por "|"; las palabras entre *asteriscos* van en
    rojo sangre. subtexto: línea pequeña espaciada. muestras: lista de
    colores HEX que se dibujan como círculos (p. ej. la paleta tradicional).
    """
    W_, H_ = estilo.ANCHO, estilo.ALTO
    img = Image.new("RGBA", (W_, H_))
    d = ImageDraw.Draw(img)
    lineas = [l.strip() for l in texto.upper().split("|")]
    tam = 150
    def medir(t, f):
        return f.getlength(t.replace("*", ""))
    while True:
        f = ImageFont.truetype(str(estilo.FUENTE_TITULO), tam)
        if max(medir(l, f) for l in lineas) <= W_ - 150 or tam <= 60:
            break
        tam -= 6
    alto_l = int(tam * 1.05)
    alto_total = alto_l * len(lineas) + (90 if subtexto else 0) + (190 if muestras else 0)
    y = (H_ - alto_total) // 2 - 60
    for l in lineas:
        x = (W_ - medir(l, f)) / 2
        rojo = False
        for trozo in l.split("*"):
            if trozo:
                col = hex_rgb(estilo.ROJO_SANGRE if rojo else estilo.BLANCO_ROTO)
                d.text((x + 4, y + 5), trozo, font=f, fill=(0, 0, 0, 160))
                d.text((x, y), trozo, font=f, fill=col + (255,))
                x += f.getlength(trozo)
            rojo = not rojo
        y += alto_l
    y += 34
    d.rectangle([(W_ - 160) / 2, y, (W_ + 160) / 2, y + 9], fill=hex_rgb(estilo.ROJO_SANGRE) + (255,))
    y += 40
    if subtexto:
        st = subtexto.upper()
        tam_s, esp = 44, 10
        while True:
            fs = ImageFont.truetype(str(estilo.FUENTE), tam_s)
            ancho = sum(fs.getlength(c) for c in st) + esp * (len(st) - 1)
            if ancho <= W_ - 160 or tam_s <= 26:
                break
            tam_s -= 2
            esp = max(4, round(tam_s * 0.2))
        _texto(d, ((W_ - ancho) / 2, y), st, fs, hex_rgb(estilo.BLANCO_ROTO) + (230,), esp)
        y += 90
    if muestras:
        r, sep = 62, 46
        total = len(muestras) * 2 * r + (len(muestras) - 1) * sep
        x = (W_ - total) / 2
        for c in muestras:
            d.ellipse([x, y + 20, x + 2 * r, y + 20 + 2 * r], fill=hex_rgb(c) + (255,),
                      outline=hex_rgb(estilo.BLANCO_ROTO) + (255,), width=5)
            x += 2 * r + sep
    img.save(ruta)
