"""Gera o catálogo de estilos e layouts prontos a partir do Galaxy (github.com/uiverse-io/galaxy, MIT).

Roda uma vez, por quem mantém o PyMorph; o PyMorph não precisa de navegador para usar o catálogo.

    git clone --depth 1 https://github.com/uiverse-io/galaxy.git /tmp/galaxy
    curl -L -o /tmp/tailwind.js https://cdn.tailwindcss.com/3.4.16
    python ferramentas/catalogo_galaxy.py /tmp/galaxy /tmp/tailwind.js src/pymorph/catalogo/galaxy.json

Precisa do PySide6 completo (o QtWebEngine). Para cada item:
  1. o navegador embutido abre o HTML com a rede bloqueada (sem fonte nem imagem de fora) e com
     transições e animações desligadas, para ler o estado parado;
  2. lê o estilo que o navegador calculou (resolve o Tailwind e a cascata) e o destaque: as regras
     :hover (no botão) e :focus (na caixa) viram uma classe, e a classe é posta no elemento;
  3. traduz para os campos do PyMorph (cor, fundo, gradiente, borda, cantos, espaço, sombra, letra);
  4. desenha o resultado com o próprio PyMorph e compara com a imagem do navegador. Só entra quem
     fica parecido: animação, ::before, transform e ícone em SVG não existem no QSS.
Nos layouts (Formulários e Cards), todo texto vira "[a preencher]": o desenho vem, o conteúdo é seu.
"""
import argparse
import json
import math
import re
import sys
from pathlib import Path

from PySide6.QtCore import QRect, Qt, QTimer, QUrl
from PySide6.QtGui import QColor, QFont, QFontMetrics, QImage, QPainter
from PySide6.QtWebEngineCore import QWebEngineUrlRequestInterceptor
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWidgets import QApplication, QWidget

from pymorph.editor import criar_widget
from pymorph.tela import Elemento, Tela

CATEGORIAS = {"Buttons": "botao", "Inputs": "caixa", "Forms": "Formulário", "Cards": "Card"}
A_PREENCHER = "[a preencher]"
# a nota mínima para entrar, calibrada olhando as comparações lado a lado (--fotos)
MINIMO_ESTILO, MINIMO_LAYOUT = 0.80, 0.88
JANELA = (900, 900)

