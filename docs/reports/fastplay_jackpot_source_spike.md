# Fast Play progressive-jackpot dollar-value discovery spike (CP3)

**Governs:** docs/specs/fastplay_extension_spec.md D2 (documentation-only,
non-blocking, budget 1 attempt).
**Author of record:** implementer (Sonnet 5) · 2026-07-27.
**Status:** COMPLETE — "not found" outcome (D2: an acceptable result, not a
failure). Does not gate CP2 or CP4.

## Question

Is a live progressive-jackpot dollar value published anywhere scrapable on
`mainelottery.com` for Maine's Fast Play progressive games (e.g., $2
BLACKJACK PROGRESSIVE, game 25), so a follow-on task could compute a real
`ev_ratio` for progressive games instead of the permanent `progressive_jackpot`
non-rateable guard shipped in v1?

## Method

One research pass (per the 1-attempt budget), starting from the frozen
CP1 fixture and following the site's own link graph rooted at the Fast Play
section. All fetches were polite (identifying UA, single GET per URL, no
retries) and are OUTSIDE the daily production politeness surface — this
spike does not add a second daily fetch to the pipeline (D2).

Pages checked:

1. `https://www.mainelottery.com/fastplay/unclaimed_fastplay.html` (the CP1
   fixture, already in hand) — the disclosure table's "Top Prize Level(s)"
   cell for every progressive game reads literally `JACKPOT`, no dollar
   figure. Confirmed already at CP1 parse time (D9).
2. `https://www.mainelottery.com/fastplay/2dollar.html` (the $2 price-point
   category page, linked from the disclosure page's own top nav) — lists
   each $2 Fast Play game as a tile linking to a `maine.gov` "whatsnew"
   CMS article/flyer page. No dollar figures of any kind on this page; no
   `jackpot`/`progressive` text beyond the game names themselves.
3. `https://www.maine.gov/tools/whatsnew/index.php?topic=Lottery_FastPlay&id=7146346&v=article`
   (the BLACKJACK PROGRESSIVE game's own flyer page, game #025 — the same
   `id=` article-page pattern `data/games.json`'s `article_id` field uses
   for scratch games). This is the most specific, most likely candidate
   page and it does NOT publish a jackpot dollar value either: its
   "Maximum Award" field reads literally **"PROGRESSIVE JACKPOT"** as text,
   not a number. The page otherwise reads as static, template-generated
   promotional copy dated to the game's launch (odds, on-sale date, total
   tickets printed) — not a live-refreshed ticker.
4. `https://www.mainelottery.com/index.html` (site homepage, checked for a
   jackpot-ticker banner widget, as some lotteries run for progressive
   games) — no `jackpot`/`progressive` text anywhere in the fetched HTML;
   the page's ad-banner div (`#bannerad`) is empty in the static response,
   consistent with client-side/JS-injected content this scraper does not
   execute, but no textual jackpot ticker was found either way.

## Finding

**Not found.** No page reachable from the Fast Play section of
`mainelottery.com` (or its linked `maine.gov` article pages) publishes a
live progressive-jackpot current dollar value as scrapable text. Every
surface that names the prize instead uses the literal word "JACKPOT" (the
unclaimed table) or "PROGRESSIVE JACKPOT" (the game's own flyer page) with
no associated number.

This corroborates docs/reports/edge_research_2026-07-26.md's finding
("the page does NOT show the progressive jackpot dollar amount") and
confirms it extends beyond the disclosure page itself to the adjacent
category and per-game pages checked here.

### Incidental finding for a DIFFERENT follow-on task (not this spike's
### question, recorded for scoping value only)

The per-game flyer page (item 3 above) DOES publish `Total Tickets:
1,200,000` (i.e., a print run) and overall/highest-prize odds text, in the
same free-text style `data/games.json`'s scratch metadata was apparently
sourced from (`article_id`). This is a plausible scrapable source for the
D1 follow-on task ("Fast Play print-run / odds discovery", out of scope
here) — noted for that task's scoping, not acted on in any way here. The
per-game flyer page is dated to the game's launch, not the current day, so
it is unlikely to help with the jackpot-value question even if machine-
parsed, but it would need its own politeness/format spec (28+ games x one
fetch each, a materially different request-volume profile than today's
single unclaimed-page pull).

## D2 recommendation for the follow-on task

Recommend the follow-on task NOT chase a jackpot-value scrape via this
site's own pages — none was found across the reachable link graph. If a
progressive-EV feature is still wanted later, options to scope (not
committed to, not started):

- Check whether Maine Lottery's press-release / news feed
  (`/about/news_events.html`) ever announces jackpot milestones with dollar
  figures (would be sporadic, not daily-refreshable — a poor fit for this
  pipeline's daily-cadence model).
- Ask the state directly (the same "Lottery data request" already noted as
  declined-for-now in CLAUDE.md's backlog) whether a jackpot-value feed
  exists off-page.
- Absent either, ship progressive games permanently non-rateable (v1's
  posture) indefinitely — an honest, defensible steady state per D2's own
  framing ("not found — ship non-rateable" is an acceptable outcome, not a
  failure).

## D10.1 column-semantics finding (recorded per AC-9)

At CP1 fixture review, the Fast Play page's dollar column is headed
**"Total Unsold"** (not "Total Unclaimed" as on the scratch page) — the
exact ambiguity docs/reports/edge_research_2026-07-26.md flagged ("total
unsold dollars") and D10 condition 1 exists to catch.

Finding: the SAME scratch disclosure page already mixes this vocabulary
internally for what is understood to be one underlying quantity — its own
intro sentence reads "the list of top **unclaimed** prizes", its percent
column is headed "Percent **Unsold**", and its prize-count column is headed
"Top Prize(s) **Unclaimed**", all on the one page whose `total_unclaimed`
semantics this project already relies on. Given the publisher already
treats "unsold" and "unclaimed" as loose synonyms on that page, the Fast
Play page's parallel "Total **Unsold**" / "Top Prize(s) **Unsold**" headers
read as the same house copywriting style, not evidence of a genuinely
different measure.

**Judgment: D10 condition 1 is CLEARED (not triggered).** The field keeps
the name `total_unclaimed` and the scratch upper-bound honesty framing
applies verbatim, per D10's stated default ("absent either condition"). This
judgment call, its full reasoning, and the D10 condition 2 (table structure
— also cleared, identical 7-cell layout and continuation-row pattern) are
additionally recorded in `scraper/fastplay.py`'s module docstring for any
future reviewer who wants to re-examine it.
