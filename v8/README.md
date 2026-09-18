# Fiscaliza.AI V8 — reconstrução paralela

A V8 é uma reconstrução limpa e paralela à versão publicada. Nada neste diretório altera o Render atual enquanto o serviço continuar apontando para o Dockerfile da raiz.

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
- templates/ e static/: interface mínima de validação.

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
- sessão temporária com expiração, encerramento explícito, cabeçalhos no-store e limite configurável por PDF.

O benchmark real deve permanecer verde antes de qualquer migração para a versão publicada.

## Próximos marcos

- ampliar o conjunto de processos reais de regressão, incluindo um PAS completo já instaurado;
- testar PDFs digitalizados com OCR e peças com baixa qualidade;
- consolidar relatório/exportação auditável da análise;
- fazer revisão visual final da V8;
- somente depois migrar, um a um, os outros cinco módulos.
