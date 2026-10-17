"""Cache HTTP de las respuestas publicas del blog (PLAN-BLOG.md, 9.4).

`Cache-Control: public, max-age=60, stale-while-revalidate=86400`: durante un
minuto la respuesta se sirve guardada (navegador o edge de Cloudflare) sin
tocar el backend; despues se sigue sirviendo la guardada mientras se
revalida en segundo plano (*stale-while-revalidate*), asi el visitante nunca
espera un cold start de Cloud Run o Neon.

`ETag`: huella del cuerpo. Un cliente que ya tiene esa version manda
`If-None-Match` y recibe 304 sin cuerpo.

Contrapartida aceptada: un cambio del autor tarda hasta `max-age` en verse.
Solo para respuestas 200: un 404 no se guarda (el blog puede aparecer).
"""

import hashlib

from fastapi import Request, Response
from pydantic import BaseModel

CACHE_CONTROL = "public, max-age=60, stale-while-revalidate=86400"


def cached_json(request: Request, model: BaseModel) -> Response:
    body = model.model_dump_json().encode("utf-8")
    etag = f'"{hashlib.sha256(body).hexdigest()[:32]}"'
    headers = {"Cache-Control": CACHE_CONTROL, "ETag": etag}
    # If-None-Match puede traer varias etiquetas separadas por coma.
    sent = {tag.strip() for tag in request.headers.get("if-none-match", "").split(",")}
    if etag in sent or "*" in sent:
        return Response(status_code=304, headers=headers)
    return Response(content=body, media_type="application/json", headers=headers)
