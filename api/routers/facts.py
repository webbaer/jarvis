from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from api.deps import get_service
from api.schemas import FactIn, FactOut, FactUpdateIn
from jarvis_memory.service import FactNotActiveError, MemoryService

router = APIRouter(prefix="/facts", tags=["facts"])


@router.get("", response_model=list[FactOut])
def list_facts(include_superseded: bool = False, service: MemoryService = Depends(get_service)) -> list[FactOut]:
    return [FactOut.model_validate(f) for f in service.list_facts(include_superseded=include_superseded)]


@router.post("", response_model=FactOut, status_code=status.HTTP_201_CREATED)
def create_fact(body: FactIn, service: MemoryService = Depends(get_service)) -> FactOut:
    """Adds a fact. An existing active fact with the same subject/attribute is superseded."""
    fact = service.add_fact(body.subject, body.attribute, body.value, body.source, body.valid_from)
    return FactOut.model_validate(fact)


@router.put("/{fact_id}", response_model=FactOut)
def update_fact(fact_id: int, body: FactUpdateIn, service: MemoryService = Depends(get_service)) -> FactOut:
    """Creates a new active version; the old one is kept as superseded."""
    try:
        fact = service.update_fact(fact_id, body.value, body.source, body.valid_from)
    except LookupError:
        raise HTTPException(status_code=404, detail="Fakt nicht gefunden") from None
    except FactNotActiveError:
        raise HTTPException(status_code=409, detail="Nur die aktuelle Version eines Fakts kann geaendert werden") from None
    return FactOut.model_validate(fact)


@router.get("/{fact_id}/history", response_model=list[FactOut])
def fact_history(fact_id: int, service: MemoryService = Depends(get_service)) -> list[FactOut]:
    history = service.fact_history(fact_id)
    if history is None:
        raise HTTPException(status_code=404, detail="Fakt nicht gefunden")
    return [FactOut.model_validate(f) for f in history]
