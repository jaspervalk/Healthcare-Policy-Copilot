"""Path-resolution hardening for the eval dataset loader.

The loader is reachable from POST /api/evals/run with no auth gate, so any
route from a `dataset` string to an arbitrary filesystem read is a leak.
"""
import pytest

from app.eval.dataset import DatasetError, _resolve_path, load_dataset


def test_resolves_bundled_starter_dataset():
    path = _resolve_path("medicare_starter")
    assert path.name == "medicare_starter.jsonl"
    assert path.exists()


def test_accepts_explicit_jsonl_suffix():
    path = _resolve_path("medicare_starter.jsonl")
    assert path.name == "medicare_starter.jsonl"


@pytest.mark.parametrize(
    "bad_input",
    [
        "../../etc/passwd",
        "/etc/passwd",
        "/etc/passwd.jsonl",
        "../medicare_starter",
        "medicare_starter/../../etc/passwd",
        "subdir/medicare_starter",
        "name with spaces",
        "name;rm -rf /",
        "",
        ".",
        "..",
    ],
)
def test_rejects_traversal_and_special_characters(bad_input):
    with pytest.raises(DatasetError):
        _resolve_path(bad_input)


def test_rejects_unknown_bundled_name():
    with pytest.raises(DatasetError, match="not found"):
        _resolve_path("does_not_exist")


def test_load_dataset_via_traversal_string_returns_400_style_error():
    # Confirms the public entry point also surfaces the validation error,
    # not a JSON parse error from /etc/passwd.
    with pytest.raises(DatasetError, match="Invalid dataset name"):
        load_dataset("../../etc/passwd")
