"""Direct tests for core_gateway seam."""

import core_gateway


def test_format_classify_response_filed_with_confidence():
    out = core_gateway.format_classify_response({"action": "filed", "path": "x.md", "confidence": 0.9})
    assert "x.md" in out
    assert "0.9" in out


def test_format_classify_response_inboxed():
    out = core_gateway.format_classify_response({"action": "inboxed"})
    assert "Inboxed" in out
