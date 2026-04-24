"""Retrieval-threshold calibration for Phase 33 (Plan 33-03, Wave 2).

Sweeps RETRIEVAL_SIMILARITY_THRESHOLD candidates against the 20-query fixture
at modules/pathfinder/tests/fixtures/rules_threshold_calibration.json and
picks the threshold that maximizes classification accuracy on hit/miss.

Procedure:
  1. Load the 149-chunk Player-Core corpus (data/rules-corpus.json).
  2. Embed every chunk once via LM Studio's
     text-embedding-nomic-embed-text-v1.5 (768-dim).
  3. Load the 20-query fixture (hit / miss / decline labels).
  4. Drop `decline` queries — those are caught by the PF1 denylist
     (app.rules.check_pf1_scope) BEFORE retrieval runs; they do not
     reach the similarity threshold.
  5. Embed each query; compute top-1 similarity against the corpus.
  6. For each candidate threshold in the sweep grid, compute:
       - accuracy on hit queries  (top1_sim >= threshold → TP)
       - accuracy on miss queries (top1_sim < threshold  → TN)
       - overall accuracy + precision + recall + F1 on the 'hit' class
  7. Print the sweep table and pick the threshold maximizing F1 (primary),
     breaking ties by higher recall (miss-a-hit is worse than spurious-hit
     in this domain — the LLM composer can still decline a weak passage).

Run (from modules/pathfinder/, with LM Studio running):
  SENTINEL_API_KEY=test OPENAI_API_KEY=dummy uv run python scripts/calibrate_retrieval_threshold.py

Output is a plain-text summary printed to stdout. The calibration log is
captured inline in the plan 33-03 SUMMARY rather than written to a file.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
from pathlib import Path

import numpy as np

# Hard-add the module root so `python scripts/…` works like the scaffold scripts.
_MODULE_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_MODULE_ROOT))

from app.llm import embed_texts  # noqa: E402
from app.rules import (  # noqa: E402
    RuleChunk,
    cosine_similarity,
    load_rules_corpus,
)

logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(message)s")

CANDIDATE_THRESHOLDS = [0.30, 0.35, 0.40, 0.45, 0.50, 0.55, 0.60, 0.65, 0.70, 0.75]


async def _embed_corpus(
    chunks: list[RuleChunk], model: str, api_base: str, batch: int = 32
) -> np.ndarray:
    """Embed every chunk text; return an (N, D) float32 matrix."""
    vectors: list[list[float]] = []
    total = len(chunks)
    for i in range(0, total, batch):
        end = min(i + batch, total)
        batch_texts = [c.text for c in chunks[i:end]]
        sys.stderr.write(f"  embedding corpus chunks [{i}:{end}] / {total}\n")
        sys.stderr.flush()
        vecs = await embed_texts(batch_texts, model=model, api_base=api_base)
        vectors.extend(vecs)
    return np.asarray(vectors, dtype=np.float32)


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--corpus",
        default=str(_MODULE_ROOT / "data" / "rules-corpus.json"),
        help="Path to rules-corpus.json",
    )
    parser.add_argument(
        "--fixture",
        default=str(_MODULE_ROOT / "tests" / "fixtures" / "rules_threshold_calibration.json"),
        help="Path to calibration fixture",
    )
    parser.add_argument(
        "--model",
        default="openai/text-embedding-nomic-embed-text-v1.5",
        help="Embedding model id (with provider prefix)",
    )
    parser.add_argument(
        "--api-base",
        default="http://localhost:1234/v1",
        help="LiteLLM api_base (LM Studio)",
    )
    args = parser.parse_args()

    print(f"Loading corpus: {args.corpus}")
    chunks = load_rules_corpus(Path(args.corpus))
    print(f"  chunks: {len(chunks)}")

    print(f"Loading fixture: {args.fixture}")
    fixture = json.loads(Path(args.fixture).read_text())
    print(f"  queries: {len(fixture)}")

    # Embed corpus.
    print("Embedding corpus (batched; this calls LM Studio many times)…")
    matrix = await _embed_corpus(chunks, model=args.model, api_base=args.api_base)
    print(f"  matrix shape: {matrix.shape}")

    # Embed queries.
    print("Embedding queries…")
    query_texts = [q["query"] for q in fixture]
    query_vectors = await embed_texts(query_texts, model=args.model, api_base=args.api_base)
    print(f"  query matrix rows: {len(query_vectors)}")

    # For each query compute top-1 similarity.
    rows: list[dict] = []
    for i, q in enumerate(fixture):
        qvec = np.asarray(query_vectors[i], dtype=np.float32)
        sims = cosine_similarity(matrix, qvec)
        top1_idx = int(np.argmax(sims))
        top1_sim = float(sims[top1_idx])
        rows.append(
            {
                "query": q["query"],
                "expected": q["expected"],
                "expected_topic": q.get("expected_topic"),
                "expected_source": q.get("expected_source"),
                "top1_sim": top1_sim,
                "top1_chunk_id": chunks[top1_idx].id,
                "top1_section": chunks[top1_idx].section,
                "top1_page": chunks[top1_idx].page,
            }
        )

    # Partition by expected label.
    hits = [r for r in rows if r["expected"] == "hit"]
    misses = [r for r in rows if r["expected"] == "miss"]
    declines = [r for r in rows if r["expected"] == "decline"]
    print(
        f"\nLabel counts: hit={len(hits)} miss={len(misses)} decline={len(declines)}"
    )
    print(
        "Declines are excluded from the sweep — they are caught by "
        "app.rules.check_pf1_scope BEFORE retrieval runs."
    )

    # Per-query diagnostic dump.
    print("\nPer-query top-1 similarity:")
    for r in rows:
        print(
            f"  [{r['expected']:<7}] sim={r['top1_sim']:.4f}  "
            f"-> {r['top1_section']} (p.{r['top1_page']})  :: {r['query'][:60]}"
        )

    # Sweep.
    print("\nThreshold sweep (hit + miss only):")
    print(
        f"{'thr':>6} | {'hit_acc':>8} | {'miss_acc':>9} | {'acc':>6} | "
        f"{'prec':>6} | {'recall':>7} | {'F1':>6}"
    )
    print("-" * 70)

    best = None  # (thr, f1, recall)
    results: list[dict] = []
    for thr in CANDIDATE_THRESHOLDS:
        tp = sum(1 for r in hits if r["top1_sim"] >= thr)
        fn = len(hits) - tp
        fp = sum(1 for r in misses if r["top1_sim"] >= thr)
        tn = len(misses) - fp
        hit_acc = tp / len(hits) if hits else 0.0
        miss_acc = tn / len(misses) if misses else 0.0
        total_correct = tp + tn
        total = len(hits) + len(misses)
        acc = total_correct / total if total else 0.0
        precision = tp / (tp + fp) if (tp + fp) else 0.0
        recall = tp / (tp + fn) if (tp + fn) else 0.0
        f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0
        results.append(
            {
                "thr": thr,
                "tp": tp, "fp": fp, "tn": tn, "fn": fn,
                "hit_acc": hit_acc, "miss_acc": miss_acc, "acc": acc,
                "precision": precision, "recall": recall, "f1": f1,
            }
        )
        print(
            f"{thr:>6.2f} | {hit_acc:>8.3f} | {miss_acc:>9.3f} | {acc:>6.3f} | "
            f"{precision:>6.3f} | {recall:>7.3f} | {f1:>6.3f}"
        )
        if best is None or (f1, recall) > (best[1], best[2]):
            best = (thr, f1, recall)

    print()
    assert best is not None
    print(
        f"Maximizer: threshold={best[0]:.2f}  F1={best[1]:.3f}  recall={best[2]:.3f}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
