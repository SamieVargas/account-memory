# The contract subset

`python scripts/select_contracts.py` applies this rule and writes
`data/selection.json`. Constants live at the top of that script.

## Rule

1. **Candidates.** CUAD contracts whose primary `contract_type` is one of the
   commercial-relationship types: license, services, outsourcing, supply,
   manufacturing, distributor, reseller, maintenance, hosting. Excluded:
   sponsorship, endorsement, strategic alliance, collaboration, co-branding,
   joint venture, franchise, agency, consulting, affiliate, promotion,
   marketing, development, IP, transportation, non-compete, joint filing.
   238 of 510 contracts.
2. **Enough clauses to score.** At least 3 distinct non-metadata CUAD
   categories with a gold span, so each contract contributes to the
   automatic retrieval set. 191 of the 238.
3. **Tiers, from the EDGAR ingest.** A: the account resolved to a CIK with a
   usable annual revenue series. B: resolved, no revenue series. C:
   unresolved.
4. **Fill to 80.** Tier A first, then B, then C. Within a tier, sort by
   contract id and shuffle with `random.Random(20260923)`. Take contracts in
   that order, skipping any whose type already has 15, until 80 are chosen.

## Result

Run on 2026-09-25 against the EDGAR ingest of the same day
(`evals/results/ingest-edgar-2026-09-25.md`), seed 20260923.

| Tier | Candidates | Selected |
| --- | --- | --- |
| A: account resolved, revenue series | 96 | 80 |
| B: account resolved, no revenue | 89 | 0 |
| C: unresolved | 6 | 0 |
| Total | 191 | 80 |

Match rate of the selection: 80 of 80 (100%); every selected contract has
a resolved account with an annual revenue series. Across all 238 commercial
contracts the match rate is 229 of 238 (96%).

| Contract type | Selected |
| --- | --- |
| distributor | 15 (the per-type cap) |
| license | 14 |
| supply | 14 |
| services | 12 |
| reseller | 7 |
| maintenance | 6 |
| manufacturing | 5 |
| outsourcing | 4 |
| hosting | 3 |

The time box did not bite: tier A alone had more than enough contracts, so
no one chased more matches. The subset is `data/selection.json`.

`--provisional` selects with every candidate in tier C, for development
before EDGAR has run. A provisional selection is marked as such in the JSON
and is not used for any reported number.
