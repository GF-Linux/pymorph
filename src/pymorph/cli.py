"""O comando pymorph, rodado na pasta do projeto.

    pymorph [pasta]                   abre o editor da tela (padrão: a pasta atual)
    pymorph rodar [pasta]             abre a tela como o usuário final vê
    pymorph funcoes [pasta]           lista as funções que o leitor achou, sem executar nada
    pymorph ... --tela NOME           outra tela que não a principal (telas/NOME.ui)
    pymorph --version
"""
import argparse
import sys
from pathlib import Path

from pymorph import __version__


def _funcoes(pasta):
    from pymorph.leitor import ler_pasta
    arquivos = ler_pasta(pasta)
    total = 0
    for a in arquivos:
        if not a.funcoes and not a.erro and not a.codigo_solto:
            continue
        print(a.caminho)
        if a.erro:
            print(f"  ✕ {a.erro}")
        if a.codigo_solto:
            print(f"  ⚠ código solto na linha {', '.join(map(str, a.codigo_solto))}: roda quando a tela rodar")
        for f in a.funcoes:
            controles = ", ".join(f"{p.nome} → {p.leitura}" for p in f.parametros)
            acao = "" if f.devolve else "    (ação: não devolve valor)"
            print(f"  {f.nome}{f.assinatura()}" + (f"    [{controles}]" if controles else "") + acao)
            total += 1
    if total == 0:
        print("nenhuma função pública encontrada (as que começam com _ ficam de fora)")
    return 0


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    comando = argv.pop(0) if argv and argv[0] in ("rodar", "funcoes") else "editar"
    parser = argparse.ArgumentParser(prog="pymorph", description="A interface gráfica nasce das suas funções.")
    parser.add_argument("pasta", nargs="?", default=".", help="a pasta do projeto (padrão: a atual)")
    parser.add_argument("--tela", default="principal", help="o nome da tela (padrão: principal)")
    parser.add_argument("--version", action="version", version=f"pymorph {__version__}")
    args = parser.parse_args(argv)
    pasta = Path(args.pasta).resolve()
    if not pasta.is_dir():
        parser.error(f"{pasta} não é uma pasta")
    if comando == "funcoes":
        return _funcoes(pasta)

    import pymorph.web  # noqa: F401  — o navegador dos originais precisa nascer antes da QApplication
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication(sys.argv[:1])
    app.setApplicationName("PyMorph")
    if comando == "rodar":
        from pymorph.executor import abrir
        from pymorph.tela import Tela
        if not Tela(nome=args.tela).caminhos(pasta)[0].exists():
            parser.error(f"não existe telas/{args.tela}.ui em {pasta}; crie a tela com  pymorph {args.pasta}")
        janela = abrir(pasta, args.tela)
        janela.mostrar()
    else:
        from pymorph.editor import Editor
        janela = Editor(pasta, args.tela)
        janela.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
