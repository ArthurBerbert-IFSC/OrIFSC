"""Acesso à rede: download único pela rede do QGIS e download paralelo de muitos.

``baixar_bytes`` usa ``QgsBlockingNetworkRequest`` (respeita proxy/timeout do QGIS
e é seguro na thread de um algoritmo) para baixas avulsas — MDT, declinação, WMS.

``baixar_varios`` baixa muitas URLs em paralelo com um pool de threads + ``urllib``
(ver a explicação na própria função): é o que baixa as tiles do satélite sem
travar nem deixar gerenciadores de rede do QGIS órfãos.

Ambos só aceitam esquemas http(s) (evita file:// e afins).
"""
from qgis.core import QgsBlockingNetworkRequest
from qgis.PyQt.QtCore import QUrl
from qgis.PyQt.QtNetwork import QNetworkRequest
from typing import Callable, Dict, Iterable, Optional


def baixar_bytes(url: str, user_agent: str = 'OrIFSC') -> bytes:
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
    if err != QgsBlockingNetworkRequest.ErrorCode.NoError:
        raise RuntimeError(blocking.errorMessage())
    return bytes(blocking.reply().content())


def baixar_varios(
        urls: Iterable[str],
        user_agent: str = 'OrIFSC',
        max_conc: int = 12,
        cancelado: Optional[Callable[[], bool]] = None,
        progresso: Optional[Callable[[int, int], None]] = None,
        timeout_ms: int = 20000,
        tentativas: int = 3,
        heartbeat: Optional[Callable[[int, int, int], None]] = None) -> Dict[str, Optional[bytes]]:
    """Baixa várias URLs http(s) em paralelo (pool de threads + ``urllib``).

    Por que ``urllib`` e não a rede do QGIS aqui:
      - criar ``QgsNetworkAccessManager`` em threads Python deixa gerenciadores
        órfãos que travavam o QGIS ao fechar (bug antigo, do tempo do pool);
      - a alternativa de NAM único assíncrono (signal ``finished`` + ``QEventLoop``
        aninhado) NÃO entrega as respostas de forma confiável a partir da thread de
        um algoritmo de Processing — o download ficava preso em "0/N" e nem o
        Cancelar respondia (o ``abort`` também depende do ``finished``).
    Threads Python com ``urllib`` baixam de verdade, em paralelo, sem objetos de
    rede do QGIS (nada a orfanar) e respeitam o proxy do sistema
    (variáveis http_proxy / configuração do Windows).

    Robustez: ``timeout_ms`` por requisição (conexão travada falha em vez de
    pendurar) e re-tentativa (``tentativas``) das que falham, para a imagem sair
    completa mesmo sob throttling do Google. O cancelamento é checado a cada tile
    concluída e a cada nova tentativa, então responde em no máximo ~1 timeout.

    Retorna ``dict`` ``url -> bytes`` (ou ``None`` se esgotar as tentativas).
    Callables opcionais: ``cancelado()`` e ``progresso(concluidas, total)``.
    ``heartbeat`` é aceito por compatibilidade e ignorado (o progresso já flui a
    cada tile concluída).
    """
    import urllib.request
    from concurrent.futures import ThreadPoolExecutor, as_completed

    urls = list(urls)
    total = len(urls)
    resultados = {}
    if total == 0:
        return resultados

    timeout_s = max(1.0, timeout_ms / 1000.0)
    cabec = {'User-Agent': user_agent or 'OrIFSC'}
    n_tent = max(1, int(tentativas))

    def _baixar_uma(url: str) -> Optional[bytes]:
        """Baixa uma URL com retentativas e respeito ao cancelamento.

        Args:
            url: Endereço HTTP/HTTPS da tile.

        Returns:
            Optional[bytes]: Conteúdo baixado ou ``None`` em erro/cancelamento.
        """
        if not url.lower().startswith(('http://', 'https://')):
            return None
        for _ in range(n_tent):
            if cancelado and cancelado():
                return None
            try:
                req = urllib.request.Request(url, headers=cabec)
                with urllib.request.urlopen(req, timeout=timeout_s) as resp:  # nosec B310
                    return resp.read()
            except Exception:
                continue
        return None

    feitas = 0
    cancelando = False
    with ThreadPoolExecutor(max_workers=max(1, int(max_conc))) as executor:
        futuros = {executor.submit(_baixar_uma, u): u for u in urls}
        for fut in as_completed(futuros):
            url = futuros[fut]
            if fut.cancelled():
                resultados[url] = None
            else:
                try:
                    resultados[url] = fut.result()
                except Exception:
                    resultados[url] = None
            feitas += 1
            if progresso:
                progresso(feitas, total)
            if not cancelando and cancelado and cancelado():
                cancelando = True
                for f in futuros:
                    f.cancel()
    return resultados
