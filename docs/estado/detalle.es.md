# Estado del port: detalle

![Estado · Linux](mapa.linux.es.svg)

![Estado · Windows](mapa.windows.es.svg)

Generado por `tools/estado/generar.py` a partir de `docs/estado/datos.toml` y `config/funcmap.csv`. No lo edites a mano.

## Resumen

| Plataforma | Librerías del SDK de Sony* | Hardware de la PS2 |
|---|---:|---:|
| Linux | 65.4% (423/647) | 53.8% |
| Windows | 65.4% (423/647) | 57.8% |

## Librerías del SDK de Sony*

| Librería | Funciones | Windows | Linux | Nota |
|---|---:|---|---|---|
| `libmpeg` | 103 | 🔧 Parcial | 🔧 Parcial | La intro FMV se decodifica por software y se reproduce entera (callbacks de flujo MPEG síncronos); falta verificar el resto de vídeos; GOW_SKIP_FMV omite los vídeos **Linux:** La intro FMV se reproduce entera tras el arreglo de callbacks síncronos (capturas hasta la tarjeta «Three Weeks Earlier»); los demás vídeos sin verificar; la pantalla tras la cinemática puede colgarse (pendiente); GOW_SKIP_FMV=1 (opción del lanzador) omite los vídeos |
| `libipu` | 5 | 🔧 Parcial | 🔧 Parcial | sceIpuInit corregido; la ruta MPEG por software funciona, sin verificar todas las operaciones de la IPU |
| `libgraph` | 7 | ✅ Funciona | ✅ Funciona |  |
| `libdma` | 8 | ✅ Funciona | ✅ Funciona |  |
| `libcdvd` | 10 | ✅ Funciona | ✅ Funciona | Lee la ISO original |
| `libdbc` | 11 | 🔧 Parcial | 🔧 Parcial | RPC de dbcman y SIO2 verificados al cargar y guardar en tarjeta; los mandos SIO2 aún se ven desconectados |
| `libpad2` | 13 | 🔧 Parcial | 🔧 Parcial | HLE del primer puerto (teclado o gamepad, mando autodetectado en Linux); presiones 0/255 **Linux:** HLE del primer puerto; mando autodetectado (índices 0-3, GOW_PAD_INDEX) con mapeo SDL genérico para mandos sin mapeo; presiones 0/255; segundo puerto desconectado |
| `libvib` | 2 | ⏳ Pendiente | ⏳ Pendiente | Sin vibración: el HLE no anuncia actuadores |
| `libmc2` | 90 | 🔧 Parcial | 🔧 Parcial | Listar, cargar, guardar y recargar verificados con una copia de tarjeta PCSX2 de 8 MB con ECC; faltan formateo y reapertura en PCSX2 |
| `libscf` | 14 | ✅ Funciona | ✅ Funciona |  |
| `libgcc` | 32 | ✅ Funciona | ✅ Funciona |  |
| `C++ EH` | 34 | ✅ Funciona | ✅ Funciona |  |
| `libm` | 14 | ✅ Funciona | ✅ Funciona |  |
| `libc` | 150 | ✅ Funciona | ✅ Funciona |  |
| `libkernel` | 101 | ✅ Funciona | ✅ Funciona |  |
| `sif` | 24 | ✅ Funciona | ✅ Funciona | Comandos y RPC del SIF |
| `fileio` | 15 | ✅ Funciona | ✅ Funciona |  |
| `loadfile` | 14 | ✅ Funciona | ✅ Funciona | Heap del IOP y carga de módulos |

## Hardware de la PS2

