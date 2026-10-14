package me.masonasons.fastgh

import me.masonasons.fastgh.data.json
import me.masonasons.fastgh.model.CommitFile
import me.masonasons.fastgh.model.ContentItem
import me.masonasons.fastgh.model.Event
import me.masonasons.fastgh.model.EventRepo
import me.masonasons.fastgh.model.Notification
import me.masonasons.fastgh.model.NotificationRepo
import me.masonasons.fastgh.model.NotificationSubject
import me.masonasons.fastgh.model.Owner
import me.masonasons.fastgh.model.PullRequest
import me.masonasons.fastgh.model.Release
import me.masonasons.fastgh.model.ReleaseAsset
import me.masonasons.fastgh.model.formatSize
import me.masonasons.fastgh.ui.CommitRoute
import me.masonasons.fastgh.ui.CommitsRoute
import me.masonasons.fastgh.ui.IssueRoute
import me.masonasons.fastgh.ui.PullRoute
import me.masonasons.fastgh.ui.ReleaseRoute
import me.masonasons.fastgh.ui.ReleasesRoute
import me.masonasons.fastgh.ui.RepoRoute
import me.masonasons.fastgh.ui.files.FileText
import me.masonasons.fastgh.ui.files.decodeFileText
import me.masonasons.fastgh.ui.releases.summary
import me.masonasons.fastgh.ui.routeForEvent
import me.masonasons.fastgh.ui.routeForNotification
import me.masonasons.fastgh.ui.splitFullName
import kotlinx.serialization.json.JsonObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test
import java.util.Base64

class RoutingAndContentTest {
    private fun event(type: String, payload: String) = Event(
        type = type,
        repo = EventRepo("o/r"),
        payload = json.decodeFromString<JsonObject>(payload),
    )

    @Test
    fun feedEventsOpenTheMatchingInAppScreen() {
        assertEquals(IssueRoute("o", "r", 7), routeForEvent(event("IssuesEvent", """{"issue":{"number":7}}""")))
        // An issue comment on a pull request opens the pull request.
        assertEquals(
            PullRoute("o", "r", 7),
            routeForEvent(event("IssueCommentEvent", """{"issue":{"number":7,"pull_request":{}}}""")),
        )
        assertEquals(
            PullRoute("o", "r", 3),
            routeForEvent(event("PullRequestReviewEvent", """{"pull_request":{"number":3}}""")),
        )
        assertEquals(
            CommitsRoute("o", "r", "dev"),
            routeForEvent(event("PushEvent", """{"ref":"refs/heads/dev"}""")),
        )
        assertEquals(ReleaseRoute("o", "r", 42), routeForEvent(event("ReleaseEvent", """{"release":{"id":42}}""")))
        assertEquals(ReleasesRoute("o", "r"), routeForEvent(event("ReleaseEvent", """{}""")))
        assertEquals(RepoRoute("o", "r"), routeForEvent(event("WatchEvent", """{}""")))
        // No in-app discussions screen yet: falls back to the browser.
        assertNull(routeForEvent(event("DiscussionEvent", """{"discussion":{"number":1}}""")))
    }

    private fun notification(type: String, url: String?) = Notification(
        subject = NotificationSubject(type = type, url = url),
        repository = NotificationRepo(name = "r", fullName = "o/r", owner = Owner("o")),
    )

    @Test
    fun notificationsOpenTheMatchingInAppScreen() {
        assertEquals(IssueRoute("o", "r", 5), routeForNotification(notification("Issue", "https://api.github.com/repos/o/r/issues/5")))
        assertEquals(PullRoute("o", "r", 9), routeForNotification(notification("PullRequest", "https://api.github.com/repos/o/r/pulls/9")))
        assertEquals(
            CommitRoute("o", "r", "abc123"),
            routeForNotification(notification("Commit", "https://api.github.com/repos/o/r/commits/abc123")),
        )
        assertEquals(ReleaseRoute("o", "r", 77), routeForNotification(notification("Release", "https://api.github.com/repos/o/r/releases/77")))
        assertEquals(ReleasesRoute("o", "r"), routeForNotification(notification("Release", null)))
        assertNull(routeForNotification(notification("Discussion", null)))
    }

    private fun encoded(bytes: ByteArray) =
        ContentItem(name = "f", size = bytes.size.toLong(), encoding = "base64", content = Base64.getMimeEncoder().encodeToString(bytes))

    private val decode: (String) -> ByteArray = { Base64.getDecoder().decode(it) }

    @Test
    fun decodesTextFilesIntoLines() {
        val text = decodeFileText(encoded("line one\r\nline two\n\nlast\n".toByteArray()), decode) as FileText.Text
        assertEquals(listOf("line one", "line two", "", "last"), text.lines)
    }

    @Test
    fun treatsBinaryAndOversizedFilesSpecially() {
        assertEquals(FileText.Binary, decodeFileText(encoded(byteArrayOf(0x50, 0x4B, 0x03, 0x04, 0x00)), decode))
        assertEquals(FileText.Binary, decodeFileText(encoded(byteArrayOf(0xC3.toByte(), 0x28)), decode))
        // Over 1 MB the contents API sends no content.
        assertEquals(FileText.TooLarge, decodeFileText(ContentItem(size = 5_000_000, encoding = "none", content = ""), decode))
    }

    @Test
    fun pullRequestStateCoversMergedAndDraft() {
        assertEquals("Merged", PullRequest(state = "closed", mergedAt = "2026-01-01T00:00:00Z").stateDisplay)
        assertEquals("Closed", PullRequest(state = "closed").stateDisplay)
        assertEquals("Draft", PullRequest(state = "open", draft = true).stateDisplay)
        assertEquals("Open", PullRequest(state = "open").stateDisplay)
    }

    @Test
    fun displayHelpersMatchDesktopConventions() {
        assertEquals("512 B", formatSize(512))
        assertTrue(formatSize(2048).matches(Regex("2[.,]0 KB")))
        assertEquals(
            "Renamed: old.txt to new.txt, 1 addition, 0 deletions",
            CommitFile("new.txt", "renamed", 1, 0, "old.txt").display,
        )
        // Downloads are only mentioned when there are assets, like the desktop.
        val noAssets = Release(tagName = "v1").summary()
        assertTrue(noAssets, noAssets.startsWith("Release, 0 assets, ") && "download" !in noAssets)
        val withAssets = Release(tagName = "v1", prerelease = true, assets = listOf(ReleaseAsset(downloadCount = 3))).summary()
        assertTrue(withAssets, withAssets.startsWith("Pre-release, 1 asset, 3 downloads, "))
        assertEquals("v1: Big update", Release(tagName = "v1", name = "Big update").title)
        assertEquals("v1", Release(tagName = "v1", name = "v1").title)
        assertEquals("o" to "r", splitFullName("o/r"))
        assertNull(splitFullName("nope"))
    }
}
