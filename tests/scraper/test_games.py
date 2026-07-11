"""M2 test surface: article/scratchdates parsers, build_games assembler,
coverage gate, CLI, determinism.

See docs/specs/m2_printrun_spec.md for the acceptance criteria (numbered
1-9 in comments below) and maine-scratch-ev-spec.md §2/§7/§8 for context.
"""
import json
import subprocess
import sys
from pathlib import Path

import pytest

# Same harness-packaging carve-out as tests/scraper/test_scrape.py: scraper/
# and data/ are this project's own code, not part of the installable
# harness self-test copy (tests/test_packaging.py's frozen manifest). Degrade
# to a clean skip there; fail loudly everywhere else (this repo).
if not (Path(__file__).resolve().parents[2] / "scraper" / "games.py").exists():
    pytest.skip(
        "scraper/ is this project's own code, not part of the installable harness",
        allow_module_level=True,
    )
from scraper.games import (
    PRICEPAGE_FILENAME_RE,
    BuildError,
    build_games,
    parse_article,
    parse_pricepage_article_ids,
    parse_scratchdates,
)
from scraper.scrape import parse as parse_unclaimed

REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURES_DIR = REPO_ROOT / "tests" / "scraper" / "fixtures"
GAMES_DIR = FIXTURES_DIR / "games"
PRICEPAGES_DIR = FIXTURES_DIR / "pricepages"
UNCLAIMED_PATH = FIXTURES_DIR / "unclaimed_prizes_2026-07-11.html"
SCRATCHDATES_PATH = FIXTURES_DIR / "scratchdates_2026-07-11.html"


def _load_provenance() -> dict:
    return json.loads((GAMES_DIR / "PROVENANCE.json").read_text(encoding="utf-8"))


def _load_all_articles() -> list[dict]:
    provenance = _load_provenance()
    articles = []
    for path in sorted(GAMES_DIR.glob("article_*.html")):
        article_id = path.stem.removeprefix("article_")
        source = provenance.get(article_id, {}).get("source")
        html = path.read_text(encoding="utf-8")
        articles.append(parse_article(html, article_id=article_id, source=source))
    return articles


def _load_unclaimed_snapshot() -> dict:
    return parse_unclaimed(UNCLAIMED_PATH.read_text(encoding="utf-8"))


def _load_scratchdates() -> dict:
    return parse_scratchdates(SCRATCHDATES_PATH.read_text(encoding="utf-8"))


def _load_tile_prices() -> dict:
    """article_id -> price, mirroring the CLI's pricepages loading."""
    tile_prices = {}
    for path in sorted(PRICEPAGES_DIR.glob("scratch*dollar_*.html")):
        price = float(PRICEPAGE_FILENAME_RE.match(path.name).group(1))
        for article_id in parse_pricepage_article_ids(
            path.read_text(encoding="utf-8")
        ):
            tile_prices[article_id] = price
    return tile_prices


def _real_games_doc() -> dict:
    return build_games(
        _load_all_articles(),
        _load_scratchdates(),
        _load_unclaimed_snapshot(),
        as_of="2026-07-11",
        tile_prices=_load_tile_prices(),
    )


# --- 1. every article fixture yields a keyed entry, no exceptions -----------

def test_build_games_covers_every_article_fixture_with_no_exceptions():
    doc = _real_games_doc()
    article_game_nos = {a["game_no"] for a in _load_all_articles()}
    assert None not in article_game_nos, "every article's Game # must parse"
    assert len(article_game_nos) == 58
    for game_no in article_game_nos:
        assert str(game_no) in doc["games"]


# --- 2. coverage gate: >=80%, measured 86.2% (56/65) ------------------------

def test_coverage_gate_matches_measured_86_2_percent():
    doc = _real_games_doc()
    coverage = doc["coverage"]
    assert coverage["active_games"] == 65
    assert coverage["with_print_run"] == 56
    assert coverage["coverage_pct"] == 86.2
    assert coverage["gate_threshold_pct"] == 80.0
    assert coverage["with_print_run"] / coverage["active_games"] >= 0.80


def test_missing_active_games_enumerated():
    doc = _real_games_doc()
    assert doc["coverage"]["missing"] == [
        586, 648, 664, 668, 669, 681, 689, 697, 710,
    ]


def test_non_active_articles_enumerated():
    doc = _real_games_doc()
    assert doc["coverage"]["non_active_articles"] == [714, 721]


def test_build_games_raises_below_coverage_threshold():
    # Synthetic: 10 "active" games, only 1 with an article -> 10% coverage.
    unclaimed_snapshot = {
        "games": [
            {"game_no": i, "name": f"GAME {i}", "price": 1.0}
            for i in range(100, 110)
        ]
    }
    articles = [
        {
            "game_no": 100,
            "name": "GAME 100",
            "print_run": 500000,
            "overall_odds": 3.0,
            "top_prize_value": 100,
            "on_sale": "2024-01-01",
            "source": "live",
            "article_id": "1",
        }
    ]
    with pytest.raises(BuildError):
        build_games(articles, {}, unclaimed_snapshot, as_of="2026-07-11")


