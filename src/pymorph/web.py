"""Os originais: componentes do Galaxy (Uiverse.io, MIT) rodando como foram escritos, num navegador
embutido (QtWebEngine) por cima do controle do Qt.

O controle do Qt continua na tela, escondido: ele guarda o que foi digitado, se está marcado e o
clique, e é dele que o executor lê. A pele (o original no navegador) só desenha e avisa:
  clique no botão → `clicou`; digitou no campo → `mudou_valor`; marcou → `mudou_marcado`.
O caminho de volta (o resultado no campo, o botão desligado enquanto a função roda) vai por JavaScript.

Todas as peles dividem um processo de navegador e a rede fica bloqueada: o original não busca fonte,
imagem nem nada de fora. Medido (PySide6 6.12): o primeiro original custa ~205 MB; cada outro, ~2,5 MB.
"""
import atexit
import html
import json
import os
import weakref
from functools import cache
from importlib import resources

# antes do navegador nascer: um processo para todos (sem isto, um por original)
_FLAGS = os.environ.get("QTWEBENGINE_CHROMIUM_FLAGS", "")
if "--renderer-process-limit" not in _FLAGS:
    os.environ["QTWEBENGINE_CHROMIUM_FLAGS"] = (_FLAGS + " --renderer-process-limit=1").strip()

from PySide6.QtCore import QEvent, Qt, QUrl, Signal  # noqa: E402
from PySide6.QtWebEngineCore import QWebEnginePage, QWebEngineProfile, QWebEngineUrlRequestInterceptor  # noqa: E402
from PySide6.QtWebEngineWidgets import QWebEngineView  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402
import shiboken6  # noqa: E402

TAILWIND = "tailwind-3.4.16.js"
MARGEM = 12         # a mesma folga do catálogo: sombra e brilho passam da caixa do elemento

# a peça do original que conversa com o PyMorph, por tipo
PECA = {
    "botao": "document.querySelector('button, input[type=submit], input[type=button], a, [role=button], .btn, .button')",
    "caixa": "document.querySelector('input:not([type=checkbox]):not([type=radio]):not([type=submit])"
             ":not([type=button]):not([type=range]), textarea')",
    "marcar": "document.querySelector('input[type=checkbox], input[type=radio]')",
    "animacao": "document.body.firstElementChild",
}

