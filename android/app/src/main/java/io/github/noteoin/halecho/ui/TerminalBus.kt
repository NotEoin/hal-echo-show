/*
 * Carries a terminal screen between the service, which talks to the PC, and the home screen,
 * which draws it. Everything runs on one thread ([post], the main thread in the app): output
 * that arrives before the screen is attached waits here, up to a limit, and is replayed.
 */
package io.github.noteoin.halecho.ui

import android.os.Handler
import android.os.Looper

class TerminalBus(private val post: (Runnable) -> Unit) {
    /** Draws the terminal; the home screen. */
    interface Screen {
        fun show(term: Long, title: String)
        fun output(term: Long, data: ByteArray)
        fun hide()
    }

    /** Sends to the PC; the service. */
    interface Uplink {
        fun input(term: Long, data: ByteArray)
        fun size(term: Long, cols: Int, rows: Int)
        fun close(term: Long)
    }

    @Volatile var uplink: Uplink? = null
    private var screen: Screen? = null
    private var openTerm: Long? = null
    private var title = ""
    private val pending = ArrayDeque<ByteArray>()
    private var pendingBytes = 0

    /** The terminal on show, or null for the eye; read on the [post] thread. */
    val current: Long? get() = openTerm

    fun open(term: Long, title: String) = post(Runnable {
        openTerm = term
        this.title = title
        clearPending()
        screen?.show(term, title)
    })

    fun output(term: Long, data: ByteArray) = post(Runnable {
        if (term != openTerm) return@Runnable
        val target = screen
        if (target != null) {
            target.output(term, data)
        } else if (pendingBytes + data.size <= MAX_PENDING_BYTES) {
            pending.addLast(data)
            pendingBytes += data.size
        }
    })

    /** Back to the eye; a null [term] closes whatever is open (the link dropped). */
    fun hide(term: Long?) = post(Runnable {
        if (openTerm == null || (term != null && term != openTerm)) return@Runnable
        openTerm = null
        clearPending()
        screen?.hide()
    })

    fun attach(target: Screen) = post(Runnable {
        screen = target
        val term = openTerm ?: return@Runnable
        target.show(term, title)
        pending.forEach { target.output(term, it) }
        clearPending()
    })

    fun detach(target: Screen) = post(Runnable { if (screen === target) screen = null })

    private fun clearPending() {
        pending.clear()
        pendingBytes = 0
    }

    companion object {
        // A btop frame is tens of kilobytes; this holds a few while the screen is not attached
        private const val MAX_PENDING_BYTES = 1 shl 20

        /** The app's bus, on the main thread. */
        val main: TerminalBus by lazy {
            val handler = Handler(Looper.getMainLooper())
            TerminalBus { handler.post(it) }
        }
    }
}
