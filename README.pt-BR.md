<div align="center">

# God of War — PS2 Static Recompilation

[English](README.md) · [Español](README.es.md) · **Português (Brasil)**

**Port nativo para PC de *God of War* (PS2, NTSC-U `SCUS-97399`) feito por recompilação estática de código MIPS R5900 para C++.**

![Plataforma](https://img.shields.io/badge/plataforma-Linux%20%7C%20Windows%20x64-0078D6?logo=linux&logoColor=white)
![Linguagem](https://img.shields.io/badge/C%2B%2B-20-00599C?logo=cplusplus&logoColor=white)
![Build](https://img.shields.io/badge/build-CMake%20%2B%20Ninja-064F8C?logo=cmake&logoColor=white)
![Baseado em](https://img.shields.io/badge/baseado%20em-PS2Recomp-8A2BE2)
![Status](https://img.shields.io/badge/status-experimental-orange)
[![Testes](https://github.com/KIexster/god-of-war-recomp/actions/workflows/pruebas.yml/badge.svg)](https://github.com/KIexster/god-of-war-recomp/actions/workflows/pruebas.yml)

</div>

---

> [!IMPORTANT]
> Este repositório **não contém nenhum arquivo do jogo** (ISO, executável, módulos IRX ou dados `.PAK`),
> nem o código C++ gerado a partir deles. Você precisa da **sua própria cópia legal** de God of War para PS2.

## Sumário

- [Propósito e objetivos](#propósito-e-objetivos)
- [Mapa de status](#mapa-de-status)
- [O que é](#o-que-é)
- [Status atual](#status-atual)
- [Linux (port nativo)](#linux-port-nativo)
- [Estrutura do repositório](#estrutura-do-repositório)
- [Requisitos](#requisitos)
- [Compilar e executar](#compilar-e-executar)
- [Como funciona](#como-funciona)
- [Documentação](#documentação)
- [Créditos e licença](#créditos-e-licença)

## Propósito e objetivos

Um **port nativo e jogável de *God of War* (2005) para Linux** por recompilação estática, sobre o
[PS2Recomp](https://github.com/ran-j/PS2Recomp). Marcos, em ordem:

1. **60 FPS estáveis** na partida.
2. Renderização em **1080p** com upscaling.

Estado atual, com honestidade: o jogo inicia a partir da sua própria ISO, toca a intro, chega à partida e salvar
funciona, mas a partida roda a apenas **~20-30 FPS** (RTX 5050), longe de 60. Problemas conhecidos: algumas falhas
visuais em orbes e partículas, um travamento após a cutscene da intro, e os vídeos do jogo ainda precisam de uma
solução provisória (**Skip movies** no lançador / `GOW_SKIP_FMV=1`; a intro já toca, os demais vídeos e seu áudio
não foram verificados).

Este repositório é um fork de [KIexster/god-of-war-recomp](https://github.com/KIexster/god-of-war-recomp). O
trabalho de Linux fica na branch `linux-native-port`; correções úteis para todos (por exemplo a dos callbacks do
fluxo MPEG, PR #92 no upstream) são enviadas ao upstream como PRs pequenos e separados.

## Mapa de status

**Linux (este fork)**

<a href="docs/estado/detalle.pt-BR.md"><img src="docs/estado/mapa.linux.pt-BR.svg" alt="Mapa de status do port: funções das bibliotecas do SDK da Sony e componentes do hardware do PS2, coloridos por status - Linux" width="100%"></a>

**Windows (upstream, não mantido aqui)**

<a href="docs/estado/detalle.pt-BR.md"><img src="docs/estado/mapa.windows.pt-BR.svg" alt="Mapa de status do port: funções das bibliotecas do SDK da Sony e componentes do hardware do PS2, coloridos por status - Windows" width="100%"></a>

O mapa do Linux é o mantido neste fork. Parte da mesma base do mapa do upstream (Windows) e só difere onde há evidência própria do Linux (GS Vulkan, lançador, compilação nativa, velocidade, travamento após a cutscene da intro).

Detalhamento por biblioteca e por componente: [`docs/estado/detalle.pt-BR.md`](docs/estado/detalle.pt-BR.md). É regenerado a partir de `docs/estado/datos.toml` por `tools/estado/generar.py` (e automaticamente ao subir para `main`).

## O que é

Em vez de emular o PlayStation 2 instrução por instrução, este projeto **traduz o executável original do
jogo (`SCUS_973.99`) para C++** com o [PS2Recomp](https://github.com/ran-j/PS2Recomp) e o compila como um
programa nativo (Linux ou Windows), ligado a um runtime que reimplementa o hardware e o sistema operacional do PS2
(kernel do EE, GS, DMA, CD/DVD…). O processador de E/S (IOP) executa os **módulos IRX originais** do jogo
(driver de som, streamer de dados…) no interpretador R3000A do PS2Recomp.

Este repositório contém tudo o que é específico de God of War:

| Componente | Descrição |
|---|---|
| **Mapa de funções** | 6.414 funções identificadas no ELF (`config/funcmap.csv`) |
| **Configuração do recompilador** | Stubs, pontos de entrada (incluindo métodos virtuais alcançados só por vtable) e patches de instruções (`config/recomp.template.toml`) |
| **Overrides do jogo** | Substituições e diagnósticos de funções do jogo (`src/gow_overrides.cpp`) |
| **Patch do runtime** | Correções no emulador do IOP e no runtime do EE do PS2Recomp necessárias para este jogo (`patches/`) |
| **Scripts de compilação** | Pipeline completo e reproduzível no Windows (`scripts/`) |
| **Ferramentas** | Extrator da camada 1 de DVD-9 (`tools/`) |

## Status atual

Estado e instruções do Linux: [Linux (port nativo)](#linux-port-nativo).


Build nativo para Windows (renderizador OpenGL) em um Ryzen 7 5800XT com uma RX 5700 XT:

<p align="center">
  <img src="docs/capturas/menu.jpg" alt="Menu principal" width="49%">
  <img src="docs/capturas/partida.jpg" alt="Jogo" width="49%">
</p>

| Marco | Status |
|---|:---:|
| Extração das duas camadas do DVD-9 | ✅ |
| Recompilação do `SCUS_973.99` para C++ (6.418 arquivos) | ✅ |
| Compilação do executável nativo (MSVC, x64) | ✅ |
| Boot: inicialização de raylib/OpenGL, heap e threads | ✅ |
| Módulos IRX originais do jogo no emulador do IOP (`989snd`, `smpd`, `libsd`…) | ✅ |
| Streaming de dados a partir da ISO original (`smpd` → `R_PERM.WAD`, configuração do jogo) | ✅ |
| Loop principal do jogo (`sys::GameLoop`) | ✅ |
| Saída de vídeo: tela legal e logo do título | ✅ |
| Barco, Kratos, inimigos e HUD com formas corretas; faltam outras verificações de renderização | 🔧 em andamento |
| Controle/teclado por HLE de libpad2; menu e seleção de dificuldade | ✅ |
| Partida alcançada; docas de Atenas a ~12 fps por padrão e ~25 fps com as threads opcionais de VU1/GS (meta: 30) | 🔧 em andamento |
| Vídeo FMV: intro decodificada e exibida sem ser pulada; faltam outros vídeos | 🔧 em andamento |
| Áudio: bancos e som contínuo emulado verificados; saída com cortes na velocidade atual | 🔧 em andamento |
| Memory card: listar, carregar, salvar e recarregar verificados em uma cópia PCSX2; falta formatação | 🔧 em andamento |

O jogo inicializa, carrega seus dados a partir da ISO e chega ao menu e à partida com teclado ou controle.
Após corrigir as cadeias DMA do scratchpad, as capturas mostram o barco, Kratos, inimigos e HUD com formas
corretas. A intro FMV também é decodificada sem `GOW_SKIP_FMV`. Carregar, salvar e recarregar uma partida
foram verificados em uma cópia de cartão PCSX2 de 8 MB com ECC; faltam formatação e reabertura no PCSX2.
O port continua experimental. Nas docas de Atenas ele roda a ~12 fps com a configuração padrão e a ~25 fps
com as threads opcionais de VU1 e do front-end do GS e o FINISH assíncrono (`PS2X_VU1_HILO=1`,
`PS2X_GS_FRENTE=1`, `GOW_GS_FINISH_ASINCRONO=1`), que ainda podem travar de vez em quando; o principal
gargalo é o microcódigo de VU1 compilado. O áudio tem cortes e faltam verificações das diferenças CPU/OpenGL
e da cobertura gráfica. Veja [desempenho](docs/RENDIMIENTO.md), [renderização](docs/COMPARACION_PCSX2.md),
[FMV e áudio](docs/FMV_Y_AUDIO.md), [memory card](docs/MEMORY_CARD.md) e
[`docs/ESTADO.md`](docs/ESTADO.md) para as verificações e seus limites (em espanhol).

## Linux (port nativo)

O port para Linux é nativo (sem Wine). O Windows é mantido compatível na medida do possível.

- **Vulkan é obrigatório.** O GS (gráficos) é rasterizado por um backend Vulkan compute cuja saída é idêntica byte a
  byte à do renderer de referência em CPU ([`docs/VULKAN.md`](docs/VULKAN.md)); é o padrão no Linux, com o renderer
  CPU como reserva.
- **Microcódigo VU1 compilado.** Os programas da VU1 são compilados para C++ no build, a partir de uma **captura
  local** do microcódigo do próprio jogo (nunca vai para o repositório); sem ela usa-se o interpretador, mais lento.
- **Lançador** (`tools/linux/gow_launcher.py`): localiza sua ISO (`GOW_ISO`, a lembrada, ou uma busca em `~/Games` e
  `~/Downloads`), valida, **extrai automaticamente o ELF e os módulos IRX** para `~/.cache/gow-one-recomp/` e abre
  uma janela de ajustes (tela cheia, filtro de escala, GPU, controle, mudo, **Skip movies**…). Detalhes:
  [`docs/LINUX_LAUNCHER.md`](docs/LINUX_LAUNCHER.md), [`docs/LINUX_ISO.md`](docs/LINUX_ISO.md).
- **Os controles são autodetectados** (com hotplug); o lançador permite escolher um específico.

**Requisitos:** Linux x86-64, GPU e driver com suporte a Vulkan, Python 3 (`python3-tk` para a janela), Git, CMake,
Ninja, um compilador C++20, as bibliotecas de desenvolvimento do PS2Recomp (X11, OpenGL, FFmpeg),
`glslangValidator` e cabeçalhos do Vulkan, e sua própria ISO **NTSC-U `SCUS-97399`**.

**Compilar e executar** (detalhes em [`docs/LINUX_COMPILACION.md`](docs/LINUX_COMPILACION.md)):

```sh
# 1. extraia o ELF da sua ISO (também a valida) e compile o runner
python3 tools/linux/gow_launcher.py --iso "/caminho/God of War.iso" --prepare-only
GOW_ELF=/caminho/para/SCUS_973.99 python3 scripts/compilar_linux.py

# 2. opcional, mas recomendado: compilar o microcódigo VU1 (capture uma vez jogando e recompile)
GOW_VU1_CAPTURA=~/vu1_micro <jogue por alguns minutos>
GOW_VU1_MICROCODIGO=~/vu1_micro python3 scripts/compilar_linux.py

# 3. jogar
python3 tools/linux/gow_launcher.py --runner /caminho/para/ps2EntryRunner   # janela; --last a pula
```

**Variáveis de ambiente úteis** (a maioria são opções do lançador):

| Variável | Efeito |
|---|---|
| `GOW_ISO`, `GOW_ISO_DIRS` | Caminho da ISO / pastas extras para procurar |
| `GOW_SKIP_FMV=1` | Pula os vídeos pré-renderizados |
| `GOW_AUDIO=0` | Muda o áudio (o SPU2 continua emulado) |
| `GOW_FULLSCREEN=1`, `GOW_SCALE_FILTER=nearest\|sharp-bilinear`, `GOW_WINDOW_SCALE=<n>` | Opções de tela (F11 alterna tela cheia) |
| `PS2X_VK_DEVICE=<índice ou nome>` | Escolhe a GPU Vulkan (padrão: a discreta primeiro) |
| `GOW_PAD_INDEX=<n>` | Escolhe um controle (padrão: automático) |
| `PS2X_GS_BACKEND=cpu` | Força o renderer CPU |
| `GOW_DEBUG_UI=1` | Sobreposição de depuração |

## Estrutura do repositório

```
.
├── .github/workflows/            # CI: testes (pruebas.yml) e mapa de status (estado.yml)
├── AGENTS.md                     # Convenções do projeto para colaboradores e agentes
├── config/
│   ├── funcmap.csv               # Mapa de funções (nome, início, fim, tamanho)
│   └── recomp.template.toml      # Configuração do PS2Recomp (@ELF@, @MAP@, @OUT@)
├── docs/                         # Documentação técnica (em espanhol)
│   └── estado/                   # Dados do mapa de status e SVG/tabelas gerados
├── game/                         # O SEU SCUS_973.99 vai aqui (ignorado pelo git)
├── patches/
│   └── ps2recomp-*.patch         # Alterações sobre o PS2Recomp @ c5a9d02, aplicadas em ordem
├── scripts/
│   ├── 1_instalar_herramientas.cmd  # Instala as ferramentas
│   ├── 2_compilar.cmd               # Pipeline completo de compilação
│   ├── 2_recompilar_rapido.cmd      # Recompila só src/gow_overrides.cpp (~1 min)
│   ├── 3_ejecutar.cmd               # Executa por 60 s e guarda os logs
│   ├── 3_ejecutar_manual.cmd        # Executa sem limite de tempo
│   ├── probar_menu.ps1              # Teste do menu com capturas do GS
│   ├── probar_pad2.cmd              # Compila e executa o teste de pacotes da libpad2
│   ├── monitor.cmd                  # Monitora CPU/RAM durante a compilação
│   └── *.ps1                        # Lógica dos scripts
├── src/
│   ├── gow_overrides.cpp         # Overrides específicos do jogo
│   └── gow_pad2_packet.h         # Formato do pacote da libpad2 (testado)
├── tests/                        # Testes independentes do jogo e falhas conhecidas da suíte
└── tools/
    ├── ci/                       # Auxiliares da CI (ordem dos patches, config, testes)
    ├── extraer_capa2.ps1         # Extrai a camada 1 de uma ISO DVD-9 de PS2
    ├── linux/gow_launcher.py     # Lançador do Linux: detecção/extração da ISO, janela de ajustes
    └── estado/generar.py         # Gerador do mapa de status
```

> Os nomes de scripts e pastas estão em espanhol, o idioma original do projeto.

## Requisitos

Esta seção e a seguinte descrevem o build para Windows; para Linux veja [acima](#linux-port-nativo).

- Windows 10/11 x64
- [Visual Studio 2022 Build Tools](https://visualstudio.microsoft.com/downloads/) com a carga de trabalho **C++** (inclui CMake e Ninja)
- [Git](https://git-scm.com/)
- ~10 GB livres; 16 GB de RAM recomendados (a compilação usa todos os núcleos)
- Uma cópia própria de **God of War (NTSC-U, SCUS-97399)**

`scripts\1_instalar_herramientas.cmd` instala o Git e as Build Tools com o `winget`.

## Compilar e executar

**1. Obtenha os arquivos do jogo.** Copie o executável do seu disco/ISO para `game\SCUS_973.99`
(ou aponte a variável de ambiente `GOW_ELF` para ele).

Coloque os **módulos `.IRX`** do disco (`SMPD_IOP.IRX`, `989NOMID.IRX`, `LIBSD.IRX`…) ao lado do ELF: o
emulador do IOP executa os originais, e o `scripts\ejecutar.ps1` os copia para `IOP_MOD\` na primeira
execução. Para ler os dados do jogo é preciso a **ISO original**: dê a ela o nome `God of War.iso` e
coloque-a na pasta acima da pasta do ELF, ou defina a variável de ambiente `GOW_ISO` com o caminho dela.

Para extrair também os dados da segunda camada do DVD:

```powershell
powershell -ExecutionPolicy Bypass -File tools\extraer_capa2.ps1 -Iso "D:\God of War.iso" -Salida "D:\GOW ISO extraida"
```

**2. Instale as ferramentas** (só na primeira vez):

```bat
scripts\1_instalar_herramientas.cmd
```

**3. Compile** (20–40 min na primeira vez):

```bat
scripts\2_compilar.cmd
```

O script clona o PS2Recomp em `<unidade>:\gowport` (um caminho curto para evitar o limite de 260
caracteres; configurável com `GOW_WORK`), fixa o commit `c5a9d02`, aplica os patches de `patches/`, gera o código C++ e
compila o `ps2EntryRunner.exe`. O log fica em `logs\2_compilar.log`.

As compilações Release desativam por padrão as trilhas de funções e RPC do IOP. Para investigar,
use `scripts\2_compilar.cmd -Trazas`. Para medir as chamadas a `vid::Flip` do jogo separadamente
da atualização da janela, execute `powershell -File scripts\probar_rendimiento.ps1`;
consulte [as notas do perfil](docs/ESTADO.md#medicion-de-rendimiento-2026-10-05).

**4. Execute:**

```bat
scripts\3_ejecutar.cmd          :: 60 segundos, saída em logs\
scripts\3_ejecutar_manual.cmd   :: sem limite
```

## Como funciona

```mermaid
flowchart LR
    A[SCUS_973.99<br/>ELF MIPS R5900] --> B[ps2_recomp]
    M[funcmap.csv] --> B
    C[recomp.template.toml] --> B
    B --> D[~6.400 arquivos C++]
    D --> E[MSVC + Ninja]
    O[gow_overrides.cpp] --> E
    P["Runtime do PS2Recomp<br/>+ patches/*.patch"] --> E
    E --> F[ps2EntryRunner.exe]
    I[Módulos IRX originais] --> G[Emulador do IOP<br/>R3000A]
    ISO[God of War.iso] --> G
    F <--> G
```

Mais detalhes em [`docs/ARQUITECTURA.md`](docs/ARQUITECTURA.md) (em espanhol).

## Documentação

A documentação técnica está atualmente em espanhol:

- [`docs/ARQUITECTURA.md`](docs/ARQUITECTURA.md) — pipeline, overrides, patches do runtime e integração contínua
- [`docs/CONTROLES.md`](docs/CONTROLES.md) — controles e testes do controle e do menu
- [`docs/RENDERIZADO.md`](docs/RENDERIZADO.md) — renderers CPU/CPU com thread/OpenGL opcionais e comparações
- [`docs/RENDIMIENTO.md`](docs/RENDIMIENTO.md) — medições de desempenho, threads opcionais e otimizações de VU1
- [`docs/LINUX_LAUNCHER.md`](docs/LINUX_LAUNCHER.md), [`docs/LINUX_ISO.md`](docs/LINUX_ISO.md), [`docs/LINUX_COMPILACION.md`](docs/LINUX_COMPILACION.md) — lançador do Linux, tratamento da ISO e build (em inglês)
- [`docs/VULKAN.md`](docs/VULKAN.md) — backend GS Vulkan (em inglês)
- [`docs/PROGRESS_LOG.md`](docs/PROGRESS_LOG.md), [`docs/NEXT_STEPS_PLAN.md`](docs/NEXT_STEPS_PLAN.md) — registro de progresso do Linux e plano rumo aos 60 FPS (em inglês)
- [`AGENTS.md`](AGENTS.md) — convenções do projeto para colaboradores e agentes
- [`docs/ESTADO.md`](docs/ESTADO.md) — status atual, registro da investigação, problemas conhecidos e próximos passos

## Créditos e licença

- [**PS2Recomp**](https://github.com/ran-j/PS2Recomp), de ran-j e colaboradores — recompilador e runtime (GPL-3.0).
- Autores do [**PCSX2**](https://github.com/PCSX2/pcsx2) — GS original utilizado pelo módulo de diagnóstico DX11 opcional (GPL-3.0+).
- [**Urban Reign recomp**](https://github.com/thiagordsfx/urban-reign-recomp), de thiagordsfx — referência compartilhada de integração GS; ajudou a identificar a convenção de campo VSync do nosso espelho ([revisão e alcance](docs/REVISION_URBAN_REIGN.md)).
- [**Fork do runtime de SotC**](https://github.com/LightVelox/PS2Recomp/tree/ac9efa070638ad3b3accd284de6f898d5ab271d1), de Taylor N. Albarnaz / LightVelox — backend GS OpenGL e fila de comandos, e correções do EE (FPU, desvios de 64 bits, LQ/SQ, saltos finais, VU0 em modo macro e cadeias DMA longas) (GPL-3.0, `ac9efa0`).
- *God of War* © Sony Interactive Entertainment / Santa Monica Studio. Este projeto não é afiliado nem
  endossado pela Sony. Nenhum conteúdo do jogo é distribuído.

O código deste repositório é publicado sob a licença **GPL-3.0**, em consonância com o PS2Recomp.
Veja [`LICENSE`](LICENSE).
