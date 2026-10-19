from pymorph import galeria
from pymorph.tela import Tela

BOTAO = {"id": "fulano/botao-1", "autor": "fulano", "url": "https://uiverse.io/fulano/botao-1", "tipo": "botao",
         "nota": 0.93, "largura": 120, "altura": 40, "texto": "Go",
         "visual": {"fundo": "qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #7c3aed, stop:1 #06b6d4)",
                    "cor": "#ffffff", "borda_largura": 0, "raio": 8, "espaco": "8px 16px",
                    "sombra": "0 4 12 #40000000", "destaque_fundo": "#5b21b6", "fonte": 11, "negrito": True}}
FORM = {"id": "ciclana/form-2", "autor": "ciclana", "url": "https://uiverse.io/ciclana/form-2",
        "categoria": "Formulário", "nota": 0.95, "largura": 300, "altura": 420, "elementos": [
            {"tipo": "caixa", "x": 0, "y": 0, "largura": 300, "altura": 420, "texto": "", "fundo": "#ffffff",
             "raio": 12, "sombra": "0 8 24 #33000000", "digitavel": False},
            {"tipo": "caixa", "x": 24, "y": 24, "largura": 200, "altura": 28, "texto": "[a preencher]",
             "fonte": 15, "negrito": True, "digitavel": False},
            {"tipo": "caixa", "x": 24, "y": 80, "largura": 252, "altura": 36, "texto": "[a preencher]",
             "borda_largura": 1, "borda_cor": "#c3c9d0", "raio": 6, "digitavel": True},
            {"tipo": "botao", "x": 24, "y": 140, "largura": 252, "altura": 40, "texto": "[a preencher]",
             "fundo": "#2563eb", "cor": "#ffffff", "digitavel": False}]}


def test_aplicar_estilo_troca_a_aparencia_e_guarda_o_credito():
    tela = Tela()
    botao = tela.adicionar("botao", texto="Somar")
    botao.cor = "#ff0000"
    galeria.aplicar_estilo(tela, botao, BOTAO)
    assert (botao.texto, botao.raio, botao.negrito, botao.destaque_fundo) == ("Somar", 8, True, "#5b21b6")
    assert botao.fundo.startswith("qlineargradient") and botao.cor == "#ffffff"
    assert tela.creditos == ["https://uiverse.io/fulano/botao-1"]
    ui = tela.para_ui()
    assert "QPushButton:hover { background: #5b21b6; }" in ui and "border: none;" in ui
    galeria.aplicar_estilo(tela, botao, None)                     # "Sem estilo"
    assert (botao.fundo, botao.raio, botao.sombra, botao.fonte) == ("", -1, "", 0)


def test_importar_layout_cabe_na_tela_e_a_caixa_vem_de_digitar(tmp_path):
    tela = Tela()                                                   # pequena: 480×360
    tela.adicionar("botao")
    criados = galeria.importar_layout(tela, FORM)
    assert tela.tamanho == "intermediaria"                          # 420 de altura não cabia em 360
    assert len(criados) == 4 and all(e.x >= 24 for e in criados)
    entrada = criados[2]
    assert tela.papel(entrada.id) == "entrada" and tela.classe(entrada) == "QLineEdit"
    tela.salvar(tmp_path)
    de_novo = Tela.carregar(tmp_path)
    assert de_novo.creditos == ["https://uiverse.io/ciclana/form-2"]
    assert de_novo.elemento(entrada.id).digitavel and de_novo.elemento(criados[0].id).sombra == "0 8 24 #33000000"


def test_o_catalogo_vem_no_pacote():
    cat = galeria.catalogo()
    assert len(galeria.estilos("botao")) > 100 and len(galeria.estilos("caixa")) > 20
    assert galeria.layouts("Formulário") and galeria.layouts("Card")
    assert all(i["nota"] >= 0.8 and i["url"].startswith("https://uiverse.io/") for i in cat["estilos"])
    textos = {c["texto"] for i in cat["layouts"] for c in i["elementos"]}
    assert textos <= {"", "[a preencher]", "[imagem a preencher]"}   # o desenho vem; o texto é seu


def test_a_galeria_do_painel_aplica_no_selecionado(app, config, tmp_path):
    from PySide6.QtWidgets import QToolButton
    from pymorph.editor import Editor, Galeria
    editor = Editor(tmp_path, config=config)
    editor._adicionar("botao")
    editor.painel.mostrar("botao")
    (vitrine,) = editor.painel.widget().findChildren(Galeria)
    vitrine.mudar_itens([BOTAO])
    botoes = [b for b in vitrine.findChildren(QToolButton) if not b.isHidden()]   # a página antiga sai depois
    botoes[1].click()                         # o 0 é "Sem estilo"
    assert editor.tela.elemento("botao").raio == 8
    assert "border-radius: 8px" in editor.palco.widgets["botao"].styleSheet()
    editor.painel.mostrar(None)
    vitrines = editor.painel.widget().findChildren(Galeria)
    vitrines[1].mudar_itens([FORM])
    [b for b in vitrines[1].findChildren(QToolButton) if not b.isHidden()][0].click()
    assert len(editor.tela.elementos) == 5 and editor.tamanho.currentData() == "intermediaria"
