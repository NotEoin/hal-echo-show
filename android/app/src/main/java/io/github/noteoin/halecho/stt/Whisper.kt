/*
 * Speech to text on the device: whisper.cpp through whisper_jni.cpp. One native context is
 * loaded per model file and used by one thread at a time.
 */
package io.github.noteoin.halecho.stt

import io.github.noteoin.halecho.listen.Transcriber
import java.io.File

class Whisper(model: File, private val threads: Int, private val audioCtx: Int) : Transcriber, AutoCloseable {
    private var handle: Long = nativeInit(model.path)

    init {
        check(handle != 0L) { "whisper could not load ${model.name}" }
    }

    @Synchronized
    override fun transcribe(pcm: ShortArray): String {
        check(handle != 0L) { "whisper is closed" }
        val samples = FloatArray(pcm.size) { pcm[it] / PCM_FULL_SCALE }
        return nativeTranscribe(handle, samples, threads, audioCtx, null)
    }

    @Synchronized
    override fun close() {
        if (handle != 0L) nativeFree(handle)
        handle = 0L
    }

    companion object {
        private const val PCM_FULL_SCALE = 32768f

        init {
            System.loadLibrary("halecho_whisper")
        }

        /** whisper.cpp's build features (NEON, FP16), for the log. */
        fun systemInfo(): String = nativeSystemInfo()

        @JvmStatic private external fun nativeInit(modelPath: String): Long

        @JvmStatic private external fun nativeTranscribe(
            handle: Long, samples: FloatArray, threads: Int, audioCtx: Int, prompt: String?,
        ): String

        @JvmStatic private external fun nativeFree(handle: Long)

        @JvmStatic private external fun nativeSystemInfo(): String
    }
}
