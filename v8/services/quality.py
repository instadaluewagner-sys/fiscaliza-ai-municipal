from v8.core.models import AnalysisResult

def validate_analysis_integrity(a: AnalysisResult) -> list[str]:
    warnings: list[str] = []
    doc_ids = [d.id for d in a.documents]
    doc_set = set(doc_ids)

    if len(doc_ids) != len(doc_set):
        warnings.append("IDs de documentos duplicados foram detectados.")

    for ev in a.evidence:
        if ev.document_id not in doc_set:
            warnings.append(f"Evidência referencia documento inexistente: {ev.document_id}.")
        doc = next((d for d in a.documents if d.id == ev.document_id), None)
        if doc and ev.page not in doc.pages:
            warnings.append(
                f"Evidência {ev.document_id} aponta p. {ev.page}, fora das páginas segmentadas da peça."
            )

    for event in a.timeline:
        if event.document_id not in doc_set:
            warnings.append(f"Cronologia referencia documento inexistente: {event.document_id}.")
        doc = next((d for d in a.documents if d.id == event.document_id), None)
        if doc and event.page not in doc.pages:
            warnings.append(
                f"Cronologia {event.document_id} aponta p. {event.page}, fora das páginas segmentadas."
            )

    rows = {x.key: x for x in a.checklist}
    for row in a.checklist:
        if row.status == "not_applicable" and (row.document_ids or row.pages):
            warnings.append(
                f"Item não aplicável mantém fonte documental indevida: {row.label}."
            )
        if row.status == "located" and not row.document_ids:
            warnings.append(
                f"Item marcado como localizado sem DOC-ID associado: {row.label}."
            )
        for document_id in row.document_ids:
            if document_id not in doc_set:
                warnings.append(
                    f"Checklist {row.label} referencia documento inexistente: {document_id}."
                )

    for pending in a.pending_items:
        if pending.kind == "missing":
            row = rows.get(pending.key)
            if row and row.status != "not_found":
                warnings.append(
                    f"Pendência de ausência não corresponde a item 'not_found': {pending.label}."
                )
        elif pending.kind == "review":
            row = rows.get(pending.key)
            if row and row.status != "inconclusive":
                warnings.append(
                    f"Item de conferência não corresponde a estado inconclusivo: {pending.label}."
                )

    return warnings
