import re
import app_v33 as core

app = core.app


# RC1: correcoes finais da Penalizacao observadas no preview real.
# Mantem a aplicacao principal intacta e aplica apenas ajustes de acabamento/consistencia.


def _best_company_and_cnpj_rc1(pages):
    joined = "\n".join(p.get("text") or "" for p in pages)
    company_candidates = []
    patterns = [
        r"(?:CONTRATADA|Empresa)\s*[:\-]?\s*([A-ZÁÉÍÓÚÂÊÔÃÕÇ0-9][A-ZÁÉÍÓÚÂÊÔÃÕÇ0-9 .,&\-]{3,140}?\b(?:LTDA|EIRELI|EPP|ME|S\.?A\.?)\b)",
        r"([A-ZÁÉÍÓÚÂÊÔÃÕÇ0-9][A-ZÁÉÍÓÚÂÊÔÃÕÇ0-9 .,&\-]{4,140}?\b(?:LTDA|EIRELI|EPP|ME|S\.?A\.?)\b)\s*,?\s*(?:inscrita|inscrito)?\s*(?:no\s+)?CNPJ",
    ]
    for pat in patterns:
        for m in re.finditer(pat, joined, flags=re.I):
            name = re.sub(r"\s+", " ", m.group(1)).strip(" ,;:-")
            # Evita falsos positivos como "EMPRESA" por causa de "S.A." dentro da palavra.
            if len(name.split()) >= 2:
                company_candidates.append((m.start(), name))

    company = company_candidates[0][1] if company_candidates else "[NÃO IDENTIFICADO AUTOMATICAMENTE]"

    cnpjs = [(m.start(), m.group(0)) for m in re.finditer(
        r"\b\d{2}\.?\d{3}\.?\d{3}\/?\d{4}-?\d{2}\b", joined
    )]
    if company_candidates and cnpjs:
        pos = company_candidates[0][0]
        cnpj = min(cnpjs, key=lambda x: abs(x[0] - pos))[1]
    else:
        cnpj = cnpjs[0][1] if cnpjs else "[NÃO IDENTIFICADO AUTOMATICAMENTE]"
    return company, cnpj


def _extract_origin_process_rc1(pages):
    joined = "\n".join(p.get("text") or "" for p in pages)
    return core._first_match(joined, [
        r"Protocolo(?:\s+de\s+origem)?\s*(?:n[ºo.]?|número)?\s*[:\-]?\s*([0-9][0-9.\-\/]+)",
        r"Processo(?:\s+Administrativo)?(?:\s+de\s+origem)?\s*(?:n[ºo.]?|número)?\s*[:\-]?\s*([0-9][0-9.\-\/]+)",
    ])


core._best_company_and_cnpj = _best_company_and_cnpj_rc1
core._extract_origin_process = _extract_origin_process_rc1


_old_process_profile = core._derive_process_profile


def _derive_unit_from_pages(pages):
    joined = "\n".join(p.get("text") or "" for p in pages[:12])
    patterns = [
        r"Interessad[oa]\s*:\s*([^\.\n]{3,140})",
        r"Unidade\s+(?:demandante|requisitante|solicitante)\s*:\s*([^\.\n]{3,140})",
        r"((?:Secretaria|Fundo|Departamento|Autarquia|Coordena[cç][aã]o|Ger[eê]ncia)\s+(?:Municipal\s+)?[^\.\n]{3,100})",
    ]
    for pat in patterns:
        m = re.search(pat, joined, flags=re.I)
        if not m:
            continue
        value = re.sub(r"\s+", " ", m.group(1)).strip(" ,;:-")
        if re.search(r"Secretaria|Fundo|Departamento|Autarquia|Coordena[cç][aã]o|Ger[eê]ncia|Unidade", value, flags=re.I):
            return value[:160]
    return ""


def _derive_process_profile_rc1(pages, module, process_number="", interested="", unit=""):
    profile = _old_process_profile(pages, module, process_number, interested, unit)
    if not unit and profile.get("unit") == "Unidade não informada":
        derived = _derive_unit_from_pages(pages)
        if derived:
            profile["unit"] = derived
    return profile


core._derive_process_profile = _derive_process_profile_rc1


_old_next_action = core._next_action


