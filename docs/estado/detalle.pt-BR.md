# Status do port: detalhes

![Status · Linux](mapa.linux.pt-BR.svg)

![Status · Windows](mapa.windows.pt-BR.svg)

Gerado por `tools/estado/generar.py` a partir de `docs/estado/datos.toml` e `config/funcmap.csv`. Não edite à mão.

## Resumo

| Plataforma | Bibliotecas do SDK da Sony* | Hardware do PS2 |
|---|---:|---:|
| Linux | 65.4% (423/647) | 53.8% |
| Windows | 65.4% (423/647) | 57.8% |

## Bibliotecas do SDK da Sony*

| Biblioteca | Funções | Windows | Linux | Nota |
|---|---:|---|---|---|
| `libmpeg` | 103 | 🔧 Parcial | 🔧 Parcial | A intro FMV é decodificada por software e toca inteira (callbacks de fluxo MPEG síncronos); os demais vídeos ainda precisam ser verificados; GOW_SKIP_FMV pula os vídeos **Linux:** A intro FMV toca inteira após a correção dos callbacks síncronos (capturas até o cartão «Three Weeks Earlier»); os demais vídeos sem verificar; a tela após a cutscene pode travar (pendente); GOW_SKIP_FMV=1 (opção do lançador) pula os vídeos |
| `libipu` | 5 | 🔧 Parcial | 🔧 Parcial | sceIpuInit corrigido; a rota MPEG por software funciona, mas a cobertura completa das operações da IPU não foi verificada |
| `libgraph` | 7 | ✅ Funciona | ✅ Funciona |  |
| `libdma` | 8 | ✅ Funciona | ✅ Funciona |  |
| `libcdvd` | 10 | ✅ Funciona | ✅ Funciona | Lê a ISO original |
| `libdbc` | 11 | 🔧 Parcial | 🔧 Parcial | RPC de dbcman e SIO2 verificados ao carregar e salvar no cartão; os controles SIO2 ainda aparecem desconectados |
| `libpad2` | 13 | 🔧 Parcial | 🔧 Parcial | HLE da primeira porta (teclado ou gamepad, controle autodetectado no Linux); pressões 0/255 **Linux:** HLE da primeira porta; controle autodetectado (índices 0-3, GOW_PAD_INDEX) com mapeamento SDL genérico para controles sem mapeamento; pressões 0/255; segunda porta desconectada |
| `libvib` | 2 | ⏳ Pendente | ⏳ Pendente | Sem vibração: o HLE não anuncia atuadores |
| `libmc2` | 90 | 🔧 Parcial | 🔧 Parcial | Listar, carregar, salvar e recarregar verificados com uma cópia de cartão PCSX2 de 8 MB com ECC; faltam formatação e reabertura no PCSX2 |
| `libscf` | 14 | ✅ Funciona | ✅ Funciona |  |
| `libgcc` | 32 | ✅ Funciona | ✅ Funciona |  |
| `C++ EH` | 34 | ✅ Funciona | ✅ Funciona |  |
| `libm` | 14 | ✅ Funciona | ✅ Funciona |  |
| `libc` | 150 | ✅ Funciona | ✅ Funciona |  |
| `libkernel` | 101 | ✅ Funciona | ✅ Funciona |  |
| `sif` | 24 | ✅ Funciona | ✅ Funciona | Comandos e RPC do SIF |
| `fileio` | 15 | ✅ Funciona | ✅ Funciona |  |
| `loadfile` | 14 | ✅ Funciona | ✅ Funciona | Heap do IOP e carga de módulos |

## Hardware do PS2

