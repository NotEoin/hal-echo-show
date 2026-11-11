/*
 * HAL's lens, centred on the screen. The drawing follows the lens on the portfolio site
 * (eoinforrest.me, LensPlate.tsx), itself a port of hal-voice's ui_eye.py: a bezel, an additive
 * red glow of 18 fading rings, a red core, a hot centre and a specular highlight. Here the bezel
 * is brushed metal around black glass, closer to the film's panel.
 *
 * Behind the lens sits the site's red wash: the hal-voice section's background, an ellipse of
 * the halvoice tint fading out by 70% of its size, here swelling with the lens.
 *
 * Brightness follows what Hal is doing (intensity). At rest the lens breathes slowly, once every
 * eight seconds, and every change of state is eased, so a wake word the PC then rejects never
 * flashes the lens. When the room is asleep a dim clock sits in the corner. The picture drifts a
 * few pixels each minute ([BurnIn]).
 */
package io.github.noteoin.halecho.ui

import android.content.Context
import android.graphics.BlendMode
import android.graphics.Canvas
import android.graphics.Color
import android.graphics.LinearGradient
import android.graphics.Matrix
import android.graphics.Paint
import android.graphics.RadialGradient
import android.graphics.RectF
import android.graphics.Shader
import android.text.Layout
import android.text.StaticLayout
import android.text.TextPaint
import android.text.TextUtils
import android.view.View
import io.github.noteoin.halecho.R
import io.github.noteoin.halecho.UiState
import io.github.noteoin.halecho.UiState.Eye
import java.text.DateFormat
import java.util.Date
import kotlin.math.PI
import kotlin.math.exp
import kotlin.math.min
import kotlin.math.pow
import kotlin.math.sin

class EyeView(context: Context) : View(context) {
    private val wash = Paint(Paint.ANTI_ALIAS_FLAG)
    private val bezel = Paint(Paint.ANTI_ALIAS_FLAG).apply { style = Paint.Style.STROKE }
    private val edge = Paint(Paint.ANTI_ALIAS_FLAG).apply { style = Paint.Style.STROKE }
    private val glass = Paint(Paint.ANTI_ALIAS_FLAG)
    // "lighter" on the web: overlapping glow rings add up instead of covering each other
    private val glow = Paint(Paint.ANTI_ALIAS_FLAG).apply { blendMode = BlendMode.PLUS }
    private val core = Paint(Paint.ANTI_ALIAS_FLAG).apply { blendMode = BlendMode.PLUS }
    private val hot = Paint(Paint.ANTI_ALIAS_FLAG).apply { blendMode = BlendMode.PLUS }
    private val specular = Paint(Paint.ANTI_ALIAS_FLAG).apply { color = Color.argb(26, 255, 255, 255) }
    // The status line of the portfolio site's lens: Geist Mono, upper case, spaced, in its tint
    private val text = TextPaint(Paint.ANTI_ALIAS_FLAG).apply {
        color = context.getColor(R.color.hal_tint)
        textAlign = Paint.Align.LEFT // StaticLayout centres lines itself
        typeface = context.resources.getFont(R.font.geist_mono)
        letterSpacing = LETTER_SPACING_EM
    }
    private var captionLayout: StaticLayout? = null
    private var captionKey = ""
    private val clock = DateFormat.getTimeInstance(DateFormat.SHORT)
    private val date = Date()
    private val oval = RectF()
    private var smoothed = 0f
    private var lastFrameMs = 0L
    private var shaderKey = ""

    init {
        setBackgroundColor(BACKGROUND)
    }

    override fun onDraw(canvas: Canvas) {
        super.onDraw(canvas)
        val now = System.currentTimeMillis()
        val eye = UiState.eye
        val shift = BurnIn.shift(now)
        val cx = width / 2f + shift
        val cy = height / 2f + shift
        val radius = min(width, height) * RADIUS
        val target = intensity(eye, now / 1000.0, UiState.level)
        smoothed = ease(smoothed, target, (now - lastFrameMs).coerceIn(0, MAX_STEP_MS), eye == Eye.SPEAKING)
        lastFrameMs = now
        drawLens(canvas, cx, cy, radius, smoothed)
        drawText(canvas, eye, now, shift)
        postInvalidateOnAnimation()
    }

