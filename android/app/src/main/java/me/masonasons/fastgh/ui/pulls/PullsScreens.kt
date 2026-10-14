package me.masonasons.fastgh.ui.pulls

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.selection.selectable
import androidx.compose.foundation.selection.selectableGroup
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.RadioButton
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import me.masonasons.fastgh.data.GitHubClient
import me.masonasons.fastgh.data.TokenStore
import me.masonasons.fastgh.model.Comment
import me.masonasons.fastgh.model.PullRequest
import me.masonasons.fastgh.model.plural
import me.masonasons.fastgh.ui.LocalNavigator
import me.masonasons.fastgh.ui.components.ActionListItem
import me.masonasons.fastgh.ui.components.BaseViewModel
import me.masonasons.fastgh.ui.components.BodyText
import me.masonasons.fastgh.ui.components.ComposeDialog
import me.masonasons.fastgh.ui.components.FilterRow
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
import me.masonasons.fastgh.ui.components.shareText
import me.masonasons.fastgh.ui.issues.STATE_FILTERS
import me.masonasons.fastgh.ui.issues.commentsSection
import me.masonasons.fastgh.ui.issues.labelsLine
import kotlinx.coroutines.async
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update

// ============ Pull request list ============

class PullsViewModel(
    private val owner: String,
    private val name: String,
    github: GitHubClient,
    tokenStore: TokenStore,
) : BaseViewModel(github, tokenStore) {
    private val _filter = MutableStateFlow("open")
    val filter: StateFlow<String> = _filter.asStateFlow()

    val list = pagedLoader { page -> github.pulls(owner, name, _filter.value, page) }

    init {
        list.refresh()
    }

    fun setFilter(state: String) {
        _filter.value = state
        list.refresh()
    }
}

@Composable
fun PullsScreen(owner: String, name: String) {
    val navigator = LocalNavigator.current
    val context = LocalContext.current
    val viewModel = appViewModel(key = "pulls/$owner/$name") { PullsViewModel(owner, name, it.github, it.tokenStore) }
    val state by viewModel.list.state.collectAsStateWithLifecycle()
    val filter by viewModel.filter.collectAsStateWithLifecycle()

    ScreenScaffold(title = "Pull requests: $owner/$name", messages = viewModel.messages) { padding, showMessage ->
        Column(Modifier.padding(padding)) {
            FilterRow(STATE_FILTERS, filter, viewModel::setFilter)
            PagedList(
                state = state,
                emptyText = "No ${if (filter == "all") "" else "$filter "}pull requests",
                onRefresh = viewModel.list::refresh,
                onLoadMore = viewModel.list::loadMore,
                key = { it.id },
            ) { pr ->
                ActionListItem(
                    overline = pr.stateDisplay,
                    headline = "#${pr.number} ${pr.title}",
                    supporting = listOfNotNull(
                        "by ${pr.user.login}, ${pr.head.ref} into ${pr.base.ref}, updated ${relativeTime(pr.updatedInstant)}",
                        labelsLine(pr.labels.map { it.name }),
                    ).joinToString("\n"),
                    onClick = { navigator.pull(owner, name, pr.number) },
                    onClickLabel = "View pull request",
                    actions = listOf(
                        RowAction("Open in browser") { context.openUrl(pr.htmlUrl) },
                        RowAction("Copy link") {
                            context.copyToClipboard("Pull request link", pr.htmlUrl)
                            showMessage("Copied ${pr.htmlUrl}")
                        },
                        RowAction("View profile of ${pr.user.login}") { navigator.user(pr.user.login) },
                    ),
                )
            }
        }
    }
}

// ============ Pull request detail ============

data class PullUiState(
    val pull: LoadState<PullRequest> = LoadState.Loading,
    val comments: LoadState<List<Comment>> = LoadState.Loading,
    val canMerge: Boolean = false,
    val sending: Boolean = false,
    val merging: Boolean = false,
)

class PullViewModel(
    private val owner: String,
    private val name: String,
    private val number: Int,
    github: GitHubClient,
    tokenStore: TokenStore,
) : BaseViewModel(github, tokenStore) {
    private val _state = MutableStateFlow(PullUiState())
    val state: StateFlow<PullUiState> = _state.asStateFlow()

    init {
        load()
    }

    fun load() {
        _state.value = PullUiState()
        launchAction {
            // Permission check mirrors the desktop's can_merge (admin or write access).
            val canMerge = async { runCatching { github.repo(owner, name).canPush }.getOrDefault(false) }
            _state.update { it.copy(pull = loadState { github.pull(owner, name, number) }) }
            _state.update { it.copy(canMerge = canMerge.await()) }
            _state.update { it.copy(comments = loadState { github.pullComments(owner, name, number) }) }
        }
    }

    fun comment(body: String, onSent: () -> Unit) {
        _state.update { it.copy(sending = true) }
        launchAction {
            try {
                val comment = github.createComment(owner, name, number, body)
                _state.update { s ->
                    val comments = (s.comments as? LoadState.Loaded)?.value.orEmpty()
                    s.copy(comments = LoadState.Loaded(comments + comment))
                }
                message("Comment posted")
                onSent()
            } finally {
                _state.update { it.copy(sending = false) }
            }
        }
    }

    fun toggleState() {
        val pr = (_state.value.pull as? LoadState.Loaded)?.value ?: return
        launchAction {
            val updated = github.setPullState(owner, name, number, open = !pr.isOpen)
            _state.update { it.copy(pull = LoadState.Loaded(updated)) }
            message(if (updated.isOpen) "Pull request reopened" else "Pull request closed")
        }
    }

    fun merge(method: String, onDone: () -> Unit) {
        _state.update { it.copy(merging = true) }
        launchAction {
            try {
                github.mergePull(owner, name, number, method)
                _state.update { it.copy(pull = LoadState.Loaded(github.pull(owner, name, number))) }
                message("Pull request merged")
                onDone()
            } finally {
                _state.update { it.copy(merging = false) }
            }
        }
    }
}