| Grupo | Componente | Peso | Windows | Linux | Nota |
|---|---|---:|---|---|---|
| EE | CPU R5900 (recompilada para C++) | 5 | ✅ Funciona | ✅ Funciona |  |
| EE | Kernel: threads, semáforos e alarmes | 3 | ✅ Funciona | ✅ Funciona |  |
| EE | FPU (COP1) e instruções MMI | 2 | ✅ Funciona | ✅ Funciona |  |
| EE | INTC: VSync e interrupção do GS | 2 | ✅ Funciona | ✅ Funciona |  |
| EE | Controlador DMA | 2 | ✅ Funciona | ✅ Funciona | As cadeias fromSPR/toSPR já copiam a paleta de ossos; formas de Kratos e inimigos verificadas na partida |
| EE | Temporizadores | 1 | ✅ Funciona | ✅ Funciona |  |
| GS / VU | GS: primitivas e framebuffer | 3 | 🔧 Parcial | 🔧 Parcial | Referência CPU e backend Vulkan compute (idêntico byte a byte à CPU, padrão no Linux) além de OpenGL no Windows; barco, Kratos, inimigos e HUD visíveis; algumas primitivas com feedback de textura ainda usam a CPU; falhas visuais em orbes/partículas; falta cobertura completa **Linux:** Backend Vulkan compute por padrão (idêntico byte a byte à CPU nos testes; no Linux o contexto OpenGL é um stub); barco, Kratos, inimigos e HUD visíveis; algumas primitivas com feedback de textura ainda usam a CPU; falhas visuais em orbes/partículas; ~20-30 fps na partida |
| GS / VU | VIF1 e VU1 | 3 | 🔧 Parcial | 🔧 Parcial | Microcódigo VU1 compilado para C++ (blocos com temporização estática, idêntico ao interpretador em testes de gravação/reprodução); precisa de uma captura local do microcódigo; na partida a thread da VU1 ainda é um dos limites de velocidade; falta verificar a cobertura |
| GS / VU | GS: texturas, CLUT e fontes | 2 | 🔧 Parcial | 🔧 Parcial | HUD visível; bilinear e nearest STQ CPU/OpenGL verificados, incluindo limites 16.16 com sinal, com padrões procedurais de PCSX2 software; feedback GPU estável em modo experimental; lotes de texturas regionais otimizados e verificados nos 13 PSMs; cache GS real e cobertura de fontes/CLUT ainda não verificadas |
| GS / VU | GIF (PATH1-3) | 2 | ✅ Funciona | ✅ Funciona |  |
| GS / VU | IPU: vídeo FMV | 2 | 🔧 Parcial | 🔧 Parcial | A intro FMV funciona por decodificação MPEG por software; isso não comprova emulação completa do hardware IPU **Linux:** A intro FMV funciona por decodificação MPEG por software com callbacks de fluxo síncronos (correção verificada com capturas); isso não comprova emulação completa do hardware IPU; travamento após a cutscene pendente |
| IOP | CPU R3000A (interpretador) | 3 | ✅ Funciona | ✅ Funciona | Escalonador ocioso de Opus integrado e validado com GS/VU1: guarda o próximo despertar; seu perfil reduz IOP de ~1300–1500 para ~570–650 ms a cada 5 s; falta comparar FPS sem compilações simultâneas |
| IOP | SPU2: saída de áudio | 3 | 🔧 Parcial | 🔧 Parcial | Carregamento de bancos e som contínuo verificados; a música em streaming não reinicia mais a cada 0,36 s (latência de leitura do CD e salto de loop do SPU2 corrigidos; verificado por log, não de ouvido); faltam reverb e ADMA **Linux:** As correções de latência do CD e de loop do SPU2 foram verificadas no Linux apenas por log (230 s de menu, áudio mudo; não de ouvido); faltam reverb e ADMA |
| IOP | Módulos IRX originais | 2 | ✅ Funciona | ✅ Funciona |  |
| IOP | SIF: RPC e DMA EE ↔ IOP | 2 | ✅ Funciona | ✅ Funciona |  |
| IOP | CDVD: leitura da ISO original | 2 | ✅ Funciona | ✅ Funciona |  |
| IOP | Controle DualShock 2 | 2 | 🔧 Parcial | 🔧 Parcial | libpad2 por HLE (primeira porta); no SIO2 emulado os controles aparecem desconectados **Linux:** libpad2 por HLE (primeira porta); controle autodetectado (com mapeamento genérico se o SDL não o conhece); botões verificados jogando; sem vibração; o SIO2 emulado continua sem ver controles |
| IOP | SIO2: memory card | 2 | 🔧 Parcial | 🔧 Parcial | SIO2 e cartão de 8 MB com ECC: carregar, salvar e recarregar verificados no jogo em uma cópia PCSX2; faltam formatação e reabertura no PCSX2 |
| Linux | Port nativo para Linux | 2 | 🔧 Parcial | 🔧 Parcial | Lançador (extrai a ISO, detecta o controle, opção de pular vídeos), GS por Vulkan (compute), VU1 compilada e compilação nativa funcionam; a VU1 compilada precisa de uma captura local do microcódigo; ~20-30 fps na partida (meta: 60); falhas visuais em orbes/partículas e um travamento após a cutscene da intro |
| Linux | Lançador e preparação da ISO | 2 | — | ✅ Funciona | Extrai o ELF/IRX da ISO pessoal e valida o hash; janela de ajustes (tela cheia, filtro, controle, GPU, mudo, pular vídeos); testes sintéticos na CI (docs/LINUX_LAUNCHER.md) |
| Linux | Compilação nativa | 2 | — | 🔧 Parcial | O runner compila e roda no Linux (scripts/compilar_linux.py); a VU1 compilada precisa de uma captura local do microcódigo (GOW_VU1_MICROCODIGO) e a CI só compila o runtime sem o ELF |
| Linux | Velocidade: 60 fps | 2 | — | ⏳ Pendente | ~20-30 fps na partida (RTX 5050; meta 60): o GS compute exato fica em ~25-30 fps e falta uma rota estilo hardware; sem 1080p real (só escalonamento) |
| Linux | Tela após a cutscene da intro | 1 | — | ⏳ Pendente | Um travamento após a cutscene da intro ainda não foi investigado (docs/PROGRESS_LOG.md, docs/ESTADO.md); GOW_SKIP_FMV=1 o evita |

* Funções das bibliotecas estáticas da Sony ligadas em SCUS_973.99 (config/funcmap.csv). Hardware: ponderado por componente.
