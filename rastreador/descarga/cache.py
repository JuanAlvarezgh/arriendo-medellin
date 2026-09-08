"""Cache en disco de respuestas HTTP.

Existe por dos razones: no volver a pedir lo ya descargado cuando el proceso se
reanuda, y poder reprocesar la extraccion sin tocar la red.
"""

from __future__ import annotations

import gzip
import hashlib
import json
import time
from dataclasses import dataclass
from pathlib import Path


@dataclass
class Entrada:
    url: str
    estado: int
    cuerpo: str
    guardado_en: float

    @property
    def edad_horas(self) -> float:
        return (time.time() - self.guardado_en) / 3600


class CacheDisco:
    """Cache de contenido por hash de URL, dividido en subcarpetas.

    Se reparte en 256 subcarpetas para que ningun directorio acumule decenas de
    miles de archivos, que en Windows degrada mucho el acceso.
    """

    def __init__(self, raiz: Path, ttl_horas: float = 168.0) -> None:
        self.raiz = Path(raiz)
        self.raiz.mkdir(parents=True, exist_ok=True)
        self.ttl_horas = ttl_horas
        self.aciertos = 0
        self.fallos = 0

    def _ruta(self, url: str) -> Path:
        h = hashlib.sha256(url.encode("utf-8")).hexdigest()
        sub = self.raiz / h[:2]
        return sub / f"{h}.json.gz"

    def obtener(self, url: str) -> Entrada | None:
        ruta = self._ruta(url)
        if not ruta.exists():
            self.fallos += 1
            return None
        try:
            with gzip.open(ruta, "rt", encoding="utf-8") as fh:
                d = json.load(fh)
        except (OSError, json.JSONDecodeError, EOFError):
            # Archivo corrupto por una interrupcion: se descarta y se vuelve a pedir
            ruta.unlink(missing_ok=True)
            self.fallos += 1
            return None

        entrada = Entrada(**d)
        if entrada.edad_horas > self.ttl_horas:
            self.fallos += 1
            return None
        self.aciertos += 1
        return entrada

    def guardar(self, url: str, estado: int, cuerpo: str) -> None:
        ruta = self._ruta(url)
        ruta.parent.mkdir(parents=True, exist_ok=True)
        d = {"url": url, "estado": estado, "cuerpo": cuerpo, "guardado_en": time.time()}
        # Escritura atomica: se escribe temporal y se renombra, para que una
        # interrupcion no deje un archivo a medias que luego parezca valido.
        tmp = ruta.with_suffix(".tmp")
        with gzip.open(tmp, "wt", encoding="utf-8") as fh:
            json.dump(d, fh)
        tmp.replace(ruta)

    def contiene(self, url: str) -> bool:
        return self._ruta(url).exists()

    @property
    def tasa_aciertos(self) -> float:
        total = self.aciertos + self.fallos
        return self.aciertos / total if total else 0.0
