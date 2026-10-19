"""O executor: a tela como o usuário final vê, chamando as funções de verdade.

- o desenho vem do .ui salvo, pelo QUiLoader (o mesmo caminho que o Qt usa para o Designer);
- o arquivo do usuário só é importado aqui, na primeira chamada;
- cada chamada roda numa thread, para a janela não congelar num cálculo longo;
- erro da função vira aviso no resultado; a janela continua aberta;
- a janela abre no tamanho desenhado e, depois, no último tamanho que o usuário deixou;
- redimensionar não escala nada: o desenho fica centralizado e a sobra vira margem;
- Ctrl + / Ctrl − / Ctrl 0 é o zoom: escala tudo, 1,2× por passo, como no VS Code.
"""
import hashlib
import importlib.util
import sys
import traceback
from functools import partial
from pathlib import Path

from PySide6.QtCore import QFile, QObject, QRect, QRunnable, QSettings, Qt, QThreadPool, Signal
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtUiTools import QUiLoader
from PySide6.QtWidgets import QCheckBox, QGridLayout, QLabel, QLineEdit, QPushButton, QWidget

from pymorph.leitor import funcoes_por_chave, ler_pasta
from pymorph.tela import ESTILO_RESULTADO, Tela

PASSO_ZOOM = 1.2
ESTILO_AVISO = ("border: 1px solid #e8b48a; border-radius: 6px; padding: 6px; "
                "background: #fdf1e7; color: #7a3608;")


class EntradaInvalida(ValueError):
    pass


def converter(texto, controle):
    """O texto do campo no tipo que a função pediu. Aceita vírgula decimal."""
    if controle == "decimal":
        try:
            return float(texto.strip().replace(",", "."))
        except ValueError:
            raise EntradaInvalida(f"“{texto}” não é um número") from None
    if controle == "inteiro":
        try:
            return int(texto.strip())
        except ValueError:
            raise EntradaInvalida(f"“{texto}” não é um número inteiro") from None
    return texto


def formatar(valor):
    if isinstance(valor, float):
        return f"{valor:.10g}".replace(".", ",")
    if valor is None:
        return "—"
    return str(valor)


class _Sinais(QObject):
    terminou = Signal(str, object)      # id do botão, valor devolvido
    falhou = Signal(str, str, str)      # id do botão, mensagem, traceback


class _Chamada(QRunnable):
    def __init__(self, sinais, botao, funcao, argumentos):
        super().__init__()
        self.sinais, self.botao, self.funcao, self.argumentos = sinais, botao, funcao, argumentos

    def run(self):
        try:
            valor = self.funcao(**self.argumentos)
        except Exception as e:  # o erro é do código do usuário: vira aviso, não derruba a janela
            self.sinais.falhou.emit(self.botao, f"{type(e).__name__}: {e}", traceback.format_exc())
        else:
            self.sinais.terminou.emit(self.botao, valor)


