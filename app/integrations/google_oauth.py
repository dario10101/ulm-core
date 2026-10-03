"""Cliente de Google OAuth 2.0 / OpenID Connect (flujo Authorization Code + PKCE).

Hace solo las dos llamadas a Google y la validacion del id_token. Que hacer
con la identidad (crear sesion, vincular, rechazar) lo decide AuthService, que
depende del Protocol y no de esta clase: los tests le pasan un cliente falso.

Por que se valida cada claim del id_token:
- firma (JWKS de Google): que lo emitio Google y nadie lo altero.
- iss: emisor Google.  aud: emitido para *esta* app y no para otra.
- exp: no vencido.     nonce: es la respuesta a *este* login, no uno
  reutilizado (ataque de replay).
"""

import base64
import hashlib
import secrets
from dataclasses import dataclass
from typing import Protocol
from urllib.parse import urlencode

import httpx
from joserfc import jwt
from joserfc.errors import JoseError
from joserfc.jwk import KeySet

AUTHORIZATION_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
JWKS_URL = "https://www.googleapis.com/oauth2/v3/certs"
ISSUERS = ["https://accounts.google.com", "accounts.google.com"]
SCOPES = "openid email profile"


class GoogleOAuthError(Exception):
    """Google rechazo el intercambio o el id_token no paso la validacion."""


@dataclass(frozen=True)
class GoogleIdentity:
    subject: str
    email: str
    email_verified: bool
    name: str | None
    picture: str | None


class GoogleOAuthClient(Protocol):
    def authorization_url(self, *, state: str, nonce: str, code_challenge: str) -> str: ...

    def exchange_code(self, *, code: str, code_verifier: str, nonce: str) -> GoogleIdentity: ...


def new_code_verifier() -> str:
    """PKCE (RFC 7636): secreto que solo conoce este backend. Si alguien
    intercepta el `code` del redirect, sin el verifier no puede canjearlo."""
    return secrets.token_urlsafe(64)


def code_challenge_for(verifier: str) -> str:
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")


class HttpGoogleOAuthClient:
    def __init__(
        self,
        *,
        client_id: str,
        client_secret: str,
        redirect_uri: str,
        http: httpx.Client | None = None,
    ) -> None:
        self._client_id = client_id
        self._client_secret = client_secret
        self._redirect_uri = redirect_uri
        self._http = http or httpx.Client(timeout=10)

    def authorization_url(self, *, state: str, nonce: str, code_challenge: str) -> str:
        params = {
            "client_id": self._client_id,
            "redirect_uri": self._redirect_uri,
            "response_type": "code",
            "scope": SCOPES,
            "state": state,
            "nonce": nonce,
            "code_challenge": code_challenge,
            "code_challenge_method": "S256",
            # Deja elegir cuenta aunque haya una sola sesion de Google abierta.
            "prompt": "select_account",
        }
        return f"{AUTHORIZATION_URL}?{urlencode(params)}"

    def exchange_code(self, *, code: str, code_verifier: str, nonce: str) -> GoogleIdentity:
        try:
            response = self._http.post(
                TOKEN_URL,
                data={
                    "grant_type": "authorization_code",
                    "code": code,
                    "code_verifier": code_verifier,
                    "redirect_uri": self._redirect_uri,
                    "client_id": self._client_id,
                    "client_secret": self._client_secret,
                },
            )
        except httpx.HTTPError as exc:
            raise GoogleOAuthError(f"No se pudo contactar a Google: {exc}") from exc
        if response.status_code != 200:
            raise GoogleOAuthError(f"Google rechazo el code ({response.status_code})")

        id_token = response.json().get("id_token")
        if not id_token:
            raise GoogleOAuthError("La respuesta de Google no trae id_token")
        return self._verify_id_token(id_token, nonce)

    def _verify_id_token(self, id_token: str, nonce: str) -> GoogleIdentity:
        # Las claves se piden en cada login en vez de cachearlas: un login es
        # un evento raro a esta escala y asi una rotacion de claves de Google
        # nunca deja una clave vieja en memoria.
        try:
            keys = KeySet.import_key_set(self._http.get(JWKS_URL).json())
            token = jwt.decode(id_token, keys, algorithms=["RS256"])
            jwt.JWTClaimsRegistry(
                leeway=60,
                iss={"essential": True, "values": ISSUERS},
                aud={"essential": True, "value": self._client_id},
                exp={"essential": True},
                sub={"essential": True},
                nonce={"essential": True, "value": nonce},
            ).validate(token.claims)
        except (httpx.HTTPError, JoseError, ValueError) as exc:
            raise GoogleOAuthError(f"id_token invalido: {exc}") from exc

        claims = token.claims
        return GoogleIdentity(
            subject=str(claims["sub"]),
            email=str(claims.get("email", "")),
            email_verified=claims.get("email_verified") is True,
            name=claims.get("name"),
            picture=claims.get("picture"),
        )
