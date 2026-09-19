from playwright.sync_api import sync_playwright, expect

BASE = "http://127.0.0.1:8000"

MODULES = [
    ("planejamento", "Planejamento da contratação", "3101/2026", "7"),
    ("formalizacao", "Formalização da contratação", "3202/2026", "13"),
    ("fiscalizacao", "Fiscalização e execução", "1001/2026", "11"),
    ("alteracoes", "Alterações contratuais", "3404/2026", "13"),
    ("penalizacao", "Penalização contratual", "2-0001/2026", "17"),
    ("encerramento", "Extinção / encerramento", "3606/2026", "8"),
]


def home(page):
    page.get_by_role("button", name="Voltar aos módulos").click()
    page.locator("#homeV86").wait_for(state="visible")
    page.wait_for_url(lambda u: "module=" not in u)


def main():
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1366, "height": 768})

        page.goto(BASE, wait_until="networkidle")
        page.locator("#homeV86").wait_for(state="visible")

        # Abrir diretamente a URL de um módulo nunca pode iniciar demonstração.
        page.goto(BASE + "/?module=planejamento", wait_until="networkidle")
        expect(page.locator("#sideModuleName")).to_have_text("Planejamento da contratação")
        expect(page.get_by_text("Nenhum processo aberto", exact=True)).to_be_visible(timeout=10000)
        assert "Carregando processo modelo" not in page.locator("body").inner_text()
        assert page.locator("#overviewHub .ov-title").count() == 0

        page.goto(BASE, wait_until="networkidle")
        page.locator("#homeV86").wait_for(state="visible")
        cards = page.locator("#homeV86 .home-v86-card")
        assert cards.count() == 6, f"Home deveria ter 6 módulos; encontrou {cards.count()}"

        for i, (key, label, number, docs) in enumerate(MODULES):
            card = page.locator(f"#homeV86 .home-v86-card[data-module='{key}']")
            expect(card).to_be_visible()

            # Abrir módulo deve abrir uma área limpa, sem processo fictício.
            card.get_by_role("button", name="Abrir módulo").click()
            page.wait_for_url(f"**?module={key}")
            expect(page.locator("#sideModuleName")).to_have_text(label)
            expect(page.get_by_text("Nenhum processo aberto", exact=True)).to_be_visible(timeout=10000)

            home(page)

            # No Planejamento, testa também a corrida: iniciar modelo e imediatamente
            # escolher "Abrir módulo" precisa cancelar a demonstração por completo.
            if key == "planejamento":
                card = page.locator("#homeV86 .home-v86-card[data-module='planejamento']")
                card.get_by_role("button", name="Processo modelo").click()
                page.wait_for_url("**?module=planejamento")
                page.evaluate("abrirModuloV92('planejamento')")
                expect(page.get_by_text("Nenhum processo aberto", exact=True)).to_be_visible(timeout=10000)
                page.wait_for_timeout(1500)
                assert "Carregando processo modelo" not in page.locator("body").inner_text()
                assert page.locator("#overviewHub .ov-title").count() == 0
                home(page)

            # Processo modelo deve carregar somente o modelo do módulo escolhido.
            card = page.locator(f"#homeV86 .home-v86-card[data-module='{key}']")
            card.get_by_role("button", name="Processo modelo").click()
            page.wait_for_url(f"**?module={key}")

            expect(page.locator("#sideModuleName")).to_have_text(label, timeout=30000)
            expect(page.locator("#workspaceModuleTitle")).to_have_text(number, timeout=30000)
            expect(page.locator("#overviewHub .ov-title")).to_have_text(number, timeout=30000)
            expect(page.locator("#dashDocs")).to_have_text(docs, timeout=10000)
            expect(page.locator("#overviewHub")).to_be_visible()
            assert page.locator("#overviewHub .ov-status").count() >= 4
            assert page.locator("#overviewHub .ov-stage").count() == 5
            assert "Não foi possível carregar o processo modelo" not in page.locator("body").inner_text()

            if key in ("planejamento", "formalizacao", "fiscalizacao", "alteracoes"):
                expect(page.locator(".pb-profile-chip").nth(0)).to_contain_text("Pimenta Bueno/RO")
                if key == "fiscalizacao":
                    expect(page.locator(".pb-profile-chip").nth(1)).to_contain_text("Execução contratual")
                elif key == "alteracoes":
                    expect(page.locator(".pb-profile-chip").nth(1)).to_contain_text("Restabelecimento do equilíbrio econômico-financeiro")
                else:
                    expect(page.locator(".pb-profile-chip").nth(1)).to_contain_text("Pregão — aquisição de bens")
                expect(page.locator("#legalMatrixPanelV100")).to_be_visible(timeout=10000)
                legal_text = page.locator("#legalMatrixPanelV100").inner_text()

            if key == "planejamento":
                text = page.locator("#overviewHub").inner_text()
                assert "DOD" in text or "Documento Oficial de Demanda" in text
                assert "Estudo Técnico Preliminar" in text
                assert "Termo de Referência" in text
                expect(page.locator("#overviewHub .ov-evidence-block h4").nth(0)).to_have_text("Documentos estruturantes", timeout=10000)
                expect(page.locator("#overviewHub .ov-evidence-block h4").nth(1)).to_have_text("Controles complementares", timeout=10000)
                stage_text = page.locator("#overviewHub .ov-track").inner_text()
                assert "Demanda" in stage_text and "Aprovação" in stage_text
                hub_text = page.locator("#overviewHub").inner_text().lower()
                assert "defesa administrativa" not in hub_text
                assert "notificação/intimação como peça autônoma" not in hub_text
                assert page.locator("#overviewHub .ov-time").count() <= 6
                assert page.locator("#legalMatrixPanelV100 tbody tr").count() == 6
                assert "Documento Oficial de Demanda" in legal_text
                assert "Secretaria de Origem" in legal_text

            if key == "formalizacao":
                assert page.locator("#legalMatrixPanelV100 tbody tr").count() == 11
                assert "Conferência da fase preparatória" in legal_text
                assert "Procuradoria-Geral do Município" in legal_text
                assert "Controladoria-Geral do Município" in legal_text
                assert "Adjudicação e homologação" in legal_text
                assert "Nota de Empenho" in legal_text
                stage_text = page.locator("#overviewHub .ov-track").inner_text()
                assert "SUPEL / edital" in stage_text
                assert "PGM / autorização" in stage_text
                assert "CGM / homologação" in stage_text
                assert "Contrato / gestão" in stage_text

            if key == "fiscalizacao":
                assert page.locator("#legalMatrixPanelV100 tbody tr").count() == 10
                assert "Designação formal de fiscal e gestor" in legal_text
                assert "Registro de acompanhamento" in legal_text
                assert "Medição / atesto" in legal_text
                assert "Recebimento provisório/definitivo" in legal_text
                assert "Notificação / comunicação à contratada" in legal_text
                assert "Encaminhamento para providência superior / penalização" in legal_text
                assert "Condicional" in legal_text
                stage_text = page.locator("#overviewHub .ov-track").inner_text()
                assert "Contrato / responsáveis" in stage_text
                assert "Início / execução" in stage_text
                assert "Medição / recebimento" in stage_text
                assert "Ocorrências / ciência" in stage_text
                assert "Providências" in stage_text

            if key == "alteracoes":
                assert page.locator("#legalMatrixPanelV100 tbody tr").count() == 12
                assert "Pedido e justificativa da alteração" in legal_text
                assert "Fato superveniente, prova e nexo com o desequilíbrio" in legal_text
                assert "Planilha / memória de cálculo / comprovação econômica" in legal_text
                assert "Conferência da matriz de riscos" in legal_text
                assert "Decisão motivada sobre a alteração" in legal_text
                assert "Termo aditivo ou apostila compatível com a hipótese" in legal_text
                assert "Índice contratual, data-base e interregno" not in legal_text
                assert "Planilha de custos e instrumento coletivo da repactuação" not in legal_text
                assert "Cálculo dos limites de acréscimo / supressão" not in legal_text
                stage_text = page.locator("#overviewHub .ov-track").inner_text()
                assert "Contrato / pedido" in stage_text
                assert "Execução / interesse" in stage_text
                assert "Prova / cálculos" in stage_text
                assert "Análises / orçamento" in stage_text
                assert "Decisão / aditivo" in stage_text

            # Navegação lateral existe para todas as áreas operacionais.
            for tab in ["documentos", "evidencias", "cronologia", "pendencias", "perguntar", "minutas", "relatorio"]:
                expect(page.locator(f".side-nav .side-item[data-tab='{tab}']")).to_be_visible()

            if i < len(MODULES) - 1:
                home(page)

        browser.close()

    print("UI SMOKE OK — URL direta + cancelamento de modelo + 6 módulos + 6 processos modelo")


if __name__ == "__main__":
    main()
