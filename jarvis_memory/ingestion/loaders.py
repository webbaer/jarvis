from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from email import policy
from email.parser import BytesParser
from pathlib import Path

from pypdf import PdfReader

from jarvis_memory.models import Document


@dataclass(slots=True)
class LoadedContent:
    text: str
    doc_type: str
    doc_date: str | None = None


class BaseLoader(ABC):
    @abstractmethod
    def can_load(self, path: Path) -> bool:
        raise NotImplementedError

    @abstractmethod
    def load(self, path: Path) -> LoadedContent:
        raise NotImplementedError


class TextLoader(BaseLoader):
    extensions = {".txt", ".md"}

    def can_load(self, path: Path) -> bool:
        return path.suffix.lower() in self.extensions

    def load(self, path: Path) -> LoadedContent:
        text = path.read_text(encoding="utf-8", errors="ignore")
        doc_type = "markdown" if path.suffix.lower() == ".md" else "text"
        return LoadedContent(text=text, doc_type=doc_type)


class PdfLoader(BaseLoader):
    def can_load(self, path: Path) -> bool:
        return path.suffix.lower() == ".pdf"

    def load(self, path: Path) -> LoadedContent:
        reader = PdfReader(str(path))
        parts: list[str] = []
        for page in reader.pages:
            parts.append(page.extract_text() or "")
        return LoadedContent(text="\n\n".join(parts), doc_type="pdf")


class EmlLoader(BaseLoader):
    def can_load(self, path: Path) -> bool:
        return path.suffix.lower() == ".eml"

    def load(self, path: Path) -> LoadedContent:
        with path.open("rb") as f:
            msg = BytesParser(policy=policy.default).parse(f)

        body = msg.get_body(preferencelist=("plain", "html"))
        body_text = body.get_content() if body is not None else ""
        subject = msg.get("subject", "")
        sender = msg.get("from", "")
        date = msg.get("date")
        combined = f"Subject: {subject}\nFrom: {sender}\n\n{body_text}"
        return LoadedContent(text=combined, doc_type="email", doc_date=date)


class LoaderRegistry:
    def __init__(self, loaders: list[BaseLoader] | None = None) -> None:
        self._loaders = loaders or [TextLoader(), PdfLoader(), EmlLoader()]

    def load_path(self, path: Path) -> Document:
        for loader in self._loaders:
            if loader.can_load(path):
                loaded = loader.load(path)
                return Document(
                    doc_id="",
                    source=str(path),
                    doc_type=loaded.doc_type,
                    content=loaded.text,
                    doc_date=loaded.doc_date,
                    metadata=None,
                )
        raise ValueError(f"Unsupported file type: {path}")
