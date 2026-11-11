# Builds whisper.cpp for the app and the JNI bridge to it (whisper_jni.cpp).
# whisper.cpp is fetched at a pinned release and checked against its SHA-256.
cmake_minimum_required(VERSION 3.22.1)
project(halecho_whisper LANGUAGES C CXX)

include(FetchContent)
FetchContent_Declare(
    whisper
    URL https://github.com/ggml-org/whisper.cpp/archive/refs/tags/v1.9.5.tar.gz
    URL_HASH SHA256=ff1a9053feb509ff9d7729703355541ae9690073a6b1c40eb692c962e0dc1720
)
set(WHISPER_BUILD_TESTS OFF CACHE BOOL "" FORCE)
set(WHISPER_BUILD_EXAMPLES OFF CACHE BOOL "" FORCE)
set(WHISPER_BUILD_SERVER OFF CACHE BOOL "" FORCE)
set(BUILD_SHARED_LIBS OFF CACHE BOOL "" FORCE)
# OpenMP threads spin while idle; the device runs other work between transcriptions
set(GGML_OPENMP OFF CACHE BOOL "" FORCE)
FetchContent_MakeAvailable(whisper)

add_library(halecho_whisper SHARED whisper_jni.cpp)
target_link_libraries(halecho_whisper PRIVATE whisper log)
