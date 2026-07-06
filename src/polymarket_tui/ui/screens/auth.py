"""Auth screen: credential status, credential entry, live toggle.

Applied credentials are saved to ~/.config/polymarket-tui/credentials.toml
(mode 0600, outside any git tree). The key input is masked and never logged.
The live flag persists with the credentials; a LIVE start is announced loudly.
"""

from __future__ import annotations

from rich.text import Text
from textual import work
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import Screen
from textual.widgets import Input, Label, Select, Static

from polymarket_tui.api.clob_auth import AuthedClobClient
from polymarket_tui.core import fmt
from polymarket_tui.core.config import Mode, Settings
from polymarket_tui.core.credstore import (
    CRED_PATH,
    clear_credentials,
    key_backend,
    save_credentials,
)
from polymarket_tui.core.proxy import check_pairing
from polymarket_tui.ui.theme import AMBER, BLUE, DOWN, UP
from polymarket_tui.ui.widgets.app_footer import AppFooter
from polymarket_tui.ui.widgets.app_header import AppHeader
from polymarket_tui.ui.widgets.confirm_modal import ConfirmModal

SIG_TYPES = [
    ("1 - Polymarket proxy wallet (default)", "1"),
    ("0 - direct EOA", "0"),
    ("2 - Magic / email login", "2"),
]

MODE_DESCRIPTIONS = {
    Mode.READ_ONLY: "browse, books, charts, watchlist",
    Mode.OBSERVER: "+ positions, P&L, activity (funder only)",
    Mode.TRADER_DRY: "+ balance, open orders; orders signed but never posted",
    Mode.TRADER_LIVE: "orders and cancels are POSTED FOR REAL",
}


def short_address(address: str) -> str:
    if len(address) <= 12:
        return address
    return f"{address[:6]}...{address[-4:]}"


def derive_signer(private_key: str) -> str | None:
    """EOA address controlled by the key. None if the key is malformed."""
    try:
        from eth_account import Account

        key = private_key if private_key.startswith("0x") else "0x" + private_key
        return Account.from_key(key).address
    except Exception:
        return None


