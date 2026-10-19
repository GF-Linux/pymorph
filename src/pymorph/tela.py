"""A tela: os elementos desenhados, as ligações botão → função e os dois arquivos que guardam isso.

    telas/<nome>.ui              o desenho, no formato do Qt Designer (abre nele)
    telas/<nome>.ligacoes.json   que função cada botão chama, de onde vêm as entradas, para onde vai a saída

O .ui leva só o que o PyMorph controla (posição, tamanho, texto, estilo). Gravar todas as
propriedades de cada widget transformaria 2 widgets em 102 propriedades; o Designer também só grava
o que mudou.
"""
import json
import re
import xml.etree.ElementTree as ET
from dataclasses import asdict, dataclass, field
from pathlib import Path

# os 3 tamanhos de desenho; são conveniência de quem desenha, o usuário final redimensiona à vontade
TAMANHOS = {"pequena": (480, 360), "intermediaria": (960, 640), "cheia": (1920, 1080)}
NOME_TAMANHO = {"pequena": "Pequena", "intermediaria": "Intermediária", "cheia": "Tela cheia"}

# tipo do PyMorph → classe Qt gravada no .ui
CLASSE = {"rotulo": "QLabel", "resultado": "QLabel", "botao": "QPushButton", "marcar": "QCheckBox",
          "decimal": "QLineEdit", "inteiro": "QLineEdit", "texto": "QLineEdit"}
CAMPOS = {"decimal", "inteiro", "texto", "marcar"}
NOME_TIPO = {"rotulo": "Rótulo", "resultado": "Resultado", "botao": "Botão", "marcar": "Caixa de marcar",
             "decimal": "Campo decimal", "inteiro": "Campo inteiro", "texto": "Campo de texto"}
TAMANHO_PADRAO = {"rotulo": (200, 24), "resultado": (432, 48), "botao": (120, 36), "marcar": (200, 28),
                  "decimal": (200, 32), "inteiro": (200, 32), "texto": (200, 32)}
ESTILO_RESULTADO = "border: 1px solid #c3c9d0; border-radius: 6px; padding: 6px; background: #f7f8f9;"
PONTOS_RESULTADO = 14   # a fonte do resultado vai no .ui, e não no estilo, para o zoom escalar


@dataclass
class Elemento:
    id: str
    tipo: str
    x: int
    y: int
    largura: int
    altura: int
    texto: str = ""     # rótulo e botão: o texto; campo: a dica dentro dele; resultado: o texto inicial

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

    def mudar_tamanho(self, tamanho):
        self.tamanho = tamanho
        self.largura, self.altura = TAMANHOS[tamanho]

    # ── edição ────────────────────────────────────────────────────────────

    def adicionar(self, tipo, x=24, y=None, texto=None):
        largura, altura = TAMANHO_PADRAO[tipo]
        if y is None:
            y = self.proxima_linha()
        if texto is None:
            texto = {"rotulo": "Rótulo", "botao": "Botão", "marcar": "Opção", "resultado": "—",
                     "decimal": "0,00", "inteiro": "0", "texto": ""}[tipo]
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
        json_.write_text(json.dumps(dados, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return ui, json_

    def para_ui(self):
        ui = ET.Element("ui", version="4.0")
        ET.SubElement(ui, "class").text = self.nome
        raiz = ET.SubElement(ui, "widget", {"class": "QWidget", "name": self.nome})
        _geometria(raiz, 0, 0, self.largura, self.altura)
        _texto(raiz, "windowTitle", self.nome)
        for e in self.elementos:
            w = ET.SubElement(raiz, "widget", {"class": CLASSE[e.tipo], "name": e.id})
            _geometria(w, e.x, e.y, e.largura, e.altura)
            if e.tipo in ("decimal", "inteiro", "texto"):
                if e.texto:
                    _texto(w, "placeholderText", e.texto)
            else:
                _texto(w, "text", e.texto)
            if e.tipo == "resultado":
                _texto(w, "styleSheet", ESTILO_RESULTADO)
                prop = ET.SubElement(w, "property", name="font")
                ET.SubElement(ET.SubElement(prop, "font"), "pointsize").text = str(PONTOS_RESULTADO)
                prop = ET.SubElement(w, "property", name="wordWrap")
                ET.SubElement(prop, "bool").text = "true"
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
            tipo = tipo or {v: k for k, v in CLASSE.items()}.get(w.get("class"), "rotulo")
            x, y, largura, altura = _ler_geometria(w)
            chave = "placeholderText" if tipo in ("decimal", "inteiro", "texto") else "text"
            texto = (props[chave].findtext("string") or "") if chave in props else ""
            tela.elementos.append(Elemento(w.get("name"), tipo, x, y, largura, altura, texto))
        if json_.exists():
            dados = json.loads(json_.read_text(encoding="utf-8"))
            tela.tamanho = dados.get("tamanho", tela.tamanho)
            tela.ligacoes = {k: Ligacao(**v) for k, v in dados.get("ligacoes", {}).items()}
        return tela


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
    """Cria o que falta para a função rodar: um campo por parâmetro, o botão e o resultado.

    Campo que já existe com o mesmo parâmetro é reaproveitado: somar, multiplicar e dividir
    de (a, b) dividem os mesmos dois campos e o mesmo resultado, cada uma com o seu botão.
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
                tela.elementos.append(Elemento(tela.novo_id(f"rotulo_{p.nome}"), "rotulo", x, y, 200, 22,
                                               _rotulo(p.nome)))
                y += 24
                dica = {"decimal": "0,00", "inteiro": "0"}.get(p.controle, p.padrao or "")
                tela.elementos.append(Elemento(campo_id, p.controle, x, y, 200, 32, dica))
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

    resultado = tela.elemento("resultado")
    if resultado is None:
        resultado = Elemento("resultado", "resultado", x, by + 36 + 16, min(432, tela.largura - 48), 48, "—")
        tela.elementos.append(resultado)
    elif resultado.contem(bx + 1, by + 1) or by + 36 > resultado.y:
        resultado.y = by + 36 + 16
    tela.ligacoes[botao.id] = Ligacao(funcao.chave, entradas, resultado.id)
    return botao
