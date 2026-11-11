/*
 * Guards against image retention: a fixed image can stay on this panel (the LineageOS thread
 * reports retention), so whatever is on screen drifts a few pixels each minute and the screen
 * dims when no one is using it. The eye and the terminal screens share these rules.
 */
package io.github.noteoin.halecho.ui

import android.view.WindowManager
import io.github.noteoin.halecho.UiState
import kotlin.math.PI
import kotlin.math.sin

object BurnIn {
    /** The largest drift in each direction; a view that must not be clipped keeps this margin. */
    const val SHIFT_PX = 6f
    private const val SHIFT_PERIOD_MIN = 16

    /** The room is asleep: no one is there to see the eye. */
    const val ASLEEP_BRIGHTNESS = 0.05f

    /** A terminal screen no one has touched or talked over: dim, but still readable across a room. */
    const val IDLE_SCREEN_BRIGHTNESS = 0.2f

    /** How long a terminal screen stays at full brightness after the last touch or conversation. */
    const val IDLE_SCREEN_MS = 2 * 60_000L

    /** The system's own brightness. */
    const val FULL_BRIGHTNESS = WindowManager.LayoutParams.BRIGHTNESS_OVERRIDE_NONE

    /** A small offset that changes once a minute and repeats every 16 minutes. */
    fun shift(nowMs: Long): Float {
        val minute = (nowMs / 60_000L % SHIFT_PERIOD_MIN).toDouble()
        return (SHIFT_PX * sin(minute / SHIFT_PERIOD_MIN * 2 * PI)).toFloat()
    }

    /** True while someone is talking with Hal, which counts as using the screen. */
    fun inConversation(eye: UiState.Eye): Boolean =
        eye == UiState.Eye.LISTENING || eye == UiState.Eye.THINKING || eye == UiState.Eye.SPEAKING

    /** The window brightness for what is on screen and how long it has gone unused. */
    fun brightness(eye: UiState.Eye, screenShown: Boolean, idleMs: Long): Float = when {
        eye == UiState.Eye.ASLEEP -> ASLEEP_BRIGHTNESS
        screenShown && idleMs >= IDLE_SCREEN_MS -> IDLE_SCREEN_BRIGHTNESS
        else -> FULL_BRIGHTNESS
    }
}
