// GOW-Port: GOW_CHEAT (depuración, desactivado por defecto). Ver docs/CONTROLES.md.
#pragma once
#include "ps2_runtime.h"
#include "ps2_runtime_macros.h"
#include <ps2_recompiled_functions.h>
#include <chrono>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <fstream>
#include <string>
#include <vector>
#include <algorithm>

namespace gow_cheat
{
    // GOW_CHEAT_DUMP=<s1,s2,...> (investigación): vuelca los 32 MB de RAM del EE a <GOW_CHEAT_DUMP_DIR o .>/ram_<s>.bin
    // cuando pasan esos segundos desde la primera lectura del mando.
    inline void dumpPoll(const uint8_t *rdram, double seconds)
    {
        static std::vector<double> times = [] {
            std::vector<double> v;
            if (const char *s = std::getenv("GOW_CHEAT_DUMP"))
                for (const char *p = s; *p;)
                {
                    char *end = nullptr;
                    v.push_back(std::strtod(p, &end));
                    p = (end && *end == ',') ? end + 1 : (end && end > p ? end : p + 1);
                }
            return v;
        }();
        static size_t next = 0;
        if (next >= times.size() || seconds < times[next]) return;
        const char *dir = std::getenv("GOW_CHEAT_DUMP_DIR");
        const std::string name = std::string(dir ? dir : ".") + "/ram_" + std::to_string(static_cast<int>(times[next])) + ".bin";
        std::ofstream(name, std::ios::binary).write(reinterpret_cast<const char *>(rdram), 0x02000000);
        std::fprintf(stderr, "[gow-cheat] dump %s at %.1f s\n", name.c_str(), seconds);
        ++next;
    }

    inline uint32_t rd32(const uint8_t *rdram, uint32_t a) { uint32_t v; std::memcpy(&v, rdram + (a & 0x01FFFFFFu), 4); return v; }
    inline float rdf(const uint8_t *rdram, uint32_t a) { float v; std::memcpy(&v, rdram + (a & 0x01FFFFFFu), 4); return v; }

    // GOW_CHEAT=god,noenemies,diag (coma). Se leen una vez.
    inline bool has(const char *token)
    {
        static const std::string env = std::getenv("GOW_CHEAT") ? std::getenv("GOW_CHEAT") : "";
        return env.find(token) != std::string::npos;
    }
    inline bool god() { static const bool v = has("god"); return v; }
    inline bool noEnemies() { static const bool v = has("noenemies"); return v; }
    inline bool diag() { static const bool v = has("diag"); return v; }

    // Kratos: [[0x29CD58]] (la funcion 0x1E0BC0 del juego compara "this" con ese objeto).
    inline uint32_t player(const uint8_t *rdram)
    {
        const uint32_t holder = rd32(rdram, 0x29CD58u);
        return holder ? rd32(rdram, holder) : 0u;
    }

    // Enemigos conocidos: criaturas de la misma clase que Kratos que pasan por la inicializacion de actor (0x1DE718
    // llama a SetHealth(this, max) desde 0x1DE818 al aparecer). Sirve para cualquier nivel: no depende del reparto del pool.
    inline std::vector<uint32_t> &enemies() { static std::vector<uint32_t> v; return v; }

    // SetHealth del juego (0x1E0A80): this=a0, nuevo valor=f12; fija vida en this+0x178 acotada a [0, this+0x17C].
    // Es la unica escritura de vida (todo dano/curacion pasa por aqui), asi que cubre todos los llamadores.
    inline void setHealth(uint8_t *rdram, R5900Context *ctx, PS2Runtime *)
    {
        const uint32_t self = GPR_U32(ctx, 4), ra = GPR_U32(ctx, 31);
        const float old = rdf(rdram, self + 0x178u), max = rdf(rdram, self + 0x17Cu);
        float v = ctx->f[12];
        const bool isPlayer = self == player(rdram);
        static unsigned logged[2] = {0, 0};
        if (diag() && v != old && logged[isPlayer]++ < 300)
            std::fprintf(stderr, "[gow-cheat:hp] this=%x vt=%x ra=%x old=%g new=%g max=%g player=%d\n", self,
                         rd32(rdram, self + 4u), ra, old, v, max, isPlayer);
        if (!isPlayer && ra == 0x1DE818u && max > 0.f && rd32(rdram, self + 4u) == rd32(rdram, player(rdram) + 4u) &&
            std::find(enemies().begin(), enemies().end(), self) == enemies().end())
        {
            enemies().push_back(self);
            if (diag()) std::fprintf(stderr, "[gow-cheat] enemy spawned this=%x hp=%g (%zu known)\n", self, max, enemies().size());
        }
        if (isPlayer && god() && v < old) v = old;       // Kratos no pierde vida
        if (!isPlayer && noEnemies() && v < old) v = 0.f; // cualquier dano mata
        v = v < 0.f ? 0.f : v > max ? max : v;
        std::memcpy(rdram + (self & 0x01FFFFFFu) + 0x178u, &v, 4);
        ctx->pc = ra;
    }

    // Se llama una vez por fotograma desde la lectura del mando (hilo principal del EE).
    inline void poll(uint8_t *rdram)
    {
        static const bool on = std::getenv("GOW_CHEAT") || std::getenv("GOW_CHEAT_DUMP");
        if (!on) return;
        static const auto start = std::chrono::steady_clock::now();
        const double seconds = std::chrono::duration<double>(std::chrono::steady_clock::now() - start).count();
        dumpPoll(rdram, seconds);
        // noenemies: los enemigos conocidos con vida pasan a 0 en cuanto aparecen; la logica del juego los mata.
        if (noEnemies())
            for (const uint32_t e : enemies())
                if (rdf(rdram, e + 0x178u) > 0.f)
                {
                    const float zero = 0.f;
                    std::memcpy(rdram + (e & 0x01FFFFFFu) + 0x178u, &zero, 4);
                    if (diag()) std::fprintf(stderr, "[gow-cheat] kill this=%x at %.1f s\n", e, seconds);
                }
    }
}
