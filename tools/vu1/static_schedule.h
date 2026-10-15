// GOW-Port: temporización estática de bloques para generar_vu1.cpp (se incluye tras VU1CompiledGenerator).
//
// Para un prefijo del bloque sin saltos, finales, DIV/EFU/XGKICK ni instrucciones inferiores fuera de línea se
// calcula el ciclo de cada par respecto al de entrada: cada par ocupa un ciclo y espera a que terminen los
// escritores del propio prefijo (latencia > distancia: espera constante). Lo único que depende de fuera son las
// lecturas de registros que el prefijo no escribe antes: el bloque comprueba al entrar que ninguna está
// pendiente más allá de su par (live-in) y, si no, usa la versión par a par. Con esa comprobación el prefijo no
// consulta la tabla de listos, no confirma colas ni avanza ciclos por par: fija m_cycle por par (constante) y,
// al final, deja la tabla de listos con el último escritor de cada registro (VU1Interpreter::stepPairStaticT).
#pragma once
#include <cstdint>
#include <set>
#include <sstream>
#include <string>
#include <tuple>
#include <vector>

namespace vu1s
{
    using G = VU1CompiledGenerator;

    struct Slot
    {
        uint8_t kind, reg, lane; // 0 = VF, 1 = VI, 2 = ACC
        uint32_t cycle;          // LiveIn: el par que la lee; Write: ciclo en que el valor queda listo
    };
    struct Plan
    {
        size_t region = 0; // pares con temporización estática (0 = el bloque no la usa)
        std::vector<uint32_t> offset;
        std::vector<Slot> liveIns, writes;
        uint32_t span = 0; // ciclos del prefijo
    };

    // Espejo de vu1c::lowerInline (ps2_vu1_compiled.inl): el código generado lo comprueba con static_assert.
    inline bool lowerInline(uint32_t instr)
    {
        const uint32_t opHi = (instr >> 25) & 0x7Fu, funct = instr & 0x3Fu;
        const uint32_t funct2 = (instr & 0x3u) | ((instr >> 4) & 0x7Cu);
        if (instr == 0x00000000u || instr == 0x8000033Cu)
            return true;
        switch (opHi)
        {
        case 0x00u: case 0x01u: case 0x04u: case 0x05u: case 0x08u: case 0x09u:
        case 0x12u: case 0x18u: case 0x1Au: case 0x1Cu:
        case 0x20u: case 0x21u: case 0x24u: case 0x25u:
        case 0x28u: case 0x29u: case 0x2Cu: case 0x2Du: case 0x2Eu: case 0x2Fu:
            return true;
        default:
            break;
        }
        if (opHi != 0x40u)
            return false;
        if (funct == 0x30u || funct == 0x31u || funct == 0x32u || funct == 0x34u || funct == 0x35u)
            return true;
        return funct >= 0x3Cu && (funct2 == 0x30u || funct2 == 0x31u || funct2 == 0x34u || funct2 == 0x35u ||
                                  funct2 == 0x3Bu || funct2 == 0x38u || funct2 == 0x3Cu || funct2 == 0x3Du);
    }

    inline bool eligible(const G::Pair &p)
    {
        if (p.eBit || p.dBit || p.tBit || G::isBranch(p))
            return false;
        const G::Usage &l = p.lowerUsage;
        // VU1Interpreter::Pipeline es privado: 3 = Fdiv, 4 = Efu, 7 = Xgkick (ps2_vu1.h).
        const int pipeline = static_cast<int>(l.pipeline);
        if (l.waitQ || l.waitP || pipeline == 3 || pipeline == 4 || pipeline == 7)
            return false;
        return p.iBit || lowerInline(p.lower);
    }

