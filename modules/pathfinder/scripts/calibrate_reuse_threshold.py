"""Reuse-threshold calibration for Phase 33.1 (D-05 reuse threshold).

Sweeps REUSE_SIMILARITY_THRESHOLD candidates against the paraphrase fixture
at modules/pathfinder/tests/fixtures/rules_reuse_calibration.json and picks
the threshold that maximizes F1 on the paraphrase class.

Procedure:
  1. Load the paraphrase fixture (8 anchors × 3 paraphrases + 2 different = 40 labeled pairs).
  2. Embed every unique query string ONCE via LM Studio's
     text-embedding-nomic-embed-text-v1.5 (768-dim).
  3. For each (anchor, candidate) pair, compute cosine similarity.
  4. Label: candidate from `paraphrases[]` -> positive (should reuse);
     candidate from `different[]`         -> negative (should NOT reuse).
  5. For each candidate threshold T:
       - paraphrase pairs with cosine >= T  -> TP (true reuse)
       - paraphrase pairs with cosine < T   -> FN (missed reuse)
       - different pairs   with cosine >= T -> FP (false reuse — bad: serves stale answer)
       - different pairs   with cosine < T  -> TN (correct compose-fresh)
  6. Print the sweep table and pick the threshold maximizing F1, breaking ties
     by HIGHER PRECISION (a false reuse serves a stale answer that's a different
     question — worse than a missed reuse, where the LLM just composes fresh
     and pays a few seconds).

Run (from modules/pathfinder/, with LM Studio running):
  SENTINEL_API_KEY=test OPENAI_API_KEY=dummy uv run python scripts/calibrate_reuse_threshold.py

Output is a plain-text summary printed to stdout. Capture inline in the
Phase 33.1 SUMMARY for the calibration record.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

import numpy as np

_MODULE_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_MODULE_ROOT))

from app.config import settings  # noqa: E402
from app.llm import embed_texts  # noqa: E402
from app.rules import cosine_similarity  # noqa: E402

_DEFAULT_EMBED_MODEL = settings.rules_embedding_model

# Sweep grid — 0.05 spacing across the plausible band for paraphrase
# similarity on nomic-embed-text-v1.5. Tighter at the upper end where the
# decision boundary actually lives.
CANDIDATE_THRESHOLDS = [
    0.50, 0.55, 0.60, 0.65, 0.68, 0.70, 0.72, 0.74, 0.76, 0.78, 0.80, 0.82, 0.85,
]


async def _embed_unique(
    queries: list[str], model: str, api_base: str, batch: int = 32
) -> dict[str, np.ndarray]:
    """Embed each unique query string exactly once; return {query: vector}."""
    unique = list(dict.fromkeys(queries))  # preserve order, dedupe
    vectors: dict[str, np.ndarray] = {}
    total = len(unique)
    for i in range(0, total, batch):
        end = min(i + batch, total)
        batch_texts = unique[i:end]
        sys.stderr.write(f"  embedding queries [{i}:{end}] / {total}\n")
        sys.stderr.flush()
        vecs = await embed_texts(batch_texts, model=model, api_base=api_base)
        for text, vec in zip(batch_texts, vecs):
            vectors[text] = np.asarray(vec, dtype=np.float32)
    return vectors


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--fixture",
        default=str(_MODULE_ROOT / "tests" / "fixtures" / "rules_reuse_calibration.json"),
        help="Path to reuse calibration fixture",
    )
    parser.add_argument(
        "--model",
        default=_DEFAULT_EMBED_MODEL,
        help="Embedding model id (defaults to settings.rules_embedding_model)",
    )
    parser.add_argument(
        "--api-base",
        default="http://localhost:1234/v1",
        help="LiteLLM api_base (LM Studio)",
    )
    args = parser.parse_args()

    print(f"Loading fixture: {args.fixture}")
    fixture = json.loads(Path(args.fixture).read_text())
    print(f"  anchors: {len(fixture)}")

    # Build the labeled pair list and the unique-query list for embedding.
    pairs: list[dict] = []
    queries: list[str] = []
    for entry in fixture:
        anchor = entry["anchor"]
        topic = entry.get("topic", "?")
        queries.append(anchor)
        for p in entry.get("paraphrases", []):
            queries.append(p)
            pairs.append({"anchor": anchor, "candidate": p, "topic": topic, "label": "paraphrase"})
        for d in entry.get("different", []):
            queries.append(d)
            pairs.append({"anchor": anchor, "candidate": d, "topic": topic, "label": "different"})

    paraphrase_count = sum(1 for p in pairs if p["label"] == "paraphrase")
    different_count = sum(1 for p in pairs if p["label"] == "different")
    print(f"  pairs: {len(pairs)} ({paraphrase_count} paraphrase, {different_count} different)")
    print(f"  unique queries to embed: {len(set(queries))}")

    # Embed every unique query string once.
    print("\nEmbedding unique queries via LM Studio…")
    vectors = await _embed_unique(queries, model=args.model, api_base=args.api_base)
    print(f"  embedded: {len(vectors)} queries, dim={len(next(iter(vectors.values())))}")

    # Compute cosine for every labeled pair.
    print("\nComputing cosine similarities for all pairs…")
    for pair in pairs:
        a = vectors[pair["anchor"]]
        b = vectors[pair["candidate"]]
        # cosine_similarity from app.rules takes (matrix, query); pass single-row matrix.
        sim = float(cosine_similarity(a.reshape(1, -1), b)[0])
        pair["cosine"] = sim

    # Per-pair diagnostic dump grouped by topic.
    print("\nPer-pair cosine similarity (grouped by anchor):")
    by_anchor: dict[str, list[dict]] = {}
    for p in pairs:
        by_anchor.setdefault(p["anchor"], []).append(p)
    for anchor, ps in by_anchor.items():
        print(f"\n  anchor: {anchor!r}")
        for p in sorted(ps, key=lambda x: -x["cosine"]):
            tag = "P" if p["label"] == "paraphrase" else "D"
            print(f"    [{tag}] cos={p['cosine']:.4f}  :: {p['candidate'][:65]}")

    # Separation diagnostics — informative even before the sweep.
    paraphrase_cosines = [p["cosine"] for p in pairs if p["label"] == "paraphrase"]
    different_cosines = [p["cosine"] for p in pairs if p["label"] == "different"]
    print("\nSeparation:")
    print(
        f"  paraphrase: n={len(paraphrase_cosines):2d}  "
        f"min={min(paraphrase_cosines):.4f} max={max(paraphrase_cosines):.4f} "
        f"mean={float(np.mean(paraphrase_cosines)):.4f}"
    )
    print(
        f"  different:  n={len(different_cosines):2d}  "
        f"min={min(different_cosines):.4f} max={max(different_cosines):.4f} "
        f"mean={float(np.mean(different_cosines)):.4f}"
    )
    overlap_lo = max(min(paraphrase_cosines), min(different_cosines))
    overlap_hi = min(max(paraphrase_cosines), max(different_cosines))
    if overlap_lo < overlap_hi:
        print(f"  overlap band: [{overlap_lo:.4f}, {overlap_hi:.4f}] — both classes coexist here")
    else:
        print(f"  CLEAN SEPARATION: paraphrases all > {min(paraphrase_cosines):.4f}, differents all < {max(different_cosines):.4f}")

    # Sweep.
    print("\nThreshold sweep (paraphrase = positive, different = negative):")
    print(
        f"{'thr':>6} | {'TP':>3} {'FN':>3} {'FP':>3} {'TN':>3} | "
        f"{'prec':>6} | {'recall':>7} | {'F1':>6}"
    )
    print("-" * 60)

    best = None  # (thr, f1, precision)
    for thr in CANDIDATE_THRESHOLDS:
        tp = sum(1 for p in pairs if p["label"] == "paraphrase" and p["cosine"] >= thr)
        fn = paraphrase_count - tp
        fp = sum(1 for p in pairs if p["label"] == "different" and p["cosine"] >= thr)
        tn = different_count - fp
        precision = tp / (tp + fp) if (tp + fp) else 0.0
        recall = tp / (tp + fn) if (tp + fn) else 0.0
        f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0
        print(
            f"{thr:>6.2f} | {tp:>3} {fn:>3} {fp:>3} {tn:>3} | "
            f"{precision:>6.3f} | {recall:>7.3f} | {f1:>6.3f}"
        )
        # Tie-breaker: PRECISION (false reuse is worse than missed reuse — see
        # module docstring). Prefer higher precision when F1 is tied.
        if best is None or (f1, precision) > (best[1], best[2]):
            best = (thr, f1, precision)

    print()
    assert best is not None
    print(
        f"Maximizer: threshold={best[0]:.2f}  F1={best[1]:.3f}  precision={best[2]:.3f}"
    )
    print(
        "\nReminder: ties broken by precision (a false-reuse serves a stale "
        "answer that's a different question — worse than a missed reuse where "
        "the LLM just re-composes from fresh)."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
