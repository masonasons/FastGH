package me.masonasons.fastgh.model

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable
import kotlinx.serialization.json.JsonObject
import java.time.Instant

@Serializable
data class Label(val name: String = "", val color: String = "", val description: String? = null)

@Serializable
data class BranchRef(val ref: String = "")

@Serializable
data class Issue(
    val id: Long = 0,
    val number: Int = 0,
    val title: String = "",
    val body: String? = null,
    val state: String = "open",
    val user: Owner = Owner(),
    val labels: List<Label> = emptyList(),
    val assignees: List<Owner> = emptyList(),
    val comments: Int = 0,
    @SerialName("created_at") val createdAt: String? = null,
    @SerialName("updated_at") val updatedAt: String? = null,
    @SerialName("html_url") val htmlUrl: String = "",
    // Present only when this "issue" is actually a pull request.
    @SerialName("pull_request") val pullRequest: JsonObject? = null,
) {
    val isOpen: Boolean get() = state == "open"
    val stateDisplay: String get() = if (isOpen) "Open" else "Closed"
    val createdInstant: Instant? get() = parseInstant(createdAt)
    val updatedInstant: Instant? get() = parseInstant(updatedAt)
}

@Serializable
data class PullRequest(
    val id: Long = 0,
    val number: Int = 0,
    val title: String = "",
    val body: String? = null,
    val state: String = "open",
    val user: Owner = Owner(),
    val labels: List<Label> = emptyList(),
    val head: BranchRef = BranchRef(),
    val base: BranchRef = BranchRef(),
    val merged: Boolean = false,
    @SerialName("merged_at") val mergedAt: String? = null,
    @SerialName("merged_by") val mergedBy: Owner? = null,
    val mergeable: Boolean? = null,
    @SerialName("mergeable_state") val mergeableState: String? = null,
    val draft: Boolean = false,
    val comments: Int = 0,
    val commits: Int = 0,
    val additions: Int = 0,
    val deletions: Int = 0,
    @SerialName("changed_files") val changedFiles: Int = 0,
    @SerialName("created_at") val createdAt: String? = null,
    @SerialName("updated_at") val updatedAt: String? = null,
    @SerialName("html_url") val htmlUrl: String = "",
) {
    // The list endpoint omits "merged"; a merge time means it was merged.
    val isMerged: Boolean get() = merged || mergedAt != null
    val isOpen: Boolean get() = state == "open"
    val stateDisplay: String
        get() = when {
            isMerged -> "Merged"
            isOpen && draft -> "Draft"
            isOpen -> "Open"
            else -> "Closed"
        }
    val createdInstant: Instant? get() = parseInstant(createdAt)
    val updatedInstant: Instant? get() = parseInstant(updatedAt)
}

@Serializable
data class Comment(
    val id: Long = 0,
    val body: String? = null,
    val user: Owner = Owner(),
    @SerialName("created_at") val createdAt: String? = null,
    @SerialName("html_url") val htmlUrl: String = "",
    // Set for pull request review comments, which are attached to a line of a file.
    val path: String? = null,
) {
    val createdInstant: Instant? get() = parseInstant(createdAt)
}

@Serializable
data class GitPerson(val name: String = "", val email: String = "", val date: String? = null)

@Serializable
data class CommitDetails(
    val message: String = "",
    val author: GitPerson = GitPerson(),
)

@Serializable
data class CommitStats(val additions: Int = 0, val deletions: Int = 0, val total: Int = 0)

@Serializable
data class CommitFile(
    val filename: String = "",
    val status: String = "modified",
    val additions: Int = 0,
    val deletions: Int = 0,
    @SerialName("previous_filename") val previousFilename: String? = null,
) {
    /** e.g. "Modified: src/app.py, 3 additions, 1 deletion". */
    val display: String
        get() {
            val name = if (status == "renamed" && previousFilename != null) {
                "$previousFilename to $filename"
            } else {
                filename
            }
            return "${status.replaceFirstChar { it.uppercase() }}: $name, " +
                "${plural(additions, "addition")}, ${plural(deletions, "deletion")}"
        }
}

@Serializable
data class Commit(
    val sha: String = "",
    @SerialName("html_url") val htmlUrl: String = "",
    val commit: CommitDetails = CommitDetails(),
    // The GitHub account behind the commit, when it maps to one.
    val author: Owner? = null,
    val stats: CommitStats? = null,
    val files: List<CommitFile> = emptyList(),
) {
    val shortSha: String get() = sha.take(7)
    val firstLine: String get() = commit.message.lineSequence().firstOrNull().orEmpty()
    val authorName: String get() = author?.login?.takeIf { it.isNotEmpty() } ?: commit.author.name
    val dateInstant: Instant? get() = parseInstant(commit.author.date)
}

@Serializable
data class Branch(val name: String = "")

@Serializable
data class ReleaseAsset(
    val id: Long = 0,
    val name: String = "",
    val size: Long = 0,
    @SerialName("download_count") val downloadCount: Int = 0,
    @SerialName("browser_download_url") val downloadUrl: String = "",
    @SerialName("content_type") val contentType: String? = null,
)

@Serializable
data class Release(
    val id: Long = 0,
    @SerialName("tag_name") val tagName: String = "",
    val name: String? = null,
    val body: String? = null,
    val draft: Boolean = false,
    val prerelease: Boolean = false,
    @SerialName("created_at") val createdAt: String? = null,
    @SerialName("published_at") val publishedAt: String? = null,
    @SerialName("html_url") val htmlUrl: String = "",
    val author: Owner? = null,
    val assets: List<ReleaseAsset> = emptyList(),
) {
    val title: String get() = name?.takeIf { it.isNotBlank() && it != tagName }?.let { "$tagName: $it" } ?: tagName
    val status: String
        get() = when {
            draft -> "Draft"
            prerelease -> "Pre-release"
            else -> "Release"
        }
    val totalDownloads: Int get() = assets.sumOf { it.downloadCount }
    val publishedInstant: Instant? get() = parseInstant(publishedAt ?: createdAt)
}

@Serializable
data class ContentItem(
    val name: String = "",
    val path: String = "",
    val type: String = "file", // file, dir, symlink or submodule
    val size: Long = 0,
    @SerialName("html_url") val htmlUrl: String? = null,
    val content: String? = null,
    val encoding: String? = null,
) {
    val isDir: Boolean get() = type == "dir"
}

@Serializable
data class StarredUser(
    @SerialName("starred_at") val starredAt: String? = null,
    val user: Owner = Owner(),
) {
    val starredInstant: Instant? get() = parseInstant(starredAt)
}

@Serializable
data class SearchResults<T>(
    @SerialName("total_count") val totalCount: Int = 0,
    val items: List<T> = emptyList(),
)

fun plural(count: Int, noun: String): String = if (count == 1) "1 $noun" else "$count ${noun}s"

/** Human-readable size, matching the desktop's B / KB / MB formatting. */
fun formatSize(bytes: Long): String = when {
    bytes < 1024 -> "$bytes B"
    bytes < 1024 * 1024 -> "%.1f KB".format(bytes / 1024.0)
    else -> "%.1f MB".format(bytes / (1024.0 * 1024.0))
}
