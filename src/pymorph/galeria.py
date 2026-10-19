"""Estilos e layouts prontos, do catálogo gerado a partir do Galaxy (Uiverse.io, MIT).

O catálogo (catalogo/galaxy.json) é feito uma vez por ferramentas/catalogo_galaxy.py: cada item foi
aberto num navegador, traduzido para os campos do PyMorph e só entrou se o desenho do PyMorph ficou
parecido com o original. Aqui não há navegador: um estilo é só um conjunto de valores do painel, e
um layout é uma lista de elementos.
"""
import json
from functools import cache
from importlib import resources

from pymorph.tela import PADRAO_VISUAL, TAMANHOS, VISUAIS, Elemento

LETRA = ("fonte", "negrito", "familia")


@cache
def catalogo():
    try:
        texto = resources.files("pymorph").joinpath("catalogo/galaxy.json").read_text(encoding="utf-8")
    except FileNotFoundError:
        return {"estilos": [], "layouts": []}
    return json.loads(texto)


def estilos(tipo):
    return [i for i in catalogo()["estilos"] if i["tipo"] == tipo]


def layouts(categoria):
    return [i for i in catalogo()["layouts"] if i["categoria"] == categoria]


def credito(item):
    return f"{item['autor']} · Uiverse.io (MIT) · {item['url']}"


def aplicar_estilo(tela, e, item):
    """Troca a aparência do elemento pela do item (None volta ao padrão). Posição, tamanho, texto e
    se a caixa é de digitar ficam como estão: o estilo é um ponto de partida, ajustável no painel."""
    for campo in VISUAIS:
        if campo != "digitavel":
            setattr(e, campo, PADRAO_VISUAL[campo])
    e.fonte, e.negrito, e.familia = 0, False, ""
    if item is None:
        return
    for campo, valor in item["visual"].items():
        if campo in VISUAIS or campo in LETRA:
            setattr(e, campo, valor)
    _creditar(tela, item)


def importar_layout(tela, item):
    """Põe o layout na tela, num espaço livre: embaixo do que já existe ou ao lado. Se não couber,
    a tela passa para o próximo tamanho que caiba. Devolve os elementos criados."""
    largura, altura = item["largura"], item["altura"]
    ocupado = tela.elementos
    for tamanho in _tamanhos_a_partir_de(tela.tamanho):
        tl, ta = TAMANHOS[tamanho]
        lugares = [(24, 24)] if not ocupado else [
            (24, max(e.y + e.altura for e in ocupado) + 16),
            (max(e.x + e.largura for e in ocupado) + 24, 24)]
        livre = next(((x, y) for x, y in lugares if x + largura <= tl and y + altura <= ta), None)
        if livre is not None:
            if tamanho != tela.tamanho:
                tela.mudar_tamanho(tamanho)
            break
    else:
        livre = (0, 0)
    x0, y0 = livre
    criados = []
    for campos in item["elementos"]:
        e = Elemento(tela.novo_id(campos["tipo"]), campos["tipo"], x0 + campos["x"], y0 + campos["y"],
                     campos["largura"], campos["altura"], campos.get("texto", ""))
        for campo, valor in campos.items():
            if campo in VISUAIS or campo in LETRA:
                setattr(e, campo, valor)
        tela.elementos.append(e)
        criados.append(e)
    _creditar(tela, item)
    return criados


def _tamanhos_a_partir_de(tamanho):
    nomes = list(TAMANHOS)
    return nomes[nomes.index(tamanho):]


def _creditar(tela, item):
    """O crédito de quem criou vai junto com a tela (no .ligacoes.json); a licença MIT pede o aviso."""
    if item["url"] not in tela.creditos:
        tela.creditos.append(item["url"])
