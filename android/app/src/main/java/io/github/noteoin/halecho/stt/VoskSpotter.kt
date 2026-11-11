/*
 * The wake word spotter: Vosk's small English model restricted to a grammar of the wake
 * phrases, so it only ever decides between "Hal" and anything else. That keeps it cheap
 * enough to hear every frame while the room is awake; Whisper then hears the request.
 *
 * A partial result is reported as HEARD, once per utterance. The final result is reported as
 * CONFIRMED only when Vosk's confidence in the word "hal" reaches CONFIRM_CONF: with a grammar
 * this small, noise and HAL's own voice are forced onto "hal" too, but with lower confidence.
 */
package io.github.noteoin.halecho.stt

import io.github.noteoin.halecho.audio.SAMPLE_RATE
import io.github.noteoin.halecho.listen.Spotter
import io.github.noteoin.halecho.listen.Wake
import org.json.JSONArray
import org.json.JSONObject
import org.vosk.Model
import org.vosk.Recognizer
import java.io.File

class VoskSpotter(modelDir: File, phrases: List<String>) : Spotter, AutoCloseable {
    private val model = Model(modelDir.path)
    private val grammar = JSONArray(phrases + UNKNOWN).toString()
    private val recognizer = Recognizer(model, SAMPLE_RATE.toFloat(), grammar).apply { setWords(true) }
    private var heardThisUtterance = false

    override fun accept(frame: ShortArray): Wake {
        if (recognizer.acceptWaveForm(frame, frame.size)) {
            heardThisUtterance = false
            return if (confidence(JSONObject(recognizer.result)) >= CONFIRM_CONF) Wake.CONFIRMED else Wake.NONE
        }
        // Partial results repeat the same words frame after frame; report the first one only
        val partial = JSONObject(recognizer.partialResult).optString("partial")
        if (heardThisUtterance || partial.split(' ').none { it == NAME }) return Wake.NONE
        heardThisUtterance = true
        return Wake.HEARD
    }

    /** Vosk's highest confidence for the word "hal" in a final result, or 0. */
    private fun confidence(result: JSONObject): Double {
        val words = result.optJSONArray("result") ?: return 0.0
        return (0 until words.length())
            .map { words.getJSONObject(it) }
            .filter { it.optString("word") == NAME }
            .maxOfOrNull { it.optDouble("conf", 0.0) } ?: 0.0
    }

    override fun reset() {
        recognizer.reset()
        heardThisUtterance = false
    }

    override fun close() {
        recognizer.close()
        model.close()
    }

    private companion object {
        const val NAME = "hal"
        const val UNKNOWN = "[unk]"
        const val CONFIRM_CONF = 0.9
    }
}
