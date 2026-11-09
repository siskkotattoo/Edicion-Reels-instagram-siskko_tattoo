"""Genera el LUT 3D (.cube) del look dark + rojo sangre de siskko_tattoo."""
import numpy as np

import estilo

N = 33


def rgb_a_hsv(rgb):
    r, g, b = rgb[..., 0], rgb[..., 1], rgb[..., 2]
    mx, mn = rgb.max(-1), rgb.min(-1)
    d = mx - mn
    h = np.zeros_like(mx)
    m = d > 1e-6
    rm = m & (mx == r)
    gm = m & (mx == g) & ~rm
    bm = m & ~rm & ~gm
    h[rm] = ((g - b)[rm] / d[rm]) % 6
    h[gm] = (b - r)[gm] / d[gm] + 2
    h[bm] = (r - g)[bm] / d[bm] + 4
    h = h * 60.0
    s = np.where(mx > 1e-6, d / np.maximum(mx, 1e-6), 0)
    return h, s, mx


def ventana_tono(h, centro, ancho):
    """1 en el centro del tono, cae suavemente a 0 a +-ancho grados."""
    d = np.abs((h - centro + 180) % 360 - 180)
    return np.clip(1 - d / ancho, 0, 1) ** 1.5


def gradar(rgb, p):
    h, s, _ = rgb_a_hsv(rgb)
    pesos = np.array([0.2126, 0.7152, 0.0722])

    # Saturación selectiva conservando la luminancia:
    # rojos vivos, piel natural, el resto casi en blanco y negro.
    w_rojo = ventana_tono(h, 358, 30) * np.clip(s * 3, 0, 1)
    w_piel = ventana_tono(h, 24, 22) * (1 - w_rojo)
    w_resto = np.clip(1 - w_rojo - w_piel, 0, 1)
    factor = w_rojo * p["sat_rojos"] + w_piel * p["sat_piel"] + w_resto * p["sat_resto"]
    luma = rgb @ pesos
    out = luma[..., None] + (rgb - luma[..., None]) * factor[..., None]

    # Rojo sangre: los rojos se oscurecen y pierden el verde que los hace naranjas.
    wr = w_rojo[..., None]
    out = out * (1 - 0.18 * wr) + wr * np.stack(
        [np.zeros_like(h), -0.06 * out[..., 0], 0.02 * out[..., 0]], -1)
    out = np.clip(out, 0, 1)

    # Exposición + contraste en S.
    out = np.clip(out * p["exposicion"], 0, 1)
    out = np.clip(0.5 + (out - 0.5) * p["contraste"], 0, 1)
    out = out * out * (3 - 2 * out) * 0.35 + out * 0.65

    # Split toning: sombras rojo-negro, luces hacia blanco roto (#EDE6DC).
    luma = out @ pesos
    sombra = (1 - luma)[..., None] ** 3
    luz = luma[..., None] ** 2
    out = out + sombra * p["sombras_rojizas"] * np.array([1.0, -0.2, -0.2])
    out = out + luz * p["luces_calidas"] * np.array([0.3, 0.0, -0.6])

    # Negro mate y techo de blancos.
    out = p["negro_mate"] + np.clip(out, 0, 1) * (p["techo_blancos"] - p["negro_mate"])
    return np.clip(out, 0, 1)


def main():
    eje = np.linspace(0, 1, N)
    # .cube: R varía más rápido, luego G, luego B.
    b, g, r = np.meshgrid(eje, eje, eje, indexing="ij")
    rgb = np.stack([r, g, b], -1).reshape(-1, 3)
    out = gradar(rgb, estilo.LUT_PARAMS)
    estilo.LUT.parent.mkdir(exist_ok=True)
    with open(estilo.LUT, "w") as f:
        f.write('TITLE "siskko_tattoo dark rojo sangre"\n')
        f.write(f"LUT_3D_SIZE {N}\n\n")
        for fila in out:
            f.write(f"{fila[0]:.6f} {fila[1]:.6f} {fila[2]:.6f}\n")
    print(f"LUT guardado en {estilo.LUT}")


if __name__ == "__main__":
    main()
