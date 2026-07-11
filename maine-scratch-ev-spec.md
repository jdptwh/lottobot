# Maine Scratch-Off EV Ranker — Project Spec

**Version:** 0.1 (draft)
**Owner:** Joe
**Status:** Pre-build
**One-liner:** A daily-updated, shareable web tool that ranks every active Maine Lottery instant game by expected value per dollar, using the state's published unclaimed-prize and percent-unsold data.

---

## 1. Purpose & Framing

The Maine Lottery publishes enough data (daily) to compute the *current* expected value of every active scratch game. This tool automates that math and publishes a ranked list at a public URL.

**What it is:** A "which game is least bad today" ranker, with occasional detection of end-of-life EV anomalies.

**What it is not:** A win predictor. Every unsold ticket within a game remains uniformly random. The tool must state this plainly in the UI (see §8, Responsible Use).

---

## 2. Data Sources (all public, all mainelottery.com)

| Source | URL | Cadence | Fields |
|---|---|---|---|
| Unclaimed Prizes | `/players_info/unclaimed_prizes.html` | Daily (~5:00 AM ET snapshot) | Price point, game no., game name, **percent unsold**, **total unclaimed $**, top prize levels + counts remaining |
| Game detail pages | `/instant/scratch{1,2,3,5,10,20,25,30}dollar.html` + per-game pages | On new game launch | Full prize structure, overall odds, (derive total print run) |
| Game End Dates | `/instant/scratchdates.html` | Weekly | Game end dates (feature: "ending soon" flag) |

**Key derivation:** `print_run ≈ total_prizes_at_launch × overall_odds`. Scraped once per game, cached in `games.json`. If a game page lacks enough info, mark `print_run: null` and fall back to unclaimed-$-per-percent-unsold as a relative score.

**Fragility note:** These are hand-maintained state HTML pages. Parser must be defensive (see §6, Verification).

---

## 3. Core Math

### v1 — Naive EV (ship first)

```
remaining_tickets = (percent_unsold / 100) × print_run
ev_per_ticket     = total_unclaimed_$ / remaining_tickets
ev_ratio          = ev_per_ticket / ticket_price        # primary sort key
```

Also computed per game:
- `top_prize_odds_now = remaining_tickets / top_prizes_remaining` vs. launch odds (the "odds shift" factor)
- `dead_game = true` if all top-tier prizes claimed → flagged prominently

### v2 — Claim-lag correction (after ≥3–4 weeks of daily snapshots)

"Unclaimed" ≠ "unsold." A prize may be on a sold ticket not yet redeemed. Naive EV therefore **overstates** value, worst on nearly-sold-out games.

- Accumulate daily snapshot deltas (git history is the time series — free).
- For each prize tier, estimate claim lag: when `percent_unsold` drops by X, how much unclaimed value disappears and with what delay?
- Discount factor per tier: `p_in_unsold_stock ≈ f(percent_unsold, tier_claim_lag)`. Simple starting model: assume prizes are uniformly distributed through the print run; probability a given unclaimed prize is in unsold stock ≈ `percent_unsold / (percent_unsold + lag_window_pct)`. Calibrate `lag_window_pct` per tier from deltas.
- Publish both numbers: naive EV and lag-adjusted EV. Confidence widens as `percent_unsold → 0`.

### v3 — Optional extras (backlog)

- Volatility metric per game (prize concentration / Gini of prize table) — "steady grinder" vs. "lottery within a lottery."
- Ending-soon urgency score (end date × EV).
- Per-price-point best pick ("best $5 game today").

---

## 4. Architecture

**Pattern:** GitHub repo + scheduled GitHub Action + static site on GitHub Pages. No servers, no keys, free, shareable URL.

```
repo/
├── scraper/
│   ├── scrape.py            # fetch + parse unclaimed_prizes.html
│   ├── games.py             # one-time-ish print-run scraper (detail pages)
│   └── compute.py           # EV math (v1, later v2)
├── data/
│   ├── games.json           # static per-game metadata (print runs, launch odds)
│   ├── latest.json          # today's computed rankings (site reads this)
│   └── history/YYYY-MM-DD.json   # daily raw snapshots (fuels v2)
├── site/
│   └── index.html           # single-file static UI, reads ../data/latest.json
├── .github/workflows/daily.yml   # cron ~10:30 UTC (after ME 5 AM refresh), scrape → compute → commit
└── SPEC.md                  # this file
```

