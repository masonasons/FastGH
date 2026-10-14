package me.masonasons.fastgh.model

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable
import kotlinx.serialization.json.JsonObject
import java.time.Instant

@Serializable
data class Owner(val login: String = "")

@Serializable
data class ParentRepo(@SerialName("full_name") val fullName: String = "")

@Serializable
data class RepoPermissions(val admin: Boolean = false, val push: Boolean = false, val pull: Boolean = false)

@Serializable
data class Repository(
    val id: Long = 0,
    val name: String = "",
    @SerialName("full_name") val fullName: String = "",
    val description: String? = null,
    val owner: Owner = Owner(),
    @SerialName("stargazers_count") val stars: Int = 0,
    @SerialName("forks_count") val forks: Int = 0,
    @SerialName("open_issues_count") val openIssues: Int = 0,
    val language: String? = null,
    @SerialName("pushed_at") val pushedAt: String? = null,
    @SerialName("html_url") val htmlUrl: String = "",
    val private: Boolean = false,
    val fork: Boolean = false,
    @SerialName("default_branch") val defaultBranch: String? = null,
    // Only returned when fetching a single repository.
    val parent: ParentRepo? = null,
    // The signed-in user's access; only returned to authenticated requests.
    val permissions: RepoPermissions? = null,
) {
    /** Matches the desktop's can_merge: admin or write access. */
    val canPush: Boolean get() = permissions?.let { it.admin || it.push } ?: false
    val pushedInstant: Instant? get() = parseInstant(pushedAt)
    val cloneUrl: String get() = "https://github.com/$fullName.git"
}

@Serializable
data class UserProfile(
    val id: Long = 0,
    val login: String = "",
    val name: String? = null,
    @SerialName("html_url") val htmlUrl: String = "",
    val bio: String? = null,
    val company: String? = null,
    val location: String? = null,
    val email: String? = null,
    val blog: String? = null,
    @SerialName("twitter_username") val twitterUsername: String? = null,
    @SerialName("public_repos") val publicRepos: Int = 0,
    val followers: Int = 0,
    val following: Int = 0,
    @SerialName("created_at") val createdAt: String? = null,
    val type: String = "User",
) {
    val displayName: String get() = name?.takeIf { it.isNotBlank() } ?: login
}

@Serializable
data class NotificationSubject(
    val title: String = "",
    val url: String? = null,
    val type: String = "",
)

@Serializable
data class NotificationRepo(
    val name: String = "",
    @SerialName("full_name") val fullName: String = "",
    val owner: Owner = Owner(),
)

@Serializable
data class Notification(
    val id: String = "",
    val unread: Boolean = false,
    val reason: String = "",
    val subject: NotificationSubject = NotificationSubject(),
    val repository: NotificationRepo = NotificationRepo(),
    @SerialName("updated_at") val updatedAt: String? = null,
) {
    val updatedInstant: Instant? get() = parseInstant(updatedAt)

    val reasonDisplay: String get() = REASONS[reason] ?: reason

    val typeDisplay: String
        get() = when (subject.type) {
            "PullRequest" -> "Pull request"
            "RepositoryVulnerabilityAlert" -> "Security alert"
            else -> subject.type
        }

    /** The subject's web page, converted from its API URL. */
    val webUrl: String
        get() = subject.url
            ?.takeIf { it.isNotBlank() }
            ?.replace("api.github.com/repos", "github.com")
            ?.replace("/pulls/", "/pull/")
            ?: "https://github.com/${repository.fullName}"

    companion object {
        val REASONS = mapOf(
            "assign" to "You were assigned",
            "author" to "You created the thread",
            "comment" to "You commented",
            "ci_activity" to "CI activity",
            "invitation" to "You were invited",
            "manual" to "You subscribed manually",
            "mention" to "You were mentioned",
            "review_requested" to "Review requested",
            "security_alert" to "Security alert",
            "state_change" to "State changed",
            "subscribed" to "You're watching the repo",
            "team_mention" to "Your team was mentioned",
        )
    }
}

@Serializable
data class EventRepo(val name: String = "")

@Serializable
data class Event(
    val id: String = "",
    val type: String = "",
    val actor: Owner = Owner(),
    val repo: EventRepo = EventRepo(),
    val payload: JsonObject = JsonObject(emptyMap()),
    @SerialName("created_at") val createdAt: String? = null,
) {
    val createdInstant: Instant? get() = parseInstant(createdAt)
    val description: String get() = EventDescriber.describe(this)
    val webUrl: String get() = EventDescriber.webUrl(this)

    /** Owner and name of the event's repository, if it has the usual owner/name form. */
    val repoOwnerAndName: Pair<String, String>?
        get() = repo.name.split("/").takeIf { it.size == 2 }?.let { it[0] to it[1] }
}

@Serializable
data class DeviceCode(
    @SerialName("device_code") val deviceCode: String,
    @SerialName("user_code") val userCode: String,
    @SerialName("verification_uri") val verificationUri: String,
    @SerialName("expires_in") val expiresIn: Int = 900,
    val interval: Int = 5,
)

@Serializable
data class TokenResponse(
    @SerialName("access_token") val accessToken: String? = null,
    val error: String? = null,
)

fun parseInstant(value: String?): Instant? =
    value?.let { runCatching { Instant.parse(it) }.getOrNull() }
