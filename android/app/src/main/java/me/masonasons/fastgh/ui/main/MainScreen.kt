package me.masonasons.fastgh.ui.main

import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.text.KeyboardActions
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.MoreVert
import androidx.compose.material.icons.filled.Refresh
import androidx.compose.material.icons.filled.Search
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.DropdownMenu
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.PrimaryScrollableTabRow
import androidx.compose.material3.Scaffold
import androidx.compose.material3.SnackbarHost
import androidx.compose.material3.SnackbarHostState
import androidx.compose.material3.Tab
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.TopAppBar
import androidx.compose.material3.pulltorefresh.PullToRefreshBox
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.focus.FocusRequester
import androidx.compose.ui.focus.focusRequester
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.input.ImeAction
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import me.masonasons.fastgh.model.Event
import me.masonasons.fastgh.model.Notification
import me.masonasons.fastgh.model.Repository
import me.masonasons.fastgh.model.UserProfile
import me.masonasons.fastgh.model.parseRepoInput
import me.masonasons.fastgh.ui.LocalNavigator
import me.masonasons.fastgh.ui.SearchRoute
import me.masonasons.fastgh.ui.routeForEvent
import me.masonasons.fastgh.ui.routeForNotification
import me.masonasons.fastgh.ui.components.ActionListItem
import me.masonasons.fastgh.ui.components.LoadState
import me.masonasons.fastgh.ui.components.RepoRow
import me.masonasons.fastgh.ui.components.RowAction
import me.masonasons.fastgh.ui.components.StatusMessage
import me.masonasons.fastgh.ui.components.appViewModel
import me.masonasons.fastgh.ui.components.copyToClipboard
import me.masonasons.fastgh.ui.components.openUrl
import me.masonasons.fastgh.ui.components.relativeTime
import me.masonasons.fastgh.ui.components.shareText
import kotlinx.coroutines.launch

