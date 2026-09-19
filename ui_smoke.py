from playwright.sync_api import sync_playwright, expect

BASE = "http://127.0.0.1:8000"


def main():
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1366, "height": 768})

        page.goto(BASE, wait_until="networkidle")
        page.locator("#homeV86").wait_for(state="visible")
        cards = page.locator("#homeV86 .home-v86-card")
        assert cards.count() == 6, f"Home deveria ter 6 módulos; encontrou {cards.count()}"

        planejamento = page.locator("#homeV86 .home-v86-card[data-module='planejamento']")
        expect(planejamento).to_be_visible()

        # Abrir módulo não pode carregar modelo automaticamente.
        planejamento.get_by_role("button", name="Abrir módulo").click()
        page.wait_for_url("**?module=planejamento")
        expect(page.get_by_text("Nenhum processo aberto", exact=True)).to_be_visible(timeout=10000)

        # Processo modelo deve carregar o modelo do próprio módulo.
        page.get_by_role("button", name="Voltar aos módulos").click()
        page.locator("#homeV86").wait_for(state="visible")
        planejamento = page.locator("#homeV86 .home-v86-card[data-module='planejamento']")
        planejamento.get_by_role("button", name="Processo modelo").click()
        page.wait_for_url("**?module=planejamento")
        expect(page.locator("#workspaceModuleTitle")).to_have_text("3101/2026", timeout=30000)
        expect(page.get_by_text("Planejamento da contratação", exact=True).first).to_be_visible()
        expect(page.get_by_text("Documento de Formalização da Demanda", exact=False).first).to_be_visible(timeout=10000)

        # Penalização continua isolada e com seu próprio modelo.
        page.get_by_role("button", name="Voltar aos módulos").click()
        page.locator("#homeV86").wait_for(state="visible")
        penalizacao = page.locator("#homeV86 .home-v86-card[data-module='penalizacao']")
        penalizacao.get_by_role("button", name="Processo modelo").click()
        page.wait_for_url("**?module=penalizacao")
        expect(page.locator("#workspaceModuleTitle")).to_have_text("2-0001/2026", timeout=30000)

        browser.close()

    print("UI SMOKE OK — Home, Abrir módulo e Processos modelo isolados")


if __name__ == "__main__":
    main()
