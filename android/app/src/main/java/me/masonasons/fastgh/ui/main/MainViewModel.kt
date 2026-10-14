package me.masonasons.fastgh.ui.main

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import me.masonasons.fastgh.data.GitHubClient
import me.masonasons.fastgh.data.TokenStore
import me.masonasons.fastgh.data.UnauthorizedException
import me.masonasons.fastgh.model.Event
import me.masonasons.fastgh.model.Notification
import me.masonasons.fastgh.model.Repository
import me.masonasons.fastgh.model.UserProfile
import me.masonasons.fastgh.ui.components.LoadState
import me.masonasons.fastgh.ui.components.userMessage
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.channels.Channel
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.receiveAsFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch

enum class MainTab(val title: String) {
    Feed("Feed"),
    Repos("Your Repos"),
    Starred("Starred"),
    Watched("Watched"),
    Following("Following"),
    Notifications("Notifications"),
}

data class MainUiState(
    val feed: LoadState<List<Event>> = LoadState.Loading,
    val repos: LoadState<List<Repository>> = LoadState.Loading,
    val starred: LoadState<List<Repository>> = LoadState.Loading,
    val watched: LoadState<List<Repository>> = LoadState.Loading,
    val following: LoadState<List<UserProfile>> = LoadState.Loading,
    val notifications: LoadState<List<Notification>> = LoadState.Loading,
    val refreshing: Set<MainTab> = emptySet(),
) {
    val unreadCount: Int
        get() = (notifications as? LoadState.Loaded)?.value?.count { it.unread } ?: 0
}

class MainViewModel(
    private val github: GitHubClient,
    private val tokenStore: TokenStore,
) : ViewModel() {
    private val _state = MutableStateFlow(MainUiState())
    val state: StateFlow<MainUiState> = _state.asStateFlow()

    private val _messages = Channel<String>(Channel.BUFFERED)
    /** One-off confirmations and errors, shown as snackbars. */
    val messages: Flow<String> = _messages.receiveAsFlow()

    init {
        refreshAll()
    }

    fun refreshAll() = MainTab.entries.forEach(::refresh)

    fun refresh(tab: MainTab) {
        if (tab in _state.value.refreshing) return
        _state.update { it.copy(refreshing = it.refreshing + tab) }
        viewModelScope.launch {
            val login = tokenStore.session.value?.login.orEmpty()
            when (tab) {
                MainTab.Feed -> load({ github.receivedEvents(login) }) { s, v -> s.copy(feed = v) }
                MainTab.Repos -> load({ github.myRepos() }) { s, v -> s.copy(repos = v) }
                MainTab.Starred -> load({ github.starred() }) { s, v -> s.copy(starred = v) }
                MainTab.Watched -> load({ github.watched() }) { s, v -> s.copy(watched = v) }
                MainTab.Following -> load({ github.following() }) { s, v -> s.copy(following = v) }
                MainTab.Notifications -> load({ github.notifications() }) { s, v -> s.copy(notifications = v) }
            }
            _state.update { it.copy(refreshing = it.refreshing - tab) }
        }
    }

    private suspend fun <T> load(
        fetch: suspend () -> T,
        apply: (MainUiState, LoadState<T>) -> MainUiState,
    ) {
        val result = try {
            LoadState.Loaded(fetch())
        } catch (e: CancellationException) {
            throw e
        } catch (e: UnauthorizedException) {
            tokenStore.clear()
            return
        } catch (e: Exception) {
            LoadState.Error(e.userMessage())
        }
        _state.update { apply(it, result) }
    }

    fun markRead(notification: Notification) = notificationAction(notification, "Marked as read") {
        if (github.markThreadRead(notification.id)) {
            updateNotifications { list -> list.map { if (it.id == notification.id) it.copy(unread = false) else it } }
            true
        } else {
            false
        }
    }

    fun markDone(notification: Notification) = notificationAction(notification, "Marked as done") {
        github.markThreadDone(notification.id).also { done ->
            if (done) updateNotifications { list -> list.filterNot { it.id == notification.id } }
        }
    }

    fun mute(notification: Notification) = notificationAction(notification, "Thread muted") {
        github.muteThread(notification.id)
    }

    fun markAllRead() = launchAction("Couldn't mark notifications as read.") {
        if (github.markAllNotificationsRead()) {
            updateNotifications { list -> list.map { it.copy(unread = false) } }
            _messages.send("All notifications marked as read")
        } else {
            _messages.send("Couldn't mark notifications as read.")
        }
    }

    fun unfollow(user: UserProfile) = launchAction("Couldn't unfollow ${user.login}.") {
        if (github.setFollowing(user.login, follow = false)) {
            _state.update { s ->
                val following = s.following as? LoadState.Loaded ?: return@update s
                s.copy(following = LoadState.Loaded(following.value.filterNot { it.login == user.login }))
            }
            _messages.send("Unfollowed ${user.login}")
        } else {
            _messages.send("Couldn't unfollow ${user.login}.")
        }
    }

    fun signOut() = tokenStore.clear()

    private fun notificationAction(
        notification: Notification,
        success: String,
        action: suspend () -> Boolean,
    ) = launchAction("Couldn't update \"${notification.subject.title}\".") {
        _messages.send(if (action()) success else "Couldn't update \"${notification.subject.title}\".")
    }

    private fun updateNotifications(transform: (List<Notification>) -> List<Notification>) {
        _state.update { s ->
            val loaded = s.notifications as? LoadState.Loaded ?: return@update s
            s.copy(notifications = LoadState.Loaded(transform(loaded.value)))
        }
    }

    private fun launchAction(failure: String, block: suspend () -> Unit) {
        viewModelScope.launch {
            try {
                block()
            } catch (e: CancellationException) {
                throw e
            } catch (e: UnauthorizedException) {
                tokenStore.clear()
            } catch (e: Exception) {
                _messages.send(failure)
            }
        }
    }
}
