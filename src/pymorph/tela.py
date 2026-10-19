"""A tela: os elementos desenhados, as ligações botão → função e os dois arquivos que guardam isso.

    telas/<nome>.ui              o desenho, no formato do Qt Designer (abre nele)
    telas/<nome>.ligacoes.json   que função cada botão chama, de onde vêm as entradas, para onde vai a saída

O .ui leva só o que o PyMorph controla (posição, tamanho, texto, letra, estilo). Gravar todas as
propriedades de cada widget transformaria 2 widgets em 102 propriedades; o Designer também só grava
o que mudou.

São três controles: a caixa, o botão e a caixa de marcar. A caixa não tem tipo nem papel fixo: o
papel vem das ligações. Nenhum botão usa → texto fixo (um título); entrada de um botão → a pessoa
digita; saída → mostra o que a função devolveu; as duas → digita, e o resultado aparece nela.
"""
import json
import re
import xml.etree.ElementTree as ET
from dataclasses import asdict, dataclass, field
from pathlib import Path

# os 3 tamanhos de desenho; são conveniência de quem desenha, o usuário final redimensiona à vontade
TAMANHOS = {"pequena": (480, 360), "intermediaria": (960, 640), "cheia": (1920, 1080)}
NOME_TAMANHO = {"pequena": "Pequena", "intermediaria": "Intermediária", "cheia": "Tela cheia"}

TIPOS = ("caixa", "botao", "marcar")
ENTRADAS = {"caixa", "marcar"}      # o que pode dar valor a um parâmetro
NOME_TIPO = {"caixa": "Caixa", "botao": "Botão", "marcar": "Caixa de marcar"}
TAMANHO_PADRAO = {"caixa": (200, 32), "botao": (120, 36), "marcar": (200, 28)}
# os tipos da 0.0.1/0.0.2 viraram a caixa: o papel agora vem das ligações
ANTIGOS = {"rotulo", "resultado", "decimal", "inteiro", "texto"}

# o papel da caixa → como ela se apresenta
TEXTO, ENTRADA, SAIDA, ENTRADA_E_SAIDA = "texto", "entrada", "saida", "entrada e saída"
QUADRO = {"border": "1px solid #c3c9d0", "border-radius": "6px", "padding": "6px", "background": "#f7f8f9"}
ESTILO_RESULTADO = "; ".join(f"{k}: {v}" for k, v in QUADRO.items()) + ";"
PONTOS_RESULTADO = 14   # a fonte do resultado vai no .ui, e não no estilo, para o zoom escalar


@dataclass
class Elemento:
    id: str
    tipo: str
    x: int
    y: int
    largura: int
    altura: int
    texto: str = ""     # caixa de entrada: a dica apagada dentro dela; o resto: o texto que aparece
    fonte: int = 0      # tamanho da letra em pontos; 0 é o padrão do sistema
    negrito: bool = False
    familia: str = ""   # a família da letra: uma do sistema ou genérica (sans-serif, serif…); "" é a padrão
    cor: str = ""       # cor do texto, '#rrggbb'; "" é a padrão
    fundo: str = ""     # cor de fundo, '#rrggbb' ou um qlineargradient(...); "" é a padrão
    borda_largura: int = -1     # px; -1 é a padrão, 0 é sem borda
    borda_cor: str = ""
    raio: int = -1              # os cantos, em px; -1 é o padrão
    espaco: str = ""            # o espaço interno (padding do QSS): "8px 16px"
    sombra: str = ""            # "dx dy desfoque cor": "0 4 12 #40000000" (a cor do Qt é #AARRGGBB)
    destaque_fundo: str = ""    # no botão, com o mouse por cima; na caixa de digitar, com o foco
    destaque_cor: str = ""
    destaque_borda: str = ""
    digitavel: bool = False     # caixa de digitar mesmo sem ligação (vem assim de um layout pronto)

    def contem(self, x, y, folga=0):
        return (self.x - folga <= x <= self.x + self.largura + folga
                and self.y - folga <= y <= self.y + self.altura + folga)


@dataclass
class Ligacao:
    funcao: str                                         # 'calculadora.py:somar'
    entradas: dict[str, str] = field(default_factory=dict)  # parâmetro → id do campo
    saida: str | None = None                            # id do elemento que mostra o retorno


