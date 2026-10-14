package me.masonasons.fastgh.ui.components

import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.RowScope
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.LazyListScope
import androidx.compose.foundation.lazy.itemsIndexed
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.Scaffold
import androidx.compose.material3.SegmentedButton
import androidx.compose.material3.SegmentedButtonDefaults
import androidx.compose.material3.SingleChoiceSegmentedButtonRow
import androidx.compose.material3.SnackbarHost
import androidx.compose.material3.SnackbarHostState
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.TopAppBar
import androidx.compose.material3.pulltorefresh.PullToRefreshBox
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.semantics.LiveRegionMode
import androidx.compose.ui.semantics.liveRegion
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import me.masonasons.fastgh.ui.LocalNavigator
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.emptyFlow
import kotlinx.coroutines.launch

/**
 * The standard screen: a top bar with Back, the screen's title and actions, and a
 * snackbar host that shows [messages] plus anything passed to `showMessage`.
 */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun ScreenScaffold(
    title: String,
    messages: Flow<String> = emptyFlow(),
    showBack: Boolean = true,
    actions: @Composable RowScope.() -> Unit = {},
    content: @Composable (padding: PaddingValues, showMessage: (String) -> Unit) -> Unit,
) {
    val navigator = LocalNavigator.current
    val snackbar = remember { SnackbarHostState() }
    val scope = rememberCoroutineScope()
    val showMessage: (String) -> Unit = { text -> scope.launch { snackbar.showSnackbar(text) } }

    LaunchedEffect(messages) {
        messages.collect { snackbar.showSnackbar(it) }
    }

    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text(title, maxLines = 1, overflow = TextOverflow.Ellipsis) },
                navigationIcon = {
                    if (showBack) {
                        IconButton(onClick = navigator::back) {
                            Icon(Icons.AutoMirrored.Filled.ArrowBack, contentDescription = "Back")
                        }
                    }
                },
                actions = actions,
            )
        },
        snackbarHost = { SnackbarHost(snackbar) },
    ) { padding -> content(padding, showMessage) }
}

/**
 * A list loaded a page at a time, with pull-to-refresh. The next page loads when the
 * last row is composed, which also happens when TalkBack moves focus onto it.
 */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun <T> PagedList(
    state: PagedState<T>,
    emptyText: String,
    onRefresh: () -> Unit,
    onLoadMore: () -> Unit,
    modifier: Modifier = Modifier,
    key: ((T) -> Any)? = null,
    header: (LazyListScope.() -> Unit)? = null,
    row: @Composable (T) -> Unit,
) {
    val firstLoad = state.loading && state.items.isEmpty()
    PullToRefreshBox(
        // Refreshing clears the list and shows "Loading…", so the indicator needn't linger.
        isRefreshing = false,
        onRefresh = onRefresh,
        modifier = modifier.fillMaxSize(),
    ) {
        LazyColumn(Modifier.fillMaxSize()) {
            header?.invoke(this)
            itemsIndexed(state.items, key = key?.let { k -> { _, item -> k(item) } }) { index, item ->
                row(item)
                if (index == state.items.lastIndex && state.hasMore) {
                    LaunchedEffect(state.items.size) { onLoadMore() }
                }
            }
            item {
                when {
                    firstLoad -> StatusMessage("Loading…", showProgress = true)
                    state.error != null -> StatusMessage(
                        state.error,
                        actionLabel = "Retry",
                        onAction = if (state.items.isEmpty()) onRefresh else onLoadMore,
                    )
                    state.loading -> LoadingMore()
                    state.items.isEmpty() -> StatusMessage(emptyText)
                }
            }
        }
    }
}

@Composable
private fun LoadingMore() {
    Column(
        Modifier.fillMaxWidth().padding(16.dp),
        horizontalAlignment = Alignment.CenterHorizontally,
    ) {
        CircularProgressIndicator()
        Text("Loading more…", Modifier.semantics { liveRegion = LiveRegionMode.Polite })
    }
}

/** A labeled filter choice shown as a row of buttons, e.g. Open / Closed / All. */
@Composable
fun <T> FilterRow(options: List<Pair<T, String>>, selected: T, onSelect: (T) -> Unit) {
    SingleChoiceSegmentedButtonRow(Modifier.fillMaxWidth().padding(8.dp)) {
        options.forEachIndexed { index, (value, label) ->
            SegmentedButton(
                selected = value == selected,
                onClick = { onSelect(value) },
                shape = SegmentedButtonDefaults.itemShape(index, options.size),
            ) { Text(label) }
        }
    }
}

/** Small text button used in top bars, e.g. "New issue". */
@Composable
fun TopBarTextButton(text: String, onClick: () -> Unit) {
    TextButton(onClick = onClick) { Text(text) }
}