class AuthScreen(Screen):
    BINDINGS = [
        Binding("escape", "app.pop_screen", "back"),
        Binding("ctrl+s", "apply", "apply & test"),
        Binding("ctrl+d", "clear_creds", "clear credentials"),
    ]

    DEFAULT_CSS = """
    AuthScreen #auth-body {
        padding: 1 2;
        width: 90;
        max-width: 100%;
    }
    AuthScreen .field-row {
        height: 3;
    }
    AuthScreen Label {
        padding: 1 1 0 0;
        width: 12;
    }
    AuthScreen Input {
        width: 1fr;
        max-width: 70;
    }
    AuthScreen Select {
        width: 44;
    }
    AuthScreen #auth-status {
        margin-bottom: 1;
        height: auto;
    }
    AuthScreen #auth-result {
        margin-top: 1;
        height: auto;
        min-height: 2;
    }
    AuthScreen .section-title {
        text-style: bold;
        margin-top: 1;
    }
    """

    def compose(self) -> ComposeResult:
        settings = self.app.settings
        yield AppHeader("auth")
        with Vertical(id="auth-body"):
            yield Static(id="auth-status")
            yield Static(
                f"credentials  (saved on apply to {CRED_PATH}, chmod 600)",
                classes="section-title",
            )
            with Horizontal(classes="field-row"):
                yield Label("funder")
                yield Input(
                    value=settings.polymarket_funder,
                    placeholder="proxy wallet address 0x...",
                    id="funder-input",
                )
            with Horizontal(classes="field-row"):
                yield Label("private key")
                yield Input(
                    password=True,
                    placeholder="unchanged" if settings.polymarket_private_key else "hex key",
                    id="key-input",
                )
            with Horizontal(classes="field-row"):
                yield Label("sig type")
                yield Select(
                    SIG_TYPES,
                    value=str(settings.polymarket_signature_type),
                    allow_blank=False,
                    id="sig-select",
                )
            with Horizontal(classes="field-row"):
                yield Label("execution")
                yield Select(
                    [("DRY - sign only, never post", "DRY"), ("LIVE - post real orders", "LIVE")],
                    value="LIVE" if settings.polymarket_execution_live else "DRY",
                    allow_blank=False,
                    id="live-select",
                )
            yield Static(id="auth-result")
        yield AppFooter()

    def on_mount(self) -> None:
        self.title = "auth"
        self._render_status()
        self.query_one("#funder-input", Input).focus()

    def _render_status(self, extra: Text | None = None) -> None:
        settings = self.app.settings
        mode = settings.mode
        out = Text()
        out.append("status\n", style="bold")
        mode_style = {"RO": "dim", "OBS": BLUE, "DRY": AMBER, "LIVE": f"bold {DOWN}"}[mode.value]
        out.append(f"  mode          {mode.value}", style=mode_style)
        out.append(f"  ({MODE_DESCRIPTIONS[mode]})\n", style="dim")
        funder = settings.polymarket_funder
        out.append(f"  funder        {short_address(funder) if funder else '(not set)'}\n")
        backend = "macOS Keychain" if key_backend() == "keychain" else "file (plaintext)"
        if settings.polymarket_private_key:
            key_state = f"present (in memory, stored in {backend})"
        else:
            key_state = "(not set)"
        out.append(f"  private key   {key_state}\n")
        if settings.polymarket_private_key:
            signer = derive_signer(settings.polymarket_private_key)
            out.append(f"  signer        {signer or 'INVALID KEY'}")
            out.append("  (verify this is your wallet address)\n", style="dim")
            if signer and funder:
                state, detail = check_pairing(
                    signer, funder, settings.polymarket_signature_type
                )
                pair_style = {"proven": UP, "mismatch": f"bold {DOWN}", "unproven": AMBER}[
                    state
                ]
                label = {"proven": "PROVEN", "mismatch": "MISMATCH", "unproven": "unproven"}[state]
                out.append(f"  key<->funder  {label}", style=pair_style)
                out.append(f"  ({detail})\n", style="dim")
        out.append(f"  sig type      {settings.polymarket_signature_type}\n")
        stored = "saved" if CRED_PATH.exists() else "not saved"
        out.append(f"  storage       {stored} ({CRED_PATH})\n")
        if self.app.authed is not None and self.app.authed.auth_failed:
            out.append(f"  L2 creds      failed: {self.app.authed.auth_failed}\n", style=DOWN)
        if extra is not None:
            out.append_text(extra)
        self.query_one("#auth-status", Static).update(out)

    # -- apply -------------------------------------------------------------------

    def _candidate_settings(self) -> Settings:
        current = self.app.settings
        funder = self.query_one("#funder-input", Input).value.strip()
        key_raw = self.query_one("#key-input", Input).value.strip()
        key = key_raw or current.polymarket_private_key  # blank = keep existing
        sig_type = int(self.query_one("#sig-select", Select).value)
        live = self.query_one("#live-select", Select).value == "LIVE"
        return Settings(
            polymarket_funder=funder,
            polymarket_private_key=key,
            polymarket_signature_type=sig_type,
            polymarket_execution_live=live,
            polymarket_host=current.polymarket_host,
            pmtui_max_notional=current.pmtui_max_notional,
        )

    def action_apply(self) -> None:
        candidate = self._candidate_settings()
        if candidate.mode is Mode.TRADER_LIVE and self.app.settings.mode is not Mode.TRADER_LIVE:
            body = Text()
            body.append("Orders and cancels will be posted to the exchange for real.\n")
            body.append("Dry-run protection is OFF for this session.", style=f"bold {DOWN}")

            def _confirmed(ok: bool | None) -> None:
                if ok:
                    self.apply_and_test(candidate)
                else:
                    self.query_one("#live-select", Select).value = "DRY"

            self.app.push_screen(
                ConfirmModal("ENABLE LIVE TRADING", body, "go live", tone="danger"),
                _confirmed,
            )
            return
        self.apply_and_test(candidate)

    @work(exclusive=True, group="auth-test")
    async def apply_and_test(self, candidate: Settings) -> None:
        result_widget = self.query_one("#auth-result", Static)
        result_widget.update(Text("testing...", style="dim"))

        report = Text()
        ok = True
        if candidate.can_auth:
            signer = derive_signer(candidate.polymarket_private_key)
            state, detail = "unproven", ""
            if signer is None:
                ok = False
                report.append("private key is not a valid secp256k1 key\n", style=DOWN)
            else:
                # Authoritative offline check: does this key control the funder?
                # Types 0/1 are proven or refuted here; type 2 stays unproven.
                state, detail = check_pairing(
                    signer, candidate.polymarket_funder, candidate.polymarket_signature_type
                )
                if state == "mismatch":
                    ok = False
                    report.append(f"key/funder mismatch: {detail}\n", style=DOWN)
            if ok:
                authed = AuthedClobClient(candidate)
                try:
                    balance = await authed.usdc_balance()
                    report.append(f"L2 auth ok - cash {fmt.money(balance)}\n", style=UP)
                    report.append(f"signer {signer}\n")
                    if state == "proven":
                        report.append(f"pairing proven: {detail}\n", style=UP)
                    elif state == "unproven":
                        report.append(f"pairing unproven: {detail}\n", style=AMBER)
                    if balance == 0 and state != "proven":
                        report.append(
                            "cash $0.00 can mean a wrong key for this funder -"
                            " check the signer matches your wallet\n",
                            style=AMBER,
                        )
                except Exception as exc:
                    ok = False
                    report.append(f"auth failed: {exc}\n", style=DOWN)
            if not ok:
                report.append("kept previous credentials\n", style="dim")
        elif candidate.polymarket_funder:
            try:
                value = await self.app.data.portfolio_value(candidate.polymarket_funder)
                report.append(
                    f"observer ok - portfolio value {fmt.money(value or 0.0)}\n", style=UP
                )
            except Exception as exc:
                ok = False
                report.append(f"funder lookup failed: {exc}\n", style=DOWN)
        else:
            report.append("no credentials - read-only mode\n", style=AMBER)

        if ok:
            self.app.reconfigure(candidate)
            self.query_one("#key-input", Input).value = ""
            self.query_one("#key-input", Input).placeholder = (
                "unchanged" if candidate.polymarket_private_key else "hex key"
            )
            if candidate.polymarket_funder or candidate.polymarket_private_key:
                path = save_credentials(
                    candidate.polymarket_funder,
                    candidate.polymarket_private_key,
                    candidate.polymarket_signature_type,
                    execution_live=candidate.polymarket_execution_live,
                )
                report.append(f"saved to {path} (0600)\n", style="dim")
            report.append(f"applied - mode is now {candidate.mode.value}", style="bold")
        result_widget.update(report)
        self._render_status()

    def action_clear_creds(self) -> None:
        def _confirmed(ok: bool | None) -> None:
            if ok:
                cleared = Settings(
                    polymarket_funder="",
                    polymarket_private_key="",
                    polymarket_signature_type=1,
                    polymarket_execution_live=False,
                    polymarket_host=self.app.settings.polymarket_host,
                    pmtui_max_notional=self.app.settings.pmtui_max_notional,
                )
                self.app.reconfigure(cleared)
                removed = clear_credentials()
                self.query_one("#funder-input", Input).value = ""
                self.query_one("#key-input", Input).value = ""
                message = "credentials cleared - read-only mode"
                if removed:
                    message += f" (deleted {CRED_PATH})"
                self.query_one("#auth-result", Static).update(Text(message, style=AMBER))
                self._render_status()

        self.app.push_screen(
            ConfirmModal(
                "CLEAR CREDENTIALS",
                "Drop funder and private key from this session AND delete the saved file?",
                "clear",
                tone="danger",
            ),
            _confirmed,
        )
