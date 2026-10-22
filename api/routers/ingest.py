from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, Request, UploadFile, status

from api.deps import get_jobs, get_service
from api.jobs import JobStore, process_jobs
from api.schemas import IngestJobOut, UploadItemOut
from api.uploads import UploadRejected, store_upload
from jarvis_memory.service import MemoryService

router = APIRouter(prefix="/ingest", tags=["ingest"])

# Allowance for multipart boundaries and headers on top of the file payloads.
_MULTIPART_OVERHEAD_BYTES = 64 * 1024


@router.post("", response_model=list[UploadItemOut], status_code=status.HTTP_202_ACCEPTED)
async def ingest(
    request: Request,
    background: BackgroundTasks,
    files: list[UploadFile] = File(...),
    service: MemoryService = Depends(get_service),
    jobs: JobStore = Depends(get_jobs),
) -> list[UploadItemOut]:
    cfg = service.config.upload
    if len(files) > cfg.max_files_per_request:
        raise HTTPException(status_code=413, detail=f"Hoechstens {cfg.max_files_per_request} Dateien pro Upload")

    # Note: Starlette has already spooled the body; this only rejects obviously oversized requests early.
    declared = int(request.headers.get("content-length", 0) or 0)
    if declared > cfg.max_files_per_request * cfg.max_file_bytes + _MULTIPART_OVERHEAD_BYTES:
        raise HTTPException(status_code=413, detail="Upload ist zu gross")

    items: list[UploadItemOut] = []
    job_ids: list[str] = []
    for upload in files:
        try:
            stored = await store_upload(upload, service.config.paths.uploads_dir, cfg)
        except UploadRejected as exc:
            items.append(UploadItemOut(filename=upload.filename or "", status="rejected", error=str(exc)))
            continue
        finally:
            await upload.close()
        job = jobs.create(filename=stored.name, stored_path=stored, document_id=service.new_document_id())
        job_ids.append(job.id)
        items.append(UploadItemOut(filename=stored.name, status="queued", job_id=job.id, document_id=job.document_id))

    if job_ids:
        background.add_task(process_jobs, service, jobs, job_ids)
    return items


@router.get("", response_model=list[IngestJobOut])
def list_jobs(jobs: JobStore = Depends(get_jobs)) -> list[IngestJobOut]:
    return [IngestJobOut.model_validate(j) for j in jobs.list()]


@router.get("/{job_id}", response_model=IngestJobOut)
def get_job(job_id: str, jobs: JobStore = Depends(get_jobs)) -> IngestJobOut:
    job = jobs.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job nicht gefunden (Jobs gehen beim API-Neustart verloren)")
    return IngestJobOut.model_validate(job)
