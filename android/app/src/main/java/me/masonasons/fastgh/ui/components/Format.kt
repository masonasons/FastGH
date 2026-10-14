package me.masonasons.fastgh.ui.components

import java.time.Duration
import java.time.Instant

/** "3 days ago" style text, matching the desktop app's long relative format. */
fun relativeTime(instant: Instant?, now: Instant = Instant.now()): String {
    if (instant == null) return "Unknown"
    val diff = Duration.between(instant, now)
    val days = diff.toDays()
    fun plural(count: Long, unit: String) = "$count $unit${if (count == 1L) "" else "s"} ago"
    return when {
        days > 365 -> plural(days / 365, "year")
        days > 30 -> plural(days / 30, "month")
        days > 0 -> plural(days, "day")
        diff.toHours() > 0 -> plural(diff.toHours(), "hour")
        diff.toMinutes() > 0 -> plural(diff.toMinutes(), "minute")
        else -> "just now"
    }
}
