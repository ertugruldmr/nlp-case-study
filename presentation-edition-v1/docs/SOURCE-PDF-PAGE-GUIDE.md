# Source PDF page-by-page guide

This guide is a human map of the supplied 95-page Özak GYO 2012 audited-report PDF. It is not pipeline output and must not be used as hidden ground truth. It exists so a reviewer can understand what is on a page before deciding whether that page belongs to the extraction contract.

## Three scopes that must not be conflated

| Scope | Pages | Purpose |
|---|---:|---|
| Case contract | PDF 5–7 plus automatically located Note 11 (PDF 53–54) | The requested financial-statement/footnote-linking task and the only authoritative acceptance scope. |
| Extended statements | PDF 5–10 plus Note 11 | A defensible research extension covering balance sheet, comprehensive income, equity changes and cash flow. It requires additional table-layout work and new independently authored gold data. |
| Full-document visual review | PDF 1–95 | Browse, inspect OCR and collect feedback. This does not mean all 95 pages are equivalent summary tables. |

The PDF is scan/image based. PDF pages 5–95 normally correspond to printed report pages 1–91, so `printed page = PDF page − 4`. Several dense schedules are physically rotated; the debugger must use the OCR coordinate space and detected rotation for those pages.

## Every PDF page

| PDF | Printed | Content and review purpose |
|---:|---:|---|
| 1 | cover | Report cover: company, reporting date and consolidated-financial-statements title. Metadata only. |
| 2 | auditor 1 | Independent auditor’s report: addressee, responsibility and audit-scope narrative. Narrative OCR, not a financial table. |
| 3 | auditor 2 | Audit opinion and emphasis/other reporting text. Narrative OCR, not a summary table. |
| 4 | contents | Table of contents. Useful for note discovery and page-range validation, but not financial evidence. |
| 5 | 1 | Consolidated balance sheet — assets. Case-contract summary page; two comparative value columns and footnote references. |
| 6 | 2 | Consolidated balance sheet — liabilities and equity. Case-contract summary page; hierarchical rows, subtotals and totals. |
| 7 | 3 | Consolidated comprehensive income statement. Case-contract summary page; Note 11-linked investment-property rows appear here. |
| 8 | 4 | Consolidated statement of changes in equity. Landscape/rotated multi-column schedule; part of extended statements, not the case contract. |
| 9 | 5 | Consolidated cash-flow statement, first page: operating activities and reconciliation. Extended-statements candidate. |
| 10 | 6 | Cash-flow statement continuation: investing/financing movements and closing cash. Extended-statements candidate. |
| 11 | 7 | Note 1, organisation and operations of the Group. Narrative and entity metadata. |
| 12 | 8 | Note 1 continuation: subsidiaries/ownership and approval of the financial statements. |
| 13 | 9 | Note 2.1, basis of presentation and SPK reporting framework. |
| 14 | 10 | Note 2.1 continuation: accounting basis/comparatives and presentation matters. |
| 15 | 11 | Note 2.1 continuation: consolidation scope and ownership information. |
| 16 | 12 | Note 2.1 continuation: consolidation principles and subsidiaries/associates. |
| 17 | 13 | Notes 2.2–2.4: functional currency, accounting changes and new/revised standards introduction. |
| 18 | 14 | Note 2.4 continuation: standards and interpretations effective for the period. |
| 19 | 15 | Note 2.4 continuation: issued but not-yet-effective standards. |
| 20 | 16 | Note 2.4 continuation: financial-instrument standard changes, including IFRS 9 material. |
| 21 | 17 | Note 2.4 continuation: consolidation/joint-arrangement/disclosure standards. |
| 22 | 18 | Note 2.4 continuation: IFRS 13 and financial-instrument disclosure changes. |
| 23 | 19 | Note 2.4 continuation: IAS 19 and other standard amendments. |
| 24 | 20 | End of Note 2.4 and start of Note 2.5 significant accounting policies; revenue recognition. |
| 25 | 21 | Note 2.5: significant policies, including tangible fixed assets. |
| 26 | 22 | Tangible fixed assets continuation, depreciation/disposals and finance leases. |
| 27 | 23 | Intangible assets and impairment policies. |
| 28 | 24 | Borrowing-cost material and investment-property accounting policy. |
| 29 | 25 | Financial instruments: financial-asset classes and measurement. |
| 30 | 26 | Financial instruments continuation: impairment of financial assets. |
| 31 | 27 | Financial-asset impairment continuation, including receivables. |
| 32 | 28 | Derecognition of financial assets and financial liabilities. |
| 33 | 29 | Financial-instrument/equity classification policy continuation. |
| 34 | 30 | Accounting-policy continuation, including recognition under applicable IFRS. |
| 35 | 31 | Significant accounting-policy continuation. |
| 36 | 32 | Significant accounting-policy continuation. |
| 37 | 33 | Provisions, contingent assets and contingent liabilities policy. |
| 38 | 34 | Accounting-policy continuation, including foreign-currency/tax-related material. |
| 39 | 35 | Employee-benefits policy. |
| 40 | 36 | Cash-flow statement policy and start of Note 2.6 significant judgments/estimates. |
| 41 | 37 | Note 2.7 critical assumptions, including investment-property valuation. |
| 42 | 38 | Note 3 segment reporting: 2012 income/operation information. |
| 43 | 39 | Note 3 continuation: 2012 segment balance-sheet information. |
| 44 | 40 | Note 3 continuation: 2011 segment income information. |
| 45 | 41 | Note 3 continuation: 2011 segment balance-sheet information. |
| 46 | 42 | Note 4, cash and cash equivalents. |
| 47 | 43 | Note 5, financial investments, and Note 6, investments accounted for using the equity method. |
| 48 | 44 | Note 7, financial borrowings — balances and classifications. |
| 49 | 45 | Note 7 continuation: fair values, currencies and borrowing details. |
| 50 | 46 | Note 8, trade receivables and trade payables, including related-party references. |
| 51 | 47 | Note 9, other receivables and other payables. |
| 52 | 48 | Note 10, inventories. |
| 53 | 49 | Note 11, investment property: opening/closing balances, additions/transfers and valuation movements. Primary case-contract footnote target. |
| 54 | 50 | Note 11 continuation: valuation approach, fair-value details and explanatory narrative. Primary case-contract footnote target. |
| 55 | 51 | Note 12, tangible fixed assets movement schedule, first rotated/landscape page. |
| 56 | 52 | Note 12 movement schedule continuation, rotated/landscape. |
| 57 | 53 | End of Note 12 (depreciation lives) and start of Note 13, intangible assets. |
| 58 | 54 | Note 13 continuation and Note 14, goodwill. |
| 59 | 55 | Note 15, provisions, contingent assets and liabilities — schedules and cases. |
| 60 | 56 | Note 15 continuation: litigation/commitment narrative. |
| 61 | 57 | End of Note 15 and Note 16, commitments and obligations. |
| 62 | 58 | Note 17, employee benefits and provision calculations. |
| 63 | 59 | Note 17 continuation and start of Note 18, other assets and liabilities. |
| 64 | 60 | Note 18 continuation: non-current assets and short-term liabilities. |
| 65 | 61 | Note 19, equity: capital/share information. |
| 66 | 62 | Note 19 continuation: capital increase and reserves. |
| 67 | 63 | Note 19 continuation: reserves, distributable profit and dividend restrictions. |
| 68 | 64 | Note 20, revenue and cost of sales. |
| 69 | 65 | Note 21, marketing/selling/distribution and general-administration expenses. |
| 70 | 66 | Note 22, expenses by nature. |
| 71 | 67 | Note 23, other operating income and expenses. |
| 72 | 68 | Notes 24–25, finance income and finance expense. |
| 73 | 69 | Note 26, tax assets/liabilities and current-tax expense. |
| 74 | 70 | Note 26 continuation: corporation tax and investment allowance. |
| 75 | 71 | Note 26 continuation: deferred-tax bases and movements. |
| 76 | 72 | End of Note 26, tax reconciliation; Note 27, earnings per share. |
| 77 | 73 | Note 28, related-party disclosures — narrative and balances. |
| 78 | 74 | Note 28 related-party transaction/balance schedule, rotated/landscape. |
| 79 | 75 | Note 28 related-party schedule continuation, rotated/landscape. |
| 80 | 76 | Note 28 related-party schedule continuation, rotated/landscape. |
| 81 | 77 | Note 28 related-party schedule continuation, rotated/landscape. |
| 82 | 78 | End of Note 28 and start of Note 29, nature and level of financial risks. |
| 83 | 79 | Note 29 financial-risk schedule, rotated/landscape. |
| 84 | 80 | Note 29 financial-risk schedule continuation, rotated/landscape. |
| 85 | 81 | Note 29 credit-risk narrative and exposure analysis. |
| 86 | 82 | Note 29 credit-risk/liquidity-risk continuation. |
| 87 | 83 | Note 29 maturity analysis for financial liabilities. |
| 88 | 84 | Note 29 foreign-currency position for 2012. |
| 89 | 85 | Note 29 foreign-currency position for 2011. |
| 90 | 86 | Note 29 currency sensitivity analysis for 2012. |
| 91 | 87 | Note 29 currency sensitivity analysis for 2011. |
| 92 | 88 | Note 29 interest-rate risk and financial-instrument classifications. |
| 93 | 89 | Note 29 fair-value/classification schedule continuation, rotated/landscape. |
| 94 | 90 | Note 30 subsequent events and start of Note 31 portfolio-restriction compliance. |
| 95 | 91 | Note 31 portfolio-restriction compliance continuation and end of report. |

## How to use the guide

Use the debugger’s visual-review mode to verify page identity and orientation. Use a configured pipeline run only when the selected pages share a table contract the extractor actually supports. If a new interviewer PDF is supplied, create a new guide from that exact file hash; do not reuse page numbers or assumptions from this report.
