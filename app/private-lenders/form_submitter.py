import sys
from november_whiskey.cli import main

if __name__ == "__main__":
    argv = ["form", "submit"] + sys.argv[1:]
    raise SystemExit(main(argv))
