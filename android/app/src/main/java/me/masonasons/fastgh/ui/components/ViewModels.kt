package me.masonasons.fastgh.ui.components

import androidx.compose.runtime.Composable
import androidx.compose.ui.platform.LocalContext
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewmodel.compose.viewModel
import androidx.lifecycle.viewmodel.initializer
import androidx.lifecycle.viewmodel.viewModelFactory
import me.masonasons.fastgh.AppContainer
import me.masonasons.fastgh.FastGhApplication

@Composable
fun appContainer(): AppContainer =
    (LocalContext.current.applicationContext as FastGhApplication).container

/** Creates a ViewModel with access to the app's shared services. */
@Composable
inline fun <reified VM : ViewModel> appViewModel(
    key: String? = null,
    crossinline create: (AppContainer) -> VM,
): VM {
    val container = appContainer()
    return viewModel(key = key, factory = viewModelFactory { initializer { create(container) } })
}
