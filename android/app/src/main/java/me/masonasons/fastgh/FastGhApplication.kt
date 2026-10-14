package me.masonasons.fastgh

import android.app.Application
import me.masonasons.fastgh.data.DeviceFlowAuth
import me.masonasons.fastgh.data.GitHubClient
import me.masonasons.fastgh.data.TokenStore
import okhttp3.OkHttpClient
import java.util.concurrent.TimeUnit

/** Shared singletons; kept deliberately small instead of a DI framework. */
class AppContainer(application: Application) {
    private val http = OkHttpClient.Builder()
        .connectTimeout(15, TimeUnit.SECONDS)
        .readTimeout(30, TimeUnit.SECONDS)
        .build()

    val tokenStore = TokenStore(application)
    val github = GitHubClient(http, tokenProvider = { tokenStore.token })
    val deviceFlow = DeviceFlowAuth(http)
}

class FastGhApplication : Application() {
    lateinit var container: AppContainer
        private set

    override fun onCreate() {
        super.onCreate()
        container = AppContainer(this)
    }
}
