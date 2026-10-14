package me.masonasons.fastgh.ui.signin

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Button
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.semantics.LiveRegionMode
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.heading
import androidx.compose.ui.semantics.liveRegion
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.lifecycle.ViewModel
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.lifecycle.viewModelScope
import me.masonasons.fastgh.data.DeviceFlowAuth
import me.masonasons.fastgh.data.GitHubClient
import me.masonasons.fastgh.data.Session
import me.masonasons.fastgh.data.TokenStore
import me.masonasons.fastgh.model.DeviceCode
import me.masonasons.fastgh.ui.components.appViewModel
import me.masonasons.fastgh.ui.components.copyToClipboard
import me.masonasons.fastgh.ui.components.openUrl
import me.masonasons.fastgh.ui.components.userMessage
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch
import java.io.IOException

sealed interface SignInState {
    data object Idle : SignInState
    data object RequestingCode : SignInState
    data class WaitingForApproval(val code: DeviceCode) : SignInState
    data object Finishing : SignInState
    data object SignedIn : SignInState
    data class Failed(val message: String) : SignInState
}

class SignInViewModel(
    private val deviceFlow: DeviceFlowAuth,
    private val github: GitHubClient,
    private val tokenStore: TokenStore,
) : ViewModel() {
    private val _state = MutableStateFlow<SignInState>(SignInState.Idle)
    val state: StateFlow<SignInState> = _state.asStateFlow()

    private var job: Job? = null

    fun start() {
        job?.cancel()
        job = viewModelScope.launch {
            try {
                _state.value = SignInState.RequestingCode
                val code = deviceFlow.requestCode()
                _state.value = SignInState.WaitingForApproval(code)
                val token = deviceFlow.awaitToken(code)
                _state.value = SignInState.Finishing
                // Save the token first so the client sends it when looking up the login.
                tokenStore.save(Session(token, login = ""))
                val login = retryOnNetworkError { github.currentUser().login }
                tokenStore.save(Session(token, login))
                _state.value = SignInState.SignedIn
            } catch (e: CancellationException) {
                throw e
            } catch (e: Exception) {
                tokenStore.clear()
                _state.value = SignInState.Failed(e.userMessage())
            }
        }
    }

    fun cancel() {
        job?.cancel()
        _state.value = SignInState.Idle
    }

    /** Approval often lands while the app is coming back from the browser, before its network is restored. */
    private suspend fun <T> retryOnNetworkError(attempts: Int = 10, block: suspend () -> T): T {
        repeat(attempts - 1) {
            try {
                return block()
            } catch (_: IOException) {
                delay(3_000)
            }
        }
        return block()
    }
}

@Composable
fun SignInScreen(onSignedIn: () -> Unit) {
    val viewModel = appViewModel { SignInViewModel(it.deviceFlow, it.github, it.tokenStore) }
    val state by viewModel.state.collectAsStateWithLifecycle()
    val context = LocalContext.current

    LaunchedEffect(state) {
        if (state == SignInState.SignedIn) onSignedIn()
    }

    Scaffold { padding ->
        Column(
            modifier = Modifier
                .fillMaxSize()
                .padding(padding)
                .verticalScroll(rememberScrollState())
                .padding(24.dp),
            verticalArrangement = Arrangement.spacedBy(16.dp, Alignment.CenterVertically),
            horizontalAlignment = Alignment.CenterHorizontally,
        ) {
            Text(
                "Welcome to FastGH",
                style = MaterialTheme.typography.headlineMedium,
                modifier = Modifier.semantics { heading() },
            )
            when (val s = state) {
                SignInState.Idle, is SignInState.Failed -> {
                    if (s is SignInState.Failed) {
                        Text(
                            s.message,
                            color = MaterialTheme.colorScheme.error,
                            textAlign = TextAlign.Center,
                            modifier = Modifier.semantics { liveRegion = LiveRegionMode.Assertive },
                        )
                    }
                    Text(
                        "Sign in with your GitHub account. You'll get a short code to enter on GitHub's website.",
                        textAlign = TextAlign.Center,
                    )
                    Button(onClick = viewModel::start) {
                        Text(if (s is SignInState.Failed) "Try again" else "Sign in with GitHub")
                    }
                }
                SignInState.RequestingCode, SignInState.Finishing, SignInState.SignedIn -> {
                    CircularProgressIndicator()
                    Text(
                        if (s == SignInState.RequestingCode) "Getting a sign-in code…" else "Finishing sign-in…",
                        modifier = Modifier.semantics { liveRegion = LiveRegionMode.Polite },
                    )
                }
                is SignInState.WaitingForApproval -> {
                    val userCode = s.code.userCode
                    Text(
                        "Enter this code on GitHub:",
                        modifier = Modifier.semantics { liveRegion = LiveRegionMode.Polite },
                    )
                    Text(
                        userCode,
                        style = MaterialTheme.typography.displaySmall,
                        fontFamily = FontFamily.Monospace,
                        // Spell the code out so TalkBack reads it character by character.
                        modifier = Modifier.semantics {
                            contentDescription = "Code: " + userCode.toCharArray().joinToString(" ")
                        },
                    )
                    Button(onClick = {
                        context.copyToClipboard("GitHub sign-in code", userCode)
                        context.openUrl(s.code.verificationUri)
                    }) {
                        Text("Copy code and open GitHub")
                    }
                    Text(
                        "Waiting for you to approve FastGH on GitHub. Come back here once you're done.",
                        textAlign = TextAlign.Center,
                    )
                    OutlinedButton(onClick = viewModel::cancel) { Text("Cancel") }
                }
            }
        }
    }
}