**Stack:** Python 3.11 + `requests` + `beautifulsoup4` for scraping; vanilla HTML/JS (or single-file React via CDN) for the site. No build step required.

### Data schemas

`latest.json` (site contract — freeze this early):

```json
{
  "as_of": "2026-07-10",
  "source_timestamp": "July 10, 2026 5:00 AM",
  "games": [
    {
      "game_no": 706,
      "name": "DOUBLE YOUR DOLLARS",
      "price": 5.00,
      "percent_unsold": 0.3,
      "total_unclaimed": 468555,
      "top_prizes": [{"level": 100000, "remaining": 1}, {"level": 10000, "remaining": 1}],
      "print_run": 1200000,
      "remaining_tickets": 3600,
      "ev_per_ticket": null,
      "ev_ratio": null,
      "ev_ratio_adjusted": null,
      "dead_game": false,
      "flags": ["low_inventory", "anomaly_candidate"],
      "confidence": "low"
    }
  ]
}
```

Rules: never delete fields from this schema, only add. Nulls allowed where data is missing. `confidence` ∈ {high, medium, low} driven by print-run availability and percent_unsold floor.

---

## 5. UI (single page)

- Header: "as of {date}" + one-sentence honest framing.
- Sortable table: game, price, EV ratio (naive + adjusted when available), % unsold, top prizes remaining, flags.
- Filters: price point tabs ($1–$30), hide dead games toggle.
- Row expansion: full prize tiers remaining, odds shift vs. launch.
- Anomaly banner: any game where `ev_ratio > 0.85` or `flags` includes `anomaly_candidate`, with the claim-lag caveat inline.
- Mobile-first (this gets checked from a phone at the gas station).
- Footer: methodology link, data source link, responsible-play line + 1-800-GAMBLER.

---

## 6. Verification Gates (agent-system compatible)

1. **Parser gate:** scrape must yield ≥40 games, every row has price/game_no/percent_unsold/total_unclaimed, sum of unclaimed > $50M sanity floor. Fail → do not commit `latest.json`, open an issue via Action, site keeps serving yesterday's data (staleness banner if `as_of` > 48h old).
2. **Math gate:** unit tests on `compute.py` with a frozen fixture of the 2026-07-10 page. EV ratios must land in (0, 1.5); anything outside flags for review rather than publishing silently.
3. **Schema gate:** `latest.json` validated against JSON Schema before commit.
4. **Diff gate:** if >30% of games changed EV ratio by >0.2 in one day, treat as probable parse breakage, hold the commit.

---

## 7. Milestones

| # | Deliverable | Definition of done |
|---|---|---|
| M1 | Scraper + fixture tests | Parses live page and frozen fixture identically; passes gates 1 & 3 |
| M2 | Print-run scrape (`games.json`) | ≥80% of active games have print_run; rest fall back gracefully |
| M3 | EV v1 + `latest.json` | Rankings match hand-calculated spot checks on 3 games |
| M4 | Static site | Renders latest.json, sortable, mobile-usable, deployed on Pages |
| M5 | Daily Action | 7 consecutive green runs, history/ accumulating |
| M6 | Claim-lag model v2 | After ~30 snapshots; adjusted EV published alongside naive |

---

## 8. Responsible Use & Legal Notes

- Prominent, non-buried statement: this ranks games by expected value; it cannot predict wins; all scratch games are negative-EV in normal conditions; 1-800-GAMBLER link.
- Data is republished state public data with attribution and a discrepancy disclaimer mirroring the Lottery's own ("Official Outstanding Prize List prevails").
- Polite scraping: 1 request/day to the unclaimed page, identify with a UA string, respect robots.txt.
- No accounts, no tracking, no monetization in v1. (If this ever grows toward the ScratchSmarter-style subscription space, that's a separate business decision with its own diligence.)

## 9. Open Questions

- Can print run be derived reliably for all games from Maine's detail pages, or do some require the official game rules PDFs?
- Does the 5 AM snapshot ever skip days (holidays)? History will reveal; staleness banner covers it.
- Fast Play games have their own unclaimed page — in scope for v2? (Different mechanics, same math.)
