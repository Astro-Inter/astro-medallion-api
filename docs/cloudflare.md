# Implantação FastAPI e operação (SCRUM-430)

Referências oficiais:
- https://developers.cloudflare.com/containers/examples/env-vars-and-secrets/
- https://developers.cloudflare.com/containers/guides/deploy/
- https://developers.cloudflare.com/containers/configuration/wrangler/

## Arquitetura

FastAPI/Uvicorn roda em um container Linux Python 3.13. Psycopg acessa o
PostgreSQL via libpq com validação TLS. O Worker `cloudflare/gateway.js` inicia
o container, espera `/health` com token e encaminha requisições HTTP para a
porta 8080. Rotas, autenticação e consultas da API ficam no Python.

A configuração usa a API nativa de Durable Object Containers, um container
nomeado e suspensão após cinco minutos de inatividade. Configure a conta
Cloudflare com suporte a Containers. Docker precisa estar ativo para construir
a imagem localmente; Workers Builds também pode construir a imagem.

## Segredos

| Nome | Uso |
| --- | --- |
| API_TOKEN | Token exclusivo da API, já existente no .env local |
| DATABASE_URL | Conexão PostgreSQL |
| DATABASE_SSL_CA | CA privada em texto PEM, com `\n` escapado |
| DATABASE_SSL_CA_FILE | Alternativa local: caminho do arquivo PEM |

O adaptador repassa os três primeiros secrets como variáveis de ambiente do
container. DATABASE_SSL_CA_FILE é uma alternativa para execução local ou
container com certificado montado; o gateway não monta arquivos locais.

Para Aiven, obter o CA no console do serviço e definir:
`DATABASE_SSL_CA="-----BEGIN CERTIFICATE-----\n...\n-----END CERTIFICATE-----\n"`.
O backend materializa um arquivo PEM temporário para libpq e o remove ao
fechar a conexão. `sslmode=verify-full` é obrigatório no código, mesmo se
a URL original contiver sslmode=require. Não desabilitar a validação TLS.

`.dockerignore` exclui .env e credenciais da imagem; o Dockerfile copia apenas
o projeto Python e o lock de dependências. Secrets são injetados em runtime.

## Execução e publicação

Para executar o container diretamente, com Docker ativo:

```sh
docker build -t astro-medallion-api .
docker run --rm -p 8000:8080 --env-file .env astro-medallion-api
```

Para desenvolvimento Cloudflare e futura publicação:

```sh
npm ci
node node_modules/wrangler/bin/wrangler.js login
npm run cloudflare:dev
# Confere somente o adaptador; não constrói a imagem Python.
node node_modules/wrangler/bin/wrangler.js deploy --dry-run --containers-rollout=none
# Publica Worker, secrets e imagem quando a conta/Docker estiverem prontos.
npm run cloudflare:deploy -- --secrets-file .env
```

Wrangler carrega .env em desenvolvimento; a publicação envia esses valores
como secrets. O comando real constrói e envia a imagem e configura o container.
Não usar vars do Wrangler para credenciais. A primeira inicialização pode
demorar até o container ficar pronto. Erros do gateway retornam 503 sem segredos.

## Operação

`/health` verifica o FastAPI e exige token. Uma chamada a
`/v1/bronze/unidade?limit=1` verifica PostgreSQL. Limites: até 1000 registros
por página e 366 dias por período; statement_timeout=10s e connect_timeout=10s.
As consultas síncronas Psycopg executam no thread pool do servidor, sem bloquear
o event loop. Cada requisição abre e fecha sua conexão; definir pooling antes
de aumentar a escala, conforme a capacidade do banco.

Rotação: atualizar API_TOKEN no Worker e no Databricks Secrets, e reiniciar ou
reimplantar os containers para carregar o novo valor. O token compartilhado dá
acesso a todos os datasets; não há permissões individuais por workspace.

## Validação e pendências

- FastAPI executado localmente com Uvicorn e ambiente Python isolado.
- Onze testes automatizados de API, conexão e consultas passando.
- Teste adicional de SQL via TEST_DATABASE_URL disponível, pulado sem banco de teste.
- SQL virtual validado separadamente em PostgreSQL em memória.
- Ruff, formatação e empacotamento do adaptador Cloudflare validados.
- Container Docker e execução Spark/Lakeflow ainda não verificados nos ambientes reais.
- Schema ativo Aiven pendente de CA. Nenhuma tabela removida ou procedure executada.
- Publicação e push não realizados; commits permanecem locais.
