// GOW-Port: repeatable GPU benchmark for GSVulkanBackend. Replays a local GOW_GS_REPLAY_TRACE capture
// (game data, never committed) headless, reports GPU ms (timestamps), dispatches, prims and wall time per
// pass, and byte-compares the final VRAM with the CPU backend replay.
// Usage: bench_vk <capture.gsr> [passes=5] [--no-cpu]   (build: scripts/compilar_bench_vk.sh)
#include "gow_gs_replay.h"
#include "runtime/gs/gs_cpu_backend.h"
#include "runtime/gs/gs_vulkan_backend.h"
#include <algorithm>
#include <chrono>
#include <cstdlib>
#include <iostream>

namespace replay = gow_gs_replay;
namespace
{
    bool apply(GSRasterBackend &b, const replay::Record &r, uint32_t &frames)
    {
        using replay::Op;
        GSPrimitiveBatch batch{}; replay::Clut clut{}; GSTransferCommand transfer{};
        replay::Clear clear{}; replay::Pixel pixel{}; GSPresentationRequest present{};
        GSSyncReason sync{}; uint32_t csr = 0;
        switch (r.op)
        {
        case Op::Submit: if (!replay::pod(r, batch)) return false; b.Submit(batch); break;
        case Op::Clut: if (!replay::pod(r, clut)) return false; b.LoadClut(clut.tex0, clut.texclut); break;
        case Op::Transfer: if (!replay::pod(r, transfer)) return false; b.BeginTransfer(transfer); break;
        case Op::Upload: b.UploadImage(r.data.data(), uint32_t(r.data.size())); break;
        case Op::TextureFlush: b.TextureFlush(); break;
        case Op::Flush: b.Flush(); break;
        case Op::Reset: b.Reset(); break;
        case Op::Sync: if (!replay::pod(r, sync)) return false; b.Sync(sync); break;
        case Op::Present: if (!replay::pod(r, present)) return false; (void)b.Present(present); ++frames; break;
        case Op::Clear: if (!replay::pod(r, clear)) return false; if (uint32_t(b.ClearFramebuffer(clear.context, clear.rgba)) != clear.result) return false; break;
        case Op::Write: if (!replay::pod(r, pixel)) return false; b.WriteVram(pixel.psm, pixel.base, pixel.bw, pixel.x, pixel.y, pixel.value); break;
        case Op::Read: if (!replay::pod(r, pixel)) return false; if (b.ReadVram(pixel.psm, pixel.base, pixel.bw, pixel.x, pixel.y) != pixel.value) return false; break;
        case Op::Mxcsr: if (!replay::pod(r, csr)) return false; _mm_setcsr(csr); break;
        case Op::Consume: {
            if (r.data.size() < 4) return false;
            uint32_t n = 0; std::memcpy(&n, r.data.data(), 4);
            std::vector<uint8_t> data(n); const auto count = b.ConsumeLocalToHostBytes(data.data(), n);
            if (count != r.data.size() - 4 || std::memcmp(data.data(), r.data.data() + 4, count)) return false; break;
        }
        default: return false;
        }
        return true;
    }
    struct Result { double wallMs = 0, gpuMs = 0; uint64_t dispatches = 0, prims = 0; uint32_t frames = 0; size_t badOp = SIZE_MAX; std::vector<uint8_t> vram; };
    template <class B> Result run(const std::vector<replay::Record> &recs, const replay::Snapshot &init)
    {
        Result res;
        uint8_t *vram = static_cast<uint8_t *>(std::aligned_alloc(4096, PS2_GS_VRAM_SIZE));
        std::memcpy(vram, init.vram.data(), PS2_GS_VRAM_SIZE);
        {
            B backend; backend.Initialize(vram, PS2_GS_VRAM_SIZE);
            if (!backend.ImportState(init.state)) { std::cerr << "ImportState failed\n"; std::exit(2); }
            backend.Sync(GSSyncReason::Finish);
            const auto t0 = std::chrono::steady_clock::now();
            for (size_t i = 0; i < recs.size(); ++i)
                if (!apply(backend, recs[i], res.frames)) { res.badOp = i; break; }
            backend.Sync(GSSyncReason::Finish);
            res.wallMs = std::chrono::duration<double, std::milli>(std::chrono::steady_clock::now() - t0).count();
            backend.SnapshotVram(res.vram);
            if constexpr (std::is_same_v<B, GSVulkanBackend>) { auto t = backend.GpuTotals(); res.gpuMs = t.busyMs; res.dispatches = t.dispatches; res.prims = t.prims; }
        }
        std::free(vram);
        return res;
    }
}

