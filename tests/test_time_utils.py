from november_whiskey.utils.time import format_pacific_human


def test_format_pacific_human_formats_as_requested():
    rendered = format_pacific_human("2026-04-14T13:00:00")
    assert rendered == "Tuesday, 4/14 at 1:00 pm Pacific"
