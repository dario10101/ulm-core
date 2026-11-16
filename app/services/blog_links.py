"""Catalogo de links del blog (redes, contacto, ventas) y su validacion.

Ver ulm-doc/plans/PLAN-BLOG-LINKS.md. Cada tipo declara su categoria (los links
se muestran agrupados por ella, L3), sus dominios permitidos y como se arma el
link a partir de lo que escribe el usuario. Es la unica fuente de las reglas:
el admin recibe el catalogo en GET /blog/settings y valida con los mismos
datos (sin duplicar las reglas en TypeScript, que terminarian distintas).

Por que validar el dominio: un link con nombre "GitHub" que lleva a otro sitio
es *phishing* por etiqueta engañosa contra los visitantes del blog. Se aceptan
los subdominios de la marca (`co.linkedin.com`, `articulo.mercadolibre.com.co`)
y sus acortadores oficiales (`amzn.to`, `meli.la`), no acortadores genericos.
"""

import base64
import re
from dataclasses import dataclass
from typing import Literal
from urllib.parse import urlsplit

from app.services.blog_documents import LinkSlot
from app.services.errors import InvalidBlogLinkError

LinkKind = Literal["url", "email", "phone"]

# Orden fijo de las categorias en la vista publica (L3).
CATEGORIES = ("contact", "professional", "social", "shop", "support", "web")

MAX_URL_LENGTH = 500
MAX_LABEL_LENGTH = 60

_MERCADOLIBRE_COUNTRIES = (
    "ar",
    "bo",
    "cl",
    "co",
    "cr",
    "do",
    "ec",
    "gt",
    "hn",
    "mx",
    "ni",
    "pa",
    "pe",
    "py",
    "sv",
    "uy",
    "ve",
)
_AMAZON_TLDS = ("com", "com.mx", "com.br", "ca", "es", "co.uk", "de", "fr", "it")


@dataclass(frozen=True)
class LinkType:
    key: str
    # Nombre del sitio: tambien el nombre por defecto del link (L4).
    label: str
    category: str
    kind: LinkKind = "url"
    # Dominios permitidos (y sus subdominios). Vacio: cualquier dominio.
    domains: tuple[str, ...] = ()
    # Exige nombre propio: el de un sitio cualquiera no dice nada (L4).
    requires_label: bool = False
    # Expone un dato personal (correo, telefono): el admin avisa y la API
    # publica lo manda ofuscado (PLAN-BLOG-LINKS.md, 3.1).
    sensitive: bool = False
    placeholder: str = ""


LINK_TYPES: dict[str, LinkType] = {
    t.key: t
    for t in (
        LinkType(
            "email",
            "Email",
            "contact",
            kind="email",
            sensitive=True,
            placeholder="you@example.com",
        ),
        LinkType(
            "whatsapp",
            "WhatsApp",
            "contact",
            kind="phone",
            sensitive=True,
            domains=("wa.me",),
            placeholder="+57 300 123 4567",
        ),
        LinkType(
            "linkedin",
            "LinkedIn",
            "professional",
            domains=("linkedin.com",),
            placeholder="https://www.linkedin.com/in/username",
        ),
        LinkType(
            "github",
            "GitHub",
            "professional",
            domains=("github.com",),
            placeholder="https://github.com/username",
        ),
        LinkType(
            "gitlab",
            "GitLab",
            "professional",
            domains=("gitlab.com",),
            placeholder="https://gitlab.com/username",
        ),
        LinkType(
            "kaggle",
            "Kaggle",
            "professional",
            domains=("kaggle.com",),
            placeholder="https://www.kaggle.com/username",
        ),
        LinkType(
            "x",
            "X",
            "social",
            domains=("x.com", "twitter.com"),
            placeholder="https://x.com/username",
        ),
        LinkType(
            "instagram",
            "Instagram",
            "social",
            domains=("instagram.com",),
            placeholder="https://www.instagram.com/username",
        ),
        LinkType(
            "facebook",
            "Facebook",
            "social",
            domains=("facebook.com", "fb.com"),
            placeholder="https://www.facebook.com/username",
        ),
        LinkType(
            "tiktok",
            "TikTok",
            "social",
            domains=("tiktok.com",),
            placeholder="https://www.tiktok.com/@username",
        ),
        LinkType(
            "youtube",
            "YouTube",
            "social",
            domains=("youtube.com", "youtu.be"),
            placeholder="https://www.youtube.com/@channel",
        ),
        LinkType(
            "mercadolibre",
            "Mercado Libre",
            "shop",
            domains=(
                *(f"mercadolibre.com.{country}" for country in _MERCADOLIBRE_COUNTRIES),
                "mercadolivre.com.br",
                "meli.la",
            ),
            placeholder="https://listado.mercadolibre.com.co/_CustId_123",
        ),
        LinkType(
            "amazon",
            "Amazon",
            "shop",
            domains=(*(f"amazon.{tld}" for tld in _AMAZON_TLDS), "amzn.to", "a.co"),
            placeholder="https://www.amazon.com/shop/username",
        ),
        LinkType(
            "etsy",
            "Etsy",
            "shop",
            domains=("etsy.com", "etsy.me"),
            placeholder="https://www.etsy.com/shop/yourshop",
        ),
        LinkType(
            "udemy",
            "Udemy",
            "shop",
            domains=("udemy.com",),
            placeholder="https://www.udemy.com/user/username",
        ),
        LinkType(
            "buymeacoffee",
            "Buy Me a Coffee",
            "support",
            domains=("buymeacoffee.com",),
            placeholder="https://buymeacoffee.com/username",
        ),
        LinkType(
            "patreon",
            "Patreon",
            "support",
            domains=("patreon.com",),
            placeholder="https://www.patreon.com/username",
        ),
        LinkType(
            "website",
            "Sitio web",
            "web",
            requires_label=True,
            placeholder="https://mysite.com",
        ),
    )
}

