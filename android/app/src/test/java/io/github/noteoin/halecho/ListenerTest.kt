/* The listener's flows, with fakes for the spotter, Whisper, the link and the speaker. */
package io.github.noteoin.halecho

import io.github.noteoin.halecho.audio.FRAME_MS
import io.github.noteoin.halecho.audio.FRAME_SAMPLES
import io.github.noteoin.halecho.listen.Listener
import io.github.noteoin.halecho.listen.ListenerSettings
import io.github.noteoin.halecho.listen.ListenerUi
import io.github.noteoin.halecho.listen.Outbox
import io.github.noteoin.halecho.listen.Speaker
import io.github.noteoin.halecho.listen.Spotter
import io.github.noteoin.halecho.listen.Wake
import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test

class ListenerTest {
    private var now = 0L
    private var wakeOnNextSound = false
    private var wakeKind = Wake.HEARD
    private var wakeOnNextQuiet = false
    private var spotterFrames = 0
    private val sent = mutableListOf<JSONObject>()
    private var playing = false
    private var stopped = false
    private var awakeShown: Boolean? = null
    private lateinit var listener: Listener

    private val loud = ShortArray(FRAME_SAMPLES) { if (it % 2 == 0) 8000 else -8000 }
    private val quiet = ShortArray(FRAME_SAMPLES) { if (it % 2 == 0) 20 else -20 }

    @Before
    fun setUp() {
        val spotter = object : Spotter {
            override fun accept(frame: ShortArray): Wake {
                spotterFrames++
                if (wakeOnNextQuiet && frame === quiet) {
                    wakeOnNextQuiet = false
                    return wakeKind
                }
                val fire = wakeOnNextSound && frame === loud
                if (fire) wakeOnNextSound = false
                return if (fire) wakeKind else Wake.NONE
            }
            override fun reset() = Unit
        }
        val outbox = object : Outbox {
            override val connected = true
            override fun send(msg: JSONObject) { sent.add(msg) }
            override fun sendAudio(turn: Long, pcm: ShortArray) = Unit
        }
        val speaker = object : Speaker {
            override val playing get() = this@ListenerTest.playing
            override fun stop() {
                stopped = true
                this@ListenerTest.playing = false
            }
        }
        val ui = object : ListenerUi {
            override fun roomAwake(awake: Boolean) { awakeShown = awake }
            override fun muted(muted: Boolean) = Unit
            override fun listening(active: Boolean) = Unit
            override fun heard(text: String) = Unit
            override fun level(db: Double) = Unit
        }
        listener = Listener(spotter, { "Hal, what time is it" }, outbox, speaker, ui, { it.run() }) { now }
        listener.configure(ListenerSettings(awakeMs = 10_000, followupMs = 4_000))
    }

    private fun feed(frame: ShortArray, count: Int) = repeat(count) {
        listener.onFrame(frame)
        now += FRAME_MS
    }

    private fun types() = sent.map { it.getString("type") }.filter { it != "state" }

    private fun settle() = feed(quiet, 100)

    @Test
    fun roomFallsAsleepAfterQuietAndStopsSpotting() {
        settle()
        feed(loud, 5)
        assertEquals(true, awakeShown)
        feed(quiet, 600) // 12 s of quiet against a 10 s awake time
        assertEquals(false, awakeShown)
        val before = spotterFrames
        feed(quiet, 50)
        assertEquals(before, spotterFrames)
    }

    @Test
    fun speechWithoutTheWakeWordIsNotSent() {
        settle()
        feed(loud, 40)
        feed(quiet, 40)
        assertEquals(emptyList<String>(), types())
    }

    @Test
    fun wakeWordSendsWakeThenTheUtteranceOnceGranted() {
        settle()
        wakeOnNextSound = true
        feed(loud, 10)
        assertEquals("wake", types().single())
        val turn = sent.last().getLong("turn")
        listener.onMessage(JSONObject().put("type", "floor").put("turn", turn).put("granted", true))
        feed(loud, 30)
        feed(quiet, 40)
        val utterance = sent.last()
        assertEquals("utterance", utterance.getString("type"))
        assertEquals(turn, utterance.getLong("turn"))
        assertFalse(utterance.getBoolean("followup"))
    }

