package me.masonasons.fastgh.ui.repo

import androidx.compose.foundation.layout.padding
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import me.masonasons.fastgh.data.GitHubClient
import me.masonasons.fastgh.data.TokenStore
import me.masonasons.fastgh.ui.LocalNavigator
import me.masonasons.fastgh.ui.components.ActionListItem
import me.masonasons.fastgh.ui.components.BaseViewModel
import me.masonasons.fastgh.ui.components.PagedList
import me.masonasons.fastgh.ui.components.RepoRow
import me.masonasons.fastgh.ui.components.RowAction
import me.masonasons.fastgh.ui.components.ScreenScaffold
import me.masonasons.fastgh.ui.components.appViewModel
import me.masonasons.fastgh.ui.components.openUrl
import me.masonasons.fastgh.ui.components.relativeTime

class ForksViewModel(owner: String, name: String, github: GitHubClient, tokenStore: TokenStore) :
    BaseViewModel(github, tokenStore) {
    val list = pagedLoader { page -> github.forks(owner, name, page) }

    init {
        list.refresh()
    }
}

@Composable
fun ForksScreen(owner: String, name: String) {
    val navigator = LocalNavigator.current
    val viewModel = appViewModel(key = "forks/$owner/$name") { ForksViewModel(owner, name, it.github, it.tokenStore) }
    val state by viewModel.list.state.collectAsStateWithLifecycle()

    ScreenScaffold(title = "Forks of $owner/$name", messages = viewModel.messages) { padding, showMessage ->
        PagedList(
            state = state,
            emptyText = "No forks",
            onRefresh = viewModel.list::refresh,
            onLoadMore = viewModel.list::loadMore,
            modifier = Modifier.padding(padding),
            key = { it.id },
        ) { fork ->
            RepoRow(
                fork,
                onOpen = { navigator.repo(fork.owner.login, fork.name) },
                onViewOwner = { navigator.user(fork.owner.login) },
                onMessage = showMessage,
            )
        }
    }
}

class StargazersViewModel(owner: String, name: String, github: GitHubClient, tokenStore: TokenStore) :
    BaseViewModel(github, tokenStore) {
    val list = pagedLoader { page -> github.stargazers(owner, name, page) }

    init {
        list.refresh()
    }
}

@Composable
fun StargazersScreen(owner: String, name: String) {
    val navigator = LocalNavigator.current
    val context = LocalContext.current
    val viewModel = appViewModel(key = "stargazers/$owner/$name") {
        StargazersViewModel(owner, name, it.github, it.tokenStore)
    }
    val state by viewModel.list.state.collectAsStateWithLifecycle()

    ScreenScaffold(title = "Stargazers of $owner/$name", messages = viewModel.messages) { padding, _ ->
        PagedList(
            state = state,
            emptyText = "No stargazers yet",
            onRefresh = viewModel.list::refresh,
            onLoadMore = viewModel.list::loadMore,
            modifier = Modifier.padding(padding),
            key = { it.user.login },
        ) { stargazer ->
            val login = stargazer.user.login
            ActionListItem(
                headline = login,
                supporting = stargazer.starredInstant?.let { "Starred ${relativeTime(it)}" },
                onClick = { navigator.user(login) },
                onClickLabel = "View profile",
                actions = listOf(RowAction("Open in browser") { context.openUrl("https://github.com/$login") }),
            )
        }
    }
}
