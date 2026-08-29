# Publicação

## Estado atual

- Git local inicializado na branch `main`.
- Commit inicial criado.
- Remote configurado:

```text
<URL_DO_SEU_REPOSITORIO>.git
```

O push ainda depende de reautenticação do GitHub CLI, pois `gh auth status` retornou token inválido.

## Publicar no GitHub

1. Reautenticar o GitHub CLI:

```bash
gh auth login -h github.com
```

2. Criar o repositório remoto:

```bash
gh repo create seu-usuario/football-intelligence-platform --public
```

3. Enviar a branch local:

```bash
git push -u origin main
```

## Publicar no Render

1. Entrar no Render com a conta GitHub.
2. Criar um novo serviço usando o repositório `seu-usuario/football-intelligence-platform`.
3. Usar o `render.yaml` do projeto ou selecionar deploy via Docker.
4. Conferir se o health check está apontando para:

```text
/api/health
```

5. Após o deploy, abrir o endpoint público e testar:

```text
/api/health
/
/team/1
/future-ai
```

6. Atualizar o `README.md` com o endpoint final.

Endpoint sugerido caso o serviço no Render use o nome do `render.yaml`:

```text
https://football-intelligence-platform.onrender.com
```