# --- 3. label tolerance: three print-run eras -------------------------------

def test_game_737_new_format_print_run():
    doc = _real_games_doc()
    assert doc["games"]["737"]["print_run"] == 960000


def test_game_647_old_format_print_run_odds_on_sale():
    doc = _real_games_doc()
    g = doc["games"]["647"]
    assert g["print_run"] == 5400000
    assert g["overall_odds"] == 3.32
    assert g["on_sale"] == "2024-08-01"


def test_game_638_dash_format_print_run():
    doc = _real_games_doc()
    assert doc["games"]["638"]["print_run"] == 840000


# --- 4. odds parsing never confuses the two ODDS labels ---------------------

def test_overall_odds_not_confused_with_highest_instant_prize_odds():
    html = (GAMES_DIR / "article_12906752.html").read_text(encoding="utf-8")
    parsed = parse_article(html, article_id="12906752", source="live")
    # HIGHEST INSTANT PRIZE ODDS 1:180,000 must never leak into overall_odds.
    assert parsed["overall_odds"] == 3.32
    assert parsed["overall_odds"] != 180000


def test_comma_bearing_overall_odds_parses_correctly():
    html = (
        "<h1>SYNTHETIC</h1><p>Game #999</p>"
        "<p>HIGHEST INSTANT PRIZE ODDS 1:96,000</p>"
        "<p>OVERALL ODDS OF WINNING 1:1,234.56 INCLUDING BREAK-EVEN PRIZES.</p>"
    )
    parsed = parse_article(html, article_id="999", source="live")
    assert parsed["overall_odds"] == 1234.56


# --- 5. scratchdates: every row parses, null fallback, join by game_no -----

def test_scratchdates_parses_all_rows_with_int_game_no_and_iso_dates():
    dates = _load_scratchdates()
    assert len(dates) > 300
    for game_no, row in dates.items():
        assert isinstance(game_no, int)
        for field in ("end_date", "last_cash_date"):
            value = row[field]
            assert value is None or (
                isinstance(value, str) and len(value) == 10 and value[4] == "-"
            )


def test_game_absent_from_scratchdates_gets_null_end_dates():
    doc = _real_games_doc()
    # Game 737 launched 2026-07-02, too new to be in the scratchdates fixture.
    g = doc["games"]["737"]
    assert g["end_date"] is None
    assert g["last_cash_date"] is None


def test_scratchdates_join_is_by_game_no_only_name_spelling_differs():
    dates = _load_scratchdates()
    unclaimed = _load_unclaimed_snapshot()
    unclaimed_name = next(
        g["name"] for g in unclaimed["games"] if g["game_no"] == 704
    )
    assert unclaimed_name == "SILVER 7S"
    assert dates[704]["name"] == "SILVER 7's"

    doc = _real_games_doc()
    g = doc["games"]["704"]
    # The join succeeded (end/last-cash dates came through) despite the name
    # spelling mismatch across sources — game_no is the only join key.
    assert g["end_date"] == "2026-06-30"
    assert g["last_cash_date"] == "2027-06-30"
    # Article <h1> wins the name (matches scratchdates here, not unclaimed).
    assert g["name"] == "SILVER 7's"


# --- 6. active games with no article: graceful null fallback ---------------

@pytest.mark.parametrize(
    "game_no", [586, 648, 664, 668, 669, 681, 689, 697, 710]
)
def test_active_game_with_no_article_has_null_metadata_and_null_source(game_no):
    doc = _real_games_doc()
    g = doc["games"][str(game_no)]
    assert g["source"] is None
    assert g["article_id"] is None
    assert g["print_run"] is None
    assert g["overall_odds"] is None
    assert g["top_prize_value"] is None
    assert g["on_sale"] is None
    # But independently-sourced fields (unclaimed page) are NOT thrown away.
    assert g["name"] is not None
    assert g["price"] is not None


# --- 7. determinism ----------------------------------------------------------

def test_build_games_is_deterministic():
    doc1 = _real_games_doc()
    doc2 = _real_games_doc()
    assert json.dumps(doc1, sort_keys=True) == json.dumps(doc2, sort_keys=True)


