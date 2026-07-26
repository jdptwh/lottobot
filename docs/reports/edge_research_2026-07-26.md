# Edge Research: ME/NH/MA/VT (deep-research run 2026-07-26)

## Summary

Across ME/NH/MA/VT, the only statistically defensible player edges are structural, not behavioral: (1) end-of-lifecycle instant-game EV ranking from official remaining-prize disclosures — Maine (daily, percent-unsold + unclaimed dollars, already operationalized by this project, and extendable as-is to Maine's separately disclosed Fast Play family including progressive jackpots), Massachusetts (hourly-cadence, full per-tier Start/Claimed/Remaining counts — the richest surface in the region), and New Hampshire (daily top-tier counts plus a public JSON API exposing odds and print-run) — though NH and MA omit a tickets-sold denominator, reproducing the same claim-lag identifiability gap already proven in the Maine panel, so all such rankings are upper bounds; and (2) draw-game jackpot screening via the peer-reviewed Abrams–Garibaldi criterion (sales-to-after-tax-jackpot ratio N/J < 1/5 above a computable threshold), which provably yields occasional positive-expected-return drawings (documented +30% case) but is not practically investable at retail scale because single-ticket variance (~4×10^11) makes optimal portfolio allocation negligible. Vermont's second-chance drawings publish no entry volumes, so per-entry EV is incomputable from official sources. The classic myths are decisively debunked by primary literature: "lucky stores" have zero predictive effect (Guryan & Kearney, AER 2008) and "due"/"hot" numbers are documented fallacies in real play data across three countries — with the sole residual nuance that crowd bias creates a tiny contrarian prize-splitting edge only in pari-mutuel formats. Recommended pipeline roadmap, in order of practicality: extend the existing Maine scraper to Fast Play (same publisher, same schema, includes progressive-jackpot games — the closest ME analog to must-hit-by mechanics), add an MA per-tier prize-burn tracker, add an NH API-based tracker, and build an N/J draw-game screener contingent on locating per-drawing sales data.

## Findings

### Draw-game jackpot screening is a proven, computable edge — but not investable at retail scale

**Claim:** Draw-game jackpot screening is a proven, computable edge — but not investable at retail scale. Peer-reviewed theory (Abrams & Garibaldi, American Mathematical Monthly 2010, reposted arXiv:2507.01993) proves drawings with ticket sales below one-fifth of the after-tax lump-sum jackpot (N/J < 1/5) have positive expected rate of return once the jackpot exceeds an easily computed threshold, while N/J above ~1 is always negative-EV; the Lotto Texas drawing of 2007-04-07 (J=$33.8M after-tax, 4.2M tickets, N/J=0.13) hit +30% expected return. However, the same paper proves the variance of a single ticket (~4×10^11) makes the optimal portfolio allocation to lottery tickets negligible — the edge is real for a screening/analytics tool but only exploitable at syndicate scale (~145k+ tickets), as the historical MA Cash WinFall/Selbee case also illustrates.

**Confidence:** high

**Sources:**
- [https://arxiv.org/abs/2507.01993](https://arxiv.org/abs/2507.01993)

**Evidence:** All three constituent claims verified verbatim against the full PDF of the peer-reviewed paper (Ford Award 2011): the N/J < 1/5 screening criterion with jackpot threshold (Theorem 6.5), the documented +30% Lotto Texas case (Tables 3a/4), and the variance/portfolio Negative Theorem. Key implementation qualifications from verification: J is the AFTER-TAX LUMP-SUM value (~45% of headline annuity), and the theorem assumes non-jackpot prizes under ~20% of revenue.

**Vote:** 3-0, 3-0, 2-1 (merged claims 0, 1, 2)

### Maine publishes the strongest scratch-EV input surface of the four states

**Claim:** Maine publishes the strongest scratch-EV input surface of the four states: a daily-updated (5:00 AM ET) table covering every active instant game with Price Point, Game No., Game Name, Percent Unsold, Total Unclaimed dollars, Top Prize Level(s), and Top Prize(s) Unclaimed count — the exact inputs for the project's existing end-of-lifecycle EV-per-dollar ranking. Because Total Unclaimed includes sold-but-unredeemed prizes and per-tier claim lag is unidentifiable (per this project's M6b result), rankings from this surface are upper bounds.

**Confidence:** high

**Sources:**
- [https://www.mainelottery.com/players_info/unclaimed_prizes.html](https://www.mainelottery.com/players_info/unclaimed_prizes.html)

**Evidence:** Headers verified against the archived fixture (C:\lottobot\tests\scraper\fixtures\unclaimed_prizes_2026-07-11.html) and the live page (65 games, as_of 2026-07-25); daily cadence corroborated by 13 consecutive daily scrapes in C:\lottobot\data\history\ showing genuine data changes each day including weekends. Note: a separate claim that sub-top-tier counts are never published was REFUTED (1-2), so tier granularity on this page is better than the minimal reading — but still not full per-tier.

**Vote:** 3-0, 3-0 (merged claims 3, 4)

### Maine Fast Play progressive-jackpot extension: highest-practicality roadmap item

**Claim:** Highest-practicality roadmap item: Maine also publishes an identical-format daily disclosure for Fast Play (terminal-generated) games at the same publisher and cadence — per-game percent unsold, total unsold dollars, top prize level, and top-prizes-unsold count for ~28-30 active games — so the existing scratch-EV methodology extends almost as a drop-in. The disclosure includes progressive-jackpot games with live jackpot-remaining counts (e.g., $2 BLACKJACK PROGRESSIVE, game 25: 22.0% unsold, 3 JACKPOT prizes unsold), the closest Maine analog to must-hit-by mechanics; a full EV calc additionally needs the current progressive jackpot dollar value from a separate Maine Lottery source.

**Confidence:** high

**Sources:**
- [https://www.mainelottery.com/fastplay/unclaimed_fastplay.html](https://www.mainelottery.com/fastplay/unclaimed_fastplay.html)

**Evidence:** Direct fetch 2026-07-25 confirmed the table structure, the as-of line ('July 25, 2026 5:00 AM'), and the BLACKJACK PROGRESSIVE row verbatim. Corrections from verification: game count is ~28-30 (not ~40 as originally claimed), and the page does NOT show the progressive jackpot dollar amount — necessary-but-not-sufficient for progressive EV.

**Vote:** 2-1, 3-0 (merged claims 11, 12)

### Massachusetts offers the richest prize-depletion data in the region

**Claim:** Massachusetts offers the richest prize-depletion data in the region: a Prizes Remaining tool with stated hourly update cadence (140 top-prize summary rows), and per-game detail pages disclosing EVERY prize tier with exact Start/Claimed/Remaining counts (verified 12-tier example, game #549 '10X'). This supports near-real-time tier-burn tracking — precise measurement rather than inference. However, MA publishes no percent-sold/unsold or total-tickets-printed figure (regex scan of the full 221KB API payload found zero such fields), so an EV-per-remaining-dollar denominator must be external or estimated — the same identifiability gap as Maine's claim-lag problem, from the opposite direction (MA has tier counts but no denominator; ME has the denominator but coarse tier counts).

**Confidence:** high

**Sources:**
- [https://www.masslottery.com/prizes_remaining](https://www.masslottery.com/prizes_remaining)
- [https://www.masslottery.com/tools/prizes-remaining](https://www.masslottery.com/tools/prizes-remaining)
- [https://www.masslottery.com/api/v1/instant-game-prizes](https://www.masslottery.com/api/v1/instant-game-prizes)

**Evidence:** Live browser verification 2026-07-25: hourly-cadence statement verbatim, 140 rows, per-tier detail confirmed on game pages, official JSON endpoints identified (api/v1/instant-game-prizes and /special). 'Hourly' is best-effort wording ('Every effort is made'), not an SLA — empirically measure before relying on it. A claim that the summary page exposes low/mid-tier counts for Blowout-style games was REFUTED (1-2); low-tier data lives on detail pages, not the summary.

**Vote:** 3-0, 2-1, 3-0 (merged claims 7, 8, 9)

### New Hampshire publishes a Prizes Remaining page covering all 56 active scratch games

**Claim:** New Hampshire publishes a Prizes Remaining page for all 56 active scratch games (ticket price, game number, remaining-vs-original counts for top three tiers plus expandable Additional Prizes; timestamp consistent with daily-or-better updates), and its public JSON API (nhlottery.com/api/v1/game/all?platform=web) exposes per-game overall odds, apparent total print run ('ticketsOrdered'), start date, and price. NH does NOT disclose percent-sold/unsold anywhere, so remaining-prize EV bounds are computable but the tickets-remaining denominator is unpublished — again reproducing the claim-lag identifiability gap. Scraper note: the HTML page is JS-rendered (static fetch returns 0 results); the API is the viable target, but the specific claim that the page offers a CSV export driven by that API was refuted, so the scrape path needs fresh engineering verification.

**Confidence:** high

**Sources:**
- [https://nhlottery.com/Games/Scratch-Tickets/Unclaimed-Top-Prizes](https://nhlottery.com/Games/Scratch-Tickets/Unclaimed-Top-Prizes)
- [https://nhlottery.com/api/v1/game/all?platform=web](https://nhlottery.com/api/v1/game/all?platform=web)

**Evidence:** Live browser render 2026-07-25 confirmed 56 results, per-game structure, and 'Results last updated: 07/25/2026 11:06 PM'; live API fetch confirmed odds/ticketsOrdered/price fields verbatim and the absence of any percent-sold or prizes-remaining field in the API. Caveats: 'ticketsOrdered' = print run is a reasonable but undocumented interpretation; daily cadence inferred from one timestamp snapshot. The machine-readable-pipeline claim was REFUTED 0-3 in its specific form.

**Vote:** 3-0, 3-0 (merged claims 5, 6)

### Second-chance drawing EV is incomputable in Vermont from official sources

**Claim:** Second-chance drawing EV is incomputable in Vermont from official sources: the VT 2nd Chance program states odds depend on total eligible entries but never publishes entry volumes — drawings disclose only winner name/town/prize counts. Without an entry denominator, the expected value of entering non-winning tickets cannot be estimated, and no third-party source fills the gap. (A related claim of a hard 10-entries-per-day cap was refuted 0-3.) This makes second-chance a low-practicality surface absent a public-records request.

**Confidence:** high

**Sources:**
- [https://vtlottery.2ndchanceplay.com/draw_standards.html](https://vtlottery.2ndchanceplay.com/draw_standards.html)

**Evidence:** Primary source quote verified verbatim; live results site (current through July 2026) confirmed drawings publish winner/prize counts but never entry totals or numeric odds; web searches found no official or third-party entry-volume disclosure.

**Vote:** 3-0 (claim 10)

### ANTI-EDGE (debunked): 'Lucky stores'

**Claim:** ANTI-EDGE (debunked): 'Lucky stores.' Selling a winning ticket confers zero probabilistic advantage — winner location is random conditional on sales volume, and store-level sales history does not predict future winning-ticket sales (the formal falsifiable test). Yet retailers that sell a winning jackpot ticket see a 12-38% relative jump in game-specific sales the following week, increasing with jackpot size and persisting up to 40 weeks — documenting that the myth measurably drives consumer behavior despite being false. Any winner-location analytics (including this project's winners dataset) should be framed as descriptive/behavioral, never predictive.

**Confidence:** high

**Sources:**
- [https://www.nber.org/system/files/working_papers/w11287/w11287.pdf](https://www.nber.org/system/files/working_papers/w11287/w11287.pdf)

**Evidence:** All three constituent claims verified verbatim against Guryan & Kearney (NBER w11287; published peer-reviewed as 'Gambling at Lucky Stores,' American Economic Review 98(1) 2008, replication data on openICPSR). Follow-on literature through 2026 treats the null probabilistic effect as settled and studies only the behavioral bias. Minor scope note: the empirical test is on draw-game data; for scratch tickets pack-level structure is not strictly i.i.d., but past winner sales still carry no forward-predictive signal.

**Vote:** 3-0, 3-0, 3-0 (merged claims 13, 14, 15)

### ANTI-EDGE (debunked): 'Due' / 'hot' numbers and games

**Claim:** ANTI-EDGE (debunked): 'Due' / 'hot' numbers and games. The gambler's fallacy is one of the most replicated findings in lottery behavior: bets on a number drop sharply immediately after it is drawn (Maryland daily numbers, Clotfelter & Cook 1993, recovering over ~3 months), Danish lotto players place 1.6% fewer bets on last week's numbers (2% among number-changers) while simultaneously betting ~1% more per additional consecutive week a 'hot' number repeats (Suetens et al., JEEA 2016), and Israeli data (115M entries) confirms avoidance of recent winners decaying over 4-5 draws (Polin & Benisaac, JDM 2023). Draws are independent; these beliefs have zero effect on probabilities. The one residual real edge: in PARI-MUTUEL formats only, the crowd's avoidance of recent numbers yields a small contrarian prize-splitting advantage for betting them (Terrell 1994) — format-dependent, tiny, and inapplicable to fixed-payout games.

**Confidence:** high

**Sources:**
- [https://dl.acm.org/doi/abs/10.5555/2772615.2772623](https://dl.acm.org/doi/abs/10.5555/2772615.2772623)
- [https://www.researchgate.net/publication/281575866_Predicting_lotto_numbers_A_natural_experiment_on_the_gambler's_fallacy_and_the_hot-hand_fallacy](https://www.researchgate.net/publication/281575866_Predicting_lotto_numbers_A_natural_experiment_on_the_gambler's_fallacy_and_the_hot-hand_fallacy)
- [https://www.cambridge.org/core/journals/judgment-and-decision-making/article/longitudinal-analysis-of-the-hot-hand-and-gamblers-fallacy-biases/FB70687B0F8B2C92B83DB439BA7DB500](https://www.cambridge.org/core/journals/judgment-and-decision-making/article/longitudinal-analysis-of-the-hot-hand-and-gamblers-fallacy-biases/FB70687B0F8B2C92B83DB439BA7DB500)

**Evidence:** Five unanimous claims merged, each verified verbatim against peer-reviewed primary sources spanning three countries and 30 years (Management Science 1993 / NBER w3769; JEEA 2016 author-hosted full text; Cambridge JDM 2023), with independent replications (Terrell 1994 NJ pari-mutuel; 2024 J. Risk & Uncertainty). Citation-hygiene note: the ACM 10.5555 URL is a placeholder index — cite INFORMS DOI 10.1287/mnsc.39.12.1521 or NBER w3769 for Clotfelter & Cook.

**Vote:** 3-0 x5 (merged claims 16, 17, 18, 19, 20)

### Roadmap shortlist for the GitHub-Actions + static-site pipeline

**Claim:** Roadmap shortlist for the GitHub-Actions + static-site pipeline, ranked by practicality x value: (1) Maine Fast Play EV extension — same publisher, same table schema, same daily 5AM cadence as the existing scraper; adds progressive-jackpot tracking (needs a second small scrape for jackpot values). (2) MA per-tier prize-burn tracker — official JSON endpoints, full tier granularity, hourly-ish cadence; publish depletion curves and remaining-prize EV upper bounds (denominator caveat displayed, consistent with the site's existing honesty-pass framing). (3) NH tracker via the game/all API + prizes-remaining data — daily cadence, includes odds and print-run for tighter bounds than ME/MA allow. (4) Regional draw-game N/J screener — provably sound math, trivially cheap to compute, but contingent on the open question of per-drawing sales data availability. Not recommended: VT second-chance EV (no entry denominator), winner-location prediction (debunked), any due/hot-number feature except as an explicitly labeled myth-debunking exhibit.

**Confidence:** medium

**Sources:**
- [https://www.mainelottery.com/fastplay/unclaimed_fastplay.html](https://www.mainelottery.com/fastplay/unclaimed_fastplay.html)
- [https://www.masslottery.com/api/v1/instant-game-prizes](https://www.masslottery.com/api/v1/instant-game-prizes)
- [https://nhlottery.com/api/v1/game/all?platform=web](https://nhlottery.com/api/v1/game/all?platform=web)
- [https://arxiv.org/abs/2507.01993](https://arxiv.org/abs/2507.01993)

**Evidence:** Synthesis judgment built on the verified findings above rather than a single verified claim; each underlying data surface was individually confirmed live on 2026-07-25, but scrape-path engineering details (NH JS rendering / refuted CSV claim, MA actual refresh cadence, ME Fast Play jackpot-value source) remain unvalidated in code.

**Vote:** synthesis (derived from all confirmed claims)

## Refuted Claims

- **Claim:** Prize-count granularity is limited: unclaimed counts are disclosed only for top prize tier(s) (with sub-top tier counts appearing for only a few high-price games), plus one aggregate Total Unclaimed dollar figure per game — full tier-by-tier remaining-prize breakdowns are NOT published, which caps EV precision and explains why per-tier claim-lag inference is underdetermined from this source alone.
  - **Vote:** 1-2
  - **Source:** [https://www.mainelottery.com/players_info/unclaimed_prizes.html](https://www.mainelottery.com/players_info/unclaimed_prizes.html)

- **Claim:** The data is machine-readable and pipeline-friendly: the page itself offers a CSV export, and the rendering is driven by an unauthenticated JSON API, meaning a GitHub-Actions scraper can pull structured data directly without HTML parsing (note: the page is JS-rendered, so a plain HTML fetch returns zero results — the API or CSV endpoint is the correct scrape target).
  - **Vote:** 0-3
  - **Source:** [https://nhlottery.com/Games/Scratch-Tickets/Unclaimed-Top-Prizes](https://nhlottery.com/Games/Scratch-Tickets/Unclaimed-Top-Prizes)

- **Claim:** The page exposes low/mid-tier prize counts for high-density 'Blowout'-style games (not just top prizes), so tier-level depletion can be measured directly — e.g. one game's $500 tier is nearly exhausted, a concrete anti-buy signal.
  - **Vote:** 1-2
  - **Source:** [https://www.masslottery.com/prizes_remaining](https://www.masslottery.com/prizes_remaining)

- **Claim:** Vermont's 2nd Chance program imposes a hard per-player cap of 10 ticket entries per day, bounding how much any single player can scale a positive-EV second-chance entry strategy.
  - **Vote:** 0-3
  - **Source:** [https://vtlottery.2ndchanceplay.com/draw_standards.html](https://vtlottery.2ndchanceplay.com/draw_standards.html)

## Caveats

Three merged claims carried 2-1 split votes (portfolio-variance non-investability; MA 140-row tier granularity; ME Fast Play extension) — each was nonetheless verified directly against primary sources, with the dissents reflecting scope/wording rather than substance (e.g., Fast Play game count is ~28-30, not ~40; MA full-tier data lives on detail pages, not the summary). Four claims were refuted outright and are excluded: the NH CSV/API-rendered-pipeline claim (0-3 — the API exists but the specific scrape-path description was wrong), the VT 10-entries/day cap (0-3), the Maine tier-granularity-is-top-only claim (1-2), and the MA Blowout low-tier-summary claim (1-2). Time-sensitivity: all state disclosure surfaces were verified live on 2026-07-25 and can change format at any time; MA 'hourly' is best-effort wording, NH daily cadence rests on one timestamp snapshot, and NH 'ticketsOrdered'=print-run is an undocumented interpretation. The Abrams-Garibaldi screening math is time-invariant but its 2010-era game parameters must be recomputed, and J means after-tax lump-sum, not the advertised annuity. Notably NOT verified by this research pass (context/background only, cite with care): the Selbee/MIT WinFall history, Srivastava's singleton flaw, and any current must-hit-by game in the four-state region. All computed instant-game EVs remain upper bounds because no state in scope publishes both full tier counts AND a tickets-sold denominator — the same identifiability wall this project's M6b analysis already proved for Maine.

## Open Questions

1. Do ME/NH/MA/VT publish per-drawing sales figures for their lotto/draw games (needed as N in the N/J screening criterion), and at what cadence — or can sales be inferred from published prize-pool or winner-count data?

2. Can MA's exact per-tier Claimed counts at high-frequency low tiers (e.g., $1/$2 prizes with known odds) be inverted into a tickets-sold estimate, giving MA a derived denominator and the first tight (non-upper-bound) EV ranking in the region?

3. Do Maine, NH, or MA second-chance programs disclose entry volumes (VT verifiably does not), and where do ME Fast Play progressive jackpot current values live for scraping?

4. Are there any live rolldown or must-hit-by mechanics in the four-state region today (e.g., in multi-state or regional draw games), or is the ME Fast Play progressive family genuinely the closest available analog?

## Source List

| URL | Quality | Angle | Claims |
|-----|---------|-------|--------|
| [https://highline.huffingtonpost.com/articles/en/lotto-winners/](https://highline.huffingtonpost.com/articles/en/lotto-winners/) | secondary | Documented historical exploits (case-study precedent) | 5 |
| [https://www.cbsnews.com/news/jerry-and-marge-selbee-how-a-retired-couple-won-millions-using-a-lottery-loophole-60-minutes-2019-06-09/](https://www.cbsnews.com/news/jerry-and-marge-selbee-how-a-retired-couple-won-millions-using-a-lottery-loophole-60-minutes-2019-06-09/) | secondary | Documented historical exploits (case-study precedent) | 5 |
| [https://www.wbur.org/news/2012/07/31/lottery-cash-winfall-report](https://www.wbur.org/news/2012/07/31/lottery-cash-winfall-report) | secondary | Documented historical exploits (case-study precedent) | 4 |
| [https://boingboing.net/2011/02/03/cracking-the-scratch.html](https://boingboing.net/2011/02/03/cracking-the-scratch.html) | blog | Documented historical exploits (case-study precedent) | 5 |
| [https://arxiv.org/abs/2507.01993](https://arxiv.org/abs/2507.01993) | primary | Academic/statistical literature on scratch-off EV | 5 |
| [https://scratchsmarter.com/scratch-off-games-ended-early-study/](https://scratchsmarter.com/scratch-off-games-ended-early-study/) | blog | Academic/statistical literature on scratch-off EV | 5 |
| [https://andykong.org/blog/palotteryexpectedvalue/](https://andykong.org/blog/palotteryexpectedvalue/) | blog | Academic/statistical literature on scratch-off EV | 4 |
| [https://www.mainelottery.com/players_info/unclaimed_prizes.html](https://www.mainelottery.com/players_info/unclaimed_prizes.html) | primary | State-specific data disclosures (ME/NH/MA/VT) | 5 |
| [https://nhlottery.com/Games/Scratch-Tickets/Unclaimed-Top-Prizes](https://nhlottery.com/Games/Scratch-Tickets/Unclaimed-Top-Prizes) | primary | State-specific data disclosures (ME/NH/MA/VT) | 5 |
| [https://www.masslottery.com/prizes_remaining](https://www.masslottery.com/prizes_remaining) | primary | State-specific data disclosures (ME/NH/MA/VT) | 5 |
| [https://vtlottery.2ndchanceplay.com/draw_standards.html](https://vtlottery.2ndchanceplay.com/draw_standards.html) | primary | State-specific data disclosures (ME/NH/MA/VT) | 5 |
| [https://www.mainelottery.com/fastplay/unclaimed_fastplay.html](https://www.mainelottery.com/fastplay/unclaimed_fastplay.html) | primary | State-specific data disclosures (ME/NH/MA/VT) | 5 |
| [https://lottoedge.com/strategy/overall-game-odds/allranking/scratch/state/maine-lottery/](https://lottoedge.com/strategy/overall-game-odds/allranking/scratch/state/maine-lottery/) | unreliable | State-specific data disclosures (ME/NH/MA/VT) | 0 |
| [https://abcnews.com/Technology/massachusetts-lottery-loophole-closed-investors-win-big/story?id=14213887](https://abcnews.com/Technology/massachusetts-lottery-loophole-closed-investors-win-big/story?id=14213887) | secondary | Draw-game structural anomalies and must-hit-by mechanics | 5 |
| [https://www.nber.org/system/files/working_papers/w11287/w11287.pdf](https://www.nber.org/system/files/working_papers/w11287/w11287.pdf) | primary | Skeptical/debunking literature on lottery myths | 5 |
| [https://dl.acm.org/doi/abs/10.5555/2772615.2772623](https://dl.acm.org/doi/abs/10.5555/2772615.2772623) | primary | Skeptical/debunking literature on lottery myths | 5 |
| [https://www.researchgate.net/publication/281575866_Predicting_lotto_numbers_A_natural_experiment_on_the_gambler's_fallacy_and_the_hot-hand_fallacy](https://www.researchgate.net/publication/281575866_Predicting_lotto_numbers_A_natural_experiment_on_the_gambler's_fallacy_and_the_hot-hand_fallacy) | primary | Skeptical/debunking literature on lottery myths | 5 |
| [https://patch.com/new-jersey/across-nj/these-lucky-nj-counties-sell-most-winning-lottery-tickets-here-s-why](https://patch.com/new-jersey/across-nj/these-lucky-nj-counties-sell-most-winning-lottery-tickets-here-s-why) | secondary | Skeptical/debunking literature on lottery myths | 5 |
| [https://www.cambridge.org/core/journals/judgment-and-decision-making/article/longitudinal-analysis-of-the-hot-hand-and-gamblers-fallacy-biases/FB70687B0F8B2C92B83DB439BA7DB500](https://www.cambridge.org/core/journals/judgment-and-decision-making/article/longitudinal-analysis-of-the-hot-hand-and-gamblers-fallacy-biases/FB70687B0F8B2C92B83DB439BA7DB500) | primary | Skeptical/debunking literature on lottery myths | 5 |
| [http://ai.stanford.edu/~nlambert/papers/judgment_sep2018.pdf](http://ai.stanford.edu/~nlambert/papers/judgment_sep2018.pdf) | primary | Skeptical/debunking literature on lottery myths | 5 |
