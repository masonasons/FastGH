package me.masonasons.fastgh.ui.repo

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Button
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import me.masonasons.fastgh.data.GitHubClient
import me.masonasons.fastgh.data.TokenStore
import me.masonasons.fastgh.model.Repository
import me.masonasons.fastgh.ui.CommitsRoute
import me.masonasons.fastgh.ui.FilesRoute
import me.masonasons.fastgh.ui.ForksRoute
import me.masonasons.fastgh.ui.IssuesRoute
import me.masonasons.fastgh.ui.LocalNavigator
import me.masonasons.fastgh.ui.PullsRoute
import me.masonasons.fastgh.ui.ReleasesRoute
import me.masonasons.fastgh.ui.StargazersRoute
import me.masonasons.fastgh.ui.components.BaseViewModel
import me.masonasons.fastgh.ui.components.LoadState
import me.masonasons.fastgh.ui.components.ScreenScaffold
import me.masonasons.fastgh.ui.components.SectionHeading
import me.masonasons.fastgh.ui.components.StatusMessage
import me.masonasons.fastgh.ui.components.appViewModel
import me.masonasons.fastgh.ui.components.copyToClipboard
import me.masonasons.fastgh.ui.components.openUrl
import me.masonasons.fastgh.ui.components.relativeTime
import me.masonasons.fastgh.ui.components.shareText
import me.masonasons.fastgh.ui.splitFullName
import kotlinx.coroutines.async
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update

data class RepoUiState(
    val repo: LoadState<Repository> = LoadState.Loading,
    val starred: Boolean? = null, // null while unknown
    val watching: Boolean? = null,
)

class RepoViewModel(
    private val owner: String,
    private val name: String,
    github: GitHubClient,
    tokenStore: TokenStore,
) : BaseViewModel(github, tokenStore) {
    private val _state = MutableStateFlow(RepoUiState())
    val state: StateFlow<RepoUiState> = _state.asStateFlow()

    init {
        load()
    }

    fun load() {
        _state.value = RepoUiState()
        launchAction {
            val starred = async { runCatching { github.isStarred(owner, name) }.getOrNull() }
            val watching = async { runCatching { github.isWatching(owner, name) }.getOrNull() }
            val repo = loadState { github.repo(owner, name) }
            _state.value = RepoUiState(repo, starred.await(), watching.await())
        }
    }

    fun toggleStar() {
        val star = _state.value.starred?.not() ?: return
        launchAction {
            if (github.setStarred(owner, name, star)) {
                _state.update { it.copy(starred = star) }
                message(if (star) "Starred $owner/$name" else "Unstarred $owner/$name")
            } else {
                message("Couldn't ${if (star) "star" else "unstar"} $owner/$name.")
            }
        }
    }

    fun toggleWatch() {
        val watch = _state.value.watching?.not() ?: return
        launchAction {
            if (github.setWatching(owner, name, watch)) {
                _state.update { it.copy(watching = watch) }
                message(if (watch) "Watching $owner/$name" else "Stopped watching $owner/$name")
            } else {
                message("Couldn't ${if (watch) "watch" else "unwatch"} $owner/$name.")
            }
        }
    }
}

