import app_v33 as core
import rc1_patch  # aplica a parametrização ativa sobre o core


def page(n, title, body):
    return {
        "file": "processo-ficticio.pdf",
        "page": n,
        "text": title + "\n" + body,
        "ocr": False,
    }


def analyze(pages):
    core._assign_document_ids(pages)
    a = core.analyze_pages(pages)
    a = core._module_overlay(pages, a, "penalizacao")
    return a


# Caso 1: há cobranças do almoxarifado e o processo já foi atribuído à Comissão,
# mas a Comissão AINDA NÃO expediu sua Notificação Extrajudicial.
pages_pre_commission = [
    page(
        1,
        "TERMO DE ABERTURA DE PROCESSO 2-1234/2026",
        "Assunto: APLICAÇÃO DE PENALIDADE. Processo aberto para apurar possível não entrega."
    ),
    page(
        2,
        "ATA DE REGISTRO DE PREÇOS Nº 010/2026",
        "Instrumento da contratação para fornecimento de materiais."
    ),
    page(
        3,
        "NOTA DE EMPENHO Nº 400/2026",
        "Ficha: 520 Unidade: Fundo Municipal de Saúde. Prazo de Entrega: Até 30 dias. Quantidade 40 UNIDADES."
    ),
    page(
        4,
        "COMPROVANTE DE ENVIO DA NOTA DE EMPENHO",
        "A empresa confirmou o recebimento da Nota de Empenho nº 400/2026."
    ),
    page(
        5,
        "NOTIFICAÇÃO - ALMOXARIFADO 01",
        "Diante da ausência de entrega, solicita-se que a empresa proceda à entrega e informe a previsão."
    ),
    page(
        6,
        "NOTIFICAÇÃO - ALMOXARIFADO 02",
        "Reitera-se a cobrança para regularização da obrigação de entrega."
    ),
    page(
        7,
        "OFÍCIO DE ENCAMINHAMENTO",
        "Encaminha-se o presente processo à Comissão de Penalização para análise de possível infração."
    ),
    page(
        8,
        "TERMO DE ATRIBUIÇÃO/DESIGNAÇÃO DE PROCESSO",
        "Atribui-se o processo ao membro da Comissão Permanente de Penalização para dar sequência aos autos."
    ),
]

a1 = analyze(pages_pre_commission)
rows1 = {x["control_id"]: x for x in a1["legal_matrix"]}

assert rows1["cobranca_previa"]["ok"] is True
assert rows1["cobranca_previa"]["pages"] == [5, 6], rows1["cobranca_previa"]
assert a1["quantity"]["value"] == "40", a1["quantity"]
assert rows1["notificacao_comissao"]["ok"] is False
assert rows1["defesa_ou_decurso"]["status"] == "Não exigível nesta fase"
assert a1["next_action"]["stage"] == "Instrução inicial pela Comissão"
assert "Notificação Extrajudicial da Comissão de Penalização" in a1["next_action"]["action"]
assert not any("Defesa administrativa ou certidão" in x["text"] for x in a1["review_flags"])


# Caso 2: a Comissão expediu a sua Notificação Extrajudicial e há ciência,
# mas ainda não existe defesa nem certidão de decurso. O sistema deve aguardar/controlar prazo.
pages_notified = pages_pre_commission + [
    page(
        9,
        "NOTIFICAÇÃO EXTRAJUDICIAL Nº 05/COMISSÃO DE PENALIZAÇÃO/2026",
        "Processo Administrativo de Penalização nº 2-1234/2026. "
        "A Comissão de Penalização NOTIFICA E INTIMA a empresa para apresentar defesa."
    ),
    page(
        10,
        "COMPROVANTE DE ENVIO E RECEBIMENTO DA NOTIFICAÇÃO EXTRAJUDICIAL",
        "A empresa confirmou o recebimento da Notificação Extrajudicial da Comissão de Penalização."
    ),
]

a2 = analyze(pages_notified)
rows2 = {x["control_id"]: x for x in a2["legal_matrix"]}

assert rows2["notificacao_comissao"]["ok"] is True
assert rows2["ciencia_notificacao_comissao"]["ok"] is True
assert rows2["defesa_ou_decurso"]["status"] == "Aguardando / conferir prazo", rows2["defesa_ou_decurso"]
assert a2["next_action"]["stage"] == "Contraditório"
assert "prazo de defesa" in a2["next_action"]["action"].lower()


# Caso 3: defesa apresentada. A próxima fase deve ser análise/instrução, nunca nova notificação.
pages_defended = pages_notified + [
    page(
        11,
        "DEFESA ADMINISTRATIVA",
        "A empresa vem apresentar sua defesa administrativa e requer análise dos documentos anexados."
    ),
]

a3 = analyze(pages_defended)
rows3 = {x["control_id"]: x for x in a3["legal_matrix"]}

assert rows3["defesa_ou_decurso"]["ok"] is True
assert a3["next_action"]["stage"] == "Análise da defesa / instrução"
assert "Notificação Extrajudicial" not in a3["next_action"]["action"]

print("PENALIZACAO V14 OK — cobrança prévia ≠ notificação da Comissão; fase e próximo ato coerentes")
