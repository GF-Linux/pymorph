"""O layout de uma imagem: um PNG de referência (a tela de um programa) vira o esqueleto editável.

A regra é de quem usa: o que é desenho vem — a paleta, a posição e o tamanho das barras e dos painéis,
as linhas que separam; o que é dos outros fica a preencher — todo texto vira "[a preencher]" (com a cor
e o tamanho de letra de lá) e todo ícone ou imagem vira um espaço marcado.

Como acha as partes, sem aprendizado de máquina:
  1. cortes sucessivos (XY-cut) nas bordas de cor que atravessam a região inteira: a barra de título
     atravessa a tela toda; dentro do meio, a lateral atravessa a altura toda, e assim por diante.
     Uma faixa de 1 a 3 px vira linha divisória; o resto vira painel com a cor dominante;
  2. dentro de cada painel, o que difere da cor dele é conteúdo: juntado na horizontal (as letras de
     uma frase), cada bloco vira texto (baixo e comprido) ou imagem/ícone (quadrado, ou grande e cheio).
"""
from collections import Counter

import cv2
import numpy as np

from pymorph.tela import TAMANHOS, Elemento

A_PREENCHER = "[a preencher]"
CORTE = 0.85            # a fração da largura (ou altura) que uma borda de cor precisa atravessar
DIFERENCA = 14          # a soma |ΔR|+|ΔG|+|ΔB| que conta como borda entre duas linhas de pontos
MINIMO_PAINEL = 6       # px: menor que isso numa direção, é linha (ou nada)


def escolher_tamanho(largura, altura):
    """Uma imagem do tamanho da tela é a escala máxima; menores vão para o tamanho mais próximo."""
    if largura >= 1400 or altura >= 900:
        return "cheia"
    if largura >= 760 or altura >= 520:
        return "intermediaria"
    return "pequena"


def _hex(rgb):
    return "#{:02x}{:02x}{:02x}".format(*(int(c) for c in rgb))


