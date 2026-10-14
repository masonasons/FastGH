package me.masonasons.fastgh

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.compose.runtime.Composable
import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.remember
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.navigation.NavDestination.Companion.hasRoute
import androidx.navigation.compose.NavHost
import androidx.navigation.compose.composable
import androidx.navigation.compose.rememberNavController
import androidx.navigation.toRoute
import me.masonasons.fastgh.ui.CommitRoute
import me.masonasons.fastgh.ui.CommitsRoute
import me.masonasons.fastgh.ui.FileRoute
import me.masonasons.fastgh.ui.FilesRoute
import me.masonasons.fastgh.ui.ForksRoute
import me.masonasons.fastgh.ui.IssueRoute
import me.masonasons.fastgh.ui.IssuesRoute
import me.masonasons.fastgh.ui.LocalNavigator
import me.masonasons.fastgh.ui.MainRoute
import me.masonasons.fastgh.ui.Navigator
import me.masonasons.fastgh.ui.PullRoute
import me.masonasons.fastgh.ui.PullsRoute
import me.masonasons.fastgh.ui.ReleaseRoute
import me.masonasons.fastgh.ui.ReleasesRoute
import me.masonasons.fastgh.ui.RepoRoute
import me.masonasons.fastgh.ui.SearchRoute
import me.masonasons.fastgh.ui.SignInRoute
import me.masonasons.fastgh.ui.StargazersRoute
import me.masonasons.fastgh.ui.UserRoute
import me.masonasons.fastgh.ui.commits.CommitScreen
import me.masonasons.fastgh.ui.commits.CommitsScreen
import me.masonasons.fastgh.ui.components.appContainer
import me.masonasons.fastgh.ui.files.FileScreen
import me.masonasons.fastgh.ui.files.FilesScreen
import me.masonasons.fastgh.ui.issues.IssueScreen
import me.masonasons.fastgh.ui.issues.IssuesScreen
import me.masonasons.fastgh.ui.main.MainScreen
import me.masonasons.fastgh.ui.pulls.PullScreen
import me.masonasons.fastgh.ui.pulls.PullsScreen
import me.masonasons.fastgh.ui.releases.ReleaseScreen
import me.masonasons.fastgh.ui.releases.ReleasesScreen
import me.masonasons.fastgh.ui.repo.ForksScreen
import me.masonasons.fastgh.ui.repo.RepoScreen
import me.masonasons.fastgh.ui.repo.StargazersScreen
import me.masonasons.fastgh.ui.search.SearchScreen
import me.masonasons.fastgh.ui.signin.SignInScreen
import me.masonasons.fastgh.ui.theme.FastGhTheme
import me.masonasons.fastgh.ui.user.UserScreen

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()
        setContent {
            FastGhTheme {
                FastGhNavHost()
            }
        }
    }
}

@Composable
private fun FastGhNavHost() {
    val navController = rememberNavController()
    val navigator = remember(navController) { Navigator(navController) }
    val tokenStore = appContainer().tokenStore
    val session by tokenStore.session.collectAsStateWithLifecycle()
    // Decided once; later sign-outs are handled by the effect below.
    val startSignedIn = remember { session != null }

    // Signing out (or an expired token) from any screen returns to sign-in.
    LaunchedEffect(session == null) {
        if (session == null && navController.currentDestination?.hasRoute(SignInRoute::class) != true) {
            navController.navigate(SignInRoute) { popUpTo(navController.graph.id) { inclusive = true } }
        }
    }

    CompositionLocalProvider(LocalNavigator provides navigator) {
        NavHost(
            navController = navController,
            startDestination = if (startSignedIn) MainRoute else SignInRoute,
        ) {
            composable<SignInRoute> {
                SignInScreen(onSignedIn = {
                    navController.navigate(MainRoute) { popUpTo(navController.graph.id) { inclusive = true } }
                })
            }
            composable<MainRoute> { MainScreen() }
            composable<SearchRoute> { SearchScreen() }
            composable<RepoRoute> { entry ->
                val r = entry.toRoute<RepoRoute>()
                RepoScreen(r.owner, r.name)
            }
            composable<UserRoute> { entry -> UserScreen(entry.toRoute<UserRoute>().login) }
            composable<IssuesRoute> { entry ->
                val r = entry.toRoute<IssuesRoute>()
                IssuesScreen(r.owner, r.name)
            }
            composable<IssueRoute> { entry ->
                val r = entry.toRoute<IssueRoute>()
                IssueScreen(r.owner, r.name, r.number)
            }
            composable<PullsRoute> { entry ->
                val r = entry.toRoute<PullsRoute>()
                PullsScreen(r.owner, r.name)
            }
            composable<PullRoute> { entry ->
                val r = entry.toRoute<PullRoute>()
                PullScreen(r.owner, r.name, r.number)
            }
            composable<CommitsRoute> { entry ->
                val r = entry.toRoute<CommitsRoute>()
                CommitsScreen(r.owner, r.name, r.branch)
            }
            composable<CommitRoute> { entry ->
                val r = entry.toRoute<CommitRoute>()
                CommitScreen(r.owner, r.name, r.sha)
            }
            composable<ReleasesRoute> { entry ->
                val r = entry.toRoute<ReleasesRoute>()
                ReleasesScreen(r.owner, r.name)
            }
            composable<ReleaseRoute> { entry ->
                val r = entry.toRoute<ReleaseRoute>()
                ReleaseScreen(r.owner, r.name, r.id)
            }
            composable<FilesRoute> { entry ->
                val r = entry.toRoute<FilesRoute>()
                FilesScreen(r.owner, r.name, r.path, r.ref)
            }
            composable<FileRoute> { entry ->
                val r = entry.toRoute<FileRoute>()
                FileScreen(r.owner, r.name, r.path, r.ref)
            }
            composable<ForksRoute> { entry ->
                val r = entry.toRoute<ForksRoute>()
                ForksScreen(r.owner, r.name)
            }
            composable<StargazersRoute> { entry ->
                val r = entry.toRoute<StargazersRoute>()
                StargazersScreen(r.owner, r.name)
            }
        }
    }
}
