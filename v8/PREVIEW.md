# Preview isolado da V8 no Render

A V8 foi preparada para ser publicada como **serviço separado** da versão atualmente em produção.

Arquivo do Blueprint: `render-v8-preview.yaml`

## O que este preview faz

- usa a branch `v8-rebuild`;
- usa o Dockerfile `v8/Dockerfile`;
- mantém a V7 atual intacta;
- usa `/api/v8/health` como health check;
- só faz novo deploy depois que os checks do GitHub passam;
- mantém análises temporárias em memória por 30 minutos;
- limita cada PDF a 30 MB, o lote a 60 MB e até 5 PDFs por análise; cada PDF pode ter até 500 páginas, o lote até 600 páginas, com limites próprios de OCR para evitar travamento da instância.

## Como criar quando chegar a hora

No Render, crie um Blueprint apontando para este mesmo repositório e informe como Blueprint Path:

    render-v8-preview.yaml

O serviço sugerido pelo arquivo se chama:

    fiscaliza-ai-v8-preview

Não substitua o serviço atual. A finalidade desta instância é somente homologação visual e funcional da V8.

## Critério antes de substituir a V7

A V8 só deve assumir o endereço principal depois de:

1. validação visual no desktop e celular;
2. teste completo do processo modelo;
3. validação de pelo menos processos públicos reais de perfis diferentes;
4. confirmação de que DOC-ID + página abre a fonte correta;
5. confirmação de que o estágio processual e a minuta sugerida são coerentes;
6. relatório PDF conferido;
7. nenhum alerta de integridade crítico nos testes de homologação.
