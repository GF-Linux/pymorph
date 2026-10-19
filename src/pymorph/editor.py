"""O editor: onde quem programa desenha a tela e liga cada botão a uma função.

À esquerda, as funções do projeto (lidas pelo ast, sem executar) e os controles; no meio, o palco,
onde tudo se arrasta e redimensiona; à direita, as propriedades e a ligação do que está selecionado.
O seu código nunca é escrito: o editor só grava em telas/.
"""
from pathlib import Path

from PySide6.QtCore import QFileSystemWatcher, QPoint, QRect, Qt, Signal
from PySide6.QtGui import QAction, QColor, QFont, QKeySequence, QPainter, QPen
from PySide6.QtWidgets import (QCheckBox, QComboBox, QFormLayout, QGridLayout, QLabel, QLineEdit,
                               QMainWindow, QMessageBox, QPushButton, QScrollArea, QSpinBox, QSplitter,
                               QToolBar, QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget)

from pymorph import __version__, executor
from pymorph.leitor import funcoes_por_chave, ler_pasta
from pymorph.tela import (CAMPOS, ESTILO_RESULTADO, NOME_TAMANHO, NOME_TIPO, PONTOS_RESULTADO, TAMANHOS,
                          Ligacao, Tela, gerar_da_funcao)

GRADE = 8           # o arrasto encaixa de 8 em 8 px; com Shift, livre
AZUL = QColor("#1f5fbf")
LARANJA = QColor("#b5560f")


def _encaixar(valor, livre=False):
    return valor if livre else round(valor / GRADE) * GRADE


def descartar(widget):
    """Some na hora e o Qt apaga depois. Só o deleteLater deixaria o antigo visível por baixo do novo
    até o laço de eventos rodar: o texto sairia desenhado duas vezes."""
    widget.hide()
    widget.deleteLater()


def criar_widget(elemento, pai):
    """O widget de verdade, como vai aparecer para o usuário final, mas sem receber clique."""
    if elemento.tipo == "botao":
        w = QPushButton(elemento.texto, pai)
    elif elemento.tipo == "marcar":
        w = QCheckBox(elemento.texto, pai)
    elif elemento.tipo in CAMPOS:
        w = QLineEdit(pai)
        w.setPlaceholderText(elemento.texto)
    else:
        w = QLabel(elemento.texto, pai)
        if elemento.tipo == "resultado":
            w.setStyleSheet(ESTILO_RESULTADO)
            w.setWordWrap(True)
            fonte = w.font()
            fonte.setPointSize(PONTOS_RESULTADO)
            w.setFont(fonte)
    w.setObjectName(elemento.id)
    w.setGeometry(elemento.x, elemento.y, elemento.largura, elemento.altura)
    w.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
    w.setFocusPolicy(Qt.FocusPolicy.NoFocus)
    w.show()
    return w


class Moldura(QWidget):
    """Camada por cima do palco: a seleção, a alça de tamanho e a marca de botão ligado."""

    def __init__(self, palco):
        super().__init__(palco)
        self.palco = palco
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        tela = self.palco.tela
        for e in tela.elementos:
            if e.tipo == "botao":
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(AZUL if e.id in tela.ligacoes else LARANJA)
                p.drawEllipse(QPoint(e.x + e.largura - 4, e.y + 4), 4, 4)
        e = tela.elemento(self.palco.selecionado)
        if e is not None:
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.setPen(QPen(AZUL, 2))
            p.drawRect(QRect(e.x - 3, e.y - 3, e.largura + 6, e.altura + 6))
            p.setBrush(AZUL)
            p.setPen(Qt.PenStyle.NoPen)
            p.drawRect(QRect(e.x + e.largura - 2, e.y + e.altura - 2, 8, 8))


