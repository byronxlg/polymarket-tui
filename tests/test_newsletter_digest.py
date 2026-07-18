"""Newsletter digest logic (infra/newsletter/src, stdlib-only modules).

The lambda sources are not part of the package; import them straight off the
source directory. Only the boto3-free modules are imported here.
"""

import json
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "infra" / "newsletter" / "src"
sys.path.insert(0, str(SRC))

from blurb import build_headlines_prompt, extract_headlines  # noqa: E402
from digest_data import (  # noqa: E402
    build_digest,
    digest_is_empty,
    select_ending_soon,
    select_movers,
    select_new_markets,
    select_top_events,
)
from digest_render import (  # noqa: E402
    UNSUB_PLACEHOLDER,
    fmt_cents,
    fmt_journey,
    fmt_usd,
    fmt_when_nz,
    render_html,
    render_subject,
    render_text,
)
from news import build_news_query, parse_news_rss  # noqa: E402
from nl_common import new_token, normalize_email  # noqa: E402

NOW = datetime(2026, 7, 18, 7, 0, tzinfo=UTC)


def market(
    question="Will it happen?",
    yes=0.40,
    change=0.05,
    volume=50_000.0,
    event_slug="the-event",
    created=None,
    end="2026-07-20T00:00:00Z",
    outcomes=None,
):
    return {
        "question": question,
        "slug": question.lower().replace(" ", "-").strip("?"),
        "outcomes": json.dumps(outcomes or ["Yes", "No"]),
        "outcomePrices": json.dumps([str(yes), str(1 - yes)]),
        "oneDayPriceChange": change,
        "volume24hr": volume,
        "endDate": end,
        "createdAt": created,
        "events": [{"slug": event_slug, "title": "The event"}],
    }


def event(
    title="The event", slug="the-event", volume=100_000.0, end="2026-07-19T12:00:00Z", markets=None
):
    return {
        "title": title,
        "slug": slug,
        "volume24hr": volume,
        "endDate": end,
        "markets": markets if markets is not None else [market()],
    }


class TestNormalizeEmail:
    def test_valid_is_lowercased_and_trimmed(self):
        assert normalize_email("  A.Reader@Example.COM ") == "a.reader@example.com"

    def test_garbage_rejected(self):
        for bad in (None, 42, "", "nope", "a@b", "a b@c.d", "x" * 300 + "@a.bc"):
            assert normalize_email(bad) is None


def test_tokens_are_unique_and_long():
    a, b = new_token(), new_token()
    assert a != b
    assert len(a) > 30


class TestSelectMovers:
    def test_picks_biggest_absolute_change_first(self):
        markets = [
            market(question="Small up", change=0.04),
            market(question="Big down", change=-0.20, event_slug="down-event"),
        ]
        picked = select_movers(markets)
        assert [m["title"] for m in picked] == ["Big down", "Small up"]

    def test_filters_resolved_prices_low_volume_small_moves(self):
        markets = [
            market(question="Basically resolved", yes=0.99, change=0.30),
            market(question="Illiquid", volume=500.0, change=0.30),
            market(question="Barely moved", change=0.01),
        ]
        assert select_movers(markets) == []

    def test_one_market_per_event(self):
        markets = [
            market(question="Leader", change=0.10),
            market(question="Sibling", change=0.08),
        ]
        picked = select_movers(markets)
        assert [m["title"] for m in picked] == ["Leader"]


