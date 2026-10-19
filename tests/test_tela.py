import json

from pymorph.leitor import funcoes_por_chave, ler_pasta
from pymorph.tela import Tela, gerar_da_funcao


def _calculadora(pasta):
    funcoes = funcoes_por_chave(ler_pasta(pasta))
    tela = Tela()
    for nome in ("somar", "multiplicar", "dividir"):
        gerar_da_funcao(tela, funcoes[f"calculadora.py:{nome}"])
    return tela, funcoes


def test_gerar_reaproveita_campos_e_resultado(calculadora):
    tela, _ = _calculadora(calculadora)
    ids = [e.id for e in tela.elementos]
    assert ids.count("campo_a") == 1 and ids.count("campo_b") == 1 and ids.count("resultado") == 1
    botoes = [e for e in tela.elementos if e.tipo == "botao"]
    assert [b.texto for b in botoes] == ["Somar", "Multiplicar", "Dividir"]
    assert len({b.y for b in botoes}) == 1                      # os três na mesma linha
    assert tela.ligacoes["botao_dividir"].entradas == {"a": "campo_a", "b": "campo_b"}
    assert tela.ligacoes["botao_dividir"].saida == "resultado"
    resultado = tela.elemento("resultado")
    assert resultado.y >= botoes[0].y + botoes[0].altura       # o resultado não fica por baixo dos botões
    assert all(e.x + e.largura <= tela.largura and e.y + e.altura <= tela.altura for e in tela.elementos)


def test_salvar_e_carregar_devolve_a_mesma_tela(calculadora):
    tela, _ = _calculadora(calculadora)
    ui, json_ = tela.salvar(calculadora)
    assert ui == calculadora / "telas" / "principal.ui"
    assert json.loads(json_.read_text())["ligacoes"]["botao_somar"]["funcao"] == "calculadora.py:somar"
    de_novo = Tela.carregar(calculadora)
    assert de_novo == tela


def test_o_ui_leva_so_o_que_o_pymorph_controla(calculadora):
    tela, _ = _calculadora(calculadora)
    ui = tela.para_ui()
    # 9 widgets: geometria + texto + tipo em cada, e o estilo/fonte do resultado; nada das ~50 do Qt
    assert ui.count("<property") < 40
    assert 'name="pymorphTipo" stdset="0"' in ui


def test_o_qt_carrega_o_ui(calculadora, app):
    from PySide6.QtCore import QFile
    from PySide6.QtUiTools import QUiLoader
    from PySide6.QtWidgets import QPushButton
    tela, _ = _calculadora(calculadora)
    ui, _ = tela.salvar(calculadora)
    arquivo = QFile(str(ui))
    arquivo.open(QFile.ReadOnly)
    w = QUiLoader().load(arquivo)
    botao = w.findChild(QPushButton, "botao_somar")
    assert botao.text() == "Somar"
    assert botao.property("pymorphTipo") == "botao"
    assert (w.width(), w.height()) == (480, 360)


def test_renomear_e_remover_atualizam_as_ligacoes(calculadora):
    tela, _ = _calculadora(calculadora)
    assert tela.renomear("campo_a", "valor_a")
    assert tela.ligacoes["botao_somar"].entradas["a"] == "valor_a"
    assert not tela.renomear("valor_a", "campo_b")       # já existe
    assert not tela.renomear("valor_a", "2a")            # não é nome Python
    tela.remover("resultado")
    assert tela.ligacoes["botao_somar"].saida is None
    tela.remover("botao_somar")
    assert "botao_somar" not in tela.ligacoes
