"""Thin HTTP client for the Jarvis Memory API."""
from __future__ import annotations

from typing import Any

import httpx


class ApiError(Exception):
    def __init__(self, message: str, status: int | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.status = status


class ApiClient:
    def __init__(self, base_url: str, timeout_s: float, upload_timeout_s: float, eval_timeout_s: float) -> None:
        self.base_url = base_url.rstrip("/")
        self._timeout = timeout_s
        self._upload_timeout = upload_timeout_s
        self._eval_timeout = eval_timeout_s

    def _request(self, method: str, path: str, timeout: float | None = None, **kwargs: Any) -> Any:
        url = f"{self.base_url}{path}"
        try:
            response = httpx.request(method, url, timeout=timeout or self._timeout, **kwargs)
        except httpx.ConnectError:
            raise ApiError(f"API nicht erreichbar unter {self.base_url}. Laeuft sie? Start mit `make api`.") from None
        except httpx.TimeoutException:
            raise ApiError(f"Zeitueberschreitung bei {method} {path}.") from None
        except httpx.HTTPError as exc:
            raise ApiError(f"Verbindungsfehler: {exc}") from None

        if response.status_code >= 400:
            raise ApiError(self._error_detail(response), status=response.status_code)
        if response.status_code == 204 or not response.content:
            return None
        return response.json()

    @staticmethod
    def _error_detail(response: httpx.Response) -> str:
        try:
            detail = response.json().get("detail")
        except ValueError:
            return f"HTTP {response.status_code}: {response.text[:200]}"
        if isinstance(detail, list):
            # FastAPI validation errors
            detail = "; ".join(f"{'.'.join(str(p) for p in d.get('loc', []))}: {d.get('msg')}" for d in detail)
        return f"HTTP {response.status_code}: {detail}"

    # --- meta / ingest / documents ---

    def health(self) -> dict:
        return self._request("GET", "/health")

    def upload(self, files: list[tuple[str, bytes]]) -> list[dict]:
        payload = [("files", (name, data, "application/octet-stream")) for name, data in files]
        return self._request("POST", "/ingest", timeout=self._upload_timeout, files=payload)

    def job(self, job_id: str) -> dict:
        return self._request("GET", f"/ingest/{job_id}")

    def documents(self) -> list[dict]:
        return self._request("GET", "/documents")

    def chunks(self, document_id: str) -> dict:
        return self._request("GET", f"/documents/{document_id}/chunks")

    def delete_document(self, document_id: str) -> None:
        self._request("DELETE", f"/documents/{document_id}")

    def reindex_document(self, document_id: str) -> dict:
        return self._request("POST", f"/documents/{document_id}/reindex", timeout=self._upload_timeout)

    # --- query ---

    def query(self, query: str, top_k: int, filters: dict | None, rerank: bool) -> dict:
        body = {"query": query, "top_k": top_k, "filters": filters, "rerank": rerank}
        return self._request("POST", "/query", json=body)

    def locate(self, query: str, document_id: str, chunk_id: str | None, top_k: int, filters: dict | None, depth: int) -> list[dict]:
        body = {
            "query": query,
            "document_id": document_id,
            "chunk_id": chunk_id,
            "top_k": top_k,
            "filters": filters,
            "depth": depth,
        }
        return self._request("POST", "/query/locate", json=body)

    # --- facts ---

    def facts(self, include_superseded: bool = False) -> list[dict]:
        return self._request("GET", "/facts", params={"include_superseded": include_superseded})

    def create_fact(self, subject: str, attribute: str, value: str, source: str, valid_from: str | None) -> dict:
        body = {"subject": subject, "attribute": attribute, "value": value, "source": source, "valid_from": valid_from}
        return self._request("POST", "/facts", json=body)

    def update_fact(self, fact_id: int, value: str, source: str, valid_from: str | None) -> dict:
        body = {"value": value, "source": source, "valid_from": valid_from}
        return self._request("PUT", f"/facts/{fact_id}", json=body)

    def fact_history(self, fact_id: int) -> list[dict]:
        return self._request("GET", f"/facts/{fact_id}/history")

    # --- eval ---

    def run_eval(self, k: int) -> dict:
        return self._request("POST", "/eval/run", timeout=self._eval_timeout, json={"k": k})

    def eval_results(self) -> list[dict]:
        return self._request("GET", "/eval/results")