# Sin parametros (?bcc=, ?body=): solo la direccion.
_EMAIL = re.compile(r"^[A-Za-z0-9._%+\-]+@[A-Za-z0-9\-]+(\.[A-Za-z0-9\-]+)+$")
# E.164 sin el "+": codigo de pais + numero, 8 a 15 digitos.
_PHONE_DIGITS = re.compile(r"^[1-9]\d{7,14}$")


def get_link_type(key: str) -> LinkType:
    try:
        return LINK_TYPES[key]
    except KeyError:
        raise InvalidBlogLinkError(f"Tipo de link desconocido: {key}") from None


def normalize_link(link_type: LinkType, raw: str) -> str:
    """El link listo para guardar (https://..., mailto:... o https://wa.me/...),
    a partir de lo que escribio el usuario. Error con el motivo si no es valido
    para ese tipo."""
    value = raw.strip()
    if not value:
        raise InvalidBlogLinkError("El link no puede estar vacio")
    if len(value) > MAX_URL_LENGTH:
        raise InvalidBlogLinkError(f"El link puede tener hasta {MAX_URL_LENGTH} caracteres")
    if link_type.kind == "email":
        return _normalize_email(value)
    if link_type.kind == "phone":
        return _normalize_whatsapp(value)
    return _normalize_url(link_type, value)


def _normalize_email(value: str) -> str:
    address = value.removeprefix("mailto:").strip()
    if len(address) > 254 or not _EMAIL.match(address):
        raise InvalidBlogLinkError("Escribe un correo valido, por ejemplo you@example.com")
    local, domain = address.rsplit("@", 1)
    return f"mailto:{local}@{domain.lower()}"


def _normalize_whatsapp(value: str) -> str:
    # Acepta el numero (+57 300 123 4567) o un link wa.me ya armado.
    if value.lower().startswith(("https://wa.me/", "http://wa.me/", "wa.me/")):
        value = value.split("wa.me/", 1)[1].split("?", 1)[0].strip("/")
    digits = re.sub(r"[\s\-().]", "", value).removeprefix("+")
    if not _PHONE_DIGITS.match(digits):
        raise InvalidBlogLinkError(
            "Escribe el numero con codigo de pais, solo digitos (ej. +57 300 123 4567)"
        )
    return f"https://wa.me/{digits}"


def _normalize_url(link_type: LinkType, value: str) -> str:
    if "://" not in value:
        value = f"https://{value}"  # "github.com/ruben" tambien vale
    try:
        parts = urlsplit(value)
        port = parts.port
    except ValueError:
        raise InvalidBlogLinkError("El link no es una URL valida") from None
    if parts.scheme.lower() != "https":
        raise InvalidBlogLinkError("El link debe empezar con https://")
    host = (parts.hostname or "").lower()
    if not host or "." not in host or any(c.isspace() for c in value):
        raise InvalidBlogLinkError("El link no es una URL valida")
    if parts.username or parts.password or port is not None:
        # https://github.com@evil.com: el "usuario" engaña a quien lee el link.
        raise InvalidBlogLinkError("El link no puede llevar usuario, contraseña ni puerto")
    if link_type.domains and not _host_allowed(host, link_type.domains):
        raise InvalidBlogLinkError(
            f"Un link de {link_type.label} debe ser de {', '.join(link_type.domains[:3])}"
            + ("..." if len(link_type.domains) > 3 else "")
        )
    return parts._replace(scheme="https", netloc=host).geturl()


def _host_allowed(host: str, domains: tuple[str, ...]) -> bool:
    return any(host == domain or host.endswith("." + domain) for domain in domains)


def comparison_key(url: str) -> str:
    """Para detectar el mismo link dos veces en un tipo: sin `www.`, sin `/`
    final, sin parametros de campaña (`utm_*`) y en minusculas."""
    if url.startswith("mailto:"):
        return url.lower()
    parts = urlsplit(url)
    query = "&".join(
        pair for pair in parts.query.split("&") if pair and not pair.lower().startswith("utm_")
    )
    host = (parts.hostname or "").removeprefix("www.")
    return f"{host}{parts.path.rstrip('/')}?{query}".lower().rstrip("?")


def obfuscate(url: str) -> str:
    """Barrera basica contra bots que recolectan correos y telefonos en el
    JSON publico: base64 del link invertido. El front lo deshace al hacer clic.
    No es cifrado: quien lea el codigo de ULM lo revierte en una linea."""
    return base64.b64encode(url[::-1].encode()).decode()


# --- Ubicaciones por seccion ---


def merge_slots(slots: list[LinkSlot], link_ids: list[str]) -> list[LinkSlot]:
    """Las ubicaciones guardadas, sin links que ya no existen, y con los links
    que nunca se ubicaron aca al final y deshabilitados (opt-in, L6)."""
    known = set(link_ids)
    kept = [slot for slot in slots if slot.id in known]
    placed = {slot.id for slot in kept}
    missing = [LinkSlot(id=link_id, enabled=False) for link_id in link_ids if link_id not in placed]
    return kept + missing


def category_rank(category: str) -> int:
    """Posicion de la categoria en el orden fijo de la vista publica (L3)."""
    return CATEGORIES.index(category) if category in CATEGORIES else len(CATEGORIES)
