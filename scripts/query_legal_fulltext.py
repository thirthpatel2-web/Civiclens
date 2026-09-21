"""Ad-hoc semantic query against the full-text legal judgment corpus (proof/debugging tool - the
citizen-facing path is ``LegalAnalysisService``, not this script).

Usage:
    python scripts/query_legal_fulltext.py "what counts as circumstantial evidence in a murder case"
"""

from __future__ import annotations

import sys
import textwrap
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def main(argv: list[str] | None = None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    if not argv:
        print("usage: query_legal_fulltext.py <query text>", file=sys.stderr)
        return 2
    query = " ".join(argv)

    from app.core.config import Settings
    from app.db.repositories.content import SqlLegalJudgmentRepository
    from app.db.session import make_engine, make_session_factory
    from app.rag.ollama import OllamaClient, OllamaEmbeddingProvider

    settings = Settings.load()
    embedder = OllamaEmbeddingProvider(OllamaClient(settings.ollama_base_url), settings.ollama_embedding_model, settings.embedding_dimensions)
    session_factory = make_session_factory(make_engine(settings))

    qvec = embedder.embed([query])[0]
    with session_factory() as session:
        repo = SqlLegalJudgmentRepository(session)
        print("Corpus stats:", repo.stats())
        print(f"\nQuery: {query!r}\n")
        hits = repo.search(qvec, top_k=5)
        if not hits:
            print("No chunks indexed yet.")
            return 1
        for rank, (chunk_id, sim) in enumerate(hits, start=1):
            chunk = repo.get_chunk(chunk_id)
            judgment = repo.get_judgment(chunk.document_id) if chunk else None
            print(f"--- #{rank}  similarity={sim:.4f}  chunk={chunk_id} ---")
            if judgment:
                cite = judgment.neutral_citation or judgment.reporter_citation or "(no citation parsed)"
                print(f"    {judgment.title or judgment.id}  [{cite}]  {judgment.decision_date or ''}  page {chunk.page}")
            print(textwrap.fill(chunk.text[:600] if chunk else "(missing)", width=100, initial_indent="    ", subsequent_indent="    "))
            print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
