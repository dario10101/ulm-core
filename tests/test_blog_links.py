"""Links del blog (PLAN-BLOG-LINKS.md): validacion por tipo, lista del
usuario, ubicaciones por seccion (en medio y al final) y lectura publica
(solo habilitados, agrupados por categoria, correo y telefono ofuscados)."""

import base64

import pytest

from app.db.models.user import User, UserPermission
from app.services.blog_links import LINK_TYPES, comparison_key, get_link_type, normalize_link
from app.services.blog_section_types import SECTION_TYPES, read_content
from app.services.errors import InvalidBlogLinkError
from tests.conftest import acting_as, client

API = "/api/v1/blog"


def _link(type_: str, url: str, label: str | None = None) -> dict:
    response = client.post(f"{API}/links", json={"type": type_, "url": url, "label": label})
    assert response.status_code == 201, response.text
    return response.json()


def _section(type_: str = "home", **fields) -> dict:
    response = client.post(f"{API}/sections", json={"type": type_, **fields})
    assert response.status_code == 201, response.text
    return response.json()


def _decode(encoded: str) -> str:
    return base64.b64decode(encoded).decode()[::-1]


# --- Validacion por tipo ---


@pytest.mark.parametrize(
    ("type_", "raw", "expected"),
    [
        ("github", "https://github.com/ruben", "https://github.com/ruben"),
        ("github", "github.com/ruben", "https://github.com/ruben"),
        ("github", "https://WWW.GitHub.com/ruben", "https://www.github.com/ruben"),
        ("linkedin", "https://co.linkedin.com/in/ruben", "https://co.linkedin.com/in/ruben"),
        ("x", "https://twitter.com/ruben", "https://twitter.com/ruben"),
        ("youtube", "https://youtu.be/abc", "https://youtu.be/abc"),
        (
            "mercadolibre",
            "https://articulo.mercadolibre.com.co/MCO-1",
            "https://articulo.mercadolibre.com.co/MCO-1",
        ),
        ("mercadolibre", "https://mercadolivre.com.br/x", "https://mercadolivre.com.br/x"),
        ("amazon", "https://amzn.to/3abc", "https://amzn.to/3abc"),
        ("website", "https://mi-sitio.dev/blog", "https://mi-sitio.dev/blog"),
        ("email", "Ruben@Example.COM", "mailto:Ruben@example.com"),
        ("email", "mailto:yo@x.co", "mailto:yo@x.co"),
        ("whatsapp", "+57 300 123 4567", "https://wa.me/573001234567"),
        ("whatsapp", "https://wa.me/573001234567?text=hola", "https://wa.me/573001234567"),
    ],
)
def test_links_are_normalized_by_type(type_, raw, expected):
    assert normalize_link(get_link_type(type_), raw) == expected


@pytest.mark.parametrize(
    ("type_", "raw"),
    [
        ("github", "https://gitlab.com/ruben"),  # otro sitio
        ("github", "https://github.com.evil.io/ruben"),  # dominio que solo lo imita
        ("github", "https://evilgithub.com/ruben"),
        ("github", "http://github.com/ruben"),  # sin https
        ("github", "https://github.com@evil.io/ruben"),  # usuario engañoso
        ("github", "https://github.com:8443/ruben"),  # puerto
        ("website", "javascript:alert(1)"),
        ("website", "https://localhost/x"),
        ("amazon", "https://bit.ly/abc"),  # acortador generico
        ("mercadolibre", "https://mercadolibre.com/x"),
        ("email", "no-es-correo"),
        ("email", "yo@x.co?bcc=otro@x.co"),  # parametros prohibidos
        ("whatsapp", "300 12"),  # muy corto
        ("whatsapp", "+57 300 abc 4567"),
        ("website", "https://x.co/" + "a" * 600),
    ],
)
def test_invalid_links_are_rejected(type_, raw):
    with pytest.raises(InvalidBlogLinkError):
        normalize_link(get_link_type(type_), raw)


def test_comparison_ignores_www_trailing_slash_case_and_utm():
    assert comparison_key("https://www.github.com/Ruben/") == comparison_key(
        "https://github.com/ruben?utm_source=x"
    )
    assert comparison_key("https://github.com/a") != comparison_key("https://github.com/b")


def test_settings_include_the_link_catalog():
    body = client.get(f"{API}/settings").json()

    assert {t["type"] for t in body["link_types"]} == set(LINK_TYPES)
    email = next(t for t in body["link_types"] if t["type"] == "email")
    assert email["sensitive"] is True and email["category"] == "contact"
    assert body["link_categories"][0] == "contact"
    assert body["max_links_per_type"] == 5


# --- Lista del usuario ---


def test_create_list_update_and_delete_a_link():
    link = _link("github", "github.com/ruben")
    assert link["url"] == "https://github.com/ruben"
    assert link["label"] is None and link["used_in"] == 0

    response = client.put(
        f"{API}/links/{link['id']}",
        json={"type": "github", "url": "https://github.com/ruben2", "label": "Mi código"},
    )
    assert response.status_code == 200, response.text
    assert response.json()["label"] == "Mi código"

    assert [item["url"] for item in client.get(f"{API}/links").json()] == [
        "https://github.com/ruben2"
    ]
    assert client.delete(f"{API}/links/{link['id']}").status_code == 204
    assert client.get(f"{API}/links").json() == []
    assert client.delete(f"{API}/links/{link['id']}").status_code == 404


def test_invalid_link_is_422_with_the_reason():
    response = client.post(f"{API}/links", json={"type": "github", "url": "https://x.com/r"})
    assert response.status_code == 422
    assert "GitHub" in response.json()["detail"]
    assert client.post(f"{API}/links", json={"type": "nope", "url": "x"}).status_code == 422


