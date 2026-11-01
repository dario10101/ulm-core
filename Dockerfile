# Imagen de produccion de ulm-core (Cloud Run). Ver ulm-doc/plans/PLAN-DOCKER.md.
#
# La misma imagen corre la API (CMD por defecto) y las migraciones
# (`alembic upgrade head`, como paso aparte antes de desplegar): no migra al
# arrancar, para que dos instancias no migren a la vez.

# Una sola etapa: psycopg2-binary trae wheel, no hace falta compilar nada.
# tzdata (base IANA que slim no trae) va por pip en requirements.txt.
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PORT=8000

WORKDIR /app

# Primero solo las dependencias: esta capa se reusa mientras requirements.txt
# no cambie, aunque cambie el codigo.
COPY requirements.txt .
RUN pip install -r requirements.txt

RUN useradd --create-home --uid 10001 ulm

COPY alembic.ini .
COPY migrations ./migrations
# manage_users (invitar el primer usuario) y check_db_names corren en el
# contenedor con `python -m scripts.<nombre>`.
COPY scripts ./scripts
COPY app ./app

USER ulm

EXPOSE 8000

# PORT lo inyecta Cloud Run. --proxy-headers: TLS termina adelante, en el
# proxy de Google. Un worker: Cloud Run escala por instancias. `exec` deja a
# uvicorn como PID 1 para que reciba el SIGTERM y cierre ordenado.
CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT} --proxy-headers --forwarded-allow-ips='*'"]
