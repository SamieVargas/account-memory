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

Not run yet: step 3 needs `scripts/ingest_edgar.py`, which needs the SEC's
servers (unreachable from the session that set this repo up). Once it runs,
record here the candidate count per tier, the selected count per tier and
type, and the match rate (selected contracts in tiers A and B over 80).

If the match rate is low, the brief's time box applies: shrink the subset to
the contracts that resolved rather than chasing more matches, and record the
new target here.

`--provisional` selects with every candidate in tier C, for development
before EDGAR has run. A provisional selection is marked as such in the JSON
and is not used for any reported number.
