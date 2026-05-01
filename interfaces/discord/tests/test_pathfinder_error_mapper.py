import pathfinder_error_mapper


def test_map_http_status_conflict():
    assert "already exists" in pathfinder_error_mapper.map_http_status(409, "dup")


def test_map_http_status_generic():
    out = pathfinder_error_mapper.map_http_status(500, "boom")
    assert "HTTP 500" in out
