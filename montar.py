"""Montaje profesional de reels de @siskko_tattoo.

Dos formas de uso:

  # 1) Automático: le das vídeos/fotos y monta el reel completo
  python montar.py auto entrada/IMG_1.MOV entrada/IMG_2.MOV entrada/foto.jpg \\
         --titulo "Blackwork" --subtitulo "Brazo completo" --musica entrada/tema.mp3

  # 2) Proyecto: control total con un JSON (ver proyectos/ejemplo.json)
  python montar.py proyecto proyectos/mi_reel.json

Qué hace: recorta, corta silencios, acelera procesos largos (timelapse),
encuadra en 9:16 (con fondo desenfocado si el plano es horizontal), aplica
el color de marca, mueve la cámara (push-in / Ken Burns), anima título y
rótulos, encadena con transiciones sincronizadas al ritmo de la música,
añade música con ducking bajo la voz, viñeta, grano, marca y cierre.
"""
import argparse
import json
import math
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import audio
import estilo
import graficos
import musica_generada
import sfx
import subtitulos

W, H, FPS = estilo.ANCHO, estilo.ALTO, estilo.FPS
EXT_FOTO = {".jpg", ".jpeg", ".png", ".heic", ".heif", ".webp"}


# --------------------------------------------------------------------------- #
# Utilidades
# --------------------------------------------------------------------------- #

def ffmpeg(args, desc=None):
    if desc:
        print(f"  · {desc}")
    res = subprocess.run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", *args],
                         capture_output=True, text=True)
    if res.returncode:
        sys.exit(f"ffmpeg falló ({desc}):\n{res.stderr[-3000:]}")


def sondear(ruta):
    out = subprocess.run(["ffprobe", "-v", "error", "-show_streams", "-show_format",
                          "-of", "json", str(ruta)], check=True, capture_output=True,
                         text=True).stdout
    info = json.loads(out)
    v = next(s for s in info["streams"] if s["codec_type"] == "video")
    w, h = int(v["width"]), int(v["height"])
    rot = 0
    for sd in v.get("side_data_list", []):
        rot = int(sd.get("rotation", rot) or 0)
    rot = int(v.get("tags", {}).get("rotate", rot))
    if abs(rot) % 180 == 90:
        w, h = h, w
    return dict(
        duracion=float(info["format"].get("duration", 0) or 0),
        audio=any(s["codec_type"] == "audio" for s in info["streams"]),
        hdr=v.get("color_transfer") in ("arib-std-b67", "smpte2084"),
        ancho=w, alto=h)


def duracion_real(ruta):
    out = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0",
                          "-show_entries", "format=duration", "-of", "csv=p=0", str(ruta)],
                         capture_output=True, text=True, check=True).stdout
    return float(out.strip())


def resolver(ruta, base):
    p = Path(ruta)
    if p.exists() or p.is_absolute():
        return p
    return (base / p) if (base / p).exists() else p


def foto_a_png(ruta, destino):
    """Abre JPG/HEIC del iPhone respetando la orientación EXIF."""
    from PIL import Image, ImageOps
    try:
        from pillow_heif import register_heif_opener
        register_heif_opener()
    except ImportError:
        pass
    img = ImageOps.exif_transpose(Image.open(ruta)).convert("RGB")
    img.save(destino)
    return img.size


# --------------------------------------------------------------------------- #
# Filtros de imagen
# --------------------------------------------------------------------------- #

FILTRO_HDR = ("zscale=t=linear:npl=203,format=gbrpf32le,zscale=p=bt709,"
              "tonemap=hable:desat=0,zscale=t=bt709:m=bt709:r=tv,format=yuv420p")


def filtro_encuadre(modo, ancho, alto, foco=None, acercar=1.0):
    """Encuadre 9:16. foco=[x, y] (0-1) elige qué parte de la foto queda al
    recortar; acercar>1 entra más cerca del detalle."""
    fx, fy = foco or (0.5, estilo.ENCUADRE_ALTURA)
    if modo == "auto":
        modo = "llenar" if (alto / ancho >= 1.5 or foco) else "relleno"
    if modo == "llenar":
        return (f"scale={int(W * acercar)}:{int(H * acercar)}:force_original_aspect_ratio=increase:"
                f"flags=lanczos,crop={W}:{H}:(iw-ow)*{fx}:(ih-oh)*{fy}")
    # Plano horizontal: imagen completa sobre su propia versión desenfocada.
    return (f"split[ea][eb];[ea]scale={W}:{H}:force_original_aspect_ratio=increase,"
            f"crop={W}:{H},gblur=sigma=40,eq=brightness=-0.12:saturation=0.7[efondo];"
            f"[eb]scale={W}:{H}:force_original_aspect_ratio=decrease:flags=lanczos[efrente];"
            f"[efondo][efrente]overlay=(W-w)/2:(H-h)/2")


