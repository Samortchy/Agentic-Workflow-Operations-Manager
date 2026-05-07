from pathlib import Path

from ..base_step import BaseStep, StepResult


class FileExtractor(BaseStep):
    """
    Reads a file attachment and returns sliding-window text chunks.

    Config fields
    -------------
    accepted_formats : list[str]  e.g. ["pdf", "docx", "txt"]
    chunk_size       : int        Characters per chunk.
    overlap_pct      : float      Fraction of chunk_size to overlap between chunks.

    File path is read from:
      envelope["task"]["attachment_path"]  or  envelope["attachment_path"]
    """

    def run(self, envelope: dict, config: dict) -> StepResult:
        try:
            attachment_path = (
                envelope.get("task", {}).get("attachment_path")
                or envelope.get("attachment_path")
            )
            if not attachment_path:
                return StepResult(
                    success=False,
                    data={},
                    error="No attachment_path found in envelope",
                )

            path = Path(attachment_path)
            if not path.exists():
                return StepResult(
                    success=False,
                    data={},
                    error=f"File not found: {attachment_path}",
                )

            accepted_formats: list = config.get("accepted_formats", ["pdf", "docx", "txt"])
            fmt = path.suffix.lstrip(".").lower()
            if fmt not in accepted_formats:
                return StepResult(
                    success=False,
                    data={},
                    error=f"Format '{fmt}' not in accepted_formats {accepted_formats}",
                )

            text = self._read(path, fmt)
            chunk_size: int = config.get("chunk_size", 1000)
            overlap_pct: float = config.get("overlap_pct", 0.1)
            chunks = self._chunk(text, chunk_size, overlap_pct)

            return StepResult(
                success=True,
                data={"chunks": chunks, "format": fmt, "total_chunks": len(chunks)},
                error=None,
            )

        except Exception as e:
            return StepResult(success=False, data={}, error=str(e))

    # ------------------------------------------------------------------
    # Format readers
    # ------------------------------------------------------------------

    @staticmethod
    def _read(path: Path, fmt: str) -> str:
        if fmt == "pdf":
            import pdfplumber
            with pdfplumber.open(str(path)) as pdf:
                return "\n".join(
                    page.extract_text() or "" for page in pdf.pages
                )

        if fmt == "docx":
            from docx import Document
            doc = Document(str(path))
            return "\n".join(para.text for para in doc.paragraphs)

        # txt (and any plain-text fallback)
        return path.read_text(encoding="utf-8", errors="replace")

    # ------------------------------------------------------------------
    # Chunking
    # ------------------------------------------------------------------

    @staticmethod
    def _chunk(text: str, chunk_size: int, overlap_pct: float) -> list:
        if not text:
            return []

        overlap = int(chunk_size * overlap_pct)
        step = max(1, chunk_size - overlap)
        chunks = []
        start = 0
        while start < len(text):
            chunks.append(text[start: start + chunk_size])
            start += step
        return chunks