class Janela(QWidget):
    def __init__(self, pasta, tela, funcoes=None, config=None, parent=None):
        super().__init__(parent)
        if parent is not None:      # aberta pelo editor: janela própria, mas com dono
            self.setWindowFlag(Qt.WindowType.Window)
        self.pasta = Path(pasta).resolve()
        self.tela = tela
        self.funcoes = funcoes if funcoes is not None else funcoes_por_chave(ler_pasta(self.pasta))
        self.config = config or QSettings("PyMorph", "pymorph")
        self.chave_config = "janelas/" + hashlib.sha1(f"{self.pasta}|{tela.nome}".encode()).hexdigest()[:12]
        self.zoom = 0
        self._modulos = {}
        self.setWindowTitle(tela.nome.replace("_", " ").capitalize())

        ui, _ = tela.caminhos(self.pasta)
        arquivo = QFile(str(ui))
        arquivo.open(QFile.ReadOnly)
        self.palco = QUiLoader().load(arquivo, self)      # com pai: o Python não apaga o palco
        arquivo.close()
        filhos = self.palco.findChildren(QWidget, options=Qt.FindChildOption.FindDirectChildrenOnly)
        self._base = {w: (w.geometry(), w.font().pointSizeF()) for w in filhos}

        grade = QGridLayout(self)
        grade.setContentsMargins(0, 0, 0, 0)
        grade.addWidget(self.palco, 1, 1)
        for i in (0, 2):
            grade.setRowStretch(i, 1)
            grade.setColumnStretch(i, 1)
        self._aplicar_zoom()

        self.sinais = _Sinais(self)
        self.sinais.terminou.connect(self._terminou)
        self.sinais.falhou.connect(self._falhou)
        for botao_id in tela.ligacoes:
            botao = self.palco.findChild(QPushButton, botao_id)
            if botao is not None:
                botao.clicked.connect(partial(self.chamar, botao_id))

        for teclas, passo in ((QKeySequence.ZoomIn, 1), ("Ctrl+=", 1), (QKeySequence.ZoomOut, -1), ("Ctrl+0", None)):
            QShortcut(QKeySequence(teclas), self, activated=partial(self.mudar_zoom, passo))

        geometria = self.config.value(self.chave_config)
        if geometria is None or not self.restoreGeometry(geometria):
            self.resize(tela.largura, tela.altura)
            self._abrir_maximizada = tela.tamanho == "cheia"
        else:
            self._abrir_maximizada = False

    def mostrar(self):
        self.showMaximized() if self._abrir_maximizada else self.show()

    # ── zoom ──────────────────────────────────────────────────────────────

    def mudar_zoom(self, passo):
        self.zoom = 0 if passo is None else max(-4, min(6, self.zoom + passo))
        self._aplicar_zoom()

    def _aplicar_zoom(self):
        f = PASSO_ZOOM ** self.zoom
        self.palco.setFixedSize(round(self.tela.largura * f), round(self.tela.altura * f))
        for w, (g, ponto) in self._base.items():
            w.setGeometry(QRect(round(g.x() * f), round(g.y() * f), round(g.width() * f), round(g.height() * f)))
            fonte = w.font()
            if ponto > 0:
                fonte.setPointSizeF(ponto * f)
                w.setFont(fonte)

    # ── chamar a função ───────────────────────────────────────────────────

    def _funcao(self, chave):
        arquivo, nome = chave.rsplit(":", 1)
        if arquivo not in self._modulos:
            caminho = self.pasta / arquivo
            if str(self.pasta) not in sys.path:
                sys.path.insert(0, str(self.pasta))
            spec = importlib.util.spec_from_file_location(f"pymorph_usuario_{caminho.stem}_{id(self)}", caminho)
            modulo = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(modulo)
            self._modulos[arquivo] = modulo
        return getattr(self._modulos[arquivo], nome)

    def _ler_campo(self, campo_id, controle):
        w = self.palco.findChild(QWidget, campo_id)
        if isinstance(w, QCheckBox):
            return w.isChecked()
        if isinstance(w, QLineEdit):
            return converter(w.text(), controle)
        raise EntradaInvalida(f"o campo {campo_id} não existe na tela")

    def chamar(self, botao_id):
        lig = self.tela.ligacoes[botao_id]
        funcao = self.funcoes.get(lig.funcao)
        if funcao is None:
            self._falhou(botao_id, f"a função {lig.funcao} não foi encontrada no projeto", "")
            return
        argumentos = {}
        try:
            for p in funcao.parametros:
                campo = lig.entradas.get(p.nome)
                if campo is None:
                    if p.padrao is None:
                        raise EntradaInvalida(f"o parâmetro {p.nome} não está ligado a nenhum campo")
                    continue
                argumentos[p.nome] = self._ler_campo(campo, p.controle)
            chamavel = self._funcao(lig.funcao)
        except EntradaInvalida as e:
            self._falhou(botao_id, str(e), "")
            return
        except Exception as e:  # erro ao importar o arquivo do usuário
            self._falhou(botao_id, f"{type(e).__name__} ao abrir {lig.funcao.split(':')[0]}: {e}",
                         traceback.format_exc())
            return
        self.palco.findChild(QPushButton, botao_id).setEnabled(False)
        QThreadPool.globalInstance().start(_Chamada(self.sinais, botao_id, chamavel, argumentos))

    def _saida(self, botao_id):
        saida = self.tela.ligacoes[botao_id].saida
        return self.palco.findChild(QLabel, saida) if saida else None

    def _terminou(self, botao_id, valor):
        self.palco.findChild(QPushButton, botao_id).setEnabled(True)
        rotulo = self._saida(botao_id)
        if rotulo is not None:
            rotulo.setStyleSheet(ESTILO_RESULTADO)
            rotulo.setToolTip("")
            rotulo.setText(formatar(valor))

    def _falhou(self, botao_id, mensagem, detalhe):
        botao = self.palco.findChild(QPushButton, botao_id)
        if botao is not None:
            botao.setEnabled(True)
        rotulo = self._saida(botao_id)
        if rotulo is not None:
            rotulo.setStyleSheet(ESTILO_AVISO)
            rotulo.setText(mensagem)
            rotulo.setToolTip(detalhe)
        else:
            print(f"pymorph: {mensagem}", file=sys.stderr)

    # ── fechar ────────────────────────────────────────────────────────────

    def closeEvent(self, evento):
        self.config.setValue(self.chave_config, self.saveGeometry())
        super().closeEvent(evento)


def abrir(pasta, nome="principal", parent=None, config=None):
    tela = Tela.carregar(pasta, nome)
    return Janela(pasta, tela, parent=parent, config=config)
