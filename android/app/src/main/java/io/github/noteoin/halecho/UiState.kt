/*
 * What the screen shows, written by the service's threads and read by the eye on every
 * animation frame. Plain volatile fields: the eye only ever needs the latest values.
 */
package io.github.noteoin.halecho

object UiState {
    /** What the eye shows, in order of priority. */
    enum class Eye { UNPAIRED, MUTED, OFFLINE, LOADING, SPEAKING, THINKING, LISTENING, AWAKE, ASLEEP }

    @Volatile var paired = false
    @Volatile var muted = false
    @Volatile var connected = false
    @Volatile var modelsReady = false
    @Volatile var speaking = false
    @Volatile var thinking = false
    @Volatile var listening = false
    @Volatile var roomAwake = true
    @Volatile var level = 0f
    @Volatile var micDb = -100.0
    @Volatile var caption = ""
        set(value) {
            field = value
            captionAtMs = System.currentTimeMillis()
        }

    /** When [caption] last changed; the eye fades it out a few seconds later. */
    @Volatile var captionAtMs = 0L
    @Volatile var status = ""

    val eye: Eye
        get() = when {
            !paired -> Eye.UNPAIRED
            muted -> Eye.MUTED
            !connected -> Eye.OFFLINE
            !modelsReady -> Eye.LOADING
            speaking -> Eye.SPEAKING
            thinking -> Eye.THINKING
            listening -> Eye.LISTENING
            roomAwake -> Eye.AWAKE
            else -> Eye.ASLEEP
        }
}