@dataclass
class Tela:
    nome: str = "principal"
    tamanho: str = "pequena"
    largura: int = TAMANHOS["pequena"][0]
    altura: int = TAMANHOS["pequena"][1]
    elementos: list[Elemento] = field(default_factory=list)
    ligacoes: dict[str, Ligacao] = field(default_factory=dict)  # id do botão → ligação
    creditos: list[str] = field(default_factory=list)   # de onde vieram os estilos e layouts prontos

    # ── consulta ──────────────────────────────────────────────────────────

    def elemento(self, id_):
        return next((e for e in self.elementos if e.id == id_), None)

    def novo_id(self, base):
        base = re.sub(r"\W", "_", base) or "elemento"
        if self.elemento(base) is None:
            return base
        n = 2
        while self.elemento(f"{base}_{n}") is not None:
            n += 1
        return f"{base}_{n}"

    def papel(self, id_):
        """O papel de uma caixa, pelas ligações: TEXTO, ENTRADA, SAIDA ou ENTRADA_E_SAIDA. A caixa
        marcada como de digitar é entrada mesmo antes de um botão ler dela."""
        e = self.elemento(id_)
        entrada = (any(id_ in lig.entradas.values() for lig in self.ligacoes.values())
                   or (e is not None and e.digitavel))
        saida = any(lig.saida == id_ for lig in self.ligacoes.values())
        return {(False, False): TEXTO, (True, False): ENTRADA, (False, True): SAIDA,
                (True, True): ENTRADA_E_SAIDA}[entrada, saida]

    def classe(self, e):
        """A classe Qt do elemento no .ui; a da caixa depende do papel."""
        return classe_de(e, self.papel(e.id))

    def mudar_tamanho(self, tamanho):
        self.tamanho = tamanho
        self.largura, self.altura = TAMANHOS[tamanho]

    # ── edição ────────────────────────────────────────────────────────────

    def adicionar(self, tipo, x=24, y=None, texto=None):
        largura, altura = TAMANHO_PADRAO[tipo]
        if y is None:
            y = self.proxima_linha()
        if texto is None:
            texto = {"caixa": "Texto", "botao": "Botão", "marcar": "Opção"}[tipo]
        elemento = Elemento(self.novo_id(tipo), tipo, x, y, largura, altura, texto)
        self.elementos.append(elemento)
        return elemento

    def remover(self, id_):
        self.elementos = [e for e in self.elementos if e.id != id_]
        self.ligacoes.pop(id_, None)
        for lig in self.ligacoes.values():
            lig.entradas = {p: c for p, c in lig.entradas.items() if c != id_}
            if lig.saida == id_:
                lig.saida = None

    def renomear(self, antigo, novo):
        """Troca o id e todas as referências a ele. Devolve False se o nome não serve."""
        if novo == antigo:
            return True
        if not novo.isidentifier() or self.elemento(novo) is not None:
            return False
        self.elemento(antigo).id = novo
        if antigo in self.ligacoes:
            self.ligacoes[novo] = self.ligacoes.pop(antigo)
        for lig in self.ligacoes.values():
            lig.entradas = {p: (novo if c == antigo else c) for p, c in lig.entradas.items()}
            if lig.saida == antigo:
                lig.saida = novo
        return True

    def proxima_linha(self):
        if not self.elementos:
            return 24
        return max(e.y + e.altura for e in self.elementos) + 16

    # ── arquivos ──────────────────────────────────────────────────────────

    def caminhos(self, pasta):
        base = Path(pasta) / "telas"
        return base / f"{self.nome}.ui", base / f"{self.nome}.ligacoes.json"

    def salvar(self, pasta):
        ui, json_ = self.caminhos(pasta)
        ui.parent.mkdir(parents=True, exist_ok=True)
        ui.write_text(self.para_ui(), encoding="utf-8")
        dados = {"versao": 1, "tamanho": self.tamanho,
                 "ligacoes": {k: asdict(v) for k, v in self.ligacoes.items()}}
        if self.creditos:
            dados["creditos"] = self.creditos
        json_.write_text(json.dumps(dados, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return ui, json_

    def para_ui(self):
        ui = ET.Element("ui", version="4.0")
        ET.SubElement(ui, "class").text = self.nome
        raiz = ET.SubElement(ui, "widget", {"class": "QWidget", "name": self.nome})
        _geometria(raiz, 0, 0, self.largura, self.altura)
        _texto(raiz, "windowTitle", self.nome)
        for e in self.elementos:
            classe = self.classe(e)
            w = ET.SubElement(raiz, "widget", {"class": classe, "name": e.id})
            _geometria(w, e.x, e.y, e.largura, e.altura)
            if classe == "QLineEdit":
                if e.texto:
                    _texto(w, "placeholderText", e.texto)
            else:
                _texto(w, "text", e.texto)
            if e.fonte or e.negrito or e.familia:
                fonte = ET.SubElement(ET.SubElement(w, "property", name="font"), "font")
                if e.familia:
                    ET.SubElement(fonte, "family").text = e.familia
                if e.fonte:
                    ET.SubElement(fonte, "pointsize").text = str(e.fonte)
                if e.negrito:
                    ET.SubElement(fonte, "bold").text = "true"
            css = estilo(e, self.papel(e.id))
            if css:
                _texto(w, "styleSheet", css)
            if classe == "QLabel":
                prop = ET.SubElement(w, "property", name="wordWrap")
                ET.SubElement(prop, "bool").text = "true"
            visual = {k: getattr(e, k) for k in VISUAIS if getattr(e, k) != PADRAO_VISUAL[k]}
            if visual:          # o que foi escolhido, para o PyMorph reler sem decifrar o estilo
                prop = ET.SubElement(w, "property", name="pymorphEstilo", stdset="0")
                ET.SubElement(prop, "string").text = json.dumps(visual, ensure_ascii=False)
            prop = ET.SubElement(w, "property", name="pymorphTipo", stdset="0")
            ET.SubElement(prop, "string").text = e.tipo
        ET.indent(ui, space=" ")
        return '<?xml version="1.0" encoding="UTF-8"?>\n' + ET.tostring(ui, encoding="unicode") + "\n"

    @classmethod
    def carregar(cls, pasta, nome="principal"):
        tela = cls(nome=nome)
        ui, json_ = tela.caminhos(pasta)
        raiz = ET.parse(ui).getroot().find("widget")
        _, _, tela.largura, tela.altura = _ler_geometria(raiz)
        for w in raiz.findall("widget"):
            props = {p.get("name"): p for p in w.findall("property")}
            tipo = props["pymorphTipo"].findtext("string") if "pymorphTipo" in props else None
            tipo = tipo or {"QPushButton": "botao", "QCheckBox": "marcar"}.get(w.get("class"), "caixa")
            if tipo in ANTIGOS:
                tipo = "caixa"
            x, y, largura, altura = _ler_geometria(w)
            chave = "placeholderText" if w.get("class") == "QLineEdit" else "text"
            texto = (props[chave].findtext("string") or "") if chave in props else ""
            fonte = props["font"].find("font") if "font" in props else None
            pontos = int(fonte.findtext("pointsize") or 0) if fonte is not None else 0
            negrito = fonte is not None and fonte.findtext("bold") == "true"
            familia = (fonte.findtext("family") or "") if fonte is not None else ""
            e = Elemento(w.get("name"), tipo, x, y, largura, altura, texto, pontos, negrito, familia)
            for antigo, campo in (("pymorphCor", "cor"), ("pymorphFundo", "fundo")):    # 0.0.4
                if antigo in props:
                    setattr(e, campo, props[antigo].findtext("string") or "")
            if "pymorphEstilo" in props:
                for k, v in json.loads(props["pymorphEstilo"].findtext("string") or "{}").items():
                    if k in VISUAIS:
                        setattr(e, k, v)
            tela.elementos.append(e)
        if json_.exists():
            dados = json.loads(json_.read_text(encoding="utf-8"))
            tela.tamanho = dados.get("tamanho", tela.tamanho)
            tela.ligacoes = {k: Ligacao(**v) for k, v in dados.get("ligacoes", {}).items()}
            tela.creditos = dados.get("creditos", [])
        return tela


VISUAIS = ("cor", "fundo", "borda_largura", "borda_cor", "raio", "espaco", "sombra", "destaque_fundo",
           "destaque_cor", "destaque_borda", "digitavel")
PADRAO_VISUAL = {k: Elemento.__dataclass_fields__[k].default for k in VISUAIS}


def classe_de(e, papel):
    if e.tipo == "caixa":
        return "QLineEdit" if papel in (ENTRADA, ENTRADA_E_SAIDA) else "QLabel"
    return {"botao": "QPushButton", "marcar": "QCheckBox"}[e.tipo]


def estilo(e, papel):
    """O estilo (QSS) do elemento: o quadro da caixa de resultado, as cores, a borda, os cantos, o
    espaço interno e o destaque (:hover no botão, :focus na caixa de digitar).

    Com aparência própria, botão e caixa de digitar ganham borda e cantos de partida: o Qt troca o
    desenho nativo pelo do estilo, e só a cor deixaria um retângulo chapado."""
    classe = classe_de(e, papel)
    d = {}
    if e.tipo == "caixa" and papel == SAIDA:
        d.update(QUADRO)
    proprio = e.fundo or e.borda_largura >= 0 or e.raio >= 0 or e.espaco or e.borda_cor
    if proprio and classe in ("QPushButton", "QLineEdit"):
        d.update({"border": "1px solid rgba(0, 0, 0, 0.25)", "border-radius": "6px",
                  "padding": "4px 12px" if classe == "QPushButton" else "2px 6px"})
    if e.borda_largura == 0:
        d["border"] = "none"
    elif e.borda_largura > 0 or e.borda_cor:
        d["border"] = f"{max(1, e.borda_largura)}px solid {e.borda_cor or '#c3c9d0'}"
    if e.raio >= 0:     # mais que meia altura, o canto passa por cima do texto (e o Qt desenha mal)
        d["border-radius"] = f"{min(e.raio, min(e.largura, e.altura) // 2)}px"
    if e.espaco:
        d["padding"] = e.espaco
    if e.cor:
        d["color"] = e.cor
    if e.fundo:
        d["background"] = e.fundo
    destaque = {k: v for k, v in (("background", e.destaque_fundo), ("color", e.destaque_cor),
                                   ("border-color", e.destaque_borda)) if v}
    pseudo = {"QPushButton": "hover", "QCheckBox": "hover", "QLineEdit": "focus"}.get(classe)
    css = ""
    if d:
        css = f"{classe} {{ " + " ".join(f"{k}: {v};" for k, v in d.items()) + " }"
    if destaque and pseudo:
        css += (" " if css else "") + f"{classe}:{pseudo} {{ " + " ".join(f"{k}: {v};" for k, v in destaque.items()) + " }"
    return css


def ler_sombra(sombra):
    """'0 4 12 #40000000' → (dx, dy, desfoque, cor) ou None."""
    partes = sombra.split(maxsplit=3)
    if len(partes) != 4:
        return None
    try:
        return float(partes[0]), float(partes[1]), float(partes[2]), partes[3]
    except ValueError:
        return None


def _geometria(widget, x, y, largura, altura):
    prop = ET.SubElement(widget, "property", name="geometry")
    rect = ET.SubElement(prop, "rect")
    for nome, valor in (("x", x), ("y", y), ("width", largura), ("height", altura)):
        ET.SubElement(rect, nome).text = str(valor)


def _ler_geometria(widget):
    for prop in widget.findall("property"):
        if prop.get("name") == "geometry":
            r = prop.find("rect")
            return tuple(int(r.findtext(k)) for k in ("x", "y", "width", "height"))
    return 0, 0, 100, 30


def _texto(widget, nome, valor):
    prop = ET.SubElement(widget, "property", name=nome)
    ET.SubElement(prop, "string").text = valor


# ── a tela nasce da função ───────────────────────────────────────────────

def _rotulo(nome):
    return nome.replace("_", " ").strip().capitalize()


def gerar_da_funcao(tela, funcao):
    """Cria o que falta para a função rodar: um título e uma caixa por parâmetro, o botão e, se ela
    devolve um valor, a caixa do resultado. Função que não devolve nada é uma ação: só o botão.

    Caixa que já existe com o mesmo parâmetro é reaproveitada: somar, multiplicar e dividir de
    (a, b) dividem as mesmas duas caixas e o mesmo resultado, cada uma com o seu botão.
    Devolve o botão criado.
    """
    x = 24
    y = tela.proxima_linha()
    entradas = {}
    for p in funcao.parametros:
        campo_id = f"campo_{p.nome}"
        if tela.elemento(campo_id) is None:
            if p.controle == "marcar":
                tela.elementos.append(Elemento(campo_id, "marcar", x, y, 200, 28, _rotulo(p.nome)))
                y += 28 + 12
            else:
                tela.elementos.append(Elemento(tela.novo_id(f"titulo_{p.nome}"), "caixa", x, y, 200, 22,
                                               _rotulo(p.nome)))
                y += 24
                dica = {"float": "0,00", "int": "0"}.get(p.tipo, p.padrao or "")
                tela.elementos.append(Elemento(campo_id, "caixa", x, y, 200, 32, dica))
                y += 32 + 12
        entradas[p.nome] = campo_id

    botoes = [e for e in tela.elementos if e.tipo == "botao"]
    if botoes and not entradas.keys() - {p for lig in tela.ligacoes.values() for p in lig.entradas}:
        ultimo = botoes[-1]
        bx, by = ultimo.x + ultimo.largura + 8, ultimo.y
        if bx + 120 > tela.largura - 24:
            bx, by = x, max(e.y + e.altura for e in botoes) + 8
    else:
        bx, by = x, y
    botao = Elemento(tela.novo_id(f"botao_{funcao.nome}"), "botao", bx, by, 120, 36, _rotulo(funcao.nome))
    tela.elementos.append(botao)

    saida = None
    if funcao.devolve:
        resultado = tela.elemento("resultado")
        if resultado is None:
            resultado = Elemento("resultado", "caixa", x, by + 36 + 16, min(432, tela.largura - 48), 48, "—",
                                 PONTOS_RESULTADO)
            tela.elementos.append(resultado)
        elif resultado.contem(bx + 1, by + 1) or by + 36 > resultado.y:
            resultado.y = by + 36 + 16
        saida = resultado.id
    tela.ligacoes[botao.id] = Ligacao(funcao.chave, entradas, saida)
    return botao
