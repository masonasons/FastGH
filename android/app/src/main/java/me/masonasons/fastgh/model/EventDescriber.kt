package me.masonasons.fastgh.model

import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonNull
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.booleanOrNull
import kotlinx.serialization.json.intOrNull

/** Human-readable feed descriptions, ported from the desktop app's models/event.py. */
object EventDescriber {

    private val EVENT_TYPES = mapOf(
        "CommitCommentEvent" to "commented on a commit",
        "CreateEvent" to "created",
        "DeleteEvent" to "deleted",
        "DiscussionCommentEvent" to "commented on discussion",
        "DiscussionEvent" to "discussion",
        "ForkEvent" to "forked",
        "GollumEvent" to "updated wiki",
        "IssueCommentEvent" to "commented on issue",
        "IssuesEvent" to "issue",
        "MemberEvent" to "added member",
        "PublicEvent" to "made public",
        "PullRequestEvent" to "pull request",
        "PullRequestReviewEvent" to "reviewed PR",
        "PullRequestReviewThreadEvent" to "updated PR review thread",
        "PullRequestReviewCommentEvent" to "commented on PR review",
        "PushEvent" to "pushed",
        "ReleaseEvent" to "released",
        "SponsorshipEvent" to "sponsorship",
        "WatchEvent" to "starred",
    )

    fun describe(event: Event): String {
        val p = event.payload
        return when (event.type) {
            "WatchEvent" -> "starred"
            "ForkEvent" -> {
                val forkName = p.obj("forkee").str("full_name")
                if (forkName.isNotEmpty()) "forked to $forkName" else "forked"
            }
            "CreateEvent" -> {
                val refType = p.str("ref_type")
                val ref = p.str("ref")
                when (refType) {
                    "repository" -> "created repository"
                    "branch" -> "created branch $ref"
                    "tag" -> "created tag $ref"
                    else -> "created $refType"
                }
            }
            "DeleteEvent" -> "deleted ${p.str("ref_type")} ${p.str("ref")}"
            "DiscussionEvent" -> {
                val discussion = p.obj("discussion")
                withTitle("${p.str("action")} discussion #${discussion.str("number")}", discussion.title())
            }
            "DiscussionCommentEvent" -> describeDiscussionComment(p)
            "PushEvent" -> describePush(p)
            "IssuesEvent" -> describeIssueOrPr(p, p.obj("issue"), "issue")
            "IssueCommentEvent" -> {
                val action = p.str("action", "created")
                val issue = p.obj("issue")
                val number = issue.str("number")
                if (action == "created" || action == "edited") {
                    withTitle("commented on issue #$number", issue.title())
                } else {
                    withTitle("$action comment on issue #$number", issue.title())
                }
            }
            "PullRequestEvent" -> describePullRequest(p)
            "PullRequestReviewEvent" -> {
                val pr = p.obj("pull_request")
                val number = pr.str("number")
                val base = when (p.obj("review").str("state")) {
                    "approved" -> "approved PR #$number"
                    "changes_requested" -> "requested changes on PR #$number"
                    else -> "reviewed PR #$number"
                }
                withTitle(base, pr.title())
            }
            "PullRequestReviewCommentEvent" -> {
                val pr = p.obj("pull_request")
                withTitle("commented on PR #${pr.str("number")}", pr.title())
            }
            "PullRequestReviewThreadEvent" -> {
                val pr = p.obj("pull_request")
                withTitle("${p.str("action")} review thread on PR #${pr.str("number")}", pr.title())
            }
            "ReleaseEvent" -> {
                val action = p.str("action")
                val tag = p.obj("release").str("tag_name")
                if (action == "published") "released $tag" else "$action release $tag"
            }
            "CommitCommentEvent" -> "commented on a commit"
            "GollumEvent" -> {
                val page = (p["pages"] as? JsonArray)?.firstOrNull() as? JsonObject
                if (page != null) {
                    "${page.str("action", "updated")} wiki page: ${page.str("title")}"
                } else {
                    "updated wiki"
                }
            }
            "MemberEvent" -> "${p.str("action")} ${p.obj("member").str("login")} as collaborator"
            "PublicEvent" -> "made repository public"
            else -> EVENT_TYPES[event.type] ?: event.type
        }
    }

    private fun describeDiscussionComment(p: JsonObject): String {
        val action = p.str("action", "created")
        val discussion = p.obj("discussion")
        val number = discussion.str("number")
        val comment = p.obj("comment")
        val isReply = comment.isPresent("in_reply_to_id") || comment.isPresent("reply_to_id")
        val base = when {
            action == "created" || action == "edited" ->
                if (isReply) "replied in discussion #$number" else "commented on discussion #$number"
            else -> "$action comment on discussion #$number"
        }
        return withTitle(base, discussion.title())
    }

    private fun describePush(p: JsonObject): String {
        // size can be 0 for force pushes; fall back to distinct_size or the commits array
        var size = p.int("size")
        if (size == 0) size = p.int("distinct_size")
        if (size == 0) size = (p["commits"] as? JsonArray)?.size ?: 0
        val ref = p.str("ref").replace("refs/heads/", "")
        return when (size) {
            0 -> "force pushed to $ref"
            1 -> "pushed 1 commit to $ref"
            else -> "pushed $size commits to $ref"
        }
    }

