"""Login con Google, sesiones y proteccion de rutas.

Google se reemplaza por FakeGoogle (mismo Protocol que el cliente real): los
tests recorren el flujo completo como un navegador -login, vuelta de Google,
cookie de sesion, request autenticado- sin red. La validacion criptografica
del id_token se prueba aparte, contra el cliente real con un transporte HTTP
falso y claves RSA generadas en el test (ver la seccion del final).

Todos usan `real_auth`: sin el reemplazo de get_current_user de conftest, un
request sin cookie de sesion recibe 401 de verdad.
"""

import time
from datetime import UTC, datetime, timedelta
from urllib.parse import parse_qs, urlparse

import httpx
import pytest
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient
from joserfc import jwt
from joserfc.jwk import KeySet, RSAKey

from app.api.deps import get_current_user, get_google_oauth_client
from app.api.session_cookie import SESSION_COOKIE
from app.core.config import settings
from app.db.models.user import User, UserIdentity, UserSession
from app.integrations.google_oauth import (
    JWKS_URL,
    TOKEN_URL,
    GoogleIdentity,
    GoogleOAuthError,
    HttpGoogleOAuthClient,
    code_challenge_for,
)
from app.main import PUBLIC_ROUTERS, app
from app.services.auth_service import hash_token

API = "/api/v1"
FRONT = settings.frontend_url

pytestmark = pytest.mark.usefixtures("real_auth")


class FakeGoogle:
    def __init__(self) -> None:
        self.identity = GoogleIdentity(
            subject="google-sub-1",
            email="ruben@example.com",
            email_verified=True,
            name="Ruben Dorado",
            picture="https://example.com/avatar.png",
        )
        self.error: Exception | None = None
        self.last_authorization: dict[str, str] = {}
        self.last_exchange: dict[str, str] = {}

    def authorization_url(self, *, state: str, nonce: str, code_challenge: str) -> str:
        self.last_authorization = {"state": state, "nonce": nonce, "challenge": code_challenge}
        return f"https://google.test/auth?state={state}"

    def exchange_code(self, *, code: str, code_verifier: str, nonce: str) -> GoogleIdentity:
        self.last_exchange = {"code": code, "verifier": code_verifier, "nonce": nonce}
        if self.error is not None:
            raise self.error
        return self.identity


@pytest.fixture
def google(monkeypatch) -> FakeGoogle:
    monkeypatch.setattr(settings, "google_client_id", "client-id")
    monkeypatch.setattr(settings, "google_client_secret", "client-secret")
    monkeypatch.setattr(settings, "session_secret", "test-secret")
    fake = FakeGoogle()
    app.dependency_overrides[get_google_oauth_client] = lambda: fake
    return fake


@pytest.fixture
def browser() -> TestClient:
    """Cliente propio por test: su jar de cookies es "el navegador"."""
    return TestClient(app)


def _start(
    browser: TestClient, tz: str | None = "Europe/Madrid", next_path: str | None = None
) -> httpx.Response:
    params = {"tz": tz} if tz else {}
    if next_path is not None:
        params["next"] = next_path
    return browser.get(f"{API}/auth/google/login", params=params, follow_redirects=False)


def _login(browser: TestClient, google: FakeGoogle, **start) -> httpx.Response:
    _start(browser, **start)
    state = google.last_authorization["state"]
    return browser.get(
        f"{API}/auth/google/callback",
        params={"code": "the-code", "state": state},
        follow_redirects=False,
    )


def _login_error(response: httpx.Response) -> str | None:
    location = urlparse(response.headers["location"])
    assert f"{location.scheme}://{location.netloc}" == FRONT
    return parse_qs(location.query).get("error", [None])[0]


# --- Flujo completo ---


def test_login_redirects_to_google_with_pkce_and_flow_cookie(browser, google):
    response = _start(browser)

    assert response.status_code == 302
    assert response.headers["location"].startswith("https://google.test/auth")
    assert "ulm_login_flow" in response.cookies
    assert len(google.last_authorization["state"]) >= 32