    private fun drawLens(canvas: Canvas, cx: Float, cy: Float, r: Float, k: Float) {
        // The shaders depend only on position and size, which change once a minute at most
        val key = "$cx/$cy/$r"
        if (key != shaderKey) {
            shaderKey = key
            wash.shader = washShader(cx, cy)
            bezel.shader = LinearGradient(
                cx - r, cy - r, cx + r, cy + r,
                intArrayOf(Color.rgb(176, 176, 184), Color.rgb(92, 92, 100), Color.rgb(36, 36, 42)),
                floatArrayOf(0f, 0.45f, 1f),
                Shader.TileMode.CLAMP,
            )
            glass.shader = RadialGradient(
                cx, cy, r, intArrayOf(Color.rgb(18, 14, 16), Color.BLACK), null, Shader.TileMode.CLAMP,
            )
            // The site draws the core and hot centre as flat discs; soft edges read as the film's glass
            core.shader = RadialGradient(
                cx, cy, r * CORE_RADIUS,
                intArrayOf(Color.rgb(230, 34, 22), Color.rgb(200, 24, 16), Color.argb(0, 120, 8, 6)),
                floatArrayOf(0f, 0.55f, 1f),
                Shader.TileMode.CLAMP,
            )
            hot.shader = RadialGradient(
                cx, cy, r * HOT_RADIUS,
                intArrayOf(Color.rgb(255, 236, 196), Color.rgb(255, 170, 100), Color.argb(0, 255, 90, 40)),
                floatArrayOf(0f, 0.4f, 1f),
                Shader.TileMode.CLAMP,
            )
        }
        wash.alpha = alpha(WASH_FLOOR + (1 - WASH_FLOOR) * k)
        canvas.drawRect(0f, 0f, width.toFloat(), height.toFloat(), wash)
        bezel.strokeWidth = r * BEZEL_WIDTH
        canvas.drawCircle(cx, cy, r * (1 + BEZEL_WIDTH / 2), bezel)
        edge.strokeWidth = r * EDGE_WIDTH
        edge.color = Color.argb(70, 255, 255, 255)
        canvas.drawCircle(cx, cy, r * (1 + BEZEL_WIDTH), edge)
        edge.color = Color.argb(200, 0, 0, 0)
        canvas.drawCircle(cx, cy, r, edge)
        canvas.drawCircle(cx, cy, r, glass)

        for (i in GLOW_RINGS downTo 1) {
            val f = i / GLOW_RINGS.toFloat()
            glow.color = Color.argb(alpha(GLOW_ALPHA * k * (1 - f).pow(GLOW_FALLOFF)), 220, 30, 20)
            canvas.drawCircle(cx, cy, r * GLOW_SPAN * f + r * GLOW_INNER, glow)
        }
        core.alpha = alpha(CORE_ALPHA + CORE_GAIN * k)
        canvas.drawCircle(cx, cy, r * CORE_RADIUS, core)
        hot.alpha = alpha(HOT_ALPHA + HOT_GAIN * k)
        canvas.drawCircle(cx, cy, r * HOT_RADIUS, hot)

        canvas.save()
        canvas.rotate(SPECULAR_ANGLE_DEG, cx - r * 0.22f, cy - r * 0.26f)
        oval.set(cx - r * 0.35f, cy - r * 0.33f, cx - r * 0.09f, cy - r * 0.19f)
        canvas.drawOval(oval, specular)
        canvas.restore()
    }

    /**
     * The site's `radial-gradient(60% 60% at ..., tint 9%, transparent 70%)`: CSS sizes the
     * ellipse by the box, so it is a circle of 60% of the width, squashed to 60% of the height.
     */
    private fun washShader(cx: Float, cy: Float): RadialGradient {
        val tint = context.getColor(R.color.hal_tint)
        val radiusX = width * WASH_SIZE
        val shader = RadialGradient(
            cx, cy, radiusX,
            intArrayOf(Color.argb(WASH_PEAK_ALPHA, Color.red(tint), Color.green(tint), Color.blue(tint)), Color.TRANSPARENT, Color.TRANSPARENT),
            floatArrayOf(0f, WASH_FADE_END, 1f),
            Shader.TileMode.CLAMP,
        )
        shader.setLocalMatrix(Matrix().apply { setScale(1f, height * WASH_SIZE / radiusX, cx, cy) })
        return shader
    }

    private fun drawText(canvas: Canvas, eye: Eye, now: Long, shift: Float) {
        if (eye == Eye.ASLEEP) {
            text.textSize = height * CLOCK_TEXT
            text.alpha = CLOCK_ALPHA
            date.time = now
            canvas.drawText(clock.format(date).uppercase(), width * CLOCK_X + shift, height * CLOCK_Y + shift, text)
            return
        }
        val (line, alpha) = when (eye) {
            Eye.UNPAIRED -> context.getString(R.string.caption_unpaired) to TEXT_ALPHA
            Eye.MUTED -> context.getString(R.string.caption_muted) to TEXT_ALPHA
            Eye.OFFLINE -> context.getString(R.string.caption_offline) to TEXT_ALPHA
            Eye.LOADING -> context.getString(R.string.caption_loading) to TEXT_ALPHA
            else -> UiState.caption to captionAlpha(now - UiState.captionAtMs)
        }
        if (line.isEmpty() || alpha == 0) return
        text.textSize = height * CAPTION_TEXT
        text.alpha = alpha
        val layout = captionLayout(line.uppercase())
        canvas.save()
        canvas.translate((width - layout.width) / 2f, height - layout.height - height * CAPTION_MARGIN)
        layout.draw(canvas)
        canvas.restore()
    }

