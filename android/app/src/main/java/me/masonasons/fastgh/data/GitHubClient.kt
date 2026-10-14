package me.masonasons.fastgh.data

import me.masonasons.fastgh.model.Branch
import me.masonasons.fastgh.model.Comment
import me.masonasons.fastgh.model.Commit
import me.masonasons.fastgh.model.ContentItem
import me.masonasons.fastgh.model.Event
import me.masonasons.fastgh.model.Issue
import me.masonasons.fastgh.model.Notification
import me.masonasons.fastgh.model.PullRequest
import me.masonasons.fastgh.model.Release
import me.masonasons.fastgh.model.Repository
import me.masonasons.fastgh.model.SearchResults
import me.masonasons.fastgh.model.StarredUser
import me.masonasons.fastgh.model.UserProfile
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import kotlinx.serialization.Serializable
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.decodeFromJsonElement
import kotlinx.serialization.json.put
import okhttp3.HttpUrl
import okhttp3.HttpUrl.Companion.toHttpUrl
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody
import okhttp3.RequestBody.Companion.toRequestBody
import okhttp3.Response
import java.time.Instant

class GitHubException(val code: Int, message: String) : Exception(message)

/** Thrown when the token is missing or revoked; the app signs out. */
class UnauthorizedException : Exception("Your GitHub session has expired. Please sign in again.")

/** One page of a paged list, and whether GitHub has another page after it. */
data class Page<T>(val items: List<T>, val hasMore: Boolean)

val json = Json {
    ignoreUnknownKeys = true
    coerceInputValues = true
    explicitNulls = false
}

/**
 * GitHub REST API client. Mirrors the endpoints the desktop app's github_api.py uses.
 */
