# Clause-position playbook

I am writing every position below. I am committing these changes _before_ the golden set is written and before any retrieval run. The playbook-check questions will be graded against this file, and its hash goes into every result. Heading are each category, and the category names match CUAD's, so each position can be joined to its gold spans. CUAD is the Contract Understanding Atticus Dataset, a massive, open-source benchmark collection used in AI & NLP to review legal agreements. 

Written from a vendor's side, the counterparty is the client account, the company whose SEC filings we have.

Not legal advice.

## 1. Cap On Liability
> **In plain terms:** Establishes the maximum aggregate financial damages that either party can recover from the other in the event of a breach, negligence, or legal claim coming out of the agreement. 
### Preferred position:
Total aggregated liability for either party is capped at 12x trailing twelve months (TTM) fees paid or payable under the agreement, or a fixed dollar cap equal to the total contract value. In-mid-market enterprise SaaS aggreements, cappting damages at 12x TTM ensures that if a software outage halts operations, the vendor's financial exporse is proportional to the subscription reneue, aligning the financial exposure directly with the commercial value of the relationship, protecting parties from disproportionate damages. 
### Acceptable fallback:
Capped at 1x to 2x annual fees, provided there is clear carve-out list for catastrophic breaches (e.g., IP infringement, confidentiality breaches).
### Escalate if:
The counterparty demands completely unlimited (uncapped) liability, or caps liability at an absurdly low amount (e.g., $1,000) that would not actually cover actual damages. 

## 2. Uncapped Liability
> **In plain terms:** A clause to identiy specific high-risk breach categories where financial limits are entirely removed, exposing the breaching party to unlimited damages.
### Preferred position:
Uncapped liability applies exclusively to a very narrow and clearly defined list of catastophic breaches, including: gross negligence, willful misconduct, breach of confidentiality, and intellectual property (IP) infringement. 
### Acceptable fallback:
Uncapped liability may also include data privacy or cybersecurity breaches (e.g., data leak exposing customer PII), **provided the obligation is mutual.** Meaning if counterparty's system causes a data leak on their end, they face the same uncapped liability. 
### Escalate if:
The counterparty tries to make _ordinary_ breaches like standard service-level agreemtn (SLA) failures) or everyday bugs subhect to uncapped liability (e.g., If a software bug crashes checkout page for an hour, that should only be covered by the normal liability cap, _not_ an infinite financial lawsuit). 

## 3. Termination For Convenience
> **In plain terms:** A clause granting either party the right to terminate the contract voluntarily without needing to prove a breach or default by the other party. 
### Preferred position: 
Either party can terminate the agreement for convenience at any time by giving **30 days written notice**, with no financial penalty other than paying for services for software already delivered up to that termination date. 
### Acceptable fallback: 
Termination of convenience is permitted with 60 to 90 days notice, plus manditory reimbursement of the counterparty's actual, non-recoverable, out-of-pocket setup costs (e.g., custom engineering, pre-purchased hardware). 
### Escalate if:
Only the counterparty retains the right to walk away while the party is locked-in, or if terminating early triggers a punitive financial penalty (e.g., paying 100% of the remaining contract value). 

## 4. Renewal Term
> **In plain terms:** Clause that governs how the contract continues after the initial expiration date, including whether it automatically rolls over into subsequent periods. 
### Preferred position:
The contract automatically renews for successive **1-year terms** unless either party gives timely written notice of non-renwal. 
### Acceptable fallback:
Automatic 1-year renewals are acceptable, but any price increases for the renewal term must be explicitly capped (e.g., maximum of 3% to 5% per year or tying it to a standard economic index like CPI). 
### Escalate if: 
The counterparty tries to lock the other party into a multi-year automatic renewal (e.g., automatic 3-year lock-ins) or leaves renewal price increases completely uncapped. 

## 5. Notice Period To Terminate Renewal
> **In plain terms:** Clause to specify the exact advance timeline required for a party to notify the counterparty that they do not wish to renew the contract. 
### Preferred position: 
Written notice of non-renewal must be provided at least 30 days prior to the expiration of the current term. 
### Acceptable fallback: 
Written notice required at least 60 days prior to the expiration of the current term. 
### Escalate if: 
The counterparty inserts a 90-to-120-day advance notice requirement, creating an intentional trap that easily leads to missed deadlines and unwanted contract lock-in. 