PONTE = """
(() => {
  const peca = %(peca)s, tipo = %(tipo)s;
  const primeiroTexto = () => { if (!peca) return null;
    const w = document.createTreeWalker(peca, NodeFilter.SHOW_TEXT); let n;
    while ((n = w.nextNode())) if (n.textContent.trim()) return n; return null; };
  const visivel = (el, p) => { const s = getComputedStyle(el, p);
    return s.display !== 'none' && s.visibility !== 'hidden' && s.width !== '0px' && parseFloat(s.opacity) > 0.05; };
  const textoDoCss = raiz => {         // texto de ::before/::after { content: "..." }: o visível primeiro
    const achados = [];
    for (const el of [raiz, ...raiz.querySelectorAll('*')]) for (const p of ['::before', '::after']) {
      const c = getComputedStyle(el, p).content;
      if (c && c.startsWith('"') && c.length > 3) achados.push([el, p]); }
    return achados.find(([el, p]) => visivel(el, p)) || achados[0] || null; };
  const letraALetra = raiz => {         // um elemento por letra (para animar cada uma): o que tiver
    for (const el of [raiz, ...raiz.querySelectorAll('*')]) {
      const filhos = [...el.children];
      if (filhos.length >= 2 && filhos.every(c => c.children.length === 0 && c.textContent.trim().length <= 1)
          && el.textContent.trim().length >= 2) return el; }
    return null; };
  const trocarTexto = (raiz, t) => {
    const letras = letraALetra(raiz);
    if (letras) {                       // refaz as letras com o molde da primeira, renumerando o atraso
      const molde = letras.children[0].cloneNode(true); letras.textContent = '';
      [...t].forEach((ch, i) => { const c = molde.cloneNode(true); c.textContent = ch === ' ' ? '\u00a0' : ch;
        const s = c.getAttribute('style'); if (s) c.setAttribute('style', s.replace(/(--[\w-]*:\s*)\d+/, '$1' + i));
        letras.appendChild(c); });
      return true; }
    const w = document.createTreeWalker(raiz, NodeFilter.SHOW_TEXT); let n;
    while ((n = w.nextNode())) if (n.textContent.trim()) {
      if (n.textContent.trim().length >= 3) n.textContent = t;
      return true; }                   // um ícone ("×") fica: o texto não caberia nele
    const css = textoDoCss(raiz);
    if (css) { css[0].setAttribute('data-pm-texto', '');
      const s = document.createElement('style');
      s.textContent = `[data-pm-texto]${css[1]}{content:${JSON.stringify(t)} !important}`;
      document.head.appendChild(s); return true; }
    return false; };
  const dicaOriginal = peca && peca.placeholder;
  window.__pm = {
    texto(t) { if (!peca || !t) return;
      if (tipo === 'caixa') {             // a dica vai para onde o original põe a dele: dica ou rótulo
        const rotulo = document.querySelector('label');
        if (dicaOriginal || !rotulo || !trocarTexto(rotulo, t)) peca.placeholder = t;
        return; }
      trocarTexto(peca, t); },
    medir() {                            // o que o original ocupa de verdade, com o texto de quem desenha
      let x0 = 1e9, y0 = 1e9, x1 = -1e9, y1 = -1e9;
      const somar = r => { if (r.width && r.height) { x0 = Math.min(x0, r.left); y0 = Math.min(y0, r.top);
                                                       x1 = Math.max(x1, r.right); y1 = Math.max(y1, r.bottom); } };
      const raiz = document.body.firstElementChild; if (!raiz) return null;
      // mede com a página larga: na largura atual, um texto maior quebraria a linha em vez de pedir espaço
      const antes = [document.documentElement.style.width, document.body.style.width];
      document.documentElement.style.width = document.body.style.width = '4000px';
      for (const el of [raiz, ...raiz.querySelectorAll('*')]) somar(el.getBoundingClientRect());
      const w = document.createTreeWalker(raiz, NodeFilter.SHOW_TEXT); let n;
      while ((n = w.nextNode())) { const r = document.createRange(); r.selectNodeContents(n); somar(r.getBoundingClientRect()); }
      if (peca) { const r = peca.getBoundingClientRect();
        somar({left: r.left, top: r.top, width: peca.scrollWidth, height: peca.scrollHeight,
               right: r.left + peca.scrollWidth, bottom: r.top + peca.scrollHeight}); }
      [document.documentElement.style.width, document.body.style.width] = antes;
      return JSON.stringify({w: Math.ceil(x1 - x0), h: Math.ceil(y1 - y0)}); },
    valor(v) { if (peca) peca.value = v; },
    marcado(b) { if (peca) peca.checked = b; },
    ativo(b) { if (peca && 'disabled' in peca) peca.disabled = !b; },
  };
  if (peca && tipo === 'botao') peca.addEventListener('click', e => { e.preventDefault(); console.log('pymorph:clique'); });
  if (peca && tipo === 'caixa') peca.addEventListener('input', () => console.log('pymorph:valor:' + JSON.stringify(peca.value)));
  if (peca && tipo === 'marcar') peca.addEventListener('change', () => console.log('pymorph:marcado:' + peca.checked));
  document.addEventListener('submit', e => e.preventDefault(), true);
  window.__pm.texto(%(texto)s);
})();
"""


@cache
def catalogo():
    try:
        texto = resources.files("pymorph").joinpath("catalogo/originais.json").read_text(encoding="utf-8")
    except FileNotFoundError:
        return {"itens": []}
    return json.loads(texto)


@cache
def _por_id():
    return {i["id"]: i for i in catalogo()["itens"]}


def item(id_):
    return _por_id().get(id_)


def originais(categoria):
    return [i for i in catalogo()["itens"] if i["categoria"] == categoria]


def _base():
    """Os arquivos do catálogo (o Tailwind) são lidos daqui; a página nasce nesta pasta."""
    return QUrl.fromLocalFile(str(resources.files("pymorph").joinpath("catalogo")) + "/")


