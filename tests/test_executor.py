from PySide6.QtCore import QThreadPool
from PySide6.QtWidgets import QApplication, QLabel, QLineEdit, QPushButton

from pymorph.executor import Janela, abrir, converter, formatar
from pymorph.leitor import funcoes_por_chave, ler_pasta
from pymorph.tela import Tela, gerar_da_funcao


def _salvar_calculadora(pasta):
    funcoes = funcoes_por_chave(ler_pasta(pasta))
    tela = Tela()
    for nome in ("somar", "multiplicar", "dividir"):
        gerar_da_funcao(tela, funcoes[f"calculadora.py:{nome}"])
    tela.salvar(pasta)


def _clicar(janela, botao, a, b):
    janela.palco.findChild(QLineEdit, "campo_a").setText(a)
    janela.palco.findChild(QLineEdit, "campo_b").setText(b)
    janela.palco.findChild(QPushButton, botao).click()
    QThreadPool.globalInstance().waitForDone(5000)
    QApplication.processEvents()
    return janela.palco.findChild(QLabel, "resultado").text()


def test_converter_e_formatar():
    assert converter("7,5", "float") == 7.5
    assert converter(" 3 ", "int") == 3
    assert converter("007", "str") == "007"
    assert converter("sim", "bool") is True and converter("não", "bool") is False
    # sem tipo: o que parece número vira número; o resto continua texto
    assert converter("2", None) == 2 and converter("7,5", None) == 7.5 and converter("-0.5", "list") == -0.5
    assert converter("ab", None) == "ab" and converter("inf", None) == "inf" and converter("", None) == ""
    assert formatar(16.0) == "16" and formatar(3.75) == "3,75" and formatar(None) == "—"


def test_a_calculadora_calcula(calculadora, config):
    _salvar_calculadora(calculadora)
    janela = abrir(calculadora, config=config)
    assert _clicar(janela, "botao_somar", "12", "4") == "16"
    assert _clicar(janela, "botao_multiplicar", "7,5", "2") == "15"
    assert _clicar(janela, "botao_dividir", "1", "4") == "0,25"


def test_erro_vira_aviso_e_a_janela_continua(calculadora, config):
    _salvar_calculadora(calculadora)
    janela = abrir(calculadora, config=config)
    assert _clicar(janela, "botao_dividir", "1", "0").startswith("ZeroDivisionError: ")
    assert "fdf1e7" in janela.palco.findChild(QLabel, "resultado").styleSheet()
    assert _clicar(janela, "botao_somar", "abc", "1") == "“abc” não é um número"
    assert _clicar(janela, "botao_somar", "1", "1") == "2"           # voltou ao normal
    assert janela.palco.findChild(QPushButton, "botao_dividir").isEnabled()


def test_o_codigo_editado_vale_na_proxima_janela(calculadora, config):
    _salvar_calculadora(calculadora)
    assert _clicar(abrir(calculadora, config=config), "botao_somar", "1", "1") == "2"
    arquivo = calculadora / "calculadora.py"
    arquivo.write_text(arquivo.read_text().replace("return a + b", "return a + b + 100"))
    assert _clicar(abrir(calculadora, config=config), "botao_somar", "1", "1") == "102"


def test_abre_no_tamanho_desenhado_e_depois_no_ultimo(calculadora, config):
    _salvar_calculadora(calculadora)
    janela = abrir(calculadora, config=config)
    assert (janela.width(), janela.height()) == (480, 360)
    janela.show()
    janela.resize(700, 500)
    QApplication.processEvents()
    janela.close()
    de_novo = abrir(calculadora, config=config)
    assert (de_novo.width(), de_novo.height()) == (700, 500)


def test_redimensionar_nao_escala_e_o_zoom_escala(calculadora, config):
    _salvar_calculadora(calculadora)
    janela = abrir(calculadora, config=config)
    janela.show()
    botao = janela.palco.findChild(QPushButton, "botao_somar")
    largura = botao.width()
    janela.resize(1200, 800)
    QApplication.processEvents()
    assert botao.width() == largura                       # a janela cresceu, o botão não
    assert janela.palco.size().toTuple() == (480, 360)
    assert janela.palco.x() > 0                           # o desenho fica no meio; a sobra vira margem
    janela.mudar_zoom(1)
    assert botao.width() == round(largura * 1.2)
    assert janela.palco.size().toTuple() == (576, 432)
    janela.mudar_zoom(None)
    assert botao.width() == largura


def test_tela_cheia_abre_maximizada_na_primeira_vez(calculadora, config):
    funcoes = funcoes_por_chave(ler_pasta(calculadora))
    tela = Tela()
    tela.mudar_tamanho("cheia")
    gerar_da_funcao(tela, funcoes["calculadora.py:somar"])
    tela.salvar(calculadora)
    janela = Janela(calculadora, Tela.carregar(calculadora), config=config)
    assert janela._abrir_maximizada


def _rodar(pasta, codigo, chave, valores, config):
    (pasta / "f.py").write_text(codigo)
    funcoes = funcoes_por_chave(ler_pasta(pasta))
    tela = Tela()
    botao = gerar_da_funcao(tela, funcoes[chave])
    tela.salvar(pasta)
    janela = abrir(pasta, config=config)
    for campo, valor in valores.items():
        janela.palco.findChild(QLineEdit, campo).setText(valor)
    janela.palco.findChild(QPushButton, botao.id).click()
    QThreadPool.globalInstance().waitForDone(5000)
    QApplication.processEvents()
    return janela


def test_sem_tipo_numero_soma_e_texto_junta(tmp_path, config):
    codigo = "def calculadora(a, b):\n    return a + b\n"
    janela = _rodar(tmp_path, codigo, "f.py:calculadora", {"campo_a": "2", "campo_b": "3"}, config)
    assert janela.palco.findChild(QLabel, "resultado").text() == "5"
    janela = _rodar(tmp_path, codigo, "f.py:calculadora", {"campo_a": "ab", "campo_b": "cd"}, config)
    assert janela.palco.findChild(QLabel, "resultado").text() == "abcd"


def test_a_acao_roda_e_o_erro_dela_vira_janela_de_aviso(tmp_path, config):
    marca = tmp_path / "feito.txt"
    codigo = f"from pathlib import Path\ndef marcar(texto: str):\n    Path({str(marca)!r}).write_text(texto)\n"
    janela = _rodar(tmp_path, codigo, "f.py:marcar", {"campo_texto": "ok"}, config)
    assert marca.read_text() == "ok" and janela._aviso is None
    codigo = "def falhar(x):\n    raise OSError('a pasta não existe')\n"
    janela = _rodar(tmp_path, codigo, "f.py:falhar", {"campo_x": "1"}, config)
    assert janela._aviso.text() == "OSError: a pasta não existe"
    assert "Traceback" in janela._aviso.detailedText()
