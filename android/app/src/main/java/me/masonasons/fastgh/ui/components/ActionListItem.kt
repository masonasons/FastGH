package me.masonasons.fastgh.ui.components

import androidx.compose.foundation.combinedClickable
import androidx.compose.foundation.layout.Box
import androidx.compose.material3.DropdownMenu
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.ListItem
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.semantics.CustomAccessibilityAction
import androidx.compose.ui.semantics.customActions
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.style.TextOverflow

/** A secondary action on a list row. */
data class RowAction(val label: String, val onAction: () -> Unit)

/**
 * A list row whose secondary actions are available both as TalkBack custom actions
 * (the TalkBack actions menu) and as a long-press menu for touch users.
 *
 * TalkBack reads the row as one item: overline, headline, supporting text, then meta.
 */
@Composable
fun ActionListItem(
    headline: String,
    onClick: () -> Unit,
    onClickLabel: String,
    actions: List<RowAction>,
    modifier: Modifier = Modifier,
    supporting: String? = null,
    meta: String? = null,
    overline: String? = null,
) {
    var menuOpen by remember { mutableStateOf(false) }
    Box(modifier) {
        ListItem(
            headlineContent = { Text(headline, maxLines = 2, overflow = TextOverflow.Ellipsis) },
            overlineContent = overline?.let { text -> { Text(text) } },
            supportingContent = supporting?.let { text ->
                { Text(text, maxLines = 3, overflow = TextOverflow.Ellipsis) }
            },
            trailingContent = meta?.let { text -> { Text(text) } },
            modifier = Modifier
                .combinedClickable(
                    onClick = onClick,
                    onClickLabel = onClickLabel,
                    onLongClick = if (actions.isNotEmpty()) {
                        { menuOpen = true }
                    } else {
                        null
                    },
                    onLongClickLabel = "Show actions",
                )
                .semantics {
                    customActions = actions.map { action ->
                        CustomAccessibilityAction(action.label) {
                            action.onAction()
                            true
                        }
                    }
                },
        )
        DropdownMenu(expanded = menuOpen, onDismissRequest = { menuOpen = false }) {
            actions.forEach { action ->
                DropdownMenuItem(
                    text = { Text(action.label) },
                    onClick = {
                        menuOpen = false
                        action.onAction()
                    },
                )
            }
        }
    }
    HorizontalDivider()
}
