"""O editor: onde quem programa desenha a tela e liga cada botão a uma função.

À esquerda, as funções do projeto (lidas pelo ast, sem executar) e os controles; no meio, o palco,
onde tudo se arrasta e redimensiona; à direita, as propriedades e a ligação do que está selecionado.
O seu código nunca é escrito: o editor só grava em telas/.
"""
import re
from functools import cache
from pathlib import Path

from PySide6.QtCore import QFileSystemWatcher, QPoint, QRect, QSize, Qt, Signal
from PySide6.QtGui import QAction, QColor, QFont, QFontDatabase, QFontMetrics, QIcon, QKeySequence, QPainter, QPen
from PySide6.QtWidgets import (QApplication, QCheckBox, QColorDialog, QComboBox, QFileDialog, QFormLayout,
                               QGridLayout, QHBoxLayout,
                               QLabel, QLineEdit,
                               QMainWindow, QMessageBox, QPushButton, QScrollArea, QSpinBox, QSplitter,
                               QToolBar, QToolButton, QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget)

from pymorph import __version__, executor, galeria, png, web
from pymorph.leitor import funcoes_por_chave, ler_pasta
from pymorph.tela import (ENTRADA, ENTRADA_E_SAIDA, ENTRADAS, NOME_TAMANHO, NOME_TIPO, SAIDA, TAMANHOS, TEXTO,
                          TIPOS, Elemento, Ligacao, Tela, estilo, gerar_da_funcao)

USO = {TEXTO: "texto fixo, como um título. Vira entrada quando um botão lê dela, e mostra o "
             "resultado quando um botão manda a saída para ela.",
       ENTRADA: "entrada: a pessoa digita aqui, e o botão passa o que foi digitado à função.",
       SAIDA: "saída: mostra o que a função devolveu.",
       ENTRADA_E_SAIDA: "entrada e saída: a pessoa digita, e o resultado aparece aqui (como o visor de "
                        "uma calculadora)."}
DICA_TIPO = {"caixa": "Texto, entrada ou resultado: o papel vem das ligações dos botões",
             "botao": "Chama uma função", "marcar": "Sim ou não"}

SOMBRA_SUAVE = "0 4 12 #40000000"
GRADE = 8           # o arrasto encaixa de 8 em 8 px; com Shift, livre
AZUL = QColor("#1f5fbf")
LARANJA = QColor("#b5560f")


# as genéricas valem em qualquer máquina: o sistema escolhe a sua (no Fedora, pelo fontconfig:
# sans-serif → Noto Sans, serif → Noto Serif, monospace → Noto Sans Mono, cursive → Z003)
GENERICAS = (("Sem serifa", "sans-serif"), ("Com serifa", "serif"), ("Monoespaçada", "monospace"),
             ("Manuscrita", "cursive"))
# o que o Qt lista como família, mas é peso ou largura de outra ("Noto Sans ExtraCondensed Thin")
_VARIANTES = {"Thin", "ExtraLight", "Light", "SemiLight", "Medium", "SemiBold", "Semibold", "Bold", "Extra",
              "ExtraBold", "Extrabold", "Black", "Condensed", "SemiCondensed", "ExtraCondensed", "Propo"}
# as Nerd Fonts têm um apelido curto para cada família
_APELIDOS = ((" NFM", " Nerd Font Mono"), (" NFP", " Nerd Font Propo"), (" NF", " Nerd Font"))


def _chave(familia):
    for curto, longo in _APELIDOS:
        if familia.endswith(curto) or curto + " " in familia:
            return familia.replace(curto, longo, 1)
    return familia


@cache
def familias_do_sistema():
    """As famílias de letra instaladas que escrevem português, uma vez cada: sem as variantes de
    peso e largura que o Qt lista como família, sem o fabricante entre colchetes ("C059 [urw]") e
    sem os apelidos ("JetBrainsMono NF" é a "JetBrainsMono Nerd Font")."""
    nomes = {}
    for f in QFontDatabase.families():
        if (QFontDatabase.isPrivateFamily(f) or "CJK" in f
                or QFontDatabase.WritingSystem.Latin not in QFontDatabase.writingSystems(f)):
            continue
        f = re.sub(r"\s*\[.*\]$", "", f)
        if f not in ("Sans Serif", "Serif", "Monospace"):
            nomes.setdefault(_chave(f), f)
    saida = []
    for chave, f in nomes.items():
        palavras = chave.split()
        if any(" ".join(palavras[:k]) in nomes
               and all(p in _VARIANTES or (p == "Mono" and palavras[k - 1] == "Font") for p in palavras[k:])
               for k in range(1, len(palavras))):
            continue
        saida.append(f)
    return sorted(saida, key=str.lower)


