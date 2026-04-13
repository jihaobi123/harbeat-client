"""GrooveEngine application entrypoint."""

from __future__ import annotations

from ui.cli import GrooveCLI


def main() -> None:
    """Run the GrooveEngine CLI."""

    GrooveCLI().run()


if __name__ == "__main__":
    main()
