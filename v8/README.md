# Fiscaliza.AI V8 RC1 — Penalização contratual

A V8 RC1 é a primeira versão candidata da nova arquitetura. Ela permanece separada da versão publicada e concentra, nesta etapa, o módulo de Penalização contratual.

## Objetivo da primeira etapa

Validar o módulo de Penalização contratual com um pipeline explícito:

1. PDF → páginas;
2. páginas → documentos autônomos (DOC-001, DOC-002...);
3. documentos → checklist com quatro estados: located, not_found, not_applicable, inconclusive;
4. documentos + evidências → estágio processual;
5. estágio → próximo ato e minuta compatível.

A V8 não deve sugerir documento incompatível com a fase atual. Ex.: processo com decisão final não pode sugerir notificação de instauração.

## Estrutura

- main.py: API da V8.
- services/pdf_reader.py: extração e OCR.
- services/document_segmenter.py: segmentação de peças.
- services/evidence.py: evidências vinculadas a documento/página.
- modules/penalizacao.py: regras do primeiro módulo.
- core/models.py: contratos de dados estáveis.
- tests/: testes de regressão.
- templates/ e static/: interface comercial de homologação com menu lateral, abas e visualizador de PDF.

## Executar localmente

    pip install -r v8/requirements.txt
    uvicorn v8.main:app --reload

## Princípio de desenvolvimento

Nenhuma regra será criada para acertar um PDF específico. Correções devem melhorar classes de documentos/processos e ser cobertas por teste.

## Estado atual do marco de Penalização

Concluído nesta etapa:

- segmentação multi-página com separação de envelopes/protocolos e peças anexas;
- gabarito automatizado do processo público ASSESTE, com gate de qualidade no GitHub Actions;
- visualizador do PDF ligado ao DOC-ID + página;
- perfil da contratação com processo, pregão, ata, contrato, empenhos, empresa, CNPJ, objeto e quantidade quando identificáveis com segurança;
- detecção explícita de divergências cadastrais, preservando as fontes conflitantes;
- central de evidências categorizadas e priorização da fonte técnica primária;
- estágio processual com fonte documental rastreável;
- checklist com quatro estados: localizado, não localizado, não aplicável e inconclusivo;
- minutas compatíveis com a fase, com fontes por DOC-ID + página;
- notificação de instauração detalhada, sem inventar prazo, competência ou dado ausente;
- sessão temporária com expiração, encerramento explícito, cabeçalhos no-store e limites por arquivo/lote;
- processo modelo fictício analisado pelo mesmo pipeline dos uploads reais;
- interface comercial com menu lateral + abas horizontais, Visão Geral executiva e prévia da minuta;
- Blueprint isolado de preview no Render em `render-v8-preview.yaml`.

Os testes internos automatizados são o gate obrigatório de cada alteração. Os benchmarks públicos reais ficam disponíveis para execução manual porque dependem de sites externos e não devem quebrar o desenvolvimento por indisponibilidade, bloqueio ou mudança de arquivo.

## Escopo fechado da RC1

A RC1 de Penalização entrega: upload de PDF, processo modelo, OCR, segmentação documental, identificação contratual rastreável, estágio processual, pendências, cronologia, evidências com DOC-ID + página, visualização do PDF original, minuta compatível com a fase, relatório PDF/JSON e exclusão da sessão.

Os outros módulos ficam fora desta RC1. Eles só serão migrados depois da validação desta base.
