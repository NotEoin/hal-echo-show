#!/usr/bin/env bash
# Cross-compiles whisper.cpp's whisper-bench and whisper-cli for the Echo, in the build image.
#   bench/build.sh [arm64-v8a|armeabi-v7a]   -> bench/out/<abi>/
# Same pinned release as the app (app/src/main/cpp/CMakeLists.txt), statically linked.
set -euo pipefail
cd "$(dirname "$0")/.."

ABI="${1:-arm64-v8a}"
VERSION=1.9.5
SHA256=ff1a9053feb509ff9d7729703355541ae9690073a6b1c40eb692c962e0dc1720

docker run --rm --user "$(id -u):$(id -g)" -e HOME=/tmp -v "$PWD:/src/android" hal-echo-android:1 bash -euo pipefail -c "
    export PATH=\$ANDROID_HOME/cmake/3.22.1/bin:\$PATH
    cd /tmp
    curl -fsSL --max-time 300 -o whisper.tgz https://github.com/ggml-org/whisper.cpp/archive/refs/tags/v${VERSION}.tar.gz
    echo '${SHA256}  whisper.tgz' | sha256sum -c -
    tar -xzf whisper.tgz
    cmake -G Ninja -S whisper.cpp-${VERSION} -B build -DCMAKE_BUILD_TYPE=Release \
        -DCMAKE_TOOLCHAIN_FILE=\$ANDROID_HOME/ndk/27.2.12479018/build/cmake/android.toolchain.cmake \
        -DANDROID_ABI=${ABI} -DANDROID_PLATFORM=android-30 -DANDROID_STL=c++_static \
        -DBUILD_SHARED_LIBS=OFF -DGGML_OPENMP=OFF -DWHISPER_BUILD_TESTS=OFF > /dev/null
    cmake --build build -j \$(nproc) --target whisper-bench whisper-cli > /dev/null
    mkdir -p /src/android/bench/out/${ABI}
    cp build/bin/whisper-bench build/bin/whisper-cli whisper.cpp-${VERSION}/samples/jfk.wav /src/android/bench/out/${ABI}/
"
echo "built bench/out/${ABI}"
