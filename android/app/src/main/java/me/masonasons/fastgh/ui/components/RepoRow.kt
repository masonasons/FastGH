package me.masonasons.fastgh.ui.components

import androidx.compose.runtime.Composable
import androidx.compose.ui.platform.LocalContext
import me.masonasons.fastgh.model.Repository
import me.masonasons.fastgh.ui.CommitsRoute
import me.masonasons.fastgh.ui.FilesRoute
import me.masonasons.fastgh.ui.IssuesRoute
import me.masonasons.fastgh.ui.LocalNavigator
import me.masonasons.fastgh.ui.PullsRoute
import me.masonasons.fastgh.ui.ReleasesRoute

/** One-line summary spoken after the description, e.g. "250 stars, Kotlin, pushed 3 days ago". */
fun Repository.statsLine(): String = buildList {
    add(if (stars == 1) "1 star" else "$stars stars")
    language?.let(::add)
    if (fork) add("fork")
    if (private) add("private")
    add("pushed ${relativeTime(pushedInstant)}")
}.joinToString(", ")

@Composable
fun RepoRow(
    repo: Repository,
    onOpen: () -> Unit,
    onViewOwner: (() -> Unit)?,
    onMessage: (String) -> Unit,
) {
    val context = LocalContext.current
    val navigator = LocalNavigator.current
    val actions = buildList {
        val (owner, name) = repo.owner.login to repo.name
        add(RowAction("View commits") { navigator.go(CommitsRoute(owner, name)) })
        add(RowAction("View issues") { navigator.go(IssuesRoute(owner, name)) })
        add(RowAction("View pull requests") { navigator.go(PullsRoute(owner, name)) })
        add(RowAction("View files") { navigator.go(FilesRoute(owner, name)) })
        add(RowAction("View releases") { navigator.go(ReleasesRoute(owner, name)) })
        add(RowAction("Open in browser") { context.openUrl(repo.htmlUrl) })
        add(RowAction("Copy URL") {
            context.copyToClipboard("Repository URL", repo.htmlUrl)
            onMessage("Copied ${repo.htmlUrl}")
        })
        add(RowAction("Copy clone URL") {
            context.copyToClipboard("Clone URL", repo.cloneUrl)
            onMessage("Copied ${repo.cloneUrl}")
        })
        add(RowAction("Share") { context.shareText(repo.htmlUrl, "Share ${repo.fullName}") })
        if (onViewOwner != null) add(RowAction("View owner, ${repo.owner.login}", onViewOwner))
    }
    ActionListItem(
        headline = repo.fullName,
        supporting = listOfNotNull(repo.description?.takeIf { it.isNotBlank() }, repo.statsLine())
            .joinToString("\n"),
        onClick = onOpen,
        onClickLabel = "View repository",
        actions = actions,
    )
}
