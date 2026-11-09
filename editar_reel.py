"""Edita un vídeo del iPhone con el estilo de reels de @siskko_tattoo.

Uso:
    python editar_reel.py VIDEO.mov
    python editar_reel.py VIDEO.mov --inicio 2 --fin 25 --salida salida/reel.mp4
    python editar_reel.py VIDEO.mov --musica tema.mp3
"""
import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

import estilo


def hex_rgb(c):
    c = c.lstrip("#")
    return tuple(int(c[i:i + 2], 16) for i in (0, 2, 4))


def analizar(video):
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_streams", "-show_format", "-of", "json", str(video)],
        check=True, capture_output=True, text=True).stdout
    info = json.loads(out)
    v = next(s for s in info["streams"] if s["codec_type"] == "video")
    tiene_audio = any(s["codec_type"] == "audio" for s in info["streams"])
    duracion = float(info["format"]["duration"])
    hdr = v.get("color_transfer") in ("arib-std-b67", "smpte2084")
    return duracion, tiene_audio, hdr


def crear_marca(ruta):
    """PNG con la marca: barra roja sangre + @siskko_tattoo en blanco roto."""
    fuente = ImageFont.truetype(str(estilo.FUENTE), estilo.MARCA_TAMANO)
    espaciado = round(estilo.MARCA_TAMANO * 0.06)
    texto = estilo.USUARIO
    anchos = [fuente.getlength(ch) for ch in texto]
    ancho_txt = int(sum(anchos) + espaciado * (len(texto) - 1))
    asc, desc = fuente.getmetrics()
    barra_w, hueco, pad = 6, 16, 8
    w = barra_w + hueco + ancho_txt + 2 * pad
    h = asc + desc + 2 * pad
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    alpha = round(255 * estilo.MARCA_OPACIDAD)
    d.rectangle([pad, pad + 4, pad + barra_w - 1, h - pad - 4], fill=hex_rgb(estilo.ROJO_SANGRE) + (255,))
    # Sombra suave para que se lea sobre fondos claros.
    x0 = pad + barra_w + hueco
    for dx, dy, col in ((2, 2, (0, 0, 0, 140)), (0, 0, hex_rgb(estilo.BLANCO_ROTO) + (alpha,))):
        x = x0 + dx
        for ch, a in zip(texto, anchos):
            d.text((x, pad + dy), ch, font=fuente, fill=col)
            x += a + espaciado
    img.save(ruta)


def construir_filtro(duracion, hdr):
    e = estilo
    pasos = []
    if hdr:
        # iPhone graba en HLG/Dolby Vision: lo pasamos a SDR Rec.709.
        pasos += [
            "zscale=t=linear:npl=203",
            "format=gbrpf32le",
            "zscale=p=bt709",
            "tonemap=hable:desat=0",
            "zscale=t=bt709:m=bt709:r=tv",
        ]
    pasos += [
        f"scale={e.ANCHO}:{e.ALTO}:force_original_aspect_ratio=increase:flags=lanczos",
        f"crop={e.ANCHO}:{e.ALTO}",
        f"fps={e.FPS}",
        "setsar=1",
        "format=gbrp",
        f"lut3d=file='{e.LUT}':interp=tetrahedral",
        f"unsharp=5:5:{e.NITIDEZ}:5:5:0",
        "format=yuv420p",
        f"vignette=angle={e.VINETA}:mode=forward",
    ]
    if e.GRANO:
        pasos.append(f"noise=c0s={e.GRANO}:c0f=t+u")
    base = ",".join(pasos)
    fin = max(duracion - e.FUNDIDO_SALIDA, 0)
    return (
        f"[0:v]{base}[g];"
        f"[g][1:v]overlay={e.MARCA_X}:{e.MARCA_Y}:format=auto,"
        f"fade=t=in:st=0:d={e.FUNDIDO_ENTRADA}:color={e.NEGRO},"
        f"fade=t=out:st={fin:.3f}:d={e.FUNDIDO_SALIDA}:color={e.NEGRO},"
        f"format=yuv420p[v]"
    )


def filtro_audio(duracion, entrada):
    fin = max(duracion - estilo.FUNDIDO_SALIDA, 0)
    return (
        f"[{entrada}:a]atrim=0:{duracion:.3f},asetpts=PTS-STARTPTS,"
        f"loudnorm=I={estilo.AUDIO_LUFS}:TP=-1.5:LRA=11,"
        f"afade=t=in:st=0:d={estilo.FUNDIDO_ENTRADA},"
        f"afade=t=out:st={fin:.3f}:d={estilo.FUNDIDO_SALIDA},"
        f"aresample=48000[a]"
    )


def main():
    ap = argparse.ArgumentParser(description="Reels con el estilo de @siskko_tattoo")
    ap.add_argument("video", type=Path)
    ap.add_argument("--salida", type=Path)
    ap.add_argument("--inicio", type=float, default=0, help="segundo de inicio del recorte")
    ap.add_argument("--fin", type=float, help="segundo final del recorte")
    ap.add_argument("--musica", type=Path, help="sustituye el audio por esta pista")
    ap.add_argument("--silencio", action="store_true", help="reel sin audio")
    a = ap.parse_args()

    if not estilo.LUT.exists():
        sys.exit("Falta el LUT: ejecuta primero  python generar_lut.py")

    dur_total, tiene_audio, hdr = analizar(a.video)
    fin = min(a.fin, dur_total) if a.fin else dur_total
    duracion = fin - a.inicio
    if duracion <= 0:
        sys.exit("El recorte no tiene duración.")
    if duracion > 180:
        print("Aviso: Instagram limita los reels a 3 minutos.")

    salida = a.salida or Path("salida") / f"{a.video.stem}_siskko.mp4"
    salida.parent.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory() as tmp:
        marca = Path(tmp) / "marca.png"
        crear_marca(marca)

        cmd = ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
               "-ss", f"{a.inicio}", "-t", f"{duracion}", "-i", str(a.video),
               "-i", str(marca)]
        filtro = construir_filtro(duracion, hdr)
        mapas = ["-map", "[v]"]
        if a.musica and not a.silencio:
            cmd += ["-stream_loop", "-1", "-i", str(a.musica)]
            filtro += ";" + filtro_audio(duracion, 2)
            mapas += ["-map", "[a]"]
        elif tiene_audio and not a.silencio:
            filtro += ";" + filtro_audio(duracion, 0)
            mapas += ["-map", "[a]"]

        cmd += ["-filter_complex", filtro, *mapas,
                "-c:v", "libx264", "-preset", "medium", "-crf", str(estilo.CRF),
                "-maxrate", "14M", "-bufsize", "28M",
                "-profile:v", "high", "-level", "4.2", "-pix_fmt", "yuv420p",
                "-color_primaries", "bt709", "-color_trc", "bt709", "-colorspace", "bt709",
                "-g", str(estilo.FPS * 2),
                "-c:a", "aac", "-b:a", "192k",
                "-t", f"{duracion}",
                "-movflags", "+faststart", str(salida)]
        print(f"Editando {a.video.name} ({duracion:.1f}s{', HDR→SDR' if hdr else ''})…")
        subprocess.run(cmd, check=True)
    print(f"Listo: {salida}")


if __name__ == "__main__":
    main()
