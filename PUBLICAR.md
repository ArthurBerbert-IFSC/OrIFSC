# Como publicar uma nova versao do OrIFSC

A publicacao no [plugins.qgis.org](https://plugins.qgis.org) e **automatica** via GitHub Actions
([.github/workflows/release.yml](.github/workflows/release.yml)). Voce nao precisa mais rodar
`empacotar.py` (ele foi aposentado para `Antigos/`).

## Configuracao unica (so na primeira vez)

A autenticacao no plugins.qgis.org e por **token** (nao mais usuario/senha do OSGeo —
util quando o login no portal e via GitHub SSO e nao existe senha OSGeo tradicional).

1. Gere um token em [plugins.qgis.org](https://plugins.qgis.org), logado: **Perfil / Account**
   > secao de **API Token** > gerar e **copiar** (so e exibido uma vez).
2. GitHub > repositorio **OrIFSC** > **Settings** > **Secrets and variables** > **Actions**.
3. Em **Repository secrets** (nao "Variables", nao "Environment secrets") > **New repository secret**:
   - Name: `QGIS_TOKEN`
   - Secret: o token gerado no passo 1

> O `GITHUB_TOKEN` ja e fornecido automaticamente pelo Actions — nao precisa criar.
> Se o `QGIS_TOKEN` estiver ausente/vazio, o log da Action mostra `--qgis-token ""`
> (em vez de `***`) e o upload falha — confira que o secret existe com valor.

## Fluxo de cada release

1. Edite o codigo na pasta `OrIFSC/` (no VSCode).
2. Atualize a versao em [OrIFSC/metadata.txt](OrIFSC/metadata.txt) (campo `version=`).
3. Commit e push normais para o `main`.
4. Crie e empurre uma **tag** com o numero da versao (formato `X.Y.Z`, **sem** o `v`):

   ```bash
   git tag 0.1.6
   git push origin 0.1.6
   ```

5. O workflow dispara sozinho: **cria o GitHub Release** da tag (passo `gh release create`),
   empacota a pasta `OrIFSC/`, publica no plugins.qgis.org usando o `QGIS_TOKEN` e anexa o
   `.zip` ao Release.

> O Release precisa existir **antes** da publicacao (o qgis-plugin-ci com `--github-token`
> exige isso, senao falha com `GithubReleaseNotFound`). Por isso o workflow cria o Release
> automaticamente — voce nao precisa cria-lo a mao.

> A versao publicada e a **da tag** — entao a tag `0.1.6` publica como 0.1.6.
> Mantenha o `version=` do metadata.txt igual a tag para evitar confusao.

## Observacoes

- Apenas **dar `git push`** (sem tag) **nao** publica nada no QGIS — so atualiza o GitHub.
  A publicacao acontece **somente quando uma tag `X.Y.Z` e empurrada**.
- O upload no plugins.qgis.org passa por um scan de seguranca (Bandit). Evite `urllib`
  direto (B310) e `xml` inseguro (B314); prefira `QgsBlockingNetworkRequest` +
  `QXmlStreamReader`, senao o upload e bloqueado.
- Para **re-disparar** a mesma versao (ex.: corrigir uma publicacao que falhou), apague a
  tag e recrie no commit ja corrigido:

  ```bash
  git push origin :refs/tags/0.1.6   # apaga a tag remota
  git tag -d 0.1.6                    # apaga a tag local
  git tag 0.1.6                       # recria no HEAD corrigido
  git push origin 0.1.6              # dispara o workflow de novo
  ```
- Para desenvolver com hot-reload, rode [dev-setup.ps1](dev-setup.ps1) com o QGIS fechado:
  ele aponta a pasta de plugins do QGIS para a pasta `OrIFSC/` deste repo (junction, sem admin).