def _cor_dominante(regiao):
    """A cor mais frequente (agrupando de 4 em 4 para o antisserrilhado não dividir a contagem)."""
    q = (regiao.reshape(-1, 3) // 4).astype(np.int32)
    chaves = (q[:, 0] << 16) | (q[:, 1] << 8) | q[:, 2]
    valores, contagens = np.unique(chaves, return_counts=True)
    k = valores[contagens.argmax()]
    return np.array([(k >> 16) * 4 + 2, ((k >> 8) & 255) * 4 + 2, (k & 255) * 4 + 2]), contagens.max() / chaves.size


def _bordas(regiao, eixo):
    """Para cada fronteira entre linhas (eixo 0) ou colunas (eixo 1): a fração atravessada por borda."""
    d = np.abs(np.diff(regiao.astype(np.int16), axis=eixo)).sum(axis=2) > DIFERENCA
    return d.mean(axis=1 - eixo)


def _cortar(img, x0, y0, x1, y1, folhas, profundidade=0):
    regiao = img[y0:y1, x0:x1]
    h, w = regiao.shape[:2]
    if h < 2 or w < 2 or profundidade > 24:
        folhas.append((x0, y0, x1, y1))
        return
    for eixo in (0, 1):                     # primeiro as faixas horizontais, depois as colunas
        if (h if eixo == 0 else w) < 4:
            continue
        frac = _bordas(regiao, eixo)
        cortes = [i + 1 for i in np.flatnonzero(frac >= CORTE)]
        if cortes:
            limites = [0] + cortes + [h if eixo == 0 else w]
            for a, b in zip(limites, limites[1:]):
                if b > a:
                    if eixo == 0:
                        _cortar(img, x0, y0 + a, x1, y0 + b, folhas, profundidade + 1)
                    else:
                        _cortar(img, x0 + a, y0, x0 + b, y1, folhas, profundidade + 1)
            return
    folhas.append((x0, y0, x1, y1))


def _raio(img, cor, x, y, w, h):
    """O arredondamento do canto: quantos pontos da diagonal, a partir do canto, ainda não são a forma."""
    for k in range(min(w, h) // 2):
        if np.abs(img[y + k, x + k].astype(int) - cor.astype(int)).sum() <= 40:
            return round(k / 0.29) if k else 0      # a diagonal entra ~0,29·r num canto de raio r
    return min(w, h) // 2


def _conteudo(img, fundo, x0, y0, x1, y1, nivel=0):
    """O conteúdo de um painel: os blocos (x, y, w, h, tipo, cor) e as linhas finas (guias, sublinhados)."""
    regiao = img[y0:y1, x0:x1].astype(np.int16)
    dist = np.abs(regiao - fundo.astype(np.int16)).sum(axis=2)
    tinta = (dist > 40).astype(np.uint8)
    if tinta.sum() == 0:
        return [], []
    # linhas finas e compridas (a guia do explorador, um sublinhado) saem antes de agrupar: grudadas
    # nos textos, virariam um bloco grande e falso
    finas = cv2.morphologyEx(tinta, cv2.MORPH_OPEN, np.ones((40, 1), np.uint8)) | \
        cv2.morphologyEx(tinta, cv2.MORPH_OPEN, np.ones((1, 60), np.uint8))
    linhas = []
    n, _, stats, _ = cv2.connectedComponentsWithStats(finas, connectivity=8)
    for i in range(1, n):
        x, y, w, h, _ = stats[i]
        if min(w, h) <= 3:
            cor = np.median(regiao[y:y + h, x:x + w][finas[y:y + h, x:x + w] > 0], axis=0)
            linhas.append((x0 + x, y0 + y, w, h, cor))
            tinta[y:y + h, x:x + w] &= (1 - finas[y:y + h, x:x + w])
    juntos = cv2.dilate(tinta, np.ones((3, 9), np.uint8))       # letras e palavras da mesma frase
    n, rotulos, stats, _ = cv2.connectedComponentsWithStats(juntos, connectivity=8)
    blocos = []
    for i in range(1, n):
        x, y, w, h, _ = stats[i]
        x, y, w, h = x + 4, y + 1, max(1, w - 8), max(1, h - 2)  # desfaz a dilatação
        if h < 6 or w < 3:
            continue                                            # risco, ruído, o minimapa
        dentro = tinta[y:y + h, x:x + w]
        pontos = regiao[y:y + h, x:x + w][dentro > 0]
        if len(pontos) == 0:
            continue
        forte = pontos[dist[y:y + h, x:x + w][dentro > 0] >= np.percentile(dist[y:y + h, x:x + w][dentro > 0], 60)]
        cor = np.median(forte, axis=0)
        densidade = dentro.mean()
        cores = len(np.unique((pontos // 32).reshape(-1, 3), axis=0))
        proporcao = w / h
        jeito_de_forma = w >= 2.2 * h or (w >= 60 and h >= 40)    # botão, campo, cartão; não um ícone
        if densidade >= 0.6 and h >= 14 and w >= 20 and jeito_de_forma and nivel < 2:
            # cheio: uma forma (botão, campo, cartão); o que está dentro dela é analisado de novo,
            # com a cor dela como fundo
            forma, _ = _cor_dominante(img[y0 + y:y0 + y + h, x0 + x:x0 + x + w])
            blocos.append((x0 + x, y0 + y, w, h, "forma", forma, _raio(img, forma, x0 + x, y0 + y, w, h)))
            dentro_blocos, dentro_linhas = _conteudo(img, forma, x0 + x, y0 + y, x0 + x + w, y0 + y + h, nivel + 1)
            blocos += dentro_blocos
            continue
        if h <= 44 and proporcao >= 1.3 and cores <= 6:
            tipo = "texto"
        elif h <= 44 and proporcao < 1.3 and h >= 10:
            tipo = "imagem"                                     # ícone
        elif h > 44 and proporcao >= 2.5 and densidade < 0.6 and cores <= 6:
            tipo = "texto"                                      # um título grande
        elif h > 44:
            tipo = "imagem"
        else:
            tipo = "texto"
        blocos.append((x0 + x, y0 + y, w, h, tipo, cor, 0))
    return _juntar_linhas(blocos), linhas


def _juntar_linhas(blocos):
    """Palavras da mesma linha com vão de até ~2 espaços viram uma frase (o código não sai picado)."""
    textos = sorted((b for b in blocos if b[4] == "texto"), key=lambda b: (b[1], b[0]))
    outros = [b for b in blocos if b[4] != "texto"]
    juntos = []
    for b in textos:
        x, y, w, h, _, cor, _ = b
        for i, (jx, jy, jw, jh, jt, jc, _) in enumerate(juntos):
            alto = max(h, jh)
            if (abs((y + h / 2) - (jy + jh / 2)) <= 0.35 * alto and max(h, jh) <= 1.6 * min(h, jh)
                    and x - (jx + jw) <= 1.2 * alto and jx - (x + w) <= 1.2 * alto):
                nx, ny = min(x, jx), min(y, jy)
                largura = max(x + w, jx + jw) - nx
                juntos[i] = (nx, ny, largura, max(y + h, jy + jh) - ny, "texto", jc if jw >= w else cor, 0)
                break
        else:
            juntos.append(b)
    return outros + juntos         # formas antes: o texto de dentro fica por cima delas


def analisar(caminho, tamanho=None):
    """O PNG → os elementos do esqueleto, já na escala da tela do PyMorph."""
    bgr = cv2.imread(str(caminho), cv2.IMREAD_COLOR)
    if bgr is None:
        raise ValueError(f"não consegui ler a imagem {caminho}")
    img = bgr[..., ::-1].copy()
    H, W = img.shape[:2]
    tamanho = tamanho or escolher_tamanho(W, H)
    TW, TH = TAMANHOS[tamanho]
    esc = min(TW / W, TH / H)

    folhas = []
    _cortar(img, 0, 0, W, H, folhas)
    geral, _ = _cor_dominante(img)
    paineis, linhas, blocos = [], [], []
    for x0, y0, x1, y1 in folhas:
        w, h = x1 - x0, y1 - y0
        fundo, _ = _cor_dominante(img[y0:y1, x0:x1])
        if min(w, h) < MINIMO_PAINEL:       # faixa fina: divisória (ou nada, se for curta)
            if max(w, h) >= 24:
                linhas.append((x0, y0, w, h, fundo))
            continue
        paineis.append((x0, y0, w, h, fundo))
        novos, finas = _conteudo(img, fundo, x0, y0, x1, y1)
        blocos += novos
        linhas += finas

    # painéis vizinhos da mesma cor e na mesma faixa viram um só (o corte separa o que a cor junta)
    paineis = _juntar(paineis)

    def em(v):              # posição: 0 continua 0
        return round(v * esc)

    def tam(v):             # tamanho: pelo menos 1 px
        return max(1, round(v * esc))

    elementos = [dict(tipo="fundo", x=0, y=0, largura=tam(W), altura=tam(H), fundo=_hex(geral))]  # nada fica sem cor
    for x, y, w, h, cor in paineis:
        elementos.append(dict(tipo="painel", x=em(x), y=em(y), largura=tam(w), altura=tam(h), fundo=_hex(cor)))
    for x, y, w, h, cor in linhas:
        elementos.append(dict(tipo="linha", x=em(x), y=em(y), largura=tam(w), altura=tam(h), fundo=_hex(cor)))
    blocos.sort(key=lambda b: b[4] != "forma")        # as formas atrás de todo texto e ícone
    for x, y, w, h, tipo, cor, raio in blocos:
        if tipo == "forma":
            elementos.append(dict(tipo="forma", x=em(x), y=em(y), largura=tam(w), altura=tam(h), fundo=_hex(cor),
                                  raio=em(raio)))
        elif tipo == "texto":
            pontos = max(6, min(48, round(h * 0.95 * 0.75 * esc)))
            elementos.append(dict(tipo="texto", x=em(x), y=em(y) - 1, largura=tam(w), altura=tam(h) + 2,
                                  cor=_hex(cor), fonte=pontos))
        else:
            elementos.append(dict(tipo="imagem", x=em(x), y=em(y), largura=tam(w), altura=tam(h), cor=_hex(cor)))

    area = Counter()
    for x, y, w, h, cor in paineis:
        area[_hex(cor)] += w * h
    for x, y, w, h, tipo, cor, _ in blocos:
        area[_hex(cor)] += w * h
    return {"tamanho": tamanho, "escala": esc, "origem": (W, H),
            "paleta": [c for c, _ in area.most_common(10)],
            "contagem": Counter(e["tipo"] for e in elementos), "elementos": elementos}


def _juntar(paineis):
    mudou = True
    while mudou:
        mudou = False
        for i, a in enumerate(paineis):
            for j, b in enumerate(paineis[i + 1:], i + 1):
                (ax, ay, aw, ah, ac), (bx, by, bw, bh, bc) = a, b
                if np.abs(ac.astype(int) - bc.astype(int)).sum() > 8:
                    continue
                if ay == by and ah == bh and (ax + aw == bx or bx + bw == ax):
                    paineis[i] = (min(ax, bx), ay, aw + bw, ah, ac)
                elif ax == bx and aw == bw and (ay + ah == by or by + bh == ay):
                    paineis[i] = (ax, min(ay, by), aw, ah + bh, ac)
                else:
                    continue
                del paineis[j]
                mudou = True
                break
            if mudou:
                break
    return paineis


def _largura_texto(texto, pontos):
    return len(texto) * pontos * 0.75 + 6


def _alargar(textos, obstaculos, largura_tela):
    """Onde o texto original era curto ("Log In"), "[a preencher]" não cabe: o espaço cresce para os
    dois lados, centralizado, até o texto vizinho da mesma linha (ou a borda da tela)."""
    for d in textos:
        precisa = _largura_texto(A_PREENCHER, d["fonte"])
        if d["largura"] >= precisa:
            continue
        mesma_linha = [o for o in obstaculos if o is not d and o["y"] < d["y"] + d["altura"] and d["y"] < o["y"] + o["altura"]]
        esquerda = max([o["x"] + o["largura"] + 4 for o in mesma_linha if o["x"] < d["x"]], default=0)
        direita = min([o["x"] - 4 for o in mesma_linha if o["x"] > d["x"]], default=largura_tela)
        centro = d["x"] + d["largura"] / 2
        nova = min(precisa, 2 * min(centro - esquerda, direita - centro))
        if nova > d["largura"]:
            d["x"], d["largura"] = round(centro - nova / 2), round(nova)


def _texto_que_cabe(largura, pontos):
    """'[a preencher]' na letra estimada; se não couber, a letra diminui; em último caso, '[…]'."""
    for p in range(pontos, 5, -1):
        if _largura_texto(A_PREENCHER, p) <= largura:
            return A_PREENCHER, p
    return "[…]", max(6, pontos)


def aplicar(tela, resultado, substituir=True):
    """Põe o esqueleto na tela (no tamanho que a imagem pede). Devolve os elementos criados."""
    if substituir:
        tela.elementos.clear()
        tela.ligacoes.clear()
    tela.mudar_tamanho(resultado["tamanho"])
    _alargar([d for d in resultado["elementos"] if d["tipo"] == "texto"],
             [d for d in resultado["elementos"] if d["tipo"] in ("texto", "imagem")], tela.largura)
    criados = []
    for d in resultado["elementos"]:
        e = Elemento(tela.novo_id(d["tipo"]), "caixa", d["x"], d["y"], d["largura"], d["altura"], "")
        e.borda_largura, e.raio = 0, 0
        if d["tipo"] in ("fundo", "painel", "linha", "forma"):
            e.fundo = d["fundo"]
            e.raio = d.get("raio", 0)
        elif d["tipo"] == "texto":
            e.texto, e.fonte = _texto_que_cabe(d["largura"], d["fonte"])
            e.cor, e.fundo = d["cor"], "transparent"
            e.espaco = "0px"
        else:                                   # ícone ou imagem: o espaço fica marcado
            e.fundo = "transparent"
            e.borda_largura, e.borda_cor, e.raio = 1, d["cor"], 3
            if d["largura"] >= 120 and d["altura"] >= 40:
                e.texto, e.cor, e.fonte = "[imagem a preencher]", d["cor"], 9
        tela.elementos.append(e)
        criados.append(e)
    return criados
