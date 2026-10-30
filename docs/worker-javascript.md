# Alternativa JavaScript no Cloudflare Free

## Motivo

Na reprodução da carga diária, o Python Worker excedeu CPU (1102) e, nas
tentativas seguintes no mesmo isolate, retornou 1101 com a exceção
`Cannot enter a promising task from inside another running promising task`.
Essa reprodução ocorreu em GRU; não está limitada a ORD.

O entrypoint `edge/worker.mjs` executa JavaScript nativo com `pg` e Hyperdrive.
Não há Pyodide, FastAPI ou inicialização de modelos Python por requisição.
O plano continua gratuito, sujeito às quotas de Workers e Hyperdrive; a mudança
não torna as quotas ilimitadas nem evita falhas do banco de origem.

## Regras preservadas

- URLs `/v1`, token Bearer, catálogo JSON 2.0, Swagger `/docs`, saúde.
- Bronze/Silver/Gold e SQL do catálogo Python, exportados no build.
- Snapshots existentes, TTL, paginação por UUID, histórico SCD e rate limit
  compartilhado no PostgreSQL. Não há backfill nem alteração de tabelas de origem.
- Chaves inteiras/contagens em strings JSON, calendário com atributos inteiros,
  NULLs e identificadores bigint sem arredondamento JavaScript.
- Logs com rota, status e correlação, sem headers, token, SQL ou registros.

`edge/build_contract.py` gera `edge/contract.json` a partir de `app/catalog.py`,
das consultas em `app/bronze`, `app/silver`, `app/gold` e de `PostgresSnapshots`.
Esse build não acessa o banco nem lê `.env`. Mudanças nas regras Python precisam
regenerar esse arquivo antes da publicação. A API FastAPI permanece disponível
para uso local; o Worker possui uma implementação HTTP própria.

Cada requisição cria um único cliente `pg`, com conexão via binding Hyperdrive.
As consultas internas usam parâmetros posicionais e uma transação por requisição,
com limite de 10 segundos por comando. O commit é aguardado antes da resposta;
erros SQL provocam rollback. Ao terminar, o cliente é fechado via `waitUntil`. O Hyperdrive
continua responsável pelo pool até o Aiven, incluindo a validação TLS existente.

## Preparação e publicação

```powershell
npm ci --ignore-scripts
.venv/Scripts/python.exe edge/build_contract.py
node node_modules/wrangler/bin/wrangler.js versions upload --config wrangler.edge.jsonc --keep-vars
```

O build requer o ambiente Python do projeto. Ele é usado somente para exportar
o contrato/SQL; o bundle Cloudflare contém JavaScript e JSON, sem pacotes Python.
A configuração separada permite validar a alternativa antes de promover uma
versão. Preserve a configuração de observabilidade/Grafana e o secret API_TOKEN.

## Validação necessária

Conferir todas as páginas da carga diária e Gold, tipos e chaves, autenticação,
períodos inválidos, histórico ausente e snapshot expirado. Comparar o resultado
ao snapshot original sem imprimir dados pessoais. A conclusão da carga HTTP
não confirma o MERGE/overwrite no Databricks: essa etapa depende do notebook.

## Estado da investigação em 30/10/2026

A primeira implementação JavaScript completou duas extrações HTTP diárias de
25 requisições, incluindo todas as páginas de eventos e posições. Gold,
autenticação, paginação, datas inválidas e tipos JSON também foram conferidos.
Entretanto, a medição de CPU ainda apresentou valores acima dos 10 ms nominais
do plano Free. Essas execuções bem-sucedidas não comprovam margem de CPU.

A versão seguinte agrupa as transações para reduzir comandos de protocolo:
`642b843c-2de4-4d34-abb9-8178e5ec4b97`. Após recuperar a conexão de administração,
completou duas cargas de 26 chamadas, incluindo 8.104 eventos e 3.820 posições,
e as verificações de contratos e Gold. Os logs confirmaram respostas normais e
redução de CPU, com várias chamadas em 7–10 ms e outras acima dos 10 ms nominais.
Isso reduz o problema, mas não garante ausência de limitação no Free.
Essa versão foi promovida a 100% do tráfego em 30/10/2026, preservando os bindings,
o secret e os destinos Grafana existentes. Não houve ativação de plano pago.

O entrypoint padrão em `wrangler.jsonc` continua Python para compatibilidade com
as ferramentas anteriores. A publicação JavaScript exige explicitamente
`wrangler.edge.jsonc`; não usar o deploy Python para atualizar a produção atual.

Referências:
- https://developers.cloudflare.com/hyperdrive/examples/connect-to-postgres/postgres-drivers-and-libraries/node-postgres/
- https://developers.cloudflare.com/workers/platform/limits/
- https://developers.cloudflare.com/workers/versions-and-deployments/version-urls/
