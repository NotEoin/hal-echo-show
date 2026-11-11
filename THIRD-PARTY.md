# Third-party software

The Android app bundles the libraries below, each under its own licence, and the bridge downloads
the speech models listed after them. The licence texts that the bundled code requires ship inside
the app, in `android/app/src/main/assets/licenses/`.

## Bundled in the app

The following libraries are compiled into the APK, unmodified.

| Library | Version | Licence | Source |
| --- | --- | --- | --- |
| whisper.cpp | 1.9.5 | MIT | <https://github.com/ggml-org/whisper.cpp> |
| Vosk (vosk-android) | 0.3.75 | Apache 2.0 | <https://github.com/alphacep/vosk-api> |
| Termux terminal-emulator and terminal-view | 0.118.3 | Apache 2.0 | <https://github.com/termux/termux-app> |
| lazysodium-android | 5.1.0 | MPL 2.0 | <https://github.com/terl/lazysodium-java> |
| libsodium (inside lazysodium) | 1.0.18 or later | ISC | <https://github.com/jedisct1/libsodium> |
| JNA | 5.12.1 | Apache 2.0 (chosen of Apache 2.0 or LGPL 2.1) | <https://github.com/java-native-access/jna> |
| Geist Mono | 1.9.2 | SIL Open Font License 1.1 | <https://github.com/vercel/geist-font> |

Only the emulator and renderer modules of Termux are used; the rest of the Termux app is GPL 3
and is not included.

## Downloaded by the bridge

The bridge downloads these models on request and sends them to devices; none ship in the
repository or the APK.

| Model | Licence | Source |
| --- | --- | --- |
| Whisper `tiny.en`, `base.en` (ggml) | MIT | <https://huggingface.co/ggerganov/whisper.cpp> |
| Vosk `vosk-model-small-en-us-0.15` | Apache 2.0 | <https://alphacephei.com/vosk/models> |
