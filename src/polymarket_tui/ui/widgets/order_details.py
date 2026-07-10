"""Full-detail rendering of a resting order for cancel confirmations.

The money-path rule: a cancel confirm must show every field the user needs to
know exactly which order they are killing (side, outcome, price, the full
size/filled/resting split, when it was placed, and the order id). Shared by the
market screen and the portfolio so the "show all the details" principle holds
in every place an order can be cancelled.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation

from rich.text import Text

from polymarket_tui.core import fmt
from polymarket_tui.models.portfolio import OpenOrder
from polymarket_tui.models.ws import UserOrderMessage
from polymarket_tui.services.orders import format_shares
from polymarket_tui.ui.theme import DOWN, UP


def action_hints(*pairs: tuple[str, str]) -> Text:
    """Key hints for an armed confirm (enter place   esc edit).

    One quiet style for every confirm surface, matching the footer: the
    key bold, the label dim. Confirms proceed with enter and step back
    with esc everywhere (order panel, cancel strips, modals).
    """
    out = Text()
    for i, (key, label) in enumerate(pairs):
        if i:
            out.append("   ")
        out.append(key, style="bold")
        out.append(f" {label}", style="dim")
    return out


def cancel_confirm_text(
    orders: list[OpenOrder], title: str | None = None, show_chip: bool = True
) -> Text:
    """The armed cancel strip: CANCEL chip, full order details, key hints.

    `show_chip` prints the leading red CANCEL chip; callers whose surface
    already carries a "CANCEL ORDER" border title pass False so the label
    is not stated twice.
    """
    out = Text()
    if show_chip:
        out.append("CANCEL", style=f"bold {DOWN}")
        if len(orders) > 1:
            out.append(f" {len(orders)} orders at this level", style="bold")
        out.append("\n")
    elif len(orders) > 1:
        out.append(f"{len(orders)} orders at this level\n", style="bold")
    for order in orders:
        out.append_text(order_detail_text(order, title))
        out.append("\n")
    out.append_text(action_hints(("enter", "confirm cancel"), ("esc", "keep")))
    return out


def order_event_label(msg: UserOrderMessage) -> str:
    """One toast line for an own-order transition arriving on /ws/user.

    `size_matched` is the only fill size the exchange hands us that we can trust
    (the post response carries makingAmount/takingAmount, whose orientation the
    CLOB does not document). A LIVE order is only *partly* resting once some of
    it has filled, so the two numbers must both appear: quoting original_size
    alone - as this toast used to - announced a 100-share sell that filled 40 as
    "Order resting: SELL 100 Yes", which is the exact confusion between an
    immediate fill and a resting limit order that this line exists to settle.
    """
    try:
        matched = Decimal(msg.size_matched or "0")
        total = Decimal(msg.original_size or "0")
    except InvalidOperation:
        matched, total = Decimal(0), Decimal(0)
    resting = total - matched

    def line(size: Decimal) -> str:
        price = fmt.cents_exact(float(msg.price or 0))
        return f"{msg.side} {format_shares(size)} {msg.outcome} @ {price}"

    # The lead word answers "filled, or resting?" before the numbers land.
    if msg.status == "MATCHED":
        return f"Filled: {line(total)}"
    if msg.status == "CANCELED":
        if matched > 0:
            return (
                f"Canceled: {line(resting)}"
                f" ({format_shares(matched)} of {format_shares(total)} had filled)"
            )
        return f"Canceled: {line(total)}"
    if msg.status == "LIVE":
        if matched > 0:
            return (
                f"Partly filled: {line(total)}"
                f" - {format_shares(matched)} filled, {format_shares(resting)} resting"
            )
        return f"Resting on the book: {line(total)} - nothing filled"
    return f"Order {msg.status.lower() or 'updated'}: {line(total)}"


def order_detail_text(order: OpenOrder, title: str | None = None) -> Text:
    """Every field of a resting order, ranked for a cancel decision.

    Which order (side/outcome/price) reads first in bold; then the amount the
    cancel removes (resting, emphasised) with the filled/original split as
    context; then placed time and id (dim) to disambiguate look-alikes. The
    whole block used to render dim and was hard to read - only the truly
    secondary meta stays dim now.
    """
    side_style = UP if order.side == "BUY" else DOWN
    out = Text()
    if title:
        out.append(title.strip() + "\n", style="bold")
    out.append(order.side + " ", style=f"bold {side_style}")
    out.append(f"{order.outcome or '-'} ", style="bold")
    out.append(f"@ {fmt.cents(order.price)}\n", style="bold")
    # The shares this cancel removes - the number that matters most here.
    out.append("resting ", style="dim")
    out.append(f"{order.remaining:,.0f}", style="bold")
    out.append(
        f"  ·  {order.size_matched:,.0f} filled of {order.original_size:,.0f}\n",
        style="dim",
    )
    placed = order.when.astimezone().strftime("%b %d %H:%M") if order.when else "unknown"
    out.append(f"placed {placed}", style="dim")
    if order.id:
        out.append(f"  ·  {order.id[:12]}…", style="dim")
    return out