def test_invited_user_links_on_first_login(browser, google, db_session):
    google.identity = GoogleIdentity(
        subject="google-sub-1",
        # Mayusculas: el email se compara normalizado.
        email="Ruben@Example.com",
        email_verified=True,
        name="Ruben Dorado",
        picture="https://example.com/avatar.png",
    )

    response = _login(browser, google)

    assert response.status_code == 302
    assert response.headers["location"] == f"{FRONT}/admin"
    assert SESSION_COOKIE in response.cookies
    me = browser.get(f"{API}/me").json()
    # Primer login: nombre de Google y zona del navegador.
    assert me == {
        "id": 1,
        "name": "Ruben Dorado",
        "email": "ruben@example.com",
        "avatar_url": "https://example.com/avatar.png",
        "timezone": "Europe/Madrid",
    }
    identity = db_session.query(UserIdentity).one()
    assert (identity.user_id, identity.provider, identity.provider_subject) == (
        1,
        "google",
        "google-sub-1",
    )
    # PKCE: el verifier que se canjea es el que corresponde al challenge enviado.
    assert google.last_exchange["code"] == "the-code"
    assert (
        code_challenge_for(google.last_exchange["verifier"])
        == (google.last_authorization["challenge"])
    )
    assert google.last_exchange["nonce"] == google.last_authorization["nonce"]


def test_later_logins_find_the_user_by_subject_not_by_email(browser, google, db_session):
    _login(browser, google)
    # La cuenta de Google cambio de email: sigue siendo la misma persona.
    google.identity = GoogleIdentity(
        subject="google-sub-1",
        email="nuevo@gmail.com",
        email_verified=True,
        name="Otro nombre",
        picture=None,
    )

    response = _login(TestClient(app), google, tz="Asia/Tokyo")

    assert response.headers["location"] == f"{FRONT}/admin"
    user = db_session.get(User, 1)
    # Solo el primer login fija nombre y zona: despues son datos del usuario.
    assert (user.email, user.name, user.timezone) == (
        "ruben@example.com",
        "Ruben Dorado",
        "Europe/Madrid",
    )
    assert db_session.query(UserIdentity).count() == 1


def test_unknown_email_is_rejected_when_invite_only(browser, google, db_session):
    google.identity = GoogleIdentity("sub-x", "extrano@gmail.com", True, "X", None)

    response = _login(browser, google)

    assert _login_error(response) == "not_invited"
    assert SESSION_COOKIE not in response.cookies
    assert db_session.query(User).count() == 1
    assert db_session.query(UserIdentity).count() == 0


def test_open_registration_creates_the_user(browser, google, db_session, monkeypatch):
    monkeypatch.setattr(settings, "registration_mode", "open")
    google.identity = GoogleIdentity("sub-new", "Nueva@Gmail.com", True, "Nueva", None)

    response = _login(browser, google, tz="America/Mexico_City")

    assert response.headers["location"] == f"{FRONT}/admin"
    me = browser.get(f"{API}/me").json()
    assert (me["email"], me["name"], me["timezone"]) == (
        "nueva@gmail.com",
        "Nueva",
        "America/Mexico_City",
    )


def test_unverified_email_is_rejected(browser, google, db_session):
    google.identity = GoogleIdentity("sub-x", "ruben@example.com", False, "X", None)

    response = _login(browser, google)

    assert _login_error(response) == "email_not_verified"
    assert db_session.query(UserIdentity).count() == 0


@pytest.mark.parametrize("already_linked", [False, True])
def test_disabled_user_cannot_log_in(browser, google, db_session, already_linked):
    if already_linked:
        _login(TestClient(app), google)
    db_session.get(User, 1).disabled_at = datetime.now(UTC)
    db_session.commit()

    response = _login(browser, google)

    assert _login_error(response) == "disabled"
    assert SESSION_COOKIE not in response.cookies


