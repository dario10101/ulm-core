"""Login con Google y sesiones. Las rutas de auth y la dependencia
get_current_user dependen de esto, nunca de los repositories.

Flujo (ver app/api/routes/auth.py):
1. start_google_login: arma la URL de Google y una cookie firmada de corta
   vida con state, nonce y el verifier de PKCE.
2. complete_google_login: Google vuelve con code+state; se valida el state
   contra esa cookie, se canjea el code y se resuelve a que usuario
   corresponde la identidad (login_with_google). Termina en una sesion.
"""

import hashlib
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from itsdangerous import BadSignature, URLSafeTimedSerializer

from app.core.config import settings
from app.db.models.user import User, UserIdentity, UserSession
from app.integrations.google_oauth import (
    GoogleIdentity,
    GoogleOAuthClient,
    GoogleOAuthError,
    code_challenge_for,
    new_code_verifier,
)
from app.repositories.user_repository import UserRepository
from app.repositories.user_session_repository import UserSessionRepository
from app.services.errors import (
    EmailNotVerifiedError,
    LoginFlowError,
    LoginNotConfiguredError,
    NotInvitedError,
    UserDisabledError,
)
from app.services.permissions import is_admin_email
from app.services.user_admin_service import UserAdminService, normalize_email, valid_timezone

GOOGLE = "google"
# Vida de la cookie del flujo: lo que puede tardar el usuario en la pantalla de Google.
LOGIN_FLOW_MAX_AGE_SECONDS = 600
# La expiracion deslizante se reescribe como mucho una vez por este intervalo,
# para no hacer un UPDATE en cada request.
SESSION_RENEW_INTERVAL = timedelta(hours=1)
# Adonde vuelve el usuario si no pidio otra pagina (ver safe_next_path).
DEFAULT_NEXT_PATH = "/admin"


@dataclass(frozen=True)
class LoginResult:
    user: User
    session_token: str  # en claro: va a la cookie, nunca a la base
    next_path: str


def safe_next_path(value: str | None) -> str:
    """La pagina del front a la que volver despues del login, o la por defecto.

    Viene del navegador, asi que se restringe al area privada (/admin...):
    un `next` arbitrario convertiria el login en un *open redirect*, un link
    con la URL real de la app que termina en un sitio del atacante."""
    if (
        not value
        or not (value == DEFAULT_NEXT_PATH or value.startswith(f"{DEFAULT_NEXT_PATH}/"))
        or "//" in value
        or "\\" in value
        or any(ord(char) < 32 for char in value)
    ):
        return DEFAULT_NEXT_PATH
    return value


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("ascii")).hexdigest()


def _as_utc(value: datetime) -> datetime:
    # SQLite (tests) devuelve DateTime(timezone=True) sin tzinfo; Postgres no.
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


