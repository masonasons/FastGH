package me.masonasons.fastgh.data

import me.masonasons.fastgh.model.DeviceCode
import me.masonasons.fastgh.model.TokenResponse
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.delay
import kotlinx.coroutines.withContext
import okhttp3.FormBody
import okhttp3.OkHttpClient
import okhttp3.Request
import java.io.IOException

/** Same OAuth app as the desktop client (github_api.py GITHUB_CLIENT_ID). */
const val GITHUB_CLIENT_ID = "Ov23liErbWGLzAKTlLFW"
const val GITHUB_SCOPES = "repo user notifications"

class AuthException(message: String) : Exception(message)

/** GitHub OAuth device flow: show the user a code, then poll until they approve it. */
class DeviceFlowAuth(
    private val http: OkHttpClient,
    private val baseUrl: String = "https://github.com",
    private val sleep: suspend (Long) -> Unit = { delay(it) },
) {
    suspend fun requestCode(): DeviceCode {
        val body = post(
            "/login/device/code",
            FormBody.Builder()
                .add("client_id", GITHUB_CLIENT_ID)
                .add("scope", GITHUB_SCOPES)
                .build(),
        )
        return runCatching { json.decodeFromString<DeviceCode>(body) }
            .getOrElse { throw AuthException("GitHub didn't return a sign-in code. Please try again.") }
    }

    /**
     * Polls until the user approves the code; returns the access token.
     *
     * Network errors are retried rather than fatal: the user approves the code in
     * a browser, and Android cuts off a backgrounded app's network meanwhile.
     */
    suspend fun awaitToken(code: DeviceCode): String {
        var interval = code.interval.coerceAtLeast(1).toLong()
        val deadline = System.currentTimeMillis() + code.expiresIn * 1000L
        while (System.currentTimeMillis() < deadline) {
            sleep(interval * 1000)
            val body = try {
                post(
                    "/login/oauth/access_token",
                    FormBody.Builder()
                        .add("client_id", GITHUB_CLIENT_ID)
                        .add("device_code", code.deviceCode)
                        .add("grant_type", "urn:ietf:params:oauth:grant-type:device_code")
                        .build(),
                )
            } catch (_: IOException) {
                continue
            }
            val response = runCatching { json.decodeFromString<TokenResponse>(body) }.getOrNull() ?: continue
            response.accessToken?.let { return it }
            when (response.error) {
                "authorization_pending", null -> Unit
                "slow_down" -> interval += 5
                "access_denied" -> throw AuthException("Sign-in was cancelled on GitHub.")
                "expired_token" -> throw AuthException("The sign-in code expired. Please try again.")
                else -> throw AuthException("Sign-in failed: ${response.error}")
            }
        }
        throw AuthException("The sign-in code expired. Please try again.")
    }

    private suspend fun post(path: String, form: FormBody): String = withContext(Dispatchers.IO) {
        val request = Request.Builder()
            .url(baseUrl + path)
            .header("Accept", "application/json")
            .post(form)
            .build()
        http.newCall(request).execute().use { response ->
            if (!response.isSuccessful) {
                throw AuthException("GitHub sign-in failed (HTTP ${response.code}).")
            }
            response.body.string()
        }
    }
}