def filtro_zoom(zoom, duracion, saltos=(), foco=None):
    """Empuje lento de cámara (zoom<0 = alejarse) + saltos de zoom en los cortes."""
    if not zoom and not saltos:
        return None
    fx, fy = foco or (0.5, estilo.ENCUADRE_ALTURA)
    d = max(duracion, 0.1)
    if (zoom or 0) >= 0:
        f = f"1+{zoom or 0}*t/{d:.3f}"
    else:
        f = f"1+{-zoom}*(1-t/{d:.3f})"
    if saltos:
        f += "+" + str(estilo.ZOOM_CORTE) + "*(" + "+".join(
            f"between(t,{a:.3f},{b:.3f})" for a, b in saltos) + ")"
    f = f"({f})"
    return (f"scale=w='trunc({W}*{f}/2)*2':h='trunc({H}*{f}/2)*2':eval=frame:flags=bicubic,"
            f"crop={W}:{H}:(iw-ow)*{fx}:(ih-oh)*{fy}")


def filtro_color(con_color=True):
    pasos = ["format=gbrp", f"lut3d=file='{estilo.LUT}':interp=tetrahedral"] if con_color else []
    if estilo.CLARIDAD:
        pasos.append(f"unsharp=13:13:{estilo.CLARIDAD}:5:5:0")
    pasos += [f"unsharp=5:5:{estilo.NITIDEZ}:5:5:0", "format=yuv420p", "setsar=1"]
    return ",".join(pasos)


# --------------------------------------------------------------------------- #
# Planificación
# --------------------------------------------------------------------------- #

def tramos_de_palabras(palabras, duracion, pausa=estilo.SILENCIO_MIN,
                       margen=estilo.MARGEN_SILENCIO):
    """Tramos con habla a partir de las marcas de tiempo de cada palabra."""
    tramos = []
    for ini, fin, _ in palabras:
        a, b = max(ini - margen, 0), min(fin + margen, duracion)
        if tramos and a - tramos[-1][1] < pausa:
            tramos[-1] = (tramos[-1][0], max(tramos[-1][1], b))
        else:
            tramos.append((a, b))
    return tramos


def mapear_palabras(palabras, tramos, velocidad):
    """Pasa las palabras del tiempo original al tiempo del clip ya cortado."""
    salida, acumulado = [], 0.0
    for a, b in tramos:
        for ini, fin, txt in palabras:
            if a - 0.05 <= ini < b:
                salida.append(((acumulado + ini - a) / velocidad,
                               (acumulado + min(fin, b) - a) / velocidad, txt))
        acumulado += b - a
    return salida


def planificar(proyecto, base, tmp):
    con_subs = proyecto.get("subtitulos", estilo.SUBTITULOS)
    clips = []
    for c in proyecto["clips"]:
        c = dict(c)
        if "video" in c:
            c["tipo"] = "video"
            c["fuente"] = resolver(c["video"], base)
            info = sondear(c["fuente"])
            c.update(info=info)
            c["inicio"] = float(c.get("inicio", 0))
            c["fin"] = min(float(c.get("fin", info["duracion"])), info["duracion"])
            c["velocidad"] = float(c.get("velocidad", 1))
            largo = c["fin"] - c["inicio"]
            c["palabras"] = []
            if info["audio"] and c["velocidad"] <= 1.5 and (con_subs or c.get("cortar_silencios", True)):
                recorte = tmp / f"audio_{len(clips):02d}.wav"
                subprocess.run(["ffmpeg", "-y", "-v", "error", "-ss", str(c["inicio"]),
                                "-t", str(largo), "-i", str(c["fuente"]), "-vn", str(recorte)],
                               check=True)
                print(f"  · transcribiendo {c['fuente'].name}…")
                c["palabras"] = subtitulos.transcribir(recorte, tmp)
            c.setdefault("voz", bool(c["palabras"]))
            if c.get("cortar_silencios", True) and info["audio"] and c["velocidad"] <= 1.5:
                if c["palabras"]:
                    c["tramos"] = tramos_de_palabras(c["palabras"], largo)
                else:
                    c["tramos"] = audio.tramos_con_sonido(c["fuente"], c["inicio"], c["fin"])
            else:
                c["tramos"] = [(0.0, largo)]
            c.setdefault("zoom", estilo.ZOOM_VIDEO)
        elif "foto" in c:
            c["tipo"] = "foto"
            c["fuente"] = resolver(c["foto"], base)
            c["duracion"] = float(c.get("duracion", estilo.DURACION_FOTO))
            c.setdefault("zoom", estilo.ZOOM_FOTO)
        elif "tarjeta" in c:
            c["tipo"] = "tarjeta"
            c["duracion"] = float(c.get("duracion", 1.6))
        else:
            sys.exit(f"Clip no reconocido: {c}")
        clips.append(c)
    return clips


