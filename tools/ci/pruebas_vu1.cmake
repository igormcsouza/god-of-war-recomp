# GOW-Port: compilar un programa procedural con el generador real; no incluye datos del juego.
set(GOW_VU1_TABLE_STUB "${CMAKE_CURRENT_LIST_DIR}/function_table_stub.cpp")
set(GOW_VU1_TEST_SOURCE "${CMAKE_CURRENT_LIST_DIR}/../../tests/vu1_compiled_test.cpp")
add_executable(gow_vu1_generator "${CMAKE_CURRENT_LIST_DIR}/../vu1/generar_vu1.cpp")
target_link_libraries(gow_vu1_generator PRIVATE ps2_runtime)
add_executable(gow_vu1_fixture "${GOW_VU1_TEST_SOURCE}")
target_link_libraries(gow_vu1_fixture PRIVATE ps2_runtime)
set(GOW_VU1_TEST_DIR "${CMAKE_BINARY_DIR}/gow_vu1_procedural")
set(GOW_VU1_TEST_PARTS)
foreach(part RANGE 0 12)
    list(APPEND GOW_VU1_TEST_PARTS "${GOW_VU1_TEST_DIR}/programa${part}.cpp")
endforeach()
add_custom_command(OUTPUT ${GOW_VU1_TEST_PARTS}
    COMMAND "${CMAKE_COMMAND}" -E make_directory "${GOW_VU1_TEST_DIR}"
    COMMAND "$<TARGET_FILE:gow_vu1_fixture>" --write "${GOW_VU1_TEST_DIR}/synthetic.bin"
    COMMAND "$<TARGET_FILE:gow_vu1_generator>" "${GOW_VU1_TEST_DIR}" "${GOW_VU1_TEST_DIR}/synthetic.bin"
    DEPENDS gow_vu1_fixture gow_vu1_generator
    VERBATIM)
add_executable(gow_vu1_compiled_test "${GOW_VU1_TEST_SOURCE}" ${GOW_VU1_TEST_PARTS})
target_link_libraries(gow_vu1_compiled_test PRIVATE ps2_runtime)
target_include_directories(gow_vu1_compiled_test PRIVATE "${CMAKE_SOURCE_DIR}/ps2xRuntime/src/lib/vu")
if(NOT MSVC)
    target_compile_options(gow_vu1_compiled_test PRIVATE -ffp-contract=off)
endif()

# GOW-Port: todas las FMAC (fuentes, máscaras DEST, cruzadas) compiladas frente al intérprete con valores
# límite aleatorios. Con -march=x86-64-v2 el código compilado usa el camino SSE de 4 carriles.
set(GOW_VU1_FMAC_SOURCE "${CMAKE_CURRENT_LIST_DIR}/../../tests/vu1_fmac_test.cpp")
add_executable(gow_vu1_fmac_fixture "${GOW_VU1_FMAC_SOURCE}" "${GOW_VU1_TABLE_STUB}")
target_link_libraries(gow_vu1_fmac_fixture PRIVATE ps2_runtime)
set(GOW_VU1_FMAC_DIR "${CMAKE_BINARY_DIR}/gow_vu1_fmac")
set(GOW_VU1_FMAC_PARTS)
foreach(part RANGE 0 12)
    list(APPEND GOW_VU1_FMAC_PARTS "${GOW_VU1_FMAC_DIR}/programa${part}.cpp")
endforeach()
add_custom_command(OUTPUT ${GOW_VU1_FMAC_PARTS}
    COMMAND "${CMAKE_COMMAND}" -E make_directory "${GOW_VU1_FMAC_DIR}"
    COMMAND "$<TARGET_FILE:gow_vu1_fmac_fixture>" --write "${GOW_VU1_FMAC_DIR}/synthetic.bin"
    COMMAND "$<TARGET_FILE:gow_vu1_generator>" "${GOW_VU1_FMAC_DIR}" "${GOW_VU1_FMAC_DIR}/synthetic.bin"
    DEPENDS gow_vu1_fmac_fixture gow_vu1_generator
    VERBATIM)
add_executable(gow_vu1_fmac_test "${GOW_VU1_FMAC_SOURCE}" ${GOW_VU1_FMAC_PARTS} "${GOW_VU1_TABLE_STUB}")
target_link_libraries(gow_vu1_fmac_test PRIVATE ps2_runtime)
target_include_directories(gow_vu1_fmac_test PRIVATE "${CMAKE_SOURCE_DIR}/ps2xRuntime/src/lib/vu")
if(NOT MSVC)
    target_compile_options(gow_vu1_fmac_test PRIVATE -ffp-contract=off)
endif()

# GOW-Port: programas sinteticos de varios bloques (esperas, colas, saltos, memoria) compilados frente al interprete.
set(GOW_VU1_BLOCK_SOURCE "${CMAKE_CURRENT_LIST_DIR}/../../tests/vu1_block_test.cpp")
add_executable(gow_vu1_block_fixture "${GOW_VU1_BLOCK_SOURCE}" "${GOW_VU1_TABLE_STUB}")
target_link_libraries(gow_vu1_block_fixture PRIVATE ps2_runtime)
set(GOW_VU1_BLOCK_DIR "${CMAKE_BINARY_DIR}/gow_vu1_block")
set(GOW_VU1_BLOCK_PARTS)
foreach(part RANGE 0 12)
    list(APPEND GOW_VU1_BLOCK_PARTS "${GOW_VU1_BLOCK_DIR}/programa${part}.cpp")
endforeach()
add_custom_command(OUTPUT ${GOW_VU1_BLOCK_PARTS}
    COMMAND "${CMAKE_COMMAND}" -E make_directory "${GOW_VU1_BLOCK_DIR}/img"
    COMMAND "$<TARGET_FILE:gow_vu1_block_fixture>" --write "${GOW_VU1_BLOCK_DIR}/img"
    COMMAND "$<TARGET_FILE:gow_vu1_generator>" "${GOW_VU1_BLOCK_DIR}" "${GOW_VU1_BLOCK_DIR}/img"
    DEPENDS gow_vu1_block_fixture gow_vu1_generator
    VERBATIM)
add_executable(gow_vu1_block_test "${GOW_VU1_BLOCK_SOURCE}" ${GOW_VU1_BLOCK_PARTS} "${GOW_VU1_TABLE_STUB}")
target_link_libraries(gow_vu1_block_test PRIVATE ps2_runtime)
target_include_directories(gow_vu1_block_test PRIVATE "${CMAKE_SOURCE_DIR}/ps2xRuntime/src/lib/vu")
if(NOT MSVC)
    target_compile_options(gow_vu1_block_test PRIVATE -ffp-contract=off)
endif()
