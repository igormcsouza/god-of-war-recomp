// GOW-Port: comprueba que los bloques compilados de VU1 (tools/vu1/generar_vu1.cpp) dan exactamente el mismo
// estado que el intérprete en programas sintéticos de varios bloques: VF/VI/ACC/Q/P/I, MAC/estado/CLIP, PC, ciclos
// y la memoria de datos. Los programas mezclan FMAC, ITOF/FTOI/ABS/CLIP, LQ/SQ/ILW/ISW, aritmética de enteros,
// lecturas de flags, DIV/WAITQ y saltos, con pocos registros para que haya dependencias (esperas dentro del
// bloque, esperas heredadas de otro bloque y colas pendientes al entrar). Protege las optimizaciones de
// temporización estática. Sin microcódigo del juego.
// Uso: vu1_block_test --write <carpeta>  |  vu1_block_test [ensayos por programa]
#include "runtime/gs/gs_frontend.h"
#include "runtime/ps2_memory.h"
#include "runtime/ps2_vu1.h"
#include <array>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <fstream>
#include <random>
#include <string>
#include <vector>
#if defined(_M_X64) || defined(__x86_64__)
#include <xmmintrin.h>
#endif

namespace
{
constexpr uint32_t kLowerNop = 0x8000033cu, kNop = 0x2ffu, kEbit = 0x40000000u;
constexpr unsigned kImages = 12, kProgramsPerImage = 24, kProgramBytes = 0x2a0; // 84 pares por programa

struct Gen
{
    std::mt19937 rng;
    uint32_t r(uint32_t n) { return static_cast<uint32_t>(rng() % n); }
    uint32_t reg() { return 1u + r(6u); } // pocos registros: dependencias frecuentes
    uint32_t dest() { return r(5u) == 0u ? 0xFu : (1u + r(15u)); }
    uint32_t upper()
    {
        const uint32_t d = dest(), ft = reg(), fs = reg(), fd = reg();
        switch (r(10u))
        {
        case 0: return kNop;
        case 1: { // ITOF/FTOI/ABS/CLIP
            static const uint32_t c[] = {0x10, 0x11, 0x12, 0x13, 0x14, 0x15, 0x16, 0x17, 0x1D, 0x1F};
            const uint32_t code = c[r(10u)];
            return 0x3Cu | (code & 3u) | ((code >> 2) << 6) | (d << 21) | (ft << 16) | (fs << 11);
        }
        case 2: { // ...A: escribe ACC
            static const uint32_t c[] = {0x00, 0x04, 0x08, 0x0C, 0x18, 0x1C, 0x1E, 0x20, 0x22, 0x28, 0x2A, 0x2C};
            const uint32_t code = c[r(12u)] + (c[r(12u)] < 0x18u ? r(4u) : 0u);
            return 0x3Cu | (code & 3u) | ((code >> 2) << 6) | (d << 21) | (ft << 16) | (fs << 11);
        }
        default: {
            const uint32_t op = r(0x30u);
            return (op == 0x2Eu ? 0x2Au : op) | (d << 21) | (ft << 16) | (fs << 11) | (fd << 6);
        }
        }
    }
    uint32_t lower()
    {
        const uint32_t d = dest(), ft = reg(), fs = reg(), it = 1u + r(6u), is = 1u + r(6u), id = 1u + r(6u);
        const uint32_t imm = r(200u);
        switch (r(14u))
        {
        case 0: case 1: return kLowerNop;
        case 2: return (d << 21) | (ft << 16) | (is << 11) | imm;                        // LQ
        case 3: return (0x01u << 25) | (d << 21) | (fs << 16) | (is << 11) | imm;        // SQ
        case 4: return (0x04u << 25) | (d << 21) | (it << 16) | (is << 11) | imm;        // ILW
        case 5: return (0x05u << 25) | (d << 21) | (it << 16) | (is << 11) | imm;        // ISW
        case 6: return (0x08u << 25) | (it << 16) | (is << 11) | imm;                    // IADDIU
        case 7: return (0x40u << 25) | (id << 6) | (it << 16) | (is << 11) | 0x30u;       // IADD
        case 8: return (0x40u << 25) | (d << 21) | (ft << 16) | (fs << 11) | 0x3Cu | (0x30u >> 2 << 6); // MOVE
        case 9: return (0x1Au << 25) | (it << 16) | (is << 11);                          // FMAND
        case 10: return (0x40u << 25) | (it << 16) | (fs << 11) | (0x3Cu << 0) | ((0x3Cu >> 2) << 6); // MTIR
        case 11: return (0x40u << 25) | (r(4u) << 21) | (r(4u) << 23) | (ft << 16) | (fs << 11) | (0xEu << 6) | 0x3Cu; // DIV
        case 12: return (0x40u << 25) | (0xEu << 6) | 0x3Fu;                              // WAITQ
        default: return (0x1Cu << 25) | (it << 16);                                       // FCGET
        }
    }
};

// Un programa: varios segmentos; cada uno acaba con B (al par que sigue al hueco de retardo) y el último con E.
std::vector<uint8_t> image(unsigned index, std::vector<uint32_t> &starts)
{
    Gen g{std::mt19937(777u + index)};
    std::vector<uint8_t> code(PS2_VU1_CODE_SIZE);
    starts.clear();
    for (unsigned p = 0; p < kProgramsPerImage; ++p)
    {
        uint32_t pc = p * kProgramBytes;
        starts.push_back(pc);
        const unsigned segments = 2u + g.r(3u);
        for (unsigned s = 0; s < segments; ++s)
        {
            const unsigned pairs = 2u + g.r(s == 0u ? 18u : 12u);
            for (unsigned i = 0; i < pairs; ++i, pc += 8u)
            {
                const uint32_t w[2] = {g.lower(), g.upper()};
                std::memcpy(&code[pc], w, 8);
            }
            const bool last = s + 1u == segments;
            const uint32_t w[4] = {last ? kLowerNop : ((0x20u << 25) | 1u), g.upper() | (last ? kEbit : 0u), g.lower(), g.upper()};
            std::memcpy(&code[pc], w, 16);
            pc += 16u;
        }
    }
    return code;
}

float pick(Gen &g)
{
    static const uint32_t sp[] = {0u, 0x80000000u, 0x3F800000u, 0xBF800000u, 0x00800000u, 0x7F7FFFFFu, 0x7F800000u, 0x00000001u, 0x40000000u};
    uint32_t b = g.r(3u) == 0u ? sp[g.r(9u)] : (0x3E000000u + g.r(0x02000000u)) | (g.r(2u) << 31);
    float f;
    std::memcpy(&f, &b, 4);
    return f;
}

bool same(const VU1State &x, const VU1State &y)
{
    return !std::memcmp(x.vf, y.vf, sizeof(x.vf)) && !std::memcmp(x.vi, y.vi, sizeof(x.vi)) && !std::memcmp(x.acc, y.acc, 16) &&
           !std::memcmp(&x.q, &y.q, 4) && !std::memcmp(&x.p, &y.p, 4) && !std::memcmp(&x.i, &y.i, 4) && x.mac == y.mac &&
           x.status == y.status && x.clip == y.clip && x.pc == y.pc && x.cycles == y.cycles && x.ebit == y.ebit &&
           x.branchPending == y.branchPending && x.stoppedByD == y.stoppedByD;
}
} // namespace

