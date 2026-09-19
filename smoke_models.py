import sys
from fastapi.testclient import TestClient
import rc1_patch

MODULES = [
    "planejamento",
    "formalizacao",
    "fiscalizacao",
    "alteracoes",
    "penalizacao",
    "encerramento",
]

EXPECTED_MARKERS = {
    "planejamento": "documento oficial de demanda",
    "formalizacao": "proposta vencedora",
    "fiscalizacao": "instrumento contratual",
    "alteracoes": "alteração contratual",
    "penalizacao": "contrato ou instrumento",
    "encerramento": "contrato ou instrumento a encerrar",
}


def fail(msg):
    print("FAIL:", msg)
    raise AssertionError(msg)


def main():
    client = TestClient(rc1_patch.app)
    results = []

    for module in MODULES:
        pdf = client.get(f"/api/demo-pdf?module={module}")
        if pdf.status_code != 200:
            fail(f"{module}: demo-pdf HTTP {pdf.status_code}: {pdf.text[:200]}")

        filename = f"Processo-Modelo-{module}-FiscalizaAI.pdf"
        res = client.post(
            f"/api/analyze?module={module}",
            files={"files": (filename, pdf.content, "application/pdf")},
        )
        if res.status_code != 200:
            fail(f"{module}: analyze HTTP {res.status_code}: {res.text[:500]}")

        data = res.json()
        analysis = data.get("analysis") or {}
        profile = data.get("profile") or analysis.get("process_profile") or {}
        matrix = analysis.get("module_matrix") or []
        questions = " | ".join(str(x.get("question", "")) for x in matrix).lower()

        if data.get("module") != module:
            fail(f"{module}: backend respondeu module={data.get('module')}")
        if analysis.get("module_key") != module:
            fail(f"{module}: analysis.module_key={analysis.get('module_key')}")
        if profile.get("module") != module:
            fail(f"{module}: profile.module={profile.get('module')}")
        if not profile.get("number") or profile.get("number") == "Número não identificado":
            fail(f"{module}: número do processo não identificado")
        if not matrix:
            fail(f"{module}: module_matrix vazia")
        marker = EXPECTED_MARKERS[module]
        if marker not in questions:
            fail(f"{module}: checklist parece genérico; não contém '{marker}'. Questões: {questions}")
        if int((analysis.get("metrics") or {}).get("checklist_total") or len(matrix)) < 5:
            fail(f"{module}: checklist incompleto")
        if int(profile.get("pages") or 0) < 5:
            fail(f"{module}: processo modelo com poucas páginas")
        if int(profile.get("documents") or 0) < 4:
            fail(f"{module}: rastreabilidade documental insuficiente: {profile.get('documents')} docs")

        if module == "planejamento":
            np = analysis.get("normative_profile") or {}
            proc = analysis.get("procedure") or {}
            legal = analysis.get("legal_matrix") or []
            if np.get("id") != "pimenta_bueno_ro":
                fail("planejamento: perfil normativo de Pimenta Bueno ausente")
            if proc.get("key") != "pregao_bens":
                fail(f"planejamento: procedimento classificado incorretamente: {proc}")
            if len(legal) != 6:
                fail(f"planejamento: matriz normativa deveria ter 6 controles; encontrou {len(legal)}")
            if legal[0].get("control_id") != "dod" or not legal[0].get("ok"):
                fail(f"planejamento: DOD não foi parametrizado/localizado corretamente: {legal[0] if legal else None}")
            if not all(x.get("foundation") for x in legal):
                fail("planejamento: há controle sem fundamento parametrizado")
            if not all(x.get("documents") for x in legal if x.get("ok")):
                fail("planejamento: controle localizado sem documento/página rastreável")

        results.append(
            (
                module,
                profile.get("number"),
                profile.get("pages"),
                profile.get("documents"),
                (analysis.get("metrics") or {}).get("checklist_ok"),
                (analysis.get("metrics") or {}).get("checklist_total"),
            )
        )

    print("\nSMOKE TEST OK — 6 módulos")
    for row in results:
        print(
            f"{row[0]:13s} processo={row[1]} paginas={row[2]} "
            f"documentos={row[3]} checklist={row[4]}/{row[5]}"
        )


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print("\nSMOKE TEST FAILED:", exc)
        sys.exit(1)