class Palco(QWidget):
    selecionou = Signal(object)     # id selecionado, ou None
    mudou = Signal()                # posição ou tamanho mudou pelo mouse/teclado

    def __init__(self, tela, parent=None):
        super().__init__(parent)
        self.tela = tela
        self.selecionado = None
        self.widgets = {}
        self._arrasto = None
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.moldura = Moldura(self)
        self.reconstruir()

    def reconstruir(self):
        for w in self.widgets.values():
            descartar(w)
        self.widgets = {e.id: criar_widget(e, self) for e in self.tela.elementos}
        self.setFixedSize(self.tela.largura, self.tela.altura)
        self.moldura.setGeometry(self.rect())
        self.moldura.raise_()
        self.moldura.update()

    def atualizar(self, id_):
        """Refaz um elemento só (depois de mudar texto, tipo, posição ou tamanho)."""
        if id_ in self.widgets:
            descartar(self.widgets.pop(id_))
        e = self.tela.elemento(id_)
        if e is not None:
            self.widgets[id_] = criar_widget(e, self)
        self.moldura.raise_()
        self.moldura.update()

    def selecionar(self, id_):
        self.selecionado = id_
        self.moldura.update()
        self.selecionou.emit(id_)

    def _no_ponto(self, ponto):
        for e in reversed(self.tela.elementos):
            if e.contem(ponto.x(), ponto.y(), folga=3):
                return e
        return None

    @staticmethod
    def _na_alca(e, ponto):
        return QRect(e.x + e.largura - 6, e.y + e.altura - 6, 14, 14).contains(ponto)

    def mousePressEvent(self, ev):
        self.setFocus()
        ponto = ev.position().toPoint()
        atual = self.tela.elemento(self.selecionado)
        # a alça do selecionado vence quem estiver embaixo dela
        e = atual if atual is not None and self._na_alca(atual, ponto) else self._no_ponto(ponto)
        self.selecionar(e.id if e else None)
        if e is not None:
            modo = "tamanho" if self._na_alca(e, ponto) else "mover"
            self._arrasto = (modo, e, ponto, (e.x, e.y, e.largura, e.altura))

    def mouseMoveEvent(self, ev):
        ponto = ev.position().toPoint()
        if self._arrasto is None:
            e = self.tela.elemento(self.selecionado)
            if e is not None and self._na_alca(e, ponto):
                self.setCursor(Qt.CursorShape.SizeFDiagCursor)
            elif self._no_ponto(ponto) is not None:
                self.setCursor(Qt.CursorShape.OpenHandCursor)
            else:
                self.unsetCursor()
            return
        modo, e, inicio, (x0, y0, l0, a0) = self._arrasto
        livre = bool(ev.modifiers() & Qt.KeyboardModifier.ShiftModifier)
        dx, dy = ponto.x() - inicio.x(), ponto.y() - inicio.y()
        if modo == "mover":
            e.x = max(0, min(self.tela.largura - e.largura, _encaixar(x0 + dx, livre)))
            e.y = max(0, min(self.tela.altura - e.altura, _encaixar(y0 + dy, livre)))
        else:
            e.largura = max(16, min(self.tela.largura - e.x, _encaixar(l0 + dx, livre)))
            e.altura = max(16, min(self.tela.altura - e.y, _encaixar(a0 + dy, livre)))
        self.widgets[e.id].setGeometry(e.x, e.y, e.largura, e.altura)
        self.moldura.update()
        self.mudou.emit()

    def mouseReleaseEvent(self, _):
        self._arrasto = None

    def keyPressEvent(self, ev):
        e = self.tela.elemento(self.selecionado)
        if e is None:
            return super().keyPressEvent(ev)
        passo = 1 if ev.modifiers() & Qt.KeyboardModifier.ShiftModifier else GRADE
        setas = {Qt.Key.Key_Left: (-passo, 0), Qt.Key.Key_Right: (passo, 0),
                 Qt.Key.Key_Up: (0, -passo), Qt.Key.Key_Down: (0, passo)}
        if ev.key() in (Qt.Key.Key_Delete, Qt.Key.Key_Backspace):
            self.tela.remover(e.id)
            descartar(self.widgets.pop(e.id))
            self.selecionar(None)
            self.mudou.emit()
        elif ev.key() in setas:
            dx, dy = setas[ev.key()]
            e.x = max(0, min(self.tela.largura - e.largura, e.x + dx))
            e.y = max(0, min(self.tela.altura - e.altura, e.y + dy))
            self.widgets[e.id].setGeometry(e.x, e.y, e.largura, e.altura)
            self.moldura.update()
            self.mudou.emit()
        else:
            super().keyPressEvent(ev)

    def paintEvent(self, _):
        p = QPainter(self)
        p.fillRect(self.rect(), QColor("#ffffff"))
        p.setPen(QColor("#dfe3e8"))
        for x in range(0, self.width(), GRADE * 2):
            for y in range(0, self.height(), GRADE * 2):
                p.drawPoint(x, y)


