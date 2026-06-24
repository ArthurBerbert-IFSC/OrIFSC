# Como publicar uma nova versao do OrIFSC

A publicacao no [plugins.qgis.org](https://plugins.qgis.org) e **automatica** via GitHub Actions
([.github/workflows/release.yml](.github/workflows/release.yml)). Voce nao precisa mais rodar
`empacotar.py` (ele foi aposentado para `Antigos/`).

## Configuracao unica (so na primeira vez)

Adicione suas credenciais do OSGeo como *secrets* do repositorio no GitHub:

1. GitHub > repositorio **OrIFSC** > **Settings** > **Secrets and variables** > **Actions**
2. **New repository secret** e crie os dois:
   - `OSGEO_USERNAME` = seu usuario do OSGeo (o mesmo de login no plugins.qgis.org)
   - `OSGEO_PASSWORD` = sua senha do OSGeo

> O `GITHUB_TOKEN` ja e fornecido automaticamente pelo Actions — nao precisa criar.

## Fluxo de cada release

1. Edite o codigo na pasta `OrIFSC/` (no VSCode).
2. Atualize a versao em [OrIFSC/metadata.txt](OrIFSC/metadata.txt) (campo `version=`).
3. Commit e push normais para o `main`.
4. Crie e empurre uma **tag** com o numero da versao (formato `X.Y.Z`, **sem** o `v`):

   ```bash
   git tag 0.1.6
   git push origin 0.1.6
   ```

5. O workflow dispara sozinho: empacota a pasta `OrIFSC/`, publica no plugins.qgis.org
   e anexa o `.zip` ao Release da tag no GitHub.

> A versao publicada e a **da tag** — entao a tag `0.1.6` publica como 0.1.6.
> Mantenha o `version=` do metadata.txt igual a tag para evitar confusao.

## Observacoes

- Apenas **dar `git push`** (sem tag) **nao** publica nada no QGIS — so atualiza o GitHub.
  A publicacao acontece **somente quando uma tag `X.Y.Z` e empurrada**.
- O upload no plugins.qgis.org passa por um scan de seguranca (Bandit). Evite `urllib`
  direto (B310) e `xml` inseguro (B314); prefira `QgsBlockingNetworkRequest` +
  `QXmlStreamReader`, senao o upload e bloqueado.
- Para desenvolver com hot-reload, rode [dev-setup.ps1](dev-setup.ps1) com o QGIS fechado:
  ele aponta a pasta de plugins do QGIS para a pasta `OrIFSC/` deste repo (junction, sem admin).
