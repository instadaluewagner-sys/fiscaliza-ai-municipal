from pathlib import Path

BASE = Path(__file__).resolve().parents[1]


def test_shell_profissional_tem_navegacao_dupla_e_viewer():
    html = (BASE / "templates" / "index.html").read_text(encoding="utf-8")
    for expected in [
        'id="startState"',
        'id="processWorkspace"',
        'class="sidebar"',
        'class="process-tabs"',
        'data-tab="overview"',
        'data-tab="documents"',
        'data-tab="evidence"',
        'data-tab="timeline"',
        'data-tab="pending"',
        'data-tab="drafts"',
        'data-tab="reports"',
        'id="pdfViewer"',
        'onclick="analyzeDemoProcess()"',
    ]:
        assert expected in html


def test_javascript_renderiza_visao_geral_minuta_e_fontes():
    js = (BASE / "static" / "app.js").read_text(encoding="utf-8")
    for function_name in [
        "function showTab(",
        "function renderOverview(",
        "function renderDocuments(",
        "function renderEvidence(",
        "function renderTimeline(",
        "function renderPending(",
        "function renderDraftPlaceholder(",
        "function renderReport(",
        "async function loadOverviewDraftPreview(",
        "async function loadCompatibleDraft(",
        "async function openDocument(",
        "async function analyzeDemoProcess(",
        "async function runAnalysis(",
    ]:
        assert function_name in js

    assert "/api/v8/draft/" in js
    assert "/api/v8/document/" in js
    assert "/api/v8/report/" in js


def test_css_tem_hierarquia_do_sistema_e_nao_depende_de_framework_externo():
    css = (BASE / "static" / "app.css").read_text(encoding="utf-8")
    for selector in [
        ".topbar",
        ".sidebar",
        ".process-header",
        ".process-tabs",
        ".workspace-grid",
        ".overview-hero",
        ".viewer-pane",
        ".profile-grid",
        ".evidence-list",
        ".draft-panel",
    ]:
        assert selector in css
    assert "@import" not in css