    /** Actions shared by issues and pull requests (labels, assignees, milestones, locks). */
    private fun describeIssueOrPr(p: JsonObject, item: JsonObject, noun: String): String {
        val action = p.str("action")
        val number = item.str("number")
        val title = item.title()
        val label = p.obj("label").str("name")
        val assignee = p.obj("assignee").str("login")
        val milestone = p.obj("milestone").str("title")
        val base = when {
            action == "labeled" && label.isNotEmpty() -> "labeled $noun #$number [$label]"
            action == "unlabeled" && label.isNotEmpty() -> "unlabeled $noun #$number [$label]"
            action == "assigned" && assignee.isNotEmpty() -> "assigned $assignee to $noun #$number"
            action == "unassigned" && assignee.isNotEmpty() -> "unassigned $assignee from $noun #$number"
            action == "milestoned" && milestone.isNotEmpty() -> "milestoned $noun #$number [$milestone]"
            action == "demilestoned" && milestone.isNotEmpty() -> "demilestoned $noun #$number [$milestone]"
            else -> "$action $noun #$number"
        }
        return withTitle(base, title)
    }

    private fun describePullRequest(p: JsonObject): String {
        val pr = p.obj("pull_request")
        val number = pr.str("number")
        val title = pr.title()
        val base = when (p.str("action")) {
            "opened" -> "opened PR #$number"
            "reopened" -> "reopened PR #$number"
            "closed" -> if (pr.bool("merged")) "merged PR #$number" else "closed PR #$number"
            "review_requested", "review_request_removed" -> {
                val removed = p.str("action") == "review_request_removed"
                val reviewer = p.obj("requested_reviewer").str("login")
                val team = p.obj("requested_team").str("name")
                val verb = if (removed) "removed review request" else "requested review"
                val prep = if (removed) "for" else "from"
                when {
                    reviewer.isNotEmpty() -> "$verb $prep $reviewer on PR #$number"
                    team.isNotEmpty() -> "$verb $prep team $team on PR #$number"
                    else -> "$verb on PR #$number"
                }
            }
            "ready_for_review" -> "marked PR #$number ready for review"
            "converted_to_draft" -> "converted PR #$number to draft"
            "synchronize" -> "updated PR #$number with new commits"
            else -> return describeIssueOrPr(p, pr, "PR")
        }
        return withTitle(base, title)
    }

    fun webUrl(event: Event): String {
        val p = event.payload
        val base = "https://github.com/${event.repo.name}"
        fun number(key: String) = p.obj(key).str("number").takeIf { it.isNotEmpty() }
        val url: String? = when (event.type) {
            "IssuesEvent" -> number("issue")?.let { "$base/issues/$it" }
            "IssueCommentEvent" -> p.obj("comment").nonEmpty("html_url")
                ?: number("issue")?.let { "$base/issues/$it" }
            "DiscussionEvent" -> p.obj("discussion").nonEmpty("html_url")
                ?: number("discussion")?.let { "$base/discussions/$it" }
            "DiscussionCommentEvent" -> p.obj("comment").nonEmpty("html_url")
                ?: p.obj("discussion").nonEmpty("html_url")
                ?: number("discussion")?.let { "$base/discussions/$it" }
            "PullRequestEvent", "PullRequestReviewEvent" -> number("pull_request")?.let { "$base/pull/$it" }
            "PullRequestReviewCommentEvent" -> p.obj("comment").nonEmpty("html_url")
                ?: number("pull_request")?.let { "$base/pull/$it" }
            "PullRequestReviewThreadEvent" -> p.obj("thread").nonEmpty("html_url")
                ?: number("pull_request")?.let { "$base/pull/$it" }
            "PushEvent" -> {
                val before = p.str("before").take(7)
                val head = p.str("head").take(7)
                if (before.isNotEmpty() && head.isNotEmpty()) "$base/compare/$before...$head" else null
            }
            "ReleaseEvent" -> p.obj("release").nonEmpty("html_url")
            "ForkEvent" -> p.obj("forkee").nonEmpty("html_url")
            "CommitCommentEvent" -> p.obj("comment").nonEmpty("html_url")
            "CreateEvent" -> {
                val ref = p.str("ref")
                when {
                    ref.isEmpty() -> null
                    p.str("ref_type") == "branch" -> "$base/tree/$ref"
                    p.str("ref_type") == "tag" -> "$base/releases/tag/$ref"
                    else -> null
                }
            }
            else -> null
        }
        return url ?: base
    }

    private fun withTitle(base: String, title: String) = if (title.isNotEmpty()) "$base: $title" else base

    private fun JsonObject.title() = str("title").take(50)
}

private val EMPTY = JsonObject(emptyMap())

internal fun JsonObject.obj(key: String): JsonObject = this[key] as? JsonObject ?: EMPTY

internal fun JsonObject.str(key: String, default: String = ""): String {
    val value = this[key]
    return if (value is JsonPrimitive && value !is JsonNull) value.content else default
}

internal fun JsonObject.int(key: String): Int = (this[key] as? JsonPrimitive)?.intOrNull ?: 0

internal fun JsonObject.bool(key: String): Boolean = (this[key] as? JsonPrimitive)?.booleanOrNull ?: false

internal fun JsonObject.nonEmpty(key: String): String? = str(key).takeIf { it.isNotEmpty() }

/** Mirrors Python truthiness for ids: present, non-null, non-zero, non-empty. */
private fun JsonObject.isPresent(key: String): Boolean {
    val value = this[key] as? JsonPrimitive ?: return false
    if (value is JsonNull) return false
    return value.content.isNotEmpty() && value.content != "0" && value.content != "false"
}
