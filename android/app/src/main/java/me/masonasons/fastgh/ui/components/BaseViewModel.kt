package me.masonasons.fastgh.ui.components

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import me.masonasons.fastgh.data.GitHubClient
import me.masonasons.fastgh.data.Page
import me.masonasons.fastgh.data.TokenStore
import me.masonasons.fastgh.data.UnauthorizedException
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Job
import kotlinx.coroutines.channels.Channel
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.receiveAsFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch

/**
 * Shared ViewModel plumbing: one-off messages for snackbars, and signing out when
 * GitHub rejects the token.
 */
abstract class BaseViewModel(
    protected val github: GitHubClient,
    protected val tokenStore: TokenStore,
) : ViewModel() {
    private val _messages = Channel<String>(Channel.BUFFERED)
    /** Confirmations and errors to show as snackbars (which TalkBack announces). */
    val messages: Flow<String> = _messages.receiveAsFlow()

    protected val signedInLogin: String get() = tokenStore.session.value?.login.orEmpty()

    protected suspend fun message(text: String) = _messages.send(text)

    /** Creates a [PagedLoader] scoped to this ViewModel. */
    protected fun <T> pagedLoader(fetch: suspend (page: Int) -> Page<T>) =
        PagedLoader(viewModelScope, fetch, onUnauthorized = tokenStore::clear)

    /** Runs an action, reporting failures as a message. */
    protected fun launchAction(block: suspend CoroutineScope.() -> Unit): Job =
        viewModelScope.launch {
            try {
                block()
            } catch (e: CancellationException) {
                throw e
            } catch (e: UnauthorizedException) {
                tokenStore.clear()
            } catch (e: Exception) {
                message(e.userMessage())
            }
        }

    /** Fetches a value as a LoadState, signing out if the token was rejected. */
    protected suspend fun <T> loadState(fetch: suspend () -> T): LoadState<T> =
        try {
            LoadState.Loaded(fetch())
        } catch (e: CancellationException) {
            throw e
        } catch (e: UnauthorizedException) {
            tokenStore.clear()
            LoadState.Error(e.userMessage())
        } catch (e: Exception) {
            LoadState.Error(e.userMessage())
        }
}

/** State of a list loaded a page at a time. */
data class PagedState<T>(
    val items: List<T> = emptyList(),
    val loading: Boolean = true,
    val hasMore: Boolean = false,
    val error: String? = null,
)

/**
 * Loads a list a page at a time. Call [refresh] to start over (for example after a
 * filter change) and [loadMore] when the end of the list is reached.
 */
class PagedLoader<T>(
    private val scope: CoroutineScope,
    private val fetch: suspend (page: Int) -> Page<T>,
    private val onUnauthorized: () -> Unit,
) {
    private val _state = MutableStateFlow(PagedState<T>())
    val state: StateFlow<PagedState<T>> = _state.asStateFlow()

    private var nextPage = 1
    private var job: Job? = null

    fun refresh() {
        job?.cancel()
        nextPage = 1
        _state.value = PagedState()
        load()
    }

    fun loadMore() {
        val current = _state.value
        if (current.loading || !current.hasMore) return
        load()
    }

    /** Applies a local change, e.g. after closing an issue from the list. */
    fun update(transform: (List<T>) -> List<T>) = _state.update { it.copy(items = transform(it.items)) }

    private fun load() {
        _state.update { it.copy(loading = true, error = null) }
        val page = nextPage
        job = scope.launch {
            try {
                val result = fetch(page)
                nextPage = page + 1
                _state.update { it.copy(items = it.items + result.items, loading = false, hasMore = result.hasMore) }
            } catch (e: CancellationException) {
                throw e
            } catch (e: UnauthorizedException) {
                onUnauthorized()
            } catch (e: Exception) {
                _state.update { it.copy(loading = false, error = e.userMessage()) }
            }
        }
    }
}
