import argparse
import json
from pathlib import Path

from v8.modules.penalizacao import analyze_penalizacao
from v8.services.document_segmenter import segment_documents
from v8.services.pdf_reader import extract_pages


def overlaps(actual_pages: set[int], start: int, end: int) -> bool:
    return bool(actual_pages.intersection(set(range(start, end + 1))))


def evaluate(pdf_path: Path, benchmark_path: Path) -> dict:
    benchmark = json.loads(benchmark_path.read_text(encoding="utf-8"))
    pages, ocr_count = extract_pages(pdf_path.read_bytes(), pdf_path.name)
    documents = segment_documents(pages)
    analysis = analyze_penalizacao(documents)

    expected_docs = benchmark.get("documents", [])
    doc_results = []
    expected_matched = 0

    for exp in expected_docs:
        candidates = [d for d in documents if d.type == exp["type"]]
        matched = [
            d for d in candidates
            if overlaps(set(d.pages), int(exp["page_start"]), int(exp["page_end"]))
        ]
        if matched:
            expected_matched += 1
        doc_results.append({
            "type": exp["type"],
            "expected_pages": [exp["page_start"], exp["page_end"]],
            "matched": bool(matched),
            "actual": [
                {"id": d.id, "pages": d.pages, "title": d.title[:120]}
                for d in matched
            ],
        })

    expected_types = {x["type"] for x in expected_docs}
    actual_relevant = [d for d in documents if d.type in expected_types]
    true_positive_actual = 0
    false_positives = []

    for doc in actual_relevant:
        matches_any = any(
            exp["type"] == doc.type
            and overlaps(set(doc.pages), int(exp["page_start"]), int(exp["page_end"]))
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
        "false_positive_count": len(false_positives),
        "false_positives": false_positives,
        "expected_stage": expected_stage,
        "actual_stage": analysis.stage.key,
        "stage_match": stage_ok,
        "suggested_draft": analysis.stage.suggested_draft,
        "documents": doc_results,
    }


def main():
    parser = argparse.ArgumentParser(description="Avalia um PDF contra gabarito da V8.")
    parser.add_argument("pdf")
    parser.add_argument("benchmark")
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
    args = parser.parse_args()

    result = evaluate(Path(args.pdf), Path(args.benchmark))
    print(json.dumps(result, ensure_ascii=False, indent=2))

    if args.fail_below_recall is not None and result["document_recall"] is not None:
        if result["document_recall"] < args.fail_below_recall:
            raise SystemExit(2)
    if args.fail_below_precision is not None and result["document_precision"] is not None:
        if result["document_precision"] < args.fail_below_precision:
            raise SystemExit(3)


if __name__ == "__main__":
    main()
