# EDGAR ingest, 2026-09-25

Candidates: 238 commercial contracts. Client: 3 requests, 578 cache hits, rate 4/s.

| Measure | n |
| --- | --- |
| Contracts with a resolved account | 229 of 238 (96%) |
| Names resolved by edgar_name_index_exact | 410 |
| Names resolved by edgar_name_index_fuzzy | 7 |
| Names resolved by tickers_exact | 130 |
| Names unresolved | 396 |
| data/cik_review.csv: decided rows kept / new rows to review | 0 / 99 |
| data/cik_review.csv: close spellings accepted automatically (mark no to reject) | 0 |
| Parent filing ambiguous | 45 |
| Parent filing no_date | 14 |
| Parent filing not_found | 9 |
| Parent filing resolved | 161 |
| 10-Ks fetched | 127 |
| Item 1A extractions succeeded / failed | 109 / 18 |
| Contracts with no 10-K to use: no 10-K on file | 67 |
| Contracts with no 10-K to use: only 10-Ks for periods before 2005-12-01, which have no Item 1A | 15 |
| Contracts with no 10-K to use: no agreement or filing date to match a 10-K to | 4 |
| Contracts that hit an error (rerun to retry) | 0 |
| Companies with a revenue series | 97 of 201 |
| Revenue concept used: Revenues | 75 companies |
| Revenue concept used: RevenueFromContractWithCustomerExcludingAssessedTax | 44 companies |
| Revenue concept used: SalesRevenueNet | 29 companies |
| Revenue concept used: RevenueFromContractWithCustomerIncludingAssessedTax | 7 companies |
| Revenue concept used: SalesRevenueGoodsNet | 3 companies |
| Revenue concept used: SalesRevenueServicesNet | 2 companies |

## Item 1A failures

- not provided (smaller reporting company or not applicable): 15
- section is 11 chars: 1
- incorporated by reference: 1
- no Item 1A heading followed by an Item 1B, 1C or 2 heading: 1

| CIK | Company | Filed | Reason | Start of the section |
| --- | --- | --- | --- | --- |
| 757641 | BNL FINANCIAL CORP | 2007-03-30 | incorporated by reference | The Company is not aware of any risk factors which may relate to speculative or risky circumstances to the Company’s outstanding common stock. To the extent whi |
| 1004963 | WATCHIT MEDIA, INC. | 2006-04-17 | no Item 1A heading followed by an Item 1B, 1C or 2 heading |  |
| 1070699 | UAGH INC | 2009-09-28 | not provided (smaller reporting company or not applicable) | Not required for smaller reporting companies. |
| 1070799 | OPTIMIZED TRANSPORTATION MANAGEMENT, INC. | 2009-03-23 | not provided (smaller reporting company or not applicable) | As a smaller reporting company, we have elected not to provide the information required by this item. |
| 1118847 | QUANTUM GROUP INC /FL | 2009-02-13 | not provided (smaller reporting company or not applicable) | We are a smaller reporting company as defined in Item 10(f)(1) of Regulation S-K and thus are not required to report the risk factors specified in Item 503(c) o |
| 1375850 | HUBEI MINKANG PHARMACEUTICAL LTD. | 2009-07-14 | not provided (smaller reporting company or not applicable) | As a “smaller reporting company” (as defined by §229.10(f)(1)), we are not required to provide the information required by this Item. |
| 1402453 | HER IMPORTS | 2016-04-14 | not provided (smaller reporting company or not applicable) | As a Smaller Reporting Company, we are not required to provide risk factors. |
| 1449574 | BRAVATEK SOLUTIONS, INC. | 2017-07-21 | not provided (smaller reporting company or not applicable) | . Not required for Smaller Reporting Companies. |
| 1492116 | FULUCAI PRODUCTIONS LTD. | 2012-07-27 | not provided (smaller reporting company or not applicable) | The Company is a smaller reporting company and is not required to provide this information. |
| 1567900 | BLACKBOXSTOCKS INC. | 2015-03-11 | not provided (smaller reporting company or not applicable) | Smaller reporting companies are not required to provide the information required by this item. |
| 1577445 | SCOUTCAM INC. | 2019-07-09 | not provided (smaller reporting company or not applicable) | As a smaller reporting company, we are not required to provide the information required by this Item. |
| 1591157 | GENTECH HOLDINGS, INC. | 2018-10-05 | not provided (smaller reporting company or not applicable) | . Since we are a smaller reporting company, we are not required to supply the information required by this Item 1A. |
| 1629205 | GRIDIRON BIONUTRIENTS, INC. | 2019-12-17 | not provided (smaller reporting company or not applicable) | As a “smaller reporting company,” as defined in Rule 12b-2 of the Exchange Act, we are not required to provide the information called for by this Item. |
| 1636509 | VITALIBIS, INC. | 2018-04-10 | not provided (smaller reporting company or not applicable) | We are a smaller reporting company as defined by Rule 12b-2 of the Exchange Act and are not required to provide the information under this item. |
| 1713210 | Agape ATP Corp | 2018-09-27 | not provided (smaller reporting company or not applicable) | We are a smaller reporting company as defined by Rule 12b-2 of the Securities Exchange Act of 1934 and are not required to provide the information under this it |
| 1729750 | KUBIENT, INC. | 2021-03-30 | not provided (smaller reporting company or not applicable) | Not applicable to smaller reporting companies. |
| 1740797 | FREECOOK | 2019-07-15 | not provided (smaller reporting company or not applicable) | Not applicable to smaller reporting companies. |
| 1357649 | WELLS FARGO MORTGAGE BACKED SECURITIES 2006-6 TRUST | 2007-03-30 | section is 11 chars | . Omitted. |

## Errors


## Unresolved contracts

- ImperialGardenResortInc_20161028_DRS (on F-1)_EX-10.13_9963189_EX-10.13_Outsourcing Agreement
- Columbia Laboratories, (Bermuda) Ltd. - AMEND NO. 2 TO MANUFACTURING AND SUPPLY AGREEMENT
- XACCT Technologies, Inc.SUPPORT AND MAINTENANCE AGREEMENT
- Apollo Endosurgery - Manufacturing and Supply Agreement
- ADMA BioManufacturing, LLC -  Amendment #3 to Manufacturing Agreement 
- ArtaraTherapeuticsInc_20200110_8-K_EX-10.5_11943350_EX-10.5_License Agreement
- ASIANDRAGONGROUPINC_08_11_2005-EX-10.5-Reseller Agreement
- ParatekPharmaceuticalsInc_20170505_10-KA_EX-10.29_10323872_EX-10.29_Outsourcing Agreement
- SPIENERGYCO,LTD_03_09_2011-EX-99.5-OPERATIONS AND MAINTENANCE AGREEMENT
