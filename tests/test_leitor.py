from pymorph.leitor import ler_pasta


def test_le_as_funcoes_com_tipos_e_docstring(calculadora):
    (arquivo,) = ler_pasta(calculadora)
    assert arquivo.caminho == "calculadora.py"
    assert [f.nome for f in arquivo.funcoes] == ["somar", "multiplicar", "dividir"]
    somar = arquivo.funcoes[0]
    assert somar.assinatura() == "(a: float, b: float) -> float"
    assert somar.doc == "Soma dois números."
    assert somar.chave == "calculadora.py:somar"
    assert [p.controle for p in somar.parametros] == ["caixa", "caixa"]
    assert [p.leitura for p in somar.parametros] == ["número", "número"]


def test_nao_executa_o_arquivo(tmp_path):
    marca = tmp_path / "rodou.txt"
    (tmp_path / "script.py").write_text(
        "from pathlib import Path\n"
        f"Path({str(marca)!r}).write_text('rodou')\n"
        "def media(xs: list, casas: int = 2) -> float:\n"
        "    return round(sum(xs) / len(xs), casas)\n"
        "if __name__ == '__main__':\n"
        "    print(media([1, 2]))\n")
    (arquivo,) = ler_pasta(tmp_path)
    assert not marca.exists()
    assert arquivo.codigo_solto == [2]          # o if __name__ não conta
    (media,) = arquivo.funcoes
    assert media.assinatura() == "(xs: list, casas: int = 2) -> float"
    assert [p.leitura for p in media.parametros] == ["automático", "número inteiro"]


def test_ignora_privadas_venv_e_telas_e_relata_erro_de_sintaxe(tmp_path):
    (tmp_path / "a.py").write_text("def _interna(): pass\ndef publica(x: bool): pass\n")
    (tmp_path / "quebrado.py").write_text("def f(:\n")
    for pasta in (".venv", "telas", "sub"):
        (tmp_path / pasta).mkdir()
        (tmp_path / pasta / "m.py").write_text("def g(): pass\n")
    arquivos = {a.caminho: a for a in ler_pasta(tmp_path)}
    assert set(arquivos) == {"a.py", "quebrado.py", "sub/m.py"}
    assert [f.nome for f in arquivos["a.py"].funcoes] == ["publica"]
    assert arquivos["a.py"].funcoes[0].parametros[0].controle == "marcar"
    assert arquivos["quebrado.py"].erro.startswith("SyntaxError")
    assert arquivos["sub/m.py"].funcoes[0].chave == "sub/m.py:g"


def test_sabe_se_a_funcao_devolve_valor_ou_e_uma_acao(tmp_path):
    (tmp_path / "f.py").write_text(
        "import os\n"
        "def somar(a, b):\n    return a + b\n"                      # sem tipo, mas devolve
        "def abrir_pasta(caminho):\n    os.system(caminho)\n"         # ação
        "def gravar(x) -> None:\n    return print(x)\n"               # a anotação manda
        "def so_volta(x):\n    if x:\n        return\n    return None\n"
        "def fabrica():\n    def dentro():\n        return 1\n    dentro()\n"  # o return é da de dentro
        "def media(xs) -> float:\n    ...\n")
    (arquivo,) = ler_pasta(tmp_path)
    assert {f.nome: f.devolve for f in arquivo.funcoes} == {
        "somar": True, "abrir_pasta": False, "gravar": False, "so_volta": False, "fabrica": False, "media": True}
