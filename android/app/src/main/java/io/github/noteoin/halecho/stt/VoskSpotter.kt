/*
 * The wake word spotter: Vosk's small English model restricted to a grammar of the wake
 * phrases, so it only ever decides between "Hal" and anything else. That keeps it cheap
 * enough to hear every frame while the room is awake; Whisper then hears the request.
 */
package io.github.noteoin.halecho.stt

import io.github.noteoin.halecho.audio.SAMPLE_RATE
import io.github.noteoin.halecho.listen.Spotter
import org.json.JSONArray
import org.json.JSONObject
import org.vosk.Model
import org.vosk.Recognizer
import java.io.File

class VoskSpotter(modelDir: File, phrases: List<String>) : Spotter, AutoCloseable {
    private val model = Model(modelDir.path)
    private val grammar = JSONArray(phrases + UNKNOWN).toString()
    private var recognizer = Recognizer(model, SAMPLE_RATE.toFloat(), grammar)
    private var firedThisUtterance = false

    override fun accept(frame: ShortArray): Boolean {
        val final = recognizer.acceptWaveForm(frame, frame.size)
        val text = if (final) {
            JSONObject(recognizer.result).optString("text")
        } else {
            JSONObject(recognizer.partialResult).optString("partial")
        }
        // Partial results repeat the same words frame after frame; fire once per utterance
        val heard = !firedThisUtterance && text.split(' ').any { it == NAME }
        if (heard) firedThisUtterance = true
        if (final) firedThisUtterance = false
        return heard
    }

    override fun reset() {
        recognizer.reset()
        firedThisUtterance = false
    }

    override fun close() {
        recognizer.close()
        model.close()
    }

    private companion object {
        const val NAME = "hal"
        const val UNKNOWN = "[unk]"
    }
}