int main(int argc, char **argv)
{
    std::vector<uint32_t> starts;
    if (argc == 3 && !std::strcmp(argv[1], "--write"))
    {
        for (unsigned i = 0; i < kImages; ++i)
        {
            const auto code = image(i, starts);
            std::ofstream(std::string(argv[2]) + "/img" + std::to_string(i) + ".bin", std::ios::binary)
                .write(reinterpret_cast<const char *>(code.data()), static_cast<std::streamsize>(code.size()));
        }
        return 0;
    }
    const unsigned trials = argc == 2 ? static_cast<unsigned>(std::atoi(argv[1])) : 6u;
#if defined(_M_X64) || defined(__x86_64__)
    _mm_setcsr(_mm_getcsr() & ~0x8040u);
#endif
    PS2Memory mem;
    if (!mem.initialize())
        return 2;
    GS gs;
    gs.init(mem.getGSVRAM(), 4u * 1024u * 1024u, &mem.gs());
    Gen in{std::mt19937(99u)};
    unsigned long long cases = 0, cycles = 0;
    for (unsigned i = 0; i < kImages; ++i)
    {
        const auto code = image(i, starts);
        std::memcpy(mem.getVU1Code(), code.data(), code.size());
        mem.write32(0x11008000u, *reinterpret_cast<const uint32_t *>(code.data()));
        for (const uint32_t pc : starts)
            for (unsigned t = 0; t < trials; ++t)
            {
                VU1State seed{};
                for (auto &v : seed.vf)
                    for (float &c : v)
                        c = pick(in);
                seed.vf[0][0] = seed.vf[0][1] = seed.vf[0][2] = 0.f, seed.vf[0][3] = 1.f;
                for (int v = 1; v < 16; ++v)
                    seed.vi[v] = static_cast<int32_t>(in.r(120u));
                for (float &c : seed.acc)
                    c = pick(in);
                seed.q = pick(in), seed.i = pick(in), seed.status = in.r(3u) == 0u ? in.r(0x40u) << 6 : 0u;
                std::vector<uint8_t> data0(PS2_VU1_DATA_SIZE);
                for (auto &b : data0)
                    b = static_cast<uint8_t>(in.r(256u));
                VU1State out[2];
                std::vector<uint8_t> mem2[2];
                for (int path = 0; path < 2; ++path)
                {
                    std::memcpy(mem.getVU1Data(), data0.data(), data0.size());
                    VU1Interpreter vu;
                    vu.setDirectRegisterWrites(true);
                    vu.setCompiledProgramsEnabled(path == 1);
                    vu.state() = seed;
                    vu.execute(mem.getVU1Code(), PS2_VU1_CODE_SIZE, mem.getVU1Data(), PS2_VU1_DATA_SIZE, gs, &mem, pc);
                    out[path] = vu.state();
                    mem2[path].assign(mem.getVU1Data(), mem.getVU1Data() + PS2_VU1_DATA_SIZE);
                }
                if (!same(out[0], out[1]) || mem2[0] != mem2[1])
                {
                    std::fprintf(stderr, "VU1 block mismatch: image=%u pc=0x%x trial=%u cycles=%llu/%llu mac=%x/%x status=%x/%x pc=%x/%x data=%d\n",
                                 i, pc, t, (unsigned long long)out[0].cycles, (unsigned long long)out[1].cycles, out[0].mac,
                                 out[1].mac, out[0].status, out[1].status, out[0].pc, out[1].pc, mem2[0] == mem2[1]);
                    return 1;
                }
                ++cases;
                cycles += out[0].cycles;
            }
    }
    std::printf("VU1 blocks: %llu synthetic multi-block executions bit-identical (%llu VU cycles)\n", cases, cycles);
    return 0;
}
