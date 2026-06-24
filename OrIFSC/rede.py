"""Acesso à rede via QGIS (QgsBlockingNetworkRequest).

Usado por todo o plugin no lugar de ``urllib`` para que o download respeite as
configurações de rede do usuário (proxy, timeout) e para evitar abrir esquemas
de URL inesperados (file://, etc.).
"""
from qgis.core import QgsBlockingNetworkRequest
from qgis.PyQt.QtCore import QUrl
from qgis.PyQt.QtNetwork import QNetworkRequest


def baixar_bytes(url, user_agent='OrIFSC'):
    """Baixa o conteúdo de uma URL http(s) pela rede do QGIS.

    Retorna ``bytes``. Levanta ``ValueError`` para esquemas não permitidos e
    ``RuntimeError`` se a requisição falhar.
    """
    if not url.lower().startswith(('http://', 'https://')):
        raise ValueError(f'Esquema de URL não permitido: {url!r}')
    req = QNetworkRequest(QUrl(url))
    if user_agent:
        req.setRawHeader(b'User-Agent', user_agent.encode('ascii', 'ignore'))
    blocking = QgsBlockingNetworkRequest()
    err = blocking.get(req, forceRefresh=True)
    if err != QgsBlockingNetworkRequest.NoError:
        raise RuntimeError(blocking.errorMessage())
    return bytes(blocking.reply().content())