def documento(item, texto="", fundo="transparent", ponte=True):
    """A página de um original: o HTML dele, centralizado, e a ponte com o PyMorph."""
    tipo = item["tipo"]
    return ("<!doctype html><html><head><meta charset='utf-8'>"
            + (f"<script src='{TAILWIND}'></script>" if item["tailwind"] else "")
            + f"<style>html,body{{margin:0;width:100%;height:100%;background:{fundo};overflow:hidden}}"
              "body{display:flex;align-items:center;justify-content:center}</style></head><body>"
            + item["html"]
            + ("<script>" + PONTE % {"peca": PECA[tipo], "tipo": json.dumps(tipo), "texto": json.dumps(texto)}
               + "</script>" if ponte else "")
            + "</body></html>")


class _SemRede(QWebEngineUrlRequestInterceptor):
    def interceptRequest(self, info):
        if info.requestUrl().scheme() not in ("file", "data", "qrc", "about"):
            info.block(True)


_perfil = None
_vistas = weakref.WeakSet()     # toda pele e vitrine viva


def encerrar():
    """Apaga as páginas antes da QApplication. Se a aplicação morre primeiro, o navegador desmonta
    páginas cujo desenho já foi desfeito e o processo cai na saída (SEGV visto no Qt 6.11/6.12)."""
    for vista in list(_vistas):
        if shiboken6.isValid(vista):
            shiboken6.delete(vista)
    _vistas.clear()


atexit.register(encerrar)       # registrado depois do PySide: roda antes da limpeza dele


def _registrar(vista):
    _vistas.add(vista)
    app = QApplication.instance()
    if app is not None and not getattr(app, "_pymorph_encerrar", False):
        app.aboutToQuit.connect(encerrar)
        app._pymorph_encerrar = True


def perfil():
    """O perfil padrão do Qt, com a rede bloqueada."""
    global _perfil
    if _perfil is None:
        _perfil = QWebEngineProfile.defaultProfile()
        _perfil._interceptor = _SemRede(_perfil)
        _perfil.setUrlRequestInterceptor(_perfil._interceptor)
    return _perfil


class _Pagina(QWebEnginePage):
    mensagem = Signal(str)

    def javaScriptConsoleMessage(self, nivel, mensagem, linha, origem):
        if mensagem.startswith("pymorph:"):
            self.mensagem.emit(mensagem[len("pymorph:"):])


class Pele(QWebEngineView):
    """O original de um elemento. `interativa=False` (no editor): não recebe mouse nem teclado — o
    palco é que arrasta e seleciona —, mas as animações em laço continuam rodando."""
    clicou = Signal()
    mudou_valor = Signal(str)
    mudou_marcado = Signal(bool)
    mediu = Signal(int, int)        # o tamanho que o original pede, já com a margem

    def __init__(self, item, texto="", parent=None, interativa=True):
        super().__init__(parent)
        self.item, self.texto, self.interativa = item, texto, interativa
        self._pronta, self._fila = False, []
        _registrar(self)
        # guardada aqui: sem a referência, o Python pode coletar a página e, com ela, a escuta do console
        self._pagina = _Pagina(perfil(), self)
        self._pagina.mensagem.connect(self._mensagem)
        self._pagina.setBackgroundColor(Qt.GlobalColor.transparent)
        self.setPage(self._pagina)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.NoContextMenu)
        if not interativa:
            self._sem_mouse(self)
        self.loadFinished.connect(self._carregou)
        self.setHtml(documento(item, texto), _base())

    @property
    def chave(self):
        return self.item["id"]

    def _sem_mouse(self, w):
        w.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        w.setFocusPolicy(Qt.FocusPolicy.NoFocus)

    def childEvent(self, evento):       # o navegador cria o widget que desenha depois de nascer
        super().childEvent(evento)
        if not self.interativa and evento.type() == QEvent.Type.ChildAdded and evento.child().isWidgetType():
            self._sem_mouse(evento.child())

    def _carregou(self, _):
        self._pronta = True
        for js in self._fila:
            self.page().runJavaScript(js)
        self._fila.clear()
        self.medir()

    def medir(self):
        def recebeu(r):
            if r:
                d = json.loads(r)
                self.mediu.emit(d["w"] + 2 * MARGEM, d["h"] + 2 * MARGEM)
        if self._pronta:
            self.page().runJavaScript("window.__pm && __pm.medir()", 0, recebeu)

    def _js(self, js):
        if self._pronta:
            self.page().runJavaScript(js)
        else:
            self._fila.append(js)

    def _mensagem(self, m):
        if m == "clique":
            self.clicou.emit()
        elif m.startswith("valor:"):
            self.mudou_valor.emit(json.loads(m[len("valor:"):]))
        elif m.startswith("marcado:"):
            self.mudou_marcado.emit(m.endswith("true"))

    def definir_texto(self, texto):
        self.texto = texto
        self._js(f"window.__pm && __pm.texto({json.dumps(texto)})")
        self.medir()

    def definir_valor(self, valor):
        self._js(f"window.__pm && __pm.valor({json.dumps(valor)})")

    def definir_marcado(self, marcado):
        self._js(f"window.__pm && __pm.marcado({json.dumps(bool(marcado))})")

    def ativar(self, ativo):
        self._js(f"window.__pm && __pm.ativo({json.dumps(bool(ativo))})")