JS_COMUM = r"""
window.__pm = (() => {
  const px = v => parseFloat(v) || 0;
  const visivel = el => { const s = getComputedStyle(el), r = el.getBoundingClientRect();
    return r.width > 0 && r.height > 0 && s.visibility !== 'hidden' && s.display !== 'none' && px(s.opacity) > 0.05; };
  const textoDireto = el => [...el.childNodes].filter(n => n.nodeType === 3 && n.textContent.trim());
  const corDoTexto = el => {           // a cor e a letra de quem tem o texto, não do embrulho
    const w = document.createTreeWalker(el, NodeFilter.SHOW_TEXT);
    let n; while ((n = w.nextNode())) if (n.textContent.trim()) return getComputedStyle(n.parentElement);
    return getComputedStyle(el);
  };
  const ler = el => {
    const s = getComputedStyle(el), t = corDoTexto(el), r = el.getBoundingClientRect();
    return {color: t.color, fontFamily: t.fontFamily, fontSize: t.fontSize, fontWeight: t.fontWeight,
      backgroundColor: s.backgroundColor, backgroundImage: s.backgroundImage,
      bw: [s.borderTopWidth, s.borderRightWidth, s.borderBottomWidth, s.borderLeftWidth].map(px),
      bs: [s.borderTopStyle, s.borderRightStyle, s.borderBottomStyle, s.borderLeftStyle],
      bc: [s.borderTopColor, s.borderRightColor, s.borderBottomColor, s.borderLeftColor],
      raio: px(s.borderTopLeftRadius), boxShadow: s.boxShadow, transform: s.transform,
      padding: [s.paddingTop, s.paddingRight, s.paddingBottom, s.paddingLeft].map(px),
      x: r.x, y: r.y, w: r.width, h: r.height,
      texto: (el.innerText || el.value || '').replace(/\s+/g, ' ').trim(),
      dica: el.placeholder || ''};
  };
  const destaque = (el, pseudo) => {   // :hover/:focus viram a classe pm-d, posta no elemento e nos pais
    const regras = [];
    const varrer = lista => { for (const r of lista) {
      if (r.cssRules && !r.selectorText) varrer(r.cssRules);
      else if (r.selectorText && r.selectorText.includes(pseudo))
        regras.push(r.selectorText.split(pseudo).join('.pm-d') + '{' + r.style.cssText + '}');
    } };
    for (const f of document.styleSheets) { try { varrer(f.cssRules); } catch (e) {} }
    const folha = document.createElement('style'); folha.textContent = regras.join('\n');
    document.head.appendChild(folha);
    for (let a = el; a; a = a.parentElement) a.classList.add('pm-d');
    const d = ler(el);
    for (let a = el; a; a = a.parentElement) a.classList.remove('pm-d');
    folha.remove();
    return d;
  };
  const principal = tipo => tipo === 'botao'
    ? document.querySelector('button, input[type=submit], input[type=button], a, [role=button], .btn, .button')
    : document.querySelector('input:not([type=checkbox]):not([type=radio]):not([type=submit]):not([type=button]):not([type=range]), textarea');
  const estilo = tipo => { const el = principal(tipo); if (!el || !visivel(el)) return null;
    const base = ler(el); base.destaque = destaque(el, tipo === 'botao' ? ':hover' : ':focus'); return base; };
  const layout = () => {
    const raiz = document.body.firstElementChild; if (!raiz) return null;
    const rr = raiz.getBoundingClientRect(), itens = [], dentro = new Set();
    const caixaDe = el => { const s = getComputedStyle(el);
      return (s.backgroundColor !== 'rgba(0, 0, 0, 0)' || s.backgroundImage !== 'none'
              || px(s.borderTopWidth) + px(s.borderBottomWidth) > 0 || s.boxShadow !== 'none'); };
    for (const el of [raiz, ...raiz.querySelectorAll('*')]) {
      if ([...dentro].some(d => d.contains(el)) || !visivel(el)) continue;
      const tag = el.tagName.toLowerCase(), tipoInput = (el.type || '').toLowerCase();
      let tipo = null;
      if (tag === 'textarea' || tag === 'select' || (tag === 'input' && !['checkbox', 'radio', 'submit', 'button', 'range', 'hidden', 'file'].includes(tipoInput))) tipo = 'entrada';
      else if (tag === 'input' && ['checkbox', 'radio'].includes(tipoInput)) tipo = 'marcar';
      else if (tag === 'button' || (tag === 'input' && ['submit', 'button'].includes(tipoInput)) || (tag === 'a' && caixaDe(el))) tipo = 'botao';
      else if (tag === 'img' || tag === 'svg' || tag === 'canvas' || tag === 'video') tipo = 'imagem';
      if (tipo) { const d = ler(el); d.tipo = tipo; itens.push(d); dentro.add(el); continue; }
      if (caixaDe(el)) { const d = ler(el); d.tipo = 'fundo'; d.texto = ''; itens.push(d); }
      for (const n of textoDireto(el)) {
        const r = document.createRange(); r.selectNodeContents(n); const b = r.getBoundingClientRect();
        if (b.width < 1 || b.height < 1) continue;
        const s = getComputedStyle(el);
        itens.push({tipo: 'texto', texto: n.textContent.replace(/\s+/g, ' ').trim(), color: s.color,
          fontFamily: s.fontFamily, fontSize: s.fontSize, fontWeight: s.fontWeight,
          backgroundColor: 'rgba(0, 0, 0, 0)', backgroundImage: 'none', bw: [0, 0, 0, 0], bs: [], bc: [],
          raio: 0, boxShadow: 'none', transform: s.transform, padding: [0, 0, 0, 0],
          x: b.x, y: b.y, w: b.width, h: b.height, dica: ''});
      }
    }
    return {x: rr.x, y: rr.y, w: rr.width, h: rr.height, itens};
  };
  return {estilo, layout};
})();
"""


