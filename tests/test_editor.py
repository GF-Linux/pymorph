from PySide6.QtCore import QPoint, QPointF, Qt
from PySide6.QtGui import QMouseEvent
import shiboken6
from PySide6.QtWidgets import QApplication, QComboBox, QLabel, QLineEdit, QPushButton, QWidget

from pymorph.editor import Editor
from pymorph.tela import Tela


def _item(editor, chave):
    raiz = editor.arvore.topLevelItem(0)
    return next(raiz.child(i) for i in range(raiz.childCount())
                if raiz.child(i).data(0, Qt.ItemDataRole.UserRole) == chave)


def _mouse(palco, tipo, x, y):
    botoes = Qt.MouseButton.LeftButton if tipo != QMouseEvent.Type.MouseButtonRelease else Qt.MouseButton.NoButton
    ev = QMouseEvent(tipo, QPointF(x, y), QPointF(palco.mapToGlobal(QPoint(x, y))), Qt.MouseButton.LeftButton,
                     botoes, Qt.KeyboardModifier.NoModifier)
    QApplication.sendEvent(palco, ev)


def test_gerar_arrastar_redimensionar_salvar(calculadora, app, config):
    editor = Editor(calculadora, config=config)
    assert editor.arvore.topLevelItem(0).text(0) == "calculadora.py"
    for nome in ("somar", "multiplicar", "dividir"):
        editor._gerar(_item(editor, f"calculadora.py:{nome}"))
    assert editor.modificado
    assert "3 de 3 botões ligados" in editor.statusBar().currentMessage()

    palco = editor.palco
    somar = editor.tela.elemento("botao_somar")
    x0, y0 = somar.x, somar.y
    _mouse(palco, QMouseEvent.Type.MouseButtonPress, x0 + 10, y0 + 10)
    assert palco.selecionado == "botao_somar"
    _mouse(palco, QMouseEvent.Type.MouseMove, x0 + 10 + 37, y0 + 10 + 3)    # encaixa na grade de 8
    _mouse(palco, QMouseEvent.Type.MouseButtonRelease, x0 + 47, y0 + 13)
    assert (somar.x, somar.y) == (x0 + 40, y0)
    assert palco.widgets["botao_somar"].x() == x0 + 40

    canto = (somar.x + somar.largura, somar.y + somar.altura)              # a alça de tamanho
    _mouse(palco, QMouseEvent.Type.MouseButtonPress, *canto)
    _mouse(palco, QMouseEvent.Type.MouseMove, canto[0] + 16, canto[1] + 12)
    _mouse(palco, QMouseEvent.Type.MouseButtonRelease, canto[0] + 16, canto[1] + 12)
    assert (somar.largura, somar.altura) == (136, 48)

    editor.salvar()
    assert not editor.modificado
    salva = Tela.carregar(calculadora)
    assert salva.elemento("botao_somar").x == x0 + 40
    assert set(salva.ligacoes) == {"botao_somar", "botao_multiplicar", "botao_dividir"}


def test_executar_abre_a_tela_que_funciona(calculadora, app, config):
    from PySide6.QtCore import QThreadPool
    editor = Editor(calculadora, config=config)
    editor._gerar(_item(editor, "calculadora.py:somar"))
    janela = editor.executar()
    assert janela.isWindow() and janela.parent() is editor
    janela.palco.findChild(QLineEdit, "campo_a").setText("2")
    janela.palco.findChild(QLineEdit, "campo_b").setText("3")
    janela.palco.findChild(QPushButton, "botao_somar").click()
    QThreadPool.globalInstance().waitForDone(5000)
    QApplication.processEvents()
    assert janela.palco.findChild(QLabel, "resultado").text() == "5"


def test_o_editor_le_de_novo_quando_o_arquivo_muda(calculadora, app, config):
    editor = Editor(calculadora, config=config)
    (calculadora / "calculadora.py").write_text("def subtrair(a: float, b: float) -> float:\n    return a - b\n")
    editor.ler_funcoes()        # o QFileSystemWatcher chama isto sozinho quando o arquivo é salvo
    assert list(editor.funcoes) == ["calculadora.py:subtrair"]


def test_painel_liga_um_botao_avulso(calculadora, app, config):
    editor = Editor(calculadora, config=config)
    for nome in ("campo_a", "campo_b", "resultado"):
        editor._adicionar("caixa")
        editor.tela.renomear("caixa", nome)
    editor.palco.reconstruir()                  # o painel faz isto ao renomear
    assert isinstance(editor.palco.widgets["campo_a"], QLabel)      # solta, a caixa é texto
    editor._adicionar("botao")
    editor.palco.selecionar("botao")
    editor.painel.mostrar("botao")
    # pela caixa, como a pessoa faz: escolher refaz o painel no meio do sinal da própria caixa, e
    # apagar a caixa ali derrubava o programa (SEGV no 0.0.1)
    escolha = next(c for c in editor.painel.widget().findChildren(QComboBox)
                   if c.findData("calculadora.py:multiplicar") >= 0)
    escolha.setCurrentIndex(escolha.findData("calculadora.py:multiplicar"))
    assert shiboken6.isValid(escolha)
    lig = editor.tela.ligacoes["botao"]
    assert lig.entradas == {"a": "campo_a", "b": "campo_b"} and lig.saida == "resultado"
    assert isinstance(editor.palco.widgets["campo_a"], QLineEdit)   # ligada como entrada, vira campo
    assert "fdf1e7" not in editor.palco.widgets["resultado"].styleSheet()

    nome = editor.painel.widget().findChild(QLineEdit)        # renomear também refaz tudo
    nome.setText("botao_vezes")
    nome.editingFinished.emit()
    assert shiboken6.isValid(nome) and "botao_vezes" in editor.tela.ligacoes


