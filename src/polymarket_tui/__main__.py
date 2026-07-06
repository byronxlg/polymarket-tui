import argparse
from importlib.metadata import version

from polymarket_tui.ui.app import PolymarketApp


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="polymarket-tui",
        description="Terminal client for Polymarket: browse markets, watch live "
        "order books, chart prices, track your portfolio, and place orders.",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"polymarket-tui {version('polymarket-tui')}",
    )
    # No positional args today; parsing still exposes --version/--help so a
    # packaged binary (Homebrew, uv tool) is inspectable without launching the UI.
    parser.parse_args()
    PolymarketApp().run()


if __name__ == "__main__":
    main()
