/*
 * A terminal whose program runs on the PC: the bytes it writes arrive over the link and go into
 * Termux's emulator, and Termux's renderer draws the screen. There is no local process. Taps
 * become xterm mouse reports when the program asks for them (btop and Textual both do), and go
 * back to the PC with any other input the emulator produces. A tap is reported when the finger
 * lifts, so that a two-second hold, which closes the terminal, never clicks the program too.
 *
 * The text size is the largest that still gives btop its minimum of 80 x 24 cells, inside a
 * border of [BurnIn.SHIFT_PX] on each side: the grid drifts within that border like the eye, so
 * btop's fixed frame never sits on the same pixels for long and its edges are never clipped.
 */
package io.github.noteoin.halecho.ui

import android.annotation.SuppressLint
import android.content.Context
import android.graphics.Canvas
import android.graphics.Color
import android.graphics.Typeface
import android.util.Log
import android.view.MotionEvent
import android.view.View
import com.termux.terminal.TerminalEmulator
import com.termux.terminal.TerminalOutput
import com.termux.terminal.TerminalSession
import com.termux.terminal.TerminalSessionClient
import com.termux.view.TerminalRenderer

class RemoteTerminalView @JvmOverloads constructor(
    context: Context,
    private val bus: TerminalBus = TerminalBus.main,
) : View(context) {
    private var term = -1L
    private var renderer = TerminalRenderer(START_TEXT_PX, Typeface.MONOSPACE)
    private var emulator: TerminalEmulator? = null
    private val early = ArrayList<ByteArray>()

    private val toPc = object : TerminalOutput() {
        override fun write(data: ByteArray, offset: Int, count: Int) {
            if (term >= 0) bus.uplink?.input(term, data.copyOfRange(offset, offset + count))
        }

        override fun titleChanged(oldTitle: String?, newTitle: String?) = Unit
        override fun onCopyTextToClipboard(text: String?) = Unit
        override fun onPasteTextFromClipboard() = Unit
        override fun onBell() = Unit
        override fun onColorsChanged() = Unit
    }

    /** Begins a new terminal; output that arrives before the first layout is kept. */
    fun start(term: Long) {
        this.term = term
        emulator = null
        early.clear()
        if (width > 0 && height > 0) layOut(width, height)
    }

    /** Feeds the program's output to the emulator and redraws. */
    fun append(data: ByteArray) {
        val target = emulator
        if (target == null) {
            early.add(data)
            return
        }
        target.append(data, data.size)
        invalidate()
    }

    override fun onSizeChanged(w: Int, h: Int, oldw: Int, oldh: Int) {
        if (term >= 0 && w > 0 && h > 0) layOut(w, h)
    }

    private fun layOut(viewW: Int, viewH: Int) {
        val w = viewW - 2 * BurnIn.SHIFT_PX.toInt()
        val h = viewH - 2 * BurnIn.SHIFT_PX.toInt()
        var size = START_TEXT_PX
        while (true) {
            renderer = TerminalRenderer(size, Typeface.MONOSPACE)
            val fits = cols(w) >= MIN_COLS && rows(h) >= MIN_ROWS
            if (fits || size <= MIN_TEXT_PX) break
            size--
        }
        val cols = cols(w)
        val rows = rows(h)
        val cellW = renderer.fontWidth.toInt()
        val cellH = renderer.fontLineSpacing
        val current = emulator
        if (current == null) {
            emulator = TerminalEmulator(toPc, cols, rows, cellW, cellH, TRANSCRIPT_ROWS, LogClient)
            early.forEach { emulator?.append(it, it.size) }
            early.clear()
        } else {
            current.resize(cols, rows, cellW, cellH)
        }
        bus.uplink?.size(term, cols, rows)
        invalidate()
    }

    private fun cols(w: Int) = (w / renderer.fontWidth).toInt()

    private fun rows(h: Int) = h / renderer.fontLineSpacing

    override fun onDraw(canvas: Canvas) {
        canvas.drawColor(Color.BLACK)
        val target = emulator ?: return
        val offset = BurnIn.SHIFT_PX + BurnIn.shift(System.currentTimeMillis())
        canvas.save()
        canvas.translate(offset, offset)
        renderer.render(target, canvas, 0, -1, -1, -1, -1)
        canvas.restore()
    }

    private val closeOnHold = Runnable {
        held = true
        if (term >= 0) bus.uplink?.close(term)
    }
    private var held = false

    // Taps are mouse reports for the program; there is nothing to click on the view itself
    @SuppressLint("ClickableViewAccessibility")
    override fun onTouchEvent(event: MotionEvent): Boolean {
        when (event.actionMasked) {
            MotionEvent.ACTION_DOWN -> {
                held = false
                postDelayed(closeOnHold, HOLD_MS)
            }
            MotionEvent.ACTION_UP -> {
                removeCallbacks(closeOnHold)
                if (!held) click(event.x, event.y)
            }
            MotionEvent.ACTION_CANCEL -> removeCallbacks(closeOnHold)
        }
        return true
    }

    private fun click(x: Float, y: Float) {
        val target = emulator ?: return
        if (!target.isMouseTrackingActive) return
        val offset = BurnIn.SHIFT_PX + BurnIn.shift(System.currentTimeMillis())
        val col = ((x - offset) / renderer.fontWidth).toInt().coerceAtLeast(0) + 1
        val row = ((y - offset) / renderer.fontLineSpacing).toInt().coerceAtLeast(0) + 1
        target.sendMouseEvent(TerminalEmulator.MOUSE_LEFT_BUTTON, col, row, true)
        target.sendMouseEvent(TerminalEmulator.MOUSE_LEFT_BUTTON, col, row, false)
    }

    /** The emulator's callbacks: logging only, since no local session exists. */
    private object LogClient : TerminalSessionClient {
        private const val TAG = "halecho-terminal"
        override fun onTextChanged(changedSession: TerminalSession) = Unit
        override fun onTitleChanged(changedSession: TerminalSession) = Unit
        override fun onSessionFinished(finishedSession: TerminalSession) = Unit
        override fun onCopyTextToClipboard(session: TerminalSession, text: String?) = Unit
        override fun onPasteTextFromClipboard(session: TerminalSession?) = Unit
        override fun onBell(session: TerminalSession) = Unit
        override fun onColorsChanged(session: TerminalSession) = Unit
        override fun onTerminalCursorStateChange(state: Boolean) = Unit
        override fun getTerminalCursorStyle(): Int = TerminalEmulator.TERMINAL_CURSOR_STYLE_BLOCK
        override fun logError(tag: String?, message: String?) { Log.e(TAG, "$tag: $message") }
        override fun logWarn(tag: String?, message: String?) { Log.w(TAG, "$tag: $message") }
        override fun logInfo(tag: String?, message: String?) = Unit
        override fun logDebug(tag: String?, message: String?) = Unit
        override fun logVerbose(tag: String?, message: String?) = Unit
        override fun logStackTraceWithMessage(tag: String?, message: String?, e: Exception?) {
            Log.e(TAG, "$tag: $message", e)
        }
        override fun logStackTrace(tag: String?, e: Exception?) { Log.e(TAG, tag, e) }
    }

    companion object {
        const val MIN_COLS = 80 // btop's minimum
        private const val HOLD_MS = 2000L // the same hold that opens the eye's menu
        const val MIN_ROWS = 24
        private const val START_TEXT_PX = 22
        private const val MIN_TEXT_PX = 10
        private const val TRANSCRIPT_ROWS = 100 // the emulator's minimum; btop draws on the alternate screen
    }
}
