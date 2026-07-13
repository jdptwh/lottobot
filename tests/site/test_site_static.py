"""tests/site/test_site_static.py — M4b gates (docs/specs/m4b_site_spec.md).

Two independent test groups, both stdlib-only (no new deps):

1. Contract test — runs against the real, M4a-regenerated data/latest.json.
   Asserts every field site/index.html's JS dereferences exists with the
   right type/nullability, plus the M4a invariants (rated <=> score/grade
   non-null, flag/reason agreement on claim-lag, lossless reason grouping,
   flags subset of the frozen vocabulary) and the current-data ground truth
   (630 tops the eligible ranking, game_no ascending, as_of ISO-parses).

2. Offline-clean + required-content lint — parametrized over BOTH the
   approved mockup (docs/mockups/best_pick_mockup.html) and the build
   (site/index.html): no externally-loaded resources beyond allowed <a href>
   links, and the verbatim copy fragments (§5/§8 caveat, framing, footer,
   explainer) are present. Site-only anchors: exactly one fetch() targeting
   ../data/latest.json, a named isEligible function referencing both `rated`
   and `ev_out_of_range`, and the mockup-only state-switcher marker absent.
   Mockup-only: the switcher marker present.

Plus a small pages_deploy.md lint (skips cleanly while that BULK-owned file
doesn't exist yet — see docs/specs/m4b_site_spec.md file plan).
"""
import datetime
import json
import re
from html.parser import HTMLParser
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
DATA_PATH = REPO_ROOT / "data" / "latest.json"
FROZEN_ARTIFACT_PATH = (
    REPO_ROOT / "tests" / "scraper" / "fixtures" / "latest_2026-07-11.json"
)
MOCKUP_PATH = REPO_ROOT / "docs" / "mockups" / "best_pick_mockup.html"
SITE_PATH = REPO_ROOT / "site" / "index.html"
PAGES_DEPLOY_PATH = REPO_ROOT / "docs" / "pages_deploy.md"

# Same harness-packaging-copy skip guard as tests/scraper/test_compute.py:
# site/ and data/ are this project's own artifacts, not part of the
# installable harness, and are not copied into the nested self-test
# directory (scripts/harness.manifest.json's copy_dirs is .claude/*, panel,
# tests, docs — no "site" or "data").
if not SITE_PATH.exists() or not DATA_PATH.exists():
    pytest.skip(
        "site/ and data/ are this project's own artifacts, not part of the installable harness",
        allow_module_level=True,
    )

CLOSED_GRADES = {"A", "A-", "B+", "B", "B-", "C", "D", "F"}
FLAG_VOCAB = {"low_inventory", "sold_out", "anomaly_candidate", "ev_out_of_range", "no_print_run"}

REQUIRED_SUBSTRINGS = [
    "1-800-GAMBLER",
    "Official Outstanding Prize List prevails",
    "cannot predict",
    "as of",
    "mainelottery.com",
    "warning sign, not a tip",
    "no score predicts a win",
]


def _load_data():
    return json.loads(DATA_PATH.read_text(encoding="utf-8"))


def _is_eligible(g):
    return g["rated"] is True and "ev_out_of_range" not in g["flags"]


# ============================================================================
# 1. Contract test (real data/latest.json)
# ============================================================================

@pytest.fixture(scope="module")
def data():
    return _load_data()


