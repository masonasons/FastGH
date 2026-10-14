package me.masonasons.fastgh.ui.issues

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.Button
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import me.masonasons.fastgh.data.GitHubClient
import me.masonasons.fastgh.data.TokenStore
import me.masonasons.fastgh.model.Comment
import me.masonasons.fastgh.model.Issue
import me.masonasons.fastgh.model.plural
import me.masonasons.fastgh.ui.LocalNavigator
import me.masonasons.fastgh.ui.components.ActionListItem
import me.masonasons.fastgh.ui.components.BaseViewModel
import me.masonasons.fastgh.ui.components.BodyText
import me.masonasons.fastgh.ui.components.CommentItem
import me.masonasons.fastgh.ui.components.ComposeDialog
import me.masonasons.fastgh.ui.components.FilterRow
import me.masonasons.fastgh.ui.components.LoadState
import me.masonasons.fastgh.ui.components.PagedList
import me.masonasons.fastgh.ui.components.RowAction
import me.masonasons.fastgh.ui.components.ScreenScaffold
import me.masonasons.fastgh.ui.components.SectionHeading
import me.masonasons.fastgh.ui.components.StatusMessage
import me.masonasons.fastgh.ui.components.TopBarTextButton
import me.masonasons.fastgh.ui.components.appViewModel
import me.masonasons.fastgh.ui.components.copyToClipboard
import me.masonasons.fastgh.ui.components.openUrl
import me.masonasons.fastgh.ui.components.relativeTime
import me.masonasons.fastgh.ui.components.shareText
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update

/** Open / closed / all, as the API's state parameter. */
val STATE_FILTERS = listOf("open" to "Open", "closed" to "Closed", "all" to "All")

/** Labels and assignees, spoken after the title: "Labels: bug, ui. Assigned to bob." */
fun labelsLine(labels: List<String>): String? = labels.takeIf { it.isNotEmpty() }?.joinToString(", ", "Labels: ")

// ============ Issue list ============

class IssuesViewModel(
    private val owner: String,
    private val name: String,
    github: GitHubClient,
    tokenStore: TokenStore,
) : BaseViewModel(github, tokenStore) {
    private val _filter = MutableStateFlow("open")
    val filter: StateFlow<String> = _filter.asStateFlow()

    private val _creating = MutableStateFlow(false)
    val creating: StateFlow<Boolean> = _creating.asStateFlow()

    val list = pagedLoader { page -> github.issues(owner, name, _filter.value, page) }

    init {
        list.refresh()
    }

    fun setFilter(state: String) {
        _filter.value = state
        list.refresh()
    }

    fun create(title: String, body: String, onCreated: (Issue) -> Unit) {
        _creating.value = true
        launchAction {
            try {
                val issue = github.createIssue(owner, name, title, body)
                message("Created issue #${issue.number}")
                onCreated(issue)
            } finally {
                _creating.value = false
            }
        }
    }
}

@Composable
fun IssuesScreen(owner: String, name: String) {
    val navigator = LocalNavigator.current
    val viewModel = appViewModel(key = "issues/$owner/$name") { IssuesViewModel(owner, name, it.github, it.tokenStore) }
    val state by viewModel.list.state.collectAsStateWithLifecycle()
    val filter by viewModel.filter.collectAsStateWithLifecycle()
    val creating by viewModel.creating.collectAsStateWithLifecycle()
    var composing by rememberSaveable { mutableStateOf(false) }

    ScreenScaffold(
        title = "Issues: $owner/$name",
        messages = viewModel.messages,
        actions = { TopBarTextButton("New issue") { composing = true } },
    ) { padding, showMessage ->
        Column(Modifier.padding(padding)) {
            FilterRow(STATE_FILTERS, filter, viewModel::setFilter)
            PagedList(
                state = state,
                emptyText = "No ${if (filter == "all") "" else "$filter "}issues",
                onRefresh = viewModel.list::refresh,
                onLoadMore = viewModel.list::loadMore,
                key = { it.id },
            ) { issue -> IssueRow(owner, name, issue, showMessage) }
        }
    }

    if (composing) {
        ComposeDialog(
            title = "New issue in $owner/$name",
            submitLabel = "Create issue",
            sending = creating,
            withTitleField = true,
            bodyLabel = "Description (optional)",
            onDismiss = { composing = false },
            onSubmit = { title, body ->
                viewModel.create(title, body) { issue ->
                    composing = false
                    viewModel.list.refresh()
                    navigator.issue(owner, name, issue.number)
                }
            },
        )
    }
}

@Composable
private fun IssueRow(owner: String, name: String, issue: Issue, onMessage: (String) -> Unit) {
    val navigator = LocalNavigator.current
    val context = LocalContext.current
    ActionListItem(
        overline = issue.stateDisplay,
        headline = "#${issue.number} ${issue.title}",
        supporting = listOfNotNull(
            "by ${issue.user.login}, ${plural(issue.comments, "comment")}, updated ${relativeTime(issue.updatedInstant)}",
            labelsLine(issue.labels.map { it.name }),
        ).joinToString("\n"),
        onClick = { navigator.issue(owner, name, issue.number) },
        onClickLabel = "View issue",
        actions = listOf(
            RowAction("Open in browser") { context.openUrl(issue.htmlUrl) },
            RowAction("Copy link") {
                context.copyToClipboard("Issue link", issue.htmlUrl)
                onMessage("Copied ${issue.htmlUrl}")
            },
            RowAction("View profile of ${issue.user.login}") { navigator.user(issue.user.login) },
        ),
    )
}

