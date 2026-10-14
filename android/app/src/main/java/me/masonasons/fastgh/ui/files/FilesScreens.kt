package me.masonasons.fastgh.ui.files

import android.util.Base64
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.itemsIndexed
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import me.masonasons.fastgh.data.GitHubClient
import me.masonasons.fastgh.data.TokenStore
import me.masonasons.fastgh.model.ContentItem
import me.masonasons.fastgh.model.formatSize
import me.masonasons.fastgh.ui.FileRoute
import me.masonasons.fastgh.ui.FilesRoute
import me.masonasons.fastgh.ui.LocalNavigator
import me.masonasons.fastgh.ui.components.ActionListItem
import me.masonasons.fastgh.ui.components.BaseViewModel
import me.masonasons.fastgh.ui.components.LoadState
import me.masonasons.fastgh.ui.components.RowAction
import me.masonasons.fastgh.ui.components.ScreenScaffold
import me.masonasons.fastgh.ui.components.SectionHeading
import me.masonasons.fastgh.ui.components.StatusMessage
import me.masonasons.fastgh.ui.components.appViewModel
import me.masonasons.fastgh.ui.components.copyToClipboard
import me.masonasons.fastgh.ui.components.openUrl
import me.masonasons.fastgh.ui.components.shareText
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import java.nio.ByteBuffer
import java.nio.charset.CharacterCodingException
import java.nio.charset.CodingErrorAction

/** What a file's contents can be shown as. */
sealed interface FileText {
    data class Text(val lines: List<String>, val raw: String) : FileText
    data object Binary : FileText
    /** The contents API leaves out files over 1 MB. */
    data object TooLarge : FileText
}

/** Decodes the contents API's base64 payload, treating non-UTF-8 or NUL bytes as binary. */
fun decodeFileText(item: ContentItem, decodeBase64: (String) -> ByteArray): FileText {
    val content = item.content
    if (item.encoding != "base64" || content.isNullOrEmpty()) {
        return if (item.size > 0) FileText.TooLarge else FileText.Text(listOf(""), "")
    }
    val bytes = runCatching { decodeBase64(content.filterNot(Char::isWhitespace)) }.getOrNull() ?: return FileText.Binary
    if (bytes.any { it == 0.toByte() }) return FileText.Binary
    val text = try {
        Charsets.UTF_8.newDecoder()
            .onMalformedInput(CodingErrorAction.REPORT)
            .onUnmappableCharacter(CodingErrorAction.REPORT)
            .decode(ByteBuffer.wrap(bytes))
            .toString()
    } catch (_: CharacterCodingException) {
        return FileText.Binary
    }
    return FileText.Text(text.removeSuffix("\n").split("\r\n", "\n"), text)
}

private fun location(path: String, ref: String?) =
    (if (path.isEmpty()) "/" else "/$path") + (ref?.let { " at ${it.take(7)}" }.orEmpty())

// ============ Folder listing ============

class FilesViewModel(
    private val owner: String,
    private val name: String,
    private val path: String,
    private val ref: String?,
    github: GitHubClient,
    tokenStore: TokenStore,
) : BaseViewModel(github, tokenStore) {
    private val _items = MutableStateFlow<LoadState<List<ContentItem>>>(LoadState.Loading)
    val items: StateFlow<LoadState<List<ContentItem>>> = _items.asStateFlow()

    init {
        load()
    }

    fun load() {
        _items.value = LoadState.Loading
        launchAction { _items.value = loadState { github.directory(owner, name, path, ref) } }
    }
}

@Composable
fun FilesScreen(owner: String, name: String, path: String, ref: String?) {
    val navigator = LocalNavigator.current
    val context = LocalContext.current
    val viewModel = appViewModel(key = "files/$owner/$name/$path/$ref") {
        FilesViewModel(owner, name, path, ref, it.github, it.tokenStore)
    }
    val items by viewModel.items.collectAsStateWithLifecycle()

    ScreenScaffold(title = "$name${location(path, ref)}", messages = viewModel.messages) { padding, showMessage ->
        when (val s = items) {
            LoadState.Loading -> StatusMessage("Loading files…", Modifier.padding(padding), showProgress = true)
            is LoadState.Error -> StatusMessage(
                s.message, Modifier.padding(padding), actionLabel = "Retry", onAction = viewModel::load,
            )
            is LoadState.Loaded -> if (s.value.isEmpty()) {
                StatusMessage("This folder is empty", Modifier.padding(padding))
            } else {
                LazyColumn(Modifier.fillMaxSize().padding(padding)) {
                    itemsIndexed(s.value, key = { _, item -> item.path }) { _, item ->
                        val webUrl = item.htmlUrl
                        ActionListItem(
                            overline = if (item.isDir) "Folder" else null,
                            headline = item.name,
                            supporting = if (item.isDir) null else formatSize(item.size),
                            onClick = {
                                when {
                                    item.isDir -> navigator.go(FilesRoute(owner, name, item.path, ref))
                                    item.type == "file" -> navigator.go(FileRoute(owner, name, item.path, ref))
                                    webUrl != null -> context.openUrl(webUrl)
                                }
                            },
                            onClickLabel = if (item.isDir) "Open folder" else "View file",
                            actions = buildList {
                                if (webUrl != null) add(RowAction("Open in browser") { context.openUrl(webUrl) })
                                add(RowAction("Copy path") {
                                    context.copyToClipboard("Path", item.path)
                                    showMessage("Copied ${item.path}")
                                })
                            },
                        )
                    }
                }
            }
        }
    }
}

