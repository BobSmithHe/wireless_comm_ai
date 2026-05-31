"""
RAG evaluator — run test cases, compare configurations, produce report.
"""
from __future__ import annotations

import time
from statistics import mean
from typing import Any

from .test_cases import TEST_CASES
from .metrics import (
    recall_at_k, precision_at_k, mrr, ndcg_at_k,
    evaluate_faithfulness, evaluate_fact_coverage,
    format_report, build_report,
)


class RAGEvaluator:
    def __init__(self, llm_client, kb):
        self.llm = llm_client
        self.kb = kb

    # ------------------------------------------------------------------
    # Retrieval evaluation
    # ------------------------------------------------------------------

    async def eval_retrieval(
        self, k: int = 5, mode: str = "hybrid", rerank: bool = True,
    ) -> dict[str, float]:
        """Evaluate retrieval quality across all test cases."""
        recalls, precisions, mrrs, ndcgs = [], [], [], []

        for tc in TEST_CASES:
            if tc["category"] == "chat" or not tc["relevant_sources"]:
                continue

            results = await self.kb.search(
                query=tc["query"], top_k=k, mode=mode, rerank=rerank,
                filters={"category": tc.get("category")} if tc.get("category") else None,
            )
            sources = [r.source for r in results]
            relevant = set(tc["relevant_sources"])

            recalls.append(recall_at_k(relevant, sources, k))
            precisions.append(precision_at_k(relevant, sources, k))
            mrrs.append(mrr(relevant, sources))
            ndcgs.append(ndcg_at_k(relevant, sources, k))

        return {
            f"recall@{k}": mean(recalls) if recalls else 0,
            f"precision@{k}": mean(precisions) if precisions else 0,
            "MRR": mean(mrrs) if mrrs else 0,
            f"NDCG@{k}": mean(ndcgs) if ndcgs else 0,
            "num_cases": len(recalls),
        }

    # ------------------------------------------------------------------
    # Generation evaluation
    # ------------------------------------------------------------------

    async def eval_generation(self, max_cases: int = 5) -> dict[str, float]:
        """LLM-as-judge: faithfulness + fact coverage on a sample."""
        faithfulness_scores = []
        coverage_scores = []

        for tc in TEST_CASES[:max_cases]:
            if not tc["expected_facts"]:
                continue

            # Retrieve context
            results = await self.kb.search(query=tc["query"], top_k=3)
            context = "\n".join(r.content[:500] for r in results)

            # Generate answer
            mock_answer = context[:800]  # simplified — in prod, call LLM here

            faith = await evaluate_faithfulness(
                self.llm, tc["query"], context, mock_answer,
            )
            faithfulness_scores.append(1.0 if faith else 0.0)

            cov = await evaluate_fact_coverage(
                self.llm, tc["query"], mock_answer, tc["expected_facts"],
            )
            coverage_scores.append(cov)

        return {
            "faithfulness": mean(faithfulness_scores) if faithfulness_scores else 0,
            "fact_coverage": mean(coverage_scores) if coverage_scores else 0,
            "num_cases": len(faithfulness_scores),
        }

    # ------------------------------------------------------------------
    # A/B comparison
    # ------------------------------------------------------------------

    async def compare_configs(
        self, k: int = 5,
    ) -> list[dict]:
        """Compare retrieval across different search modes."""
        configs = [
            {"name": "vector_only", "mode": "vector", "rerank": False},
            {"name": "hybrid_no_rerank", "mode": "hybrid", "rerank": False},
            {"name": "hybrid_with_rerank", "mode": "hybrid", "rerank": True},
        ]

        reports = []
        for cfg in configs:
            t0 = time.time()
            metrics = await self.eval_retrieval(k=k, mode=cfg["mode"], rerank=cfg["rerank"])
            elapsed = time.time() - t0
            metrics["latency_ms"] = round(elapsed / max(metrics["num_cases"], 1) * 1000, 1)
            report = build_report(cfg["name"], metrics, {})
            reports.append(report)

        return reports

    # ------------------------------------------------------------------
    # Report
    # ------------------------------------------------------------------

    async def run_full_report(self, k: int = 5, gen_samples: int = 3) -> str:
        """Run both retrieval and generation evaluation, format as markdown."""
        parts = ["# RAG Evaluation Report", ""]

        # Retrieval comparison
        parts.append("## Retrieval Comparison (k=5)")
        parts.append("")
        parts.append("| Config | Recall@5 | Precision@5 | MRR | NDCG@5 | Latency/query |")
        parts.append("|--------|----------|-------------|-----|--------|---------------|")

        configs = [
            ("vector_only", "vector", False),
            ("hybrid", "hybrid", False),
            ("hybrid + rerank", "hybrid", True),
        ]

        for name, mode, rerank in configs:
            ret = await self.eval_retrieval(k=k, mode=mode, rerank=rerank)
            parts.append(
                f"| {name} | {ret[f'recall@{k}']:.3f} | {ret[f'precision@{k}']:.3f} "
                f"| {ret['MRR']:.3f} | {ret[f'NDCG@{k}']:.3f} | {ret.get('latency_ms', '-')} |"
            )

        # Generation evaluation
        parts.append("")
        parts.append("## Generation Quality (LLM-as-Judge)")
        parts.append("")
        gen = await self.eval_generation(max_cases=gen_samples)
        parts.append(f"| Metric | Value |")
        parts.append(f"|--------|-------|")
        parts.append(f"| Faithfulness | {gen['faithfulness']:.3f} |")
        parts.append(f"| Fact Coverage | {gen['fact_coverage']:.3f} |")
        parts.append(f"| Samples | {gen['num_cases']} |")

        # Details
        parts.append("")
        parts.append("## Test Cases")
        parts.append("")
        for tc in TEST_CASES:
            parts.append(f"- **{tc['id']}**: {tc['query'][:80]}")
            parts.append(f"  Sources: {tc['relevant_sources']}")
            parts.append(f"  Facts: {tc['expected_facts']}")

        return "\n".join(parts)