// ============ Issue detail ============

data class IssueUiState(
    val issue: LoadState<Issue> = LoadState.Loading,
    val comments: LoadState<List<Comment>> = LoadState.Loading,
    val sending: Boolean = false,
)

class IssueViewModel(
    private val owner: String,
    private val name: String,
    private val number: Int,
    github: GitHubClient,
    tokenStore: TokenStore,
) : BaseViewModel(github, tokenStore) {
    private val _state = MutableStateFlow(IssueUiState())
    val state: StateFlow<IssueUiState> = _state.asStateFlow()

    init {
        load()
    }

    fun load() {
        _state.value = IssueUiState()
        launchAction {
            _state.update { it.copy(issue = loadState { github.issue(owner, name, number) }) }
            _state.update { it.copy(comments = loadState { github.issueComments(owner, name, number) }) }
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
        val issue = (_state.value.issue as? LoadState.Loaded)?.value ?: return
        launchAction {
            val updated = github.setIssueState(owner, name, number, open = !issue.isOpen)
            _state.update { it.copy(issue = LoadState.Loaded(updated)) }
            message(if (updated.isOpen) "Issue reopened" else "Issue closed")
        }
    }
}

@OptIn(ExperimentalLayoutApi::class)
@Composable
fun IssueScreen(owner: String, name: String, number: Int) {
    val navigator = LocalNavigator.current
    val context = LocalContext.current
    val viewModel = appViewModel(key = "issue/$owner/$name/$number") {
        IssueViewModel(owner, name, number, it.github, it.tokenStore)
    }
    val state by viewModel.state.collectAsStateWithLifecycle()
    var composing by rememberSaveable { mutableStateOf(false) }

    ScreenScaffold(title = "Issue #$number", messages = viewModel.messages) { padding, showMessage ->
        when (val issueState = state.issue) {
            LoadState.Loading -> StatusMessage("Loading issue…", Modifier.padding(padding), showProgress = true)
            is LoadState.Error -> StatusMessage(
                issueState.message, Modifier.padding(padding), actionLabel = "Retry", onAction = viewModel::load,
            )
            is LoadState.Loaded -> {
                val issue = issueState.value
                LazyColumn(Modifier.fillMaxSize().padding(padding)) {
                    item {
                        Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
                            SectionHeading(issue.title)
                            Text(
                                listOfNotNull(
                                    "${issue.stateDisplay}. Opened by ${issue.user.login} ${relativeTime(issue.createdInstant)}.",
                                    labelsLine(issue.labels.map { it.name }),
                                    issue.assignees.takeIf { it.isNotEmpty() }
                                        ?.joinToString(", ", "Assigned to ") { it.login },
                                ).joinToString("\n"),
                            )
                            BodyText(issue.body)
                            FlowRow(
                                horizontalArrangement = Arrangement.spacedBy(8.dp),
                                verticalArrangement = Arrangement.spacedBy(8.dp),
                            ) {
                                Button(onClick = { composing = true }) { Text("Comment") }
                                OutlinedButton(onClick = viewModel::toggleState) {
                                    Text(if (issue.isOpen) "Close issue" else "Reopen issue")
                                }
                                OutlinedButton(onClick = { context.openUrl(issue.htmlUrl) }) { Text("Open in browser") }
                                OutlinedButton(onClick = {
                                    context.copyToClipboard("Issue link", issue.htmlUrl)
                                    showMessage("Copied ${issue.htmlUrl}")
                                }) { Text("Copy link") }
                                OutlinedButton(onClick = { context.shareText(issue.htmlUrl, "Share issue") }) {
                                    Text("Share")
                                }
                                OutlinedButton(onClick = { navigator.user(issue.user.login) }) { Text("View author") }
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
            title = "Comment on issue #$number",
            submitLabel = "Post comment",
            sending = state.sending,
            onDismiss = { composing = false },
            onSubmit = { _, body -> viewModel.comment(body) { composing = false } },
        )
    }
}

/** The "Comments (n)" heading and the comments, shared by issues and pull requests. */
fun androidx.compose.foundation.lazy.LazyListScope.commentsSection(
    comments: LoadState<List<Comment>>,
    onRetry: () -> Unit,
    showMessage: (String) -> Unit,
    onViewAuthor: (String) -> Unit,
) {
    val loaded = (comments as? LoadState.Loaded)?.value
    item {
        SectionHeading(
            if (loaded != null) "Comments (${loaded.size})" else "Comments",
            Modifier.padding(horizontal = 16.dp, vertical = 8.dp),
        )
    }
    when (comments) {
        LoadState.Loading -> item { StatusMessage("Loading comments…", showProgress = true) }
        is LoadState.Error -> item { StatusMessage(comments.message, actionLabel = "Retry", onAction = onRetry) }
        is LoadState.Loaded -> if (comments.value.isEmpty()) {
            item { Text("No comments yet.", Modifier.padding(16.dp)) }
        } else {
            // Review comments (which have a path) and conversation comments use separate id spaces.
            items(comments.value, key = { "${it.path != null}:${it.id}" }) { comment ->
                CommentItem(comment, onViewAuthor = onViewAuthor, onMessage = showMessage)
            }
        }
    }
}