    @Test
    fun deniedFloorDropsTheUtterance() {
        settle()
        wakeOnNextSound = true
        feed(loud, 10)
        val turn = sent.last().getLong("turn")
        listener.onMessage(JSONObject().put("type", "floor").put("turn", turn).put("granted", false))
        feed(loud, 30)
        feed(quiet, 40)
        assertEquals(listOf("wake"), types())
    }

    @Test
    fun followUpAfterAReplyNeedsNoWakeWord() {
        settle()
        listener.onMessage(JSONObject().put("type", "say").put("turn", 1))
        listener.onMessage(JSONObject().put("type", "turn_end").put("turn", 1).put("finished", true))
        feed(quiet, 5) // playback has drained: the follow-up window opens
        feed(loud, 30)
        feed(quiet, 40)
        val msg = sent.last()
        assertEquals("utterance", msg.getString("type"))
        assertTrue(msg.getBoolean("followup"))
    }

    @Test
    fun confirmedWakeWordWhileSpeakingStopsHal() {
        settle()
        listener.onMessage(JSONObject().put("type", "say").put("turn", 3))
        playing = true
        wakeKind = Wake.CONFIRMED
        wakeOnNextSound = true
        feed(loud, 5)
        assertTrue(stopped)
        assertTrue(types().containsAll(listOf("barge_in", "wake")))
        assertEquals(3L, sent.first { it.getString("type") == "barge_in" }.getLong("turn"))
    }

    /** Regression: HAL's own voice, heard as a partial "Hal", cut his weather reply short. */
    @Test
    fun partialWakeWordWhileSpeakingDoesNotStopHal() {
        settle()
        listener.onMessage(JSONObject().put("type", "say").put("turn", 8))
        playing = true
        wakeOnNextSound = true
        feed(loud, 30)
        assertFalse(stopped)
        assertEquals(emptyList<String>(), types())
    }

    @Test
    fun wakeAfterTheUtteranceEndedOpensNoTurn() {
        settle()
        wakeOnNextQuiet = true
        wakeKind = Wake.CONFIRMED
        feed(quiet, 5)
        assertEquals(emptyList<String>(), types())
        wakeKind = Wake.HEARD
        wakeOnNextSound = true
        feed(loud, 5)
        assertEquals("wake", types().single()) // a stale turn does not block the next wake
    }

    @Test
    fun ownVoiceWithoutTheWakeWordIsIgnored() {
        settle()
        listener.onMessage(JSONObject().put("type", "say").put("turn", 4))
        listener.onMessage(JSONObject().put("type", "turn_end").put("turn", 4).put("finished", true))
        playing = true
        feed(loud, 30) // HAL's voice reaching the microphones
        playing = false
        feed(quiet, 40)
        assertEquals(emptyList<String>(), types())
    }

    @Test
    fun approvalAnswerGoesBackAsAnApproval() {
        settle()
        listener.onMessage(JSONObject().put("type", "listen").put("turn", 5).put("purpose", "approval").put("timeout_s", 20))
        feed(loud, 20)
        feed(quiet, 40)
        val msg = sent.last()
        assertEquals("approval", msg.getString("type"))
        assertEquals(5L, msg.getLong("turn"))
    }

    @Test
    fun silenceAfterAnApprovalRequestAnswersEmpty() {
        settle()
        listener.onMessage(JSONObject().put("type", "listen").put("turn", 6).put("purpose", "approval").put("timeout_s", 1))
        feed(quiet, 900) // past the 1 s limit plus the time allowed for the question
        val msg = sent.last { it.getString("type") == "approval" }
        assertEquals("", msg.getString("text"))
    }
}
