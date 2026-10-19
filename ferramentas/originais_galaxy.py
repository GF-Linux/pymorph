"""Gera o catálogo dos originais: os componentes do Galaxy (Uiverse.io, MIT) como foram escritos, para
rodarem no navegador embutido do PyMorph, com animação, ::before, rotação e o mouse por cima.

    python ferramentas/originais_galaxy.py /tmp/galaxy src/pymorph/catalogo/tailwind-3.4.16.js \\
        src/pymorph/catalogo/originais.json

Para cada item: abre no navegador embutido (rede bloqueada), acha a peça que conversa com o PyMorph
(o botão, o campo, a caixa de marcar; nos loaders, o todo) e mede o tamanho em 4 instantes da
animação, porque peça que anda sai da caixa do começo. Fica de fora o que não tem a peça ou passa de
480×320.
"""
import argparse
import json
import re
import sys
from pathlib import Path

from PySide6.QtCore import QRect, Qt, QTimer, QUrl
from PySide6.QtGui import QColor
from PySide6.QtWebEngineCore import QWebEngineUrlRequestInterceptor
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWidgets import QApplication

from pymorph.web import PECA

CATEGORIAS = {"Buttons": "botao", "Inputs": "caixa", "Checkboxes": "marcar", "Toggle-switches": "marcar",
              "loaders": "animacao"}
NOME = {"Buttons": "Botão", "Inputs": "Caixa", "Checkboxes": "Caixa de marcar", "Toggle-switches": "Toggle",
        "loaders": "Animação"}
MAXIMO = (480, 320)
MARGEM = 12

JS_MEDIR = """
(() => {
  const peca = %s;
  if (!peca) return JSON.stringify(null);
  const todos = [document.body.firstElementChild, ...document.body.firstElementChild.querySelectorAll('*')];
  const anims = document.getAnimations();
  const fim = Math.max(0, ...anims.map(a => { const t = a.effect.getComputedTiming();
                                              return (t.duration || 0) + (t.delay || 0); }));
  let x0 = 1e9, y0 = 1e9, x1 = -1e9, y1 = -1e9;
  for (const f of [0, 0.25, 0.5, 0.75]) {
    anims.forEach(a => { a.pause(); a.currentTime = fim * f; });
    for (const el of todos) { const r = el.getBoundingClientRect();
      if (r.width && r.height) { x0 = Math.min(x0, r.left); y0 = Math.min(y0, r.top);
                                 x1 = Math.max(x1, r.right); y1 = Math.max(y1, r.bottom); } }
  }
  const w = document.createTreeWalker(peca, NodeFilter.SHOW_TEXT); let n, texto = '';
  while ((n = w.nextNode())) if (n.textContent.trim()) { texto = n.textContent.trim(); break; }
  anims.forEach(a => { a.currentTime = 0; });
  return JSON.stringify({w: x1 - x0, h: y1 - y0, x: x0, y: y0, texto: texto, animado: anims.length > 0});
})()
"""


def visiveis(imagem, fundo):
    """Quantos pontos se distinguem do fundo: o original aparece mais no claro ou no escuro?"""
    n = 0
    for y in range(0, imagem.height(), 2):
        for x in range(0, imagem.width(), 2):
            c = QColor(imagem.pixel(x, y))
            n += abs(c.red() - fundo.red()) + abs(c.green() - fundo.green()) + abs(c.blue() - fundo.blue()) > 60
    return n


class SemRede(QWebEngineUrlRequestInterceptor):
    def interceptRequest(self, info):
        if info.requestUrl().scheme() not in ("file", "data", "qrc", "about"):
            info.block(True)


