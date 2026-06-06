import argparse

import pytest

from orchestrator.__main__ import parse_timeout_arg
from orchestrator.session import infer_project_path_from_task


def test_parse_timeout_arg_supports_infinite() -> None:
    assert parse_timeout_arg("inf") is None
    assert parse_timeout_arg("infinite") is None
    assert parse_timeout_arg("0") is None


def test_parse_timeout_arg_supports_positive_seconds() -> None:
    assert parse_timeout_arg("1800") == 1800
    assert parse_timeout_arg("60") == 60


def test_parse_timeout_arg_rejects_invalid_values() -> None:
    with pytest.raises(argparse.ArgumentTypeError):
        parse_timeout_arg("-1")

    with pytest.raises(argparse.ArgumentTypeError):
        parse_timeout_arg("abc")


def test_infer_project_path_from_task_finds_existing_directory(temp_dir) -> None:
    project_dir = temp_dir / "Apps" / "FocusSprint"
    project_dir.mkdir(parents=True)

    task = "Crea una web app Focus Sprint in Apps/FocusSprint con backend FastAPI"
    inferred = infer_project_path_from_task(task, cwd=temp_dir)

    assert inferred == project_dir.resolve()


def test_infer_project_path_from_task_ignores_missing_paths(temp_dir) -> None:
    task = "Implementa la feature in Apps/DoesNotExist e aggiungi test"
    inferred = infer_project_path_from_task(task, cwd=temp_dir)
    assert inferred is None
