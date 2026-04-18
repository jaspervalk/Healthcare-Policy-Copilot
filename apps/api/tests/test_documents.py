from app.services.documents import _detect_version


def test_detect_version_extracts_first_capture_group():
    assert _detect_version("Policy revision: 7.3") == "7.3"
    assert _detect_version("Document Version ABC-2026") == "ABC-2026"
    assert _detect_version("Rev. :") is None
