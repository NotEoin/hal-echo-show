/*
 * The microphone: 16 kHz mono frames of 20 ms, delivered on one thread. The voice
 * recognition source skips the call-audio processing that would dull a far voice, and the
 * platform echo canceller is attached when the device offers one, so HAL hears less of itself.
 */
package io.github.noteoin.halecho.audio

import android.annotation.SuppressLint
import android.media.AudioFormat
import android.media.AudioRecord
import android.media.MediaRecorder
import android.media.audiofx.AcousticEchoCanceler
import android.util.Log

class Capture(private val onFrame: (ShortArray) -> Unit) {
    @Volatile private var running = false
    private var thread: Thread? = null

    // RECORD_AUDIO is granted at setup (adb pm grant) or by the prompt in HomeActivity
    @SuppressLint("MissingPermission")
    fun start() {
        if (running) return
        running = true
        thread = Thread({
            val minBytes = AudioRecord.getMinBufferSize(SAMPLE_RATE, AudioFormat.CHANNEL_IN_MONO, AudioFormat.ENCODING_PCM_16BIT)
            val record = AudioRecord(
                MediaRecorder.AudioSource.VOICE_RECOGNITION,
                SAMPLE_RATE,
                AudioFormat.CHANNEL_IN_MONO,
                AudioFormat.ENCODING_PCM_16BIT,
                maxOf(minBytes, FRAME_SAMPLES * 2 * BUFFER_FRAMES),
            )
            val echo = if (AcousticEchoCanceler.isAvailable()) AcousticEchoCanceler.create(record.audioSessionId) else null
            echo?.enabled = true
            Log.i(TAG, "capture started; echo canceller ${if (echo != null) "on" else "unavailable"}")
            record.startRecording()
            try {
                while (running) {
                    val frame = ShortArray(FRAME_SAMPLES)
                    var filled = 0
                    while (filled < FRAME_SAMPLES && running) {
                        val n = record.read(frame, filled, FRAME_SAMPLES - filled)
                        if (n < 0) throw IllegalStateException("AudioRecord.read failed: $n")
                        filled += n
                    }
                    if (running) onFrame(frame)
                }
            } finally {
                record.stop()
                echo?.release()
                record.release()
            }
        }, "capture").apply { start() }
    }

    fun stop() {
        running = false
        thread?.join(JOIN_TIMEOUT_MS)
        thread = null
    }

    private companion object {
        const val TAG = "halecho-capture"
        const val BUFFER_FRAMES = 25 // half a second of slack if the listener falls behind
        const val JOIN_TIMEOUT_MS = 2000L
    }
}
