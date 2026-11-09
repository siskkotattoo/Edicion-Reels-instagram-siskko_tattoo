"""Guía de estilo de los reels de @siskko_tattoo.

Todo lo que define el look está aquí: cambia un valor y los próximos
reels saldrán con el ajuste nuevo. Si tocas LUT_PARAMS, ejecuta
`python generar_lut.py`.
"""
from pathlib import Path

RAIZ = Path(__file__).resolve().parent

# --- Paleta: negro + rojo sangre -------------------------------------------
NEGRO = "#0B0B0C"          # negro profundo (fondos, fundidos, cierre)
ROJO_SANGRE = "#B3001B"    # acento de marca
BLANCO_ROTO = "#EDE6DC"    # textos, nunca blanco puro

# --- Formato Instagram Reels -----------------------------------------------
ANCHO, ALTO = 1080, 1920   # 9:16
FPS = 30
CRF = 17                   # calidad H.264 final (más bajo = más calidad)
AUDIO_LUFS = -14           # volumen estándar de Instagram

# --- Look "dark cinematográfico" -------------------------------------------
LUT = RAIZ / "luts" / "siskko_dark_rojo.cube"
VINETA = 0.55              # ángulo del vignette (rad); más alto = más oscuro
GRANO = 7                  # grano de película (0 = sin grano)
NITIDEZ = 0.45             # realce de la línea del tatuaje
FUNDIDO_ENTRADA = 0.35     # segundos desde negro al empezar
FUNDIDO_SALIDA = 0.6       # segundos a negro al terminar

LUT_PARAMS = dict(
    exposicion=0.92,       # oscurece ligeramente la imagen
    contraste=1.18,        # curva en S
    negro_mate=0.025,      # negros levemente levantados (look cine)
    techo_blancos=0.95,    # luces suavizadas
    sat_rojos=1.15,        # rojos: se intensifican
    sat_piel=0.80,         # tonos piel: algo apagados pero naturales
    sat_resto=0.35,        # resto de colores: casi desaturados
    sombras_rojizas=0.035, # tinte rojo-negro en sombras
    luces_calidas=0.02,    # luces hacia blanco roto
)

# --- Movimiento y transiciones ---------------------------------------------
# Cualquier transición de ffmpeg xfade (fadeblack, zoomin, slideup,
# circleopen, dissolve, pixelize, ...) más dos propias:
#   "flash" -> destello rojo sangre     "corte" -> corte seco
TRANSICIONES = ["zoomin", "fadeblack", "flash", "slideup"]   # rotan en modo auto
DURACION_TRANSICION = 0.4
ZOOM_VIDEO = 0.05          # empuje lento de cámara en los vídeos (5 %)
ZOOM_FOTO = 0.10           # efecto Ken Burns en las fotos (10 %)
DURACION_FOTO = 2.5

# --- Limpieza de audio ------------------------------------------------------
UMBRAL_SILENCIO = -35      # dB: por debajo se considera silencio
SILENCIO_MIN = 0.45        # s: silencios más cortos no se cortan
MARGEN_SILENCIO = 0.12     # s de aire que se deja antes/después de hablar

# --- Música -----------------------------------------------------------------
MUSICA_VOLUMEN = 0.75
VOLUMEN_CLIP_CON_MUSICA = 0.3  # sonido ambiente de los clips bajo la música
BPM_GENERADA = 88

# --- Tipografía y marca -----------------------------------------------------
USUARIO = "@siskko_tattoo"
FUENTE = RAIZ / "assets" / "fonts" / "InterDisplay-SemiBold.otf"
FUENTE_TITULO = RAIZ / "assets" / "fonts" / "InterDisplay-Black.otf"
LOGO = RAIZ / "assets" / "logo.png"   # opcional: si existe, sale en el cierre

MARCA_TAMANO = 38
MARCA_OPACIDAD = 0.85
# Zona segura de Reels: arriba ~250 px y abajo ~420 px los tapa la interfaz,
# y a la derecha están los botones.
MARCA_X, MARCA_Y = 64, 250

TITULO_TAMANO = 120
TITULO_Y = 760
TITULO_DURACION = 2.8
ROTULO_TAMANO = 44
ROTULO_Y = 1330

CIERRE_TEXTO = "@siskko_tattoo"
CIERRE_SUBTEXTO = "CITAS POR DM"
CIERRE_DURACION = 2.8