@OptIn(ExperimentalLayoutApi::class)
@Composable
fun RepoScreen(owner: String, name: String) {
    val navigator = LocalNavigator.current
    val context = LocalContext.current
    val viewModel = appViewModel(key = "repo/$owner/$name") { RepoViewModel(owner, name, it.github, it.tokenStore) }
    val state by viewModel.state.collectAsStateWithLifecycle()

    ScreenScaffold(title = "$owner/$name", messages = viewModel.messages) { padding, showMessage ->
        when (val repoState = state.repo) {
            LoadState.Loading -> StatusMessage("Loading repository…", Modifier.padding(padding), showProgress = true)
            is LoadState.Error -> StatusMessage(
                repoState.message,
                Modifier.padding(padding),
                actionLabel = "Retry",
                onAction = viewModel::load,
            )
            is LoadState.Loaded -> {
                val repo = repoState.value
                Column(
                    Modifier
                        .fillMaxSize()
                        .padding(padding)
                        .verticalScroll(rememberScrollState())
                        .padding(16.dp),
                    verticalArrangement = Arrangement.spacedBy(12.dp),
                ) {
                    SectionHeading("Description")
                    Text(repo.description?.takeIf { it.isNotBlank() } ?: "No description")

                    SectionHeading("Details")
                    repoDetails(repo).forEach { line ->
                        Text(line, style = MaterialTheme.typography.bodyMedium)
                    }

                    SectionHeading("Browse")
                    FlowRow(
                        horizontalArrangement = Arrangement.spacedBy(8.dp),
                        verticalArrangement = Arrangement.spacedBy(8.dp),
                    ) {
                        OutlinedButton(onClick = { navigator.go(FilesRoute(owner, name)) }) { Text("Files") }
                        OutlinedButton(onClick = { navigator.go(IssuesRoute(owner, name)) }) { Text("Issues") }
                        OutlinedButton(onClick = { navigator.go(PullsRoute(owner, name)) }) { Text("Pull requests") }
                        OutlinedButton(onClick = { navigator.go(CommitsRoute(owner, name)) }) { Text("Commits") }
                        OutlinedButton(onClick = { navigator.go(ReleasesRoute(owner, name)) }) { Text("Releases") }
                        OutlinedButton(onClick = { navigator.go(ForksRoute(owner, name)) }) { Text("Forks") }
                        OutlinedButton(onClick = { navigator.go(StargazersRoute(owner, name)) }) { Text("Stargazers") }
                    }

                    SectionHeading("Actions")
                    FlowRow(
                        horizontalArrangement = Arrangement.spacedBy(8.dp),
                        verticalArrangement = Arrangement.spacedBy(8.dp),
                    ) {
                        Button(onClick = viewModel::toggleStar, enabled = state.starred != null) {
                            Text(if (state.starred == true) "Unstar" else "Star")
                        }
                        Button(onClick = viewModel::toggleWatch, enabled = state.watching != null) {
                            Text(if (state.watching == true) "Unwatch" else "Watch")
                        }
                        OutlinedButton(onClick = { context.openUrl(repo.htmlUrl) }) {
                            Text("Open in browser")
                        }
                        OutlinedButton(onClick = {
                            context.copyToClipboard("Repository URL", repo.htmlUrl)
                            showMessage("Copied ${repo.htmlUrl}")
                        }) {
                            Text("Copy URL")
                        }
                        OutlinedButton(onClick = {
                            context.copyToClipboard("Clone URL", repo.cloneUrl)
                            showMessage("Copied ${repo.cloneUrl}")
                        }) {
                            Text("Copy clone URL")
                        }
                        OutlinedButton(onClick = { context.shareText(repo.htmlUrl, "Share ${repo.fullName}") }) {
                            Text("Share")
                        }
                        OutlinedButton(onClick = { navigator.user(repo.owner.login) }) {
                            Text("View owner")
                        }
                        repo.parent?.fullName?.let(::splitFullName)?.let { (parentOwner, parentName) ->
                            OutlinedButton(onClick = { navigator.repo(parentOwner, parentName) }) {
                                Text("View upstream")
                            }
                        }
                    }
                }
            }
        }
    }
}

private fun repoDetails(repo: Repository): List<String> = buildList {
    add("Owner: ${repo.owner.login}")
    add("Language: ${repo.language ?: "Not specified"}")
    add("Stars: ${repo.stars}")
    add("Forks: ${repo.forks}")
    add("Open issues: ${repo.openIssues}")
    add("Visibility: ${if (repo.private) "Private" else "Public"}")
    repo.defaultBranch?.let { add("Default branch: $it") }
    if (repo.fork) add(repo.parent?.let { "Forked from: ${it.fullName}" } ?: "Fork: Yes")
    repo.pushedInstant?.let { add("Last push: ${relativeTime(it)}") }
    add("URL: ${repo.htmlUrl}")
}