def _next_action_rc1(pages, a):
    if a.get("final_sanction"):
        return {
            "stage": "Pós-decisão",
            "action": "Conferir a ciência da empresa sobre a decisão e verificar eventual recurso, publicação e registro cabíveis.",
            "why": "Há decisão final com sanção expressa nos autos; a providência seguinte é de ciência e encerramento/seguimento do fluxo."
        }
    return _old_next_action(pages, a)


core._next_action = _next_action_rc1


_old_generic_document_draft = core._generic_document_draft


def _generic_document_draft_rc1(item, kind):
    kind = (kind or "").lower()
    if kind != "comunicacao_decisao":
        return _old_generic_document_draft(item, kind)

    pages = item["pages"]
    md = core._validated_metadata(pages)
    lines = core._draft_header(md, "MINUTA — CIÊNCIA DA DECISÃO ADMINISTRATIVA")
    lines += [
        "Fica a empresa " + md["empresa"] + " CIENTIFICADA da decisão administrativa proferida no Processo Administrativo de Penalização nº " + md["penalizacao"] + ".",
        "",
        "A íntegra da decisão deverá acompanhar esta comunicação, assegurando à interessada conhecimento dos fundamentos, da conclusão e das providências determinadas pela autoridade competente.",
        "",
        "Eventual recurso, pedido de reconsideração ou outra medida cabível deverá observar o prazo, a forma e o canal previstos na legislação e regulamentação aplicáveis, os quais deverão ser conferidos antes da expedição desta comunicação.",
        "",
        "Após a comprovação da ciência, deverão ser adotadas, conforme o caso, as providências de registro, publicação, cumprimento da decisão e encerramento ou continuidade da fase recursal.",
        "",
        "[LOCAL], [DATA].",
        "",
        "[RESPONSÁVEL / AUTORIDADE COMPETENTE]",
        "",
        "MINUTA ASSISTIDA — REVISÃO HUMANA OBRIGATÓRIA."
    ]
    return {
        "draft": "\n".join(lines),
        "sources": ["Decisão administrativa e documentos do processo analisado"]
    }


core._generic_document_draft = _generic_document_draft_rc1


_rc1_css = r"""
<style id="rc1-final-fixes">
/* Uma unica navegacao: menu lateral. */
#processTabs,
.process-tabs.visible{display:none!important}

/* Evita paineis esticados e elimina o vazio observado no preview. */
.ov-grid{align-items:start}
.ov-grid:last-child{grid-template-columns:1fr!important}
.ov-grid:last-child .ov-panel{min-height:0!important}

/* Minuta precisa ser lida como documento, nao como coluna estreita. */
.ov-grid:last-child .ov-draft-paper{
  width:100%;
  max-height:520px;
  font-size:11.5px;
  line-height:1.72;
  padding:22px 28px;
}
.ov-grid:last-child .ov-draft-actions{margin-top:10px}

/* Legibilidade do painel executivo. */
.ov-summary{font-size:11px;line-height:1.65}
.ov-evidence-item p{font-size:10px;line-height:1.5}
.ov-evidence-item span{font-size:8.3px}
.ov-time{min-width:145px}
.ov-time b{font-size:9.6px}
.ov-time small{font-size:7.8px}

@media(max-width:700px){
  .ov-grid:last-child .ov-draft-paper{padding:16px;font-size:10.8px}
}
</style>
"""

_rc1_js = r"""
<script id="rc1-final-fixes-js">
function ovDefaultDraftKind(a){
  var m=a.module_key||selectedModule;
  if(m==="penalizacao"){
    if(a.final_sanction && a.final_sanction.length)return "comunicacao_decisao";
    if(a.has && a.has.decisao)return "comunicacao_decisao";
    return "notificacao";
  }
  if(m==="sindicancia"||m==="disciplinar"||m==="fiscalizacao")return "relatorio";
  if(m==="reequilibrio"||m==="rescisao")return "decisao";
  return "relatorio";
}
function ovDraftLabel(kind){
  return {
    notificacao:"Notificação de instauração",
    relatorio:"Relatório conclusivo",
    decisao:"Minuta de decisão",
    diligencia:"Despacho de diligência",
    despacho:"Despacho",
    intimacao:"Intimação",
    comunicacao_decisao:"Ciência da decisão administrativa"
  }[kind]||"Minuta assistida";
}
</script>
"""

core.HTML = core.HTML.replace("</head>", _rc1_css + "</head>", 1)
core.HTML = core.HTML.replace("</body>", _rc1_js + "</body>", 1)
