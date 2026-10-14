package me.masonasons.fastgh

import me.masonasons.fastgh.data.json
import me.masonasons.fastgh.model.Notification
import me.masonasons.fastgh.model.NotificationSubject
import me.masonasons.fastgh.model.Repository
import me.masonasons.fastgh.model.parseRepoInput
import me.masonasons.fastgh.ui.components.relativeTime
import me.masonasons.fastgh.ui.components.statsLine
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test
import java.time.Duration
import java.time.Instant

class ModelsTest {
    @Test
    fun parsesRepoInputLikeDesktop() {
        assertEquals("octocat" to "Hello-World", parseRepoInput("octocat/Hello-World"))
        assertEquals("octocat" to "Hello-World", parseRepoInput("  https://github.com/octocat/Hello-World  "))
        assertEquals("octocat" to "Hello-World", parseRepoInput("github.com/octocat/Hello-World.git"))
        assertEquals("octocat" to "Hello-World", parseRepoInput("https://www.github.com/octocat/Hello-World/"))
        assertNull(parseRepoInput("octocat"))
        assertNull(parseRepoInput("https://github.com/octocat"))
        assertNull(parseRepoInput("a/b/c"))
    }

    @Test
    fun notificationWebUrlConvertsApiUrl() {
        val pr = Notification(subject = NotificationSubject(url = "https://api.github.com/repos/o/r/pulls/5"))
        assertEquals("https://github.com/o/r/pull/5", pr.webUrl)
        val issue = Notification(subject = NotificationSubject(url = "https://api.github.com/repos/o/r/issues/9"))
        assertEquals("https://github.com/o/r/issues/9", issue.webUrl)
    }

    @Test
    fun notificationWithoutSubjectUrlFallsBackToRepo() {
        val payload = """{"id":"1","subject":{"title":"t","url":null,"type":"Release"},
            "repository":{"name":"r","full_name":"o/r","owner":{"login":"o"}}}"""
        assertEquals("https://github.com/o/r", json.decodeFromString<Notification>(payload).webUrl)
    }

    @Test
    fun repositoryParsesApiPayloadAndIgnoresUnknownFields() {
        val repo = json.decodeFromString<Repository>(
            """{"id":1,"name":"r","full_name":"o/r","owner":{"login":"o","id":2},
               "description":null,"stargazers_count":1,"language":"Kotlin","fork":true,
               "pushed_at":"2026-01-01T00:00:00Z","html_url":"https://github.com/o/r","topics":["x"]}""",
        )
        assertEquals("o", repo.owner.login)
        assertEquals("https://github.com/o/r.git", repo.cloneUrl)
        assertEquals(Instant.parse("2026-01-01T00:00:00Z"), repo.pushedInstant)
        assertTrue(repo.statsLine(), repo.statsLine().startsWith("1 star, Kotlin, fork, pushed "))
    }

    @Test
    fun relativeTimeMatchesDesktopWording() {
        val now = Instant.parse("2026-06-01T12:00:00Z")
        fun ago(d: Duration) = relativeTime(now.minus(d), now)
        assertEquals("just now", ago(Duration.ofSeconds(30)))
        assertEquals("1 minute ago", ago(Duration.ofSeconds(90)))
        assertEquals("4 hours ago", ago(Duration.ofHours(4)))
        assertEquals("1 day ago", ago(Duration.ofDays(1)))
        assertEquals("2 months ago", ago(Duration.ofDays(60)))
        assertEquals("1 year ago", ago(Duration.ofDays(400)))
        assertEquals("Unknown", relativeTime(null, now))
    }
}