class AuthService:
    def __init__(
        self,
        users: UserRepository,
        sessions: UserSessionRepository,
        user_admin: UserAdminService,
        google: GoogleOAuthClient,
    ) -> None:
        self._users = users
        self._sessions = sessions
        self._user_admin = user_admin
        self._google = google

    # --- Flujo OAuth ---

    def start_google_login(
        self, browser_timezone: str | None, next_path: str | None = None
    ) -> tuple[str, str]:
        """(URL de Google, valor de la cookie del flujo). `next_path` viaja
        firmado en la cookie, asi que nadie lo cambia a mitad del flujo."""
        serializer = self._flow_serializer()
        state = secrets.token_urlsafe(32)
        nonce = secrets.token_urlsafe(32)
        verifier = new_code_verifier()
        flow_cookie = serializer.dumps(
            {
                "state": state,
                "nonce": nonce,
                "verifier": verifier,
                "tz": browser_timezone,
                "next": safe_next_path(next_path),
            }
        )
        url = self._google.authorization_url(
            state=state, nonce=nonce, code_challenge=code_challenge_for(verifier)
        )
        return url, flow_cookie

    def complete_google_login(
        self,
        *,
        code: str | None,
        state: str | None,
        flow_cookie: str | None,
        user_agent: str | None,
    ) -> LoginResult:
        serializer = self._flow_serializer()
        if not code or not state or not flow_cookie:
            raise LoginFlowError("Faltan code, state o la cookie del login")
        try:
            flow = serializer.loads(flow_cookie, max_age=LOGIN_FLOW_MAX_AGE_SECONDS)
        except BadSignature as exc:  # incluye SignatureExpired
            raise LoginFlowError("Cookie del login invalida o vencida") from exc
        # El state ata la vuelta de Google a *este* navegador: sin esto, un
        # atacante podria hacer que la victima termine logueada en la cuenta
        # del atacante (CSRF de login). compare_digest: comparacion en tiempo
        # constante.
        if not secrets.compare_digest(str(flow.get("state", "")), state):
            raise LoginFlowError("El state no coincide")

        try:
            identity = self._google.exchange_code(
                code=code, code_verifier=flow["verifier"], nonce=flow["nonce"]
            )
        except GoogleOAuthError as exc:
            raise LoginFlowError(str(exc)) from exc

        user = self.login_with_google(identity, flow.get("tz"))
        return LoginResult(
            user=user,
            session_token=self.create_session(user.id, user_agent),
            next_path=safe_next_path(flow.get("next")),
        )

    def login_with_google(self, identity: GoogleIdentity, browser_timezone: str | None) -> User:
        """A que usuario corresponde esta cuenta de Google.

        Se busca por el `sub` (id estable de Google), nunca primero por email:
        el email de una cuenta puede cambiar. Solo si la cuenta todavia no
        esta vinculada se usa el email, y solo si Google lo verifico."""
        linked = self._users.get_identity(GOOGLE, identity.subject)
        if linked is not None:
            user = self._users.get(linked.user_id)
            if user is None:  # imposible por la FK; se trata como no invitado
                raise NotInvitedError()
            self._check_enabled(user)
        else:
            user = self._link_new_identity(identity, browser_timezone)

        user.avatar_url = identity.picture
        user.last_login_at = datetime.now(UTC)
        self._users.flush()
        return user

    def _link_new_identity(self, identity: GoogleIdentity, browser_timezone: str | None) -> User:
        if not identity.email_verified or not identity.email:
            raise EmailNotVerifiedError()
        email = normalize_email(identity.email)

        user = self._users.get_by_email(email)
        if user is None:
            # Un admin entra aunque nadie lo haya invitado: en una base nueva
            # (primer deploy) no hay quien pueda invitar a nadie.
            if settings.registration_mode != "open" and not is_admin_email(email):
                raise NotInvitedError()
            user = self._user_admin.register(
                email=email, name=identity.name, timezone=browser_timezone
            )
        else:
            self._check_enabled(user)
            if not self._users.has_identities(user.id):
                # Primer login de un usuario invitado: la invitacion no sabe en
                # que zona vive ni como se llama; el navegador y Google si.
                user.timezone = valid_timezone(browser_timezone) or user.timezone
                if identity.name:
                    user.name = identity.name

        self._users.add_identity(
            UserIdentity(
                user_id=user.id,
                provider=GOOGLE,
                provider_subject=identity.subject,
                email_at_link=email,
            )
        )
        return user

    # --- Sesiones ---

    def create_session(self, user_id: int, user_agent: str | None) -> str:
        token = secrets.token_urlsafe(32)
        now = datetime.now(UTC)
        # Limpieza de las vencidas de este usuario. Se hace aca y no al
        # detectarlas en resolve_session: ese request termina en 401 y su
        # transaccion se revierte, asi que el borrado no sobreviviria.
        self._sessions.delete_expired_for_user(user_id, now)
        self._sessions.add(
            UserSession(
                user_id=user_id,
                token_hash=hash_token(token),
                created_at=now,
                last_seen_at=now,
                expires_at=now + timedelta(days=settings.session_ttl_days),
                user_agent=(user_agent or "")[:255] or None,
            )
        )
        self._sessions.flush()
        return token

    def resolve_session(self, token: str | None) -> tuple[User | None, bool]:
        """(usuario de la sesion o None, si la expiracion se renovo).

        El bool le dice a la ruta que reenvie la cookie con un Max-Age nuevo,
        para que la expiracion del navegador acompañe a la del servidor."""
        if not token:
            return None, False
        session = self._sessions.get_by_token_hash(hash_token(token))
        if session is None:
            return None, False

        now = datetime.now(UTC)
        if _as_utc(session.expires_at) <= now:
            return None, False

        user = self._users.get(session.user_id)
        if user is None or user.disabled_at is not None:
            return None, False

        renewed = now - _as_utc(session.last_seen_at) >= SESSION_RENEW_INTERVAL
        if renewed:
            session.last_seen_at = now
            session.expires_at = now + timedelta(days=settings.session_ttl_days)
            self._sessions.flush()
        return user, renewed

    def logout(self, token: str | None) -> None:
        if not token:
            return
        session = self._sessions.get_by_token_hash(hash_token(token))
        if session is not None:
            self._sessions.delete(session)
            self._sessions.flush()

    # --- Internos ---

    @staticmethod
    def _check_enabled(user: User) -> None:
        if user.disabled_at is not None:
            raise UserDisabledError()

    @staticmethod
    def _flow_serializer() -> URLSafeTimedSerializer:
        if not (
            settings.google_client_id and settings.google_client_secret and settings.session_secret
        ):
            raise LoginNotConfiguredError()
        return URLSafeTimedSerializer(settings.session_secret, salt="google-login-flow")
