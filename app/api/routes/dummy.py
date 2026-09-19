"""Rutas de lectura/escritura sobre la tabla dummy, prueba de acceso a Postgres."""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.models.dummy import DummyRecord
from app.db.session import get_db
from app.schemas.dummy import DummyCreate, DummyRead

router = APIRouter(prefix="/dummy", tags=["dummy"])


@router.post("/", response_model=DummyRead, status_code=201)
def create_dummy(payload: DummyCreate, db: Session = Depends(get_db)) -> DummyRecord:
    # Guarda un registro nuevo en la tabla dummy
    record = DummyRecord(**payload.model_dump())
    db.add(record)
    db.commit()
    db.refresh(record)
    return record


@router.get("/", response_model=list[DummyRead])
def list_dummy(db: Session = Depends(get_db)) -> list[DummyRecord]:
    # Lee todos los registros de la tabla dummy
    return db.query(DummyRecord).order_by(DummyRecord.id).all()
