import json
from pathlib import Path

import pytest

from kronos.configuration.exceptions import ConfigurationError
from kronos.configuration.pdf_visual_review import (
    PDF_VISUAL_REVIEW_CONFIGURATION_SCHEMA,
    default_pdf_visual_review_directories,
    default_mcx_supporting_context_directories,
    load_or_provision_pdf_visual_review_configuration,
)


def test_mcx_supporting_context_uses_segregated_governed_directories(tmp_path: Path) -> None:
    question, answer = default_mcx_supporting_context_directories(home=tmp_path)
    root = tmp_path / "Documents" / "Project-KRONOS" / "KRONOS REVIEW PACK" / "Support Charts"
    assert question == root / "KRONOS QUESTIONS"
    assert answer == root / "CHATGPT ANSWERS"


def test_provisions_non_secret_sponsor_directories_from_configuration(tmp_path: Path) -> None:
    target = tmp_path / "Library" / "Application Support" / "Project-KRONOS" / "pdf.json"
    configuration = load_or_provision_pdf_visual_review_configuration(
        path=target, home=tmp_path
    )

    expected = default_pdf_visual_review_directories(home=tmp_path)
    assert (configuration.question_directory, configuration.answer_directory) == expected
    assert all(item.is_dir() for item in expected)
    payload = json.loads(target.read_text(encoding="utf-8"))
    assert payload["schema_identity"] == PDF_VISUAL_REVIEW_CONFIGURATION_SCHEMA
    assert set(payload) == {"schema_identity", "question_directory", "answer_directory"}
    assert expected == (
        tmp_path
        / "Documents"
        / "Project-KRONOS"
        / "KRONOS REVIEW PACK"
        / "SWING"
        / "KRONOS QUESTIONS",
        tmp_path
        / "Documents"
        / "Project-KRONOS"
        / "KRONOS REVIEW PACK"
        / "SWING"
        / "CHATGPT ANSWERS",
    )

    configuration.ensure_directories()
    assert all(item.is_dir() for item in expected)


def test_legacy_default_paths_are_segregated_without_moving_historical_files(
    tmp_path: Path,
) -> None:
    target = tmp_path / "Library" / "Application Support" / "Project-KRONOS" / "pdf.json"
    historical_root = (
        tmp_path / "Documents" / "Project-KRONOS" / "KRONOS REVIEW PACK"
    )
    historical_questions = historical_root / "KRONOS QUESTIONS"
    historical_answers = historical_root / "CHATGPT ANSWERS"
    historical_questions.mkdir(parents=True)
    historical_answers.mkdir(parents=True)
    question = historical_questions / "HISTORICAL_QUESTIONS.pdf"
    answer = historical_answers / "HISTORICAL_ANSWERS.pdf"
    question.write_bytes(b"historical-question")
    answer.write_bytes(b"historical-answer")
    target.parent.mkdir(parents=True)
    target.write_text(json.dumps({
        "schema_identity": PDF_VISUAL_REVIEW_CONFIGURATION_SCHEMA,
        "question_directory": str(historical_questions),
        "answer_directory": str(historical_answers),
    }), encoding="utf-8")

    configuration = load_or_provision_pdf_visual_review_configuration(
        path=target, home=tmp_path
    )

    assert (
        configuration.question_directory,
        configuration.answer_directory,
    ) == default_pdf_visual_review_directories(home=tmp_path)
    assert question.read_bytes() == b"historical-question"
    assert answer.read_bytes() == b"historical-answer"


def test_configuration_rejects_symlink_directory(tmp_path: Path) -> None:
    actual = tmp_path / "actual"
    actual.mkdir()
    linked = tmp_path / "linked"
    linked.symlink_to(actual, target_is_directory=True)
    target = tmp_path / "pdf.json"
    target.write_text(json.dumps({
        "schema_identity": PDF_VISUAL_REVIEW_CONFIGURATION_SCHEMA,
        "question_directory": str(linked),
        "answer_directory": str(tmp_path / "answers"),
    }), encoding="utf-8")

    with pytest.raises(ConfigurationError, match="DIRECTORY_INVALID"):
        load_or_provision_pdf_visual_review_configuration(path=target)
