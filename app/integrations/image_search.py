"""Busqueda de imagenes para el banco de ingles (ENGLISH-TEACHER-PLAN.md, seccion 5).

Tres fuentes gratuitas detras de un mismo Protocol, para que el service no
sepa de HTTP y los tests usen una falsa:
- ARASAAC: pictogramas pensados para comunicacion y aprendizaje; los mejores
  para verbos y adjetivos. Sin key. CC BY-NC-SA (no comercial, con credito).
- Pexels: fotos para sustantivos concretos. Necesita PEXELS_API_KEY (opcional).
- Openverse: respaldo (Wikimedia, Flickr con licencias CC). Sin key.

El LLM no busca imagenes (D2): inventaria URLs y no controla licencias.
"""

from dataclasses import dataclass
from typing import Protocol
from urllib.parse import quote

import httpx

from app.core.logging import get_logger

logger = get_logger(__name__)

ARASAAC_ATTRIBUTION = (
    "Pictograms author: Sergio Palao. Origin: ARASAAC (http://www.arasaac.org). "
    "License: CC (BY-NC-SA). Owner: Government of Aragon (Spain)"
)


class ImageSearchError(Exception):
    """La fuente fallo (caida, timeout, key invalida)."""


@dataclass(frozen=True)
class ImageCandidate:
    url: str
    source: str
    license: str
    attribution: str
    page_url: str | None


class ImageSource(Protocol):
    name: str

    def search(self, query: str, *, limit: int) -> list[ImageCandidate]: ...


class ArasaacSource:
    name = "arasaac"
    BASE = "https://api.arasaac.org/v1/pictograms/en/search/"

    def __init__(self, client: httpx.Client) -> None:
        self._client = client

    def search(self, query: str, *, limit: int) -> list[ImageCandidate]:
        try:
            response = self._client.get(self.BASE + quote(query))
        except httpx.HTTPError as exc:
            raise ImageSearchError(f"ARASAAC: {exc}") from exc
        # Sin resultados, ARASAAC responde 404 en vez de una lista vacia.
        if response.status_code == 404:
            return []
        if response.status_code != 200:
            raise ImageSearchError(f"ARASAAC respondio {response.status_code}")
        pictograms = [p for p in response.json() if not p.get("violence")]

        # Primero los que tienen la palabra exacta como keyword: la busqueda
        # tambien devuelve parecidos ("running shoes" para "run").
        def exact(pictogram: dict) -> bool:
            return any(k.get("keyword", "").lower() == query for k in pictogram.get("keywords", []))

        pictograms.sort(key=lambda p: not exact(p))
        return [
            ImageCandidate(
                url=f"https://static.arasaac.org/pictograms/{p['_id']}/{p['_id']}_500.png",
                source=self.name,
                license="CC BY-NC-SA 4.0",
                attribution=ARASAAC_ATTRIBUTION,
                page_url=f"https://arasaac.org/pictograms/en/{p['_id']}/{quote(query)}",
            )
            for p in pictograms[:limit]
        ]


class PexelsSource:
    name = "pexels"
    URL = "https://api.pexels.com/v1/search"

    def __init__(self, client: httpx.Client, api_key: str) -> None:
        self._client = client
        self._api_key = api_key

    def search(self, query: str, *, limit: int) -> list[ImageCandidate]:
        try:
            response = self._client.get(
                self.URL,
                params={"query": query, "per_page": limit},
                headers={"Authorization": self._api_key},
            )
        except httpx.HTTPError as exc:
            raise ImageSearchError(f"Pexels: {exc}") from exc
        if response.status_code != 200:
            raise ImageSearchError(f"Pexels respondio {response.status_code}")
        return [
            ImageCandidate(
                url=photo["src"]["large"],
                source=self.name,
                license="Pexels License",
                attribution=f"Photo by {photo['photographer']} on Pexels",
                page_url=photo.get("url"),
            )
            for photo in response.json().get("photos", [])[:limit]
        ]


class OpenverseSource:
    name = "openverse"
    URL = "https://api.openverse.org/v1/images/"

    def __init__(self, client: httpx.Client) -> None:
        self._client = client

    def search(self, query: str, *, limit: int) -> list[ImageCandidate]:
        try:
            response = self._client.get(
                self.URL, params={"q": query, "page_size": limit, "mature": "false"}
            )
        except httpx.HTTPError as exc:
            raise ImageSearchError(f"Openverse: {exc}") from exc
        if response.status_code != 200:
            raise ImageSearchError(f"Openverse respondio {response.status_code}")
        candidates = []
        for result in response.json().get("results", [])[:limit]:
            license_name = (
                f"CC {result.get('license', '').upper()} {result.get('license_version', '')}"
            )
            candidates.append(
                ImageCandidate(
                    url=result["url"],
                    source=self.name,
                    license=license_name.strip(),
                    attribution=result.get("attribution") or license_name,
                    page_url=result.get("foreign_landing_url"),
                )
            )
        return candidates


class ImageSearch(Protocol):
    def find(self, word: str, *, pos: str, limit: int) -> list[ImageCandidate]:
        """Candidatas en orden de preferencia segun la categoria gramatical."""
        ...


class MultiSourceImageSearch:
    """Consulta las fuentes en el orden que conviene a cada categoria (seccion 5):
    fotos primero para sustantivos, pictogramas primero para verbos y adjetivos.
    Una fuente caida se salta: las demas pueden alcanzar."""

    def __init__(
        self,
        *,
        arasaac: ImageSource,
        openverse: ImageSource,
        pexels: ImageSource | None,
    ) -> None:
        self._arasaac = arasaac
        self._openverse = openverse
        self._pexels = pexels

    def _sources_for(self, pos: str) -> list[ImageSource]:
        if pos == "noun":
            ordered = [self._pexels, self._arasaac, self._openverse]
        else:
            ordered = [self._arasaac, self._openverse]
        return [source for source in ordered if source is not None]

    def find(self, word: str, *, pos: str, limit: int) -> list[ImageCandidate]:
        found: list[ImageCandidate] = []
        for source in self._sources_for(pos):
            if len(found) >= limit:
                break
            try:
                found.extend(source.search(word, limit=limit - len(found)))
            except ImageSearchError as exc:
                logger.warning("Fuente de imagenes fallo para %r: %s", word, exc)
        return found[:limit]


def build_image_search(*, pexels_api_key: str, timeout_seconds: float) -> MultiSourceImageSearch:
    client = httpx.Client(timeout=timeout_seconds, follow_redirects=True)
    return MultiSourceImageSearch(
        arasaac=ArasaacSource(client),
        openverse=OpenverseSource(client),
        pexels=PexelsSource(client, pexels_api_key) if pexels_api_key else None,
    )
