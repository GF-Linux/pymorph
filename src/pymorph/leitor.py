"""O leitor: acha as funções dos arquivos .py de uma pasta sem executar nada.

Usa só o ast, a árvore do código. Importar o arquivo rodaria o código solto dele: um script de
análise inteiro dispararia só porque o editor abriu. O arquivo só é importado quando a tela roda.
"""
import ast
from dataclasses import dataclass, field
from pathlib import Path

# pastas que não são código do projeto
IGNORAR = {".venv", "venv", "env", ".git", "__pycache__", "node_modules", "telas", "build", "dist",
           ".pytest_cache", ".ruff_cache"}

# o controle que cada tipo sugere; tipo sem anotação ou desconhecido vira campo de texto
CONTROLE_POR_TIPO = {"float": "decimal", "int": "inteiro", "str": "texto", "bool": "marcar"}


@dataclass
class Parametro:
    nome: str
    tipo: str | None        # a anotação como foi escrita: "float", "list[int]"…
    padrao: str | None      # o valor padrão como foi escrito, ou None

    @property
    def controle(self):
        return CONTROLE_POR_TIPO.get(self.tipo, "texto")


@dataclass
class Funcao:
    nome: str
    arquivo: str            # caminho relativo à pasta do projeto, com /
    linha: int
    parametros: list[Parametro]
    retorno: str | None
    doc: str | None

    @property
    def chave(self):
        """Como a ligação guarda a função: 'calculadora.py:somar'."""
        return f"{self.arquivo}:{self.nome}"

    def assinatura(self):
        partes = []
        for p in self.parametros:
            texto = p.nome + (f": {p.tipo}" if p.tipo else "")
            if p.padrao is not None:
                texto += f" = {p.padrao}"
            partes.append(texto)
        seta = f" -> {self.retorno}" if self.retorno else ""
        return f"({', '.join(partes)}){seta}"


@dataclass
class Arquivo:
    caminho: str                                        # relativo à pasta, com /
    funcoes: list[Funcao] = field(default_factory=list)
    codigo_solto: list[int] = field(default_factory=list)  # linhas que chamam algo ao importar
    erro: str | None = None                             # erro de sintaxe, se houver


def _texto(no):
    return ast.unparse(no) if no is not None else None


def _parametros(args):
    """Os parâmetros que a tela pode preencher: os posicionais e os nomeados, sem self, *args e **kw."""
    posicionais = args.posonlyargs + args.args
    padroes = [None] * (len(posicionais) - len(args.defaults)) + list(args.defaults)
    saida = [Parametro(a.arg, _texto(a.annotation), _texto(d)) for a, d in zip(posicionais, padroes)]
    for a, d in zip(args.kwonlyargs, args.kw_defaults):
        saida.append(Parametro(a.arg, _texto(a.annotation), _texto(d)))
    return saida


def _e_guarda_main(no):
    """if __name__ == "__main__": — o bloco que não roda ao importar."""
    return (isinstance(no, ast.If) and isinstance(no.test, ast.Compare)
            and isinstance(no.test.left, ast.Name) and no.test.left.id == "__name__")


def _chama_algo(no):
    return any(isinstance(n, ast.Call) for n in ast.walk(no))


def ler_arquivo(caminho, pasta):
    rel = Path(caminho).relative_to(pasta).as_posix()
    arquivo = Arquivo(rel)
    try:
        arvore = ast.parse(Path(caminho).read_text(encoding="utf-8"), filename=rel)
    except (SyntaxError, UnicodeDecodeError) as e:
        arquivo.erro = f"{type(e).__name__}: {e}"
        return arquivo
    for no in arvore.body:
        if isinstance(no, ast.FunctionDef):
            if no.name.startswith("_"):
                continue
            arquivo.funcoes.append(Funcao(no.name, rel, no.lineno, _parametros(no.args),
                                          _texto(no.returns), ast.get_docstring(no)))
        elif isinstance(no, (ast.Import, ast.ImportFrom, ast.ClassDef, ast.AsyncFunctionDef)):
            continue
        elif _e_guarda_main(no):
            continue
        elif _chama_algo(no):
            arquivo.codigo_solto.append(no.lineno)
    return arquivo


def ler_pasta(pasta):
    """Todos os .py da pasta e das subpastas do projeto, em ordem de nome."""
    pasta = Path(pasta).resolve()
    arquivos = []
    for caminho in sorted(pasta.rglob("*.py")):
        if any(parte in IGNORAR for parte in caminho.relative_to(pasta).parts[:-1]):
            continue
        arquivos.append(ler_arquivo(caminho, pasta))
    return arquivos


def funcoes_por_chave(arquivos):
    return {f.chave: f for a in arquivos for f in a.funcoes}
