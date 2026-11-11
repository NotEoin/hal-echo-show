/*
 * The red lens, after hal-voice's ui_eye.py: brightness follows what Hal is doing and, while it
 * speaks, the level of its voice. When the room is asleep it shows a dim clock with a small
 * lens. The whole picture moves a few pixels each minute, because a fixed image can stay on
 * this panel (the LineageOS thread reports retention).
 */
package io.github.noteoin.halecho.ui

import android.content.Context
import android.graphics.Canvas
import android.graphics.Color
import android.graphics.Paint
import android.graphics.RadialGradient
import android.graphics.Shader
import android.graphics.Typeface
import android.view.View
import io.github.noteoin.halecho.R
import io.github.noteoin.halecho.UiState
import io.github.noteoin.halecho.UiState.Eye
import java.text.DateFormat
import java.util.Date
import kotlin.math.PI
import kotlin.math.min
import kotlin.math.sin

class EyeView(context: Context) : View(context) {
    private val ring = Paint(Paint.ANTI_ALIAS_FLAG).apply { style = Paint.Style.STROKE }
    private val lens = Paint(Paint.ANTI_ALIAS_FLAG)
    private val text = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        color = Color.rgb(170, 170, 170)
        textAlign = Paint.Align.CENTER
        typeface = Typeface.create(Typeface.SANS_SERIF, Typeface.NORMAL)
    }
    private val clock = DateFormat.getTimeInstance(DateFormat.SHORT)
    private val date = Date()
    private var smoothed = 0f
    private var shaderKey = ""

    init {
        setBackgroundColor(Color.BLACK)
    }

    override fun onDraw(canvas: Canvas) {
        super.onDraw(canvas)
        val now = System.currentTimeMillis()
        val eye = UiState.eye
        val shift = burnInShift(now)
        val asleep = eye == Eye.ASLEEP
        val cx = width / 2f + shift
        val cy = (if (asleep) height * SLEEP_EYE_Y else height * EYE_Y) + shift
        val radius = min(width, height) * (if (asleep) SLEEP_RADIUS else RADIUS)
        val target = intensity(eye, now / 1000.0, UiState.level)
        smoothed += (target - smoothed) * SMOOTHING
        drawLens(canvas, cx, cy, radius, smoothed)
        if (asleep) {
            text.textSize = height * CLOCK_TEXT
            text.alpha = CLOCK_ALPHA
            date.time = now
            canvas.drawText(clock.format(date), cx, height * CLOCK_Y + shift, text)
        } else {
            text.alpha = TEXT_ALPHA
            text.textSize = height * CAPTION_TEXT
            canvas.drawText(caption(eye), width / 2f, height * CAPTION_Y, text)
            text.textSize = height * STATUS_TEXT
            canvas.drawText(UiState.status, width / 2f, height * STATUS_Y, text)
        }
        postInvalidateOnAnimation()
    }

    private fun drawLens(canvas: Canvas, cx: Float, cy: Float, radius: Float, glow: Float) {
        ring.strokeWidth = radius * RING_WIDTH
        ring.color = Color.rgb(120, 120, 128)
        canvas.drawCircle(cx, cy, radius, ring)
        // The gradient changes only when the lens moves (each minute) or changes size
        val key = "$cx/$cy/$radius"
        if (key != shaderKey) {
            shaderKey = key
            lens.shader = RadialGradient(
                cx, cy, radius * LENS_RADIUS,
                intArrayOf(Color.rgb(255, 216, 102), Color.rgb(MAX_RED, 0, 0), Color.BLACK),
                floatArrayOf(0f, CORE, 1f),
                Shader.TileMode.CLAMP,
            )
        }
        lens.alpha = (ALPHA_FLOOR + (255 - ALPHA_FLOOR) * glow).toInt().coerceIn(0, 255)
        canvas.drawCircle(cx, cy, radius * LENS_RADIUS, lens)
    }

    private fun caption(eye: Eye): String = when (eye) {
        Eye.UNPAIRED -> context.getString(R.string.caption_unpaired)
        Eye.MUTED -> context.getString(R.string.caption_muted)
        Eye.OFFLINE -> context.getString(R.string.caption_offline)
        Eye.LOADING -> context.getString(R.string.caption_loading)
        else -> UiState.caption
    }

    // The home screen's hold gesture calls this on release, for accessibility services
    override fun performClick(): Boolean = super.performClick()

    companion object {
        private const val RADIUS = 0.34f
        private const val SLEEP_RADIUS = 0.12f
        private const val EYE_Y = 0.44f
        private const val SLEEP_EYE_Y = 0.72f
        private const val LENS_RADIUS = 0.86f
        private const val RING_WIDTH = 0.08f
        private const val CORE = 0.18f
        private const val MAX_RED = 255
        private const val ALPHA_FLOOR = 40
        private const val SMOOTHING = 0.2f
        private const val CLOCK_Y = 0.42f
        private const val CLOCK_TEXT = 0.28f
        private const val CLOCK_ALPHA = 110
        private const val TEXT_ALPHA = 220
        private const val CAPTION_Y = 0.93f
        private const val CAPTION_TEXT = 0.06f
        private const val STATUS_Y = 0.06f
        private const val STATUS_TEXT = 0.04f
        private const val SHIFT_PX = 6f
        private const val SHIFT_PERIOD_MIN = 16

        /** How bright the lens is, 0 to 1, for a state at time [t] seconds. */
        fun intensity(eye: Eye, t: Double, level: Float): Float = when (eye) {
            Eye.SPEAKING -> 0.55f + 0.45f * level
            Eye.THINKING -> (0.6 + 0.3 * sin(t * 2 * PI * 1.5)).toFloat()
            Eye.LISTENING -> 0.9f
            Eye.AWAKE -> (0.45 + 0.08 * sin(t * 2 * PI * 0.25)).toFloat()
            Eye.ASLEEP -> 0.25f
            Eye.LOADING -> (0.3 + 0.2 * sin(t * 2 * PI * 0.5)).toFloat()
            Eye.OFFLINE, Eye.UNPAIRED -> 0.2f
            Eye.MUTED -> 0f
        }

        /** A small offset that changes once a minute and repeats every 16 minutes. */
        fun burnInShift(nowMs: Long): Float {
            val minute = (nowMs / 60_000L % SHIFT_PERIOD_MIN).toDouble()
            return (SHIFT_PX * sin(minute / SHIFT_PERIOD_MIN * 2 * PI)).toFloat()
        }
    }
}