class Gerador:
    def __init__(self, galaxy, tailwind, saida, paralelos):
        self.tailwind = Path(tailwind).resolve()
        self.saida = Path(saida)
        self.fila = [(c, f) for c in CATEGORIAS for f in sorted((Path(galaxy) / c).glob("*.html"))]
        self.total = len(self.fila)
        self.itens, self.fora = [], 0
        self.interceptor = SemRede()
        self.vistas, self.ativos = [], 0
        for _ in range(paralelos):
            v = QWebEngineView()
            v.page().profile().setUrlRequestInterceptor(self.interceptor)
            v.resize(900, 700)
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
        html = re.sub(r"^\s*<!--.*?-->", "", arquivo.read_text(errors="ignore"), flags=re.S).strip()
        tailwind = not re.search(r"<style", html)
        pagina = ("<!doctype html><html><head><meta charset='utf-8'>"
                  + (f"<script src='{self.tailwind.as_uri()}'></script>" if tailwind else "")
                  + "<style>html,body{margin:0;height:100%;background:#fff}"
                    "body{display:flex;align-items:center;justify-content:center}</style></head><body>"
                  + html + "</body></html>")

        def carregou(_):
            QTimer.singleShot(900 if tailwind else 250, medir)

        def medir():
            vista.page().runJavaScript(JS_MEDIR % PECA[CATEGORIAS[cat]], 0, lambda r: guardar(r))

        def guardar(r):
            dados = json.loads(r) if r else None
            if dados and 6 <= dados["w"] <= MAXIMO[0] and 6 <= dados["h"] <= MAXIMO[1]:
                caixa = QRect(round(dados["x"]) - MARGEM, round(dados["y"]) - MARGEM,
                              round(dados["w"]) + 2 * MARGEM, round(dados["h"]) + 2 * MARGEM)
                claro = vista.grab().toImage().copy(caixa)
                vista.page().runJavaScript("document.body.style.background = '#212121'; 1", 0,
                                           lambda _: QTimer.singleShot(80, lambda: decidir(dados, claro, caixa)))
                return
            concluir(dados, False)

        def decidir(dados, claro, caixa):
            escuro = vista.grab().toImage().copy(caixa)
            concluir(dados, visiveis(escuro, QColor("#212121")) > 1.3 * visiveis(claro, QColor("#ffffff")))

        def concluir(dados, fundo_escuro):
            if (dados and 6 <= dados["w"] <= MAXIMO[0] and 6 <= dados["h"] <= MAXIMO[1]):
                autor, _, nome = arquivo.stem.partition("_")
                self.itens.append({
                    "id": f"{autor}/{nome}", "autor": autor, "url": f"https://uiverse.io/{autor}/{nome}",
                    "categoria": NOME[cat], "tipo": CATEGORIAS[cat],
                    "largura": round(dados["w"]) + 2 * MARGEM, "altura": round(dados["h"]) + 2 * MARGEM,
                    "texto": dados["texto"][:40], "animado": dados["animado"], "escuro": fundo_escuro,
                    "tailwind": tailwind, "html": html})
            else:
                self.fora += 1
            feitos = self.total - len(self.fila)
            if feitos % 200 == 0:
                print(f"{feitos}/{self.total}  dentro {len(self.itens)}  fora {self.fora}", flush=True)
            self.proximo(vista)

        vista.loadFinished.connect(carregou, Qt.ConnectionType.SingleShotConnection)
        vista.setHtml(pagina, QUrl.fromLocalFile(str(self.tailwind.parent) + "/"))

    def terminar(self):
        self.saida.parent.mkdir(parents=True, exist_ok=True)
        self.saida.write_text(json.dumps({
            "fonte": "https://github.com/uiverse-io/galaxy",
            "licenca": "MIT — Copyright (c) 2023 Uiverse.io; cada item é de quem o criou (autor e url)",
            "itens": self.itens}, ensure_ascii=False, separators=(",", ":")) + "\n")
        print(f"pronto: {len(self.itens)} originais, {self.fora} de fora → {self.saida}")
        QApplication.quit()


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("galaxy")
    ap.add_argument("tailwind")
    ap.add_argument("saida")
    ap.add_argument("--paralelos", type=int, default=6)
    args = ap.parse_args()
    app = QApplication(sys.argv[:1])
    gerador = Gerador(args.galaxy, args.tailwind, args.saida, args.paralelos)
    QTimer.singleShot(0, gerador.comecar)
    app.exec()


if __name__ == "__main__":
    main()
