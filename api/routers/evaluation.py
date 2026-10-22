from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from api.deps import check_limit, get_service
from api.schemas import EvalRunIn, EvalRunOut
from jarvis_memory.service import MemoryService

router = APIRouter(prefix="/eval", tags=["eval"])


@router.post("/run", response_model=EvalRunOut)
def run_eval(body: EvalRunIn, service: MemoryService = Depends(get_service)) -> EvalRunOut:
    """Runs the configured eval dataset synchronously and stores the result."""
    check_limit("k", body.k, service.config.inspection.max_top_k)
    try:
        run = service.run_eval(k=body.k)
    except FileNotFoundError:
        raise HTTPException(
            status_code=409, detail=f"Eval-Datensatz nicht gefunden: {service.config.paths.eval_dataset_path}"
        ) from None
    except (KeyError, TypeError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=f"Eval-Datensatz ungueltig: {exc}") from None
    return EvalRunOut.model_validate(run)


@router.get("/results", response_model=list[EvalRunOut])
def eval_results(service: MemoryService = Depends(get_service)) -> list[EvalRunOut]:
    return [EvalRunOut.model_validate(r) for r in service.list_eval_runs()]
