#!/usr/bin/env bash
# Times Whisper on the connected Echo without installing anything: pushes whisper-bench,
# whisper-cli, a speech sample and the models to /data/local/tmp, runs them, deletes them.
#   bench/run-on-device.sh MODEL.bin [MODEL.bin ...]   (models from `hal-echo models NAME`)
set -euo pipefail
cd "$(dirname "$0")"

[ $# -gt 0 ] || { echo "usage: $0 MODEL.bin [MODEL.bin ...]" >&2; exit 2; }
DIR=/data/local/tmp/hal-echo-bench
ADB_TIMEOUT=600  # seconds; base.en on four slow cores takes well under this

adb get-state > /dev/null
abi="$(adb shell getprop ro.product.cpu.abi | tr -d '\r')"
[ -d "out/$abi" ] || { echo "run bench/build.sh $abi first" >&2; exit 1; }

echo "== device"
for prop in ro.product.model ro.build.version.release ro.lineage.version ro.product.cpu.abi; do
    echo "$prop=$(adb shell getprop "$prop" | tr -d '\r')"
done
adb shell "grep -E 'MemTotal|MemAvailable' /proc/meminfo"
adb shell nproc

trap 'adb shell rm -rf "$DIR" > /dev/null 2>&1 || true' EXIT
adb shell mkdir -p "$DIR"
adb push "out/$abi/whisper-bench" "out/$abi/whisper-cli" "out/$abi/jfk.wav" "$DIR/" > /dev/null
adb shell chmod 755 "$DIR/whisper-bench" "$DIR/whisper-cli"

for model in "$@"; do
    name="$(basename "$model")"
    adb push "$model" "$DIR/$name" > /dev/null
    for threads in 4 2; do
        echo "== $name, $threads threads: encoder benchmark"
        timeout "$ADB_TIMEOUT" adb shell "$DIR/whisper-bench -m $DIR/$name -t $threads 2>&1 | grep -E 'load time|encode time|total time'"
    done
    for ctx in 0 768; do
        echo "== $name: jfk.wav (11 s of speech), audio_ctx $ctx"
        timeout "$ADB_TIMEOUT" adb shell "$DIR/whisper-cli -m $DIR/$name -f $DIR/jfk.wav -t 4 -nt -ac $ctx 2>&1 | grep -E 'total time|^ *[A-Za-z]' | tail -3"
    done
    adb shell rm -f "$DIR/$name"
done
echo "== removed $DIR"