private val MERGE_METHODS = listOf(
    "merge" to "Create a merge commit",
    "squash" to "Squash and merge",
    "rebase" to "Rebase and merge",
)

@OptIn(ExperimentalLayoutApi::class)
@Composable
fun PullScreen(owner: String, name: String, number: Int) {
    val navigator = LocalNavigator.current
    val context = LocalContext.current
    val viewModel = appViewModel(key = "pull/$owner/$name/$number") {
        PullViewModel(owner, name, number, it.github, it.tokenStore)
    }
    val state by viewModel.state.collectAsStateWithLifecycle()
    var composing by rememberSaveable { mutableStateOf(false) }
    var mergeDialog by rememberSaveable { mutableStateOf(false) }

    ScreenScaffold(title = "Pull request #$number", messages = viewModel.messages) { padding, showMessage ->
        when (val pullState = state.pull) {
            LoadState.Loading -> StatusMessage("Loading pull request…", Modifier.padding(padding), showProgress = true)
            is LoadState.Error -> StatusMessage(
                pullState.message, Modifier.padding(padding), actionLabel = "Retry", onAction = viewModel::load,
            )
            is LoadState.Loaded -> {
                val pr = pullState.value
                LazyColumn(Modifier.fillMaxSize().padding(padding)) {
                    item {
                        Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
                            SectionHeading(pr.title)
                            Text(pullSummary(pr))
                            BodyText(pr.body)
                            FlowRow(
                                horizontalArrangement = Arrangement.spacedBy(8.dp),
                                verticalArrangement = Arrangement.spacedBy(8.dp),
                            ) {
                                Button(onClick = { composing = true }) { Text("Comment") }
                                if (state.canMerge && pr.isOpen && !pr.draft) {
                                    Button(onClick = { mergeDialog = true }) { Text("Merge") }
                                }
                                if (!pr.isMerged) {
                                    OutlinedButton(onClick = viewModel::toggleState) {
                                        Text(if (pr.isOpen) "Close pull request" else "Reopen pull request")
                                    }
                                }
                                OutlinedButton(onClick = { context.openUrl(pr.htmlUrl) }) { Text("Open in browser") }
                                OutlinedButton(onClick = {
                                    context.copyToClipboard("Pull request link", pr.htmlUrl)
                                    showMessage("Copied ${pr.htmlUrl}")
                                }) { Text("Copy link") }
                                OutlinedButton(onClick = { context.shareText(pr.htmlUrl, "Share pull request") }) {
                                    Text("Share")
                                }
                                OutlinedButton(onClick = { navigator.user(pr.user.login) }) { Text("View author") }
                            }
                        }
                    }
                    commentsSection(state.comments, onRetry = viewModel::load, showMessage = showMessage, onViewAuthor = navigator::user)
                }
            }
        }
    }

    if (composing) {
        ComposeDialog(
            title = "Comment on pull request #$number",
            submitLabel = "Post comment",
            sending = state.sending,
            onDismiss = { composing = false },
            onSubmit = { _, body -> viewModel.comment(body) { composing = false } },
        )
    }

    if (mergeDialog) {
        MergeDialog(
            merging = state.merging,
            onDismiss = { mergeDialog = false },
            onMerge = { method -> viewModel.merge(method) { mergeDialog = false } },
        )
    }
}

private fun pullSummary(pr: PullRequest): String = buildList {
    add("${pr.stateDisplay}. Opened by ${pr.user.login} ${relativeTime(pr.createdInstant)}.")
    add("Wants to merge ${plural(pr.commits, "commit")} from ${pr.head.ref} into ${pr.base.ref}.")
    add("${plural(pr.changedFiles, "file")} changed, ${plural(pr.additions, "addition")}, ${plural(pr.deletions, "deletion")}.")
    if (pr.isMerged) {
        add("Merged${pr.mergedBy?.let { " by ${it.login}" }.orEmpty()}.")
    } else if (pr.isOpen) {
        when (pr.mergeable) {
            true -> add("Can be merged.")
            false -> add("Has conflicts that must be resolved before merging.")
            null -> Unit // GitHub is still computing mergeability
        }
    }
    labelsLine(pr.labels.map { it.name })?.let(::add)
}.joinToString("\n")

@Composable
private fun MergeDialog(merging: Boolean, onDismiss: () -> Unit, onMerge: (String) -> Unit) {
    var method by rememberSaveable { mutableStateOf("merge") }
    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text("Merge pull request") },
        text = {
            Column(Modifier.selectableGroup()) {
                MERGE_METHODS.forEach { (value, label) ->
                    Row(
                        Modifier
                            .fillMaxWidth()
                            .selectable(selected = method == value, onClick = { method = value }, role = Role.RadioButton)
                            .padding(vertical = 12.dp),
                        verticalAlignment = Alignment.CenterVertically,
                    ) {
                        RadioButton(selected = method == value, onClick = null)
                        Text(label, Modifier.padding(start = 12.dp))
                    }
                }
            }
        },
        confirmButton = {
            TextButton(onClick = { onMerge(method) }, enabled = !merging) {
                Text(if (merging) "Merging…" else "Merge")
            }
        },
        dismissButton = { TextButton(onClick = onDismiss) { Text("Cancel") } },
    )
}
