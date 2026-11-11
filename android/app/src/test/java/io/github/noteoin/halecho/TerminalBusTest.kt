/* The terminal bus: output before the screen attaches is replayed; closed terminals are dropped. */
package io.github.noteoin.halecho

import io.github.noteoin.halecho.ui.TerminalBus
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test

class TerminalBusTest {
    private val events = mutableListOf<String>()
    private val bus = TerminalBus { it.run() }
    private val screen = object : TerminalBus.Screen {
        override fun show(term: Long, title: String) { events += "show $term $title" }
        override fun output(term: Long, data: ByteArray) { events += "out $term ${String(data)}" }
        override fun hide() { events += "hide" }
    }

    @Test
    fun outputBeforeTheScreenAttachesIsReplayed() {
        bus.open(1, "Monitor")
        bus.output(1, "a".toByteArray())
        bus.attach(screen)
        assertEquals(listOf("show 1 Monitor", "out 1 a"), events)
    }

    @Test
    fun outputForAnotherTerminalIsDropped() {
        bus.attach(screen)
        bus.open(2, "Monitor")
        bus.output(1, "stale".toByteArray())
        assertEquals(listOf("show 2 Monitor"), events)
    }

    @Test
    fun hidingAnotherTerminalLeavesTheOpenOne() {
        bus.attach(screen)
        bus.open(3, "Monitor")
        bus.hide(2)
        assertEquals(3L, bus.current)
        bus.hide(null)
        assertNull(bus.current)
        assertEquals(listOf("show 3 Monitor", "hide"), events)
    }
}
