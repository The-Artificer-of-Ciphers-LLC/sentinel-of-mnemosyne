from app.services.message_error_mapper import to_http_status


def test_to_http_status_known_codes():
    assert to_http_status("context_overflow") == 422
    assert to_http_status("provider_unavailable") == 503
    assert to_http_status("provider_misconfigured") == 502
    assert to_http_status("security_blocked") == 500


def test_to_http_status_unknown_defaults_502():
    assert to_http_status("unknown") == 502