def duracion_clip(c):
    if c["tipo"] == "video":
        return sum(b - a for a, b in c["tramos"]) / c["velocidad"]
    return c["duracion"]


def recortar_final(c, segundos):
    """Acorta un clip `segundos` por el final (para caer en el golpe)."""
    if c["tipo"] != "video":
        c["duracion"] -= segundos
        return
    resto = segundos * c["velocidad"]
    tramos = list(c["tramos"])
    while resto > 1e-6 and tramos:
        a, b = tramos[-1]
        if b - a > resto:
            tramos[-1] = (a, b - resto)
            resto = 0
        else:
            resto -= b - a
            tramos.pop()
    c["tramos"] = tramos


def transiciones(proyecto, n):
    defecto = proyecto.get("transicion", "rotar")
    lista = []
    for i in range(n):
        t = proyecto["clips"][i].get("transicion", defecto) if i < len(proyecto["clips"]) else defecto
        if t == "rotar":
            t = estilo.TRANSICIONES[i % len(estilo.TRANSICIONES)]
        d = float(proyecto.get("duracion_transicion", estilo.DURACION_TRANSICION))
        if t == "corte":
            d = 1 / FPS
        elif t == "flash":
            d = 0.2
        lista.append((t, d))
    return lista


def sincronizar(clips, trans, golpes_t, duracion_cierre):
    """Ajusta el final de cada clip para que el cambio caiga en un golpe."""
    if not golpes_t:
        return
    durs = [duracion_clip(c) for c in clips] + ([duracion_cierre] if duracion_cierre else [])
    pos = 0.0
    for k in range(len(durs) - 1):
        _, td = trans[k]
        corte = pos + durs[k] - td / 2          # momento visual del cambio
        minimo = pos + 1.0 + td / 2
        candidatos = [g for g in golpes_t if minimo <= g <= corte]
        if candidatos:
            g = candidatos[-1]
            quitar = corte - g
            if quitar < 2.0 and k < len(clips):
                recortar_final(clips[k], quitar)
                durs[k] -= quitar
        pos += durs[k] - td


# --------------------------------------------------------------------------- #
# Render de segmentos
# --------------------------------------------------------------------------- #