// ============ File viewer ============

class FileViewModel(
    private val owner: String,
    private val name: String,
    private val path: String,
    private val ref: String?,
    github: GitHubClient,
    tokenStore: TokenStore,
) : BaseViewModel(github, tokenStore) {
    private val _file = MutableStateFlow<LoadState<Pair<ContentItem, FileText>>>(LoadState.Loading)
    val file: StateFlow<LoadState<Pair<ContentItem, FileText>>> = _file.asStateFlow()

    init {
        load()
    }

    fun load() {
        _file.value = LoadState.Loading
        launchAction {
            _file.value = loadState {
                val item = github.file(owner, name, path, ref)
                item to decodeFileText(item) { Base64.decode(it, Base64.DEFAULT) }
            }
        }
    }
}

@OptIn(ExperimentalLayoutApi::class)
@Composable
fun FileScreen(owner: String, name: String, path: String, ref: String?) {
    val context = LocalContext.current
    val viewModel = appViewModel(key = "file/$owner/$name/$path/$ref") {
        FileViewModel(owner, name, path, ref, it.github, it.tokenStore)
    }
    val fileState by viewModel.file.collectAsStateWithLifecycle()
    val fileName = path.substringAfterLast('/')

    ScreenScaffold(title = fileName, messages = viewModel.messages) { padding, showMessage ->
        when (val s = fileState) {
            LoadState.Loading -> StatusMessage("Loading $fileName…", Modifier.padding(padding), showProgress = true)
            is LoadState.Error -> StatusMessage(
                s.message, Modifier.padding(padding), actionLabel = "Retry", onAction = viewModel::load,
            )
            is LoadState.Loaded -> {
                val (item, text) = s.value
                LazyColumn(Modifier.fillMaxSize().padding(padding)) {
                    item {
                        Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
                            Text("${location(path, ref)}, ${formatSize(item.size)}" +
                                if (text is FileText.Text) ", ${text.lines.size} lines" else "")
                            FlowRow(
                                horizontalArrangement = Arrangement.spacedBy(8.dp),
                                verticalArrangement = Arrangement.spacedBy(8.dp),
                            ) {
                                if (text is FileText.Text) {
                                    OutlinedButton(onClick = {
                                        context.copyToClipboard(fileName, text.raw)
                                        showMessage("Copied contents of $fileName")
                                    }) { Text("Copy contents") }
                                    OutlinedButton(onClick = { context.shareText(text.raw, "Share $fileName") }) {
                                        Text("Share contents")
                                    }
                                }
                                item.htmlUrl?.let { url ->
                                    OutlinedButton(onClick = { context.openUrl(url) }) { Text("Open in browser") }
                                }
                                OutlinedButton(onClick = {
                                    context.copyToClipboard("Path", path)
                                    showMessage("Copied $path")
                                }) { Text("Copy path") }
                            }
                            SectionHeading("Contents")
                        }
                    }
                    when (text) {
                        FileText.Binary -> item {
                            Text("This is a binary file and can't be shown here.", Modifier.padding(16.dp))
                        }
                        FileText.TooLarge -> item {
                            Text("This file is too large to show here. Open it in the browser instead.", Modifier.padding(16.dp))
                        }
                        // One item per line, so TalkBack can move through the file line by line.
                        is FileText.Text -> itemsIndexed(text.lines) { _, line ->
                            Text(
                                line,
                                fontFamily = FontFamily.Monospace,
                                style = MaterialTheme.typography.bodySmall,
                                modifier = Modifier
                                    .fillMaxWidth()
                                    .padding(horizontal = 16.dp, vertical = 2.dp)
                                    .then(
                                        if (line.isBlank()) Modifier.semantics { contentDescription = "Blank line" }
                                        else Modifier,
                                    ),
                            )
                        }
                    }
                }
            }
        }
    }
}