class TestSelectTopEvents:
    def test_sorted_by_volume_with_leader(self):
        events = [
            event(title="Quiet", volume=10.0),
            event(
                title="Busy",
                volume=5_000_000.0,
                markets=[
                    market(question="Longshot", yes=0.05),
                    {**market(question="Front runner", yes=0.80), "groupItemTitle": "Front runner"},
                ],
            ),
        ]
        picked = select_top_events(events)
        assert picked[0]["title"] == "Busy"
        assert picked[0]["leader"]["name"] == "Front runner"
        assert picked[0]["leader"]["yes"] == 0.80

    def test_zero_volume_dropped(self):
        assert select_top_events([event(volume=0.0)]) == []

    def test_leader_name_blanked_when_it_repeats_the_title(self):
        single = event(
            title="Utah Jazz vs. Portland Trail Blazers",
            markets=[
                {
                    **market(question="Utah Jazz vs. Portland Trail Blazers", yes=0.57),
                    "groupItemTitle": "Utah Jazz vs. Portland Trail Blazers",
                }
            ],
        )
        leader = select_top_events([single])[0]["leader"]
        assert leader["name"] == ""
        assert leader["yes"] == 0.57

    def test_match_leader_is_the_main_markets_leading_team(self):
        match = event(
            title="HLE vs T1",
            slug="lol-hle-t1",
            markets=[
                {**market(question="Any Player Penta Kill?", yes=0.50), "slug": "penta"},
                {
                    **market(question="Match Winner", yes=0.14, outcomes=["HLE", "T1"]),
                    "slug": "lol-hle-t1",
                },
            ],
        )
        leader = select_top_events([match])[0]["leader"]
        assert leader["name"] == "T1"
        assert abs(leader["yes"] - 0.86) < 1e-9

    def test_decided_match_still_names_the_winner_over_props(self):
        match = event(
            title="HLE vs T1",
            slug="lol-hle-t1",
            markets=[
                {**market(question="Any Player Penta Kill?", yes=0.50), "slug": "penta"},
                {
                    **market(question="Match Winner", yes=0.0, outcomes=["HLE", "T1"]),
                    "slug": "lol-hle-t1",
                },
            ],
        )
        leader = select_top_events([match])[0]["leader"]
        assert leader["name"] == "T1"
        assert leader["yes"] == 1.0

    def test_leader_skips_resolved_outcomes(self):
        events = [
            event(
                markets=[
                    {**market(question="Game 1 already over", yes=1.0), "groupItemTitle": "Game 1"},
                    {**market(question="Series winner", yes=0.60), "groupItemTitle": "Series"},
                ]
            )
        ]
        assert select_top_events(events)[0]["leader"]["name"] == "Series"


class TestSelectEndingSoon:
    def test_window_and_volume_filter_soonest_first(self):
        events = [
            event(title="Later", slug="later", end=(NOW + timedelta(hours=40)).isoformat()),
            event(title="Sooner", slug="sooner", end=(NOW + timedelta(hours=4)).isoformat()),
            event(title="Too far", slug="far", end=(NOW + timedelta(hours=80)).isoformat()),
            event(
                title="Micro",
                slug="micro",
                end=(NOW + timedelta(hours=2)).isoformat(),
                volume=100.0,
            ),
        ]
        picked = select_ending_soon(events, NOW)
        assert [e["title"] for e in picked] == ["Sooner", "Later"]

    def test_sibling_events_collapse_to_highest_volume(self):
        end = (NOW + timedelta(hours=3)).isoformat()
        events = [
            event(title="Game", slug="mls-lag-laf-2026-07-17", end=end, volume=164_000.0),
            event(
                title="Game - Exact Score",
                slug="mls-lag-laf-2026-07-17-exact-score",
                end=end,
                volume=43_000.0,
            ),
            event(
                title="Game - More Markets",
                slug="mls-lag-laf-2026-07-17-more-markets",
                end=end,
                volume=90_000.0,
            ),
        ]
        picked = select_ending_soon(events, NOW)
        assert [e["title"] for e in picked] == ["Game"]


class TestSelectNewMarkets:
    def test_only_recent_creations_with_volume(self):
        markets = [
            market(question="Fresh and busy", created=(NOW - timedelta(hours=10)).isoformat()),
            market(
                question="Old", created=(NOW - timedelta(days=30)).isoformat(), event_slug="old"
            ),
            market(
                question="Fresh but dead",
                created=(NOW - timedelta(hours=5)).isoformat(),
                volume=10.0,
                event_slug="dead",
            ),
        ]
        picked = select_new_markets(markets, NOW)
        assert [m["title"] for m in picked] == ["Fresh and busy"]

    def test_sibling_events_deduped_keeping_busiest(self):
        created = (NOW - timedelta(hours=3)).isoformat()
        markets = [
            market(
                question="Team to Win",
                created=created,
                volume=1_200_000.0,
                event_slug="fifwc-fra-eng-2026-07-18-more-markets",
            ),
            market(
                question="Exact Score 3-1",
                created=created,
                volume=509_000.0,
                event_slug="fifwc-fra-eng-2026-07-18-exact-score",
            ),
            market(
                question="Will France win?",
                created=created,
                volume=1_100_000.0,
                event_slug="fifwc-fra-eng-2026-07-18",
            ),
        ]
        picked = select_new_markets(markets, NOW)
        assert [m["title"] for m in picked] == ["Team to Win"]

    def test_already_ended_markets_dropped(self):
        finished = market(
            question="Finished game O/U",
            created=(NOW - timedelta(hours=6)).isoformat(),
            end=(NOW - timedelta(hours=1)).isoformat(),
        )
        assert select_new_markets([finished], NOW) == []

    def test_effectively_decided_prices_dropped_but_longshots_kept(self):
        created = (NOW - timedelta(hours=6)).isoformat()
        markets = [
            market(question="Decided mid-match", yes=0.001, created=created),
            market(question="Real longshot", yes=0.02, created=created, event_slug="longshot"),
        ]
        picked = select_new_markets(markets, NOW)
        assert [m["title"] for m in picked] == ["Real longshot"]


