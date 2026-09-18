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

## Próximos marcos

- segmentação multi-página melhorada;
- gabarito de processos reais;
- visualizador de PDF ligado ao DOC-ID + página;
- central de evidências;
- geração de minutas condicionada ao estágio;
- só então migração dos outros cinco módulos.
