# Fiscaliza.AI Municipal

Aplicação demonstrativa para apoio auditável à análise documental de processos administrativos municipais.

## Versão preparada para demonstração
- leitura de PDFs com camada de texto;
- OCR em português para documentos escaneados;
- identificação de documentos esperados e pendências;
- perguntas livres sobre o processo;
- classificação das respostas em fato documentado, inferência, pendência e hipótese de enquadramento;
- leitura equilibrada da defesa;
- relatório em PDF;
- trilha de revisão humana;
- cenários fictícios de demonstração;
- endpoint de saúde em `/api/health`.

## Deploy
O repositório está configurado para deploy no Render com Docker. O `Dockerfile` instala o Tesseract OCR e reconstrói a aplicação a partir do pacote de código validado incluído em `.bundle/`.

O arquivo `render.yaml` configura um Web Service no plano gratuito e usa `/api/health` como health check.

A variável `OPENAI_API_KEY` é opcional. Sem uma chave, a aplicação continua funcionando no modo local.

## Observação
Os cenários de demonstração são fictícios. A ferramenta apoia a análise; a decisão administrativa permanece humana.