def _encaixar(valor, livre=False):
    return valor if livre else round(valor / GRADE) * GRADE


def descartar(widget):
    """Some na hora e o Qt apaga depois. Só o deleteLater deixaria o antigo visível por baixo do novo
    até o laço de eventos rodar: o texto sairia desenhado duas vezes."""
    widget.hide()
    widget.deleteLater()


def criar_widget(elemento, pai, papel=TEXTO):
    """O widget de verdade, como vai aparecer para o usuário final, mas sem receber clique.
    A caixa se apresenta pelo papel que as ligações dão a ela (como no .ui). Com um original do
    Galaxy, é a pele dele, com as animações rodando, mas sem pegar o mouse do palco."""
    item = web.item(elemento.original) if elemento.original else None
    if item is not None:
        w = web.Pele(item, elemento.texto, pai, interativa=False)
        w.setObjectName(elemento.id)
        w.setGeometry(elemento.x, elemento.y, elemento.largura, elemento.altura)
        w.show()
        return w
    if elemento.tipo == "botao":
        w = QPushButton(elemento.texto, pai)
    elif elemento.tipo == "marcar":
        w = QCheckBox(elemento.texto, pai)
    elif papel in (ENTRADA, ENTRADA_E_SAIDA):
        w = QLineEdit(pai)
        w.setPlaceholderText(elemento.texto)
    else:
        w = QLabel(elemento.texto, pai)
        w.setWordWrap(True)
    w.setStyleSheet(estilo(elemento, papel))
    if elemento.fonte or elemento.negrito or elemento.familia:
        fonte = w.font()
        if elemento.familia:
            fonte.setFamily(elemento.familia)
        if elemento.fonte:
            fonte.setPointSize(elemento.fonte)
        fonte.setBold(elemento.negrito)
        w.setFont(fonte)
    w.setObjectName(elemento.id)
    if elemento.sombra:
        executor.aplicar_sombra(w, elemento.sombra)
    w.setGeometry(elemento.x, elemento.y, elemento.largura, elemento.altura)
    w.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
    w.setFocusPolicy(Qt.FocusPolicy.NoFocus)
    w.show()
    return w


def _contraste(cor):
    """Preto ou branco, o que se lê melhor sobre a cor."""
    c = QColor(cor)
    return "#000000" if not c.isValid() or c.alphaF() < 0.4 or c.lightnessF() > 0.55 else "#ffffff"


def caber_texto(e, folga=32):     # 12 px de espaço interno de cada lado, e uma sobra
    """Um estilo pronto traz o tamanho de letra do original, mas o tamanho do elemento é de quem
    desenha: a letra diminui até o texto caber (nunca aumenta)."""
    if not e.fonte or not e.texto:
        return
    letra = QFont(e.familia) if e.familia else QFont()
    letra.setBold(e.negrito)
    while e.fonte > 7:
        letra.setPointSize(e.fonte)
        if QFontMetrics(letra).horizontalAdvance(e.texto) <= e.largura - folga:
            return
        e.fonte -= 1


# ── a galeria de prontos ─────────────────────────────────────────────────────

_MINIATURAS = {}


def miniatura(item, largura=108):     # duas colunas cabem no painel de 300 px
    """O item desenhado pelo próprio PyMorph (o que se vê é o que se aplica), guardado depois da 1ª vez."""
    chave = (item["id"] if item else "padrão", largura, item["tipo"] if item and "tipo" in item else "")
    if chave in _MINIATURAS:
        return _MINIATURAS[chave]
    folga = 14
    fundo = QWidget()
    fundo.setObjectName("fundo")
    fundo.setStyleSheet("QWidget#fundo { background: #ffffff; }")
    fundo.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen)
    tela = Tela()
    if item is not None and "elementos" in item:          # um layout
        fundo.resize(item["largura"], item["altura"])
        for i, campos in enumerate(item["elementos"]):
            e = Elemento(f"e{i}", **{k: v for k, v in campos.items() if k in Elemento.__dataclass_fields__})
            tela.elementos.append(e)
            criar_widget(e, fundo, tela.papel(e.id))
    else:                                                  # um estilo, num botão ou caixa de exemplo
        tipo = item["tipo"] if item else "botao"
        e = Elemento("exemplo", tipo, folga, folga, largura - 2 * folga, 40 if tipo == "botao" else 34,
                     "Botão" if tipo == "botao" else "Texto", digitavel=tipo == "caixa")
        if item is not None:
            for campo, valor in item["visual"].items():
                if hasattr(e, campo):
                    setattr(e, campo, valor)
            caber_texto(e)
        fundo.resize(largura, e.altura + 2 * folga)
        tela.elementos.append(e)
        criar_widget(e, fundo, tela.papel(e.id))
    fundo.show()
    imagem = fundo.grab()
    fundo.deleteLater()
    if imagem.width() > largura:
        imagem = imagem.scaledToWidth(largura, Qt.TransformationMode.SmoothTransformation)
    _MINIATURAS[chave] = imagem
    return imagem


