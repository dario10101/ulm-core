"""Catalogo de tipos de seccion del blog (decision B9 de PLAN-BLOG.md).

Patron de registro: cada tipo se declara una vez aca (y su vista/formulario en
el registro del front). Agregar un tipo nuevo es un modelo de contenido + una
entrada en SECTION_TYPES: sin migracion (el contenido es JSON en blg_entities)
ni rutas nuevas.

El contenido de cada plantilla lo valida su modelo al escribir y al leer.
`extra="forbid"`: un campo mal escrito en el formulario es un error, no un dato
que se guarda y nunca se muestra.

Versiones: cada seccion guarda el `schema_version` con el que se escribio su
contenido. Si un modelo cambia de forma, se sube `schema_version` y se agrega
en `upgrades` la funcion que lleva un dict de la version N a la N+1; los
documentos viejos se actualizan al leerlos (y se guardan asi en la siguiente
escritura), sin migracion de base. Es el patron habitual en DynamoDB.
"""

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Annotated, Any, Literal

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, HttpUrl
from pydantic import ValidationError as PydanticValidationError

from app.services.errors import InvalidSectionContentError, UnknownSectionTypeError


def _require_https(url: HttpUrl) -> HttpUrl:
    # Imagenes y links solo por https (B14): una pagina https no carga http
    # (mixed content) y un http filtraria la visita sin cifrar.
    if url.scheme != "https":
        raise ValueError("La URL debe empezar con https://")
    return url


HttpsUrl = Annotated[HttpUrl, AfterValidator(_require_https)]

# Fechas de experiencia/estudios: "2024" o "2024-03". Texto y no date: un CV
# rara vez tiene el dia, y "actual" es la ausencia de `end`.
YearMonth = Annotated[str, Field(pattern=r"^\d{4}(-(0[1-9]|1[0-2]))?$")]

ShortText = Annotated[str, Field(max_length=120)]


class _Content(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class Link(_Content):
    label: Annotated[str, Field(min_length=1, max_length=60)]
    url: HttpsUrl


class Highlight(_Content):
    kind: Literal["project", "product", "link"] = "project"
    title: Annotated[str, Field(min_length=1, max_length=120)]
    description: Annotated[str, Field(max_length=500)] = ""
    image_url: HttpsUrl | None = None
    url: HttpsUrl | None = None


class HomeContent(_Content):
    """Inicio: introduccion general del blog y su proposito; puede presentar
    proyectos y productos."""

    headline: ShortText = ""
    intro: Annotated[str, Field(max_length=5000)] = ""  # markdown
    highlights: Annotated[list[Highlight], Field(max_length=12)] = []
    cta: Link | None = None


class AboutContent(_Content):
    """Sobre mi: introduccion personal."""

    photo_url: HttpsUrl | None = None
    bio: Annotated[str, Field(max_length=10000)] = ""  # markdown
    interests: Annotated[list[Annotated[str, Field(max_length=60)]], Field(max_length=20)] = []
    links: Annotated[list[Link], Field(max_length=10)] = []


class Experience(_Content):
    company: Annotated[str, Field(min_length=1, max_length=120)]
    role: Annotated[str, Field(min_length=1, max_length=120)]
    start: YearMonth
    end: YearMonth | None = None
    description: Annotated[str, Field(max_length=2000)] = ""  # markdown


class Education(_Content):
    institution: Annotated[str, Field(min_length=1, max_length=120)]
    degree: Annotated[str, Field(min_length=1, max_length=120)]
    start: YearMonth | None = None
    end: YearMonth | None = None
    description: Annotated[str, Field(max_length=1000)] = ""


class Certification(_Content):
    name: Annotated[str, Field(min_length=1, max_length=120)]
    issuer: ShortText = ""
    year: Annotated[int, Field(ge=1950, le=2100)] | None = None
    url: HttpsUrl | None = None


class ProfessionalContent(_Content):
    """Perfil profesional."""

    headline: ShortText = ""
    summary: Annotated[str, Field(max_length=10000)] = ""  # markdown
    experience: Annotated[list[Experience], Field(max_length=30)] = []
    education: Annotated[list[Education], Field(max_length=20)] = []
    skills: Annotated[list[Annotated[str, Field(max_length=60)]], Field(max_length=50)] = []
    certifications: Annotated[list[Certification], Field(max_length=30)] = []
    links: Annotated[list[Link], Field(max_length=10)] = []


class CollectionContent(_Content):
    """Coleccion (Proyectos, Libros, How-to...): intro de la seccion y como se
    listan sus elementos. Los elementos (.md) y subsecciones van aparte."""

    intro: Annotated[str, Field(max_length=5000)] = ""  # markdown
    layout: Literal["list", "cards"] = "list"
    sort: Literal["date_desc", "manual", "title"] = "date_desc"


@dataclass(frozen=True)
class SectionType:
    key: str
    # Una sola por usuario (su id es el propio tipo, ver blog_keys).
    singleton: bool
    # Tiene subsecciones y elementos .md.
    has_items: bool
    content_model: type[BaseModel]
    default_label: str
    # Slug por defecto (el "nombre base de la plantilla"). None: se deriva
    # del label (colecciones, que pueden ser varias).
    default_slug: str | None
    schema_version: int = 1
    # version de origen -> funcion que lleva el dict a la version siguiente.
    upgrades: dict[int, Callable[[dict[str, Any]], dict[str, Any]]] = field(default_factory=dict)


SECTION_TYPES: dict[str, SectionType] = {
    section_type.key: section_type
    for section_type in (
        SectionType(
            key="home",
            singleton=True,
            has_items=False,
            content_model=HomeContent,
            default_label="Inicio",
            default_slug="inicio",
        ),
        SectionType(
            key="about",
            singleton=True,
            has_items=False,
            content_model=AboutContent,
            default_label="Sobre mí",
            default_slug="sobre-mi",
        ),
        SectionType(
            key="professional",
            singleton=True,
            has_items=False,
            content_model=ProfessionalContent,
            default_label="Perfil profesional",
            default_slug="perfil",
        ),
        SectionType(
            key="collection",
            singleton=False,
            has_items=True,
            content_model=CollectionContent,
            default_label="Proyectos",
            default_slug=None,
        ),
    )
}


def get_section_type(key: str) -> SectionType:
    try:
        return SECTION_TYPES[key]
    except KeyError:
        raise UnknownSectionTypeError(key) from None


def _describe(exc: PydanticValidationError) -> str:
    """Errores legibles en un toast, con la ruta del campo que fallo:
    `highlights.0.url: La URL debe empezar con https://; ...`."""
    parts = []
    for error in exc.errors():
        location = ".".join(str(part) for part in error["loc"]) or "contenido"
        parts.append(f"{location}: {error['msg']}")
    return "; ".join(parts)


def validate_content(section_type: SectionType, content: dict[str, Any]) -> dict[str, Any]:
    """El contenido validado por el modelo del tipo, listo para guardar (JSON)."""
    try:
        model = section_type.content_model.model_validate(content)
    except PydanticValidationError as exc:
        raise InvalidSectionContentError(_describe(exc)) from exc
    return model.model_dump(mode="json")


def read_content(
    section_type: SectionType, content: dict[str, Any], stored_version: int
) -> dict[str, Any]:
    """El contenido guardado, llevado a la version actual del modelo y validado."""
    for version in range(stored_version, section_type.schema_version):
        content = section_type.upgrades[version](content)
    return validate_content(section_type, content)
