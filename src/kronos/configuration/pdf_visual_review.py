"""Non-secret filesystem configuration for Sponsor-mediated PDF Review."""

from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
import stat
import tempfile

from kronos.configuration.exceptions import ConfigurationError


PDF_VISUAL_REVIEW_CONFIGURATION_SCHEMA = "KRONOS-PDF-VISUAL-REVIEW-CONFIG-V1"
PDF_VISUAL_REVIEW_CONFIGURATION_FILE = "pdf-visual-review.json"


def pdf_visual_review_configuration_path(*, home: Path | None = None) -> Path:
    root = Path.home() if home is None else Path(home)
    return (
        root / "Library" / "Application Support" / "Project-KRONOS"
        / PDF_VISUAL_REVIEW_CONFIGURATION_FILE
    )


def default_pdf_visual_review_directories(
    *, home: Path | None = None,
) -> tuple[Path, Path]:
    root = Path.home() if home is None else Path(home)
    review_root = root / "Documents" / "Project-KRONOS" / "KRONOS REVIEW PACK"
    return review_root / "KRONOS QUESTIONS", review_root / "CHATGPT ANSWERS"


@dataclass(frozen=True, slots=True)
class PdfVisualReviewConfiguration:
    question_directory: Path
    answer_directory: Path
    schema_identity: str = PDF_VISUAL_REVIEW_CONFIGURATION_SCHEMA

    def __post_init__(self) -> None:
        if (
            self.schema_identity != PDF_VISUAL_REVIEW_CONFIGURATION_SCHEMA
            or not isinstance(self.question_directory, Path)
            or not isinstance(self.answer_directory, Path)
            or not self.question_directory.is_absolute()
            or not self.answer_directory.is_absolute()
            or self.question_directory == self.answer_directory
        ):
            raise ConfigurationError("PDF_VISUAL_REVIEW_CONFIGURATION_INVALID")

    def ensure_directories(self) -> None:
        for directory in (self.question_directory, self.answer_directory):
            directory.mkdir(mode=0o700, parents=True, exist_ok=True)
            metadata = directory.lstat()
            if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISDIR(metadata.st_mode):
                raise ConfigurationError("PDF_VISUAL_REVIEW_DIRECTORY_INVALID")
            os.chmod(directory, 0o700)


def load_or_provision_pdf_visual_review_configuration(
    *,
    path: Path | None = None,
    home: Path | None = None,
) -> PdfVisualReviewConfiguration:
    target = pdf_visual_review_configuration_path(home=home) if path is None else Path(path)
    if not target.exists():
        question, answer = default_pdf_visual_review_directories(home=home)
        _write_configuration(target, question, answer)
    configuration = _read_configuration(target)
    configuration.ensure_directories()
    return configuration


def _read_configuration(path: Path) -> PdfVisualReviewConfiguration:
    try:
        metadata = path.lstat()
        if (
            stat.S_ISLNK(metadata.st_mode)
            or not stat.S_ISREG(metadata.st_mode)
            or metadata.st_size > 16_384
        ):
            raise ConfigurationError("PDF_VISUAL_REVIEW_CONFIGURATION_INVALID")
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ConfigurationError("PDF_VISUAL_REVIEW_CONFIGURATION_INVALID") from error
    if (
        type(payload) is not dict
        or set(payload) != {"schema_identity", "question_directory", "answer_directory"}
        or payload.get("schema_identity") != PDF_VISUAL_REVIEW_CONFIGURATION_SCHEMA
        or any(type(payload.get(key)) is not str or not payload[key].strip() for key in (
            "question_directory", "answer_directory",
        ))
    ):
        raise ConfigurationError("PDF_VISUAL_REVIEW_CONFIGURATION_INVALID")
    return PdfVisualReviewConfiguration(
        Path(payload["question_directory"]).expanduser(),
        Path(payload["answer_directory"]).expanduser(),
    )


def _write_configuration(path: Path, question: Path, answer: Path) -> None:
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    payload = json.dumps(
        {
            "schema_identity": PDF_VISUAL_REVIEW_CONFIGURATION_SCHEMA,
            "question_directory": str(question),
            "answer_directory": str(answer),
        },
        indent=2,
        sort_keys=True,
    ) + "\n"
    temporary_name = ""
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=path.parent,
            prefix=f".{path.name}.", delete=False,
        ) as temporary:
            temporary_name = temporary.name
            temporary.write(payload)
            temporary.flush()
            os.fsync(temporary.fileno())
        os.chmod(temporary_name, 0o600)
        os.replace(temporary_name, path)
    except OSError as error:
        if temporary_name:
            try:
                os.unlink(temporary_name)
            except OSError:
                pass
        raise ConfigurationError("PDF_VISUAL_REVIEW_CONFIGURATION_WRITE_FAILED") from error


__all__ = [
    "PDF_VISUAL_REVIEW_CONFIGURATION_SCHEMA",
    "PdfVisualReviewConfiguration",
    "default_pdf_visual_review_directories",
    "load_or_provision_pdf_visual_review_configuration",
    "pdf_visual_review_configuration_path",
]
