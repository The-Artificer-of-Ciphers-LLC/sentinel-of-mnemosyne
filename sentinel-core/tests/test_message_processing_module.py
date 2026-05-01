from app.services.message_processing import MessageProcessor


def test_format_search_results_includes_filename_and_snippet():
    text = MessageProcessor._format_search_results(
        [{"filename": "a.md", "matches": [{"context": "hello"}]}]
    )
    assert "a.md" in text
    assert "hello" in text


def test_context_length_marker_detection():
    class E(Exception):
        pass

    exc = E("maximum context length exceeded")
    assert MessageProcessor._is_context_length_error(exc) is True
