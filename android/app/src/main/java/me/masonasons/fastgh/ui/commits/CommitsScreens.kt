package me.masonasons.fastgh.ui.commits

import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.text.selection.SelectionContainer
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.semantics.selected
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import me.masonasons.fastgh.data.GitHubClient
import me.masonasons.fastgh.data.TokenStore
import me.masonasons.fastgh.model.Branch
import me.masonasons.fastgh.model.Commit
import me.masonasons.fastgh.model.plural
import me.masonasons.fastgh.ui.FileRoute
import me.masonasons.fastgh.ui.LocalNavigator
import me.masonasons.fastgh.ui.components.ActionListItem
import me.masonasons.fastgh.ui.components.BaseViewModel
import me.masonasons.fastgh.ui.components.LoadState
import me.masonasons.fastgh.ui.components.PagedList
import me.masonasons.fastgh.ui.components.RowAction
import me.masonasons.fastgh.ui.components.ScreenScaffold
import me.masonasons.fastgh.ui.components.SectionHeading
import me.masonasons.fastgh.ui.components.StatusMessage
import me.masonasons.fastgh.ui.components.appViewModel
import me.masonasons.fastgh.ui.components.copyToClipboard
import me.masonasons.fastgh.ui.components.openUrl
import me.masonasons.fastgh.ui.components.relativeTime
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow

// ============ Commit list ============

class CommitsViewModel(
    private val owner: String,
    private val name: String,
    initialBranch: String?,
    github: GitHubClient,
    tokenStore: TokenStore,
) : BaseViewModel(github, tokenStore) {
    /** Null means the repository's default branch. */
    private val _branch = MutableStateFlow(initialBranch)
    val branch: StateFlow<String?> = _branch.asStateFlow()

    private val _branches = MutableStateFlow<LoadState<List<Branch>>>(LoadState.Loading)
    val branches: StateFlow<LoadState<List<Branch>>> = _branches.asStateFlow()

    private val _defaultBranch = MutableStateFlow<String?>(null)
    val defaultBranch: StateFlow<String?> = _defaultBranch.asStateFlow()

    val list = pagedLoader { page -> github.commits(owner, name, _branch.value, page) }

    init {
        list.refresh()
        launchAction {
            _defaultBranch.value = runCatching { github.repo(owner, name).defaultBranch }.getOrNull()
            _branches.value = loadState { github.branches(owner, name) }
        }
    }

    fun selectBranch(branch: String) {
        _branch.value = branch
        list.refresh()
    }
}

@Composable
fun CommitsScreen(owner: String, name: String, initialBranch: String?) {
    val navigator = LocalNavigator.current
    val context = LocalContext.current
    val viewModel = appViewModel(key = "commits/$owner/$name/$initialBranch") {
        CommitsViewModel(owner, name, initialBranch, it.github, it.tokenStore)
    }
    val state by viewModel.list.state.collectAsStateWithLifecycle()
    val branch by viewModel.branch.collectAsStateWithLifecycle()
    val defaultBranch by viewModel.defaultBranch.collectAsStateWithLifecycle()
    val branches by viewModel.branches.collectAsStateWithLifecycle()
    var picking by rememberSaveable { mutableStateOf(false) }
    val currentBranch = branch ?: defaultBranch

    ScreenScaffold(title = "Commits: $owner/$name", messages = viewModel.messages) { padding, showMessage ->
        Column(Modifier.padding(padding)) {
            OutlinedButton(
                onClick = { picking = true },
                modifier = Modifier.fillMaxWidth().padding(8.dp),
            ) {
                Text("Branch: ${currentBranch ?: "default"}. Change branch")
            }
            PagedList(
                state = state,
                emptyText = "No commits",
                onRefresh = viewModel.list::refresh,
                onLoadMore = viewModel.list::loadMore,
                key = { it.sha },
            ) { commit ->
                ActionListItem(
                    headline = commit.firstLine,
                    supporting = "${commit.authorName}, ${relativeTime(commit.dateInstant)}, ${commit.shortSha}",
                    onClick = { navigator.commit(owner, name, commit.sha) },
                    onClickLabel = "View commit",
                    actions = listOf(
                        RowAction("Copy SHA") {
                            context.copyToClipboard("Commit SHA", commit.sha)
                            showMessage("Copied ${commit.shortSha}")
                        },
                        RowAction("Open in browser") { context.openUrl(commit.htmlUrl) },
                        RowAction("Browse files at this commit") {
                            navigator.go(me.masonasons.fastgh.ui.FilesRoute(owner, name, ref = commit.sha))
                        },
                    ),
                )
            }
        }
    }

    if (picking) {
        BranchPicker(
            branches = branches,
            current = currentBranch,
            onDismiss = { picking = false },
            onPick = {
                picking = false
                viewModel.selectBranch(it)
            },
        )
    }
}

