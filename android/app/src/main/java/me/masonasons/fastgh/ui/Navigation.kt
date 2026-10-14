package me.masonasons.fastgh.ui

import androidx.compose.runtime.staticCompositionLocalOf
import androidx.navigation.NavHostController
import kotlinx.serialization.Serializable

@Serializable object SignInRoute
@Serializable object MainRoute
@Serializable object SearchRoute
@Serializable data class RepoRoute(val owner: String, val name: String)
@Serializable data class UserRoute(val login: String)
@Serializable data class IssuesRoute(val owner: String, val name: String)
@Serializable data class IssueRoute(val owner: String, val name: String, val number: Int)
@Serializable data class PullsRoute(val owner: String, val name: String)
@Serializable data class PullRoute(val owner: String, val name: String, val number: Int)
@Serializable data class CommitsRoute(val owner: String, val name: String, val branch: String? = null)
@Serializable data class CommitRoute(val owner: String, val name: String, val sha: String)
@Serializable data class ReleasesRoute(val owner: String, val name: String)
@Serializable data class ReleaseRoute(val owner: String, val name: String, val id: Long)
@Serializable data class FilesRoute(val owner: String, val name: String, val path: String = "", val ref: String? = null)
@Serializable data class FileRoute(val owner: String, val name: String, val path: String, val ref: String? = null)
@Serializable data class ForksRoute(val owner: String, val name: String)
@Serializable data class StargazersRoute(val owner: String, val name: String)

/** Screen-to-screen navigation, available to every screen through [LocalNavigator]. */
class Navigator(private val nav: NavHostController) {
    fun back() {
        nav.popBackStack()
    }

    fun go(route: Any) = nav.navigate(route)

    fun repo(owner: String, name: String) = go(RepoRoute(owner, name))
    fun user(login: String) = go(UserRoute(login))
    fun issue(owner: String, name: String, number: Int) = go(IssueRoute(owner, name, number))
    fun pull(owner: String, name: String, number: Int) = go(PullRoute(owner, name, number))
    fun commit(owner: String, name: String, sha: String) = go(CommitRoute(owner, name, sha))
}

val LocalNavigator = staticCompositionLocalOf<Navigator> { error("No Navigator provided") }

/** Splits "owner/name" into its parts, or null if it isn't in that form. */
fun splitFullName(fullName: String): Pair<String, String>? =
    fullName.split("/").takeIf { it.size == 2 && it.none(String::isEmpty) }?.let { it[0] to it[1] }