class SemRede(QWebEngineUrlRequestInterceptor):
    """Só arquivo local e data: — nada de fonte, imagem ou script de fora."""
    def interceptRequest(self, info):
        if info.requestUrl().scheme() not in ("file", "data", "qrc", "about"):
            info.block(True)


# ── tradução: estilo calculado pelo navegador → campos do PyMorph ───────────

def _rgba(c):
    m = re.match(r"rgba?\(([^)]+)\)", c or "")
    if not m:
        return None
    p = [x.strip() for x in m.group(1).replace("/", ",").split(",")]
    r, g, b = (round(float(x)) for x in p[:3])
    a = float(p[3].rstrip("%")) / (100 if p[3].endswith("%") else 1) if len(p) > 3 else 1.0
    return r, g, b, a


def cor(c):
    """'rgba(1, 2, 3, 0.5)' → '#rrggbb', ou '#aarrggbb' com transparência (o formato do Qt)."""
    v = _rgba(c)
    if v is None or v[3] == 0:
        return None
    r, g, b, a = v
    return f"#{r:02x}{g:02x}{b:02x}" if a >= 0.999 else f"#{round(a * 255):02x}{r:02x}{g:02x}{b:02x}"


def gradiente(imagem):
    m = re.fullmatch(r"linear-gradient\((.*)\)", (imagem or "").strip())
    if not m:
        return None
    partes = re.split(r",(?![^(]*\))", m.group(1))
    angulo = 180.0
    primeiro = partes[0].strip()
    if primeiro.endswith("deg") or primeiro.startswith("to "):
        partes.pop(0)
        cantos = {"to right": 90, "to left": 270, "to bottom": 180, "to top": 0, "to bottom right": 135,
                  "to right bottom": 135, "to top right": 45, "to right top": 45, "to bottom left": 225,
                  "to left bottom": 225, "to top left": 315, "to left top": 315}
        angulo = cantos.get(primeiro, float(primeiro[:-3]) if primeiro.endswith("deg") else 180)
    rad = math.radians(angulo)
    x2, y2 = 0.5 + 0.5 * math.sin(rad), 0.5 - 0.5 * math.cos(rad)
    paradas = []
    for i, p in enumerate(partes):
        c = re.search(r"rgba?\([^)]+\)", p)
        if not c:
            return None
        pos = re.search(r"([\d.]+)%", p[c.end():])
        v = _rgba(c.group())
        paradas.append((float(pos.group(1)) / 100 if pos else i / max(1, len(partes) - 1),
                        f"rgba({v[0]}, {v[1]}, {v[2]}, {round(v[3] * 255)})"))
    return (f"qlineargradient(x1:{1 - x2:.2f}, y1:{1 - y2:.2f}, x2:{x2:.2f}, y2:{y2:.2f}, "
            + ", ".join(f"stop:{min(1, s):.2f} {c}" for s, c in paradas) + ")")


def sombra(box_shadow):
    if not box_shadow or box_shadow == "none":
        return ""
    primeira = re.split(r",(?![^(]*\))", box_shadow)[0]
    if "inset" in primeira:
        return ""
    c = re.search(r"rgba?\([^)]+\)", primeira)
    numeros = re.findall(r"(-?[\d.]+)px", primeira.replace(c.group(), "") if c else primeira)
    if not c or len(numeros) < 3 or cor(c.group()) is None:
        return ""
    v = _rgba(c.group())
    qt = f"#{round(v[3] * 255):02x}{v[0]:02x}{v[1]:02x}{v[2]:02x}"
    return f"{float(numeros[0]):g} {float(numeros[1]):g} {float(numeros[2]):g} {qt}"