class GitHubClient(
    private val http: OkHttpClient,
    private val tokenProvider: () -> String?,
    private val baseUrl: String = "https://api.github.com",
) {
    // ============ Users ============

    suspend fun currentUser(): UserProfile = getJson("/user")

    suspend fun user(login: String): UserProfile = getJson("/users/$login")

    suspend fun userRepos(login: String): List<Repository> =
        getAllPages("/users/$login/repos", mapOf("sort" to "pushed", "direction" to "desc"))

    suspend fun following(): List<UserProfile> = getAllPages("/user/following")

    suspend fun isFollowing(login: String): Boolean = status("GET", "/user/following/$login") == 204

    suspend fun setFollowing(login: String, follow: Boolean): Boolean =
        status(if (follow) "PUT" else "DELETE", "/user/following/$login") == 204

    // ============ Repositories ============

    suspend fun myRepos(): List<Repository> = getAllPages(
        "/user/repos",
        mapOf(
            "sort" to "pushed",
            "direction" to "desc",
            "affiliation" to "owner,collaborator,organization_member",
        ),
    )

    suspend fun starred(): List<Repository> = getAllPages<Repository>("/user/starred").sortedByPushed()

    suspend fun watched(): List<Repository> = getAllPages<Repository>("/user/subscriptions").sortedByPushed()

    suspend fun repo(owner: String, name: String): Repository = getJson("/repos/$owner/$name")

    suspend fun isStarred(owner: String, name: String): Boolean =
        status("GET", "/user/starred/$owner/$name") == 204

    suspend fun setStarred(owner: String, name: String, star: Boolean): Boolean =
        status(if (star) "PUT" else "DELETE", "/user/starred/$owner/$name") == 204

    suspend fun isWatching(owner: String, name: String): Boolean =
        status("GET", "/repos/$owner/$name/subscription") == 200

    suspend fun setWatching(owner: String, name: String, watch: Boolean): Boolean =
        if (watch) {
            status("PUT", "/repos/$owner/$name/subscription", """{"subscribed":true}""") == 200
        } else {
            status("DELETE", "/repos/$owner/$name/subscription") == 204
        }

    suspend fun forks(owner: String, name: String, page: Int): Page<Repository> =
        getPage("/repos/$owner/$name/forks", page, params = mapOf("sort" to "newest"))

    /** Uses the star media type so each entry carries when the user starred. */
    suspend fun stargazers(owner: String, name: String, page: Int): Page<StarredUser> =
        getPage("/repos/$owner/$name/stargazers", page, perPage = 100, accept = "application/vnd.github.star+json")

    // ============ Issues ============

    /** One page of issues; the issues endpoint also returns pull requests, which are dropped. */
    suspend fun issues(owner: String, name: String, state: String, page: Int): Page<Issue> {
        val result = getPage<Issue>("/repos/$owner/$name/issues", page, params = mapOf("state" to state))
        return result.copy(items = result.items.filter { it.pullRequest == null })
    }

    suspend fun issue(owner: String, name: String, number: Int): Issue =
        getJson("/repos/$owner/$name/issues/$number")

    suspend fun issueComments(owner: String, name: String, number: Int): List<Comment> =
        getAllPages("/repos/$owner/$name/issues/$number/comments")

    suspend fun createIssue(owner: String, name: String, title: String, body: String): Issue =
        sendJson("POST", "/repos/$owner/$name/issues", buildJsonObject {
            put("title", title)
            put("body", body)
        }.toString())

    /** Comments on issues and pull requests share this endpoint. */
    suspend fun createComment(owner: String, name: String, number: Int, body: String): Comment =
        sendJson("POST", "/repos/$owner/$name/issues/$number/comments", buildJsonObject {
            put("body", body)
        }.toString())

    suspend fun setIssueState(owner: String, name: String, number: Int, open: Boolean): Issue =
        sendJson("PATCH", "/repos/$owner/$name/issues/$number", stateBody(open))

    // ============ Pull requests ============

    suspend fun pulls(owner: String, name: String, state: String, page: Int): Page<PullRequest> =
        getPage("/repos/$owner/$name/pulls", page, params = mapOf("state" to state))

    suspend fun pull(owner: String, name: String, number: Int): PullRequest =
        getJson("/repos/$owner/$name/pulls/$number")

    /** Conversation and review comments together, oldest first, like the desktop app. */
    suspend fun pullComments(owner: String, name: String, number: Int): List<Comment> {
        val conversation = issueComments(owner, name, number)
        val review = getAllPages<Comment>("/repos/$owner/$name/pulls/$number/comments")
        return (conversation + review).sortedBy { it.createdInstant ?: Instant.EPOCH }
    }

    suspend fun setPullState(owner: String, name: String, number: Int, open: Boolean): PullRequest =
        sendJson("PATCH", "/repos/$owner/$name/pulls/$number", stateBody(open))

    /** method is "merge", "squash" or "rebase". */
    suspend fun mergePull(owner: String, name: String, number: Int, method: String) {
        sendJson<MergeResult>("PUT", "/repos/$owner/$name/pulls/$number/merge", buildJsonObject {
            put("merge_method", method)
        }.toString())
    }

    // ============ Commits ============

    suspend fun commits(owner: String, name: String, branch: String?, page: Int): Page<Commit> =
        getPage("/repos/$owner/$name/commits", page, params = branch?.let { mapOf("sha" to it) } ?: emptyMap())

    suspend fun commit(owner: String, name: String, sha: String): Commit =
        getJson("/repos/$owner/$name/commits/$sha")

    suspend fun branches(owner: String, name: String): List<Branch> =
        getAllPages("/repos/$owner/$name/branches")

    // ============ Releases ============

    suspend fun releases(owner: String, name: String, page: Int): Page<Release> =
        getPage("/repos/$owner/$name/releases", page, perPage = 30)

    suspend fun release(owner: String, name: String, id: Long): Release =
        getJson("/repos/$owner/$name/releases/$id")

    // ============ Files ============

    /** Directory listing, directories first then files, each alphabetical (like the desktop). */
    suspend fun directory(owner: String, name: String, path: String, ref: String? = null): List<ContentItem> {
        val element = getJson<kotlinx.serialization.json.JsonElement>(contentsPath(owner, name, path), refParam(ref))
        val items = (element as? JsonArray)
            ?.map { json.decodeFromJsonElement<ContentItem>(it) }
            ?: throw GitHubException(400, "$path is a file, not a folder.")
        return items.sortedWith(compareBy({ !it.isDir }, { it.name.lowercase() }))
    }

    suspend fun file(owner: String, name: String, path: String, ref: String? = null): ContentItem =
        getJson(contentsPath(owner, name, path), refParam(ref))

    private fun refParam(ref: String?) = ref?.let { mapOf("ref" to it) } ?: emptyMap()

    private fun contentsPath(owner: String, name: String, path: String) =
        "/repos/$owner/$name/contents/" + path.split("/").joinToString("/") { it.encodePathSegment() }

    // ============ Search ============

    suspend fun searchRepos(query: String, sort: String?): SearchResults<Repository> =
        getJson("/search/repositories", searchParams(query, sort))

    suspend fun searchUsers(query: String, sort: String?): SearchResults<UserProfile> =
        getJson("/search/users", searchParams(query, sort))

    private fun searchParams(query: String, sort: String?) =
        mapOf("q" to query, "per_page" to "50") + (sort?.let { mapOf("sort" to it) } ?: emptyMap())

    // ============ Activity ============

    /** The activity feed. GitHub caps this at 300 events. */
    suspend fun receivedEvents(login: String): List<Event> =
        getAllPages("/users/$login/received_events", maxPages = 3)

    suspend fun notifications(): List<Notification> = getAllPages("/notifications", perPage = 50)

    suspend fun markThreadRead(id: String): Boolean =
        status("PATCH", "/notifications/threads/$id") in setOf(200, 205)

    suspend fun markThreadDone(id: String): Boolean =
        status("DELETE", "/notifications/threads/$id") == 204

    suspend fun muteThread(id: String): Boolean =
        status("PUT", "/notifications/threads/$id/subscription", """{"ignored":true}""") == 200

    suspend fun markAllNotificationsRead(): Boolean =
        status("PUT", "/notifications", "{}") in setOf(202, 205)

    // ============ Plumbing ============

    private suspend inline fun <reified T> getJson(path: String, params: Map<String, String> = emptyMap()): T {
        val body = execute(request(url(path, params))) { response ->
            if (!response.isSuccessful) throw httpError(response)
            response.body.string()
        }
        return json.decodeFromString(body)
    }

    private suspend inline fun <reified T> sendJson(method: String, path: String, body: String): T {
        val request = request(url(path)).newBuilder()
            .method(method, body.toRequestBody(JSON_MEDIA))
            .build()
        val text = execute(request) { response ->
            if (!response.isSuccessful) throw httpError(response)
            response.body.string()
        }
        return json.decodeFromString(text)
    }

    private suspend inline fun <reified T> getPage(
        path: String,
        page: Int,
        perPage: Int = 50,
        params: Map<String, String> = emptyMap(),
        accept: String = DEFAULT_ACCEPT,
    ): Page<T> {
        val url = url(path, params + mapOf("per_page" to "$perPage", "page" to "$page"))
        val (body, hasNext) = execute(request(url, accept)) { response ->
            if (!response.isSuccessful) throw httpError(response)
            // GitHub sends a rel="next" link while more pages remain.
            response.body.string() to (response.header("Link")?.contains("rel=\"next\"") == true)
        }
        return Page(json.decodeFromString(body), hasNext)
    }

    private suspend inline fun <reified T> getAllPages(
        path: String,
        params: Map<String, String> = emptyMap(),
        perPage: Int = 100,
        maxPages: Int = 20,
    ): List<T> {
        val items = mutableListOf<T>()
        for (page in 1..maxPages) {
            val result = getPage<T>(path, page, perPage, params)
            items += result.items
            if (!result.hasMore || result.items.size < perPage) break
        }
        return items
    }

    private suspend fun status(method: String, path: String, jsonBody: String? = null): Int {
        val body: RequestBody? = when {
            jsonBody != null -> jsonBody.toRequestBody(JSON_MEDIA)
            method == "PUT" || method == "PATCH" -> ByteArray(0).toRequestBody(null)
            else -> null
        }
        val request = request(url(path)).newBuilder().method(method, body).build()
        return execute(request) { it.code }
    }

    private fun stateBody(open: Boolean) =
        buildJsonObject { put("state", if (open) "open" else "closed") }.toString()

    private fun url(path: String, params: Map<String, String> = emptyMap()): HttpUrl =
        (baseUrl + path).toHttpUrl().newBuilder().apply {
            params.forEach { (key, value) -> addQueryParameter(key, value) }
        }.build()

    private fun request(url: HttpUrl, accept: String = DEFAULT_ACCEPT): Request {
        val builder = Request.Builder()
            .url(url)
            .header("Accept", accept)
            .header("X-GitHub-Api-Version", "2022-11-28")
        tokenProvider()?.let { builder.header("Authorization", "Bearer $it") }
        return builder.build()
    }

    private suspend fun <T> execute(request: Request, handle: (Response) -> T): T =
        withContext(Dispatchers.IO) {
            http.newCall(request).execute().use { response ->
                if (response.code == 401) throw UnauthorizedException()
                handle(response)
            }
        }

    private fun httpError(response: Response): GitHubException {
        val message = runCatching {
            json.decodeFromString<ErrorBody>(response.body.string()).message
        }.getOrNull()
        return GitHubException(response.code, message ?: "GitHub returned HTTP ${response.code}")
    }

    @Serializable
    private data class ErrorBody(val message: String? = null)

    @Serializable
    private data class MergeResult(val merged: Boolean = false, val message: String? = null)

    private fun List<Repository>.sortedByPushed() = sortedByDescending { it.pushedInstant ?: Instant.EPOCH }

    private fun String.encodePathSegment(): String =
        HttpUrl.Builder().scheme("https").host("x").addPathSegment(this).build().encodedPath.removePrefix("/")

    private companion object {
        const val DEFAULT_ACCEPT = "application/vnd.github+json"
        val JSON_MEDIA = "application/json".toMediaType()
    }
}
