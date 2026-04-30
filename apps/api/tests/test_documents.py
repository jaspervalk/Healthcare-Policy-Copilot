from app.services.documents import (
    _detect_department,
    _detect_document_type,
    _detect_policy_status,
    _detect_version,
)


def test_detect_version_extracts_first_capture_group():
    assert _detect_version("Policy revision: 7.3") == "7.3"
    assert _detect_version("Document Version ABC-2026") == "ABC-2026"
    assert _detect_version("Rev. :") is None


def test_detect_document_type_picks_more_frequent_match():
    """Procedure document that mentions 'policy' once must classify as procedure.

    Reproduction of the audit's H7: previously returned 'policy' because dict
    insertion order made it the first match.
    """
    text = (
        "Care Management Procedure. This procedure governs the discharge workflow. "
        "It supports the broader policy on care transitions. Procedure step 1: ..."
    )

    assert _detect_document_type(text) == "procedure"


def test_detect_document_type_returns_none_when_no_keywords():
    assert _detect_document_type("Some unrelated text about foo and bar.") is None


def test_detect_document_type_uses_word_boundary():
    """'policymaker' must not match 'policy'."""
    assert _detect_document_type("Notes from a policymaker who attended a procedure review") == "procedure"


def test_detect_department_picks_strongest_signal():
    text = (
        "This document covers utilization management workflows. "
        "Prior authorization steps are documented below. "
        "Discharge handoff is mentioned once."
    )

    assert _detect_department(text) == "utilization_management"


def test_detect_policy_status_returns_none_without_signal():
    """Previously defaulted to 'active' — a confident claim from no evidence."""
    assert _detect_policy_status("Document covers prior authorization escalation steps.") is None


def test_detect_policy_status_active_requires_explicit_signal():
    assert _detect_policy_status("This policy is currently active.") == "active"
    assert _detect_policy_status("Effective as of January 2026.") == "active"


def test_detect_policy_status_retired_takes_precedence():
    assert _detect_policy_status("This policy is retired and superseded.") == "retired"
    assert _detect_policy_status("Draft retired version.") == "retired"


def test_detect_policy_status_draft_takes_precedence_over_active():
    # 'draft' should win over 'active' since drafts are explicitly non-final.
    assert _detect_policy_status("Draft policy currently under review.") == "draft"