def render_segmento(c, i, tmp, hay_musica, borrador):
    salida = tmp / f"seg_{i:02d}.mkv"
    dur = duracion_clip(c)
    entradas, fv, fa = [], [], None

    if c["tipo"] == "video":
        info = c["info"]
        entradas = ["-ss", f"{c['inicio']:.3f}", "-t", f"{c['fin'] - c['inicio']:.3f}",
                    "-i", str(c["fuente"])]
        if info["hdr"]:
            fv.append(FILTRO_HDR)
        fv.append(f"fps={FPS}")
        tramos = c["tramos"]
        completo = len(tramos) == 1 and tramos[0][0] < 0.05
        sel = "+".join(f"between(t,{a:.3f},{b:.3f})" for a, b in tramos)
        if not completo:
            fv += [f"select='{sel}'", f"setpts=N/{FPS}/TB"]
        else:
            fv.append("setpts=PTS-STARTPTS")
        v = c["velocidad"]
        if v != 1:
            fv += [f"setpts=PTS/{v}", f"fps={FPS}"]
        fv.append(filtro_encuadre(c.get("encuadre", "auto"), info["ancho"], info["alto"]))
        c["palabras_out"] = mapear_palabras(c.get("palabras", []), tramos, v)
        if len(tramos) > 1:
            limites, acc = [], 0.0
            for a, b in tramos:
                limites.append((acc / v, (acc + b - a) / v))
                acc += b - a
            c["saltos"] = [limites[j] for j in range(1, len(limites), 2)]
        if info["audio"] and v <= 1.5 and c.get("volumen", 1) > 0:
            vol = c.get("volumen", estilo.VOLUMEN_CLIP_CON_MUSICA if hay_musica and not c.get("voz") else 1.0)
            fa = []
            if not completo:
                fa += [f"aselect='{sel}'", "asetpts=N/SR/TB"]
            else:
                fa.append("asetpts=PTS-STARTPTS")
            if v != 1:
                fa.append(f"atempo={v}")
            fa.append(f"volume={vol}")
    elif c["tipo"] == "foto":
        png = tmp / f"foto_{i:02d}.png"
        ancho, alto = foto_a_png(c["fuente"], png)
        entradas = ["-loop", "1", "-framerate", str(FPS), "-t", f"{dur:.3f}", "-i", str(png)]
        fv.append(filtro_encuadre(c.get("encuadre", "auto"), ancho, alto, c.get("foco"),
                                  float(c.get("acercar", 1.0))))
    else:  # tarjeta de texto sobre negro
        entradas = ["-f", "lavfi", "-t", f"{dur:.3f}", "-i",
                    f"color=c={estilo.NEGRO.replace('#', '0x')}:s={W}x{H}:r={FPS}"]

    zoom = (filtro_zoom(c.get("zoom"), dur, c.get("saltos", ()), c.get("foco"))
            if c["tipo"] != "tarjeta" else None)
    if zoom:
        fv.append(zoom)
    fv.append(filtro_color(c.get("color", True) and c["tipo"] != "tarjeta"))
    fv.append(f"trim=duration={dur:.3f}")

    capas = graficos.Capas(primer_indice=1)
    grafo = f"[0:v]{','.join(fv)}[v0]"
    etiqueta = "v0"
    if c["tipo"] == "tarjeta":
        png = tmp / f"tarjeta_{i:02d}.png"
        graficos.tarjeta_png(png, c["tarjeta"], c.get("subtexto"), c.get("muestras"))
        etiqueta = capas.capa(etiqueta, png, 0, 0, 0.0, dur, desde="abajo", dur_mov=0.5,
                              fundido_in=0.2, fundido_out=0.15)
    if c.get("texto"):
        png = tmp / f"rotulo_{i:02d}.png"
        graficos.rotulo_png(png, c["texto"])
        etiqueta = capas.capa(etiqueta, png, 64, estilo.ROTULO_Y, 0.35,
                              max(dur - 0.75, 0.6), desde="izq")
    if capas.filtros:
        grafo += ";" + ";".join(capas.filtros)

    idx_audio = capas.indice
    if fa:
        grafo += f";[0:a]{','.join(fa)},aresample=48000,aformat=channel_layouts=stereo,apad,atrim=duration={dur:.3f}[a]"
        mapa_audio = []
    else:
        mapa_audio = ["-f", "lavfi", "-t", f"{dur:.3f}", "-i", "anullsrc=r=48000:cl=stereo"]
        grafo += f";[{idx_audio}:a]anull[a]"

    ffmpeg([*entradas, *capas.entradas, *mapa_audio, "-filter_complex", grafo,
            "-map", f"[{etiqueta}]", "-map", "[a]",
            "-c:v", "libx264", "-preset", "ultrafast" if borrador else "veryfast",
            "-crf", "12", "-pix_fmt", "yuv420p", "-c:a", "pcm_s16le",
            "-t", f"{dur:.3f}", str(salida)],
           f"clip {i + 1}: {c['tipo']} ({dur:.1f}s)")
    return salida


