# ASCII Space Explorer

Protetor de tela espacial procedural executado diretamente no terminal. A animação acompanha um foguete em uma exploração contínua por estrelas, planetas, nebulosas, galáxias e buracos negros, com aproximações, sobrevoos, pousos e decolagens.

O estado da viagem é salvo automaticamente, permitindo continuar a exploração na próxima execução.

## Recursos

- Cenários ASCII gerados proceduralmente.
- Viagens reproduzíveis por meio de uma semente (`seed`).
- Planetas com diferentes biomas, terrenos e locais de pouso.
- Parallax para estrelas, objetos cósmicos e montanhas.
- Cores ANSI opcionais.
- Adaptação automática ao tamanho do terminal.
- Monitoramento de CPU e memória sem bibliotecas externas.
- Redução de detalhes sob pressão de memória.
- Eventos visuais associados ao uso crítico de recursos.
- Persistência automática da exploração em `status.json`.

## Requisitos

- Python 3.10 ou superior.
- Terminal com suporte a sequências ANSI para exibição colorida.

O projeto utiliza somente a biblioteca padrão do Python.

## Execução

Clone o repositório e execute o arquivo principal:

```bash
git clone <URL_DO_REPOSITORIO>
cd acii_animation
python main.py
```

Pressione `Ctrl+C` para encerrar. O cursor é restaurado e o progresso é salvo antes da saída.

O terminal deve ter pelo menos 33 colunas por 12 linhas. Para uma experiência melhor, use uma janela maior e fonte monoespaçada.

## Opções

```text
--seed N         inicia uma viagem reproduzível com a semente N
--no-color       desativa as cores ANSI
--fps N          define a taxa de quadros por segundo (padrão: 12)
--reset-status   ignora o progresso salvo e inicia uma nova exploração
```

Exemplos:

```bash
python main.py --seed 42
python main.py --no-color --fps 20
python main.py --reset-status
```

Quando `--seed` ou `--reset-status` é usado, uma nova exploração substitui o estado salvo durante a execução.

## Configuração

Os parâmetros da animação ficam em `config.py`. Nesse arquivo podem ser ajustados, entre outros:

- FPS e uso de cores;
- dimensões mínimas do terminal;
- densidade de estrelas;
- duração de cada etapa da viagem;
- frequência de encontros e pousos;
- objetos e cenários habilitados;
- intervalos de salvamento e leitura das métricas do sistema;
- limites de pressão de memória e carga crítica.

## Testes

Execute a suíte com o módulo `unittest`:

```bash
python -m unittest discover -s tests -v
```

Os testes cobrem geração procedural, renderização, transições de estado, redimensionamento, persistência e métricas do sistema.

## Estrutura

```text
main.py          entrada da aplicação e loop de animação
explorer.py      máquina de estados e composição das cenas
procedural.py    geração de estrelas, planetas, terrenos e objetos cósmicos
renderer.py      buffer ASCII, clipping e composição de cores ANSI
rocket.py        sprites e desenho do foguete
metrics.py       leitura de CPU e memória
persistence.py   gravação e restauração do estado da exploração
config.py        parâmetros da aplicação
status.json      estado persistido da viagem
tests/           testes automatizados
```

## Licença

Distribuído sob a licença MIT. Consulte [LICENSE](LICENSE).
