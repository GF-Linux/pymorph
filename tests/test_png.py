"""O layout de uma imagem: uma tela sintética, com posições e cores conhecidas, vira o esqueleto certo."""
import cv2
import numpy as np

from pymorph import png
from pymorph.tela import Tela

# BGR, como o OpenCV desenha
TITULO, LATERAL, EDITOR, STATUS, DIVISORIA, AZUL = (24, 24, 24), (38, 37, 37), (31, 31, 31), (204, 122, 0), (60, 60, 60), (220, 120, 40)


def _desenhar(caminho):
    img = np.zeros((1080, 1920, 3), np.uint8)
    img[:] = EDITOR
    img[0:36, :] = TITULO
    img[1056:, :] = STATUS
    img[36:1056, 0:300] = LATERAL
    img[36:1056, 300:301] = DIVISORIA
    cv2.rectangle(img, (8, 6), (32, 30), (90, 200, 250), -1)                     # um ícone na barra de título
    for i, nome in enumerate(("EXPLORER", "arquivo.py", "outro_modulo.py")):
        cv2.putText(img, nome, (20, 80 + 30 * i), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (220, 220, 220), 1, cv2.LINE_AA)
    # um botão: retângulo arredondado azul com texto dentro
    x0, y0, x1, y1, r = 800, 500, 1100, 548, 10
    cv2.rectangle(img, (x0 + r, y0), (x1 - r, y1), AZUL, -1)
    cv2.rectangle(img, (x0, y0 + r), (x1, y1 - r), AZUL, -1)
    for cx, cy in ((x0 + r, y0 + r), (x1 - r, y0 + r), (x0 + r, y1 - r), (x1 - r, y1 - r)):
        cv2.circle(img, (cx, cy), r, AZUL, -1, cv2.LINE_AA)
    cv2.putText(img, "Continuar", (900, 532), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 1, cv2.LINE_AA)
    cv2.imwrite(str(caminho), img)


def _hex_bgr(bgr):
    return "#{:02x}{:02x}{:02x}".format(*bgr[::-1])


def _perto(cor_hex, bgr, tolerancia=12):
    rgb = tuple(int(cor_hex[i:i + 2], 16) for i in (1, 3, 5))
    return sum(abs(a - b) for a, b in zip(rgb, bgr[::-1])) <= tolerancia


def test_a_imagem_vira_o_esqueleto(tmp_path):
    imagem = tmp_path / "tela.png"
    _desenhar(imagem)
    r = png.analisar(imagem)
    assert r["tamanho"] == "cheia" and r["escala"] == 1.0
    paineis = [e for e in r["elementos"] if e["tipo"] == "painel"]

    def painel(x, y):           # o painel que contém o ponto
        return min((p for p in paineis if p["x"] <= x < p["x"] + p["largura"] and p["y"] <= y < p["y"] + p["altura"]),
                   key=lambda p: p["largura"] * p["altura"])
    titulo, lateral, status = painel(960, 18), painel(150, 600), painel(960, 1068)
    assert (titulo["y"], titulo["altura"]) == (0, 36) and _perto(titulo["fundo"], TITULO)
    assert (lateral["x"], lateral["largura"]) == (0, 300) and _perto(lateral["fundo"], LATERAL)
    assert (status["y"], status["altura"]) == (1056, 24) and _perto(status["fundo"], STATUS)
    assert any(e["tipo"] == "linha" and e["x"] == 300 and e["largura"] == 1 for e in r["elementos"])  # a divisória
    (botao,) = [e for e in r["elementos"] if e["tipo"] == "forma"]
    assert abs(botao["x"] - 800) <= 2 and abs(botao["largura"] - 301) <= 3 and _perto(botao["fundo"], AZUL, 20)
    assert 6 <= botao["raio"] <= 14
    icones = [e for e in r["elementos"] if e["tipo"] == "imagem"]
    assert any(abs(e["x"] - 8) <= 2 and abs(e["y"] - 6) <= 2 for e in icones)
    textos = [e for e in r["elementos"] if e["tipo"] == "texto"]
    assert len(textos) == 4                         # os três da lateral e o do botão


def test_aplicar_poe_tudo_a_preencher_e_o_texto_por_cima_do_botao(tmp_path):
    imagem = tmp_path / "tela.png"
    _desenhar(imagem)
    tela = Tela()
    tela.adicionar("botao")
    criados = png.aplicar(tela, png.analisar(imagem))
    assert tela.tamanho == "cheia" and tela.elementos == criados and not tela.ligacoes     # substituiu
    textos = [e for e in criados if e.texto and e.id.startswith("texto")]
    assert textos and {e.texto for e in textos} <= {"[a preencher]", "[…]"}
    assert not any(t in e.texto for e in criados for t in ("EXPLORER", "arquivo", "Continuar"))
    ordem = [e.id for e in criados]
    forma = next(e for e in criados if e.id.startswith("forma"))
    dentro = next(e for e in textos if forma.contem(e.x + e.largura / 2, e.y + e.altura / 2))
    assert ordem.index(forma.id) < ordem.index(dentro.id)                  # o texto fica por cima
    assert criados[0].id == "fundo" and (criados[0].largura, criados[0].altura) == (1920, 1080)


def test_o_editor_importa_a_imagem(tmp_path, app, config):
    from pymorph.editor import Editor
    imagem = tmp_path / "ref.png"
    _desenhar(imagem)
    editor = Editor(tmp_path, config=config)
    resultado = editor.importar_png(imagem)
    assert editor.tamanho.currentData() == "cheia" and editor.modificado
    assert len(editor.palco.widgets) == len(resultado["elementos"])
    assert "a preencher" in editor.statusBar().currentMessage()