class PainelPropriedades(QScrollArea):
    """O que está selecionado: nome, texto, posição, tamanho e, num botão, a ligação com a função."""
    alterou = Signal(str, bool)     # id do elemento (já com o nome novo), precisa reconstruir tudo?

    def __init__(self, editor):
        super().__init__(editor)
        self.editor = editor
        self.setWidgetResizable(True)
        self.setMinimumWidth(300)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.mostrar(None)

    @property
    def tela(self):
        return self.editor.tela

    def _titulo(self, texto, cor="#59616b"):
        r = QLabel(texto.upper())
        r.setStyleSheet(f"color: {cor}; font-size: 11px; letter-spacing: 1px; margin-top: 10px;")
        return r

    @staticmethod
    def _caixa_escolha():
        caixa = QComboBox()
        caixa.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        caixa.setMinimumContentsLength(12)
        return caixa

    def mostrar(self, id_):
        corpo = QWidget()
        form = QFormLayout(corpo)
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        e = self.tela.elemento(id_) if id_ else None
        if e is None:
            form.addRow(self._titulo("Tela"))
            form.addRow("Nome", QLabel(self.tela.nome))
            form.addRow("Tamanho", QLabel(f"{NOME_TAMANHO[self.tela.tamanho]} · "
                                          f"{self.tela.largura}×{self.tela.altura}"))
            dica = QLabel("Clique num controle para editar.\nDuplo clique numa função gera os campos, "
                          "o botão e o resultado dela.\nArraste para mover; a alça azul no canto muda o "
                          "tamanho; Shift solta da grade; Delete apaga.")
            dica.setWordWrap(True)
            dica.setStyleSheet("color: #59616b;")
            form.addRow(dica)
            self.setWidget(corpo)
            return

        form.addRow(self._titulo(NOME_TIPO[e.tipo]))
        nome = QLineEdit(e.id)
        nome.editingFinished.connect(lambda: self._renomear(e, nome))
        form.addRow("Nome", nome)
        texto = QLineEdit(e.texto)
        texto.textEdited.connect(lambda t: self._mudar(e, "texto", t))
        form.addRow("Dica" if e.tipo in CAMPOS - {"marcar"} else "Texto", texto)
        for campo, rotulo, limite in (("x", "X", self.tela.largura), ("y", "Y", self.tela.altura),
                                      ("largura", "Largura", self.tela.largura),
                                      ("altura", "Altura", self.tela.altura)):
            caixa = QSpinBox()
            caixa.setRange(0 if campo in "xy" else 16, limite)
            caixa.setValue(getattr(e, campo))
            caixa.setSuffix(" px")
            caixa.valueChanged.connect(lambda v, c=campo: self._mudar(e, c, v))
            setattr(self, f"_caixa_{campo}", caixa)
            form.addRow(rotulo, caixa)
        if e.tipo == "botao":
            self._ligacao(form, e)
        self.setWidget(corpo)

    def atualizar_geometria(self, id_):
        """O mouse mexeu no elemento: só os números, sem refazer o painel (não rouba o foco)."""
        e = self.tela.elemento(id_)
        if e is None:
            return self.mostrar(None)
        for campo in ("x", "y", "largura", "altura"):
            caixa = getattr(self, f"_caixa_{campo}", None)
            if caixa is not None:
                caixa.blockSignals(True)
                caixa.setValue(getattr(e, campo))
                caixa.blockSignals(False)

    def _mudar(self, e, campo, valor):
        setattr(e, campo, valor)
        self.alterou.emit(e.id, False)

    def _renomear(self, e, caixa):
        antigo, novo = e.id, caixa.text().strip()
        if not self.tela.renomear(antigo, novo):
            caixa.setText(antigo)
            self.editor.statusBar().showMessage(f"“{novo}” não serve de nome: precisa ser um nome Python "
                                                "e não pode repetir.", 5000)
            return
        if novo != antigo:
            self.editor.palco.selecionado = novo
            self.alterou.emit(novo, True)

    # ── a ligação de um botão ─────────────────────────────────────────────

    def _ligacao(self, form, botao):
        form.addRow(self._titulo("Ao clicar, chamar", "#174a94"))
        lig = self.tela.ligacoes.get(botao.id)
        funcoes = self.editor.funcoes
        escolha = self._caixa_escolha()
        escolha.addItem("(nenhuma função)", None)
        for chave, f in funcoes.items():
            escolha.addItem(f"{f.nome}{f.assinatura()}  ·  {f.arquivo}", chave)
        if lig is not None:
            i = escolha.findData(lig.funcao)
            if i < 0:
                escolha.addItem(f"{lig.funcao}  (não encontrada)", lig.funcao)
                i = escolha.count() - 1
            escolha.setCurrentIndex(i)
        escolha.currentIndexChanged.connect(lambda _: self._trocar_funcao(botao, escolha.currentData()))
        form.addRow(escolha)
        funcao = funcoes.get(lig.funcao) if lig else None
        if funcao is None:
            return
        if funcao.doc:
            doc = QLabel(funcao.doc.splitlines()[0])
            doc.setWordWrap(True)
            doc.setStyleSheet("color: #3b4652;")
            form.addRow(doc)

        form.addRow(self._titulo("Entradas", "#174a94"))
        campos = [e for e in self.tela.elementos if e.tipo in CAMPOS]
        for p in funcao.parametros:
            caixa = self._caixa_escolha()
            caixa.addItem("(padrão da função)" if p.padrao is not None else "(nenhum campo)", None)
            for c in campos:
                caixa.addItem(f"{c.id} · {NOME_TIPO[c.tipo]}", c.id)
            caixa.setCurrentIndex(max(0, caixa.findData(lig.entradas.get(p.nome))))
            caixa.currentIndexChanged.connect(
                lambda _, nome=p.nome, cx=caixa: self._ligar_entrada(botao, nome, cx.currentData()))
            form.addRow(f"{p.nome}: {p.tipo or '?'}", caixa)

        form.addRow(self._titulo("Saída", "#174a94"))
        saida = self._caixa_escolha()
        saida.addItem("(não mostrar)", None)
        for r in (e for e in self.tela.elementos if e.tipo in ("resultado", "rotulo")):
            saida.addItem(f"{r.id} · {NOME_TIPO[r.tipo]}", r.id)
        saida.setCurrentIndex(max(0, saida.findData(lig.saida)))
        saida.currentIndexChanged.connect(lambda _: self._ligar_saida(botao, saida.currentData()))
        form.addRow(f"-> {funcao.retorno or '?'}", saida)

    def _trocar_funcao(self, botao, chave):
        if chave is None:
            self.tela.ligacoes.pop(botao.id, None)
        else:
            funcao = self.editor.funcoes.get(chave)
            antigo = self.tela.ligacoes.get(botao.id)
            entradas = {}
            if funcao is not None:   # liga sozinho o campo que tem o nome do parâmetro
                for p in funcao.parametros:
                    if self.tela.elemento(f"campo_{p.nome}") is not None:
                        entradas[p.nome] = f"campo_{p.nome}"
            saida = antigo.saida if antigo else ("resultado" if self.tela.elemento("resultado") else None)
            self.tela.ligacoes[botao.id] = Ligacao(chave, entradas, saida)
        self.alterou.emit(botao.id, False)
        self.mostrar(botao.id)

    def _ligar_entrada(self, botao, parametro, campo):
        lig = self.tela.ligacoes[botao.id]
        if campo is None:
            lig.entradas.pop(parametro, None)
        else:
            lig.entradas[parametro] = campo
        self.alterou.emit(botao.id, False)

    def _ligar_saida(self, botao, id_):
        self.tela.ligacoes[botao.id].saida = id_
        self.alterou.emit(botao.id, False)