def test_refazer_o_palco_nao_deixa_widget_antigo_visivel(calculadora, app, config):
    editor = Editor(calculadora, config=config)
    for nome in ("somar", "multiplicar", "dividir"):
        editor._gerar(_item(editor, f"calculadora.py:{nome}"))     # cada geração refaz o palco
    visiveis = [w for w in editor.palco.findChildren(QLabel) if w.isVisibleTo(editor.palco) and w.text() == "A"]
    assert len(visiveis) == 1


def test_a_caixa_ajusta_letra_e_negrito(calculadora, app, config):
    from PySide6.QtWidgets import QCheckBox, QSpinBox
    editor = Editor(calculadora, config=config)
    editor._adicionar("caixa")
    editor.painel.mostrar("caixa")
    editor.painel.widget().findChildren(QSpinBox)[0].setValue(20)      # a primeira é a letra
    next(c for c in editor.painel.widget().findChildren(QCheckBox) if c.text() == "Negrito").setChecked(True)
    fonte = editor.palco.widgets["caixa"].font()
    assert (fonte.pointSize(), fonte.bold()) == (20, True)
    editor.salvar()
    caixa = Tela.carregar(calculadora).elemento("caixa")
    assert (caixa.fonte, caixa.negrito, caixa.texto) == (20, True, "Texto")


def test_a_caixa_escolhe_fonte_e_cores(calculadora, app, config):
    from pymorph.editor import familias_do_sistema
    editor = Editor(calculadora, config=config)
    editor._adicionar("caixa")
    editor.painel.mostrar("caixa")
    corpo = editor.painel.widget()
    fonte = next(c for c in corpo.findChildren(QComboBox) if c.findData("serif") >= 0)
    assert fonte.count() > len(familias_do_sistema())          # genéricas + as do sistema
    fonte.setCurrentIndex(fonte.findData("serif"))
    corpo.findChild(QWidget, "cor_cor").escolher("#b3261e")
    corpo.findChild(QWidget, "cor_fundo").escolher("#fff4d6")
    w = editor.palco.widgets["caixa"]
    assert w.font().family() == "serif" and "color: #b3261e" in w.styleSheet()
    editor.salvar()
    caixa = Tela.carregar(calculadora).elemento("caixa")
    assert (caixa.familia, caixa.cor, caixa.fundo) == ("serif", "#b3261e", "#fff4d6")
    corpo.findChild(QWidget, "cor_fundo").escolher("")          # o × volta ao padrão
    assert "background" not in editor.palco.widgets["caixa"].styleSheet()


def test_a_caixa_padrao_aparece_no_palco_em_qualquer_tema(calculadora, app, config):
    """A caixa nova (com "Texto", sem fundo nem borda) tem o contorno tracejado, e o palco tem o fundo da
    janela do sistema: com branco fixo, no tema escuro o texto saía branco sobre branco."""
    from PySide6.QtGui import QColor, QPalette
    original = QPalette(app.palette())
    escuro = QPalette(original)
    escuro.setColor(QPalette.ColorRole.Window, QColor("#202326"))
    escuro.setColor(QPalette.ColorRole.WindowText, QColor("#fcfcfc"))
    try:
        for paleta in (original, escuro):
            app.setPalette(paleta)      # o tema do sistema chega assim, pela aplicação
            editor = Editor(calculadora, config=config)
            editor._adicionar("caixa")
            e = editor.tela.elementos[-1]
            editor.palco.selecionado = None
            imagem = editor.palco.grab().toImage()
            fundo = QColor(imagem.pixel(e.x + e.largura + 20, e.y + e.altura // 2 + 1))
            assert fundo == paleta.color(QPalette.ColorRole.Window)
            borda = [QColor(imagem.pixel(e.x + e.largura // 2 + d, e.y)) for d in range(6)]
            assert any(c != fundo for c in borda)          # o tracejado na borda de cima
            letras = [QColor(imagem.pixel(x, y)) for x in range(e.x, e.x + 40) for y in range(e.y, e.y + e.altura)]
            assert any(abs(c.lightness() - fundo.lightness()) > 80 for c in letras)
    finally:
        app.setPalette(original)


def test_o_texto_do_png_nao_ganha_tracejado(calculadora, app, config):
    from pymorph.editor import Moldura
    from pymorph.tela import Elemento
    editor = Editor(calculadora, config=config)
    e = Elemento("caixa_1", "caixa", 300, 300, 120, 24, "[a preencher]")
    e.fundo = "transparent"
    editor.tela.elementos.append(e)
    editor.palco.reconstruir()
    editor.palco.selecionado = None
    imagem = editor.palco.grab().toImage()
    fundo = imagem.pixel(e.x + 60, e.y - 6)
    assert all(imagem.pixel(e.x + 60 + d, e.y) == fundo for d in range(6))
