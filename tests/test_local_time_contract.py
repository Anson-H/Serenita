from datetime import datetime
from backend.app.core.time import local_now_iso as now_iso
from backend.app.application.report_validation import normalize_report_time
from backend.app.core.time import local_datetime_from_epoch_ms, local_iso, local_now, parse_local_datetime
from backend.app.domain.conversations.events import iso_to_epoch_ms


def test_generated_times_use_the_process_local_offset():
    generated = datetime.fromisoformat(now_iso())

    assert generated.tzinfo is not None
    assert generated.utcoffset() == local_now().utcoffset()


def test_aware_input_is_rendered_in_local_time():
    source = "2026-08-21T01:15:30+00:00"
    expected = datetime.fromisoformat(source).astimezone()

    assert parse_local_datetime(source) == expected
    assert local_iso(source) == expected.isoformat()


def test_naive_input_is_interpreted_as_local_wall_clock_time():
    source = "2026-08-21T09:15:30"
    expected = datetime.fromisoformat(source).astimezone()

    assert parse_local_datetime(source) == expected
    assert iso_to_epoch_ms(source) == int(expected.timestamp() * 1000)


def test_epoch_event_output_is_local_time():
    timestamp = 1_777_777_777_000
    rendered = local_datetime_from_epoch_ms(timestamp)

    assert rendered.tzinfo is not None
    assert rendered.utcoffset() == local_now().utcoffset()
    assert int(rendered.timestamp() * 1000) == timestamp


def test_report_dates_and_datetimes_normalize_to_local_iso():

    assert normalize_report_time("2026-08-21") == local_iso(
        "2026-08-21T00:00:00"
    )
    assert normalize_report_time(
        "2026-08-21T01:15:30Z"
    ) == local_iso("2026-08-21T01:15:30Z")
