/* The burn-in guards: the drift stays inside its border, and the screen dims only when unused. */
package io.github.noteoin.halecho

import io.github.noteoin.halecho.UiState.Eye
import io.github.noteoin.halecho.ui.BurnIn
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test
import kotlin.math.abs

class BurnInTest {
    @Test
    fun shiftStaysWithinTheBorderAndMoves() {
        val shifts = (0 until 16).map { BurnIn.shift(it * 60_000L) }
        assertTrue(shifts.all { abs(it) <= BurnIn.SHIFT_PX })
        assertTrue(shifts.toSet().size > 4)
    }

    @Test
    fun anAsleepRoomIsDimWhateverIsShown() {
        assertEquals(BurnIn.ASLEEP_BRIGHTNESS, BurnIn.brightness(Eye.ASLEEP, false, 0), 0f)
        assertEquals(BurnIn.ASLEEP_BRIGHTNESS, BurnIn.brightness(Eye.ASLEEP, true, 0), 0f)
    }

    @Test
    fun anUnusedTerminalScreenDims() {
        assertEquals(BurnIn.FULL_BRIGHTNESS, BurnIn.brightness(Eye.AWAKE, true, BurnIn.IDLE_SCREEN_MS - 1), 0f)
        assertEquals(BurnIn.IDLE_SCREEN_BRIGHTNESS, BurnIn.brightness(Eye.AWAKE, true, BurnIn.IDLE_SCREEN_MS), 0f)
    }

    @Test
    fun theEyeStaysBrightInAnAwakeRoom() {
        assertEquals(BurnIn.FULL_BRIGHTNESS, BurnIn.brightness(Eye.AWAKE, false, Long.MAX_VALUE), 0f)
    }

    @Test
    fun talkingWithHalCountsAsUse() {
        assertTrue(BurnIn.inConversation(Eye.LISTENING))
        assertTrue(BurnIn.inConversation(Eye.SPEAKING))
        assertFalse(BurnIn.inConversation(Eye.AWAKE))
    }
}
