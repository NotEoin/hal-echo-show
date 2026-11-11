/*
 * Cuts the microphone stream into utterances: from the first sound frame (with a little audio
 * from before it, so a quiet first syllable survives) to a pause of `endSilenceFrames`, or
 * `maxFrames` at most. The same shape as hal-voice's hands-free segmenter.
 */
package io.github.noteoin.halecho.listen

import io.github.noteoin.halecho.audio.FRAME_SAMPLES

class Segmenter(
    private val preRollFrames: Int = 30, // 600 ms, hal-voice's activation.keyword.pre_roll_ms
    private val endSilenceFrames: Int = 30, // 600 ms, its end_silence_ms
    private val maxFrames: Int = 1500, // 30 s, its audio.max_utterance_s
) {
    private val preRoll = ArrayDeque<ShortArray>()
    private val frames = ArrayList<ShortArray>()
    private var silent = 0

    /** True while an utterance is being collected. */
    val inSpeech: Boolean get() = frames.isNotEmpty()

    /** Adds one frame; returns the finished utterance, if this frame ended one. */
    fun feed(frame: ShortArray, sound: Boolean): ShortArray? {
        if (frames.isEmpty()) {
            if (!sound) {
                preRoll.addLast(frame)
                if (preRoll.size > preRollFrames) preRoll.removeFirst()
                return null
            }
            frames.addAll(preRoll)
            preRoll.clear()
        }
        frames.add(frame)
        silent = if (sound) 0 else silent + 1
        if (silent < endSilenceFrames && frames.size < maxFrames) return null
        val out = ShortArray(frames.size * FRAME_SAMPLES)
        frames.forEachIndexed { i, f -> f.copyInto(out, i * FRAME_SAMPLES) }
        reset()
        return out
    }

    /** Drops whatever is being collected. */
    fun reset() {
        frames.clear()
        preRoll.clear()
        silent = 0
    }
}