def test_cli_output_is_byte_identical_across_two_runs(tmp_path):
    out1 = tmp_path / "games1.json"
    out2 = tmp_path / "games2.json"
    for out in (out1, out2):
        result = subprocess.run(
            [
                sys.executable, "-m", "scraper.games",
                "--fixtures-dir", str(FIXTURES_DIR),
                "--as-of", "2026-07-11",
                "--out", str(out),
            ],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, result.stderr
    assert out1.read_bytes() == out2.read_bytes()


# --- 8. no network -----------------------------------------------------------
# tests/scraper/conftest.py's autouse `_block_network` fixture patches
# socket.socket.connect and urllib.request.urlopen for every test collected
# under tests/scraper/, this module included — no separate assertion needed.


# --- 9. full gate: non-active articles included, CLI green ------------------

def test_non_active_articles_714_and_721_are_included_with_tile_prices():
    # 714 and 721 aren't on the unclaimed page (not yet active) so the
    # fallback can't price them — but both ARE tiled on price-point pages
    # (714: sole tile on scratch25dollar, 721: scratch10dollar), and the
    # tile page is the primary price source per the spec.
    doc = _real_games_doc()
    for game_no, expected_price, expected_print_run in (
        (714, 25.0, 1600000),
        (721, 10.0, 1560000),
    ):
        g = doc["games"][str(game_no)]
        assert g["price"] == expected_price
        assert g["print_run"] == expected_print_run
        assert g["source"] == "live"


# --- price sources: tile-primary, unclaimed-fallback, agreement check --------

def test_tile_price_and_unclaimed_price_agree_for_all_games_in_both_sources():
    tile_prices = _load_tile_prices()
    articles = _load_all_articles()
    unclaimed = _load_unclaimed_snapshot()
    unclaimed_price = {g["game_no"]: g["price"] for g in unclaimed["games"]}

    article_id_to_game_no = {a["article_id"]: a["game_no"] for a in articles}
    checked = 0
    for article_id, tile_price in tile_prices.items():
        game_no = article_id_to_game_no.get(article_id)
        if game_no in unclaimed_price:
            assert tile_price == unclaimed_price[game_no], (
                f"game {game_no}: tile price {tile_price} != unclaimed "
                f"price {unclaimed_price[game_no]}"
            )
            checked += 1
    # 35 tiled articles minus the 2 not-yet-active games (714, 721).
    assert checked == 33

    # And the build recorded zero conflicts.
    doc = _real_games_doc()
    assert doc["coverage"]["price_conflicts"] == []


def test_tile_price_conflict_prefers_tile_and_is_recorded():
    unclaimed_snapshot = {
        "games": [
            {"game_no": i, "name": f"GAME {i}", "price": 1.0}
            for i in range(100, 105)
        ]
    }
    articles = [
        {
            "game_no": no,
            "name": f"GAME {no}",
            "print_run": 500000,
            "overall_odds": 3.0,
            "top_prize_value": 100,
            "on_sale": "2024-01-01",
            "source": "live",
            "article_id": str(no),
        }
        for no in range(100, 105)
    ]
    # Article "100" is tiled on a $2 page but the unclaimed page says $1.
    doc = build_games(
        articles,
        {},
        unclaimed_snapshot,
        as_of="2026-07-11",
        tile_prices={"100": 2.0},
    )
    assert doc["games"]["100"]["price"] == 2.0  # tile wins
    assert doc["coverage"]["price_conflicts"] == [
        {"game_no": 100, "tile_price": 2.0, "unclaimed_price": 1.0}
    ]
    # Untiled article falls back to the unclaimed price.
    assert doc["games"]["101"]["price"] == 1.0


def test_pricepage_parser_extracts_tile_article_ids():
    html = (PRICEPAGES_DIR / "scratch25dollar_2026-07-11.html").read_text(
        encoding="utf-8"
    )
    assert parse_pricepage_article_ids(html) == {"13342573"}


# --- CLI ---------------------------------------------------------------------

def test_cli_writes_games_json_from_fixtures(tmp_path):
    out_path = tmp_path / "games.json"
    result = subprocess.run(
        [
            sys.executable, "-m", "scraper.games",
            "--fixtures-dir", str(FIXTURES_DIR),
            "--as-of", "2026-07-11",
            "--out", str(out_path),
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    data = json.loads(out_path.read_text(encoding="utf-8"))
    assert data["as_of"] == "2026-07-11"
    assert data["coverage"]["coverage_pct"] == 86.2
    assert len(data["games"]) == 67


def test_cli_stdout_when_no_out_given():
    result = subprocess.run(
        [
            sys.executable, "-m", "scraper.games",
            "--fixtures-dir", str(FIXTURES_DIR),
            "--as-of", "2026-07-11",
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    data = json.loads(result.stdout)
    assert data["as_of"] == "2026-07-11"


def test_cli_missing_fixtures_is_nonzero_exit_and_writes_nothing(tmp_path):
    empty_dir = tmp_path / "empty_fixtures"
    empty_dir.mkdir()
    (empty_dir / "games").mkdir()
    out_path = tmp_path / "games.json"
    result = subprocess.run(
        [
            sys.executable, "-m", "scraper.games",
            "--fixtures-dir", str(empty_dir),
            "--as-of", "2026-07-11",
            "--out", str(out_path),
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0
    assert not out_path.exists()
