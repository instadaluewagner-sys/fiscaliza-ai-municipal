import io
from datetime import datetime, timezone
from html import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
    PageBreak,
)

from v8.core.models import AnalysisResult


STATUS_LABELS = {
    "located": "Localizado",
    "not_found": "Nao localizado",
    "not_applicable": "Nao aplicavel",
    "inconclusive": "Inconclusivo",
}

KIND_LABELS = {
    "missing": "Pendencia",
    "review": "Conferencia",
    "next_step": "Proximo passo",
}


def _safe(value) -> str:
    if value is None or value == "":
        return "Nao identificado com seguranca"
    if isinstance(value, list):
        return ", ".join(str(x) for x in value) if value else "Nao identificado com seguranca"
    return str(value)


def _ascii_dash(value: str) -> str:
    return (
        str(value or "")
        .replace("\u2014", "-")
        .replace("\u2013", "-")
        .replace("\u2212", "-")
    )


def build_audit_payload(
    analysis_id: str,
    analysis: AnalysisResult,
    source_files: list[dict],
    page_count: int,
    ocr_pages: int | None = None,
) -> dict:
    return {
        "schema": "fiscaliza-ai-v8-audit-report/1",
        "analysis_id": analysis_id,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "module": analysis.module,
        "source_files": [
            {
                "filename": item.get("filename"),
                "sha256": item.get("sha256"),
                "size_bytes": item.get("size_bytes"),
            }
            for item in source_files
        ],
        "page_count": page_count,
        "ocr_pages": ocr_pages,
        "analysis": analysis.model_dump(),
    }


