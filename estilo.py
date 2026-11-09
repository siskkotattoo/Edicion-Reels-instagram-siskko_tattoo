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
NITIDEZ = 0.5              # realce de la línea del tatuaje
CLARIDAD = 0.35            # contraste local: da volumen al sombreado
FUNDIDO_ENTRADA = 0.35     # segundos desde negro al empezar
FUNDIDO_SALIDA = 0.6       # segundos a negro al terminar

# Realismo ilustrativo: contrastes altos, negros densos, rojo como acento.
LUT_PARAMS = dict(
    exposicion=0.95,       # oscurece ligeramente la imagen
    contraste=1.32,        # curva en S fuerte (alto contraste)
    negro_mate=0.012,      # negros densos con un mínimo de detalle
    techo_blancos=0.97,    # luces brillantes sin quemar
    sat_rojos=1.2,         # rojos: se intensifican
    sat_piel=0.78,         # tonos piel: algo apagados pero naturales
    sat_resto=0.28,        # resto de colores: casi blanco y negro
    sombras_rojizas=0.035, # tinte rojo-negro en sombras
    luces_calidas=0.02,    # luces hacia blanco roto
)

# --- Movimiento y transiciones ---------------------------------------------
# Cualquier transición de ffmpeg xfade (fadeblack, zoomin, slideup,
# circleopen, dissolve, pixelize, ...) más dos propias:
#   "flash" -> destello rojo sangre     "corte" -> corte seco
TRANSICIONES = ["zoomin", "flash", "slideup", "fadeblack"]   # rotan en modo auto
DURACION_TRANSICION = 0.3
ZOOM_VIDEO = 0.05          # empuje lento de cámara en los vídeos (5 %)
ZOOM_CORTE = 0.14          # salto de zoom en cada corte de lo hablado (14 %)
ENCUADRE_ALTURA = 0.42     # al recortar/zoom: 0 = arriba, 0.5 = centro (caras)
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
ROTULO_Y = 330             # bajo la marca, para no chocar con los subtítulos

# --- Subtítulos dinámicos y gancho -------------------------------------------
SUBTITULOS = True
MODELO_SUBTITULOS = "small"   # tiny/base/small/medium: más grande = más preciso y lento
IDIOMA = "es"
VOCABULARIO = ("Tatuaje, realismo ilustrativo, contraste, sombreado, degradado, "
               "línea fina, tinta negra, blackwork, black and grey, piel, "
               "cicatrización, sesión, diseño, siskko.")
FUENTE_SUBTITULO = "Inter Display Black"   # nombre de familia para libass
SUBTITULO_TAMANO = 84
SUBTITULO_Y = 1290         # línea base de los subtítulos
GANCHO_TAMANO = 92
GANCHO_Y = 820
GANCHO_DURACION = 2.2
# Palabras que salen siempre en rojo sangre en los subtítulos.
DESTACAR = ["realismo", "ilustrativo", "contraste", "contrastes", "sombras",
            "negro", "tatuaje", "tinta", "error", "secreto", "nunca", "siempre"]

# --- Efectos de sonido -------------------------------------------------------
SFX = True
SFX_WHOOSH = 0.35          # volumen del whoosh en transiciones
SFX_IMPACTO = 0.55         # volumen del golpe al aparecer el gancho

CIERRE_TEXTO = "@siskko_tattoo"
CIERRE_SUBTEXTO = "CITAS POR DM"
CIERRE_DURACION = 2.8