class TestBuildDigest:
    def test_sections_survive_a_failing_fetch(self):
        def fetch(path, params):
            if path == "/events":
                raise OSError("gamma down")
            return [market(created=(NOW - timedelta(hours=1)).isoformat())]

        digest = build_digest(NOW, fetch=fetch)
        assert digest["top_events"] == []
        assert digest["ending_soon"] == []
        assert len(digest["movers"]) == 1
        # same event family as the mover, so cross-section dedupe drops it
        assert digest["new_markets"] == []
        assert not digest_is_empty(digest)

    def test_empty_when_everything_fails(self):
        def fetch(path, params):
            raise OSError("gamma down")

        assert digest_is_empty(build_digest(NOW, fetch=fetch))


class TestRender:
    def digest(self):
        def fetch(path, params):
            if path == "/markets":
                if params.get("order") == "volume24hr":
                    return [
                        market(
                            question="Fresh market",
                            created=(NOW - timedelta(hours=1)).isoformat(),
                            event_slug="fresh-event",
                        )
                    ]
                return [market()]
            if params.get("order") == "endDate":
                return [
                    event(title="Ender", slug="ender", end=(NOW + timedelta(hours=6)).isoformat())
                ]
            return [event()]

        return build_digest(NOW, fetch=fetch)

    def test_text_has_sections_and_unsub_placeholder(self):
        text = render_text(self.digest())
        assert "TOP MOVERS (24H)" in text
        assert "ENDING WITHIN 48H" in text
        assert UNSUB_PLACEHOLDER in text
        assert "polymarket.com/event/the-event" in text

    def test_html_escapes_titles_and_keeps_placeholder(self):
        digest = self.digest()
        digest["movers"][0]["title"] = "Will <b>X</b> & Y?"
        html_body = render_html(digest, "https://example.test")
        assert "Will &lt;b&gt;X&lt;/b&gt; &amp; Y?" in html_body
        assert "<b>X</b>" not in html_body
        assert UNSUB_PLACEHOLDER in html_body

    def test_subject_carries_the_date(self):
        assert render_subject(NOW) == "Polymarket daily - Sat 18 Jul"

    def test_subject_front_loads_the_story(self):
        subject = render_subject(NOW, "Nordone 11c -> 69c for SC Senate")
        assert subject == "Nordone 11c -> 69c for SC Senate - Polymarket daily"

    def test_preheader_hidden_div_present_only_when_set(self):
        digest = build_digest(NOW, fetch=lambda p, q: [])
        digest["movers"] = [
            {"title": "T", "outcome": "", "url": "u", "yes": 0.5, "change": 0.1,
             "volume24h": 1.0, "end": None}
        ]
        assert "display:none" not in render_html(digest, "https://example.test")
        digest["preheader"] = "Second story of the day"
        assert "Second story of the day" in render_html(digest, "https://example.test")


class TestBlurb:
    def digest(self):
        return TestRender.digest(self)

    def test_prompt_carries_the_data_and_the_rules(self):
        prompt = build_headlines_prompt(self.digest())
        assert "MOVER 1: Will it happen?" in prompt
        assert "MOST TRADED: The event" in prompt
        assert "no markdown" in prompt
        assert "Never invent facts" in prompt
        assert '"subject"' in prompt

    def test_extract_parses_json_and_drops_invalid_fields(self):
        raw = (
            'noise {"subject": "Nordone 11c -> 69c", "preheader": "",'
            ' "blurb": "  Two  lines. "} tail'
        )
        parsed = extract_headlines(raw)
        assert parsed == {"subject": "Nordone 11c -> 69c", "blurb": "Two lines."}
        assert extract_headlines("not json at all") == {}
        assert extract_headlines(None) == {}
        assert "subject" not in extract_headlines('{"subject": "' + "x" * 100 + '"}')

    def test_renderers_include_blurb_only_when_present(self):
        digest = self.digest()
        digest["blurb"] = "Spain <b>leads</b> the final."
        text = render_text(digest)
        html_body = render_html(digest, "https://example.test")
        assert "Spain <b>leads</b> the final." in text
        assert "Spain &lt;b&gt;leads&lt;/b&gt; the final." in html_body


