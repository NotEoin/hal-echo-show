// JNI bridge from stt/Whisper.kt to whisper.cpp: load a model, transcribe 16 kHz mono floats.
// One context serves one thread at a time; Whisper.kt serialises calls.
#include <jni.h>
#include <android/log.h>

#include <string>

#include "whisper.h"

namespace {

constexpr const char *kTag = "halecho-whisper";
// Segments Whisper rates as more likely silence than speech are dropped, as hal-voice does
// (its stt.py NO_SPEECH_MAX)
constexpr float kNoSpeechMax = 0.5f;

std::string to_string(JNIEnv *env, jstring value) {
    if (value == nullptr) return {};
    const char *chars = env->GetStringUTFChars(value, nullptr);
    std::string out(chars);
    env->ReleaseStringUTFChars(value, chars);
    return out;
}

}  // namespace

extern "C" JNIEXPORT jlong JNICALL
Java_io_github_noteoin_halecho_stt_Whisper_nativeInit(JNIEnv *env, jclass, jstring model_path) {
    whisper_context_params params = whisper_context_default_params();
    params.use_gpu = false;
    whisper_context *ctx =
        whisper_init_from_file_with_params(to_string(env, model_path).c_str(), params);
    if (ctx == nullptr) __android_log_print(ANDROID_LOG_ERROR, kTag, "model failed to load");
    return reinterpret_cast<jlong>(ctx);
}

extern "C" JNIEXPORT jstring JNICALL
Java_io_github_noteoin_halecho_stt_Whisper_nativeTranscribe(
    JNIEnv *env, jclass, jlong handle, jfloatArray samples, jint threads, jint audio_ctx,
    jstring prompt) {
    auto *ctx = reinterpret_cast<whisper_context *>(handle);
    whisper_full_params params = whisper_full_default_params(WHISPER_SAMPLING_GREEDY);
    params.n_threads = threads;
    params.language = "en";
    params.translate = false;
    params.no_timestamps = true;
    params.print_progress = false;
    params.print_realtime = false;
    params.print_special = false;
    params.print_timestamps = false;
    params.suppress_blank = true;
    params.audio_ctx = audio_ctx;  // 0 is the model's full 30 s window
    std::string initial_prompt = to_string(env, prompt);
    params.initial_prompt = initial_prompt.empty() ? nullptr : initial_prompt.c_str();

    jsize count = env->GetArrayLength(samples);
    jfloat *data = env->GetFloatArrayElements(samples, nullptr);
    int status = whisper_full(ctx, params, data, count);
    env->ReleaseFloatArrayElements(samples, data, JNI_ABORT);
    if (status != 0) {
        __android_log_print(ANDROID_LOG_ERROR, kTag, "whisper_full failed: %d", status);
        return env->NewStringUTF("");
    }
    std::string text;
    const int segments = whisper_full_n_segments(ctx);
    for (int i = 0; i < segments; ++i) {
        if (whisper_full_get_segment_no_speech_prob(ctx, i) >= kNoSpeechMax) continue;
        text += whisper_full_get_segment_text(ctx, i);
    }
    return env->NewStringUTF(text.c_str());
}

extern "C" JNIEXPORT void JNICALL
Java_io_github_noteoin_halecho_stt_Whisper_nativeFree(JNIEnv *, jclass, jlong handle) {
    whisper_free(reinterpret_cast<whisper_context *>(handle));
}

extern "C" JNIEXPORT jstring JNICALL
Java_io_github_noteoin_halecho_stt_Whisper_nativeSystemInfo(JNIEnv *env, jclass) {
    return env->NewStringUTF(whisper_print_system_info());
}