def render_cierre(tmp, proyecto, borrador):
    cfg = proyecto.get("cierre", {})
    dur = float(cfg.get("duracion", estilo.CIERRE_DURACION))
    salida = tmp / "seg_cierre.mkv"
    capas = graficos.Capas(primer_indice=1)
    et = "v0"
    texto = cfg.get("texto", estilo.CIERRE_TEXTO)
    sub = cfg.get("subtexto", estilo.CIERRE_SUBTEXTO)
    y = H // 2 - 80
    if estilo.LOGO.exists():
        from PIL import Image
        logo = Image.open(estilo.LOGO).convert("RGBA")
        logo.thumbnail((520, 520))
        logo.save(tmp / "logo.png")
        et = capas.capa(et, tmp / "logo.png", "(W-w)/2", y - logo.height - 60, 0.1,
                        dur - 0.1, desde="abajo", dur_mov=0.6)
    graficos.texto_png(tmp / "cierre.png", texto, estilo.FUENTE_TITULO, 92, esp_rel=0.01)
    graficos.rect_png(tmp / "cierre_linea.png", 240, 8)
    graficos.texto_png(tmp / "cierre_sub.png", sub.upper(), estilo.FUENTE, 40,
                       opacidad=0.9, esp_rel=0.3)
    et = capas.capa(et, tmp / "cierre.png", "(W-w)/2", y, 0.05, dur - 0.05,
                    desde="abajo", dur_mov=0.6)
    et = capas.capa(et, tmp / "cierre_linea.png", "(W-w)/2", y + 150, 0.35, dur - 0.35,
                    desde="izq", dur_mov=0.5)
    et = capas.capa(et, tmp / "cierre_sub.png", "(W-w)/2", y + 190, 0.55, dur - 0.55,
                    desde="abajo")
    grafo = (f"[0:v]format=yuv420p[v0];" + ";".join(capas.filtros) +
             f";[{capas.indice}:a]anull[a]")
    ffmpeg(["-f", "lavfi", "-t", f"{dur:.3f}", "-i",
            f"color=c={estilo.NEGRO.replace('#', '0x')}:s={W}x{H}:r={FPS}",
            *capas.entradas, "-f", "lavfi", "-t", f"{dur:.3f}", "-i",
            "anullsrc=r=48000:cl=stereo", "-filter_complex", grafo,
            "-map", f"[{et}]", "-map", "[a]", "-c:v", "libx264",
            "-preset", "ultrafast" if borrador else "veryfast", "-crf", "12",
            "-pix_fmt", "yuv420p", "-c:a", "pcm_s16le", "-t", f"{dur:.3f}", str(salida)],
           f"cierre ({dur:.1f}s)")
    return salida


# --------------------------------------------------------------------------- #
# Montaje final
# --------------------------------------------------------------------------- #