def test_invalid_browser_timezone_is_ignored(browser, google, db_session):
    _login(browser, google, tz="Mars/Olympus")

    assert db_session.get(User, 1).timezone == "America/Bogota"


def test_login_returns_to_the_requested_admin_page(browser, google):
    response = _login(browser, google, next_path="/admin/records/weight?page=2")

    assert response.headers["location"] == f"{FRONT}/admin/records/weight?page=2"


@pytest.mark.parametrize(
    "next_path",
    [
        "https://evil.example/admin",
        "//evil.example/admin",
        "/admin//evil.example",
        "/admin\evil",
        "/blog",
        "/administrator",
        "",
    ],
)
def test_login_ignores_a_next_outside_admin(browser, google, next_path):
    """Sin esto el login seria un open redirect: un link con la URL real de
    la app que despues del login manda al usuario a otro sitio."""
    response = _login(browser, google, next_path=next_path)

    assert response.headers["location"] == f"{FRONT}/admin"


# --- Flujo roto: siempre vuelve a /login, nunca deja sesion ---


def test_login_without_configuration_returns_to_login(browser, monkeypatch):
    monkeypatch.setattr(settings, "google_client_id", "")

    response = _start(browser)

    assert _login_error(response) == "not_configured"


def test_callback_with_wrong_state_is_rejected(browser, google):
    _start(browser)

    response = browser.get(
        f"{API}/auth/google/callback",
        params={"code": "c", "state": "otro-state"},
        follow_redirects=False,
    )

    assert _login_error(response) == "oauth_failed"
    assert google.last_exchange == {}  # ni siquiera se intento canjear el code


def test_callback_without_flow_cookie_is_rejected(google):
    """Otro navegador (sin la cookie del login) no puede completar el flujo."""
    _start(TestClient(app))
    state = google.last_authorization["state"]

    response = TestClient(app).get(
        f"{API}/auth/google/callback",
        params={"code": "c", "state": state},
        follow_redirects=False,
    )

    assert _login_error(response) == "oauth_failed"


def test_google_rejecting_the_code_returns_to_login(browser, google):
    google.error = GoogleOAuthError("invalid_grant")

    assert _login_error(_login(browser, google)) == "oauth_failed"


@pytest.mark.parametrize(
    ("google_error", "code"), [("access_denied", "cancelled"), ("server_error", "oauth_failed")]
)
def test_error_from_google_returns_to_login(browser, google, google_error, code):
    response = browser.get(
        f"{API}/auth/google/callback", params={"error": google_error}, follow_redirects=False
    )

    assert _login_error(response) == code


# --- Sesion ---


def test_requests_without_session_are_rejected(browser):
    assert browser.get(f"{API}/me").status_code == 401
    assert browser.get(f"{API}/weights/").status_code == 401
    assert browser.post(f"{API}/weights/", json={}).status_code == 401
    assert browser.get(f"{API}/health").status_code == 200


def test_invented_session_cookie_is_rejected(browser):
    browser.cookies.set(SESSION_COOKIE, "inventada")

    assert browser.get(f"{API}/me").status_code == 401


def test_session_token_is_stored_hashed(browser, google, db_session):
    response = _login(browser, google)
    token = response.cookies[SESSION_COOKIE]

    stored = db_session.query(UserSession).one()
    assert stored.token_hash == hash_token(token)
    assert token not in stored.token_hash


def test_logout_ends_the_session(browser, google, db_session):
    _login(browser, google)
    assert browser.get(f"{API}/me").status_code == 200

    assert browser.post(f"{API}/auth/logout").status_code == 204

    assert browser.get(f"{API}/me").status_code == 401
    assert db_session.query(UserSession).count() == 0
    # Idempotente.
    assert browser.post(f"{API}/auth/logout").status_code == 204


