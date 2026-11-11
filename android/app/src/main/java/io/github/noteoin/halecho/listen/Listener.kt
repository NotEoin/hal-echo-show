/*
 * The device's half of a conversation: everything between the microphone and the link.
 *
 * Every 20 ms frame is measured (muted? sound?). While the room is asleep that is all. While
 * it is awake the wake word spotter hears every frame and the segmenter cuts utterances.
 * An utterance is transcribed only when it is for Hal:
 *
 * - it contains the wake word (after the PC grants this device the floor);
 * - it starts in the follow-up window after a reply, or after a bare "Hal";
 * - it is the answer to a spoken approval request.
 *
 * Everything else is dropped unheard. An utterance that starts while HAL is speaking is his
 * own voice coming back, unless it holds the wake word, which stops him (barge-in). With no echo
 * canceller on this ROM, HAL's voice can sound like "Hal" to the spotter, so stopping him needs a
 * confirmed wake, not a partial one.
 * Transcription runs on [worker] so capture never stalls. The PC's messages arrive through
 * [onMessage] from the link thread; [lock] keeps the two threads' views consistent.
 */
package io.github.noteoin.halecho.listen

import io.github.noteoin.halecho.audio.FRAME_MS
import io.github.noteoin.halecho.audio.MuteDetector
import io.github.noteoin.halecho.audio.NoiseFloor
import io.github.noteoin.halecho.audio.levelDb
import org.json.JSONObject
import java.util.concurrent.Executor
import java.util.concurrent.TimeUnit

/** What the spotter made of one frame. */
enum class Wake {
    NONE,

    /** A partial result names Hal: quick, and good enough when HAL is silent. */
    HEARD,

    /** A final result names Hal with high confidence: needed to stop HAL mid-reply. */
    CONFIRMED,
}

/** Hears the wake word in a stream of frames. */
interface Spotter {
    /** Whether the wake word was heard in this frame. */
    fun accept(frame: ShortArray): Wake

    fun reset()
}

/** Turns an utterance into text. */
fun interface Transcriber {
    fun transcribe(pcm: ShortArray): String
}

/** The link to the PC, as the listener uses it. */
interface Outbox {
    val connected: Boolean

    fun send(msg: JSONObject)

    fun sendAudio(turn: Long, pcm: ShortArray)
}

/** What the listener needs from playback. */
interface Speaker {
    val playing: Boolean

    fun stop()
}

/** What the listener shows; the eye reads these. */
interface ListenerUi {
    fun roomAwake(awake: Boolean)

    fun muted(muted: Boolean)

    fun listening(active: Boolean)

    fun heard(text: String)

    fun level(db: Double)
}

/** The listening settings the PC sends in `welcome`. */
data class ListenerSettings(
    val awakeMs: Long = TimeUnit.MINUTES.toMillis(5),
    val followupMs: Long = TimeUnit.SECONDS.toMillis(8),
    val sttOnDevice: Boolean = true,
) {
    companion object {
        /** Reads the `listener` object of a `welcome` message. */
        fun from(json: JSONObject?): ListenerSettings {
            json ?: return ListenerSettings()
            return ListenerSettings(
                awakeMs = (json.optDouble("awake_s", 300.0) * 1000).toLong(),
                followupMs = (json.optDouble("followup_s", 8.0) * 1000).toLong(),
                sttOnDevice = json.optString("stt_location", "device") != "pc",
            )
        }
    }
}

