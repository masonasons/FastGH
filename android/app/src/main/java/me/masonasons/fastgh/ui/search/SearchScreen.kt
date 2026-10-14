package me.masonasons.fastgh.ui.search

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.text.KeyboardActions
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material3.Button
import androidx.compose.material3.DropdownMenu
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.focus.FocusRequester
import androidx.compose.ui.focus.focusRequester
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalSoftwareKeyboardController
import androidx.compose.ui.semantics.LiveRegionMode
import androidx.compose.ui.semantics.liveRegion
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import me.masonasons.fastgh.data.GitHubClient
import me.masonasons.fastgh.data.TokenStore
import me.masonasons.fastgh.model.Repository
import me.masonasons.fastgh.model.UserProfile
import me.masonasons.fastgh.ui.LocalNavigator
import me.masonasons.fastgh.ui.components.ActionListItem
import me.masonasons.fastgh.ui.components.BaseViewModel
import me.masonasons.fastgh.ui.components.FilterRow
import me.masonasons.fastgh.ui.components.LoadState
import me.masonasons.fastgh.ui.components.RepoRow
import me.masonasons.fastgh.ui.components.RowAction
import me.masonasons.fastgh.ui.components.ScreenScaffold
import me.masonasons.fastgh.ui.components.StatusMessage
import me.masonasons.fastgh.ui.components.appViewModel
import me.masonasons.fastgh.ui.components.openUrl
import kotlinx.coroutines.Job
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow

enum class SearchType(val label: String, val sorts: List<Pair<String?, String>>) {
    Repositories("Repositories", listOf(null to "Best match", "stars" to "Stars", "forks" to "Forks", "updated" to "Updated")),
    Users("Users", listOf(null to "Best match", "followers" to "Followers", "repositories" to "Repositories", "joined" to "Joined")),
}

sealed interface SearchResultList {
    val total: Int
    data class Repos(override val total: Int, val items: List<Repository>) : SearchResultList
    data class Users(override val total: Int, val items: List<UserProfile>) : SearchResultList
}

class SearchViewModel(github: GitHubClient, tokenStore: TokenStore) : BaseViewModel(github, tokenStore) {
    /** Null until the first search. */
    private val _results = MutableStateFlow<LoadState<SearchResultList>?>(null)
    val results: StateFlow<LoadState<SearchResultList>?> = _results.asStateFlow()

    private var job: Job? = null

    fun search(query: String, type: SearchType, sort: String?) {
        if (query.isBlank()) return
        job?.cancel()
        _results.value = LoadState.Loading
        job = launchAction {
            _results.value = loadState {
                when (type) {
                    SearchType.Repositories -> github.searchRepos(query, sort).let { SearchResultList.Repos(it.totalCount, it.items) }
                    SearchType.Users -> github.searchUsers(query, sort).let { SearchResultList.Users(it.totalCount, it.items) }
                }
            }
        }
    }

    fun clear() {
        job?.cancel()
        _results.value = null
    }
}

@Composable
fun SearchScreen() {
    val navigator = LocalNavigator.current
    val context = LocalContext.current
    val keyboard = LocalSoftwareKeyboardController.current
    val viewModel = appViewModel { SearchViewModel(it.github, it.tokenStore) }
    val results by viewModel.results.collectAsStateWithLifecycle()

    var query by rememberSaveable { mutableStateOf("") }
    var type by rememberSaveable { mutableStateOf(SearchType.Repositories) }
    var sort by rememberSaveable { mutableStateOf<String?>(null) }
    var sortMenu by remember { mutableStateOf(false) }
    val focus = remember { FocusRequester() }
    LaunchedEffect(Unit) { focus.requestFocus() }

    val runSearch = {
        keyboard?.hide()
        viewModel.search(query.trim(), type, sort)
    }

    ScreenScaffold(title = "Search GitHub", messages = viewModel.messages) { padding, showMessage ->
        Column(Modifier.fillMaxSize().padding(padding)) {
            Column(Modifier.padding(horizontal = 8.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
                FilterRow(SearchType.entries.map { it to it.label }, type) {
                    type = it
                    sort = null
                    viewModel.clear()
                }
                OutlinedTextField(
                    value = query,
                    onValueChange = { query = it },
                    label = { Text(if (type == SearchType.Repositories) "Search repositories" else "Search users") },
                    singleLine = true,
                    keyboardOptions = KeyboardOptions(imeAction = ImeAction.Search, autoCorrectEnabled = false),
                    keyboardActions = KeyboardActions(onSearch = { runSearch() }),
                    modifier = Modifier.fillMaxWidth().focusRequester(focus),
                )
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalAlignment = Alignment.CenterVertically) {
                    Button(onClick = runSearch, enabled = query.isNotBlank()) { Text("Search") }
                    Box {
                        val sortLabel = type.sorts.first { it.first == sort }.second
                        OutlinedButton(onClick = { sortMenu = true }) { Text("Sort: $sortLabel") }
                        DropdownMenu(expanded = sortMenu, onDismissRequest = { sortMenu = false }) {
                            type.sorts.forEach { (value, label) ->
                                DropdownMenuItem(
                                    text = { Text(label) },
                                    onClick = {
                                        sortMenu = false
                                        sort = value
                                        if (results != null) viewModel.search(query.trim(), type, value)
                                    },
                                )
                            }
                        }
                    }
                }
            }
            when (val r = results) {
                null -> Unit
                LoadState.Loading -> StatusMessage("Searching…", showProgress = true)
                is LoadState.Error -> StatusMessage(r.message, actionLabel = "Retry", onAction = runSearch)
                is LoadState.Loaded -> {
                    val list = r.value
                    LazyColumn(Modifier.fillMaxSize()) {
                        item {
                            Text(
                                when {
                                    list.total == 0 -> "No results"
                                    list.total == 1 -> "1 result"
                                    // The API returns at most 50 here; say so when there are more.
                                    list.total > 50 -> "%,d results, showing the first 50".format(list.total)
                                    else -> "${list.total} results"
                                },
                                modifier = Modifier
                                    .padding(16.dp)
                                    .semantics { liveRegion = LiveRegionMode.Polite },
                            )
                        }
                        when (list) {
                            is SearchResultList.Repos -> items(list.items, key = { it.id }) { repo ->
                                RepoRow(
                                    repo,
                                    onOpen = { navigator.repo(repo.owner.login, repo.name) },
                                    onViewOwner = { navigator.user(repo.owner.login) },
                                    onMessage = showMessage,
                                )
                            }
                            is SearchResultList.Users -> items(list.items, key = { it.login }) { user ->
                                ActionListItem(
                                    headline = user.login,
                                    supporting = if (user.type == "Organization") "Organization" else null,
                                    onClick = { navigator.user(user.login) },
                                    onClickLabel = "View profile",
                                    actions = listOf(RowAction("Open in browser") { context.openUrl(user.htmlUrl) }),
                                )
                            }
                        }
                    }
                }
            }
        }
    }
}