def build_pdf_report(
    analysis_id: str,
    analysis: AnalysisResult,
    source_files: list[dict],
    page_count: int,
    ocr_pages: int | None = None,
) -> bytes:
    buffer = io.BytesIO()

    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=16 * mm,
        leftMargin=16 * mm,
        topMargin=16 * mm,
        bottomMargin=16 * mm,
        title="Fiscaliza.AI V8 - Relatorio Auditavel",
        author="Fiscaliza.AI Municipal",
    )

    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(
        name="ReportTitle",
        parent=styles["Title"],
        fontName="Helvetica-Bold",
        fontSize=18,
        leading=22,
        textColor=colors.HexColor("#0F2F49"),
        alignment=TA_CENTER,
        spaceAfter=8,
    ))
    styles.add(ParagraphStyle(
        name="Section",
        parent=styles["Heading2"],
        fontName="Helvetica-Bold",
        fontSize=11,
        leading=14,
        textColor=colors.HexColor("#0F2F49"),
        spaceBefore=10,
        spaceAfter=6,
    ))
    styles.add(ParagraphStyle(
        name="Small",
        parent=styles["BodyText"],
        fontName="Helvetica",
        fontSize=7.5,
        leading=10,
        textColor=colors.HexColor("#5D7182"),
    ))
    styles.add(ParagraphStyle(
        name="BodySmall",
        parent=styles["BodyText"],
        fontName="Helvetica",
        fontSize=8.5,
        leading=11.5,
        textColor=colors.HexColor("#20384A"),
    ))

    story = [
        Paragraph("Fiscaliza.AI Municipal", styles["ReportTitle"]),
        Paragraph("Relatorio auditavel de analise processual - V8", styles["Heading3"]),
        Paragraph(
            "Analise assistida. A revisao humana permanece obrigatoria antes de qualquer ato, decisao ou expedicao de documento.",
            styles["Small"],
        ),
        Spacer(1, 7),
    ]

    p = analysis.profile
    process_number = p.process_number or p.origin_process or "Nao identificado"
    header_data = [
        ["Analise", analysis_id],
        ["Modulo", analysis.module],
        ["Processo", process_number],
        ["Estagio", analysis.stage.label],
        ["Paginas", str(page_count)],
        ["OCR", str(ocr_pages or 0)],
    ]
    header_table = Table(header_data, colWidths=[42 * mm, 130 * mm])
    header_table.setStyle(TableStyle([
        ("FONTNAME", (0,0), (0,-1), "Helvetica-Bold"),
        ("FONTNAME", (1,0), (1,-1), "Helvetica"),
        ("FONTSIZE", (0,0), (-1,-1), 8.5),
        ("TEXTCOLOR", (0,0), (0,-1), colors.HexColor("#0F2F49")),
        ("GRID", (0,0), (-1,-1), 0.35, colors.HexColor("#D7E1E9")),
        ("BACKGROUND", (0,0), (0,-1), colors.HexColor("#F3F7F9")),
        ("VALIGN", (0,0), (-1,-1), "TOP"),
        ("LEFTPADDING", (0,0), (-1,-1), 5),
        ("RIGHTPADDING", (0,0), (-1,-1), 5),
        ("TOPPADDING", (0,0), (-1,-1), 4),
        ("BOTTOMPADDING", (0,0), (-1,-1), 4),
    ]))
    story += [header_table, Spacer(1, 8)]

    story.append(Paragraph("Fontes digitais analisadas", styles["Section"]))
    if source_files:
        source_rows = [["Arquivo", "SHA-256", "Tamanho"]]
        for item in source_files:
            source_rows.append([
                Paragraph(escape(_ascii_dash(item.get("filename") or "")), styles["BodySmall"]),
                Paragraph(escape(item.get("sha256") or "nao calculado"), styles["Small"]),
                f"{item.get('size_bytes') or 0} bytes",
            ])
        tbl = Table(source_rows, colWidths=[58*mm, 83*mm, 31*mm], repeatRows=1)
        tbl.setStyle(TableStyle([
            ("BACKGROUND", (0,0), (-1,0), colors.HexColor("#0F2F49")),
            ("TEXTCOLOR", (0,0), (-1,0), colors.white),
            ("FONTNAME", (0,0), (-1,0), "Helvetica-Bold"),
            ("FONTSIZE", (0,0), (-1,-1), 7.2),
            ("GRID", (0,0), (-1,-1), 0.3, colors.HexColor("#D7E1E9")),
            ("VALIGN", (0,0), (-1,-1), "TOP"),
            ("LEFTPADDING", (0,0), (-1,-1), 4),
            ("RIGHTPADDING", (0,0), (-1,-1), 4),
            ("TOPPADDING", (0,0), (-1,-1), 4),
            ("BOTTOMPADDING", (0,0), (-1,-1), 4),
        ]))
        story.append(tbl)
    else:
        story.append(Paragraph("Nenhuma fonte digital associada.", styles["BodySmall"]))

    story.append(Paragraph("Situacao processual", styles["Section"]))
    story.append(Paragraph(f"<b>{escape(_ascii_dash(analysis.stage.label))}</b>", styles["BodySmall"]))
    story.append(Paragraph(escape(_ascii_dash(analysis.stage.rationale)), styles["BodySmall"]))
    story.append(Spacer(1, 3))
    story.append(Paragraph(
        "<b>Proximo ato:</b> " + escape(_ascii_dash(analysis.stage.next_action)),
        styles["BodySmall"],
    ))
    story.append(Paragraph(
        "<b>Minuta compativel:</b> " + escape(_ascii_dash(analysis.stage.suggested_draft)),
        styles["BodySmall"],
    ))
    if analysis.stage.sources:
        refs = ", ".join(
            f"{ref.document_id or 'DOC?'} p. {ref.page}"
            for ref in analysis.stage.sources
        )
        story.append(Paragraph("<b>Fontes do estagio:</b> " + escape(refs), styles["Small"]))

    story.append(Paragraph("Identificacao e contratacao", styles["Section"]))
    profile_rows = [["Campo", "Valor", "Fonte"]]
    fields = [
        ("Processo de penalizacao", "process_number", p.process_number),
        ("Processo/protocolo de origem", "origin_process", p.origin_process),
        ("Pregao", "pregao", p.pregao),
        ("Ata de Registro de Precos", "ata", p.ata),
        ("Contrato", "contrato", p.contrato),
        ("Nota(s) de Empenho", "empenhos", p.empenhos),
        ("Empresa/interessado", "company", p.company),
        ("CNPJ", "cnpj", p.cnpj),
        ("Objeto", "object_description", p.object_description),
        ("Quantidade", "quantity", p.quantity),
    ]
    for label, key, value in fields:
        ref = p.sources.get(key)
        source = f"{ref.document_id} p. {ref.page}" if ref and ref.document_id else "sem fonte segura"
        conflict = p.conflicts.get(key, [])
        rendered = _safe(value)
        if conflict:
            rendered += " | Divergencia: " + "; ".join(conflict)
        profile_rows.append([
            Paragraph(escape(_ascii_dash(label)), styles["Small"]),
            Paragraph(escape(_ascii_dash(rendered)), styles["BodySmall"]),
            Paragraph(escape(source), styles["Small"]),
        ])
    tbl = Table(profile_rows, colWidths=[39*mm, 96*mm, 37*mm], repeatRows=1)
    tbl.setStyle(TableStyle([
        ("BACKGROUND", (0,0), (-1,0), colors.HexColor("#0F2F49")),
        ("TEXTCOLOR", (0,0), (-1,0), colors.white),
        ("FONTNAME", (0,0), (-1,0), "Helvetica-Bold"),
        ("FONTSIZE", (0,0), (-1,-1), 7.3),
        ("GRID", (0,0), (-1,-1), 0.3, colors.HexColor("#D7E1E9")),
        ("VALIGN", (0,0), (-1,-1), "TOP"),
        ("LEFTPADDING", (0,0), (-1,-1), 4),
        ("RIGHTPADDING", (0,0), (-1,-1), 4),
        ("TOPPADDING", (0,0), (-1,-1), 4),
        ("BOTTOMPADDING", (0,0), (-1,-1), 4),
    ]))
    story.append(tbl)

    story.append(Paragraph("Pendencias e providencias", styles["Section"]))
    if analysis.pending_items:
        for item in analysis.pending_items:
            story.append(Paragraph(
                f"<b>{escape(KIND_LABELS.get(item.kind, item.kind))} - {escape(_ascii_dash(item.label))}</b>: "
                + escape(_ascii_dash(item.reason)),
                styles["BodySmall"],
            ))
    else:
        story.append(Paragraph("Nenhuma pendencia atual identificada.", styles["BodySmall"]))

    story.append(Paragraph("Evidencias prioritarias", styles["Section"]))
    if analysis.evidence:
        evidence_rows = [["Categoria", "Fato / trecho", "Fonte"]]
        for ev in analysis.evidence:
            text = f"{ev.fact}. Trecho: {ev.excerpt}"
            evidence_rows.append([
                ev.category,
                Paragraph(escape(_ascii_dash(text)), styles["BodySmall"]),
                f"{ev.document_id} p. {ev.page}",
            ])
        tbl = Table(evidence_rows, colWidths=[27*mm, 111*mm, 34*mm], repeatRows=1)
        tbl.setStyle(TableStyle([
            ("BACKGROUND", (0,0), (-1,0), colors.HexColor("#0F2F49")),
            ("TEXTCOLOR", (0,0), (-1,0), colors.white),
            ("FONTNAME", (0,0), (-1,0), "Helvetica-Bold"),
            ("FONTSIZE", (0,0), (-1,-1), 7),
            ("GRID", (0,0), (-1,-1), 0.3, colors.HexColor("#D7E1E9")),
            ("VALIGN", (0,0), (-1,-1), "TOP"),
            ("LEFTPADDING", (0,0), (-1,-1), 4),
            ("RIGHTPADDING", (0,0), (-1,-1), 4),
            ("TOPPADDING", (0,0), (-1,-1), 4),
            ("BOTTOMPADDING", (0,0), (-1,-1), 4),
        ]))
        story.append(tbl)
    else:
        story.append(Paragraph("Nenhuma evidencia prioritaria consolidada.", styles["BodySmall"]))

    story.append(PageBreak())
    story.append(Paragraph("Cronologia essencial", styles["Section"]))
    if analysis.timeline:
        timeline_rows = [["Seq.", "Data", "Evento", "Fonte"]]
        for ev in analysis.timeline:
            timeline_rows.append([
                str(ev.sequence),
                ev.date or "nao identificada",
                Paragraph(escape(_ascii_dash(ev.label)), styles["BodySmall"]),
                f"{ev.document_id} p. {ev.page}",
            ])
        tbl = Table(timeline_rows, colWidths=[13*mm, 28*mm, 96*mm, 35*mm], repeatRows=1)
        tbl.setStyle(TableStyle([
            ("BACKGROUND", (0,0), (-1,0), colors.HexColor("#0F2F49")),
            ("TEXTCOLOR", (0,0), (-1,0), colors.white),
            ("FONTNAME", (0,0), (-1,0), "Helvetica-Bold"),
            ("FONTSIZE", (0,0), (-1,-1), 7.2),
            ("GRID", (0,0), (-1,-1), 0.3, colors.HexColor("#D7E1E9")),
            ("VALIGN", (0,0), (-1,-1), "TOP"),
            ("LEFTPADDING", (0,0), (-1,-1), 4),
            ("RIGHTPADDING", (0,0), (-1,-1), 4),
            ("TOPPADDING", (0,0), (-1,-1), 4),
            ("BOTTOMPADDING", (0,0), (-1,-1), 4),
        ]))
        story.append(tbl)
    else:
        story.append(Paragraph("Nenhum marco cronologico consolidado.", styles["BodySmall"]))

    story.append(Paragraph("Checklist de aplicabilidade", styles["Section"]))
    check_rows = [["Item", "Estado", "Fundamentacao", "Fonte"]]
    for row in analysis.checklist:
        refs = ", ".join(
            f"{doc_id}" for doc_id in row.document_ids
        )
        if row.pages:
            refs += (" " if refs else "") + "p. " + ", ".join(str(x) for x in row.pages)
        check_rows.append([
            Paragraph(escape(_ascii_dash(row.label)), styles["Small"]),
            STATUS_LABELS.get(row.status, row.status),
            Paragraph(escape(_ascii_dash(row.reason)), styles["BodySmall"]),
            Paragraph(escape(refs or "-"), styles["Small"]),
        ])
    tbl = Table(check_rows, colWidths=[42*mm, 27*mm, 79*mm, 24*mm], repeatRows=1)
    tbl.setStyle(TableStyle([
        ("BACKGROUND", (0,0), (-1,0), colors.HexColor("#0F2F49")),
        ("TEXTCOLOR", (0,0), (-1,0), colors.white),
        ("FONTNAME", (0,0), (-1,0), "Helvetica-Bold"),
        ("FONTSIZE", (0,0), (-1,-1), 6.8),
        ("GRID", (0,0), (-1,-1), 0.3, colors.HexColor("#D7E1E9")),
        ("VALIGN", (0,0), (-1,-1), "TOP"),
        ("LEFTPADDING", (0,0), (-1,-1), 3),
        ("RIGHTPADDING", (0,0), (-1,-1), 3),
        ("TOPPADDING", (0,0), (-1,-1), 3),
        ("BOTTOMPADDING", (0,0), (-1,-1), 3),
    ]))
    story.append(tbl)

    if analysis.warnings:
        story.append(Paragraph("Alertas de integridade", styles["Section"]))
        for warning in analysis.warnings:
            story.append(Paragraph(escape(_ascii_dash(warning)), styles["BodySmall"]))

    story += [
        Spacer(1, 8),
        Paragraph(
            "Rastreabilidade: cada conclusao relevante deste relatorio deve ser conferida no documento e pagina indicados. "
            "O relatorio nao substitui a leitura dos autos, a analise juridica, a competencia da autoridade nem a revisao humana.",
            styles["Small"],
        ),
    ]

    doc.build(story)
    return buffer.getvalue()