@Composable
private fun BranchPicker(
    branches: LoadState<List<Branch>>,
    current: String?,
    onDismiss: () -> Unit,
    onPick: (String) -> Unit,
) {
    var filter by rememberSaveable { mutableStateOf("") }
    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text("Choose branch") },
        text = {
            Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                OutlinedTextField(
                    value = filter,
                    onValueChange = { filter = it },
                    label = { Text("Search branches") },
                    singleLine = true,
                    modifier = Modifier.fillMaxWidth(),
                )
                when (branches) {
                    LoadState.Loading -> Text("Loading branches…")
                    is LoadState.Error -> Text(branches.message)
                    is LoadState.Loaded -> {
                        val matching = remember(branches, filter) {
                            branches.value.filter { it.name.contains(filter.trim(), ignoreCase = true) }
                        }
                        if (matching.isEmpty()) Text("No matching branches")
                        LazyColumn(Modifier.heightIn(max = 360.dp)) {
                            items(matching, key = { it.name }) { branch ->
                                val isCurrent = branch.name == current
                                Text(
                                    branch.name + if (isCurrent) " (current)" else "",
                                    modifier = Modifier
                                        .fillMaxWidth()
                                        .semantics { selected = isCurrent }
                                        .clickable(role = Role.Button) { onPick(branch.name) }
                                        .padding(vertical = 12.dp),
                                )
                            }
                        }
                    }
                }
            }
        },
        confirmButton = { TextButton(onClick = onDismiss) { Text("Cancel") } },
    )
}

// ============ Commit detail ============

class CommitViewModel(
    private val owner: String,
    private val name: String,
    private val sha: String,
    github: GitHubClient,
    tokenStore: TokenStore,
) : BaseViewModel(github, tokenStore) {
    private val _commit = MutableStateFlow<LoadState<Commit>>(LoadState.Loading)
    val commit: StateFlow<LoadState<Commit>> = _commit.asStateFlow()

    init {
        load()
    }

    fun load() {
        _commit.value = LoadState.Loading
        launchAction { _commit.value = loadState { github.commit(owner, name, sha) } }
    }
}

@OptIn(ExperimentalLayoutApi::class)
@Composable
fun CommitScreen(owner: String, name: String, sha: String) {
    val navigator = LocalNavigator.current
    val context = LocalContext.current
    val viewModel = appViewModel(key = "commit/$owner/$name/$sha") {
        CommitViewModel(owner, name, sha, it.github, it.tokenStore)
    }
    val commitState by viewModel.commit.collectAsStateWithLifecycle()

    ScreenScaffold(title = "Commit ${sha.take(7)}", messages = viewModel.messages) { padding, showMessage ->
        when (val s = commitState) {
            LoadState.Loading -> StatusMessage("Loading commit…", Modifier.padding(padding), showProgress = true)
            is LoadState.Error -> StatusMessage(
                s.message, Modifier.padding(padding), actionLabel = "Retry", onAction = viewModel::load,
            )
            is LoadState.Loaded -> {
                val commit = s.value
                LazyColumn(Modifier.fillMaxSize().padding(padding)) {
                    item {
                        Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
                            SectionHeading(commit.firstLine)
                            Text(
                                buildList {
                                    add("By ${commit.commit.author.name}" +
                                        commit.author?.login?.let { " ($it)" }.orEmpty() +
                                        ", ${relativeTime(commit.dateInstant)}.")
                                    commit.stats?.let {
                                        add("${plural(commit.files.size, "file")} changed, " +
                                            "${plural(it.additions, "addition")}, ${plural(it.deletions, "deletion")}.")
                                    }
                                }.joinToString("\n"),
                            )
                            SelectionContainer {
                                Text(commit.commit.message, style = MaterialTheme.typography.bodyMedium)
                            }
                            Text("SHA: ${commit.sha}", fontFamily = FontFamily.Monospace)
                            FlowRow(
                                horizontalArrangement = Arrangement.spacedBy(8.dp),
                                verticalArrangement = Arrangement.spacedBy(8.dp),
                            ) {
                                OutlinedButton(onClick = {
                                    context.copyToClipboard("Commit SHA", commit.sha)
                                    showMessage("Copied ${commit.shortSha}")
                                }) { Text("Copy SHA") }
                                OutlinedButton(onClick = {
                                    context.copyToClipboard("Commit message", commit.commit.message)
                                    showMessage("Commit message copied")
                                }) { Text("Copy message") }
                                OutlinedButton(onClick = { context.openUrl(commit.htmlUrl) }) { Text("Open in browser") }
                                commit.author?.login?.let { login ->
                                    OutlinedButton(onClick = { navigator.user(login) }) { Text("View author") }
                                }
                            }
                            SectionHeading("Changed files (${commit.files.size})")
                        }
                    }
                    items(commit.files, key = { it.filename }) { file ->
                        val removed = file.status == "removed"
                        ActionListItem(
                            headline = file.display,
                            onClick = {
                                if (removed) {
                                    showMessage("${file.filename} was removed in this commit.")
                                } else {
                                    navigator.go(FileRoute(owner, name, file.filename, ref = commit.sha))
                                }
                            },
                            onClickLabel = "View file at this commit",
                            actions = listOf(
                                RowAction("Copy file name") {
                                    context.copyToClipboard("File name", file.filename)
                                    showMessage("Copied ${file.filename}")
                                },
                                RowAction("Open changes in browser") { context.openUrl(commit.htmlUrl) },
                            ),
                        )
                    }
                }
            }
        }
    }
}
