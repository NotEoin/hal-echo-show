plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
}

android {
    namespace = "io.github.noteoin.halecho"
    compileSdk = 35
    buildToolsVersion = "35.0.0"
    ndkVersion = "27.2.12479018"

    defaultConfig {
        applicationId = "io.github.noteoin.halecho"
        // LineageOS 18.1 for the Echo Show 5 is Android 11
        minSdk = 30
        targetSdk = 34
        versionCode = 2
        versionName = "0.2.0-dev"
        ndk {
            // The MT8163 is ARMv8; which ABI the ROM's userspace runs is checked on the device
            abiFilters += listOf("arm64-v8a", "armeabi-v7a")
        }
        externalNativeBuild {
            cmake {
                arguments += listOf("-DANDROID_STL=c++_shared", "-DCMAKE_BUILD_TYPE=Release")
            }
        }
    }

    signingConfigs {
        create("release") {
            // A local keystore made by build.sh; updates must be signed with the same key
            storeFile = file(System.getenv("HAL_ECHO_KEYSTORE") ?: "../keystore/release.jks")
            storePassword = System.getenv("HAL_ECHO_KEYSTORE_PASSWORD")
            keyAlias = "hal-echo"
            keyPassword = System.getenv("HAL_ECHO_KEYSTORE_PASSWORD")
        }
    }

    buildTypes {
        release {
            isMinifyEnabled = false
            signingConfig = signingConfigs.getByName("release")
        }
    }

    externalNativeBuild {
        cmake {
            path = file("src/main/cpp/CMakeLists.txt")
            version = "3.22.1"
        }
    }

    buildFeatures {
        buildConfig = true
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }

    kotlinOptions {
        jvmTarget = "17"
    }

    testOptions {
        unitTests.isReturnDefaultValues = true
    }

    lint {
        abortOnError = true
        warningsAsErrors = false
        // Sideloaded onto one Android 11 device; Play's target level rules do not apply
        disable += listOf("ExpiredTargetSdkVersion", "OldTargetApi")
    }
}

dependencies {
    implementation("com.alphacephei:vosk-android:0.3.75")
    // Apache 2.0, unlike the rest of the Termux app: the emulator and its renderer only
    implementation("com.github.termux.termux-app:terminal-view:v0.118.3")
    // 5.1.x: 5.2.0 is built for Java 21 class files; both have ristretto255
    implementation("com.goterl:lazysodium-android:5.1.0@aar")
    implementation("net.java.dev.jna:jna:5.12.1@aar")

    testImplementation("junit:junit:4.13.2")
    testImplementation("com.goterl:lazysodium-java:5.1.4")
    testImplementation("org.json:json:20250517")
}