ORIGINAIS = {"botao": ("Botão",), "caixa": ("Caixa", "Animação"), "marcar": ("Caixa de marcar", "Toggle")}
NOME_CATEGORIA = {"Botão": "Botões", "Caixa": "Caixas", "Caixa de marcar": "Caixas de marcar", "Toggle": "Toggles",
                  "Animação": "Animações"}


class GaleriaOriginais(QWidget):
    """Os originais do Galaxy, vivos (com animação), numa vitrine do navegador; páginas de 12."""
    POR_PAGINA = 12
    CELULA = (116, 60)

    def __init__(self, categorias, ao_escolher, com_padrao=False, parent=None):
        super().__init__(parent)
        self.ao_escolher, self.com_padrao = ao_escolher, com_padrao
        col = QVBoxLayout(self)
        col.setContentsMargins(0, 0, 0, 0)
        self.categoria = PainelPropriedades._caixa_escolha()
        for c in categorias:
            self.categoria.addItem(NOME_CATEGORIA[c], c)
        self.categoria.setVisible(len(categorias) > 1)
        self.categoria.currentIndexChanged.connect(lambda _: self._trocar())
        col.addWidget(self.categoria)
        barra = QHBoxLayout()
        self.voltar, self.avancar = QPushButton("‹"), QPushButton("›")
        for b in (self.voltar, self.avancar):
            b.setFixedWidth(32)
        self.voltar.clicked.connect(lambda: self._ir(-1))
        self.avancar.clicked.connect(lambda: self._ir(1))
        self.contagem = QLabel()
        self.contagem.setAlignment(Qt.AlignmentFlag.AlignCenter)
        barra.addWidget(self.voltar)
        barra.addWidget(self.contagem, 1)
        barra.addWidget(self.avancar)
        col.addLayout(barra)
        self.vitrine = web.Vitrine()
        self.vitrine.escolheu.connect(self._escolheu)
        col.addWidget(self.vitrine)
        self._trocar()

    def _trocar(self):
        self.itens = web.originais(self.categoria.currentData())
        self.pagina = 0
        self._mostrar()

    def _ir(self, passo):
        paginas = max(1, -(-len(self.itens) // self.POR_PAGINA))
        self.pagina = (self.pagina + passo) % paginas
        self._mostrar()

    def _mostrar(self):
        inicio = self.pagina * self.POR_PAGINA
        self.parte = self.itens[inicio:inicio + self.POR_PAGINA]
        celulas = len(self.parte) + (1 if self.com_padrao else 0)
        self.vitrine.setFixedHeight(-(-celulas // 2) * (self.CELULA[1] + 20) + 6)    # célula + borda + vão
        self.vitrine.mostrar(self.parte, *self.CELULA, com_padrao=self.com_padrao)
        total = len(self.itens)
        self.contagem.setText(f"{inicio + 1}–{inicio + len(self.parte)} de {total}" if total else "catálogo vazio")

    def _escolheu(self, i):
        self.ao_escolher(None if i < 0 else self.parte[i])


class Galeria(QWidget):
    """Os prontos em páginas de 12, em duas colunas; um clique escolhe."""
    POR_PAGINA = 12

    def __init__(self, itens, ao_escolher, com_padrao=False, parent=None):
        super().__init__(parent)
        self.ao_escolher = ao_escolher
        self.com_padrao = com_padrao
        self.pagina = 0
        col = QVBoxLayout(self)
        col.setContentsMargins(0, 0, 0, 0)
        barra = QHBoxLayout()
        self.voltar, self.avancar = QPushButton("‹"), QPushButton("›")
        for b in (self.voltar, self.avancar):
            b.setFixedWidth(32)
        self.voltar.clicked.connect(lambda: self._ir(-1))
        self.avancar.clicked.connect(lambda: self._ir(1))
        self.contagem = QLabel()
        self.contagem.setAlignment(Qt.AlignmentFlag.AlignCenter)
        barra.addWidget(self.voltar)
        barra.addWidget(self.contagem, 1)
        barra.addWidget(self.avancar)
        col.addLayout(barra)
        self.grade = QGridLayout()
        self.grade.setSpacing(6)
        col.addLayout(self.grade)
        self.mudar_itens(itens)

    def mudar_itens(self, itens):
        self.itens = ([None] if self.com_padrao else []) + list(itens)
        self.pagina = 0
        self._mostrar()

    def _ir(self, passo):
        paginas = max(1, -(-len(self.itens) // self.POR_PAGINA))
        self.pagina = (self.pagina + passo) % paginas
        self._mostrar()

    def _mostrar(self):
        while self.grade.count():
            descartar(self.grade.takeAt(0).widget())
        inicio = self.pagina * self.POR_PAGINA
        parte = self.itens[inicio:inicio + self.POR_PAGINA]
        for i, item in enumerate(parte):
            b = QToolButton()
            b.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
            imagem = miniatura(item)
            b.setIcon(QIcon(imagem))
            b.setIconSize(imagem.size())
            b.setMinimumSize(QSize(imagem.width() + 8, imagem.height() + 8))
            b.setToolTip("Sem estilo: volta ao padrão" if item is None else
                         f"{item.get('categoria', NOME_TIPO.get(item.get('tipo'), ''))} de {galeria.credito(item)}"
                         f"\nparecença com o original: {round(item['nota'] * 100)}%")
            b.clicked.connect(lambda _=False, it=item: self.ao_escolher(it))
            self.grade.addWidget(b, i // 2, i % 2)
        total = len(self.itens)
        self.contagem.setText(f"{inicio + 1 if total else 0}–{inicio + len(parte)} de {total}" if total
                              else "catálogo vazio")
        self.voltar.setEnabled(total > self.POR_PAGINA)
        self.avancar.setEnabled(total > self.POR_PAGINA)


class Moldura(QWidget):
    """Camada por cima do palco: a seleção, a alça de tamanho, a marca de botão ligado e o contorno
    tracejado da caixa de texto que, vazia e sem fundo, sumiria do palco."""

    def __init__(self, palco):
        super().__init__(palco)
        self.palco = palco
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        tela = self.palco.tela
        for e in tela.elementos:
            invisivel = not e.texto and e.fundo in ("", "transparent") and e.borda_largura <= 0 and not e.original
            if e.tipo == "caixa" and tela.papel(e.id) == TEXTO and invisivel:
                p.setBrush(Qt.BrushStyle.NoBrush)
                p.setPen(QPen(QColor("#c3c9d0"), 1, Qt.PenStyle.DashLine))
                p.drawRect(QRect(e.x, e.y, e.largura - 1, e.altura - 1))
            elif e.tipo == "botao":
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
        antigos, self.widgets = self.widgets, {}
        for e in self.tela.elementos:
            self.widgets[e.id] = self._widget(e, antigos.pop(e.id, None))
            self.widgets[e.id].raise_()         # a ordem da lista é a ordem de quem fica por cima
        for w in antigos.values():
            descartar(w)
        self.setFixedSize(self.tela.largura, self.tela.altura)
        self.moldura.setGeometry(self.rect())
        self.moldura.raise_()
        self.moldura.update()

    def _widget(self, e, antigo):
        """A pele de um original é reaproveitada: recarregar o navegador a cada tecla piscaria e
        reiniciaria a animação."""
        if isinstance(antigo, web.Pele) and antigo.chave == e.original:
            antigo.setGeometry(e.x, e.y, e.largura, e.altura)
            if antigo.texto != e.texto:
                antigo.definir_texto(e.texto)
            antigo.setObjectName(e.id)
            return antigo
        if antigo is not None:
            descartar(antigo)
        w = criar_widget(e, self, self.tela.papel(e.id))
        if isinstance(w, web.Pele):
            w.mediu.connect(lambda largura, altura, id_=e.id: self._crescer(id_, largura, altura))
        return w

    def _crescer(self, id_, largura, altura):
        """O original, com o texto de quem desenha, pede mais espaço: o elemento cresce (nunca encolhe
        sozinho), dentro da tela."""
        e = self.tela.elemento(id_)
        if e is None or (largura <= e.largura and altura <= e.altura):
            return
        e.largura = min(max(e.largura, largura), self.tela.largura - e.x)
        e.altura = min(max(e.altura, altura), self.tela.altura - e.y)
        if id_ in self.widgets:
            self.widgets[id_].setGeometry(e.x, e.y, e.largura, e.altura)
        self.moldura.update()
        self.mudou.emit()

    def atualizar(self, id_):
        """Refaz um elemento só (depois de mudar texto, tipo, posição ou tamanho)."""
        antigo = self.widgets.pop(id_, None)
        e = self.tela.elemento(id_)
        if e is not None:
            self.widgets[id_] = self._widget(e, antigo)
        elif antigo is not None:
            descartar(antigo)
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
            sob = self._no_ponto(ponto)
            self._destacar(sob.id if sob is not None else None)
            e = self.tela.elemento(self.selecionado)
            if e is not None and self._na_alca(e, ponto):
                self.setCursor(Qt.CursorShape.SizeFDiagCursor)
            elif self._no_ponto(ponto) is not None:
                self.setCursor(Qt.CursorShape.OpenHandCursor)
            else:
                self.unsetCursor()
            return
        modo, e, inicio, (x0, y0, l0, a0) = self._arrasto
        self._destacar(None)
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

    def _destacar(self, id_):
        """O original debaixo do mouse mostra o estado de mouse por cima (a pele não pega o mouse,
        para o palco poder arrastar; então o palco liga o estado por ela)."""
        anterior = getattr(self, "_destacado", None)
        if anterior == id_:
            return
        for alvo, ligado in ((anterior, False), (id_, True)):
            w = self.widgets.get(alvo)
            if isinstance(w, web.Pele):
                w.destacar(ligado)
        self._destacado = id_

    def leaveEvent(self, ev):
        self._destacar(None)
        super().leaveEvent(ev)

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
            self.reconstruir()      # sem o botão, as caixas dele podem mudar de papel
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
        # quem pede para refazer o painel costuma ser uma caixa dele, no meio do próprio sinal: o
        # setWidget apagaria o corpo antigo na hora, com a caixa dentro, e o Qt cairia (SEGV)
        antigo = self.takeWidget()
        if antigo is not None:
            descartar(antigo)
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
            self._prontos_da_tela(form)
            self.setWidget(corpo)
            return

        form.addRow(self._titulo(NOME_TIPO[e.tipo]))
        nome = QLineEdit(e.id)
        nome.editingFinished.connect(lambda: self._renomear(e, nome))
        form.addRow("Nome", nome)
        papel = self.tela.papel(e.id) if e.tipo == "caixa" else None
        if papel is not None:
            uso = QLabel(USO[papel])
            uso.setWordWrap(True)
            uso.setStyleSheet("color: #3b4652;")
            form.addRow("Uso", uso)
        texto = QLineEdit(e.texto)
        texto.textEdited.connect(lambda t: self._mudar(e, "texto", t))
        form.addRow("Dica" if papel in (ENTRADA, ENTRADA_E_SAIDA) else "Texto", texto)
        letra = QSpinBox()
        letra.setRange(0, 96)
        letra.setSpecialValueText("padrão")
        letra.setSuffix(" pt")
        letra.setValue(e.fonte)
        letra.valueChanged.connect(lambda v: self._mudar(e, "fonte", v))
        form.addRow("Fonte", self._caixa_familia(e))
        form.addRow("Letra", letra)
        negrito = QCheckBox("Negrito")
        negrito.setChecked(e.negrito)
        negrito.toggled.connect(lambda v: self._mudar(e, "negrito", v))
        form.addRow("", negrito)
        form.addRow("Cor do texto", self._seletor_cor(e, "cor"))
        form.addRow("Fundo", self._seletor_cor(e, "fundo"))
        borda = self._numero(e, "borda_largura", 20, {-1: "padrão", 0: "sem borda"})
        linha = QWidget()
        lado = QHBoxLayout(linha)
        lado.setContentsMargins(0, 0, 0, 0)
        lado.addWidget(borda)
        lado.addWidget(self._seletor_cor(e, "borda_cor"), 1)
        form.addRow("Borda", linha)
        form.addRow("Cantos", self._numero(e, "raio", 60, {-1: "padrão"}))
        espaco = QLineEdit(e.espaco)
        espaco.setPlaceholderText("padrão (ex.: 8px 16px)")
        espaco.editingFinished.connect(lambda: self._mudar(e, "espaco", espaco.text().strip()))
        form.addRow("Espaço interno", espaco)
        sombra = QCheckBox("Sombra")
        sombra.setChecked(bool(e.sombra))
        sombra.setToolTip(e.sombra or "liga uma sombra suave; a dos prontos vem com a medida deles")
        sombra.toggled.connect(lambda v: self._mudar(e, "sombra", (e.sombra or SOMBRA_SUAVE) if v else ""))
        form.addRow("", sombra)
        quando = {"botao": "Mouse por cima", "marcar": "Mouse por cima"}.get(
            e.tipo, "Com o foco" if papel in (ENTRADA, ENTRADA_E_SAIDA) else None)
        if quando:          # título próprio: rótulo comprido alarga a coluna e empurra o painel para fora
            form.addRow(self._titulo(quando))
            form.addRow("Fundo", self._seletor_cor(e, "destaque_fundo"))
            form.addRow("Texto", self._seletor_cor(e, "destaque_cor"))
        if e.tipo == "caixa":
            digitavel = QCheckBox("De digitar, mesmo sem ligação")
            digitavel.setChecked(e.digitavel)
            digitavel.toggled.connect(lambda v: self._mudar(e, "digitavel", v, tudo=True))
            form.addRow("", digitavel)
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
        if e.tipo in ORIGINAIS:
            form.addRow(self._titulo("Originais (com animação)", "#174a94"))
            form.addRow(GaleriaOriginais(ORIGINAIS[e.tipo], lambda item: self._aplicar_original(e, item),
                                         com_padrao=True))
        if e.tipo in ("botao", "caixa"):
            form.addRow(self._titulo("Estilos prontos", "#174a94"))
            form.addRow(Galeria(galeria.estilos(e.tipo), lambda item: self._aplicar_estilo([e], item),
                                com_padrao=True))
        self.setWidget(corpo)

    def _prontos_da_tela(self, form):
        """Sem nada selecionado: um estilo vale para todos os elementos do tipo; um layout entra na tela."""
        form.addRow(self._titulo("Estilos prontos", "#174a94"))
        tipo = self._caixa_escolha()
        tipo.addItem("Botões", "botao")
        tipo.addItem("Caixas", "caixa")
        form.addRow("Para todos os", tipo)
        estilos = Galeria(galeria.estilos("botao"), lambda item: self._aplicar_estilo(
            [x for x in self.tela.elementos if x.tipo == tipo.currentData()], item), com_padrao=True)
        tipo.currentIndexChanged.connect(lambda _: estilos.mudar_itens(galeria.estilos(tipo.currentData())))
        form.addRow(estilos)

        form.addRow(self._titulo("Originais (com animação)", "#174a94"))
        dica = QLabel("Rodam como foram escritos, no navegador embutido. Um clique põe um elemento novo na tela.")
        dica.setWordWrap(True)
        dica.setStyleSheet("color: #59616b; font-size: 11px;")
        form.addRow(dica)
        form.addRow(GaleriaOriginais(("Botão", "Caixa", "Caixa de marcar", "Toggle", "Animação"),
                                     self._adicionar_original))

        self._layout_png(form)

    def _layout_png(self, form):
        form.addRow(self._titulo("Layout de uma imagem (PNG)", "#174a94"))
        dica = QLabel("A captura de tela de um programa vira o esqueleto: as cores, as barras e os painéis "
                      "nas posições de lá. Texto vira “[a preencher]”; ícone e imagem, um espaço marcado — "
                      "o que é dos outros fica para você preencher.")
        dica.setWordWrap(True)
        dica.setStyleSheet("color: #59616b; font-size: 11px;")
        form.addRow(dica)
        escolher = QPushButton("Escolher imagem…")
        escolher.clicked.connect(self._escolher_png)
        form.addRow(escolher)

    def _escolher_png(self):
        caminho, _ = QFileDialog.getOpenFileName(self, "Imagem de referência", str(self.editor.pasta),
                                                 "Imagens (*.png *.jpg *.jpeg *.webp *.bmp)")
        if not caminho:
            return
        substituir = True
        if self.tela.elementos:
            caixa = QMessageBox(QMessageBox.Icon.Question, "PyMorph",
                                "A tela já tem elementos. O esqueleto da imagem substitui a tela ou entra junto?",
                                parent=self)
            trocar = caixa.addButton("Substituir", QMessageBox.ButtonRole.AcceptRole)
            juntar = caixa.addButton("Acrescentar", QMessageBox.ButtonRole.ActionRole)
            caixa.addButton(QMessageBox.StandardButton.Cancel)
            caixa.exec()
            if caixa.clickedButton() not in (trocar, juntar):
                return
            substituir = caixa.clickedButton() is trocar
        self.editor.importar_png(caminho, substituir)

    def _aplicar_estilo(self, elementos, item):
        for e in elementos:
            galeria.aplicar_estilo(self.tela, e, item)
            caber_texto(e)
        quem = "ao padrão" if item is None else f"de {item['autor']} (Uiverse.io)"
        self.editor.statusBar().showMessage(
            f"{len(elementos)} elemento(s) com o estilo {quem}" if elementos else "nenhum elemento desse tipo", 5000)
        self.alterou.emit(elementos[0].id if elementos else "", True)
        self.mostrar(self.editor.palco.selecionado)

    def _aplicar_original(self, e, item):
        galeria.aplicar_original(self.tela, e, item)
        self.editor.statusBar().showMessage(
            "de volta ao desenho do Qt" if item is None else
            f"{item['categoria']} de {item['autor']} (Uiverse.io), {item['largura']}×{item['altura']}", 6000)
        self.alterou.emit(e.id, True)
        self.mostrar(e.id)

    def _adicionar_original(self, item):
        if item is None:
            return
        e = galeria.adicionar_original(self.tela, item)
        if e.y + e.altura > self.tela.altura:
            e.y = max(0, self.tela.altura - e.altura - 8)
        self.editor.statusBar().showMessage(f"{item['categoria']} de {item['autor']} (Uiverse.io)", 6000)
        self.alterou.emit(e.id, True)
        self.editor.palco.selecionar(e.id)

    def _importar_layout(self, item):
        tamanho = self.tela.tamanho
        criados = galeria.importar_layout(self.tela, item)
        mudou = "" if tamanho == self.tela.tamanho else f" A tela passou para {NOME_TAMANHO[self.tela.tamanho]} para caber."
        self.editor.statusBar().showMessage(
            f"{item['categoria']} de {item['autor']} (Uiverse.io): {len(criados)} elementos.{mudou}", 8000)
        self.alterou.emit(criados[0].id if criados else "", True)
        self.mostrar(None)

    def _numero(self, e, campo, maximo, especiais):
        caixa = QSpinBox()
        caixa.setRange(min(especiais), maximo)
        caixa.setSpecialValueText(especiais[min(especiais)])
        caixa.setSuffix(" px")
        caixa.setValue(getattr(e, campo))
        caixa.valueChanged.connect(lambda v: self._mudar(e, campo, v))
        if 0 in especiais and min(especiais) < 0:
            caixa.setToolTip("0 = " + especiais[0])
        return caixa

    def _caixa_familia(self, e):
        """As genéricas primeiro, depois as do sistema; cada nome escrito na própria letra."""
        caixa = self._caixa_escolha()
        caixa.addItem("Padrão do sistema", "")
        for nome, familia in GENERICAS:
            caixa.addItem(f"{nome} ({familia})", familia)
        caixa.insertSeparator(caixa.count())
        for familia in familias_do_sistema():
            caixa.addItem(familia, familia)
        for i in range(1, caixa.count()):
            if caixa.itemData(i):
                caixa.setItemData(i, QFont(caixa.itemData(i)), Qt.ItemDataRole.FontRole)
        i = caixa.findData(e.familia)
        if i < 0:       # escolhida em outra máquina: o Qt usa a mais parecida que houver aqui
            caixa.addItem(f"{e.familia} (não instalada aqui)", e.familia)
            i = caixa.count() - 1
        caixa.setCurrentIndex(i)
        caixa.setMaxVisibleItems(20)
        caixa.currentIndexChanged.connect(lambda _: self._mudar(e, "familia", caixa.currentData()))
        return caixa

    def _seletor_cor(self, e, campo):
        """Um botão com a amostra da cor (abre o seletor do Qt) e um × que volta ao padrão."""
        linha = QWidget()
        caixa = QHBoxLayout(linha)
        caixa.setContentsMargins(0, 0, 0, 0)
        amostra = QPushButton()
        limpar = QPushButton("×")
        limpar.setFixedWidth(28)
        limpar.setToolTip("voltar ao padrão")

        def mostrar():
            valor = getattr(e, campo)
            amostra.setText("gradiente" if valor.startswith("qlineargradient") else (valor or "padrão"))
            amostra.setStyleSheet(f"background: {valor}; color: {_contraste(valor)}; text-align: left; "
                                  "padding: 3px 8px; border: 1px solid #c3c9d0; border-radius: 4px;"
                                  if valor else "text-align: left; padding: 3px 8px;")
            limpar.setEnabled(bool(valor))

        def escolher(valor=None):
            if valor is None:
                inicial = QColor(getattr(e, campo) or ("#000000" if campo == "cor" else "#ffffff"))
                cor = QColorDialog.getColor(inicial, self, "Cor do texto" if campo == "cor" else "Fundo")
                if not cor.isValid():
                    return
                valor = cor.name()
            self._mudar(e, campo, valor)
            mostrar()

        amostra.clicked.connect(lambda: escolher())
        limpar.clicked.connect(lambda: escolher(""))
        linha.escolher = escolher           # os testes escolhem sem abrir o seletor
        caixa.addWidget(amostra, 1)
        caixa.addWidget(limpar)
        mostrar()
        linha.setObjectName(f"cor_{campo}")
        return linha

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

    def _mudar(self, e, campo, valor, tudo=False):
        setattr(e, campo, valor)
        self.alterou.emit(e.id, tudo)

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
        campos = [e for e in self.tela.elementos if e.tipo in ENTRADAS]
        for p in funcao.parametros:
            caixa = self._caixa_escolha()
            caixa.addItem("(padrão da função)" if p.padrao is not None else "(nenhuma caixa)", None)
            for c in campos:
                caixa.addItem(f"{c.id} · {NOME_TIPO[c.tipo]}", c.id)
            caixa.setCurrentIndex(max(0, caixa.findData(lig.entradas.get(p.nome))))
            caixa.currentIndexChanged.connect(
                lambda _, nome=p.nome, cx=caixa: self._ligar_entrada(botao, nome, cx.currentData()))
            caixa.setToolTip(f"o que for digitado chega a {p.nome} como {p.leitura}")
            form.addRow(f"{p.nome} · {p.leitura}", caixa)

        form.addRow(self._titulo("Saída", "#174a94"))
        saida = self._caixa_escolha()
        saida.addItem("(não mostrar)", None)
        for r in (e for e in self.tela.elementos if e.tipo == "caixa"):
            saida.addItem(f"{r.id} · {NOME_TIPO[r.tipo]}", r.id)
        saida.setCurrentIndex(max(0, saida.findData(lig.saida)))
        saida.currentIndexChanged.connect(lambda _: self._ligar_saida(botao, saida.currentData()))
        form.addRow(f"→ {funcao.retorno or 'valor'}" if funcao.devolve else "→ nada (ação)", saida)

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
            if funcao is not None and not funcao.devolve:
                saida = None
            self.tela.ligacoes[botao.id] = Ligacao(chave, entradas, saida)
        self.alterou.emit(botao.id, True)       # as caixas ligadas mudam de papel
        self.mostrar(botao.id)

    def _ligar_entrada(self, botao, parametro, campo):
        lig = self.tela.ligacoes[botao.id]
        if campo is None:
            lig.entradas.pop(parametro, None)
        else:
            lig.entradas[parametro] = campo
        self.alterou.emit(botao.id, True)

    def _ligar_saida(self, botao, id_):
        self.tela.ligacoes[botao.id].saida = id_
        self.alterou.emit(botao.id, True)


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
        gerar.setToolTip("Cria as caixas dos parâmetros, o botão e, se a função devolve um valor, "
                         "a caixa do resultado")
        gerar.clicked.connect(lambda: self._gerar(self.arvore.currentItem()))
        col.addWidget(gerar)
        col.addWidget(self._secao("Controles"))
        grade = QGridLayout()
        for i, tipo in enumerate(TIPOS):
            b = QPushButton(NOME_TIPO[tipo])
            b.setToolTip(DICA_TIPO[tipo])
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

    def importar_png(self, caminho, substituir=True):
        """O esqueleto de uma imagem de referência (png.py) na tela; devolve o resultado da análise."""
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            resultado = png.analisar(caminho)
            png.aplicar(self.tela, resultado, substituir)
        except ValueError as erro:
            QApplication.restoreOverrideCursor()
            QMessageBox.warning(self, "PyMorph", str(erro))
            return None
        QApplication.restoreOverrideCursor()
        self.tamanho.blockSignals(True)
        self.tamanho.setCurrentIndex(self.tamanho.findData(self.tela.tamanho))
        self.tamanho.blockSignals(False)
        self.palco.reconstruir()
        self.palco.selecionar(None)
        self._modificou()
        c = resultado["contagem"]
        self.statusBar().showMessage(
            f"{Path(caminho).name}: {c['painel']} painéis, {c['forma']} formas, {c['linha']} linhas, "
            f"{c['texto']} textos e {c['imagem']} imagens a preencher · paleta {' '.join(resultado['paleta'][:6])}",
            15000)
        return resultado

    def _mudar_tamanho(self):
        self.tela.mudar_tamanho(self.tamanho.currentData())
        self.palco.reconstruir()
        self.painel.mostrar(self.palco.selecionado)
        self._modificou()

    def _palco_mudou(self):
        self.painel.atualizar_geometria(self.palco.selecionado)
        self._modificou()

    def _painel_alterou(self, id_, tudo):
        if self.tamanho.currentData() != self.tela.tamanho:     # um layout pronto pode aumentar a tela
            self.tamanho.blockSignals(True)
            self.tamanho.setCurrentIndex(self.tamanho.findData(self.tela.tamanho))
            self.tamanho.blockSignals(False)
            tudo = True
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
