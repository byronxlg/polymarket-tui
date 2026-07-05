"""Full-detail rendering of a resting order for cancel confirmations.

The money-path rule: a cancel confirm must show every field the user needs to
know exactly which order they are killing (side, outcome, price, the full
size/filled/resting split, when it was placed, and the order id). Shared by the
market screen and the portfolio so the "show all the details" principle holds
in every place an order can be cancelled.
"""

from __future__ import annotations

from rich.text import Text

from polymarket_tui.core import fmt
from polymarket_tui.models.portfolio import OpenOrder
from polymarket_tui.ui.theme import DOWN, UP


def order_detail_text(order: OpenOrder, title: str | None = None) -> Text:
    """Every field of a resting order, as a multi-line Text block."""
    side_style = UP if order.side == "BUY" else DOWN
    out = Text()
    if title:
        out.append(title.strip() + "\n", style="bold")
    out.append(order.side + " ", style=f"bold {side_style}")
    out.append(f"{order.outcome or '-'} ", style="bold")
    out.append(f"@ {fmt.cents(order.price)}\n", style="bold")
    out.append(
        f"size {order.original_size:,.0f}   filled {order.size_matched:,.0f}"
        f"   resting {order.remaining:,.0f}\n",
        style="dim",
    )
    placed = order.when.astimezone().strftime("%b %d %H:%M") if order.when else "unknown"
    out.append(f"placed {placed}", style="dim")
    if order.id:
        out.append(f"   id {order.id[:12]}…", style="dim")
    return out
