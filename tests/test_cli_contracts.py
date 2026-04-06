from november_whiskey.cli import build_parser


def test_parser_has_expected_commands():
    parser = build_parser()
    args = parser.parse_args(["signal", "find"])
    assert args.command == "signal"


def test_parser_output_format_choices():
    parser = build_parser()
    args = parser.parse_args(["--output-format", "json", "config-check"])
    assert args.output_format == "json"