def familia(pilha):
    nomes = [n.strip().strip("\"'").lower() for n in (pilha or "").split(",")]
    for generica in ("monospace", "cursive"):
        if generica in nomes:
            return generica
    if "serif" in nomes and "sans-serif" not in nomes:
        return "serif"
    return ""


def visual(d, tipo):
    """Os campos do PyMorph que reproduzem o estilo calculado."""
    v = {}
    fundo = gradiente(d["backgroundImage"]) if d["backgroundImage"] != "none" else None
    if d["backgroundImage"] != "none" and fundo is None:
        v["_perde"] = "fundo"
    fundo = fundo or cor(d["backgroundColor"])
    if fundo:
        v["fundo"] = fundo
    elif tipo in ("botao", "caixa", "entrada"):
        v["fundo"] = "transparent"      # no navegador é transparente; no Qt, campo e botão nascem com fundo
    if cor(d["color"]):
        v["cor"] = cor(d["color"])
    lados = [w if s not in ("none", "hidden") and cor(c) else 0      # borda transparente não aparece
             for w, s, c in zip(d["bw"], d["bs"] or ["none"] * 4, d["bc"] or [""] * 4)]
    if tipo != "texto":
        if max(lados) == 0:
            v["borda_largura"] = 0
        else:
            if len(set(lados)) > 1:     # borda de um lado só (um sublinhado, um divisor): o PyMorph não tem
                v["_perde"] = "borda"
                v["borda_largura"] = 0
            else:
                v["borda_largura"] = round(max(lados))
                v["borda_cor"] = cor(d["bc"][0])
        v["raio"] = round(min(d["raio"], d["h"] / 2))
        # no navegador o espaço interno faz o botão crescer em volta do texto; no PyMorph o tamanho é de
        # quem desenha e o espaço só espremeria o texto. Na caixa fica o recuo dos lados, até 16 px.
        if tipo in ("caixa", "entrada"):
            v["espaco"] = f"0px {min(16, round(d['padding'][1]))}px 0px {min(16, round(d['padding'][3]))}px"
    if sombra(d["boxShadow"]):
        v["sombra"] = sombra(d["boxShadow"])
    v["fonte"] = max(6, round(float(d["fontSize"].rstrip("px") or 13) * 0.75))
    v["negrito"] = int(float(d["fontWeight"] or 400)) >= 600
    if familia(d["fontFamily"]):
        v["familia"] = familia(d["fontFamily"])
    destaque = d.get("destaque")
    if destaque:
        for campo, base, novo in (("destaque_fundo", fundo,
                                   gradiente(destaque["backgroundImage"]) or cor(destaque["backgroundColor"])),
                                  ("destaque_cor", cor(d["color"]), cor(destaque["color"])),
                                  ("destaque_borda", v.get("borda_cor"), cor(destaque["bc"][0]))):
            if novo and novo != base:
                v[campo] = novo
    return v


def elemento(d, tipo, x, y, texto):
    campos = {k: val for k, val in visual(d, "texto" if tipo == "texto" else tipo).items() if not k.startswith("_")}
    largura = d["w"]
    if tipo == "texto":
        campos = {k: val for k, val in campos.items() if k in ("cor", "fonte", "negrito", "familia")}
        largura = d["w"] * 1.15 + 8     # a letra do Qt é um pouco mais larga: sem folga, quebra a linha
    return {"tipo": {"texto": "caixa", "fundo": "caixa", "imagem": "caixa", "entrada": "caixa"}.get(tipo, tipo),
            "x": round(x), "y": round(y), "largura": max(8, round(largura)), "altura": max(8, round(d["h"])),
            "texto": texto, "digitavel": tipo == "entrada", **campos}


def _luminancia(r, g, b):
    def canal(c):
        c /= 255
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    return 0.2126 * canal(r) + 0.7152 * canal(g) + 0.0722 * canal(b)