def test_expired_session_is_rejected(browser, google, db_session):
    _login(browser, google)
    session = db_session.query(UserSession).one()
    session.expires_at = datetime.now(UTC) - timedelta(minutes=1)
    db_session.commit()

    assert browser.get(f"{API}/me").status_code == 401


def test_new_login_purges_the_users_expired_sessions(google, db_session):
    _login(TestClient(app), google)
    db_session.query(UserSession).one().expires_at = datetime.now(UTC) - timedelta(days=1)
    db_session.commit()

    _login(TestClient(app), google)

    [session] = db_session.query(UserSession).all()
    assert session.expires_at.replace(tzinfo=UTC) > datetime.now(UTC)


def test_session_expiration_slides_with_use(browser, google, db_session):
    _login(browser, google)
    session = db_session.query(UserSession).one()
    session.last_seen_at = datetime.now(UTC) - timedelta(hours=2)
    session.expires_at = datetime.now(UTC) + timedelta(days=1)
    db_session.commit()

    response = browser.get(f"{API}/me")

    assert response.status_code == 200
    # El navegador recibe la cookie de nuevo, con Max-Age completo.
    assert f"Max-Age={settings.session_ttl_days * 24 * 3600}" in response.headers["set-cookie"]
    db_session.refresh(session)
    expires_at = session.expires_at.replace(tzinfo=session.expires_at.tzinfo or UTC)
    assert expires_at > datetime.now(UTC) + timedelta(days=settings.session_ttl_days - 1)


def test_recent_session_is_not_rewritten_on_every_request(browser, google):
    _login(browser, google)

    response = browser.get(f"{API}/me")

    assert "set-cookie" not in response.headers


def test_disabled_user_loses_access_immediately(browser, google, db_session):
    _login(browser, google)
    db_session.get(User, 1).disabled_at = datetime.now(UTC)
    db_session.commit()

    assert browser.get(f"{API}/me").status_code == 401


def test_session_belongs_to_the_logged_user(google, db_session, monkeypatch):
    """Dos navegadores, dos usuarios: cada uno ve lo suyo."""
    monkeypatch.setattr(settings, "registration_mode", "open")
    ruben, ana = TestClient(app), TestClient(app)
    _login(ruben, google)
    google.identity = GoogleIdentity("sub-ana", "ana@gmail.com", True, "Ana", None)
    _login(ana, google)

    ruben.post(f"{API}/weights/", json={"weight_kg": 70, "recorded_on": "2026-09-01"})

    assert ruben.get(f"{API}/weights/").json()["total"] == 1
    assert ana.get(f"{API}/weights/").json()["total"] == 0
    assert ana.get(f"{API}/me").json()["email"] == "ana@gmail.com"


# --- Proteccion de rutas (fail-closed) ---


def _depends_on(dependant, target) -> bool:
    return any(dep.call is target or _depends_on(dep, target) for dep in dependant.dependencies)


def test_every_non_public_route_requires_a_session():
    """Si alguien agrega un router sin pasarlo por PRIVATE_ROUTERS (o una ruta
    suelta en app), esto falla. Mas seguro que acordarse en cada endpoint."""
    public_paths = {
        f"{settings.api_prefix}{route.path}" for router in PUBLIC_ROUTERS for route in router.routes
    }
    unprotected = [
        route.path
        for route in app.routes
        if isinstance(route, APIRoute)
        and route.path not in public_paths
        and route.path != "/"
        and not _depends_on(route.dependant, get_current_user)
    ]

    assert unprotected == []


# --- CSRF: chequeo de Origin ---


@pytest.mark.parametrize(
    ("origin", "status"),
    [("https://evil.example", 403), ("null", 403), (FRONT, 204), (None, 204)],
)
def test_writes_check_the_origin_header(browser, origin, status):
    headers = {"Origin": origin} if origin else {}

    assert browser.post(f"{API}/auth/logout", headers=headers).status_code == status


