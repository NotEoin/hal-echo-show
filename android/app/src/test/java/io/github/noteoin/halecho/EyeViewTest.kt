/* The eye's arithmetic: brightness per state and the anti-burn-in shift. */
package io.github.noteoin.halecho

import io.github.noteoin.halecho.UiState.Eye
import io.github.noteoin.halecho.ui.EyeView
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test
import kotlin.math.abs

class EyeViewTest {
    @Test
    fun mutedEyeIsDark() = assertEquals(0f, EyeView.intensity(Eye.MUTED, 0.0, 1f))

    @Test
    fun speakingFollowsTheVoice() =
        assertTrue(EyeView.intensity(Eye.SPEAKING, 0.0, 1f) > EyeView.intensity(Eye.SPEAKING, 0.0, 0f))

    @Test
    fun shiftStaysWithinSixPixelsAndMoves() {
        val shifts = (0 until 16).map { EyeView.burnInShift(it * 60_000L) }
        assertTrue(shifts.all { abs(it) <= 6f })
        assertTrue(shifts.toSet().size > 4)
    }
}
