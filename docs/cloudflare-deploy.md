# Deploy Cloudflare

O workflow cloudflare.yml valida o Worker em PRs, sem credenciais de produção. Após os checks, publica somente pushes na main ou execução manual na main; mantém os workflows existentes. Deploys de produção são serializados.

O workflow publica o Worker JavaScript nativo usando `uv run --no-sync npm run
cloudflare:deploy`. Esse script usa `wrangler.edge.jsonc`, gera o contrato/SQL a
partir do catálogo Python e preserva as variáveis existentes com `--keep-vars`.
Isso evita voltar ao Worker Python anterior a cada merge, inclusive ao adicionar
novas fontes para a carga do Databricks.

As validações incluem Ruff, testes Python, `npm ci --ignore-scripts`, testes SQL
e `uv run --no-sync npm run cloudflare:deploy -- --dry-run`. O dry-run usa a mesma
configuração JavaScript da publicação; não publica uma versão nem precisa de
credenciais de produção. A instalação usa os lockfiles `uv.lock` e
`package-lock.json` existentes.

CLOUDFLARE_API_TOKEN fica nos secrets do repositório; CLOUDFLARE_ACCOUNT_ID é uma variável pública. O token é restrito à conta Astro, com Workers Scripts: Edit, e expira em 25/10/2027. Os secrets de aplicação, Hyperdrives e demais bindings existentes permanecem no Cloudflare; este workflow não importa arquivos .env nem provisiona conectores.

A configuração entra em vigor após a revisão e o merge desta PR. Nenhum deploy ocorre ao atualizar a branch da PR.

O uv.lock foi versionado com as dependências validadas. A CI usa uv sync --locked para rejeitar divergências entre os metadados e as versões travadas. Os testes instalam os extras local/dev apenas no ambiente de testes. O Python é usado no build para exportar o catálogo; o bundle publicado contém o Worker JavaScript e suas dependências de runtime.