def montar_final(segmentos, trans, proyecto, musica, musica_inicio, tmp, salida, borrador,
                 idx_titulo=0, palabras_seg=()):
    durs = [duracion_real(s) for s in segmentos]
    n = len(segmentos)
    entradas = []
    for s in segmentos:
        entradas += ["-i", str(s)]
    f = []
    for i in range(n):
        f.append(f"[{i}:v]settb=AVTB,fps={FPS},format=yuv420p[sv{i}]")
    # Encadenado con transiciones.
    v, a = "sv0", "0:a"
    pos = durs[0]
    inicios = [0.0]
    flashes, cambios = [], []
    for k in range(1, n):
        tipo, td = trans[k - 1]
        td = min(td, durs[k - 1] - 0.05, durs[k] - 0.05)
        off = pos - td
        xf = "fade" if tipo in ("flash", "corte") else tipo
        f.append(f"[{v}][sv{k}]xfade=transition={xf}:duration={td:.3f}:offset={off:.3f}[xv{k}]")
        f.append(f"[{a}][{k}:a]acrossfade=d={td:.3f}:c1=tri:c2=tri[xa{k}]")
        v, a = f"xv{k}", f"xa{k}"
        cambios.append(off + td / 2)
        if tipo == "flash":
            flashes.append(off + td / 2)
        inicios.append(off)
        pos = off + durs[k]
    total = pos
    tiene_cierre = segmentos[-1].name == "seg_cierre.mkv"
    inicio_cierre = cambios[-1] if tiene_cierre and cambios else total

    capas = graficos.Capas(primer_indice=n)
    gancho = proyecto.get("gancho")
    # Título de apertura (si hay gancho, entra cuando el gancho se va).
    if proyecto.get("titulo"):
        t_tit = inicios[min(idx_titulo, n - 1)] + (0.15 if idx_titulo == 0 else 0.25)
        if gancho:
            t_tit = max(t_tit, estilo.GANCHO_DURACION + 0.1)
        v = graficos.titulo(capas, v, tmp, proyecto["titulo"], proyecto.get("subtitulo"),
                            inicio=t_tit)
    # Destellos rojo sangre en las transiciones "flash".
    for j, t in enumerate(flashes):
        i = capas.indice
        capas.indice += 1
        capas.entradas += ["-f", "lavfi", "-t", "0.5", "-i",
                           f"color=c={estilo.ROJO_SANGRE.replace('#', '0x')}@1:s={W}x{H}:r={FPS}"]
        capas.filtros.append(
            f"[{i}:v]format=rgba,colorchannelmixer=aa=0.85,fade=t=in:st=0:d=0.1:alpha=1,"
            f"fade=t=out:st=0.12:d=0.38:alpha=1,setpts=PTS-STARTPTS+{t - 0.1:.3f}/TB[fl{j}]")
        capas.filtros.append(
            f"[{v}][fl{j}]overlay=0:0:eof_action=pass:enable='between(t,{t - 0.1:.3f},{t + 0.4:.3f})'[fv{j}]")
        v = f"fv{j}"
    f += capas.filtros
    # Viñeta y grano sobre todo el montaje.
    acabado = [f"vignette=angle={estilo.VINETA}:mode=forward"]
    if estilo.GRANO:
        acabado.append(f"noise=c0s={estilo.GRANO}:c0f=t+u")
    f.append(f"[{v}]{','.join(acabado)}[vg]")
    # Marca de agua (desaparece en el cierre, que ya muestra el usuario).
    marca = tmp / "marca.png"
    graficos.marca_png(marca)
    im = capas.indice
    entradas_extra = list(capas.entradas) + ["-loop", "1", "-framerate", str(FPS),
                                             "-t", f"{total:.3f}", "-i", str(marca)]
    fin_marca = inicio_cierre - 0.2
    f.append(f"[{im}:v]format=rgba,fade=t=in:st=0.4:d=0.5:alpha=1,"
             f"fade=t=out:st={max(fin_marca - 0.3, 0):.3f}:d=0.3:alpha=1[marca]")
    # Subtítulos dinámicos + gancho (libass), por encima del grano.
    palabras = []
    for i, ps in enumerate(palabras_seg):
        palabras += [(a_ + inicios[i], b_ + inicios[i], t_) for a_, b_, t_ in ps
                     if a_ + inicios[i] < inicio_cierre]
    loc = proyecto.get("locucion")
    if loc:
        ini_loc = float(loc.get("inicio", 0))
        palabras += [(p[0] + ini_loc, p[1] + ini_loc, p[2]) for p in loc.get("palabras", [])]
    if gancho:   # mientras se ve el gancho no se duplica el texto abajo
        palabras = [p for p in palabras if p[0] >= estilo.GANCHO_DURACION - 0.05]
    subs = ""
    if palabras or gancho:
        ass = tmp / "subtitulos.ass"
        destacar = list(estilo.DESTACAR) + list(proyecto.get("destacar", []))
        subtitulos.escribir_ass(ass, palabras, destacar, gancho, fin_total=inicio_cierre)
        subs = f"ass=filename='{ass}':fontsdir='{estilo.FUENTE.parent}',"
    f.append(f"[vg][marca]overlay={estilo.MARCA_X}:{estilo.MARCA_Y}:eof_action=pass,{subs}"
             f"fade=t=in:st=0:d={estilo.FUNDIDO_ENTRADA}:color={estilo.NEGRO},"
             f"fade=t=out:st={total - estilo.FUNDIDO_SALIDA:.3f}:d={estilo.FUNDIDO_SALIDA}:color={estilo.NEGRO},"
             f"format=yuv420p[vout]")

    # Locución en off (voz IA o grabada aparte).
    if loc:
        iloc = im + 1
        entradas_extra += ["-i", str(loc["audio"])]
        ms = int(float(loc.get("inicio", 0)) * 1000)
        f.append(f"[{iloc}:a]aresample=48000,aformat=channel_layouts=stereo,"
                 f"adelay={ms}|{ms},apad,atrim=0:{total:.3f}[loc]")
        f.append(f"[{a}][loc]amix=inputs=2:normalize=0:duration=first[conLoc]")
        a = "conLoc"
        im += 1

    # Efectos de sonido: whoosh en cada transición, impacto con el gancho.
    if proyecto.get("sfx", estilo.SFX):
        whooshes = [t for (tipo, _), t in zip(trans, cambios) if tipo != "corte"]
        pista = tmp / "sfx.wav"
        sfx.pista(pista, total, whooshes, [0.06] if gancho else [],
                  estilo.SFX_WHOOSH, estilo.SFX_IMPACTO)
        isfx = im + 1
        entradas_extra += ["-i", str(pista)]
        f.append(f"[{a}][{isfx}:a]amix=inputs=2:normalize=0:duration=first[conSfx]")
        a = "conSfx"
        im += 1

    # Audio: voz/ambiente + música con ducking.
    fin_a = total - estilo.FUNDIDO_SALIDA
    if musica:
        im2 = im + 1
        entradas_extra += ["-stream_loop", "-1", "-ss", f"{musica_inicio:.3f}", "-i", str(musica)]
        vol = proyecto.get("musica_volumen", estilo.MUSICA_VOLUMEN)
        f.append(f"[{a}]aresample=48000,asplit[voz][sc]")
        f.append(f"[{im2}:a]aresample=48000,aformat=channel_layouts=stereo,"
                 f"atrim=0:{total:.3f},asetpts=PTS-STARTPTS,volume={vol},"
                 f"afade=t=in:st=0:d=0.3,afade=t=out:st={total - 1.5:.3f}:d=1.5[mus]")
        f.append("[mus][sc]sidechaincompress=threshold=0.04:ratio=6:attack=15:release=400[musd]")
        f.append(f"[voz][musd]amix=inputs=2:normalize=0:duration=first,")
        f[-1] += (f"loudnorm=I={estilo.AUDIO_LUFS}:TP=-1.5:LRA=11,aresample=48000,"
                  f"afade=t=out:st={fin_a:.3f}:d={estilo.FUNDIDO_SALIDA}[aout]")
    else:
        f.append(f"[{a}]loudnorm=I={estilo.AUDIO_LUFS}:TP=-1.5:LRA=11,aresample=48000,"
                 f"afade=t=out:st={fin_a:.3f}:d={estilo.FUNDIDO_SALIDA}[aout]")

    script = tmp / "grafo.txt"
    script.write_text(";\n".join(f))
    salida.parent.mkdir(parents=True, exist_ok=True)
    ffmpeg([*entradas, *entradas_extra, "-filter_complex_script", str(script),
            "-map", "[vout]", "-map", "[aout]",
            "-c:v", "libx264", "-preset", "ultrafast" if borrador else "medium",
            "-crf", str(estilo.CRF + (6 if borrador else 0)),
            "-maxrate", "14M", "-bufsize", "28M",
            "-profile:v", "high", "-level", "4.2", "-pix_fmt", "yuv420p",
            "-color_primaries", "bt709", "-color_trc", "bt709", "-colorspace", "bt709",
            "-g", str(FPS * 2), "-c:a", "aac", "-b:a", "192k", "-ar", "48000",
            "-t", f"{total:.3f}", "-movflags", "+faststart", str(salida)],
           f"montaje final ({total:.1f}s, {n} partes)")
    return total