def contraste(v):
    """A razão de contraste (WCAG) entre a cor do texto e o fundo; fundo transparente é o branco da tela,
    gradiente é a média das paradas. Botão de texto invisível tirava nota alta: há pouco o que comparar."""
    texto = QColor(v.get("cor") or "#000000")
    fundo = v.get("fundo", "")
    if fundo.startswith("qlineargradient"):
        cores = [QColor(int(r), int(g), int(b)) for r, g, b, _ in re.findall(r"rgba\((\d+), (\d+), (\d+), (\d+)\)", fundo)]
    else:
        cores = [QColor(fundo)] if fundo and fundo != "transparent" else []
    cores = [c for c in cores if c.isValid() and c.alpha() > 40] or [QColor("#ffffff")]
    media = [sum(getattr(c, k)() for c in cores) / len(cores) for k in ("red", "green", "blue")]
    a, b = _luminancia(texto.red(), texto.green(), texto.blue()), _luminancia(*media)
    return (max(a, b) + 0.05) / (min(a, b) + 0.05)


# ── comparação ─────────────────────────────────────────────────────────────

def desenhar(elementos, largura, altura):
    """O desenho do PyMorph, como o editor e a tela rodando fazem."""
    tela = Tela(largura=largura, altura=altura)
    fundo = QWidget()
    fundo.resize(largura, altura)
    fundo.setObjectName("fundo")        # com seletor: sem ele, o branco valeria para todos os filhos
    fundo.setStyleSheet("QWidget#fundo { background: #ffffff; }")
    fundo.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen)
    for i, campos in enumerate(elementos):
        e = Elemento(f"e{i}", **{k: v for k, v in campos.items() if k in Elemento.__dataclass_fields__})
        tela.elementos.append(e)
        criar_widget(e, fundo, tela.papel(e.id))
    fundo.show()
    QApplication.processEvents()
    imagem = fundo.grab().toImage()
    fundo.deleteLater()
    return imagem


