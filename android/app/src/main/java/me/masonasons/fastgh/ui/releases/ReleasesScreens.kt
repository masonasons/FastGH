package me.masonasons.fastgh.ui.releases

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
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
import me.masonasons.fastgh.model.Release
import me.masonasons.fastgh.model.formatSize
import me.masonasons.fastgh.model.plural
import me.masonasons.fastgh.ui.FilesRoute
import me.masonasons.fastgh.ui.LocalNavigator
import me.masonasons.fastgh.ui.ReleaseRoute
import me.masonasons.fastgh.ui.components.ActionListItem
import me.masonasons.fastgh.ui.components.BaseViewModel
import me.masonasons.fastgh.ui.components.BodyText
import me.masonasons.fastgh.ui.components.LoadState
import me.masonasons.fastgh.ui.components.PagedList
import me.masonasons.fastgh.ui.components.RowAction
import me.masonasons.fastgh.ui.components.ScreenScaffold
import me.masonasons.fastgh.ui.components.SectionHeading
import me.masonasons.fastgh.ui.components.StatusMessage
import me.masonasons.fastgh.ui.components.appViewModel
import me.masonasons.fastgh.ui.components.copyToClipboard
import me.masonasons.fastgh.ui.components.downloadFile
import me.masonasons.fastgh.ui.components.openUrl
import me.masonasons.fastgh.ui.components.relativeTime
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow

/** "Release, 3 assets, 1,204 downloads, 2 days ago" — downloads only when there are assets, like the desktop. */
fun Release.summary(): String = buildList {
    add(status)
    add(plural(assets.size, "asset"))
    if (assets.isNotEmpty()) add(plural(totalDownloads, "download"))
    add(relativeTime(publishedInstant))
}.joinToString(", ")

class ReleasesViewModel(
    private val owner: String,
    private val name: String,
    github: GitHubClient,
    tokenStore: TokenStore,
) : BaseViewModel(github, tokenStore) {
    val list = pagedLoader { page -> github.releases(owner, name, page) }

    init {
        list.refresh()
    }
}

@Composable
fun ReleasesScreen(owner: String, name: String) {
    val navigator = LocalNavigator.current
    val context = LocalContext.current
    val viewModel = appViewModel(key = "releases/$owner/$name") { ReleasesViewModel(owner, name, it.github, it.tokenStore) }
    val state by viewModel.list.state.collectAsStateWithLifecycle()

    ScreenScaffold(title = "Releases: $owner/$name", messages = viewModel.messages) { padding, showMessage ->
        PagedList(
            state = state,
            emptyText = "No releases",
            onRefresh = viewModel.list::refresh,
            onLoadMore = viewModel.list::loadMore,
            modifier = Modifier.padding(padding),
            key = { it.id },
        ) { release ->
            ActionListItem(
                headline = release.title,
                supporting = release.summary(),
                onClick = { navigator.go(ReleaseRoute(owner, name, release.id)) },
                onClickLabel = "View release",
                actions = listOf(
                    RowAction("Open in browser") { context.openUrl(release.htmlUrl) },
                    RowAction("Copy link") {
                        context.copyToClipboard("Release link", release.htmlUrl)
                        showMessage("Copied ${release.htmlUrl}")
                    },
                    RowAction("Browse files at ${release.tagName}") {
                        navigator.go(FilesRoute(owner, name, ref = release.tagName))
                    },
                ),
            )
        }
    }
}

class ReleaseViewModel(
    private val owner: String,
    private val name: String,
    private val id: Long,
    github: GitHubClient,
    tokenStore: TokenStore,
) : BaseViewModel(github, tokenStore) {
    private val _release = MutableStateFlow<LoadState<Release>>(LoadState.Loading)
    val release: StateFlow<LoadState<Release>> = _release.asStateFlow()

    init {
        load()
    }

    fun load() {
        _release.value = LoadState.Loading
        launchAction { _release.value = loadState { github.release(owner, name, id) } }
    }
}

@OptIn(ExperimentalLayoutApi::class)
@Composable
fun ReleaseScreen(owner: String, name: String, id: Long) {
    val navigator = LocalNavigator.current
    val context = LocalContext.current
    val viewModel = appViewModel(key = "release/$owner/$name/$id") {
        ReleaseViewModel(owner, name, id, it.github, it.tokenStore)
    }
    val releaseState by viewModel.release.collectAsStateWithLifecycle()

    ScreenScaffold(title = "Release", messages = viewModel.messages) { padding, showMessage ->
        when (val s = releaseState) {
            LoadState.Loading -> StatusMessage("Loading release…", Modifier.padding(padding), showProgress = true)
            is LoadState.Error -> StatusMessage(
                s.message, Modifier.padding(padding), actionLabel = "Retry", onAction = viewModel::load,
            )
            is LoadState.Loaded -> {
                val release = s.value
                LazyColumn(Modifier.fillMaxSize().padding(padding)) {
                    item {
                        Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
                            SectionHeading(release.title)
                            Text(release.summary() + release.author?.login?.let { ", published by $it" }.orEmpty())
                            BodyText(release.body, emptyText = "No release notes.")
                            FlowRow(
                                horizontalArrangement = Arrangement.spacedBy(8.dp),
                                verticalArrangement = Arrangement.spacedBy(8.dp),
                            ) {
                                OutlinedButton(onClick = { context.openUrl(release.htmlUrl) }) { Text("Open in browser") }
                                OutlinedButton(onClick = {
                                    context.copyToClipboard("Release link", release.htmlUrl)
                                    showMessage("Copied ${release.htmlUrl}")
                                }) { Text("Copy link") }
                                OutlinedButton(onClick = { navigator.go(FilesRoute(owner, name, ref = release.tagName)) }) {
                                    Text("Browse files")
                                }
                            }
                            SectionHeading("Assets (${release.assets.size})")
                            if (release.assets.isEmpty()) Text("This release has no downloadable assets.")
                        }
                    }
                    items(release.assets, key = { it.id }) { asset ->
                        ActionListItem(
                            headline = asset.name,
                            supporting = "${formatSize(asset.size)}, ${plural(asset.downloadCount, "download")}",
                            onClick = {
                                context.downloadFile(asset.downloadUrl, asset.name)
                                showMessage("Downloading ${asset.name}")
                            },
                            onClickLabel = "Download",
                            actions = listOf(
                                RowAction("Open in browser") { context.openUrl(asset.downloadUrl) },
                                RowAction("Copy download link") {
                                    context.copyToClipboard("Download link", asset.downloadUrl)
                                    showMessage("Copied ${asset.downloadUrl}")
                                },
                            ),
                        )
                    }
                }
            }
        }
    }
}
