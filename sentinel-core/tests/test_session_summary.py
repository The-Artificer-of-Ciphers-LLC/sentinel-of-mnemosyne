from app.services.session_summary import build_session_summary


def test_build_session_summary_path_and_content_shape():
    path, content = build_session_summary("u1", "hi", "hello", "m1")
    assert path.startswith("ops/sessions/")
    assert "/u1-" in path
    assert "## User" in content
    assert "## Sentinel" in content
