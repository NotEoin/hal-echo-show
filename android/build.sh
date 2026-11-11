#!/usr/bin/env bash
# Builds and tests the Android app inside the pinned build image (Dockerfile); needs only docker.
#   ./build.sh test     unit tests and lint
#   ./build.sh apk      the signed release APK, in app/build/outputs/apk/release/
# The first run makes a signing key in keystore/ (git-ignored): keep it, updates need it.
set -euo pipefail
cd "$(dirname "$0")"

IMAGE=hal-echo-android:1
task="${1:-apk}"

# The host network: on GitHub's runners the default build network cannot resolve DNS
docker image inspect "$IMAGE" > /dev/null 2>&1 || docker build --network host -t "$IMAGE" .

run() {
    docker run --rm \
        --user "$(id -u):$(id -g)" \
        -e HOME=/tmp \
        -e ANDROID_USER_HOME=/tmp/.android \
        -e HAL_ECHO_KEYSTORE=/src/android/keystore/release.jks \
        -e HAL_ECHO_KEYSTORE_PASSWORD="${password:-}" \
        -v "$PWD/..:/src" \
        -v hal-echo-gradle:/cache \
        "$IMAGE" "$@"
}

# The cache volume is created by root; hand it to the build user once
docker run --rm -v hal-echo-gradle:/cache "$IMAGE" chown "$(id -u):$(id -g)" /cache

if [ ! -f keystore/release.jks ]; then
    mkdir -p keystore
    chmod 700 keystore
    head -c 24 /dev/urandom | base64 | tr -d '/+=' > keystore/password
    chmod 600 keystore/password
    password="$(cat keystore/password)"
    run keytool -genkeypair -keystore /src/android/keystore/release.jks -alias hal-echo \
        -keyalg EC -groupname secp256r1 -sigalg SHA256withECDSA -validity 10000 \
        -dname "CN=hal-echo-show" -storepass "$password" -keypass "$password"
fi
password="$(cat keystore/password)"

[ -f gradlew ] || run gradle wrapper --gradle-version 8.11.1 --distribution-type bin --no-daemon

case "$task" in
    test) run ./gradlew --no-daemon testDebugUnitTest lintRelease ;;
    apk) run ./gradlew --no-daemon assembleRelease ;;
    *) echo "usage: $0 [test|apk]" >&2; exit 2 ;;
esac
