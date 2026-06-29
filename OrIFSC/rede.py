"""Acesso à rede via QGIS (QgsBlockingNetworkRequest).

Usado por todo o plugin no lugar de ``urllib`` para que o download respeite as
configurações de rede do usuário (proxy, timeout) e para evitar abrir esquemas
de URL inesperados (file://, etc.).
"""
from qgis.core import QgsBlockingNetworkRequest, QgsNetworkAccessManager
from qgis.PyQt.QtCore import QUrl, QEventLoop
from qgis.PyQt.QtNetwork import QNetworkRequest, QNetworkReply


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


def baixar_varios(urls, user_agent='OrIFSC', max_conc=24,
                  cancelado=None, progresso=None):
    """Baixa várias URLs http(s) concorrentemente NA THREAD ATUAL.

    Usa o ``QgsNetworkAccessManager`` da thread atual de forma assíncrona (vários
    ``get()`` em voo + um ``QEventLoop`` aninhado), em vez de um pool de threads
    Python. Cada thread Python que chama a rede do QGIS cria um gerenciador de
    rede próprio que fica órfão ao fim da thread e trava o QGIS no fechamento;
    aqui há um só gerenciador (o da thread do algoritmo), limpo pelo QGIS.

    Retorna ``dict`` ``url -> bytes`` (ou ``None`` em falha). ``cancelado()`` e
    ``progresso(concluidas, total)`` são callables opcionais.
    """
    urls = list(urls)
    total = len(urls)
    resultados = {}
    if total == 0:
        return resultados

    nam = QgsNetworkAccessManager.instance()
    loop = QEventLoop()
    pendentes = list(reversed(urls))          # pop() retira do fim
    em_voo = {}                               # reply -> url
    estado = {'feitas': 0, 'parar': False}
    ua = user_agent.encode('ascii', 'ignore') if user_agent else b''

    def _concluir(url):
        estado['feitas'] += 1
        if progresso:
            progresso(estado['feitas'], total)

    def _lancar():
        while pendentes and len(em_voo) < max_conc and not estado['parar']:
            url = pendentes.pop()
            if not url.lower().startswith(('http://', 'https://')):
                resultados[url] = None
                _concluir(url)
                continue
            req = QNetworkRequest(QUrl(url))
            if ua:
                req.setRawHeader(b'User-Agent', ua)
            reply = nam.get(req)
            em_voo[reply] = url

    def _ao_terminar(reply):
        url = em_voo.pop(reply, None)
        if url is None:
            return                            # resposta de outra requisição
        if reply.error() == QNetworkReply.NetworkError.NoError:
            resultados[url] = bytes(reply.readAll())
        else:
            resultados[url] = None
        reply.deleteLater()
        _concluir(url)
        if cancelado and cancelado():
            estado['parar'] = True
        if estado['parar']:
            for u in pendentes:
                resultados.setdefault(u, None)
            pendentes.clear()
        if not em_voo and not pendentes:
            loop.quit()
        else:
            _lancar()

    nam.finished.connect(_ao_terminar)
    try:
        _lancar()
        if em_voo:
            loop.exec()
    finally:
        nam.finished.disconnect(_ao_terminar)
    return resultados