class Editor(QMainWindow):
    def __init__(self, pasta, nome="principal", config=None):
        super().__init__()
        self.pasta = Path(pasta).resolve()
        self.config = config
        ui, _ = Tela(nome=nome).caminhos(self.pasta)
        self.tela = Tela.carregar(self.pasta, nome) if ui.exists() else Tela(nome=nome)
        self.modificado = False
        self.arquivos = []
        self.funcoes = {}
        self._janelas = []

        self.palco = Palco(self.tela)
        self.painel = PainelPropriedades(self)
        self.arvore = QTreeWidget()
        self._montar()
        self.vigia = QFileSystemWatcher(self)
        self.vigia.fileChanged.connect(lambda _: self.ler_funcoes())
        self.vigia.directoryChanged.connect(lambda _: self.ler_funcoes())
        self.ler_funcoes()

        self.palco.selecionou.connect(self.painel.mostrar)
        self.palco.mudou.connect(self._palco_mudou)
        self.painel.alterou.connect(self._painel_alterou)
        self._titulo()
        self.resize(1360, 820)

    # ── montagem ──────────────────────────────────────────────────────────

    def _montar(self):
        barra = QToolBar("Principal", self)
        barra.setMovable(False)
        self.addToolBar(barra)
        barra.addWidget(QLabel("  Tamanho do desenho  "))
        self.tamanho = QComboBox()
        for chave, (l, a) in TAMANHOS.items():
            self.tamanho.addItem(f"{NOME_TAMANHO[chave]} · {l}×{a}", chave)
        self.tamanho.setCurrentIndex(self.tamanho.findData(self.tela.tamanho))
        self.tamanho.currentIndexChanged.connect(self._mudar_tamanho)
        barra.addWidget(self.tamanho)
        barra.addSeparator()
        salvar = QAction("Salvar", self, shortcut=QKeySequence.StandardKey.Save, triggered=self.salvar)
        executar = QAction("Executar ▶", self, shortcut=QKeySequence("F5"), triggered=self.executar)
        barra.addAction(salvar)
        barra.addAction(executar)

        esquerda = QWidget()
        col = QVBoxLayout(esquerda)
        col.setContentsMargins(8, 8, 8, 8)
        col.addWidget(self._secao("Suas funções"))
        self.arvore.setHeaderHidden(True)
        self.arvore.itemDoubleClicked.connect(lambda item, _: self._gerar(item))
        col.addWidget(self.arvore, 1)
        gerar = QPushButton("Gerar na tela")
        gerar.setToolTip("Cria os campos, o botão e o resultado da função selecionada")
        gerar.clicked.connect(lambda: self._gerar(self.arvore.currentItem()))
        col.addWidget(gerar)
        col.addWidget(self._secao("Controles"))
        grade = QGridLayout()
        for i, tipo in enumerate(("rotulo", "decimal", "inteiro", "texto", "marcar", "botao", "resultado")):
            b = QPushButton(NOME_TIPO[tipo])
            b.clicked.connect(lambda _, t=tipo: self._adicionar(t))
            grade.addWidget(b, i // 2, i % 2)
        col.addLayout(grade)

        meio = QScrollArea()
        meio.setWidget(self.palco)
        meio.setAlignment(Qt.AlignmentFlag.AlignCenter)
        meio.setStyleSheet("QScrollArea { background: #e9ecef; border: none; }")

        divisor = QSplitter(Qt.Orientation.Horizontal)
        divisor.addWidget(esquerda)
        divisor.addWidget(meio)
        divisor.addWidget(self.painel)
        divisor.setStretchFactor(1, 1)
        divisor.setSizes([290, 760, 310])
        self.setCentralWidget(divisor)
        self.statusBar()

    @staticmethod
    def _secao(texto):
        r = QLabel(texto.upper())
        r.setStyleSheet("color: #59616b; font-size: 11px; letter-spacing: 1px; margin-top: 6px;")
        return r

    # ── funções do projeto ────────────────────────────────────────────────

    def ler_funcoes(self):
        self.arquivos = ler_pasta(self.pasta)
        self.funcoes = funcoes_por_chave(self.arquivos)
        self.arvore.clear()
        negrito = QFont()
        negrito.setBold(True)
        for a in self.arquivos:
            if not a.funcoes and not a.erro:
                continue
            item = QTreeWidgetItem([a.caminho])
            item.setFont(0, negrito)
            self.arvore.addTopLevelItem(item)
            if a.erro:
                QTreeWidgetItem(item, [f"✕ {a.erro}"]).setForeground(0, QColor("#b3261e"))
            if a.codigo_solto:
                linhas = ", ".join(map(str, a.codigo_solto[:5]))
                aviso = QTreeWidgetItem(item, [f"⚠ código solto (linha {linhas}): roda quando a tela rodar"])
                aviso.setForeground(0, LARANJA)
            for f in a.funcoes:
                filho = QTreeWidgetItem(item, [f"{f.nome}{f.assinatura()}"])
                filho.setData(0, Qt.ItemDataRole.UserRole, f.chave)
                filho.setToolTip(0, f.doc or "sem docstring")
            item.setExpanded(True)
        caminhos = [str(self.pasta / a.caminho) for a in self.arquivos]
        if self.vigia.files():
            self.vigia.removePaths(self.vigia.files())
        if caminhos:
            self.vigia.addPaths(caminhos)
        if str(self.pasta) not in self.vigia.directories():
            self.vigia.addPath(str(self.pasta))
        self._status()
        if self.palco.selecionado:
            self.painel.mostrar(self.palco.selecionado)

    def _gerar(self, item):
        chave = item.data(0, Qt.ItemDataRole.UserRole) if item else None
        if chave is None:
            self.statusBar().showMessage("Escolha uma função na lista.", 4000)
            return
        botao = gerar_da_funcao(self.tela, self.funcoes[chave])
        self.palco.reconstruir()
        self.palco.selecionar(botao.id)
        self._modificou()

    # ── edição ────────────────────────────────────────────────────────────

    def _adicionar(self, tipo):
        e = self.tela.adicionar(tipo)
        if e.y + e.altura > self.tela.altura:
            e.y = max(0, self.tela.altura - e.altura - 8)
        self.palco.atualizar(e.id)
        self.palco.selecionar(e.id)
        self._modificou()

    def _mudar_tamanho(self):
        self.tela.mudar_tamanho(self.tamanho.currentData())
        self.palco.reconstruir()
        self.painel.mostrar(self.palco.selecionado)
        self._modificou()

    def _palco_mudou(self):
        self.painel.atualizar_geometria(self.palco.selecionado)
        self._modificou()

    def _painel_alterou(self, id_, tudo):
        if tudo:
            self.palco.reconstruir()
        else:
            self.palco.atualizar(id_)
        self._modificou()

    def _modificou(self):
        self.modificado = True
        self._titulo()
        self._status()

    def _titulo(self):
        marca = " •" if self.modificado else ""
        self.setWindowTitle(f"PyMorph {__version__} — {self.pasta.name} — {self.tela.nome}{marca}")

    def _status(self):
        botoes = [e for e in self.tela.elementos if e.tipo == "botao"]
        ligados = sum(1 for b in botoes if b.id in self.tela.ligacoes)
        self.statusBar().showMessage(
            f"{len(self.funcoes)} funções em {sum(1 for a in self.arquivos if a.funcoes)} arquivo(s) · "
            f"{ligados} de {len(botoes)} botões ligados · telas/{self.tela.nome}.ui")

    # ── salvar e executar ─────────────────────────────────────────────────

    def salvar(self):
        ui, json_ = self.tela.salvar(self.pasta)
        self.modificado = False
        self._titulo()
        self.statusBar().showMessage(f"Salvo: {ui.relative_to(self.pasta)} + {json_.name}", 4000)
        return True

    def executar(self):
        """Salva e abre a tela como o usuário final vê: o que roda é o arquivo salvo."""
        self.salvar()
        tela = Tela.carregar(self.pasta, self.tela.nome)
        janela = executor.Janela(self.pasta, tela, funcoes=self.funcoes, parent=self, config=self.config)
        janela.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        janela.mostrar()
        self._janelas = [j for j in self._janelas if j.isVisible()] + [janela]
        return janela

    def closeEvent(self, ev):
        if self.modificado:
            r = QMessageBox.question(self, "PyMorph", "A tela tem mudanças não salvas. Salvar antes de sair?",
                                     QMessageBox.StandardButton.Save | QMessageBox.StandardButton.Discard
                                     | QMessageBox.StandardButton.Cancel)
            if r == QMessageBox.StandardButton.Cancel:
                ev.ignore()
                return
            if r == QMessageBox.StandardButton.Save:
                self.salvar()
        super().closeEvent(ev)
