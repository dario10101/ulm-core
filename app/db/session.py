"""Motor de conexion y manejo de sesiones de SQLAlchemy."""

from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import settings

engine = create_engine(settings.database_url)

# expire_on_commit=False: al commitear, SQLAlchemy por defecto marca como
# expirados los atributos de todos los objetos de la sesion, y volver a leerlos
# dispara un SELECT. Como el commit ahora ocurre al final del request (ver
# get_db), esa recarga caeria fuera de la transaccion y puede fallar con la
# sesion ya cerrada. Los services usan flush(), asi que los valores generados
# por la base (ids) ya estan cargados cuando se mapea la respuesta.
SessionLocal = sessionmaker(autocommit=False, autoflush=False, expire_on_commit=False, bind=engine)


def get_db() -> Generator[Session, None, None]:
    """Sesion de base de datos con **una transaccion por request**.

    Este es el unico lugar donde se hace commit. Antes cada repository exponia
    su propio `commit()` y los services lo llamaban varias veces por operacion,
    asi que una falla a mitad dejaba escrito lo de antes: `create_week` podia
    dejar una semana abierta y vacia, y como no se puede crear otra mientras
    haya una sin cerrar, el usuario quedaba bloqueado sin salida desde la UI.

    Ahora, o se escribe la operacion completa o no se escribe nada.

    Nota: FastAPI ejecuta el codigo posterior al `yield` despues de enviar la
    respuesta, asi que un fallo del commit en si (no de las escrituras, que ya
    se validaron en el flush) se registra en el log pero no alcanza a cambiar
    la respuesta que el cliente ya recibio.
    """
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        # Incluye las HTTPException que levantan las rutas al traducir un error
        # de dominio: si la operacion no termino bien, no se guarda nada.
        db.rollback()
        raise
    finally:
        db.close()
