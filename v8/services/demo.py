import io

from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas


PAGES = [
    (
        "PROCESSO ADMINISTRATIVO DE PENALIZAÇÃO Nº 2-0001/2026",
        [
            "Órgão: MUNICÍPIO MODELO",
            "Empresa: EMPRESA MODELO LTDA",
            "CNPJ: 12.345.678/0001-95",
            "Processo/Protocolo de origem: 1-4321/2026",
            "Fica instaurado o presente procedimento para apuração de possível inexecução contratual,",
            "assegurados o contraditório e a ampla defesa, sem antecipação de responsabilidade."
        ],
    ),
    (
        "PREGÃO ELETRÔNICO Nº 071/2026",
        [
            "Objeto: aquisição de kits de higiene bucal para atendimento das unidades municipais.",
            "Empresa vencedora: EMPRESA MODELO LTDA",
            "CNPJ: 12.345.678/0001-95",
        ],
    ),
    (
        "ATA DE REGISTRO DE PREÇOS Nº 083/2026",
        [
            "Pregão Eletrônico nº 071/2026",
            "Empresa: EMPRESA MODELO LTDA",
            "CNPJ: 12.345.678/0001-95",
            "Objeto: fornecimento de 500 kits de higiene bucal.",
        ],
    ),
    (
        "CONTRATO ADMINISTRATIVO Nº 140/2026",
        [
            "Contratada: EMPRESA MODELO LTDA",
            "CNPJ: 12.345.678/0001-95",
            "Pregão Eletrônico nº 071/2026",
            "Ata de Registro de Preços nº 083/2026",
            "Objeto do Contrato: fornecimento de 500 kits de higiene bucal para unidades municipais.",
            "Quantidade total: 500 kits de higiene bucal.",
            "Prazo de entrega: conforme instrumento convocatório e ordem de fornecimento."
        ],
    ),
    (
        "NOTA DE EMPENHO Nº 1450/2026",
        [
            "Contrato nº 140/2026",
            "Empresa: EMPRESA MODELO LTDA",
            "Objeto: 500 kits de higiene bucal.",
        ],
    ),
    (
        "ORDEM DE FORNECIMENTO Nº 032/2026",
        [
            "Contrato nº 140/2026",
            "Nota de Empenho nº 1450/2026",
            "Autoriza-se o fornecimento de 500 kits de higiene bucal.",
        ],
    ),
    (
        "RELATÓRIO TÉCNICO Nº 009/2026",
        [
            "Unidade demandante: Secretaria Municipal de Saúde.",
            "Após conferência do prazo e dos registros de execução, constatou-se que a empresa",
            "não realizou nenhuma entrega referente aos 500 kits de higiene bucal contratados.",
            "A ocorrência foi encaminhada para apuração administrativa."
        ],
    ),
    (
        "NOTIFICAÇÃO DE INSTAURAÇÃO Nº 016/2026",
        [
            "Processo Administrativo de Penalização nº 2-0001/2026",
            "Notificado: EMPRESA MODELO LTDA",
            "CNPJ: 12.345.678/0001-95",
            "A empresa fica NOTIFICADA da instauração e intimada a apresentar defesa administrativa",
            "no prazo de 10 (dez) dias úteis, conforme regra fictícia adotada exclusivamente neste processo modelo.",
            "A presente notificação não representa aplicação antecipada de penalidade."
        ],
    ),
    (
        "INTIMAÇÃO Nº 021/2026",
        [
            "Processo Administrativo de Penalização nº 2-0001/2026",
            "Intimo a empresa EMPRESA MODELO LTDA para apresentar sua defesa no prazo já comunicado.",
            "Ciência registrada em 10/09/2026."
        ],
    ),
    (
        "DEFESA ADMINISTRATIVA",
        [
            "Processo Administrativo de Penalização nº 2-0001/2026",
            "EMPRESA MODELO LTDA apresenta defesa administrativa.",
            "Alega dificuldade temporária de abastecimento do fabricante e requer o afastamento da penalidade.",
            "Junta comunicação do fornecedor e cronograma de regularização.",
        ],
    ),
    (
        "PARECER TÉCNICO Nº 012/2026",
        [
            "Após análise da defesa e dos documentos juntados, permanece comprovada a ausência de entrega",
            "no prazo originalmente previsto. A justificativa apresentada deve ser considerada na avaliação",
            "das circunstâncias concretas e de eventual consequência administrativa."
        ],
    ),
    (
        "PARECER JURÍDICO Nº 144/2026",
        [
            "Processo Administrativo de Penalização nº 2-0001/2026",
            "Opina-se pelo regular prosseguimento do feito, com apreciação motivada da defesa,",
            "das provas e dos critérios juridicamente aplicáveis antes de qualquer decisão sancionadora."
        ],
    ),
    (
        "RELATÓRIO CONCLUSIVO DA COMISSÃO",
        [
            "A comissão examinou a notificação, a defesa, os documentos e os pareceres constantes dos autos.",
            "Conclui-se pela existência de descumprimento contratual, sem prejuízo da análise final",
            "da autoridade competente quanto à consequência juridicamente cabível."
        ],
    ),
    (
        "DECISÃO ADMINISTRATIVA FINAL",
        [
            "Processo Administrativo de Penalização nº 2-0001/2026",
            "Considerando a instrução e o relatório conclusivo, DECIDO e APLICO A SANÇÃO de advertência",
            "à EMPRESA MODELO LTDA, exclusivamente para fins deste caso fictício de demonstração.",
            "Dê-se ciência à interessada e observe-se o prazo recursal previsto na norma fictícia do modelo."
        ],
    ),
]


def build_demo_pdf() -> bytes:
    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4

    for index, (title, lines) in enumerate(PAGES, start=1):
        pdf.setFont("Helvetica-Bold", 14)
        pdf.drawString(50, height - 65, title)

        pdf.setFont("Helvetica", 9)
        pdf.drawRightString(width - 50, height - 45, f"PROCESSO MODELO · p. {index}")

        y = height - 100
        pdf.setFont("Helvetica", 10.5)
        for line in lines:
            for wrapped in _wrap(line, 92):
                pdf.drawString(50, y, wrapped)
                y -= 17
            y -= 4

        pdf.setFont("Helvetica-Oblique", 8)
        pdf.drawString(
            50,
            45,
            "Documento fictício para demonstração e teste do Fiscaliza.AI. Não possui efeito jurídico.",
        )
        pdf.showPage()

    pdf.save()
    return buffer.getvalue()


def _wrap(text: str, width: int) -> list[str]:
    words = text.split()
    lines = []
    current = []
    size = 0
    for word in words:
        extra = len(word) + (1 if current else 0)
        if current and size + extra > width:
            lines.append(" ".join(current))
            current = [word]
            size = len(word)
        else:
            current.append(word)
            size += extra
    if current:
        lines.append(" ".join(current))
    return lines