private enum class PromptKind { Repo, User }

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun MainScreen() {
    val navigator = LocalNavigator.current
    val onOpenRepo = navigator::repo
    val onOpenUser = navigator::user
    val viewModel = appViewModel { MainViewModel(it.github, it.tokenStore) }
    val state by viewModel.state.collectAsStateWithLifecycle()
    val snackbar = remember { SnackbarHostState() }
    val scope = rememberCoroutineScope()
    val showMessage: (String) -> Unit = { message -> scope.launch { snackbar.showSnackbar(message) } }

    var selectedTab by rememberSaveable { mutableStateOf(MainTab.Feed) }
    var menuOpen by remember { mutableStateOf(false) }
    var prompt by remember { mutableStateOf<PromptKind?>(null) }

    LaunchedEffect(viewModel) {
        viewModel.messages.collect { snackbar.showSnackbar(it) }
    }

    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text("FastGH") },
                actions = {
                    IconButton(onClick = { navigator.go(SearchRoute) }) {
                        Icon(Icons.Default.Search, contentDescription = "Search GitHub")
                    }
                    IconButton(onClick = { viewModel.refresh(selectedTab) }) {
                        Icon(Icons.Default.Refresh, contentDescription = "Refresh ${selectedTab.title}")
                    }
                    IconButton(onClick = { menuOpen = true }) {
                        Icon(Icons.Default.MoreVert, contentDescription = "More options")
                    }
                    DropdownMenu(expanded = menuOpen, onDismissRequest = { menuOpen = false }) {
                        DropdownMenuItem(
                            text = { Text("Refresh all") },
                            onClick = { menuOpen = false; viewModel.refreshAll() },
                        )
                        DropdownMenuItem(
                            text = { Text("Go to repository…") },
                            onClick = { menuOpen = false; prompt = PromptKind.Repo },
                        )
                        DropdownMenuItem(
                            text = { Text("View user profile…") },
                            onClick = { menuOpen = false; prompt = PromptKind.User },
                        )
                        DropdownMenuItem(
                            text = { Text("Mark all notifications read") },
                            onClick = { menuOpen = false; viewModel.markAllRead() },
                        )
                        DropdownMenuItem(
                            text = { Text("Sign out") },
                            onClick = { menuOpen = false; viewModel.signOut() },
                        )
                    }
                },
            )
        },
        snackbarHost = { SnackbarHost(snackbar) },
    ) { padding ->
        Column(Modifier.fillMaxSize().padding(padding)) {
            PrimaryScrollableTabRow(selectedTabIndex = selectedTab.ordinal) {
                MainTab.entries.forEach { tab ->
                    val label = if (tab == MainTab.Notifications && state.unreadCount > 0) {
                        "${tab.title} (${state.unreadCount})"
                    } else {
                        tab.title
                    }
                    Tab(
                        selected = tab == selectedTab,
                        onClick = { selectedTab = tab },
                        text = { Text(label) },
                    )
                }
            }
            PullToRefreshBox(
                isRefreshing = selectedTab in state.refreshing && selectedTab.load(state) is LoadState.Loaded,
                onRefresh = { viewModel.refresh(selectedTab) },
                modifier = Modifier.fillMaxSize(),
            ) {
                val retry = { viewModel.refresh(selectedTab) }
                when (selectedTab) {
                    MainTab.Feed -> LoadedList(state.feed, "No recent activity", retry) { events ->
                        items(events, key = { it.id }) { event ->
                            FeedRow(event, onOpenRepo, onOpenUser, showMessage)
                        }
                    }
                    MainTab.Repos, MainTab.Starred, MainTab.Watched -> {
                        @Suppress("UNCHECKED_CAST")
                        val repos = selectedTab.load(state) as LoadState<List<Repository>>
                        LoadedList(repos, "No repositories", retry) { list ->
                            items(list, key = { it.id }) { repo ->
                                RepoRow(
                                    repo,
                                    onOpen = { onOpenRepo(repo.owner.login, repo.name) },
                                    onViewOwner = { onOpenUser(repo.owner.login) },
                                    onMessage = showMessage,
                                )
                            }
                        }
                    }
                    MainTab.Following -> LoadedList(state.following, "You aren't following anyone", retry) { users ->
                        items(users, key = { it.login }) { user ->
                            FollowingRow(user, onOpenUser, onUnfollow = { viewModel.unfollow(user) })
                        }
                    }
                    MainTab.Notifications -> LoadedList(state.notifications, "No unread notifications", retry) { list ->
                        items(list, key = { it.id }) { notification ->
                            NotificationRow(notification, viewModel, onOpenRepo, showMessage)
                        }
                    }
                }
            }
        }
    }

    prompt?.let { kind ->
        when (kind) {
            PromptKind.Repo -> TextPrompt(
                title = "Go to repository",
                label = "Repository URL or owner/repo",
                onDismiss = { prompt = null },
                onSubmit = { text ->
                    val parsed = parseRepoInput(text)
                    if (parsed != null) {
                        prompt = null
                        onOpenRepo(parsed.first, parsed.second)
                    } else {
                        showMessage("Enter a GitHub URL or owner/repo, like octocat/Hello-World.")
                    }
                },
            )
            PromptKind.User -> TextPrompt(
                title = "View user profile",
                label = "GitHub username",
                onDismiss = { prompt = null },
                onSubmit = { text ->
                    prompt = null
                    onOpenUser(text.trim().removePrefix("@"))
                },
            )
        }
    }
}

private fun MainTab.load(state: MainUiState): LoadState<List<Any>> = when (this) {
    MainTab.Feed -> state.feed
    MainTab.Repos -> state.repos
    MainTab.Starred -> state.starred
    MainTab.Watched -> state.watched
    MainTab.Following -> state.following
    MainTab.Notifications -> state.notifications
}

@Composable
private fun <T> LoadedList(
    state: LoadState<List<T>>,
    emptyText: String,
    onRetry: () -> Unit,
    content: androidx.compose.foundation.lazy.LazyListScope.(List<T>) -> Unit,
) {
    when (state) {
        LoadState.Loading -> StatusMessage("Loading…", showProgress = true)
        is LoadState.Error -> StatusMessage(state.message, actionLabel = "Retry", onAction = onRetry)
        is LoadState.Loaded -> if (state.value.isEmpty()) {
            // Still scrollable so pull-to-refresh works on an empty tab.
            LazyColumn(Modifier.fillMaxSize()) { item { StatusMessage(emptyText) } }
        } else {
            LazyColumn(Modifier.fillMaxSize()) { content(state.value) }
        }
    }
}

