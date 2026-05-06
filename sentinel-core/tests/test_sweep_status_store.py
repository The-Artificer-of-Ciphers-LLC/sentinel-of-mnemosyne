from app.services.sweep_status_store import get_sweep_status, reset_sweep_status, set_sweep_status_from_report


class _Report:
    sweep_id = "id-1"
    status = "running"
    files_processed = 1
    files_total = 5
    duplicates_moved = 2
    noise_moved = 3


def test_sweep_status_store_set_get_reset():
    reset_sweep_status()
    set_sweep_status_from_report(_Report())

    current = get_sweep_status()
    assert current["sweep_id"] == "id-1"
    assert current["status"] == "running"
    assert current["files_processed"] == 1

    reset_sweep_status()
    reset = get_sweep_status()
    assert reset["status"] == "idle"
    assert reset["sweep_id"] is None
