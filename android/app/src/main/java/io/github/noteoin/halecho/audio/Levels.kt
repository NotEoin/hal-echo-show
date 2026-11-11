/*
 * Cheap per-frame sound measures: loudness, an adaptive noise floor, and the privacy mute.
 * These run on every 20 ms frame, idle or not, so they are plain arithmetic.
 */
package io.github.noteoin.halecho.audio

import kotlin.math.log10
import kotlin.math.max
import kotlin.math.sqrt

/** 20 ms of 16 kHz mono: the unit every listener stage works in. */
const val SAMPLE_RATE = 16_000
const val FRAME_SAMPLES = 320
const val FRAME_MS = 20L

private const val PCM_FULL_SCALE = 32768.0
private const val MUTE_FRAMES = 75 // 1.5 s of exact zeros
private const val SILENCE_DB = -100.0

/** Root-mean-square level of a frame in dBFS; -100 for digital silence. */
fun levelDb(frame: ShortArray): Double {
    if (frame.isEmpty()) return SILENCE_DB
    var sum = 0.0
    for (s in frame) sum += s.toDouble() * s
    val rms = sqrt(sum / frame.size) / PCM_FULL_SCALE
    return if (rms <= 0.0) SILENCE_DB else max(SILENCE_DB, 20 * log10(rms))
}

/**
 * Tracks the room's background level and says which frames stand out from it.
 *
 * The floor falls to a quieter frame at once and rises slowly, so a voice does not raise it
 * but a fan that starts does. A frame is sound when it is [marginDb] above the floor: the
 * same idea as hal-voice's `audio.vad_margin_db`, which a PC's fan hum made necessary.
 */
class NoiseFloor(
    private val marginDb: Double = 8.0,
    private val riseDbPerFrame: Double = 0.02,
    initialDb: Double = -60.0,
) {
    var floorDb: Double = initialDb
        private set

    /** Updates the floor with [db] and returns true when the frame is sound, not background. */
    fun isSound(db: Double): Boolean {
        floorDb = if (db < floorDb) db else floorDb + riseDbPerFrame
        return db > floorDb + marginDb
    }
}

/**
 * Notices the hardware privacy mute. When the mute button cuts the microphones the frames
 * come back as exact zeros, which a real room never produces for long.
 */
class MuteDetector(private val framesToMute: Int = MUTE_FRAMES) {
    private var silentFrames = 0

    var muted: Boolean = false
        private set

    /** Updates the state with one frame; returns true when the state changed. */
    fun update(frame: ShortArray): Boolean {
        val digitalSilence = frame.all { it.toInt() in -1..1 }
        silentFrames = if (digitalSilence) silentFrames + 1 else 0
        val now = silentFrames >= framesToMute
        if (now == muted) return false
        muted = now
        return true
    }
}
