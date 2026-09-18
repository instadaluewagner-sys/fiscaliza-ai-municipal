import argparse
import json
from pathlib import Path

from v8.modules.penalizacao import analyze_penalizacao
from v8.services.document_segmenter import segment_documents
from v8.services.pdf_reader import extract_pages


def expected_pages(exp: dict) -> set[int]:
    if exp.get("content_pages"):
        return {int(x) for x in exp["content_pages"]}
    return set(range(int(exp["page_start"]), int(exp["page_end"]) + 1))


def page_iou(actual: set[int], expected: set[int]) -> float:
    union = actual | expected
    if not union:
        return 0.0
    return len(actual & expected) / len(union)


def evaluate(pdf_path: Path, benchmark_path: Path) -> dict:
    benchmark = json.loads(benchmark_path.read_text(encoding="utf-8"))
    pages, ocr_count = extract_pages(pdf_path.read_bytes(), pdf_path.name)
    documents = segment_documents(pages)
    analysis = analyze_penalizacao(documents)

    expected_docs = benchmark.get("documents", [])
    doc_results = []
    expected_matched = 0
    boundary_scores = []
    exact_boundaries = 0

    for exp in expected_docs:
        exp_pages = expected_pages(exp)
        candidates = [d for d in documents if d.type == exp["type"]]
        ranked = sorted(
            ((page_iou(set(d.pages), exp_pages), d) for d in candidates),
            key=lambda x: x[0],
            reverse=True,
        )
        score, best = ranked[0] if ranked else (0.0, None)
        matched = best is not None and score > 0

        if matched:
            expected_matched += 1
            boundary_scores.append(score)
            if set(best.pages) == exp_pages:
                exact_boundaries += 1

        doc_results.append({
            "type": exp["type"],
            "expected_pages": sorted(exp_pages),
            "matched": matched,
            "boundary_iou": score if matched else 0.0,
            "actual": (
                {
                    "id": best.id,
                    "pages": best.pages,
                    "title": best.title[:120],
                }
                if best is not None
                else None
            ),
        })

    expected_types = {x["type"] for x in expected_docs}
    actual_relevant = [d for d in documents if d.type in expected_types]
    true_positive_actual = 0
    false_positives = []

    for doc in actual_relevant:
        matches_any = any(
            exp["type"] == doc.type
            and page_iou(set(doc.pages), expected_pages(exp)) > 0
            for exp in expected_docs
        )
        if matches_any:
            true_positive_actual += 1
        else:
            false_positives.append({
                "id": doc.id,
                "type": doc.type,
                "pages": doc.pages,
                "title": doc.title[:120],
            })

    recall = (expected_matched / len(expected_docs)) if expected_docs else None
    precision = (true_positive_actual / len(actual_relevant)) if actual_relevant else None
    boundary_mean_iou = (
        sum(boundary_scores) / len(boundary_scores)
        if boundary_scores
        else None
    )

    expected_stage = benchmark.get("expected_stage")
    stage_ok = analysis.stage.key == expected_stage if expected_stage else None

    return {
        "case_id": benchmark.get("case_id"),
        "pages": len(pages),
        "ocr_pages": ocr_count,
        "documents_detected": len(documents),
        "expected_document_matches": expected_matched,
        "expected_document_total": len(expected_docs),
        "document_recall": recall,
        "document_precision": precision,
        "boundary_mean_iou": boundary_mean_iou,
        "exact_boundary_count": exact_boundaries,
        "false_positive_count": len(false_positives),
        "false_positives": false_positives,
        "expected_stage": expected_stage,
        "actual_stage": analysis.stage.key,
        "stage_match": stage_ok,
        "suggested_draft": analysis.stage.suggested_draft,
        "integrity_warnings": analysis.warnings,
        "documents": doc_results,
    }


def main():
    parser = argparse.ArgumentParser(description="Avalia um PDF contra gabarito da V8.")
    parser.add_argument("pdf")
    parser.add_argument("benchmark")
    parser.add_argument(
        "--output",
        help="Grava o JSON limpo neste arquivo, além de imprimi-lo no stdout.",
    )
    parser.add_argument(
        "--fail-below-recall",
        type=float,
        default=None,
        help="Retorna código 2 se o recall documental ficar abaixo deste limite.",
    )
    parser.add_argument(
        "--fail-below-precision",
        type=float,
        default=None,
        help="Retorna código 3 se a precisão documental ficar abaixo deste limite.",
    )
    parser.add_argument(
        "--fail-below-boundary",
        type=float,
        default=None,
        help="Retorna código 4 se o IoU médio de fronteiras ficar abaixo deste limite.",
    )
    args = parser.parse_args()

    result = evaluate(Path(args.pdf), Path(args.benchmark))
    payload = json.dumps(result, ensure_ascii=False, indent=2)
    print(payload)

    if args.output:
        Path(args.output).write_text(payload + "\n", encoding="utf-8")

    if args.fail_below_recall is not None and result["document_recall"] is not None:
        if result["document_recall"] < args.fail_below_recall:
            raise SystemExit(2)
    if args.fail_below_precision is not None and result["document_precision"] is not None:
        if result["document_precision"] < args.fail_below_precision:
            raise SystemExit(3)
    if args.fail_below_boundary is not None and result["boundary_mean_iou"] is not None:
        if result["boundary_mean_iou"] < args.fail_below_boundary:
            raise SystemExit(4)


if __name__ == "__main__":
    main()
