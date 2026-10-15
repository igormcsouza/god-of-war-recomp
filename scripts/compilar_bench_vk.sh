#!/bin/sh
# Builds logs/bench/bench_vk (needs PS2Recomp/build with ps2_runtime already built). See docs/VULKAN.md.
set -e
R="$(cd "$(dirname "$0")/.." && pwd)"; B="$R/PS2Recomp/build"; RT="$R/PS2Recomp/ps2xRuntime"
mkdir -p "$R/logs/bench"
c++ -std=c++20 -march=x86-64-v2 -O2 -DPS2X_GS_VULKAN=1 -I"$RT/src/runner" -I"$RT/include" \
  "$R/tools/render/bench_vk.cpp" -o "$R/logs/bench/bench_vk" -Wl,--unresolved-symbols=ignore-all \
  "$B/ps2xRuntime/libps2_runtime.a" "$B/ps2xRuntime/librlImGui.a" "$B/ps2xRuntime/libimgui.a" \
  -lavcodec -lavformat -lavutil -lswresample -lswscale "$B/ps2xIOP/libps2_iop.a" -lvulkan \
  "$B/_deps/raylib-build/raylib/libraylib.a" -lm -lpthread -lGL -lrt
