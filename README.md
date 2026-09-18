# Fiscaliza.AI Municipal

Aplicação demonstrativa para apoio auditável à análise documental de processos administrativos municipais.

## Versão atual
- leitura de PDFs com camada de texto e OCR em português para documentos escaneados;
- análise de processos consolidados: um único PDF pode conter várias peças processuais;
- classificação por página/bloco de contrato, empenho, ordem de fornecimento, nota fiscal, termo de recebimento, notificação, intimação, defesa, parecer técnico, parecer jurídico, decisão, manifestação e norma;
- perguntas livres sobre o processo;
- separação entre fato documentado, inferência, pendência e hipótese de enquadramento;
- leitura equilibrada da defesa e dos elementos contrários;
- identificação de documentos efetivamente ausentes sem tratar automaticamente a falta de termo de recebimento como falha quando os autos registram que não houve entrega;
- cautela com quantidades ambíguas: referências como "por viagem" ou "metade da quantidade prevista" não são tratadas como total contratual;
- identificação do estágio sancionador quando os autos apenas autorizam ou determinam a instauração de procedimento posterior;
- relatório PDF, trilha de revisão humana e endpoint de saúde em `/api/health`.

## Deploy
O repositório está configurado para deploy no Render com Docker. O `Dockerfile` instala o Tesseract OCR e reconstrói a aplicação a partir do pacote de código incluído em `.bundle/`.

A variável `OPENAI_API_KEY` é opcional. Sem uma chave, a aplicação continua funcionando em modo local.

## Observação
A ferramenta organiza e apoia a análise; a decisão administrativa continua humana. Em processos reais, resultados devem ser conferidos com as peças originais antes de qualquer providência.
