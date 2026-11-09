"""Guía de estilo de los reels de @siskko_tattoo.

Todo lo que define el look está aquí: cambia un valor, vuelve a
ejecutar `python generar_lut.py` (si tocas el color) y los próximos
reels saldrán con el ajuste nuevo.
"""
from pathlib import Path

RAIZ = Path(__file__).resolve().parent

# --- Paleta: negro + rojo sangre -------------------------------------------
NEGRO = "#0B0B0C"          # negro profundo (fondos, fundidos)
ROJO_SANGRE = "#B3001B"    # acento de marca
BLANCO_ROTO = "#EDE6DC"    # textos, sin blanco puro

# --- Formato Instagram Reels -----------------------------------------------
ANCHO, ALTO = 1080, 1920   # 9:16
FPS = 30
CRF = 17                   # calidad H.264 (más bajo = más calidad)
AUDIO_LUFS = -14           # volumen estándar de Instagram

# --- Look "dark cinematográfico" -------------------------------------------
LUT = RAIZ / "luts" / "siskko_dark_rojo.cube"
VINETA = 0.55              # ángulo del vignette (rad); más alto = más oscuro
GRANO = 7                  # intensidad del grano de película (0 = sin grano)
NITIDEZ = 0.45             # realce de detalle de la línea del tatuaje
FUNDIDO_ENTRADA = 0.35     # segundos desde negro
FUNDIDO_SALIDA = 0.6       # segundos a negro

# Parámetros del LUT (los usa generar_lut.py)
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

# --- Marca de agua -----------------------------------------------------------
USUARIO = "@siskko_tattoo"
FUENTE = RAIZ / "assets" / "fonts" / "InterDisplay-SemiBold.otf"
MARCA_TAMANO = 38          # px
MARCA_OPACIDAD = 0.85
# Zona segura de Reels: arriba ~250 px y abajo ~420 px los tapa la interfaz,
# y a la derecha están los botones. La marca va arriba a la izquierda.
MARCA_X, MARCA_Y = 64, 250