def montar(proyecto, base=Path("."), borrador=False):
    if not estilo.LUT.exists():
        subprocess.run([sys.executable, str(estilo.RAIZ / "generar_lut.py")], check=True)
    t0 = time.time()
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        print("Planificando…")
        clips = planificar(proyecto, base, tmp)
        con_cierre = proyecto.get("cierre", {}) is not False
        dur_cierre = float((proyecto.get("cierre") or {}).get("duracion", estilo.CIERRE_DURACION)) if con_cierre else 0
        trans = transiciones(proyecto, len(clips) + (1 if con_cierre else 0))
        if con_cierre:
            trans[len(clips) - 1] = ("fadeblack", 0.4)
        # Música y golpes.
        musica = proyecto.get("musica")
        inicio_m = float(proyecto.get("musica_inicio", 0))
        golpes_t = []
        if musica == "generada":
            bpm = estilo.BPM_GENERADA
            golpes_t = [k * 60 / bpm for k in range(4, 400)]
        elif musica:
            musica = resolver(musica, base)
            golpes_t, bpm = audio.golpes(musica, inicio_m)
            if bpm:
                print(f"  · música: {bpm:.0f} BPM")
        if proyecto.get("sincronizar_ritmo", True) and golpes_t:
            sincronizar(clips, trans, golpes_t, dur_cierre)
        estimado = sum(duracion_clip(c) for c in clips) + dur_cierre - sum(d for _, d in trans[:len(clips) - (0 if con_cierre else 1)])
        if musica == "generada":
            musica = tmp / "musica.wav"
            musica_generada.guardar(musica, estimado + 2)
            inicio_m = 0

        print("Renderizando clips…")
        segmentos = [render_segmento(c, i, tmp, bool(musica), borrador) for i, c in enumerate(clips)]
        if con_cierre:
            segmentos.append(render_cierre(tmp, proyecto, borrador))
        print("Montando…")
        salida = Path(proyecto.get("salida", "salida/reel_siskko.mp4"))
        idx_titulo = next((i for i, c in enumerate(clips) if c["tipo"] != "tarjeta"), 0)
        palabras_seg = [c.get("palabras_out", []) for c in clips]
        total = montar_final(segmentos, trans, proyecto, musica, inicio_m, tmp, salida, borrador,
                             idx_titulo, palabras_seg)
        if proyecto.get("portada", True):
            portada = salida.with_name(salida.stem + "_portada.jpg")
            graficos.portada(portada, segmentos[idx_titulo],
                             proyecto.get("gancho") or proyecto.get("titulo") or "")
            print(f"Portada: {portada}")
    print(f"Listo: {salida}  ({total:.1f}s, {time.time() - t0:.0f}s de render)")
    if total > 180:
        print("Aviso: Instagram limita los reels a 3 minutos.")
    return salida


