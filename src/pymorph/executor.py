"""O executor: a tela como o usuário final vê, chamando as funções de verdade.

- o desenho vem do .ui salvo, pelo QUiLoader (o mesmo caminho que o Qt usa para o Designer);
- o arquivo do usuário só é importado aqui, na primeira chamada;
- cada chamada roda numa thread, para a janela não congelar num cálculo longo;
- o que foi digitado chega à função como o parâmetro pede (float, int, str); sem tipo, automático;
- erro da função vira aviso na caixa do resultado ou, numa ação sem resultado, numa janela de aviso;
  a janela continua aberta;
- a janela abre no tamanho desenhado e, depois, no último tamanho que o usuário deixou;
- redimensionar não escala nada: o desenho fica centralizado e a sobra vira margem;
- Ctrl + / Ctrl − / Ctrl 0 é o zoom: escala tudo, 1,2× por passo, como no VS Code.
"""
import hashlib
import importlib.util
import re
import sys
import traceback
from functools import partial
from pathlib import Path

from PySide6.QtCore import QFile, QObject, QPointF, QRect, QRunnable, QSettings, Qt, QThreadPool, Signal
from PySide6.QtGui import QColor, QKeySequence, QShortcut
from PySide6.QtUiTools import QUiLoader
from PySide6.QtWidgets import (QCheckBox, QGraphicsDropShadowEffect, QGridLayout, QLabel, QLineEdit, QMessageBox,
                               QPushButton, QWidget)

from pymorph.leitor import funcoes_por_chave, ler_pasta
from pymorph.tela import Tela, ler_sombra

PASSO_ZOOM = 1.2
ESTILO_AVISO = ("border: 1px solid #e8b48a; border-radius: 6px; padding: 6px; "
                "background: #fdf1e7; color: #7a3608;")


def aplicar_sombra(widget, sombra, escala=1.0):
    """A sombra do elemento: o QSS não tem box-shadow, o Qt tem o efeito de sombra."""
    valores = ler_sombra(sombra) if sombra else None
    if valores is None:
        widget.setGraphicsEffect(None)
        return
    dx, dy, desfoque, cor = valores
    efeito = QGraphicsDropShadowEffect(widget)
    efeito.setOffset(QPointF(dx * escala, dy * escala))
    efeito.setBlurRadius(desfoque * escala)
    efeito.setColor(QColor(cor))
    widget.setGraphicsEffect(efeito)


class EntradaInvalida(ValueError):
    pass


INTEIRO = re.compile(r"[+-]?\d+")
DECIMAL = re.compile(r"[+-]?(\d+[.,]\d*|[.,]\d+)")
SIM = {"sim", "s", "verdadeiro", "true", "1"}
NAO = {"não", "nao", "n", "falso", "false", "0", ""}


