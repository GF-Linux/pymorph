# Mudanças

## 0.0.3

- **uma caixa só.** Campo decimal, campo inteiro, campo de texto, rótulo e resultado viraram a
  **Caixa**. Os controles agora são Caixa, Botão e Caixa de marcar. O papel da caixa vem das ligações:
  texto fixo (título), entrada, saída, ou entrada e saída (o visor). Letra e negrito no painel.
- **o tipo é do parâmetro, não da caixa:** `float`, `int`, `str` e `bool` dizem como o que foi digitado
  chega à função; sem tipo é automático (número se parece número, senão texto). `def f(a, b): return a + b`
  com 2 e 3 dá 5, e não mais "23".
- **ação:** função sem `return valor` (ou `-> None`) não ganha caixa de resultado; o erro dela vira
  janela de aviso. `pymorph funcoes` marca as ações.
- telas da 0.0.1/0.0.2 abrem: os tipos antigos viram caixa.

## 0.0.2

- **corrigido:** escolher a função na caixa "Ao clicar, chamar" derrubava o editor (falha de
  segmentação). O painel se refazia no meio do sinal da própria caixa e o Qt apagava a caixa ali
  mesmo; agora o corpo antigo é apagado depois. O teste passa pela caixa, como a pessoa faz.

## 0.0.1

O primeiro protótipo funcional: do `.py` com funções tipadas à janela que o usuário final usa.

- **o leitor** acha as funções públicas pelo `ast`, sem executar o arquivo; tipo vira controle
  (`float` decimal, `int` inteiro, `str` texto, `bool` marcar); código solto vira aviso; erro de
  sintaxe aparece no lugar das funções.
- **o editor**: funções e controles à esquerda, palco no meio, propriedades à direita. Duplo clique numa
  função gera campos, botão e resultado, reaproveitando campos do mesmo parâmetro. Arrastar, alça de
  tamanho, grade de 8 px, setas, Delete. Ligação botão → função com entradas e saída escolhidas na mão.
  3 tamanhos de desenho. A lista de funções acompanha o arquivo salvo.
- **os arquivos** em `telas/`: o `.ui` no formato do Qt Designer, só com o que o PyMorph controla, e o
  `.ligacoes.json`.
- **a tela rodando**: `QUiLoader`, chamada em thread, erro vira aviso, abre no tamanho desenhado e depois
  no último do usuário, redimensionar não escala (o desenho centraliza), zoom Ctrl ± de 1,2×.
- o comando `pymorph` (editor), `pymorph rodar` e `pymorph funcoes`.