# --------------------------------------------------------------------------- #
# Modo automático
# --------------------------------------------------------------------------- #

def proyecto_auto(archivos, a):
    videos = [p for p in archivos if p.suffix.lower() not in EXT_FOTO]
    clips = []
    # Reparto del tiempo objetivo entre los vídeos: lo largo se acelera.
    tiempo_fotos = estilo.DURACION_FOTO * (len(archivos) - len(videos))
    por_video = max((a.duracion - tiempo_fotos - estilo.CIERRE_DURACION) / max(len(videos), 1), 2.5)
    for p in archivos:
        if p.suffix.lower() in EXT_FOTO:
            clips.append({"foto": str(p)})
            continue
        c = {"video": str(p), "cortar_silencios": not a.sin_cortes}
        dur = sondear(p)["duracion"]
        if dur > por_video * 1.6 and not a.sin_timelapse:
            c["velocidad"] = round(min(max(dur / por_video, 1.6), 12), 2)
        clips.append(c)
    return {
        "salida": str(a.salida or Path("salida") / f"reel_{time.strftime('%Y%m%d_%H%M')}.mp4"),
        "gancho": a.gancho, "titulo": a.titulo, "subtitulo": a.subtitulo,
        "destacar": a.destacar or [], "subtitulos": not a.sin_subtitulos, "sfx": not a.sin_sfx,
        "clips": clips, "transicion": "rotar",
        "musica": str(a.musica) if a.musica else ("generada" if not a.sin_musica else None),
        "sincronizar_ritmo": True,
    }


def main():
    ap = argparse.ArgumentParser(description="Montaje de reels @siskko_tattoo")
    sub = ap.add_subparsers(dest="modo", required=True)
    pa = sub.add_parser("auto", help="monta automáticamente vídeos y fotos")
    pa.add_argument("archivos", nargs="+", type=Path)
    pa.add_argument("--gancho", help="frase grande del primer segundo")
    pa.add_argument("--destacar", nargs="*", help="palabras extra en rojo en los subtítulos")
    pa.add_argument("--sin-subtitulos", action="store_true")
    pa.add_argument("--sin-sfx", action="store_true")
    pa.add_argument("--titulo")
    pa.add_argument("--subtitulo")
    pa.add_argument("--musica", type=Path)
    pa.add_argument("--sin-musica", action="store_true")
    pa.add_argument("--duracion", type=float, default=30, help="duración objetivo (s)")
    pa.add_argument("--sin-cortes", action="store_true", help="no cortar silencios")
    pa.add_argument("--sin-timelapse", action="store_true")
    pa.add_argument("--salida", type=Path)
    pa.add_argument("--guardar-proyecto", type=Path, help="guarda el JSON generado")
    pa.add_argument("--borrador", action="store_true", help="render rápido de prueba")
    pp = sub.add_parser("proyecto", help="monta a partir de un JSON")
    pp.add_argument("json", type=Path)
    pp.add_argument("--borrador", action="store_true")
    a = ap.parse_args()

    if a.modo == "auto":
        proyecto = proyecto_auto(a.archivos, a)
        if a.guardar_proyecto:
            a.guardar_proyecto.parent.mkdir(parents=True, exist_ok=True)
            a.guardar_proyecto.write_text(json.dumps(proyecto, indent=2, ensure_ascii=False))
        montar(proyecto, Path("."), a.borrador)
    else:
        proyecto = json.loads(a.json.read_text())
        montar(proyecto, a.json.parent, a.borrador)


if __name__ == "__main__":
    main()
