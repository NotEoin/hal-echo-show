/*
 * Whether the room is worth listening to. Asleep, the device measures loudness and nothing
 * else; any sound wakes it for `listener.awake_s` (5 minutes by default), so someone who walks
 * in and says "Hey Hal" is heard at once, and the wake word spotter runs only while awake.
 */
package io.github.noteoin.halecho.listen

class RoomState(private val awakeMs: Long) {
    var awake: Boolean = false
        private set
    private var until = 0L

    /** Updates the state for one frame; returns true when it changed. */
    fun onFrame(nowMs: Long, sound: Boolean): Boolean {
        if (sound) {
            until = nowMs + awakeMs
            if (!awake) {
                awake = true
                return true
            }
            return false
        }
        if (awake && nowMs >= until) {
            awake = false
            return true
        }
        return false
    }
}
