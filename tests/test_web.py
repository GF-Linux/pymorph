"""Os originais do Galaxy no navegador embutido: o clique e o que se digita lá dentro chegam à função."""
import time

from PySide6.QtCore import QThreadPool
from PySide6.QtWidgets import QApplication, QLabel, QLineEdit

from pymorph import galeria, web
from pymorph.executor import abrir
from pymorph.leitor import funcoes_por_chave, ler_pasta
from pymorph.tela import Tela, gerar_da_funcao


def esperar(condicao, segundos=15):
    fim = time.time() + segundos
    while time.time() < fim:
        QApplication.processEvents()
        QThreadPool.globalInstance().waitForDone(20)
        if condicao():
            return True
    return False


def _primeiro(categoria, trecho):
    return next(i for i in web.originais(categoria) if trecho in i["html"] and not i["tailwind"])


def test_o_catalogo_dos_originais_vem_no_pacote():
    assert {c: len(web.originais(c)) > 100 for c in ("Botão", "Animação", "Toggle", "Caixa", "Caixa de marcar")} \
        == dict.fromkeys(("Botão", "Animação", "Toggle", "Caixa", "Caixa de marcar"), True)
    item = web.originais("Botão")[0]
    assert item["url"].startswith("https://uiverse.io/") and item["largura"] <= 480 + 24
    assert "<script" not in item["html"]


def test_clicar_e_digitar_no_original_chama_a_funcao(calculadora, config, app):
    funcoes = funcoes_por_chave(ler_pasta(calculadora))
    tela = Tela()
    botao = gerar_da_funcao(tela, funcoes["calculadora.py:somar"])
    galeria.aplicar_original(tela, botao, _primeiro("Botão", "<button"))
    galeria.aplicar_original(tela, tela.elemento("campo_a"), _primeiro("Caixa", "<input"))
    tela.salvar(calculadora)
    janela = abrir(calculadora, config=config)
    janela.show()
    pele_a, pele_botao = janela._peles["campo_a"], janela._peles[botao.id]
    assert not janela.palco.findChild(QLineEdit, "campo_a").isVisible()     # o controle fica por baixo
    assert esperar(lambda: pele_a._pronta and pele_botao._pronta)
    pele_a.page().runJavaScript(f"(() => {{ const p = {web.PECA['caixa']}; p.value = '2';"
                                f" p.dispatchEvent(new Event('input')); }})()")
    assert esperar(lambda: janela.palco.findChild(QLineEdit, "campo_a").text() == "2")
    janela.palco.findChild(QLineEdit, "campo_b").setText("3")
    pele_botao.page().runJavaScript(f"{web.PECA['botao']}.click()")
    assert esperar(lambda: janela.palco.findChild(QLabel, "resultado").text() == "5")


def test_o_editor_mostra_o_original_e_reaproveita_a_pele(calculadora, config, app):
    from pymorph.editor import Editor, GaleriaOriginais
    editor = Editor(calculadora, config=config)
    editor._adicionar("botao")
    editor.painel.mostrar("botao")
    (vitrine,) = editor.painel.widget().findChildren(GaleriaOriginais)
    item = vitrine.itens[0]
    vitrine._escolheu(0)
    e = editor.tela.elemento("botao")
    assert e.original == item["id"] and (e.largura, e.altura) == (item["largura"], item["altura"])
    pele = editor.palco.widgets["botao"]
    assert isinstance(pele, web.Pele)
    e.texto = "Somar"
    editor.palco.reconstruir()
    assert editor.palco.widgets["botao"] is pele and pele.texto == "Somar"   # sem recarregar
    editor.salvar()
    assert Tela.carregar(calculadora).elemento("botao").original == item["id"]
    assert item["url"] in Tela.carregar(calculadora).creditos


def _avaliar(pele, js):
    r = []
    pele.page().runJavaScript(js, 0, r.append)
    assert esperar(lambda: r, 5)
    return r[0]


def test_o_texto_de_quem_desenha_entra_no_original(app):
    casos = (   # (original, texto, o que conferir lá dentro, o esperado)
        ("3bdel3ziz-T/brown-earwig-37", "Somar",            # texto no ::after visível (o ::before é do hover)
         "getComputedStyle(document.querySelector('.button'), '::after').content", '"Somar"'),
        ("AbanoubMagdy1/afraid-yak-99", "Nome",             # rótulo letra a letra, com o atraso renumerado
         "[...document.querySelectorAll('.label-char')].map(c => c.textContent + c.style.getPropertyValue('--index')).join(',')",
         "N0,o1,m2,e3"),
        ("AKAspidey01/brown-quail-36", "Dividir",           # ícone: fica o ícone
         "document.querySelector('button').innerText.trim()", "×"),
    )
    for id_, texto, js, esperado in casos:
        pele = web.Pele(web.item(id_), texto)
        pele.resize(300, 120)
        pele.show()
        assert esperar(lambda: pele._pronta)
        assert _avaliar(pele, js).replace(" ", "") == esperado, id_


def test_no_editor_o_elemento_cresce_para_o_texto_caber(calculadora, config, app):
    from pymorph.editor import Editor
    editor = Editor(calculadora, config=config)
    editor.show()
    editor._adicionar("botao")
    e = editor.tela.elemento("botao")
    galeria.aplicar_original(editor.tela, e, web.item("0x-Sarthak/hungry-penguin-30"))
    largura = e.largura
    e.texto = "Calcular a média ponderada"
    editor.palco.reconstruir()
    assert esperar(lambda: e.largura > largura, 8)