| Grupo | Componente | Peso | Windows | Linux | Nota |
|---|---|---:|---|---|---|
| EE | CPU R5900 (recompilada a C++) | 5 | ✅ Funciona | ✅ Funciona |  |
| EE | Kernel: hilos, semáforos y alarmas | 3 | ✅ Funciona | ✅ Funciona |  |
| EE | FPU (COP1) e instrucciones MMI | 2 | ✅ Funciona | ✅ Funciona |  |
| EE | INTC: VSync e interrupción del GS | 2 | ✅ Funciona | ✅ Funciona |  |
| EE | Controlador DMA | 2 | ✅ Funciona | ✅ Funciona | Las cadenas fromSPR/toSPR ya copian la paleta de huesos; formas de Kratos y enemigos verificadas en partida |
| EE | Temporizadores | 1 | ✅ Funciona | ✅ Funciona |  |
| GS / VU | GS: primitivas y framebuffer | 3 | 🔧 Parcial | 🔧 Parcial | Referencia CPU y backend Vulkan compute (byte a byte idéntico a la CPU, por defecto en Linux) además de OpenGL en Windows; barco, Kratos, enemigos y HUD visibles; algunas primitivas con feedback de textura siguen en CPU; fallos visuales en orbes/partículas; falta cobertura completa **Linux:** Backend Vulkan compute por defecto (byte a byte idéntico a la CPU en las pruebas; en Linux el contexto OpenGL es un stub); barco, Kratos, enemigos y HUD visibles; algunas primitivas con feedback de textura siguen en CPU; fallos visuales en orbes/partículas; ~20-30 fps en partida |
| GS / VU | VIF1 y VU1 | 3 | 🔧 Parcial | 🔧 Parcial | Microcódigo VU1 compilado a C++ (bloques con temporización estática, idéntico al intérprete en pruebas de grabación/reproducción); necesita una captura local del microcódigo; en partida el hilo de VU1 sigue siendo uno de los límites de velocidad; falta certificar cobertura |
| GS / VU | GS: texturas, CLUT y fuentes | 2 | 🔧 Parcial | 🔧 Parcial | HUD visible; bilineal y nearest STQ CPU/OpenGL verificados, incluidos límites 16.16 con signo, con patrones procedurales de PCSX2 software; feedback GPU estable en modo experimental; lotes de texturas regionales optimizados y verificados en los 13 PSM; quedan pendientes la caché GS real y la cobertura de fuentes/CLUT |
| GS / VU | GIF (PATH1-3) | 2 | ✅ Funciona | ✅ Funciona |  |
| GS / VU | IPU: vídeo FMV | 2 | 🔧 Parcial | 🔧 Parcial | La intro FMV funciona por decodificación MPEG por software; no demuestra emulación completa del hardware IPU **Linux:** La intro FMV funciona por decodificación MPEG por software con callbacks de flujo síncronos (arreglo verificado con capturas); no demuestra emulación completa del hardware IPU; cuelgue tras la cinemática pendiente |
| IOP | CPU R3000A (intérprete) | 3 | ✅ Funciona | ✅ Funciona | Planificador ocioso de Opus integrado y validado con GS/VU1: recuerda el próximo despertar; su perfil reduce IOP de ~1300–1500 a ~570–650 ms cada 5 s; falta una comparación de FPS sin compilaciones concurrentes |
| IOP | SPU2: salida de audio | 3 | 🔧 Parcial | 🔧 Parcial | Bancos cargados y sonido continuo verificados; la música en streaming ya no se reinicia cada 0,36 s (latencia de lectura del CD y salto de bucle del SPU2 corregidos; comprobado por registro, no de oído); faltan reverb y ADMA **Linux:** Los arreglos de latencia del CD y de bucle del SPU2 se comprobaron en Linux solo por registro (230 s de menú, audio silenciado; no de oído); faltan reverb y ADMA |
| IOP | Módulos IRX originales | 2 | ✅ Funciona | ✅ Funciona |  |
| IOP | SIF: RPC y DMA EE ↔ IOP | 2 | ✅ Funciona | ✅ Funciona |  |
| IOP | CDVD: lectura de la ISO original | 2 | ✅ Funciona | ✅ Funciona |  |
| IOP | Mando DualShock 2 | 2 | 🔧 Parcial | 🔧 Parcial | libpad2 por HLE (primer puerto); en el SIO2 emulado los mandos se ven desconectados **Linux:** libpad2 por HLE (primer puerto); mando autodetectado (con mapeo genérico si SDL no lo conoce); botones comprobados jugando; sin vibración; SIO2 emulado sigue sin ver mandos |
| IOP | SIO2: memory card | 2 | 🔧 Parcial | 🔧 Parcial | SIO2 y tarjeta de 8 MB con ECC: cargar, guardar y recargar verificados en el juego sobre una copia PCSX2; faltan formateo y reapertura en PCSX2 |
| Linux | Port nativo para Linux | 2 | 🔧 Parcial | 🔧 Parcial | Lanzador (extrae la ISO, detecta el mando, opción de omitir vídeos), GS por Vulkan (compute), VU1 compilada y compilación nativa funcionan; la VU1 compilada necesita una captura local del microcódigo; ~20-30 fps en partida (objetivo: 60); fallos visuales en orbes/partículas y un cuelgue tras la cinemática de la intro |
| Linux | Lanzador y preparación de la ISO | 2 | — | ✅ Funciona | Extrae el ELF/IRX de la ISO personal y valida el hash; ventana de ajustes (pantalla completa, filtro, mando, GPU, silenciar, omitir vídeos); pruebas sintéticas en la CI (docs/LINUX_LAUNCHER.md) |
| Linux | Compilación nativa | 2 | — | 🔧 Parcial | El runner se compila y se ejecuta en Linux (scripts/compilar_linux.py); la VU1 compilada necesita una captura local del microcódigo (GOW_VU1_MICROCODIGO) y la CI solo compila el runtime sin el ELF |
| Linux | Velocidad: 60 fps | 2 | — | ⏳ Pendiente | ~20-30 fps en partida (RTX 5050; objetivo 60): el GS compute exacto ronda 25-30 fps y falta una ruta estilo hardware; sin 1080p real (solo escalado) |
| Linux | Pantalla tras la cinemática de la intro | 1 | — | ⏳ Pendiente | Un cuelgue tras la cinemática de la intro sigue sin investigarse (docs/PROGRESS_LOG.md, docs/ESTADO.md); GOW_SKIP_FMV=1 lo evita |

* Funciones de las librerías estáticas de Sony enlazadas en SCUS_973.99 (config/funcmap.csv). Hardware: ponderado por componente.
