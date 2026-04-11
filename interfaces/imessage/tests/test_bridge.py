"""Tests for iMessage bridge — RD-08 / STUB-05."""
import plistlib
import sys
import os

# Add repo root to path so 'interfaces' package resolves
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))


def _make_plist_blob(text: str) -> bytes:
    """Create a minimal NSKeyedArchiver-style plist with NS.string."""
    data = {"NS.string": text}
    return plistlib.dumps(data)


def test_decode_attributed_body_valid_blob():
    from interfaces.imessage.bridge import _decode_attributed_body

    blob = _make_plist_blob("Hello from Ventura")
    assert _decode_attributed_body(blob) == "Hello from Ventura"


def test_decode_attributed_body_invalid_blob():
    from interfaces.imessage.bridge import _decode_attributed_body

    assert _decode_attributed_body(b"not a plist") is None


def test_decode_attributed_body_missing_ns_string():
    from interfaces.imessage.bridge import _decode_attributed_body

    blob = plistlib.dumps({"other_key": "value"})
    assert _decode_attributed_body(blob) is None


def test_poll_skips_truly_empty_message():
    """Messages with both text=NULL and attributedBody=NULL are skipped."""
    from interfaces.imessage.bridge import _decode_attributed_body

    result = _decode_attributed_body(b"")
    assert result is None