@Composable
private fun FeedRow(
    event: Event,
    onOpenRepo: (String, String) -> Unit,
    onOpenUser: (String) -> Unit,
    onMessage: (String) -> Unit,
) {
    val context = LocalContext.current
    val navigator = LocalNavigator.current
    val ownerAndName = event.repoOwnerAndName
    val route = routeForEvent(event)
    val actions = buildList {
        if (route != null) add(RowAction("Open on GitHub") { context.openUrl(event.webUrl) })
        if (ownerAndName != null) {
            add(RowAction("View repository") { onOpenRepo(ownerAndName.first, ownerAndName.second) })
        }
        add(RowAction("View profile of ${event.actor.login}") { onOpenUser(event.actor.login) })
        add(RowAction("Copy link") {
            context.copyToClipboard("Link", event.webUrl)
            onMessage("Copied ${event.webUrl}")
        })
        add(RowAction("Share") { context.shareText(event.webUrl, "Share link") })
    }
    ActionListItem(
        headline = "${event.actor.login} ${event.description}",
        supporting = "in ${event.repo.name}, ${relativeTime(event.createdInstant)}",
        onClick = { if (route != null) navigator.go(route) else context.openUrl(event.webUrl) },
        onClickLabel = if (route != null) "Open" else "Open on GitHub",
        actions = actions,
    )
}

@Composable
private fun FollowingRow(user: UserProfile, onOpenUser: (String) -> Unit, onUnfollow: () -> Unit) {
    val context = LocalContext.current
    ActionListItem(
        headline = user.login,
        supporting = user.name,
        onClick = { onOpenUser(user.login) },
        onClickLabel = "View profile",
        actions = listOf(
            RowAction("Open in browser") { context.openUrl(user.htmlUrl) },
            RowAction("Unfollow") { onUnfollow() },
        ),
    )
}

@Composable
private fun NotificationRow(
    notification: Notification,
    viewModel: MainViewModel,
    onOpenRepo: (String, String) -> Unit,
    onMessage: (String) -> Unit,
) {
    val context = LocalContext.current
    val navigator = LocalNavigator.current
    val repo = notification.repository
    val route = routeForNotification(notification)
    val actions = buildList {
        if (route != null) add(RowAction("Open on GitHub") { context.openUrl(notification.webUrl) })
        if (notification.unread) add(RowAction("Mark as read") { viewModel.markRead(notification) })
        add(RowAction("Mark as done") { viewModel.markDone(notification) })
        add(RowAction("Mute thread") { viewModel.mute(notification) })
        add(RowAction("View repository") { onOpenRepo(repo.owner.login, repo.name) })
        add(RowAction("Copy link") {
            context.copyToClipboard("Link", notification.webUrl)
            onMessage("Copied ${notification.webUrl}")
        })
    }
    ActionListItem(
        overline = if (notification.unread) "Unread" else null,
        headline = notification.subject.title,
        supporting = "${notification.typeDisplay} in ${repo.fullName}, ${notification.reasonDisplay}, " +
            relativeTime(notification.updatedInstant),
        onClick = {
            if (route != null) navigator.go(route) else context.openUrl(notification.webUrl)
            if (notification.unread) viewModel.markRead(notification)
        },
        onClickLabel = if (route != null) "Open" else "Open on GitHub",
        actions = actions,
    )
}

@Composable
private fun TextPrompt(
    title: String,
    label: String,
    onDismiss: () -> Unit,
    onSubmit: (String) -> Unit,
) {
    var text by rememberSaveable { mutableStateOf("") }
    val focus = remember { FocusRequester() }
    LaunchedEffect(Unit) { focus.requestFocus() }
    val submit = { if (text.isNotBlank()) onSubmit(text) }
    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text(title) },
        text = {
            OutlinedTextField(
                value = text,
                onValueChange = { text = it },
                label = { Text(label) },
                singleLine = true,
                keyboardOptions = KeyboardOptions(imeAction = ImeAction.Go, autoCorrectEnabled = false),
                keyboardActions = KeyboardActions(onGo = { submit() }),
                modifier = Modifier.focusRequester(focus),
            )
        },
        confirmButton = { TextButton(onClick = submit) { Text("Go") } },
        dismissButton = { TextButton(onClick = onDismiss) { Text("Cancel") } },
    )
}
