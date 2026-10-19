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


def test_o_papel_da_caixa_vem_das_ligacoes(calculadora):
    tela, _ = _calculadora(calculadora)
    ui = tela.para_ui()
    assert '<widget class="QLabel" name="titulo_a">' in ui          # ninguém usa: texto
    assert '<widget class="QLineEdit" name="campo_a">' in ui        # entrada
    assert '<widget class="QLabel" name="resultado">' in ui         # saída, com o estilo do resultado
    assert ui.count("styleSheet") == 1
    tela.ligacoes["botao_somar"].saida = "campo_a"                  # entrada e saída: o visor
    assert tela.papel("campo_a") == "entrada e saída"
    tela.remover("botao_multiplicar")
    tela.remover("botao_dividir")
    assert tela.papel("resultado") == "texto"                       # sem botão que mande nada para ela


def test_acao_nao_ganha_resultado(tmp_path):
    from pymorph.leitor import funcoes_por_chave, ler_pasta
    (tmp_path / "f.py").write_text("def abrir(pasta: str):\n    print(pasta)\n")
    tela = Tela()
    botao = gerar_da_funcao(tela, funcoes_por_chave(ler_pasta(tmp_path))["f.py:abrir"])
    assert [e.id for e in tela.elementos] == ["titulo_pasta", "campo_pasta", "botao_abrir"]
    assert tela.ligacoes[botao.id].saida is None


def test_abre_a_tela_da_versao_anterior(tmp_path):
    (tmp_path / "telas").mkdir()
    (tmp_path / "telas" / "principal.ui").write_text(
        '<ui version="4.0"><widget class="QWidget" name="principal">'
        '<property name="geometry"><rect><x>0</x><y>0</y><width>480</width><height>360</height></rect></property>'
        '<widget class="QLineEdit" name="campo_a"><property name="placeholderText"><string>0,00</string></property>'
        '<property name="pymorphTipo" stdset="0"><string>decimal</string></property></widget>'
        '<widget class="QLabel" name="resultado"><property name="text"><string>—</string></property>'
        '<property name="font"><font><pointsize>14</pointsize></font></property>'
        '<property name="pymorphTipo" stdset="0"><string>resultado</string></property></widget>'
        '</widget></ui>')
    tela = Tela.carregar(tmp_path)
    assert [(e.id, e.tipo, e.texto, e.fonte) for e in tela.elementos] == [
        ("campo_a", "caixa", "0,00", 0), ("resultado", "caixa", "—", 14)]