class TestContract:
    def test_top_level_shape(self, data):
        assert {"as_of", "source_timestamp", "games"} <= set(data.keys())
        assert isinstance(data["games"], list)
        assert len(data["games"]) > 0

    def test_games_game_no_ascending(self, data):
        nos = [g["game_no"] for g in data["games"]]
        assert nos == sorted(nos)

    def test_as_of_iso_parses(self, data):
        datetime.date.fromisoformat(data["as_of"])

    def test_field_types_and_nullability(self, data):
        for g in data["games"]:
            assert isinstance(g["game_no"], int)
            assert isinstance(g["name"], str) and g["name"]
            assert isinstance(g["price"], (int, float)) and not isinstance(g["price"], bool)
            assert isinstance(g["percent_unsold"], (int, float))
            assert isinstance(g["total_unclaimed"], (int, float))
            assert isinstance(g["top_prizes"], list)
            for tp in g["top_prizes"]:
                assert isinstance(tp["level"], int)
                assert isinstance(tp["remaining"], int)
            assert g["print_run"] is None or isinstance(g["print_run"], int)
            assert g["remaining_tickets"] is None or isinstance(g["remaining_tickets"], (int, float))
            assert g["ev_per_ticket"] is None or isinstance(g["ev_per_ticket"], (int, float))
            assert g["ev_ratio"] is None or isinstance(g["ev_ratio"], (int, float))
            assert g["ev_ratio_adjusted"] is None  # always null in v1 — never rendered blank-as-zero
            assert g["relative_score"] is None or isinstance(g["relative_score"], (int, float))
            assert g["top_prize_odds_now"] is None or isinstance(g["top_prize_odds_now"], (int, float))
            assert isinstance(g["dead_game"], bool)
            assert isinstance(g["flags"], list)
            assert isinstance(g["confidence"], str)
            # M4a fields
            assert g["value_score"] is None or (
                isinstance(g["value_score"], int) and not isinstance(g["value_score"], bool)
            )
            assert g["grade"] is None or g["grade"] in CLOSED_GRADES
            assert isinstance(g["rated"], bool)
            assert isinstance(g["reason"], str) and g["reason"] != ""

    def test_rated_iff_score_and_grade_nonnull(self, data):
        for g in data["games"]:
            assert g["rated"] == (g["value_score"] is not None), g["game_no"]
            assert g["rated"] == (g["grade"] is not None), g["game_no"]

    def test_flags_subset_of_frozen_vocabulary(self, data):
        for g in data["games"]:
            assert set(g["flags"]) <= FLAG_VOCAB, (g["game_no"], g["flags"])

    def test_ev_out_of_range_reason_matches_claim_lag_exactly(self, data):
        """Every rated ev_out_of_range game's reason is the SAME string —
        proves flag-keying and reason-string semantics agree (AC binding).
        Invariant form: holds on ANY data, including days with zero
        ev_out_of_range games (empty set trivially satisfies "at most one
        distinct reason"). The exact-count pin (11 OOR games) lives in
        TestFrozenArtifactRegression against the frozen fixture-derived
        artifact, since live data/latest.json's OOR count moves day to day."""
        reasons = {
            g["reason"]
            for g in data["games"]
            if g["rated"] and "ev_out_of_range" in g["flags"]
        }
        if reasons:
            assert len(reasons) == 1, reasons

    def test_reason_bucket_grouping_is_lossless(self, data):
        by_reason = {}
        for g in data["games"]:
            by_reason.setdefault(g["reason"], []).append(g["game_no"])
        assert sum(len(v) for v in by_reason.values()) == len(data["games"])

    def test_top_eligible_never_carries_ev_out_of_range(self, data):
        """Selection-integrity invariant: the max-score eligible game never
        carries ev_out_of_range — holds on ANY data. The exact "630 tops the
        ranking" pin lives in TestFrozenArtifactRegression against the
        frozen fixture-derived artifact, since live data/latest.json's top
        game moves day to day."""
        eligible = [g for g in data["games"] if _is_eligible(g)]
        if not eligible:
            return
        eligible.sort(key=lambda g: (-g["value_score"], g["game_no"]))
        assert "ev_out_of_range" not in eligible[0]["flags"]
        for g in eligible:
            assert "ev_out_of_range" not in g["flags"]


# ============================================================================
# 1b. Fixture-pinned regression exacts (frozen fixture-derived artifact)
# ============================================================================
#
# data/latest.json is overwritten daily by the M5 bot (live data), so exact
# counts/rankings that were valid on one day's snapshot are not stable
# invariants. These regression checks pin against
# tests/scraper/fixtures/latest_2026-07-11.json (the exact bytes of the
# pre-bot committed data/latest.json at e4a8b7a) so the pipeline is still
# deterministically regression-tested.

@pytest.fixture(scope="module")
def frozen_data():
    return json.loads(FROZEN_ARTIFACT_PATH.read_text(encoding="utf-8"))


class TestFrozenArtifactRegression:
    def test_ev_out_of_range_count_is_11(self, frozen_data):
        oor_games = [
            g for g in frozen_data["games"]
            if g["rated"] and "ev_out_of_range" in g["flags"]
        ]
        assert len(oor_games) == 11

    def test_top_eligible_by_score_then_game_no_is_630(self, frozen_data):
        eligible = [g for g in frozen_data["games"] if _is_eligible(g)]
        eligible.sort(key=lambda g: (-g["value_score"], g["game_no"]))
        assert eligible[0]["game_no"] == 630
        assert eligible[0]["value_score"] == 95


