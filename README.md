# PyMorph

**A interface gráfica nasce das suas funções.** Quem sabe escrever a função que soma não precisa saber
desenhar uma janela. Você escreve funções Python com tipos; o PyMorph lê, você desenha a tela e liga
cada botão a uma função. O seu código nunca é alterado.

```python
def somar(a: float, b: float) -> float:
    """Soma dois números."""
    return a + b
```

```
pymorph            ← na pasta do projeto: abre o editor
pymorph rodar      ← a tela como o usuário final vê
```

## Como funciona

1. **O leitor** acha as funções públicas de todos os `.py` da pasta pelo `ast`, **sem executar nada**:
   importar o arquivo rodaria o código solto dele. Cada tipo sugere um controle: `float` vira campo
   decimal (aceita vírgula), `int` campo inteiro, `str` campo de texto, `bool` caixa de marcar. Código
   solto que chama algo ao importar aparece como aviso.
2. **O editor** tem as funções e os controles à esquerda, o palco no meio e as propriedades à direita.
   - duplo clique numa função gera os campos, o botão e o resultado dela; campos com o mesmo parâmetro
     são reaproveitados (somar, multiplicar e dividir dividem `a`, `b` e o resultado);
   - arrastar move, a alça azul no canto muda o tamanho, a grade é de 8 px (Shift solta), as setas
     movem, Delete apaga;
   - num botão, "Ao clicar, chamar" escolhe a função e casa cada parâmetro com um campo e o retorno com
     um resultado; a bolinha azul marca botão ligado, a laranja, botão sem função;
   - a lista de funções se atualiza sozinha quando o `.py` é salvo;
   - o tamanho do desenho é Pequena (480×360), Intermediária (960×640) ou Tela cheia (1920×1080):
     conveniência de quem desenha, não limite de quem usa.
3. **Os arquivos** ficam ao lado do seu código, em `telas/`:
   - `principal.ui` — o desenho, no formato do Qt Designer (abre nele); leva só o que o PyMorph
     controla, e não as dezenas de propriedades padrão de cada widget;
   - `principal.ligacoes.json` — que função cada botão chama, de onde vêm as entradas, para onde vai a
     saída.
4. **A tela rodando** (`Executar ▶` no editor, ou `pymorph rodar`):
   - o desenho vem do `.ui` pelo `QUiLoader`; o seu arquivo só é importado na primeira chamada;
   - cada chamada roda numa thread: a janela não congela num cálculo longo;
   - erro da função vira aviso no lugar do resultado (o traceback fica no texto de ajuda); a janela
     continua aberta;
   - a janela abre no tamanho desenhado (Tela cheia abre maximizada) e, depois, no último tamanho que
     o usuário deixou;
   - redimensionar não escala nada: o desenho fica no centro e a sobra vira margem, como o VS Code
     faz com a área do editor; o mínimo é o tamanho do desenho;
   - Ctrl + / Ctrl − / Ctrl 0 é o zoom: escala tudo, 1,2× por passo (o mesmo passo do VS Code).

## Instalar

Precisa do Python 3.10+; o PySide6 (LGPL) vem junto. O comando `pymorph`, uma vez por máquina:

```bash
pipx install git+https://github.com/GF-Linux/pymorph.git
# sem pipx:
python3 -m pip install --user git+https://github.com/GF-Linux/pymorph.git
```

E na pasta do seu projeto:

```bash
cd meu-projeto
pymorph funcoes        # o que o leitor achou
pymorph                # o editor
```

Para atualizar: `pipx upgrade pymorph` (ou o mesmo `pip install --user --upgrade git+…`).

**Para mexer no PyMorph** (o exemplo da calculadora e os testes):

```bash
git clone https://github.com/GF-Linux/pymorph.git && cd pymorph
python3 -m venv .venv
.venv/bin/pip install -e ".[teste]"
.venv/bin/pymorph exemplos/calculadora
```

No Fedora, o PySide6 do sistema serve no lugar do que vem do PyPI: `sudo dnf install python3-pyside6` e
`python3 -m venv --system-site-packages .venv`.

## Comandos

```
pymorph [pasta]               abre o editor (padrão: a pasta atual)
pymorph rodar [pasta]         abre a tela como o usuário final vê
pymorph funcoes [pasta]       lista o que o leitor achou, sem executar nada
pymorph ... --tela NOME       outra tela que não a principal (telas/NOME.ui)
```

## Fora da 0.0.1

Decidido, ainda não construído: barras presas às bordas e laterais que encolhem até um mínimo ao
redimensionar; derivar os outros tamanhos do desenho-base com ajuste à mão por tamanho; moldura própria
(barra de título, logo, fechar e minimizar obrigatórios no modo padrão) e o modo "liberdade total";
tabela (DataFrame), gráfico, imagem; mais de uma tela e submenus; ler um PNG de referência (paleta,
posição das barras e tamanhos; texto e imagem ficam "a preencher"); empacotar o app.

Um `.ui` editado no Qt Designer abre no PyMorph, mas as propriedades que o PyMorph não controla se
perdem ao salvar por ele.

## Testes

```
.venv/bin/pytest
```

Rodam sem tela (`QT_QPA_PLATFORM=offscreen`): o leitor não executa o arquivo, o `.ui` abre no
`QUiLoader`, a calculadora calcula, o erro vira aviso, o tamanho é lembrado, o zoom escala, o editor
gera, arrasta, redimensiona e salva.