def parecenca(a, b):
    """1 = igual. Dos pontos onde uma das duas imagens tem algo desenhado, a fração que bate (cor a
    menos de 12% de distância). A média enganava: um card torto com o mesmo fundo escuro tirava 0,87.
    Nada desenhado nas duas é 0: não há o que mostrar."""
    a = a.convertToFormat(QImage.Format.Format_RGB32).scaled(160, 160 * a.height() // max(1, a.width()))
    b = b.convertToFormat(QImage.Format.Format_RGB32).scaled(a.width(), a.height())
    soma = n = 0
    for y in range(a.height()):
        for x in range(a.width()):
            p, q = QColor(a.pixel(x, y)), QColor(b.pixel(x, y))
            if p.lightness() > 250 and q.lightness() > 250:
                continue
            distancia = (abs(p.red() - q.red()) + abs(p.green() - q.green()) + abs(p.blue() - q.blue())) / 765
            soma += distancia > 0.12
            n += 1
    return 0.0 if n == 0 else 1 - soma / n


# ── o laço ─────────────────────────────────────────────────────────────────

class Gerador:
    def __init__(self, galaxy, tailwind, saida, categorias, limite, fotos, paralelos):
        self.tailwind = Path(tailwind).resolve()
        self.saida, self.fotos = Path(saida), Path(fotos) if fotos else None
        self.fila = []
        for cat in categorias:
            arquivos = sorted((Path(galaxy) / cat).glob("*.html"))
            self.fila += [(cat, f) for f in (arquivos[:limite] if limite else arquivos)]
        self.total = len(self.fila)
        self.estilos, self.layouts, self.notas = [], [], []
        self.ativos = 0
        self.interceptor = SemRede()
        self.vistas = []
        for _ in range(paralelos):
            v = QWebEngineView()
            v.page().profile().setUrlRequestInterceptor(self.interceptor)
            v.resize(*JANELA)
            v.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen)
            v.show()
            self.vistas.append(v)

    def comecar(self):
        for v in self.vistas:
            self.ativos += 1
            self.proximo(v)

    def proximo(self, vista):
        if not self.fila:
            self.ativos -= 1
            if self.ativos == 0:
                self.terminar()
            return
        cat, arquivo = self.fila.pop(0)
        html = arquivo.read_text(errors="ignore")
        tailwind = not re.search(r"<style", html)
        pagina = ("<!doctype html><html><head><meta charset='utf-8'>"
                  + (f"<script src='{self.tailwind.as_uri()}'></script>" if tailwind else "")
                  + "<style>html,body{margin:0;min-height:100%;background:#fff}"
                    "body{display:flex;align-items:center;justify-content:center;min-height:900px}"
                    "*,*::before,*::after{transition:none!important;animation:none!important}</style>"
                  + "</head><body>" + re.sub(r"^\s*<!--.*?-->", "", html, flags=re.S).strip()
                  + f"<script>{JS_COMUM}</script></body></html>")

        def carregou(_):
            QTimer.singleShot(900 if tailwind else 250, ler)

        def ler():
            js = (f"JSON.stringify(window.__pm.estilo('{CATEGORIAS[cat]}'))" if cat in ("Buttons", "Inputs")
                  else "JSON.stringify(window.__pm.layout())")
            vista.page().runJavaScript(js, 0, lambda r: guardar(r))

        def guardar(resultado):
            try:
                self.processar(cat, arquivo, json.loads(resultado) if resultado else None,
                               vista.grab().toImage(), tailwind)
            except Exception as erro:  # um item quebrado não para o catálogo
                print(f"  ✕ {arquivo.name}: {type(erro).__name__}: {erro}", file=sys.stderr)
            feitos = self.total - len(self.fila)
            if feitos % 100 == 0:
                print(f"{feitos}/{self.total}  estilos {len(self.estilos)}  layouts {len(self.layouts)}", flush=True)
            self.proximo(vista)

        vista.loadFinished.connect(carregou, Qt.ConnectionType.SingleShotConnection)
        vista.setHtml(pagina, QUrl.fromLocalFile(str(self.tailwind.parent) + "/"))

    def processar(self, cat, arquivo, dados, foto, tailwind):
        if not dados:
            return
        autor, _, nome = arquivo.stem.partition("_")
        base = {"id": f"{autor}/{nome}", "autor": autor, "url": f"https://uiverse.io/{autor}/{nome}"}
        if cat in ("Buttons", "Inputs"):
            tipo = CATEGORIAS[cat]
            v = visual(dados, tipo)
            perde = v.pop("_perde", None)
            texto = dados["texto"] or dados["dica"] or ("Botão" if tipo == "botao" else "Texto")
            campos = elemento(dados, "entrada" if tipo == "caixa" else "botao", 0, 0, texto)
            margem = 16
            x0, y0 = dados["x"] - margem, dados["y"] - margem
            largura, altura = round(dados["w"]) + 2 * margem, round(dados["h"]) + 2 * margem
            campos["x"], campos["y"] = margem, margem
            web = foto.copy(QRect(round(x0), round(y0), largura, altura))
            nota = parecenca(web, desenhar([campos], largura, altura))
            item = {**base, "tipo": tipo, "largura": campos["largura"], "altura": campos["altura"],
                    "texto": texto, "nota": round(nota, 3),
                    "visual": {k: val for k, val in v.items() if not k.startswith("_")}}
            if contraste(v) < 3:
                perde = "contraste"
            self.notas.append((nota, cat, arquivo.stem, perde))
            if perde is None:
                self.estilos.append(item)
        else:
            margem = 16
            x0, y0 = dados["x"] - margem, dados["y"] - margem
            largura, altura = round(dados["w"]) + 2 * margem, round(dados["h"]) + 2 * margem
            if (len(dados["itens"]) < 3 or largura > 1000 or altura > 1000 or dados["w"] < 120 or dados["h"] < 80
                    or any(d.get("transform", "none") != "none" for d in dados["itens"])):
                return
            originais, finais = [], []
            for d in dados["itens"]:
                texto = d["texto"] if d["tipo"] in ("texto", "botao") else (d["dica"] if d["tipo"] == "entrada" else "")
                if d["tipo"] == "imagem":
                    texto = ""
                campos = elemento(d, d["tipo"], d["x"] - x0, d["y"] - y0, texto)
                originais.append(campos)
                final = dict(campos)
                if d["tipo"] in ("texto", "botao", "entrada") and texto:
                    final["texto"] = A_PREENCHER
                if d["tipo"] == "texto" and texto:     # "[a preencher]" é mais comprido que "Nome"
                    letra = QFont(final.get("familia") or QFont().family())
                    letra.setPointSize(final.get("fonte") or 10)
                    letra.setBold(final.get("negrito", False))
                    final["largura"] = max(final["largura"], QFontMetrics(letra).horizontalAdvance(A_PREENCHER) + 10)
                if d["tipo"] == "imagem":
                    final.update(texto="[imagem a preencher]", fundo="#eef1f4", borda_largura=1,
                                 borda_cor="#c3c9d0", raio=6)
                finais.append(final)
            web = foto.copy(QRect(round(x0), round(y0), largura, altura))
            nota = parecenca(web, desenhar(originais, largura, altura))
            self.notas.append((nota, cat, arquivo.stem, None))
            self.layouts.append({**base, "categoria": CATEGORIAS[cat], "largura": largura, "altura": altura,
                                 "nota": round(nota, 3), "elementos": finais})
        if self.fotos is not None:
            self.fotos.mkdir(parents=True, exist_ok=True)
            par = QImage(web.width() * 2 + 8, web.height(), QImage.Format.Format_RGB32)
            par.fill(QColor("#dfe3e8"))
            p = QPainter(par)
            p.drawImage(0, 0, web)
            p.drawImage(web.width() + 8, 0, desenhar(
                [campos] if cat in ("Buttons", "Inputs") else originais, web.width(), web.height()))
            p.end()
            par.save(str(self.fotos / f"{nota:.3f}_{cat}_{arquivo.stem}.png"))

    def terminar(self):
        catalogo = {
            "fonte": "https://github.com/uiverse-io/galaxy",
            "licenca": "MIT — Copyright (c) 2023 Uiverse.io; cada item é de quem o criou (autor e url)",
            "estilos": sorted((i for i in self.estilos if i["nota"] >= MINIMO_ESTILO), key=lambda i: -i["nota"]),
            "layouts": sorted((i for i in self.layouts if i["nota"] >= MINIMO_LAYOUT), key=lambda i: -i["nota"]),
        }
        self.saida.parent.mkdir(parents=True, exist_ok=True)
        self.saida.write_text(json.dumps(catalogo, ensure_ascii=False, separators=(",", ":")) + "\n")
        (self.saida.parent / (self.saida.stem + ".notas.tsv")).write_text(
            "\n".join(f"{n:.3f}\t{c}\t{a}\t{p or ''}" for n, c, a, p in sorted(self.notas, reverse=True)) + "\n")
        print(f"pronto: {len(catalogo['estilos'])} de {len(self.estilos)} estilos e {len(catalogo['layouts'])} de "
              f"{len(self.layouts)} layouts passaram → {self.saida}")
        QApplication.quit()


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("galaxy")
    ap.add_argument("tailwind")
    ap.add_argument("saida")
    ap.add_argument("--categorias", default=",".join(CATEGORIAS))
    ap.add_argument("--limite", type=int, default=0, help="só os N primeiros de cada categoria")
    ap.add_argument("--fotos", help="pasta para as comparações lado a lado (web | PyMorph)")
    ap.add_argument("--paralelos", type=int, default=4)
    args = ap.parse_args()
    app = QApplication(sys.argv[:1])
    gerador = Gerador(args.galaxy, args.tailwind, args.saida, args.categorias.split(","), args.limite,
                      args.fotos, args.paralelos)
    QTimer.singleShot(0, gerador.comecar)
    app.exec()


if __name__ == "__main__":
    main()
