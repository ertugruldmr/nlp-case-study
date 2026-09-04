# Genuine alternate-PDF demo

This smoke sends a genuinely different public filing through the app's upload API and
the sealed `ftlink` pipeline. It proves document/config propagation and run isolation;
it is not an accuracy benchmark.

## Evidence-bound input

- Filing: Özak GYO, 31 December 2013 consolidated financial statements.
- Local source (package-safe): `fixtures/ozak_gyo_2013.pdf`.
- Research provenance source: `../research/assets/second-doc/ozak-gyo-2013/source.pdf`.
- Source provenance: `../research/assets/second-doc/ozak-gyo-2013/SOURCE.md`.
- SHA-256: `7bed2e05c84a467e2c797767f59a1087594526aead2362bd810f5d5e123a36bd`.
- PDF facts independently checked with `pdfinfo`: 91 pages, 1,126,664 bytes,
  unencrypted. Unlike the scanned 2012 case PDF, all 91 pages have a text layer;
  the current pipeline still OCRs them.
- Configuration: summary PDF pages 6-8, footnote 12, reporting period
  `2013-12-31`, currency `TL`, OCR language `tur`, extra control pages 10-11.

The historical research run completed in 22.0 seconds and emitted 6 tables, 111 rows,
220 cells, 4 relations and checks 80 pass / 8 fail / 3 not-evaluable. Those are
observations, not accuracy figures: there is no committed cell/relation gold set for
this filing. Do not say “4/4 correct” from this smoke alone. Its historical
`config.yaml` also carries a stale `period_end: 2012-12-31`; this recipe deliberately
passes and verifies the source-correct `2013-12-31` instead of copying that metadata.

## Run

Start the app, then run the evidence-bound smoke:

```bash
cd app
make serve
# in another terminal
./demo_alternate_pdf.sh
```

The script refuses a source hash mismatch, uploads the PDF through
`POST /api/documents`, starts it through `POST /api/documents/{doc_id}/run`, waits for
completion, and asserts all of the following against the newly stored result:

1. output `source_sha256` equals the alternate PDF and differs from the baseline;
2. effective summary pages are 6-8;
3. effective footnote is 12;
4. effective document metadata is the 2013 reporting period with `TL`/`tur`;
5. effective calibration-control pages are 10 and 11;
6. every emitted table page is inside the alternate PDF's 91-page boundary.

It then prints observed counts and links to the run's debugger and JSON. Review the
report/debugger for qualitative evidence. A quantitative accuracy claim requires an
independent gold set and scorer for this document.

## Known boundary

This is evidence for transfer to another Özak Turkish KAP-style filing. It does not
establish arbitrary-layout or arbitrary-language generality. The existing Emlak Konut
2012 research input is a useful negative case: its `DİPNOT n` locator convention is
not supported by the current `NOT n`/numeric-heading locator, and the recorded run
exits cleanly without output.