def converter(texto, tipo, nome="o campo"):
    """O que foi digitado na caixa, do jeito que o parâmetro pede (a anotação dele: 'float', 'int'…).
    Sem anotação, ou com uma que a tela não sabe ler, é automático: o que parece número vira
    número, o resto continua texto. Aceita vírgula decimal."""
    limpo = texto.strip()
    if tipo in ("float", "int") and not limpo:
        raise EntradaInvalida(f"falta preencher {nome}")
    if tipo == "float":
        try:
            return float(limpo.replace(",", "."))
        except ValueError:
            raise EntradaInvalida(f"“{texto}” não é um número") from None
    if tipo == "int":
        try:
            return int(limpo)
        except ValueError:
            raise EntradaInvalida(f"“{texto}” não é um número inteiro") from None
    if tipo == "str":
        return texto
    if tipo == "bool":
        if limpo.lower() in SIM | NAO:
            return limpo.lower() in SIM
        raise EntradaInvalida(f"“{texto}” não é sim nem não")
    if INTEIRO.fullmatch(limpo):
        return int(limpo)
    if DECIMAL.fullmatch(limpo):
        return float(limpo.replace(",", "."))
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
        self._aviso = None
        self.setWindowTitle(tela.nome.replace("_", " ").capitalize())

        ui, _ = tela.caminhos(self.pasta)
        arquivo = QFile(str(ui))
        arquivo.open(QFile.ReadOnly)
        self.palco = QUiLoader().load(arquivo, self)      # com pai: o Python não apaga o palco
        arquivo.close()
        filhos = self.palco.findChildren(QWidget, options=Qt.FindChildOption.FindDirectChildrenOnly)
        self._base = {w: (w.geometry(), w.font().pointSizeF()) for w in filhos}
        self._estilo = {w.objectName(): w.styleSheet() for w in filhos}     # para voltar depois de um aviso

        self._peles = {}
        if any(e.original for e in tela.elementos):
            self._vestir()

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

    def _vestir(self):
        """Os originais do Galaxy: a pele (navegador) no lugar do controle, que fica escondido e
        continua guardando o texto, a marcação e o clique."""
        from pymorph import web
        for e in self.tela.elementos:
            item = web.item(e.original) if e.original else None
            w = self.palco.findChild(QWidget, e.id)
            if item is None or w is None:
                continue
            pele = web.Pele(item, e.texto, self.palco)
            pele.setObjectName(f"pele_{e.id}")
            pele.setGeometry(w.geometry())
            w.hide()
            pele.show()
            self._base[pele] = (w.geometry(), 0.0)
            self._peles[e.id] = pele
            if e.tipo == "botao":
                pele.clicou.connect(partial(self.chamar, e.id))
            elif e.tipo == "caixa" and isinstance(w, QLineEdit):
                pele.mudou_valor.connect(w.setText)
            elif e.tipo == "marcar":
                pele.mudou_marcado.connect(w.setChecked)

    def _ativar(self, botao_id, ativo):
        botao = self.palco.findChild(QPushButton, botao_id)
        if botao is not None:
            botao.setEnabled(ativo)
        if botao_id in self._peles:
            self._peles[botao_id].ativar(ativo)

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
        for pele in self._peles.values():
            pele.setZoomFactor(f)
        for e in self.tela.elementos:
            if e.sombra:
                w = self.palco.findChild(QWidget, e.id)
                if w is not None:
                    aplicar_sombra(w, e.sombra, f)

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

    def _ler_campo(self, campo_id, parametro):
        w = self.palco.findChild(QWidget, campo_id)
        if isinstance(w, QCheckBox):
            return w.isChecked()
        if isinstance(w, (QLineEdit, QLabel)):
            return converter(w.text(), parametro.tipo, parametro.nome)
        raise EntradaInvalida(f"a caixa {campo_id} não existe na tela")

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
                        raise EntradaInvalida(f"o parâmetro {p.nome} não está ligado a nenhuma caixa")
                    continue
                argumentos[p.nome] = self._ler_campo(campo, p)
            chamavel = self._funcao(lig.funcao)
        except EntradaInvalida as e:
            self._falhou(botao_id, str(e), "")
            return
        except Exception as e:  # erro ao importar o arquivo do usuário
            self._falhou(botao_id, f"{type(e).__name__} ao abrir {lig.funcao.split(':')[0]}: {e}",
                         traceback.format_exc())
            return
        self._ativar(botao_id, False)
        QThreadPool.globalInstance().start(_Chamada(self.sinais, botao_id, chamavel, argumentos))

    def _saida(self, botao_id):
        """A caixa que mostra o resultado: só de mostrar (QLabel) ou a mesma em que se digita."""
        saida = self.tela.ligacoes[botao_id].saida
        return self.palco.findChild(QWidget, saida) if saida else None

    def _terminou(self, botao_id, valor):
        self._ativar(botao_id, True)
        caixa = self._saida(botao_id)
        if isinstance(caixa, QLabel):
            caixa.setStyleSheet(self._estilo.get(caixa.objectName(), ""))
            caixa.setToolTip("")
        if caixa is not None:
            caixa.setText(formatar(valor))
            if caixa.objectName() in self._peles:
                self._peles[caixa.objectName()].definir_valor(formatar(valor))

    def _falhou(self, botao_id, mensagem, detalhe):
        self._ativar(botao_id, True)
        caixa = self._saida(botao_id)
        if isinstance(caixa, QLabel):
            caixa.setStyleSheet(ESTILO_AVISO)
            caixa.setText(mensagem)
            caixa.setToolTip(detalhe)
            return
        # uma ação não tem resultado, e a caixa em que se digita não pode perder o que foi digitado
        self._aviso = QMessageBox(QMessageBox.Icon.Warning, self.windowTitle(), mensagem,
                                  QMessageBox.StandardButton.Ok, self)
        if detalhe:
            self._aviso.setDetailedText(detalhe)
        self._aviso.open()

    # ── fechar ────────────────────────────────────────────────────────────

    def closeEvent(self, evento):
        self.config.setValue(self.chave_config, self.saveGeometry())
        super().closeEvent(evento)


def abrir(pasta, nome="principal", parent=None, config=None):
    tela = Tela.carregar(pasta, nome)
    return Janela(pasta, tela, parent=parent, config=config)
