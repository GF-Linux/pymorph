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
   importar o arquivo rodaria o código solto dele. O tipo do parâmetro diz como o que foi digitado
   chega à função: `float` como número (aceita vírgula), `int` como inteiro, `str` como texto, `bool`
   vira caixa de marcar; **sem tipo, é automático**: o que parece número vira número, o resto continua
   texto (2 e 3 somam 5; "ab" e "cd" juntam "abcd"). Função sem `return valor` (ou com `-> None`) é uma
   **ação**: abre, grava, move, e não tem resultado a mostrar. Código solto que chama algo ao importar
   aparece como aviso.
2. **O editor** tem as funções e os controles à esquerda, o palco no meio e as propriedades à direita.
   - são três controles: **Caixa**, **Botão** e **Caixa de marcar**. A caixa não tem tipo, e o papel
     dela vem das ligações dos botões:

     | a caixa é… | quando | aparece como |
     |---|---|---|
     | texto fixo (um título) | nenhum botão usa | texto |
     | entrada | um botão lê dela | campo para digitar |
     | saída | um botão manda o resultado para ela | o resultado, num quadro |
     | entrada e saída | as duas coisas (o visor de uma calculadora) | campo, e o resultado aparece nele |

   - todo elemento tem **fonte**, letra (tamanho), negrito, **cor do texto** e **fundo**. A lista de
     fontes vem do sistema (só as que escrevem português, uma vez cada, cada nome na própria letra),
     com as genéricas primeiro (sem serifa, com serifa, monoespaçada, manuscrita), que o sistema de
     quem usa resolve para a dele. Quer uma letra de quadrinho? A Comic Neue é livre e está no
     Fedora: `sudo dnf install comic-neue-fonts`, e ela aparece na lista;
   - duplo clique numa função gera um título e uma caixa por parâmetro, o botão e, se ela devolve um
     valor, a caixa do resultado; numa ação, só o botão. Caixas do mesmo parâmetro são reaproveitadas
     (somar, multiplicar e dividir dividem `a`, `b` e o resultado);
   - arrastar move, a alça azul no canto muda o tamanho, a grade é de 8 px (Shift solta), as setas
     movem, Delete apaga;
   - num botão, "Ao clicar, chamar" escolhe a função e casa cada parâmetro com uma caixa e o retorno
     com outra; a bolinha azul marca botão ligado, a laranja, botão sem função;
   - a lista de funções se atualiza sozinha quando o `.py` é salvo;
   - o tamanho do desenho é Pequena (480×360), Intermediária (960×640) ou Tela cheia (1920×1080):
     conveniência de quem desenha, não limite de quem usa.
3. **Estilos e layouts prontos**, do [Galaxy](https://github.com/uiverse-io/galaxy) da Uiverse.io (MIT):
   - **estilos** (474 de botão, 66 de caixa): no painel de um botão ou caixa, um clique aplica ao
     elemento; com nada selecionado, aplica a todos do tipo. O estilo vira valores do painel (fundo e
     gradiente, cor, borda, cantos, sombra, letra, cor com o mouse por cima ou com o foco), ajustáveis
     à mão; a letra diminui se o texto não couber no tamanho que você deu;
   - **layouts** (Formulários e Cards): com nada selecionado, um clique põe o layout num espaço livre
     da tela (e aumenta o tamanho do desenho se não couber). O desenho vem; **todo texto vem
     "[a preencher]"**, e as caixas de digitar já vêm de digitar;
   - o crédito de cada autor fica salvo com a tela (`creditos` no `.ligacoes.json`), e a licença do
     Galaxy vai junto com o catálogo (`catalogo/LICENSE-galaxy.txt`);
   - por que nem todos: o Qt desenha com uma parte do CSS. Nos 3.802 itens do Galaxy, 64% usam
     `transform`, 48% sombra, 39% `::before/::after`, 36% animação e 32% ícone SVG. O catálogo é
     gerado por `ferramentas/catalogo_galaxy.py`: abre cada item num navegador embutido, lê o estilo
     calculado, traduz, desenha com o próprio PyMorph e compara as duas imagens. Só entra o que fica
     parecido (estilo ≥ 80%, layout ≥ 88%) e com texto legível (contraste ≥ 3). A galeria mostra o
     desenho do PyMorph: o que você vê é o que entra na tela.
4. **Originais com animação**: 2.355 componentes do Galaxy rodando **como foram escritos**, num
   navegador embutido (QtWebEngine): 1.142 botões, 195 caixas, 159 caixas de marcar, 223 toggles e
   636 animações (loaders). Animação, `::before`, rotação, o mouse por cima: tudo como no original.
   - num botão, caixa ou caixa de marcar, "Originais (com animação)" mostra uma vitrine viva; um
     clique veste o elemento com o original. Sem nada selecionado, um clique põe um elemento novo;
   - o elemento continua o mesmo: ligado à função, com o seu texto. O texto entra onde o original
     põe o dele (no HTML, no `content` do CSS, no rótulo animado letra a letra); botão que é só
     ícone fica com o ícone; se o seu texto pedir mais espaço, o elemento cresce no editor;
   - por baixo da pele, o controle do Qt continua na tela, escondido: é dele que a função lê. Por
     isso o `.ui` continua abrindo no Qt Designer;
   - todos os originais dividem um processo de navegador e a rede fica bloqueada. Medido: o
     primeiro original custa ~205 MB de memória; cada outro, ~2,5 MB;
   - o catálogo é gerado por `ferramentas/originais_galaxy.py` (o tamanho real em 4 instantes da
     animação; o fundo, claro ou escuro, em que o original aparece).
5. **Os arquivos** ficam ao lado do seu código, em `telas/`:
   - `principal.ui` — o desenho, no formato do Qt Designer (abre nele); leva só o que o PyMorph
     controla, e não as dezenas de propriedades padrão de cada widget;
   - `principal.ligacoes.json` — que função cada botão chama, de onde vêm as entradas, para onde vai a
     saída.
6. **A tela rodando** (`Executar ▶` no editor, ou `pymorph rodar`):
   - o desenho vem do `.ui` pelo `QUiLoader`; o seu arquivo só é importado na primeira chamada;
   - cada chamada roda numa thread: a janela não congela num cálculo longo;
   - erro da função vira aviso no lugar do resultado (o traceback fica no texto de ajuda); numa ação,
     ou quando a saída é a própria caixa de digitar, vira uma janela de aviso; a janela continua aberta;
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
