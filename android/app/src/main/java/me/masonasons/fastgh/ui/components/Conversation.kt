package me.masonasons.fastgh.ui.components

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.imePadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.text.selection.SelectionContainer
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Button
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.focus.FocusRequester
import androidx.compose.ui.focus.focusRequester
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.semantics.CustomAccessibilityAction
import androidx.compose.ui.semantics.customActions
import androidx.compose.ui.semantics.heading
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.unit.dp
import androidx.compose.ui.window.Dialog
import androidx.compose.ui.window.DialogProperties
import me.masonasons.fastgh.model.Comment

/**
 * A comment, read by TalkBack as one item ("alice, 2 days ago" then the text), with
 * custom actions to copy it, open it in the browser or view the author.
 */
@Composable
fun CommentItem(comment: Comment, onViewAuthor: (String) -> Unit, onMessage: (String) -> Unit) {
    val context = LocalContext.current
    val body = comment.body?.trim().orEmpty().ifEmpty { "No text" }
    val header = buildString {
        append(comment.user.login)
        append(", ")
        append(relativeTime(comment.createdInstant))
        comment.path?.let { append(", on $it") }
    }
    Column(
        Modifier
            .fillMaxWidth()
            .semantics(mergeDescendants = true) {
                customActions = listOf(
                    CustomAccessibilityAction("Copy comment") {
                        context.copyToClipboard("Comment", body)
                        onMessage("Comment copied")
                        true
                    },
                    CustomAccessibilityAction("Open in browser") {
                        context.openUrl(comment.htmlUrl)
                        true
                    },
                    CustomAccessibilityAction("View profile of ${comment.user.login}") {
                        onViewAuthor(comment.user.login)
                        true
                    },
                )
            }
            .padding(16.dp),
        verticalArrangement = Arrangement.spacedBy(4.dp),
    ) {
        Text(header, style = MaterialTheme.typography.labelLarge)
        Text(body, style = MaterialTheme.typography.bodyMedium)
    }
    HorizontalDivider()
}

/** Long text such as an issue body, selectable so it can be copied in parts. */
@Composable
fun BodyText(text: String?, emptyText: String = "No description provided.") {
    SelectionContainer {
        Text(text?.trim()?.takeIf { it.isNotEmpty() } ?: emptyText, style = MaterialTheme.typography.bodyMedium)
    }
}

/**
 * A full-screen editor for writing a comment or a new issue. Focus starts in the first
 * field; [sending] disables the submit button while the request is in flight.
 */
@Composable
fun ComposeDialog(
    title: String,
    submitLabel: String,
    sending: Boolean,
    onDismiss: () -> Unit,
    onSubmit: (title: String, body: String) -> Unit,
    withTitleField: Boolean = false,
    bodyLabel: String = "Comment",
) {
    var titleText by rememberSaveable { mutableStateOf("") }
    var bodyText by rememberSaveable { mutableStateOf("") }
    val focus = remember { FocusRequester() }
    LaunchedEffect(Unit) { focus.requestFocus() }
    // A new issue only needs a title; a comment needs text.
    val canSubmit = !sending && if (withTitleField) titleText.isNotBlank() else bodyText.isNotBlank()

    Dialog(onDismissRequest = onDismiss, properties = DialogProperties(usePlatformDefaultWidth = false)) {
        Surface(Modifier.fillMaxSize()) {
            Column(
                Modifier
                    .fillMaxSize()
                    .imePadding()
                    .verticalScroll(rememberScrollState())
                    .padding(16.dp),
                verticalArrangement = Arrangement.spacedBy(12.dp),
            ) {
                Text(title, style = MaterialTheme.typography.titleLarge, modifier = Modifier.semantics { heading() })
                if (withTitleField) {
                    OutlinedTextField(
                        value = titleText,
                        onValueChange = { titleText = it },
                        label = { Text("Title") },
                        singleLine = true,
                        modifier = Modifier.fillMaxWidth().focusRequester(focus),
                    )
                }
                OutlinedTextField(
                    value = bodyText,
                    onValueChange = { bodyText = it },
                    label = { Text(bodyLabel) },
                    minLines = 6,
                    modifier = Modifier
                        .fillMaxWidth()
                        .then(if (withTitleField) Modifier else Modifier.focusRequester(focus)),
                )
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    Button(onClick = { onSubmit(titleText.trim(), bodyText.trim()) }, enabled = canSubmit) {
                        Text(if (sending) "Sending…" else submitLabel)
                    }
                    TextButton(onClick = onDismiss) { Text("Cancel") }
                }
            }
        }
    }
}
