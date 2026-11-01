# External reference: Persona 4 (2026-10-11)

Review requested by the user of
[Raikaru/Persona4-Decompilation](https://github.com/Raikaru/Persona4-Decompilation),
pinned to commit `6d3b9e362cc43eff2cb67b5ec5a289f38bb77025`.
Its documentation, tools and examples of matrices/VU0/skinning are read;
its installation, compilers and game are not run and no code is imported.

It is a reconstruction for Persona 4 USA `SLUS_217.82`, with C that aims to
reproduce the bytes of the PS2 executable, and assembly fallbacks. Its
[README](https://github.com/Raikaru/Persona4-Decompilation/blob/6d3b9e362cc43eff2cb67b5ec5a289f38bb77025/README.md)
distinguishes byte matching, C recovery and linking with original code.
Its addresses, structures, compilers and data do not correspond to GoW.

Material useful for our research:

- [effect_vu0_internal.h](https://github.com/Raikaru/Persona4-Decompilation/blob/6d3b9e362cc43eff2cb67b5ec5a289f38bb77025/include/effect_vu0_internal.h)
  makes explicit ordered VU0 operations, registers that stay live,
  aligned loads/stores, bit transfers and lane
  masks. It helps guide review of EE/VU0 semantics and build
  our own procedural cases; it does not compile directly as a PC implementation.
- [fndiff.py](https://github.com/Raikaru/Persona4-Decompilation/blob/6d3b9e362cc43eff2cb67b5ec5a289f38bb77025/tools/fndiff.py)
  and [verify.py](https://github.com/Raikaru/Persona4-Decompilation/blob/6d3b9e362cc43eff2cb67b5ec5a289f38bb77025/tools/verify.py)
  compare instructions/bytes and check relocations. The tool
  avoids presenting included original assembly as validated C recovery; nor should it hide undecoded R5900
  instructions under a single
  unknown text. The method is useful when comparing a GoW routine
  against its ELF, although our PC recompilation needs semantic testing.
- [RenderWare.md](https://github.com/Raikaru/Persona4-Decompilation/blob/6d3b9e362cc43eff2cb67b5ec5a289f38bb77025/wiki/RenderWare.md)
  distinguishes the core and the PS2 driver: some functions are still in assembly and the
  core source does not contain the sky2 driver. The rpskin and
  skinskycommon files reviewed belong to that middleware; they do not provide a
  demonstrated fix for GoW's skinning or GS path.

The reviewed tree shows no repository-wide license. There are
licenses for specific components, which do not automatically extend to the
rest. Links and methodology are kept; any code reuse
would need to identify its terms. No RenderWare sources, retail assembly
or Persona 4 data are incorporated.

Immediate application: review bit transfers and lane masks
if a GoW input/output or its VIF/VU submission shows a discrepancy. Do not
attribute to the external repository a fix for framing, animations or
performance without reproducing it. GoW's current probe only confirms final products
in a sample; it does not rule out incorrect input poses.
