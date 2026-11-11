# The Android build environment: JDK 17, the SDK, the NDK and Gradle, all pinned.
# Build with ./build.sh; nothing here needs to be installed on the host.
FROM eclipse-temurin:17-jdk-jammy

ARG CMDLINE_TOOLS=commandlinetools-linux-16111833_latest.zip
# SHA-1 from Google's repository2-3.xml, the checksum Google publishes for this file
ARG CMDLINE_TOOLS_SHA1=e025545c62a8e64c7559119566a569fb1dec5f60
ARG GRADLE_VERSION=8.11.1
ARG GRADLE_SHA256=f397b287023acdba1e9f6fc5ea72d22dd63669d59ed4a289a29b1a76eee151c6

ENV ANDROID_HOME=/opt/android-sdk \
    GRADLE_USER_HOME=/cache/gradle
ENV PATH=$PATH:/opt/gradle/bin:$ANDROID_HOME/cmdline-tools/latest/bin:$ANDROID_HOME/platform-tools

RUN apt-get update \
    && apt-get install -y --no-install-recommends unzip curl ca-certificates \
    && rm -rf /var/lib/apt/lists/*

RUN curl -fsSL --max-time 600 -o /tmp/tools.zip "https://dl.google.com/android/repository/${CMDLINE_TOOLS}" \
    && echo "${CMDLINE_TOOLS_SHA1}  /tmp/tools.zip" | sha1sum -c - \
    && mkdir -p "$ANDROID_HOME/cmdline-tools" \
    && unzip -q /tmp/tools.zip -d "$ANDROID_HOME/cmdline-tools" \
    && mv "$ANDROID_HOME/cmdline-tools/cmdline-tools" "$ANDROID_HOME/cmdline-tools/latest" \
    && rm /tmp/tools.zip

# sdkmanager checks each package against the same manifest's checksums; build.sh runs as
# the host user, so every file must be readable and every tool executable by anyone
RUN yes | sdkmanager --licenses > /dev/null \
    && sdkmanager --install \
        "platforms;android-35" \
        "build-tools;35.0.0" \
        "ndk;27.2.12479018" \
        "cmake;3.22.1" \
        "platform-tools" > /dev/null \
    && chmod -R a+rX "$ANDROID_HOME"

RUN curl -fsSL --max-time 600 -o /tmp/gradle.zip \
        "https://services.gradle.org/distributions/gradle-${GRADLE_VERSION}-bin.zip" \
    && echo "${GRADLE_SHA256}  /tmp/gradle.zip" | sha256sum -c - \
    && unzip -q /tmp/gradle.zip -d /opt \
    && mv "/opt/gradle-${GRADLE_VERSION}" /opt/gradle \
    && rm /tmp/gradle.zip

WORKDIR /src/android
