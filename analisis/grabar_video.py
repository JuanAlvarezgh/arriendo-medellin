"""Graba la animacion a MP4, cuadro por cuadro.

No se graba la pantalla en tiempo real: para cada cuadro se fija el reloj de la
animacion, se espera a que el mapa termine de cargar las teselas de ese
instante y recien ahi se toma la captura. Asi el video sale fluido y nitido
aunque el equipo no alcance a dibujar 30 cuadros por segundo en vivo.

Requiere ffmpeg con libx264 en el PATH.
"""

from __future__ import annotations

import argparse
import functools
import http.server
import shutil
import subprocess
import threading
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

WEB = Path("datos/salidas/web")
SALIDA = Path("datos/salidas/video/arriendo_medellin.mp4")


def _servidor(carpeta: Path, puerto: int) -> http.server.ThreadingHTTPServer:
    manejador = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(carpeta))
    http.server.SimpleHTTPRequestHandler.log_message = lambda *a: None
    s = http.server.ThreadingHTTPServer(("127.0.0.1", puerto), manejador)
    threading.Thread(target=s.serve_forever, daemon=True).start()
    return s


def grabar(salida: Path = SALIDA, ancho: int = 1920, alto: int = 1080, fps: int = 30,
           desde: float = 0.0, hasta: float | None = None, puerto: int = 8795) -> Path:
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise RuntimeError("No se encontro ffmpeg en el PATH.")
    salida.parent.mkdir(parents=True, exist_ok=True)
    servidor = _servidor(WEB, puerto)
    codificador = subprocess.Popen(
        [ffmpeg, "-y", "-loglevel", "error", "-f", "image2pipe", "-framerate", str(fps), "-i", "-",
         "-c:v", "libx264", "-preset", "slow", "-crf", "18", "-pix_fmt", "yuv420p",
         "-movflags", "+faststart", str(salida)],
        stdin=subprocess.PIPE,
    )
    try:
        with sync_playwright() as p:
            nav = p.chromium.launch(args=["--enable-gpu", "--ignore-gpu-blocklist", "--use-angle=d3d11"])
            pagina = nav.new_page(viewport={"width": ancho, "height": alto})
            pagina.goto(f"http://127.0.0.1:{puerto}/animacion.html?grabar=1")
            pagina.wait_for_function("window.listoParaGrabar !== undefined", timeout=60_000)
            pagina.evaluate("Promise.all([window.listoParaGrabar, document.fonts.ready])")
            duracion = hasta if hasta is not None else pagina.evaluate("window.DURACION")
            cuadros = int(round((duracion - desde) * fps)) + 1
            inicio = time.perf_counter()
            for k in range(cuadros):
                pagina.evaluate("t => window.fijarTiempo(t)", desde + k / fps)
                codificador.stdin.write(pagina.screenshot(type="jpeg", quality=95))
                if k % fps == 0:
                    print(f"  segundo {k // fps:>3} de {int(duracion)}  ({time.perf_counter() - inicio:.0f} s)", flush=True)
            nav.close()
    finally:
        codificador.stdin.close()
        codificador.wait()
        servidor.shutdown()
    return salida


if __name__ == "__main__":
    a = argparse.ArgumentParser(description="Graba la animacion del arriendo a MP4.")
    a.add_argument("--fps", type=int, default=30)
    a.add_argument("--ancho", type=int, default=1920)
    a.add_argument("--alto", type=int, default=1080)
    a.add_argument("--desde", type=float, default=0.0)
    a.add_argument("--hasta", type=float, default=None)
    a.add_argument("--salida", type=Path, default=SALIDA)
    args = a.parse_args()
    ruta = grabar(args.salida, args.ancho, args.alto, args.fps, args.desde, args.hasta)
    print(f"video en {ruta}  ({ruta.stat().st_size / 1e6:.1f} MB)")
