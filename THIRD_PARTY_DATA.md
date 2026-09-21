# Third-party data

The MIT license in `LICENSE` covers CivicLens's own source code only. Data ingested into the
database by the scripts below comes from external public sources under their own licenses -
those licenses apply to that data independently of how this repository is licensed.

## Indian Supreme Court judgments

- **Source:** [`indian-supreme-court-judgments`](https://github.com/vanga/indian-supreme-court-judgments)
  public S3 bucket (`indian-supreme-court-judgments.s3.amazonaws.com`), maintained by Vanga.
- **License:** CC-BY-4.0 (per the source repository).
- **What CivicLens ingests, and with which script:**
  - Judgment metadata (`metadata/parquet/year=YYYY/metadata.parquet`) -
    `scripts/ingest_legal_metadata_bulk.py` -> the `legal_precedents` table.
  - Full judgment text PDFs (`data/pdf/year=YYYY/english/*.pdf`) -
    `scripts/ingest_legal_fulltext.py` -> the `legal_judgments` / `legal_judgment_chunks` tables.
- **Attribution:** case metadata and full judgment text originate from the Supreme Court of
  India's own public judgments, redistributed by the above project under CC-BY-4.0. Any
  redistribution of this data (not just the CivicLens code that processes it) must carry the
  same attribution.

## Government platform integrations (no data ingested - reference only)

`app/integrations/adapters.py` implements HTTP clients for CPGRAMS, UMANG, Swachhata, BBMP
Sahaaya and MyGov. These are **not populated with any real government data** - they require
official API credentials this project does not have, and report `NOT_CONFIGURED` until an
authorized deployment supplies them. No third-party license applies because no data from these
platforms is bundled or ingested.

## Runtime models (not bundled - pulled by the operator, not this repository)

Ollama models (`llama3.1`, `nomic-embed-text`, etc.), Whisper speech-to-text models, and any
OCR language data are downloaded separately by whoever deploys CivicLens, under their own
respective licenses (see each model's own card/repository). None of these model weights are
committed to this repository.
