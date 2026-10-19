# Mudanças

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
