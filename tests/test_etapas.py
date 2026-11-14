"""Etapas do Assistente (acoes/etapas.py): feito / próximo / atenção /
desatualizado, sem nunca bloquear."""


def _estados(etapas, **situacao):
    lista = etapas.calcular_etapas(etapas.Situacao(**situacao))
    return {e.id: e.estado for e in lista}


def test_projeto_novo_sugere_definir_local(etapas):
    est = _estados(etapas)
    assert est['local'] == etapas.PROXIMO
    assert est['ajustar'] == etapas.OPCIONAL
    assert est['limite'] == etapas.OPCIONAL
    assert [est[i] for i in ('fundo', 'curvas', 'exportar')] == \
        [etapas.PENDENTE] * 3


def test_ordem_e_acoes_sempre_disponiveis(etapas):
    lista = etapas.calcular_etapas(etapas.Situacao())
    assert [e.id for e in lista] == ['local', 'ajustar', 'fundo', 'limite',
                                     'curvas', 'exportar']
    # Guia sem travar: toda etapa tem pelo menos uma ação clicável.
    assert all(e.acoes for e in lista)


def test_caminho_principal_avanca(etapas):
    base = dict(tem_folha=True, folha_girada=True)
    assert _estados(etapas, **base)['fundo'] == etapas.PROXIMO
    base['tem_fundo'] = True
    est = _estados(etapas, **base)
    assert (est['local'], est['fundo'], est['curvas']) == \
        (etapas.FEITO, etapas.FEITO, etapas.PROXIMO)
    base['tem_curvas'] = True
    assert _estados(etapas, **base)['exportar'] == etapas.PROXIMO


def test_fundo_e_recomendado_mas_nao_bloqueia(etapas):
    # Sem fundo, mas com curvas: o ▶ fica no fundo e as curvas aparecem feitas.
    est = _estados(etapas, tem_folha=True, folha_girada=True,
                   tem_curvas=True)
    assert est['fundo'] == etapas.PROXIMO
    assert est['curvas'] == etapas.FEITO


def test_folha_da_versao_antiga_pede_atencao(etapas):
    lista = etapas.calcular_etapas(etapas.Situacao(tem_folha=True))
    local = lista[0]
    assert local.estado == etapas.AVISO
    assert ('Ajustar folha', 'ajustar_folha') in local.acoes


def test_curvas_desatualizadas_quando_a_folha_muda(etapas):
    s = dict(tem_folha=True, folha_girada=True, tem_fundo=True,
             tem_curvas=True, folha_revisao=3, curvas_folha_revisao=2,
             curvas_geracao=1)
    assert _estados(etapas, **s)['curvas'] == etapas.AVISO
    s['curvas_folha_revisao'] = 3
    assert _estados(etapas, **s)['curvas'] == etapas.FEITO


def test_curvas_sem_registro_contam_como_em_dia(etapas):
    # Curvas de um projeto antigo (sem marca de revisão): não alarmar.
    est = _estados(etapas, tem_folha=True, folha_girada=True,
                   tem_curvas=True, folha_revisao=5)
    assert est['curvas'] == etapas.FEITO


def test_exportacao_em_dia_e_desatualizada(etapas):
    s = dict(tem_folha=True, folha_girada=True, tem_fundo=True,
             tem_curvas=True, folha_revisao=2, curvas_folha_revisao=2,
             curvas_geracao=4, exportado=True, exportacao_folha_revisao=2,
             exportacao_curvas_geracao=4, exportacao_pasta='C:/mapas/parque')
    lista = etapas.calcular_etapas(etapas.Situacao(**s))
    assert lista[-1].estado == etapas.FEITO
    assert 'C:/mapas/parque' in lista[-1].detalhe
    # Folha ajustada depois da exportação.
    assert _estados(etapas, **dict(s, folha_revisao=3))['exportar'] == \
        etapas.AVISO
    # Curvas geradas de novo depois da exportação.
    assert _estados(etapas, **dict(s, curvas_geracao=5))['exportar'] == \
        etapas.AVISO


def test_limite_desenhado_oferece_encaixar_folha(etapas):
    lista = etapas.calcular_etapas(etapas.Situacao(
        tem_folha=True, folha_girada=True, tem_limite=True))
    limite = [e for e in lista if e.id == 'limite'][0]
    assert limite.estado == etapas.FEITO
    assert ('Encaixar folha no limite', 'ajustar_folha') in limite.acoes


def test_no_maximo_um_proximo(etapas):
    for s in (etapas.Situacao(), etapas.Situacao(tem_folha=True,
                                                 folha_girada=True)):
        estados = [e.estado for e in etapas.calcular_etapas(s)]
        assert estados.count(etapas.PROXIMO) == 1


def test_aviso_no_caminho_segura_o_proximo(etapas):
    # Curvas desatualizadas: não sugerir exportar com curvas velhas.
    est = _estados(etapas, tem_folha=True, folha_girada=True, tem_fundo=True,
                   tem_curvas=True, folha_revisao=2, curvas_folha_revisao=1)
    assert est['curvas'] == etapas.AVISO
    assert est['exportar'] == etapas.PENDENTE
    assert etapas.PROXIMO not in est.values()
    # Folha da versão antiga: o aviso no local vem antes do fundo.
    est = _estados(etapas, tem_folha=True)
    assert est['local'] == etapas.AVISO and est['fundo'] == etapas.PENDENTE
