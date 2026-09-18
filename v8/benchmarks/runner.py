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
    for exp in expected_docs:
        candidates = [d for d in documents if d.type == exp["type"]]
        matched = [
            d for d in candidates
            if overlaps(set(d.pages), int(exp["page_start"]), int(exp["page_end"]))
        ]
        doc_results.append({
            "type": exp["type"],
            "expected_pages": [exp["page_start"], exp["page_end"]],
            "matched": bool(matched),
            "actual": [
                {"id": d.id, "pages": d.pages, "title": d.title[:120]}
                for d in matched
            ],
        })

    expected_stage = benchmark.get("expected_stage")
    stage_ok = analysis.stage.key == expected_stage if expected_stage else None
    matched_count = sum(1 for x in doc_results if x["matched"])
    return {
        "case_id": benchmark.get("case_id"),
        "pages": len(pages),
        "ocr_pages": ocr_count,
        "documents_detected": len(documents),
        "document_matches": matched_count,
        "document_total": len(doc_results),
        "document_accuracy": (matched_count / len(doc_results)) if doc_results else None,
        "expected_stage": expected_stage,
        "actual_stage": analysis.stage.key,
        "stage_match": stage_ok,
        "documents": doc_results,
    }


def main():
    parser = argparse.ArgumentParser(description="Avalia um PDF contra gabarito da V8.")
    parser.add_argument("pdf")
    parser.add_argument("benchmark")
    args = parser.parse_args()
    result = evaluate(Path(args.pdf), Path(args.benchmark))
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