    inline Plan plan(const std::vector<const G::Pair *> &pairs)
    {
        Plan pl;
        size_t n = 0;
        while (n + 1u < pairs.size() && eligible(*pairs[n]))
            ++n; // el último par del bloque siempre va por la ruta par a par
        if (n < 4u)
            return pl;
        struct W
        {
            bool valid = false;
            uint32_t ready = 0;
        };
        W vf[32][4]{}, vi[16]{}, acc[4]{};
        std::set<std::tuple<int, int, int>> seen;
        for (size_t i = 0; i < n; ++i)
        {
            const G::Pair &p = *pairs[i];
            uint32_t o = i ? pl.offset[i - 1] + 1u : 0u;
            std::vector<Slot> pending;
            const auto read = [&](uint8_t kind, uint8_t reg, uint8_t lane, const W &w)
            {
                if (w.valid)
                    o = std::max(o, w.ready);
                else
                    pending.push_back({kind, reg, lane, 0});
            };
            for (const G::Usage *u : {&p.upperUsage, &p.lowerUsage})
            {
                for (uint32_t k = 0; k < u->vfReadCount && k < 2u; ++k)
                    for (uint32_t c = 0; c < 4u; ++c)
                        if ((u->vfRead[k].lanes & (8u >> c)) != 0u && u->vfRead[k].reg != 0u)
                            read(0, u->vfRead[k].reg, static_cast<uint8_t>(c), vf[u->vfRead[k].reg & 31u][c]);
                for (uint32_t r = 1; r < 16u; ++r)
                    if ((u->viRead & (1u << r)) != 0u)
                        read(1, static_cast<uint8_t>(r), 0, vi[r]);
                for (uint32_t c = 0; c < 4u; ++c)
                    if ((u->accRead & (8u >> c)) != 0u)
                        read(2, 0, static_cast<uint8_t>(c), acc[c]);
            }
            pl.offset.push_back(o);
            for (Slot s : pending)
                if (seen.insert({s.kind, s.reg, s.lane}).second)
                    pl.liveIns.push_back({s.kind, s.reg, s.lane, o});
            // Escrituras del par (markPairWrites): primero la inferior y después la superior.
            const G::VfAccess lw = p.lowerUsage.vfWrite, uw = p.upperUsage.vfWrite;
            if (lw.reg != 0u && p.suppressedLowerVf != lw.reg)
            {
                const uint32_t lat = p.lowerUsage.vfLatency ? p.lowerUsage.vfLatency : p.lowerUsage.latency;
                for (uint32_t c = 0; c < 4u; ++c)
                    if (lw.lanes & (8u >> c))
                        vf[lw.reg & 31u][c] = {true, o + lat};
            }
            if (uw.reg != 0u)
            {
                const uint32_t lat = p.upperUsage.vfLatency ? p.upperUsage.vfLatency : p.upperUsage.latency;
                for (uint32_t c = 0; c < 4u; ++c)
                    if (uw.lanes & (8u >> c))
                        vf[uw.reg & 31u][c] = {true, o + lat};
            }
            for (uint32_t r = 1; r < 16u; ++r)
                if (p.lowerUsage.viWrite & (1u << r))
                    vi[r] = {true, o + (p.lowerUsage.viLatency ? p.lowerUsage.viLatency : p.lowerUsage.latency)};
            for (uint32_t c = 0; c < 4u; ++c)
                if (p.upperUsage.accWrite & (8u >> c))
                    acc[c] = {true, o + G::kAccLatency};
        }
        pl.region = n;
        pl.span = pl.offset[n - 1] + 1u;
        for (uint32_t r = 0; r < 32u; ++r)
            for (uint32_t c = 0; c < 4u; ++c)
                if (vf[r][c].valid)
                    pl.writes.push_back({0, static_cast<uint8_t>(r), static_cast<uint8_t>(c), vf[r][c].ready});
        for (uint32_t r = 1; r < 16u; ++r)
            if (vi[r].valid)
                pl.writes.push_back({1, static_cast<uint8_t>(r), 0, vi[r].ready});
        for (uint32_t c = 0; c < 4u; ++c)
            if (acc[c].valid)
                pl.writes.push_back({2, 0, static_cast<uint8_t>(c), acc[c].ready});
        return pl;
    }

    inline std::string ready(const Slot &s)
    {
        std::ostringstream o;
        if (s.kind == 0)
            o << "VU1CompiledAccess::vfReady(vu, " << int(s.reg) << ", " << int(s.lane) << ")";
        else if (s.kind == 1)
            o << "VU1CompiledAccess::viReady(vu, " << int(s.reg) << ")";
        else
            o << "VU1CompiledAccess::accReady(vu, " << int(s.lane) << ")";
        return o.str();
    }

    // Función de bloque estático: comprueba la entrada, ejecuta el prefijo con temporización fija y sigue con
    // los pares restantes (stepText) igual que el bloque par a par `fallback`, que usa si la entrada no cumple.
    inline std::string emit(const Plan &pl, const std::string &name, const std::string &fallback, uint32_t head,
                            const std::vector<uint32_t> &words, const std::vector<uint32_t> &pcs,
                            const std::vector<std::string> &types, const std::vector<bool> &dead,
                            const std::vector<std::string> &stepText)
    {
        std::ostringstream o;
        o << "    VU1C_FAST int " << name << "(VU1Interpreter &vu, C &c)\n    {\n"
          << "        static constexpr uint32_t words[" << words.size() << "] = {";
        for (size_t w = 0; w < words.size(); ++w)
            o << (w ? ", " : "") << "0x" << std::hex << words[w] << "u" << std::dec;
        o << "};\n"
          << "        static VU1CompiledAccess::BlockCheck check;\n"
          << "        if (!VU1CompiledAccess::block(vu, c, " << head << "u, words, sizeof(words), check))\n            return 0;\n"
          << "        const uint64_t base = VU1CompiledAccess::cycle(vu);\n"
          << "        if (!g_staticOn || !VU1CompiledAccess::staticEntry(vu, base + " << pl.span << "u)";
        for (const Slot &s : pl.liveIns)
            o << " ||\n            " << ready(s) << " > base + " << s.cycle << "u";
        o << ")\n        {\n            ++g_staticMisses;\n            return " << fallback << "(vu, c);\n        }\n"
          << "        ++g_staticHits;\n        g_blockPairs += " << pcs.size() << "u;\n";
        for (size_t i = 0; i < pl.region; ++i)
            o << "        static_assert(vu1c::lowerInline(" << types[i] << "::value.lower) || " << types[i] << "::value.iBit);\n"
              << "        VU1CompiledAccess::stepStatic<" << types[i] << ", " << (dead[i] ? "true" : "false") << ">(vu, c, base + "
              << pl.offset[i] << "u);\n";
        for (const Slot &s : pl.writes)
        {
            const char *fn = s.kind == 0 ? "setVfReady" : s.kind == 1 ? "setViReady" : "setAccReady";
            o << "        VU1CompiledAccess::" << fn << "(vu, ";
            if (s.kind == 0) o << int(s.reg) << ", " << int(s.lane);
            else if (s.kind == 1) o << int(s.reg);
            else o << int(s.lane);
            o << ", base + " << s.cycle << "u);\n";
        }
        o << "        VU1CompiledAccess::staticExit(vu, base + " << pl.span << "u, " << pcs[pl.region] << "u);\n";
        for (size_t i = pl.region; i < stepText.size(); ++i)
            o << stepText[i];
        o << "        return 1;\n    }\n";
        return o.str();
    }
}