class TestNews:
    RSS = b"""<rss><channel>
      <item><title>Trump endorses Nordone - Reuters</title>
        <pubDate>Fri, 17 Jul 2026 20:00:00 GMT</pubDate></item>
      <item><title>Old story - AP</title>
        <pubDate>Mon, 01 Jun 2026 10:00:00 GMT</pubDate></item>
      <item><title>Newer story - BBC</title>
        <pubDate>Sat, 18 Jul 2026 01:00:00 GMT</pubDate></item>
      <item><title>No date</title></item>
    </channel></rss>"""

    def test_query_drops_question_scaffolding(self):
        q = build_news_query(
            "Will Darline Graham Nordone be the new republican nominee for Senate?"
        )
        assert q == "Darline Graham Nordone republican nominee Senate"

    def test_rss_parse_keeps_fresh_newest_first(self):
        lines = parse_news_rss(self.RSS, NOW)
        assert lines == [
            "Newer story - BBC (Sat 18 Jul)",
            "Trump endorses Nordone - Reuters (Fri 17 Jul)",
        ]


class TestMoverNotes:
    def test_prompt_numbers_movers_and_carries_news(self):
        digest = TestRender.digest(TestRender())
        news = {digest["movers"][0]["url"]: ["Trump endorses Nordone - Reuters (Fri 17 Jul)"]}
        prompt = build_headlines_prompt(digest, news)
        assert "- MOVER 1:" in prompt
        assert "    NEWS: Trump endorses Nordone" in prompt
        assert '"mover_notes"' in prompt

    def test_extract_cleans_notes(self):
        raw = '{"subject": "s", "mover_notes": ["  a  cause ", 42, "' + "x" * 200 + '"]}'
        assert extract_headlines(raw)["mover_notes"] == ["a cause", "", ""]

    def test_note_renders_in_both_formats(self):
        digest = TestRender.digest(TestRender())
        digest["movers"][0]["note"] = "Trump endorsed Nordone on Friday"
        text = render_text(digest)
        html_body = render_html(digest, "https://example.test")
        assert "why: Trump endorsed Nordone on Friday" in text
        assert "why: Trump endorsed Nordone on Friday" in html_body


class TestFormatting:
    def test_cents(self):
        assert fmt_cents(0.33) == "33c"
        assert fmt_cents(0.005) == "0.5c"
        assert fmt_cents(0.999) == "99.9c"
        assert fmt_cents(1.0) == "100c"

    def test_usd(self):
        assert fmt_usd(4_900_000) == "$4.9m"
        assert fmt_usd(770_000) == "$770k"
        assert fmt_usd(320) == "$320"

    def test_outcome_label_names_the_yes_side_only_for_team_markets(self):
        from digest_data import _outcome_label

        assert _outcome_label(market(outcomes=["France", "England"])) == "France"
        assert _outcome_label(market(outcomes=["Yes", "No"])) == ""
        assert _outcome_label({"outcomes": "not json"}) == ""

    def test_journey_shows_prior_to_current(self):
        assert fmt_journey({"yes": 0.69, "change": 0.57}) == "12c -> 69c"
        assert fmt_journey({"yes": 0.5, "change": 0.004}) is None

    def test_nz_deadlines_read_like_a_clock(self):
        # NOW is Sat 18 Jul 07:00 UTC = Sat 19:00 NZT
        same_day = datetime(2026, 7, 18, 9, 30, tzinfo=UTC)  # 21:30 NZT Sat
        next_day = datetime(2026, 7, 18, 22, 0, tzinfo=UTC)  # 10am NZT Sun
        assert fmt_when_nz(same_day, NOW) == "today 9:30pm NZT"
        assert fmt_when_nz(next_day, NOW) == "tomorrow 10am NZT"