def vitrine(itens, largura_celula, altura_celula, com_padrao=False):
    """Uma página com vários originais lado a lado, cada um isolado num iframe (os CSS do Galaxy
    usam seletores globais e brigariam entre si). Um clique na célula avisa 'escolha:<i>'."""
    celulas = []
    if com_padrao:
        celulas.append("<div class='c' onclick=\"console.log('pymorph:escolha:-1')\" title='Sem original'>"
                       "<span class='sem'>Sem original</span></div>")
    for i, it in enumerate(itens):
        escala = min(1.0, largura_celula / it["largura"], altura_celula / it["altura"])
        fundo = "#212121" if it.get("escuro") else "#ffffff"     # o fundo em que o original aparece
        doc = html.escape(documento(it, ponte=False, fundo=fundo), quote=True)
        titulo = html.escape(f"{it['categoria']} de {it['autor']} · Uiverse.io (MIT)")
        celulas.append(
            f"<div class='c' style='background:{fundo}' onclick=\"console.log('pymorph:escolha:{i}')\" "
            f"title='{titulo}'>"
            f"<div style='width:{it['largura'] * escala:.0f}px;height:{it['altura'] * escala:.0f}px;overflow:hidden'>"
            f"<iframe srcdoc=\"{doc}\" style='width:{it['largura']}px;height:{it['altura']}px;"
            f"transform:scale({escala:.3f});transform-origin:0 0'></iframe></div></div>")
    return ("<!doctype html><html><head><meta charset='utf-8'><style>"
            "html,body{margin:0;background:transparent;font:12px sans-serif;color:#59616b;overflow:hidden}"
            ".g{display:grid;grid-template-columns:1fr 1fr;gap:6px;padding:2px}"
            f".c{{height:{altura_celula + 12}px;background:#fff;border:1px solid #d5dae0;border-radius:6px;"
            "display:flex;align-items:center;justify-content:center;cursor:pointer;overflow:hidden}"
            ".c:hover{border-color:#1f5fbf;box-shadow:0 0 0 1px #1f5fbf}"
            "iframe{border:0;pointer-events:none;background:#fff}.sem{padding:4px}"
            "</style></head><body><div class='g'>" + "".join(celulas) + "</div></body></html>")


class Vitrine(QWebEngineView):
    escolheu = Signal(int)      # o índice na página; -1 é "sem original"

    def __init__(self, parent=None):
        super().__init__(parent)
        _registrar(self)
        self._pagina = _Pagina(perfil(), self)
        self._pagina.mensagem.connect(lambda m: m.startswith("escolha:") and self.escolheu.emit(int(m.split(":")[1])))
        self._pagina.setBackgroundColor(Qt.GlobalColor.transparent)
        self.setPage(self._pagina)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.NoContextMenu)

    def mostrar(self, itens, largura_celula, altura_celula, com_padrao=False):
        self.setHtml(vitrine(itens, largura_celula, altura_celula, com_padrao), _base())
