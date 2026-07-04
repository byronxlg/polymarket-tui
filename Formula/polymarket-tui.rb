class PolymarketTui < Formula
  desc "Terminal client for Polymarket"
  homepage "https://github.com/byronxlg/polymarket-tui"
  # Brew users get this pinned snapshot; bump revision (and version) to ship
  # newer code to them. `brew install --HEAD` tracks main instead.
  url "https://github.com/byronxlg/polymarket-tui.git",
      revision: "4e6df237d436a7818ad03f4bdc2d726e7567e12e"
  version "0.1.0"
  head "https://github.com/byronxlg/polymarket-tui.git", branch: "main"

  depends_on "python@3.12"

  def install
    python = Formula["python@3.12"].opt_bin/"python3.12"
    system python, "-m", "venv", libexec
    # Personal tap: dependencies come from PyPI at install time instead of
    # being vendored as homebrew-core-style resource blocks.
    system libexec/"bin/pip", "install", "--quiet", "--upgrade", "pip"
    system libexec/"bin/pip", "install", "--quiet", buildpath.to_s
    bin.install_symlink libexec/"bin/polymarket-tui"
  end

  test do
    system libexec/"bin/python", "-c", "import polymarket_tui"
  end
end