def test_website_requires_a_label():
    response = client.post(f"{API}/links", json={"type": "website", "url": "https://a.dev"})
    assert response.status_code == 422
    _link("website", "https://a.dev", "https://a.dev")  # el mismo link como nombre vale


def test_up_to_five_links_per_type_and_no_repeats():
    for n in range(5):
        _link("email", f"yo{n}@x.co")
    response = client.post(f"{API}/links", json={"type": "email", "url": "otro@x.co"})
    assert response.status_code == 422
    # El tope es por tipo: otro tipo si entra.
    _link("github", "github.com/a")
    repeated = client.post(
        f"{API}/links", json={"type": "github", "url": "https://www.github.com/A/"}
    )
    assert repeated.status_code == 422


def test_updating_a_link_to_itself_is_not_a_repeat():
    link = _link("github", "github.com/a")
    response = client.put(
        f"{API}/links/{link['id']}", json={"type": "github", "url": "github.com/a", "label": "X"}
    )
    assert response.status_code == 200


def test_settings_update_keeps_the_links():
    _link("github", "github.com/a")
    client.put(f"{API}/settings", json={"enabled": True, "display_name": "R"})
    assert len(client.get(f"{API}/links").json()) == 1


def test_links_are_per_user(other_user):
    _link("github", "github.com/a")
    with acting_as(other_user):
        assert client.get(f"{API}/links").json() == []


# --- Ubicaciones por seccion ---


def test_new_links_appear_disabled_in_every_section():
    section = _section()
    link = _link("github", "github.com/a")

    sections = client.get(f"{API}/sections").json()
    assert sections[0]["id"] == section["id"]
    slot = {"id": link["id"], "enabled": False}
    assert sections[0]["links"] == {"inline": [slot], "end": [slot]}


def test_set_section_links_order_and_enabled():
    section = _section()
    a = _link("github", "github.com/a")
    b = _link("email", "a@x.co")
    payload = {
        "inline": [{"id": b["id"], "enabled": True}, {"id": a["id"], "enabled": False}],
        "end": [{"id": a["id"], "enabled": True}],
    }
    response = client.put(f"{API}/sections/{section['id']}/links", json=payload)
    assert response.status_code == 200, response.text
    links = response.json()["links"]
    assert links["inline"] == payload["inline"]
    # Los que faltan se completan al final, deshabilitados.
    assert links["end"] == [{"id": a["id"], "enabled": True}, {"id": b["id"], "enabled": False}]

    used = {item["id"]: item["used_in"] for item in client.get(f"{API}/links").json()}
    assert used == {a["id"]: 1, b["id"]: 1}


def test_set_section_links_rejects_unknown_or_repeated():
    section = _section()
    a = _link("github", "github.com/a")
    url = f"{API}/sections/{section['id']}/links"
    unknown = client.put(url, json={"inline": [{"id": "NOPE", "enabled": True}]})
    assert unknown.status_code == 404
    twice = client.put(
        url, json={"inline": [{"id": a["id"], "enabled": True}, {"id": a["id"], "enabled": False}]}
    )
    assert twice.status_code == 422


def test_deleting_a_link_removes_it_from_the_sections():
    section = _section()
    a = _link("github", "github.com/a")
    client.put(
        f"{API}/sections/{section['id']}/links", json={"end": [{"id": a["id"], "enabled": True}]}
    )

    client.delete(f"{API}/links/{a['id']}")

    assert client.get(f"{API}/sections").json()[0]["links"] == {"inline": [], "end": []}


def test_home_v1_cta_is_dropped_on_read():
    home = SECTION_TYPES["home"]
    content = read_content(
        home, {"headline": "Hola", "cta": {"label": "Escríbeme", "url": "https://a.co"}}, 1
    )
    assert "cta" not in content and content["headline"] == "Hola"


# --- Lectura publica ---


@pytest.fixture
def public_blog(db_session):
    user = db_session.get(User, 1)
    user.username = "ruben"
    db_session.add(UserPermission(user_id=1, permission="blog"))
    db_session.commit()


def test_public_links_only_enabled_grouped_and_obfuscated(public_blog):
    section = _section(enabled=True)
    site = _link("website", "https://a.dev", "Mi sitio")
    github = _link("github", "github.com/a")
    email = _link("email", "yo@x.co", "Escríbeme")
    phone = _link("whatsapp", "+57 300 123 4567")
    hidden = _link("x", "x.com/a")
    client.put(
        f"{API}/sections/{section['id']}/links",
        json={
            "inline": [
                {"id": site["id"], "enabled": True},
                {"id": github["id"], "enabled": True},
                {"id": hidden["id"], "enabled": False},
                {"id": email["id"], "enabled": True},
            ],
            "end": [{"id": phone["id"], "enabled": True}],
        },
    )

    response = client.get("/api/v1/public/blogs/ruben")
    body = response.text
    links = response.json()["sections"][0]["links"]

    # Contacto primero, luego profesional, web al final; el deshabilitado no sale.
    assert [link["type"] for link in links["inline"]] == ["email", "github", "website"]
    assert links["inline"][1] == {
        "type": "github",
        "category": "professional",
        "label": "GitHub",  # sin nombre propio: el del sitio
        "url": "https://github.com/a",
        "encoded": None,
    }
    assert links["inline"][0]["url"] is None
    assert _decode(links["inline"][0]["encoded"]) == "mailto:yo@x.co"
    assert links["end"][0]["label"] == "WhatsApp"
    assert _decode(links["end"][0]["encoded"]) == "https://wa.me/573001234567"
    # Ni el correo ni el telefono ni el link deshabilitado viajan en claro.
    for secret in ("yo@x.co", "573001234567", "x.com/a", site["id"]):
        assert secret not in body