class Listener(
    private val spotter: Spotter,
    private val transcriber: Transcriber,
    private val outbox: Outbox,
    private val speaker: Speaker,
    private val ui: ListenerUi,
    private val worker: Executor,
    private val clock: () -> Long = System::currentTimeMillis,
) {
    private val lock = Any()
    private val floor = NoiseFloor()
    private val mute = MuteDetector()
    private val segmenter = Segmenter()
    private var settings = ListenerSettings()
    private var room = RoomState(settings.awakeMs)

    private var nextTurn = 0L
    private var wakeTurn: Long? = null
    private var wakeInUtterance = false
    private var utteranceStartedWhileSpeaking = false
    private var awaiting: Awaiting? = null
    private var activeTurn: Long? = null
    private var turnEnded = false
    private var followUntil = 0L
    private val floorDecisions = HashMap<Long, Boolean>()

    /** A request the PC is waiting for: the words after a bare "Hal", or an approval. */
    private data class Awaiting(val turn: Long, val approval: Boolean, val deadline: Long)

    /** Applies the PC's settings; called on every `welcome`. */
    fun configure(newSettings: ListenerSettings) = synchronized(lock) {
        settings = newSettings
        room = RoomState(newSettings.awakeMs)
    }

    /** Handles one microphone frame, on the capture thread. */
    fun onFrame(frame: ShortArray) {
        val db = levelDb(frame)
        ui.level(db)
        if (mute.update(frame)) {
            ui.muted(mute.muted)
            sendState()
        }
        if (mute.muted) return
        synchronized(lock) { onSound(frame, db) }
    }

    private fun onSound(frame: ShortArray, db: Double) {
        val now = clock()
        val sound = floor.isSound(db)
        if (room.onFrame(now, sound || activeTurn != null || awaiting != null)) {
            ui.roomAwake(room.awake)
            if (!room.awake) {
                spotter.reset()
                segmenter.reset()
            }
            sendState()
        }
        if (!room.awake) return
        finishTurnIfDrained(now)
        expireAwaiting(now)
        if (!segmenter.inSpeech && sound) {
            utteranceStartedWhileSpeaking = speaker.playing
            wakeInUtterance = false
        }
        when (spotter.accept(frame)) {
            Wake.HEARD -> onWake(db, sound, confirmed = false)
            Wake.CONFIRMED -> onWake(db, sound, confirmed = true)
            Wake.NONE -> Unit
        }
        val utterance = segmenter.feed(frame, sound) ?: return
        val startedWhileSpeaking = utteranceStartedWhileSpeaking
        val hadWake = wakeInUtterance
        wakeInUtterance = false
        ui.listening(false)
        route(utterance, now, startedWhileSpeaking && !hadWake)
    }

    private fun onWake(db: Double, sound: Boolean, confirmed: Boolean) {
        val playing = speaker.playing
        if (playing && !confirmed) return // most likely HAL's own voice
        val active = activeTurn
        if (active != null && playing) {
            speaker.stop() // barge-in: the rest of this utterance becomes the new request
            outbox.send(JSONObject().put("type", "barge_in").put("turn", active))
        }
        // A final result can land after the utterance has ended; it opens no turn of its own
        if (!segmenter.inSpeech && !sound) return
        wakeInUtterance = true
        if (wakeTurn != null || !outbox.connected) return
        val turn = ++nextTurn
        wakeTurn = turn
        ui.listening(true)
        // Louder means nearer: the PC gives the floor to the device nearest the speaker
        val score = ((db - floor.floorDb) / SCORE_RANGE_DB).coerceIn(0.0, 1.0)
        outbox.send(JSONObject().put("type", "wake").put("turn", turn).put("score", score))
    }

    private fun route(utterance: ShortArray, now: Long, echo: Boolean) {
        val waiting = awaiting
        val wake = wakeTurn
        when {
            echo -> Unit
            waiting != null -> {
                awaiting = null
                if (waiting.approval) {
                    transcribeThen(waiting.turn, utterance, approval = true, followup = false)
                } else {
                    transcribeThen(waiting.turn, utterance, approval = false, followup = true)
                }
            }
            wake != null -> {
                wakeTurn = null
                worker.execute { afterFloor(wake, utterance) }
            }
            now < followUntil && activeTurn == null -> {
                followUntil = 0L
                transcribeThen(++nextTurn, utterance, approval = false, followup = true)
            }
        }
    }

    /** Waits for the PC's floor decision, then sends the utterance if this device won. */
    private fun afterFloor(turn: Long, utterance: ShortArray) {
        val deadline = clock() + FLOOR_WAIT_MS
        var granted: Boolean? = null
        while (granted == null && clock() < deadline) {
            granted = synchronized(lock) { floorDecisions.remove(turn) }
            if (granted == null) Thread.sleep(FLOOR_POLL_MS)
        }
        if (granted == true) deliver(turn, utterance, approval = false, followup = false)
    }

    private fun transcribeThen(turn: Long, utterance: ShortArray, approval: Boolean, followup: Boolean) {
        worker.execute { deliver(turn, utterance, approval, followup) }
    }

    private fun deliver(turn: Long, utterance: ShortArray, approval: Boolean, followup: Boolean) {
        if (!settings.sttOnDevice) {
            outbox.send(JSONObject().put("type", "utterance_audio").put("turn", turn))
            outbox.sendAudio(turn, utterance)
            outbox.send(JSONObject().put("type", "utterance_audio_end").put("turn", turn).put("followup", followup))
            return
        }
        val text = transcriber.transcribe(utterance).trim()
        ui.heard(text)
        if (approval) {
            outbox.send(JSONObject().put("type", "approval").put("turn", turn).put("text", text))
        } else if (text.isNotEmpty()) {
            outbox.send(
                JSONObject().put("type", "utterance").put("turn", turn).put("text", text).put("followup", followup),
            )
        }
    }

    /** Handles a message from the PC, on the link thread. */
    fun onMessage(msg: JSONObject) = synchronized(lock) {
        val turn = msg.optLong("turn")
        when (msg.getString("type")) {
            "floor" -> {
                floorDecisions[turn] = msg.optBoolean("granted")
                if (!msg.optBoolean("granted") && wakeTurn == turn) wakeTurn = null
            }
            "state" -> if (msg.optString("state") == "thinking") activeTurn = turn.takeIf { it != 0L } ?: -1L
            "say" -> {
                activeTurn = turn
                turnEnded = false
            }
            "listen" -> {
                val approval = msg.optString("purpose") == "approval"
                val waitMs = if (approval) (msg.optDouble("timeout_s", APPROVAL_DEFAULT_S) * 1000).toLong() else settings.followupMs
                awaiting = Awaiting(turn, approval, clock() + waitMs + if (approval) SPEECH_GRACE_MS else 0)
                ui.listening(true)
            }
            "turn_end" -> {
                turnEnded = true
                if (msg.optBoolean("finished", false)) followUntil = Long.MAX_VALUE // set when playback drains
                if (activeTurn == null) activeTurn = turn
            }
        }
    }

    /** Clears the in-flight turn when the link drops, so the next one starts clean. */
    fun onDisconnected() = synchronized(lock) {
        activeTurn = null
        awaiting = null
        wakeTurn = null
        floorDecisions.clear()
        ui.listening(false)
    }

    private fun finishTurnIfDrained(now: Long) {
        if (activeTurn == null || !turnEnded || speaker.playing) return
        activeTurn = null
        turnEnded = false
        if (followUntil == Long.MAX_VALUE) followUntil = now + settings.followupMs
    }

    private fun expireAwaiting(now: Long) {
        val waiting = awaiting ?: return
        if (now < waiting.deadline || segmenter.inSpeech) return
        awaiting = null
        ui.listening(false)
        if (waiting.approval) {
            outbox.send(JSONObject().put("type", "approval").put("turn", waiting.turn).put("text", ""))
        }
    }

    private fun sendState() {
        if (!outbox.connected) return
        outbox.send(JSONObject().put("type", "state").put("muted", mute.muted).put("awake", room.awake))
    }

    /** True while a turn is in progress or the PC is waiting for words. */
    val busy: Boolean get() = synchronized(lock) { activeTurn != null || awaiting != null }

    companion object {
        private const val SCORE_RANGE_DB = 40.0 // a voice 40 dB over the room scores 1
        private const val FLOOR_WAIT_MS = 3000L // the PC decides within floor.window_ms; this covers the link
        private const val FLOOR_POLL_MS = FRAME_MS
        private const val APPROVAL_DEFAULT_S = 20.0

        // The approval clock starts while the question is still being spoken
        private const val SPEECH_GRACE_MS = 15_000L
    }
}
