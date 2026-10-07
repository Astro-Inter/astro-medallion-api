# Implantação e operação (SCRUM-430)

A API é Python/FastAPI. O Dockerfile instala as dependências fixadas e
executa Uvicorn na porta 8080 com usuário sem privilégios.

O adaptador Cloudflare e a configuração Wrangler foram removidos junto
com a pasta `integrations`, a pedido do usuário. Não há configuração pronta
para publicar no Cloudflare no estado atual do projeto.

## Configuração do serviço

Fornecer `API_TOKEN` e `DATABASE_URL` por secrets do ambiente de execução.
Para bancos com CA privada, configurar `DATABASE_SSL_CA` ou
`DATABASE_SSL_CA_FILE`. As opções disponíveis estão em `.env.example`.
Não incluir `.env` na imagem nem no controle de versão.

Usar HTTPS na URL pública. `/docs` e `/openapi.json` são públicos para
carregar o Swagger; as rotas de dados e `/health` exigem o token Bearer.

A execução completa do container e a publicação exigem validação no ambiente
de destino. Nenhuma implantação foi executada.
