/*
 * Plays HAL's voice as it arrives: PCM segments are queued and written to an AudioTrack by
 * one thread, so the link thread never blocks on the speaker. stop() drops the queue at once
 * (barge-in). The level of what is playing drives the eye.
 */
package io.github.noteoin.halecho.audio

import android.media.AudioAttributes
import android.media.AudioFormat
import android.media.AudioTrack
import io.github.noteoin.halecho.listen.Speaker
import java.util.concurrent.LinkedBlockingQueue
import java.util.concurrent.TimeUnit
import kotlin.math.sqrt

class Player(private val onLevel: (Float) -> Unit) : Speaker {
    private class Chunk(val sampleRate: Int, val pcm: ShortArray)

    private val queue = LinkedBlockingQueue<Chunk>()
    @Volatile private var writing = false
    @Volatile private var generation = 0
    private var track: AudioTrack? = null
    private var trackRate = 0
    private val thread = Thread(::run, "player").apply { isDaemon = true; start() }

    override val playing: Boolean
        get() = writing || queue.isNotEmpty()

    /** Queues one piece of a sentence. */
    fun enqueue(sampleRate: Int, pcm: ShortArray) {
        queue.put(Chunk(sampleRate, pcm))
    }

    override fun stop() {
        generation++
        queue.clear()
        track?.pause()
        track?.flush()
    }

    private fun run() {
        while (true) {
            val chunk = queue.poll(IDLE_POLL_MS, TimeUnit.MILLISECONDS)
            if (chunk == null) {
                if (writing) onLevel(0f)
                writing = false
                continue
            }
            writing = true
            val gen = generation
            val out = trackFor(chunk.sampleRate)
            out.play()
            var offset = 0
            val block = chunk.sampleRate / LEVEL_UPDATES_PER_S
            while (offset < chunk.pcm.size && gen == generation) {
                val n = minOf(block, chunk.pcm.size - offset)
                onLevel(rms(chunk.pcm, offset, n))
                out.write(chunk.pcm, offset, n)
                offset += n
            }
        }
    }

    private fun trackFor(rate: Int): AudioTrack {
        val current = track
        if (current != null && trackRate == rate) return current
        current?.release()
        val minBytes = AudioTrack.getMinBufferSize(rate, AudioFormat.CHANNEL_OUT_MONO, AudioFormat.ENCODING_PCM_16BIT)
        return AudioTrack.Builder()
            .setAudioAttributes(
                AudioAttributes.Builder()
                    .setUsage(AudioAttributes.USAGE_ASSISTANT)
                    .setContentType(AudioAttributes.CONTENT_TYPE_SPEECH)
                    .build(),
            )
            .setAudioFormat(
                AudioFormat.Builder()
                    .setSampleRate(rate)
                    .setChannelMask(AudioFormat.CHANNEL_OUT_MONO)
                    .setEncoding(AudioFormat.ENCODING_PCM_16BIT)
                    .build(),
            )
            .setBufferSizeInBytes(minBytes * BUFFER_MULTIPLE)
            .setTransferMode(AudioTrack.MODE_STREAM)
            .build()
            .also {
                track = it
                trackRate = rate
            }
    }

    private fun rms(pcm: ShortArray, offset: Int, n: Int): Float {
        var sum = 0.0
        for (i in offset until offset + n) sum += pcm[i].toDouble() * pcm[i]
        return (sqrt(sum / maxOf(1, n)) / FULL_SCALE * LEVEL_GAIN).toFloat().coerceIn(0f, 1f)
    }

    private companion object {
        const val IDLE_POLL_MS = 100L
        const val LEVEL_UPDATES_PER_S = 50 // 20 ms blocks, as hal-voice's player meters
        const val BUFFER_MULTIPLE = 4
        const val FULL_SCALE = 32768.0
        const val LEVEL_GAIN = 3.0 // hal-voice's eye uses the same gain on the RMS
    }
}