def test_reads_do_not_check_the_origin_header(browser):
    response = browser.get(f"{API}/health", headers={"Origin": "https://evil.example"})

    assert response.status_code == 200


# --- Cliente real de Google: validacion del id_token ---

CLIENT_ID = "client-id.apps.googleusercontent.com"


@pytest.fixture(scope="module")
def google_key() -> RSAKey:
    return RSAKey.generate_key(2048, parameters={"kid": "test-key"})


def _id_token(key: RSAKey, **overrides) -> str:
    now = int(time.time())
    claims = {
        "iss": "https://accounts.google.com",
        "aud": CLIENT_ID,
        "sub": "1234567890",
        "email": "ruben@example.com",
        "email_verified": True,
        "name": "Ruben",
        "iat": now,
        "exp": now + 3600,
        "nonce": "the-nonce",
        **overrides,
    }
    return jwt.encode({"alg": "RS256", "kid": "test-key"}, claims, key)


def _real_client(key: RSAKey, *, id_token: str | None, token_status: int = 200):
    public_keys = KeySet([key]).as_dict(private=False)
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if str(request.url) == TOKEN_URL:
            body = {"access_token": "at", "id_token": id_token} if id_token else {}
            return httpx.Response(token_status, json=body)
        if str(request.url) == JWKS_URL:
            return httpx.Response(200, json=public_keys)
        return httpx.Response(404)

    client = HttpGoogleOAuthClient(
        client_id=CLIENT_ID,
        client_secret="secret",
        redirect_uri="http://localhost:5173/api/v1/auth/google/callback",
        http=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    return client, requests


def test_real_client_accepts_a_valid_id_token(google_key):
    client, requests = _real_client(google_key, id_token=_id_token(google_key))

    identity = client.exchange_code(code="c", code_verifier="v", nonce="the-nonce")

    assert identity == GoogleIdentity(
        subject="1234567890",
        email="ruben@example.com",
        email_verified=True,
        name="Ruben",
        picture=None,
    )
    token_request = parse_qs(requests[0].content.decode())
    assert token_request["code_verifier"] == ["v"]
    assert token_request["grant_type"] == ["authorization_code"]


@pytest.mark.parametrize(
    "overrides",
    [
        {"aud": "otra-app"},
        {"iss": "https://evil.example"},
        {"exp": int(time.time()) - 3600},
        {"nonce": "otro-nonce"},
    ],
    ids=["audience", "issuer", "expired", "nonce"],
)
def test_real_client_rejects_invalid_claims(google_key, overrides):
    client, _ = _real_client(google_key, id_token=_id_token(google_key, **overrides))

    with pytest.raises(GoogleOAuthError):
        client.exchange_code(code="c", code_verifier="v", nonce="the-nonce")


def test_real_client_rejects_a_token_signed_by_someone_else(google_key):
    forger = RSAKey.generate_key(2048, parameters={"kid": "test-key"})
    client, _ = _real_client(google_key, id_token=_id_token(forger))

    with pytest.raises(GoogleOAuthError):
        client.exchange_code(code="c", code_verifier="v", nonce="the-nonce")


def test_real_client_reports_a_rejected_code(google_key):
    client, _ = _real_client(google_key, id_token=None, token_status=400)

    with pytest.raises(GoogleOAuthError):
        client.exchange_code(code="c", code_verifier="v", nonce="the-nonce")


def test_authorization_url_carries_pkce_state_and_nonce():
    client = HttpGoogleOAuthClient(client_id=CLIENT_ID, client_secret="s", redirect_uri="http://x")

    url = urlparse(client.authorization_url(state="st", nonce="no", code_challenge="ch"))
    params = {key: values[0] for key, values in parse_qs(url.query).items()}

    assert params["state"] == "st"
    assert params["nonce"] == "no"
    assert params["code_challenge"] == "ch"
    assert params["code_challenge_method"] == "S256"
    assert params["scope"] == "openid email profile"