    /** The caption laid out in at most two lines; rebuilt only when the text or size changes. */
    private fun captionLayout(line: String): StaticLayout {
        val maxWidth = (width * CAPTION_WIDTH).toInt()
        val key = "$line/$maxWidth/${text.textSize}"
        captionLayout?.takeIf { key == captionKey }?.let { return it }
        val layout = StaticLayout.Builder.obtain(line, 0, line.length, text, maxWidth)
            .setAlignment(Layout.Alignment.ALIGN_CENTER)
            .setMaxLines(CAPTION_LINES)
            .setEllipsize(TextUtils.TruncateAt.END)
            .build()
        captionLayout = layout
        captionKey = key
        return layout
    }

    // The home screen's hold gesture calls this on release, for accessibility services
    override fun performClick(): Boolean = super.performClick()

    companion object {
        private val BACKGROUND = Color.rgb(6, 6, 8)
        private const val RADIUS = 0.32f // leaves room under the bezel for a two-line caption
        private const val WASH_SIZE = 0.6f
        private const val WASH_FADE_END = 0.7f
        // The site mixes 9% of the tint into the page; on this panel's near-black that barely
        // shows, so the wash peaks at 18% (46 of 255), judged by eye on the device
        private const val WASH_PEAK_ALPHA = 46
        private const val WASH_FLOOR = 0.55f // dimmest share of the wash, with the lens at rest
        private const val BEZEL_WIDTH = 0.11f
        private const val EDGE_WIDTH = 0.012f
        private const val GLOW_RINGS = 18
        private const val GLOW_ALPHA = 0.055f * 2.4f // the site's 0.055, on black glass not a page
        private const val GLOW_FALLOFF = 1.4f
        private const val GLOW_SPAN = 0.9f
        private const val GLOW_INNER = 0.12f
        private const val CORE_RADIUS = 0.46f // wider than the site's 0.3: the soft edge fades early
        private const val CORE_ALPHA = 0.55f
        private const val CORE_GAIN = 0.4f
        private const val HOT_RADIUS = 0.17f
        private const val HOT_ALPHA = 0.35f
        private const val HOT_GAIN = 0.5f
        private const val SPECULAR_ANGLE_DEG = -28.6f // -0.5 rad, as on the site
        private const val CLOCK_X = 0.03f
        private const val CLOCK_Y = 0.12f
        private const val CLOCK_TEXT = 0.08f
        private const val CLOCK_ALPHA = 90
        private const val TEXT_ALPHA = 200
        private const val CAPTION_MARGIN = 0.02f
        private const val CAPTION_TEXT = 0.036f
        private const val CAPTION_WIDTH = 0.9f
        private const val CAPTION_LINES = 2

        private const val LETTER_SPACING_EM = 0.12f // the site's tracking-[.12em]
        private const val CAPTION_HOLD_MS = 6000L
        private const val CAPTION_FADE_MS = 2000L
        private const val MAX_STEP_MS = 100L

        /** One slow breath every eight seconds at rest. */
        const val BREATH_PERIOD_S = 8.0

        // Time constants of the easing: the voice is followed closely, everything else glides
        private const val SPEAKING_TAU_MS = 60f
        private const val STATE_TAU_MS = 700f

        /** How bright the lens is, 0 to 1, for a state at time [t] seconds. */
        fun intensity(eye: Eye, t: Double, level: Float): Float = when (eye) {
            Eye.SPEAKING -> (0.45f + level).coerceIn(0.35f, 1f)
            // hal-voice's irregular flicker while it considers
            Eye.THINKING -> (0.55 + 0.18 * sin(t * 7) * sin(t * 2.3)).toFloat()
            Eye.LISTENING -> 1f
            Eye.AWAKE, Eye.LOADING -> breath(t, 0.30, 0.16)
            Eye.ASLEEP -> breath(t, 0.18, 0.10)
            Eye.OFFLINE, Eye.UNPAIRED -> breath(t, 0.10, 0.06)
            Eye.MUTED -> 0f
        }

        /** A slow swell and fade: eased, so the lens lingers at its brightest and dimmest. */
        private fun breath(t: Double, base: Double, depth: Double): Float {
            val phase = 0.5 + 0.5 * sin(t * 2 * PI / BREATH_PERIOD_S)
            val eased = phase * phase * (3 - 2 * phase)
            return (base + depth * eased).toFloat()
        }

        /** Moves [current] toward [target] over [stepMs], fast while speaking, slow otherwise. */
        fun ease(current: Float, target: Float, stepMs: Long, speaking: Boolean): Float {
            val tau = if (speaking) SPEAKING_TAU_MS else STATE_TAU_MS
            val blend = 1f - exp(-stepMs / tau)
            return current + (target - current) * blend
        }

        /** A caption shows for six seconds, then fades over two. */
        fun captionAlpha(ageMs: Long): Int = when {
            ageMs < CAPTION_HOLD_MS -> TEXT_ALPHA
            ageMs < CAPTION_HOLD_MS + CAPTION_FADE_MS ->
                (TEXT_ALPHA * (1 - (ageMs - CAPTION_HOLD_MS) / CAPTION_FADE_MS.toFloat())).toInt()
            else -> 0
        }

        private fun alpha(fraction: Float): Int = (fraction * 255).toInt().coerceIn(0, 255)
    }
}
