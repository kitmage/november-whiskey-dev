from november_whiskey.cli import main

if __name__ == "__main__":
    raise SystemExit(main(["signal", "find", "--output-format", "ndjson"]))
