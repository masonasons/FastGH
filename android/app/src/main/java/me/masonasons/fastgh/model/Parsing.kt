package me.masonasons.fastgh.model

private val REPO_URL = Regex("""^(?:https?://)?(?:www\.)?github\.com/([^/\s]+)/([^/\s]+?)(?:\.git)?/?$""")
private val REPO_PAIR = Regex("""^([^/\s]+)/([^/\s]+)$""")

/**
 * Parses "owner/repo" or a GitHub repository URL into (owner, repo), using the
 * same rules as the desktop app's Go to Repository dialog.
 */
fun parseRepoInput(input: String): Pair<String, String>? {
    val text = input.trim()
    val match = REPO_URL.matchEntire(text) ?: REPO_PAIR.matchEntire(text) ?: return null
    return match.groupValues[1] to match.groupValues[2]
}