## 6. Anti-Assignment
> **In plain terms:** Clause regulating whether and under what conditions the contracting parties can transfer their rights, duties, or obligations under the agreement to a third-party. 
### Preferred position: 
Complete feedom to aggin or transfer the contract to an affiliate or to a successor entity in connection with a merger, acquisition, corporate reorganization, or sale of substantially all assets, without requiring prior written consent. 
### Acceptable fallback: 
Assignment requires written notice or consent, provided that such consent cannot be unreasonably withheld, delayed, or conditioned, and internal affiliate transfers are permitted unconditionally. 
### Escalate if: 
The counterparty reserves the absolute right to block corporate restructuring or demands a financial transfer fee unpon acquisition. 

## 7. Change Of Control
> **In plain terms:** Clause governing what happens to the contract if ownership or control of a contracting party shift (e.g., sale of more than 50% of the voting stock, a merger, or a sale of substantially all asset to a third party). 
### Preferred position: 
The agreement permits either party to terminate the contract without penalty if the counterparty undergoes a Change of Control involving a direct competitor of the terminating party. 
### Acceptable fallback: 
No automatic termination right for Change of Control, provided the agreement remains fully guaranteed by the surviving entity and confidential data barriers are maintained. 
### Escalate if: 
The counterparty imposes a Change of Control penalty on the party if they under an acquisition, or claims the right to cancel service unpon ownership change. 

## 8. Exclusivity
> **In plain terms:** Clause restricting one or both parties from engaging with competitors, sourcing similar services elsewhere, or selling to specific markets during the agreement terms. 
### Preferred position: 
The contract is entierly non-exclusive, preserving the right for both parties to partner with, buy from or sell to any third-party, including direct competitors. 
### Acceptable fallback: 
Mutual exclusivity, strictly bounded to a narrow product sub-category, specific territory, and a short duration (e.g., maximum 6 months). 
### Escalate if: 
The counterparty imposes broad, unilateral, long-term exclusivity that locks the party out of entire product categories or supplier networks without reciprical commercial considerations. 

## 9. Most Favored Nation
> **In plain terms:** Clause requiring vendors to guarantee that the contracting party receives pricing, discounts, and terms that are a least as favorable as those offered to any other customer. 
### Preferred position: 
Reject Most Favorable Nation (MFN) clauses entirely.
### Acceptable fallback: 
If acceptable, MFN is restricted strictly to pricing (excluding general terms), applies exclusively to clients of identical size ordering identical volum tiers, and has a defined expiration timeline (e.g., expires after 1 year). 
### Escalate if: 
Broad, multi-year MFN clauses that require deep historical pricing audits and retrospective cash refunds across the entire agreement history. 

## 10. Audit Rights
> **In plain terms:** Clause defining whether, when, and how one party can inspect the financial records, systems, and facilities of the other party to verify compliance with pricing, usage caps, or regulatory obligations. 
### Preferred position:
Audits are permitted strictly once per calendar year, during normal business hours, upon at least 30 days prior written notice, and conducted by an independent certified public accountant bound by confidentiality, with the auditing party bearing all costs. 
### Acceptable fallback: 
Audits are permitted up to twice per year with 15 days written notice; if an underpayment or discrepancy exceeding 5% is uncovered, the audited party reimburses the reasonable cost of the audit. 
### Escalate if: 
The counterparty demands unannounced audits, unlimited access to proprietary source code or core systems or forces the other party to pay for their auditing expenses regardless of findings. 

## Filing-data rules (optional)
Lines that use the counterparty's SEC filings or revenue series, which gives the playbook check a cross-document case. Any comparison they need is computed in pandas from the revenu table. 
1. **Rule 1 (Revenue-Tied Pricing Verification):** Compare the counterparty's TTM revenue pulled from their latest SEC Form 10-K against the pricing tier thresholds define in the agreement. Flag any discrepancy where tier-based discounts do not match reported revenue brackets.
2. **Rule 2 (Insolvency & Cash Flow Monitoring):** Compute operating cash flow and current rations from the counterparty's quarterly SEC filings in pandas. If net operating cash flow drops below threshold $X for two consecutive quarters, escalate for financial viability review. 
