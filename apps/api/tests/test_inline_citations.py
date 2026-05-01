"""Tests for the inline-citation marker safety net.

The frontend's chip renderer needs `[N]` or `[uuid]` markers in the answer text.
The model sometimes forgets to inline them — `ensure_inline_citation_markers`
appends `[1] [2]...` at the end so the chips always render when there are
citations.
"""
from app.services.answering import ensure_inline_citation_markers


def test_appends_markers_when_answer_has_none():
    out = ensure_inline_citation_markers("Some answer text.", 3)
    assert out == "Some answer text. [1] [2] [3]"


def test_appends_with_period_separator_when_answer_does_not_end_in_punctuation():
    out = ensure_inline_citation_markers("Some answer text", 2)
    assert out == "Some answer text. [1] [2]"


def test_leaves_answer_alone_when_numeric_marker_present():
    text = "Inpatient stays are covered when medically necessary [1]."
    assert ensure_inline_citation_markers(text, 2) == text


def test_leaves_answer_alone_when_numeric_marker_with_multiple_citations_present():
    text = "Coverage extends to **supplies and equipment** [1, 2]."
    assert ensure_inline_citation_markers(text, 3) == text


def test_leaves_answer_alone_when_uuid_marker_present():
    text = "Coverage requires medical necessity [4abde88e-71bb-475e-a752-b159f75c8158]."
    assert ensure_inline_citation_markers(text, 2) == text


def test_leaves_answer_alone_when_multiple_uuid_markers_present():
    text = (
        "Inpatient services are covered "
        "[4abde88e-71bb-475e-a752-b159f75c8158; 185644d6-d7e3-4966-b5b2-f6930b99333c]."
    )
    assert ensure_inline_citation_markers(text, 3) == text


def test_no_change_when_no_citations():
    out = ensure_inline_citation_markers("answer text", 0)
    assert out == "answer text"


def test_no_change_when_empty_answer():
    assert ensure_inline_citation_markers("", 3) == ""


def test_brackets_with_unrelated_content_do_not_count_as_markers():
    """A bracketed plain word like '[Note]' shouldn't suppress the safety-net append."""
    text = "Coverage applies [Note: see chapter 1]."
    out = ensure_inline_citation_markers(text, 2)
    assert "[1]" in out and "[2]" in out
