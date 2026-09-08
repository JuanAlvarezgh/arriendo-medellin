"""Capa e: extraccion asistida por modelo de lenguaje, como ultimo recurso.

Se invoca solo cuando las cuatro capas anteriores fallaron. El resultado se
valida contra el mismo esquema que el resto, asi que un modelo que alucine un
campo produce un registro rechazado, no un dato falso en la base.

Es opcional: sin credencial configurada, la capa se desactiva sola y la cascada
sigue funcionando.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from pathlib import Path
from typing import Any

from ..normalizacion.area import parsear_area
from ..normalizacion.moneda import parsear_precio
from .heuristica import texto_visible

MODELO = "claude-haiku-4-5-20251001"
LIMITE_CARACTERES = 6_000

ESQUEMA_HERRAMIENTA = {
    "name": "registrar_aviso",
    "description": "Registra los datos de un aviso de arriendo inmobiliario.",
    "input_schema": {
        "type": "object",
        "properties": {
            "precio": {
                "type": ["number", "null"],
                "description": "Canon mensual de arriendo en pesos colombianos, sin administracion.",
            },
            "administracion": {"type": ["number", "null"]},
            "area_privada": {"type": ["number", "null"], "description": "Metros cuadrados."},
            "alcobas": {"type": ["integer", "null"]},
            "banos": {"type": ["integer", "null"]},
            "parqueaderos": {"type": ["integer", "null"]},
            "estrato": {"type": ["integer", "null"], "description": "De 1 a 6."},
            "piso": {"type": ["integer", "null"]},
            "direccion": {"type": ["string", "null"]},
            "barrio": {"type": ["string", "null"]},
            "tipo_inmueble": {
                "type": ["string", "null"],
                "enum": ["apartamento", "apartaestudio", "casa", "habitacion", "otro", None],
            },
        },
        "required": [],
    },
}

INSTRUCCION = (
    "Extrae los datos del aviso de arriendo del texto. Reglas: el precio es el canon "
    "mensual, no el valor de venta ni la administracion. Si un dato no aparece "
    "explicitamente, devuelve null; no lo deduzcas ni lo inventes. Los precios van en "
    "pesos colombianos como numero, sin puntos ni simbolos."
)


class ExtractorModelo:
    """Envoltura del modelo con cache en disco y tope de gasto."""

    def __init__(
        self,
        cache_dir: Path | str = "datos/cache/modelo",
        tope_llamadas: int = 500,
        activo: bool | None = None,
    ) -> None:
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.tope_llamadas = tope_llamadas
        self.llamadas = 0
        self.tokens_entrada = 0
        self.tokens_salida = 0
        self._cliente: Any = None
        if activo is None:
            activo = bool(os.environ.get("ANTHROPIC_API_KEY"))
        self.activo = activo

    def _ruta_cache(self, texto: str) -> Path:
        h = hashlib.sha256(texto.encode("utf-8")).hexdigest()
        return self.cache_dir / f"{h}.json"

    def _obtener_cliente(self) -> Any:
        if self._cliente is None:
            try:
                from anthropic import Anthropic
            except ImportError:
                self.activo = False
                return None
            self._cliente = Anthropic()
        return self._cliente

    @property
    def costo_estimado_usd(self) -> float:
        # Haiku 4.5: 1 USD por millon de tokens de entrada, 5 por millon de salida
        return self.tokens_entrada / 1e6 * 1.0 + self.tokens_salida / 1e6 * 5.0

    def extraer(self, html: str, url: str = "") -> dict[str, Any] | None:
        if not self.activo or self.llamadas >= self.tope_llamadas:
            return None

        texto = self._preparar(html)
        if len(texto) < 80:
            return None

        cache = self._ruta_cache(texto)
        if cache.exists():
            try:
                return json.loads(cache.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                cache.unlink(missing_ok=True)

        cliente = self._obtener_cliente()
        if cliente is None:
            return None

        try:
            respuesta = cliente.messages.create(
                model=MODELO,
                max_tokens=1024,
                system=INSTRUCCION,
                tools=[ESQUEMA_HERRAMIENTA],
                tool_choice={"type": "tool", "name": "registrar_aviso"},
                messages=[{"role": "user", "content": f"URL: {url}\n\n{texto}"}],
            )
        except Exception:
            return None

        self.llamadas += 1
        uso = getattr(respuesta, "usage", None)
        if uso:
            self.tokens_entrada += getattr(uso, "input_tokens", 0)
            self.tokens_salida += getattr(uso, "output_tokens", 0)

        campos: dict[str, Any] | None = None
        for bloque in respuesta.content:
            if getattr(bloque, "type", None) == "tool_use":
                campos = dict(bloque.input or {})
                break

        if campos is None:
            return None

        campos = {k: v for k, v in campos.items() if v is not None}
        cache.write_text(json.dumps(campos, ensure_ascii=False), encoding="utf-8")
        return campos or None

    @staticmethod
    def _preparar(html: str) -> str:
        """Reduce la pagina a texto util, para no pagar tokens por maquetado."""
        texto = texto_visible(html)
        texto = re.sub(r"(\s*\|\s*){2,}", " | ", texto)
        return texto[:LIMITE_CARACTERES]


def verificar_coherencia(campos: dict[str, Any], html: str) -> dict[str, Any]:
    """Descarta valores que el modelo afirme pero que no aparezcan en la pagina.

    Es la defensa contra alucinacion: si el modelo reporta un precio que no
    figura en el texto, se elimina en vez de confiar en el.
    """
    if not campos:
        return campos
    visible = texto_visible(html)
    limpio = dict(campos)

    precio = campos.get("precio")
    if precio:
        del_texto, _ = parsear_precio(visible)
        if del_texto is None or abs(del_texto - float(precio)) / max(del_texto, 1) > 0.02:
            # Se acepta solo si el numero aparece literalmente en la pagina
            crudo = f"{int(precio):,}".replace(",", ".")
            if crudo not in visible and str(int(precio)) not in visible:
                limpio.pop("precio", None)

    area = campos.get("area_privada")
    if area:
        del_texto = parsear_area(visible)
        if del_texto is None and str(int(area)) not in visible:
            limpio.pop("area_privada", None)

    return limpio
