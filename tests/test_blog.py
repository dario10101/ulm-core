"""Username (de la cuenta) y lectura publica de blogs.

El username se crea una vez desde /me/username; con el, y el permiso `blog`,
el usuario tiene blog publico en /public/blogs/<username>, que se lee sin
sesion.
"""

from datetime import UTC, datetime

import pytest

from app.db.models.user import User, UserPermission
from app.services.errors import InvalidUsernameError
from app.services.username import validate_username
from tests.conftest import OTHER_USER_ID, acting_as, client

API = "/api/v1"


def _set_username(username: str):
    return client.put(f"{API}/me/username", json={"username": username})


def _give_username(db_session, user_id: int, username: str) -> None:
    db_session.get(User, user_id).username = username
    db_session.commit()


def _grant_blog(db_session, user_id: int = 1) -> None:
    db_session.add(UserPermission(user_id=user_id, permission="blog"))
    db_session.commit()


# --- Formato (reglas puras) ---


@pytest.mark.parametrize(
    ("raw", "expected"),
    [("ruben", "ruben"), ("  Ruben-D21 ", "ruben-d21"), ("abc", "abc"), ("a" * 30, "a" * 30)],
)
def test_valid_usernames_are_normalized(raw, expected):
    assert validate_username(raw) == expected


@pytest.mark.parametrize(
    "raw",
    [
        "ab",  # corto
        "a" * 31,  # largo
        "-ruben",
        "ruben-",
        "ru--ben",
        "ru ben",
        "ru_ben",
        "ru.ben",
        "rubén",  # no ASCII
        "аdmin",  # "а" cirilica: homoglifo de admin
        "admin",  # reservado
        "Blog",  # reservado, sin importar mayusculas
    ],
)
def test_invalid_usernames_are_rejected(raw):
    with pytest.raises(InvalidUsernameError):
        validate_username(raw)


# --- PUT /me/username ---


def test_set_username_saves_it_normalized_and_me_returns_it():
    response = _set_username("Ruben-D")

    assert response.status_code == 200
    assert response.json()["username"] == "ruben-d"
    assert client.get(f"{API}/me").json()["username"] == "ruben-d"


def test_me_has_no_username_until_it_is_created():
    assert client.get(f"{API}/me").json()["username"] is None


def test_invalid_username_is_a_422_with_the_reason():
    response = _set_username("admin")

    assert response.status_code == 422
    assert "reservado" in response.json()["detail"]


def test_username_of_another_user_is_a_409_regardless_of_case(db_session, other_user):
    _give_username(db_session, other_user, "ruben")

    response = _set_username("RUBEN")

    assert response.status_code == 409
    assert client.get(f"{API}/me").json()["username"] is None


def test_username_cannot_be_changed_once_created():
    assert _set_username("ruben").status_code == 200

    response = _set_username("otro-nombre")

    assert response.status_code == 409
    assert client.get(f"{API}/me").json()["username"] == "ruben"


def test_each_user_sets_only_their_own_username(db_session, other_user):
    with acting_as(OTHER_USER_ID):
        assert _set_username("otra").status_code == 200

    assert db_session.get(User, 1).username is None
    assert db_session.get(User, OTHER_USER_ID).username == "otra"


def test_set_username_needs_no_domain_permission(real_permissions):
    """Es de la cuenta (y futuro login), no del modulo blog."""
    assert _set_username("ruben").status_code == 200


# --- GET /public/blogs/{username} ---


@pytest.fixture
def public_blog(db_session):
    _give_username(db_session, 1, "ruben")
    _grant_blog(db_session)


@pytest.mark.usefixtures("public_blog", "real_auth", "real_permissions")
def test_public_blog_is_read_without_session():
    response = client.get(f"{API}/public/blogs/ruben")

    assert response.status_code == 200
    # Solo lo publico: ni id, ni email, ni nombre de Google, ni avatar.
    assert response.json() == {"username": "ruben"}


@pytest.mark.usefixtures("public_blog", "real_auth", "real_permissions")
def test_public_blog_url_ignores_case():
    assert client.get(f"{API}/public/blogs/Ruben").status_code == 200


@pytest.mark.usefixtures("real_auth", "real_permissions")
def test_unknown_username_is_a_404():
    assert client.get(f"{API}/public/blogs/nadie").status_code == 404


@pytest.mark.usefixtures("real_auth", "real_permissions")
def test_blog_without_the_blog_permission_is_a_404(db_session):
    _give_username(db_session, 1, "ruben")

    response = client.get(f"{API}/public/blogs/ruben")

    assert response.status_code == 404
    # Mismo cuerpo que un username inexistente: no revela que existe.
    assert response.json() == client.get(f"{API}/public/blogs/nadie").json()


@pytest.mark.usefixtures("public_blog", "real_auth", "real_permissions")
def test_blog_of_a_disabled_user_is_a_404(db_session):
    db_session.get(User, 1).disabled_at = datetime.now(UTC)
    db_session.commit()

    assert client.get(f"{API}/public/blogs/ruben").status_code == 404