# ============================================================================
# 2. Offline-clean + required-content lint (mockup AND site)
# ============================================================================

def _is_external_url(url):
    if not url:
        return False
    return bool(re.match(r"^(https?:)?//", url.strip(), re.IGNORECASE))


class _ExternalResourceChecker(HTMLParser):
    """Flags externally-loaded resources; <a href> is intentionally exempt
    (mainelottery.com + tel: links are allowed and required by the spec)."""

    CHECKED_SRC_TAGS = {"script", "img", "iframe"}

    def __init__(self):
        super().__init__()
        self.violations = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag in self.CHECKED_SRC_TAGS and _is_external_url(attrs.get("src")):
            self.violations.append((tag, "src", attrs.get("src")))
        if tag == "link" and _is_external_url(attrs.get("href")):
            self.violations.append((tag, "href", attrs.get("href")))
        if attrs.get("srcset") and _is_external_url(attrs.get("srcset").split(",")[0].strip().split(" ")[0]):
            self.violations.append((tag, "srcset", attrs.get("srcset")))


def _assert_offline_clean(text):
    parser = _ExternalResourceChecker()
    parser.feed(text)
    assert not parser.violations, f"external resource(s) found: {parser.violations}"
    assert not re.search(r"@import\s+[\"']?(https?:)?//", text, re.IGNORECASE), "external @import found"
    assert not re.search(r"url\(\s*[\"']?(https?:)?//", text, re.IGNORECASE), "external url(...) found"


def _assert_required_content(text):
    lowered = text.lower()
    for fragment in REQUIRED_SUBSTRINGS:
        assert fragment.lower() in lowered, f"missing required copy fragment: {fragment!r}"


@pytest.mark.parametrize("path", [MOCKUP_PATH, SITE_PATH], ids=["mockup", "site"])
class TestOfflineCleanAndCopyLint:
    def test_offline_clean(self, path):
        _assert_offline_clean(path.read_text(encoding="utf-8"))

    def test_required_copy_present(self, path):
        _assert_required_content(path.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def site_text():
    return SITE_PATH.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def mockup_text():
    return MOCKUP_PATH.read_text(encoding="utf-8")


class TestSiteOnlyAnchors:
    def test_exactly_one_fetch_targeting_data_latest_json(self, site_text):
        assert site_text.count("fetch(") == 1
        assert re.search(r"fetch\(\s*[\"']\.\./data/latest\.json[\"']", site_text)

    def test_isEligible_defined_and_flag_keyed(self, site_text):
        match = re.search(r"function\s+isEligible\s*\([^)]*\)\s*\{", site_text)
        assert match, "no named isEligible function found"
        # Read a bounded window after the signature to inspect the body
        # without a full brace-matching parser.
        window = site_text[match.end():match.end() + 400]
        assert "rated" in window
        assert "ev_out_of_range" in window

    def test_mockup_only_switcher_marker_absent(self, site_text):
        assert "MOCKUP ONLY" not in site_text


class TestMockupOnlyAnchors:
    def test_mockup_only_switcher_marker_present(self, mockup_text):
        assert "MOCKUP ONLY" in mockup_text


# ============================================================================
# 3. docs/pages_deploy.md lint — BULK-owned; skip cleanly while absent
# ============================================================================

PAGES_DEPLOY_REQUIRED_SUBSTRINGS = [
    "root",       # root publishing required (never /docs)
    "/site/",     # published URL shape
    "8208",       # local preview port (distinct from panel dashboard's 8207)
]


@pytest.mark.skipif(
    not PAGES_DEPLOY_PATH.exists(),
    reason="docs/pages_deploy.md not yet landed (BULK task, docs/specs/m4b_site_spec.md file plan)",
)
def test_pages_deploy_lint():
    text = PAGES_DEPLOY_PATH.read_text(encoding="utf-8")
    for fragment in PAGES_DEPLOY_REQUIRED_SUBSTRINGS:
        assert fragment in text, f"missing required pages_deploy.md fragment: {fragment!r}"
