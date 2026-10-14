package me.masonasons.fastgh.ui

import me.masonasons.fastgh.model.Event
import me.masonasons.fastgh.model.Notification
import me.masonasons.fastgh.model.obj
import me.masonasons.fastgh.model.str

/**
 * Where opening a feed event should go in the app, following the desktop's
 * on_open_feed_event. Null means there's no in-app screen; use the browser.
 */
fun routeForEvent(event: Event): Any? {
    val (owner, name) = event.repoOwnerAndName ?: return null
    val p = event.payload
    fun number(key: String) = p.obj(key).str("number").toIntOrNull()
    return when (event.type) {
        "IssuesEvent", "IssueCommentEvent" -> number("issue")?.let { n ->
            // Comments on pull requests arrive as issue comments on an "issue" that is a PR.
            if (p.obj("issue")["pull_request"] != null) PullRoute(owner, name, n) else IssueRoute(owner, name, n)
        }
        "PullRequestEvent", "PullRequestReviewEvent", "PullRequestReviewCommentEvent", "PullRequestReviewThreadEvent" ->
            number("pull_request")?.let { PullRoute(owner, name, it) }
        "PushEvent" -> CommitsRoute(owner, name, p.str("ref").removePrefix("refs/heads/").ifEmpty { null })
        "CommitCommentEvent" -> CommitsRoute(owner, name)
        "ReleaseEvent" -> p.obj("release").str("id").toLongOrNull()
            ?.let { ReleaseRoute(owner, name, it) } ?: ReleasesRoute(owner, name)
        "WatchEvent", "ForkEvent", "CreateEvent", "PublicEvent", "GollumEvent", "MemberEvent" -> RepoRoute(owner, name)
        else -> null
    }
}

/**
 * Where opening a notification should go in the app, following the desktop's
 * on_open_notification. Null means there's no in-app screen; use the browser.
 */
fun routeForNotification(notification: Notification): Any? {
    val owner = notification.repository.owner.login
    val name = notification.repository.name
    if (owner.isEmpty() || name.isEmpty()) return null
    // e.g. https://api.github.com/repos/owner/repo/issues/123
    val last = notification.subject.url?.trimEnd('/')?.substringAfterLast('/')
    return when (notification.subject.type) {
        "Issue" -> last?.toIntOrNull()?.let { IssueRoute(owner, name, it) }
        "PullRequest" -> last?.toIntOrNull()?.let { PullRoute(owner, name, it) }
        "Release" -> last?.toLongOrNull()?.let { ReleaseRoute(owner, name, it) } ?: ReleasesRoute(owner, name)
        "Commit" -> last?.takeIf { it.isNotEmpty() }?.let { CommitRoute(owner, name, it) } ?: CommitsRoute(owner, name)
        else -> null
    }
}