int main(int argc, char **argv)
{
    if (argc < 2) { std::cerr << "usage: bench_vk <capture.gsr> [passes] [--no-cpu]\n"; return 1; }
    int passes = argc > 2 && argv[2][0] != '-' ? std::atoi(argv[2]) : 5;
    bool cpu = true;
    for (int i = 2; i < argc; ++i) if (!std::strcmp(argv[i], "--no-cpu")) cpu = false;
    setenv("PS2X_GS_VULKAN_STATS", "1", 1); // enables GPU timestamps (per-second lines go to stderr)
    replay::Reader reader(argv[1]); replay::Record rec; replay::Snapshot init; std::vector<replay::Record> recs; replay::Snapshot fin;
    if (!reader.next(rec) || rec.op != replay::Op::Initial || !replay::decodeSnapshot(rec, init)) { std::cerr << "bad capture: " << reader.error << "\n"; return 1; }
    while (reader.next(rec)) { if (rec.op == replay::Op::End) { replay::decodeSnapshot(rec, fin); break; } recs.push_back(std::move(rec)); }
    {   // primitive mix of the capture (type, textured, blended)
        uint64_t n[8][2][2]{};
        for (auto &r : recs) if (r.op == replay::Op::Submit) { GSPrimitiveBatch b{}; if (replay::pod(r, b)) ++n[b.state.prim.type & 7][b.state.prim.tme][b.state.prim.abe]; }
        const char *names[] = {"point", "line", "linestrip", "triangle", "tristrip", "trifan", "sprite", "?"};
        std::cout << "records=" << recs.size() << " mix:";
        for (int t = 0; t < 8; ++t) for (int a = 0; a < 2; ++a) for (int e = 0; e < 2; ++e) if (n[t][a][e]) std::cout << " " << names[t] << (a ? "+tex" : "") << (e ? "+blend" : "") << "=" << n[t][a][e];
        std::cout << "\n";
    }
    std::vector<uint8_t> ref;
    if (cpu) {
        Result c = run<GSCpuBackend>(recs, init);
        std::cout << "cpu: wall=" << c.wallMs << " ms frames=" << c.frames << " badOp=" << int64_t(c.badOp) << "\n"; ref = c.vram;
    }
    std::vector<double> gpu, wall;
    int rc = 0;
    for (int p = 0; p < passes; ++p) {
        Result v = run<GSVulkanBackend>(recs, init);
        gpu.push_back(v.gpuMs); wall.push_back(v.wallMs);
        size_t diff = 0, first = SIZE_MAX;
        if (cpu) for (size_t i = 0; i < ref.size() && i < v.vram.size(); ++i) if (ref[i] != v.vram[i]) { if (first == SIZE_MAX) first = i; ++diff; }
        std::cout << "pass " << p << ": gpu_ms=" << v.gpuMs << " (per frame " << v.gpuMs / std::max(1u, v.frames) << ") dispatches=" << v.dispatches
                  << " prims=" << v.prims << " wall_ms=" << v.wallMs << " frames=" << v.frames << " badOp=" << int64_t(v.badOp)
                  << (cpu ? " vram_diff_bytes=" + std::to_string(diff) : "") << "\n";
        if (diff || v.badOp != SIZE_MAX) rc = 3;
    }
    auto stat = [](const std::vector<double> &v) { double m = 0, s = 0; for (double x : v) m += x; m /= v.size(); for (double x : v) s += (x - m) * (x - m); return std::pair{m, std::sqrt(s / v.size())}; };
    auto g = stat(gpu), w = stat(wall);
    std::cout << "SUMMARY gpu_ms mean=" << g.first << " sd=" << g.second << " | wall_ms mean=" << w.first << " sd=" << w.second << "\n";
    return rc;
}
