/* The eye's arithmetic: brightness per state, easing and captions. */
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

    /** Regression: the resting lens pulsed every four seconds; it should breathe slowly. */
    @Test
    fun restingLensBreathesOnceEveryEightSeconds() {
        val period = EyeView.BREATH_PERIOD_S
        assertEquals(8.0, period, 0.0)
        for (t in listOf(0.0, 1.3, 5.7)) {
            assertEquals(EyeView.intensity(Eye.AWAKE, t, 0f), EyeView.intensity(Eye.AWAKE, t + period, 0f), 1e-5f)
        }
        val steps = (0 until 160).map { EyeView.intensity(Eye.AWAKE, it * 0.05, 0f) }
        assertTrue(steps.zipWithNext().all { (a, b) -> abs(b - a) < 0.01f })
        assertTrue(steps.max() - steps.min() > 0.1f)
    }

    @Test
    fun briefWakeDoesNotFlashTheLens() {
        // 150 ms of "listening" from a wake the PC rejects moves the lens less than a fifth of the way
        var k = 0.3f
        repeat(9) { k = EyeView.ease(k, 1f, 16, speaking = false) }
        assertTrue(k < 0.3f + 0.2f * 0.7f)
    }

    @Test
    fun speakingTracksTheVoiceQuickly() {
        val k = EyeView.ease(0.3f, 1f, 100, speaking = true)
        assertTrue(k > 0.8f)
    }

    @Test
    fun captionHoldsThenFades() {
        assertEquals(200, EyeView.captionAlpha(1000))
        assertTrue(EyeView.captionAlpha(7000) in 1 until 200)
        assertEquals(0, EyeView.captionAlpha(9000))
    }
}
