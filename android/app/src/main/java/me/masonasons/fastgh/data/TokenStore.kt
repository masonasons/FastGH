package me.masonasons.fastgh.data

import android.content.Context
import androidx.core.content.edit
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow

data class Session(val token: String, val login: String)

/**
 * Stores the signed-in session in app-private preferences, like the desktop app
 * keeps its token in its config file. Backups are disabled in the manifest so the
 * token never leaves the device.
 */
class TokenStore(context: Context) {
    private val prefs = context.getSharedPreferences("session", Context.MODE_PRIVATE)

    private val _session = MutableStateFlow(load())
    val session: StateFlow<Session?> = _session.asStateFlow()

    val token: String? get() = _session.value?.token

    fun save(session: Session) {
        prefs.edit {
            putString(KEY_TOKEN, session.token)
            putString(KEY_LOGIN, session.login)
        }
        _session.value = session
    }

    fun clear() {
        prefs.edit { clear() }
        _session.value = null
    }

    private fun load(): Session? {
        val token = prefs.getString(KEY_TOKEN, null) ?: return null
        val login = prefs.getString(KEY_LOGIN, null) ?: return null
        return Session(token, login)
    }

    private companion object {
        const val KEY_TOKEN = "token"
        const val KEY_LOGIN = "login"
    }
}
