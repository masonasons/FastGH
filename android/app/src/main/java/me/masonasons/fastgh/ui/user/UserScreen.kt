package me.masonasons.fastgh.ui.user

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
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
import me.masonasons.fastgh.model.UserProfile
import me.masonasons.fastgh.model.parseInstant
import me.masonasons.fastgh.ui.LocalNavigator
import me.masonasons.fastgh.ui.components.BaseViewModel
import me.masonasons.fastgh.ui.components.LoadState
import me.masonasons.fastgh.ui.components.RepoRow
import me.masonasons.fastgh.ui.components.ScreenScaffold
import me.masonasons.fastgh.ui.components.SectionHeading
import me.masonasons.fastgh.ui.components.StatusMessage
import me.masonasons.fastgh.ui.components.appViewModel
import me.masonasons.fastgh.ui.components.openUrl
import me.masonasons.fastgh.ui.components.relativeTime
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update

data class UserUiState(
    val profile: LoadState<UserProfile> = LoadState.Loading,
    val repos: LoadState<List<Repository>> = LoadState.Loading,
    val following: Boolean? = null, // null while unknown
)

class UserViewModel(
    private val login: String,
    github: GitHubClient,
    tokenStore: TokenStore,
) : BaseViewModel(github, tokenStore) {
    private val _state = MutableStateFlow(UserUiState())
    val state: StateFlow<UserUiState> = _state.asStateFlow()

    val isSelf: Boolean get() = login.equals(signedInLogin, ignoreCase = true)

    init {
        load()
    }

    fun load() {
        _state.value = UserUiState()
        launchAction {
            val profile = loadState { github.user(login) }
            _state.update { it.copy(profile = profile) }
            if (profile !is LoadState.Loaded) return@launchAction

            if (!isSelf) {
                val following = runCatching { github.isFollowing(login) }.getOrNull()
                _state.update { it.copy(following = following) }
            }
            _state.update { it.copy(repos = loadState { github.userRepos(login) }) }
        }
    }

    fun toggleFollow() {
        val follow = _state.value.following?.not() ?: return
        launchAction {
            if (github.setFollowing(login, follow)) {
                _state.update { it.copy(following = follow) }
                message(if (follow) "Now following $login" else "Unfollowed $login")
            } else {
                message("Couldn't ${if (follow) "follow" else "unfollow"} $login.")
            }
        }
    }
}

@OptIn(ExperimentalLayoutApi::class)
@Composable
fun UserScreen(login: String) {
    val navigator = LocalNavigator.current
    val context = LocalContext.current
    val viewModel = appViewModel(key = "user/$login") { UserViewModel(login, it.github, it.tokenStore) }
    val state by viewModel.state.collectAsStateWithLifecycle()

    ScreenScaffold(title = login, messages = viewModel.messages) { padding, showMessage ->
        when (val profileState = state.profile) {
            LoadState.Loading -> StatusMessage("Loading profile…", Modifier.padding(padding), showProgress = true)
            is LoadState.Error -> StatusMessage(
                profileState.message,
                Modifier.padding(padding),
                actionLabel = "Retry",
                onAction = viewModel::load,
            )
            is LoadState.Loaded -> {
                val user = profileState.value
                LazyColumn(Modifier.fillMaxSize().padding(padding)) {
                    item {
                        Column(
                            Modifier.padding(16.dp),
                            verticalArrangement = Arrangement.spacedBy(12.dp),
                        ) {
                            SectionHeading("Profile")
                            profileDetails(user).forEach { line ->
                                Text(line, style = MaterialTheme.typography.bodyMedium)
                            }
                            FlowRow(
                                horizontalArrangement = Arrangement.spacedBy(8.dp),
                                verticalArrangement = Arrangement.spacedBy(8.dp),
                            ) {
                                if (!viewModel.isSelf) {
                                    Button(onClick = viewModel::toggleFollow, enabled = state.following != null) {
                                        Text(if (state.following == true) "Unfollow" else "Follow")
                                    }
                                }
                                OutlinedButton(onClick = { context.openUrl(user.htmlUrl) }) {
                                    Text("Open in browser")
                                }
                            }
                            val repoCount = (state.repos as? LoadState.Loaded)?.value?.size
                            SectionHeading(if (repoCount != null) "Repositories ($repoCount)" else "Repositories")
                        }
                    }
                    when (val repos = state.repos) {
                        LoadState.Loading -> item { StatusMessage("Loading repositories…", showProgress = true) }
                        is LoadState.Error -> item {
                            StatusMessage(repos.message, actionLabel = "Retry", onAction = viewModel::load)
                        }
                        is LoadState.Loaded -> if (repos.value.isEmpty()) {
                            item { Text("No public repositories", Modifier.padding(16.dp)) }
                        } else {
                            items(repos.value, key = { it.id }) { repo ->
                                RepoRow(
                                    repo,
                                    onOpen = { navigator.repo(repo.owner.login, repo.name) },
                                    // Every repo listed here is owned by this user.
                                    onViewOwner = null,
                                    onMessage = showMessage,
                                )
                            }
                        }
                    }
                }
            }
        }
    }
}

private fun profileDetails(user: UserProfile): List<String> = buildList {
    add("Username: ${user.login}")
    user.name?.takeIf { it.isNotBlank() }?.let { add("Name: $it") }
    add("Type: ${user.type}")
    user.bio?.takeIf { it.isNotBlank() }?.let { add("Bio: ${it.trim()}") }
    user.company?.takeIf { it.isNotBlank() }?.let { add("Company: $it") }
    user.location?.takeIf { it.isNotBlank() }?.let { add("Location: $it") }
    user.email?.takeIf { it.isNotBlank() }?.let { add("Email: $it") }
    user.blog?.takeIf { it.isNotBlank() }?.let { add("Website: $it") }
    user.twitterUsername?.takeIf { it.isNotBlank() }?.let { add("Twitter: @$it") }
    add("Public repos: ${user.publicRepos}")
    add("Followers: ${user.followers}, following: ${user.following}")
    parseInstant(user.createdAt)?.let { add("Joined ${relativeTime(it)}") }
}
