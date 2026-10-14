package me.masonasons.fastgh

import me.masonasons.fastgh.data.AuthException
import me.masonasons.fastgh.data.DeviceFlowAuth
import me.masonasons.fastgh.data.GitHubClient
import me.masonasons.fastgh.data.GitHubException
import me.masonasons.fastgh.data.UnauthorizedException
import me.masonasons.fastgh.model.DeviceCode
import kotlinx.coroutines.test.runTest
import okhttp3.OkHttpClient
import okhttp3.mockwebserver.MockResponse
import okhttp3.mockwebserver.MockWebServer
import okhttp3.mockwebserver.SocketPolicy
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Assert.fail
import org.junit.Before
import org.junit.Test

class GitHubClientTest {
    private lateinit var server: MockWebServer
    private lateinit var client: GitHubClient
    private val http = OkHttpClient()

    @Before
    fun setUp() {
        server = MockWebServer()
        server.start()
        client = GitHubClient(http, tokenProvider = { "secret" }, baseUrl = server.url("").toString().trimEnd('/'))
    }

    @After
    fun tearDown() = server.shutdown()

    private fun repoJson(id: Int, pushed: String = "2026-01-01T00:00:00Z") =
        """{"id":$id,"name":"r$id","full_name":"o/r$id","owner":{"login":"o"},"pushed_at":"$pushed"}"""

    @Test
    fun sendsAuthAndFollowsNextLinks() = runTest {
        server.enqueue(
            MockResponse()
                .setBody("[" + (1..100).joinToString(",") { repoJson(it) } + "]")
                .addHeader("Link", "<${server.url("/user/repos?page=2")}>; rel=\"next\""),
        )
        server.enqueue(MockResponse().setBody("[" + repoJson(101) + "]"))

        val repos = client.myRepos()

        assertEquals(101, repos.size)
        val first = server.takeRequest()
        assertEquals("Bearer secret", first.getHeader("Authorization"))
        assertEquals("1", first.requestUrl!!.queryParameter("page"))
        assertEquals("owner,collaborator,organization_member", first.requestUrl!!.queryParameter("affiliation"))
        assertEquals("2", server.takeRequest().requestUrl!!.queryParameter("page"))
    }

    @Test
    fun stopsPagingWithoutNextLink() = runTest {
        server.enqueue(MockResponse().setBody("[" + (1..100).joinToString(",") { repoJson(it) } + "]"))
        assertEquals(100, client.myRepos().size)
        assertEquals(1, server.requestCount)
    }

    @Test
    fun starredIsSortedByLastPush() = runTest {
        server.enqueue(
            MockResponse().setBody(
                "[" + repoJson(1, "2025-01-01T00:00:00Z") + "," + repoJson(2, "2026-05-01T00:00:00Z") + "]",
            ),
        )
        assertEquals(listOf(2L, 1L), client.starred().map { it.id })
    }

    @Test
    fun unauthorizedThrowsSoTheAppCanSignOut() = runTest {
        server.enqueue(MockResponse().setResponseCode(401))
        try {
            client.currentUser()
            fail("Expected UnauthorizedException")
        } catch (_: UnauthorizedException) {
        }
    }

    @Test
    fun httpErrorsCarryGitHubsMessage() = runTest {
        server.enqueue(MockResponse().setResponseCode(404).setBody("""{"message":"Not Found"}"""))
        try {
            client.repo("o", "missing")
            fail("Expected GitHubException")
        } catch (e: GitHubException) {
            assertEquals(404, e.code)
            assertEquals("Not Found", e.message)
        }
    }

    @Test
    fun starAndWatchUseTheDesktopEndpoints() = runTest {
        server.enqueue(MockResponse().setResponseCode(204))
        server.enqueue(MockResponse().setResponseCode(404))
        server.enqueue(MockResponse().setResponseCode(200))
        server.enqueue(MockResponse().setResponseCode(204))

        assertTrue(client.setStarred("o", "r", star = true))
        assertFalse(client.isWatching("o", "r"))
        assertTrue(client.setWatching("o", "r", watch = true))
        assertTrue(client.setWatching("o", "r", watch = false))

        server.takeRequest().let { assertEquals("PUT /user/starred/o/r", "${it.method} ${it.path}") }
        server.takeRequest().let { assertEquals("GET /repos/o/r/subscription", "${it.method} ${it.path}") }
        server.takeRequest().let {
            assertEquals("PUT /repos/o/r/subscription", "${it.method} ${it.path}")
            assertEquals("""{"subscribed":true}""", it.body.readUtf8())
        }
        server.takeRequest().let { assertEquals("DELETE /repos/o/r/subscription", "${it.method} ${it.path}") }
    }

    @Test
    fun issuesDropPullRequestsAndReportMorePages() = runTest {
        server.enqueue(
            MockResponse()
                .setBody("""[{"id":1,"number":1,"title":"Bug"},{"id":2,"number":2,"title":"PR","pull_request":{"url":"x"}}]""")
                .addHeader("Link", "<${server.url("/x?page=2")}>; rel=\"next\""),
        )
        val page = client.issues("o", "r", "closed", page = 1)
        assertEquals(listOf(1), page.items.map { it.number })
        assertTrue(page.hasMore)
        val url = server.takeRequest().requestUrl!!
        assertEquals("closed", url.queryParameter("state"))
        assertEquals("1", url.queryParameter("page"))
    }

    @Test
    fun pullCommentsMergeConversationAndReviewCommentsByTime() = runTest {
        server.enqueue(MockResponse().setBody("""[{"id":1,"body":"later","created_at":"2026-01-03T00:00:00Z"}]"""))
        server.enqueue(
            MockResponse().setBody("""[{"id":1,"body":"earlier","path":"a.kt","created_at":"2026-01-02T00:00:00Z"}]"""),
        )
        val comments = client.pullComments("o", "r", 4)
        assertEquals(listOf("earlier", "later"), comments.map { it.body })
        assertEquals("/repos/o/r/issues/4/comments?per_page=100&page=1", server.takeRequest().path)
        assertEquals("/repos/o/r/pulls/4/comments?per_page=100&page=1", server.takeRequest().path)
    }

    @Test
    fun commentsAndStateChangesPostJson() = runTest {
        server.enqueue(MockResponse().setResponseCode(201).setBody("""{"id":9,"body":"Thanks!"}"""))
        server.enqueue(MockResponse().setBody("""{"id":1,"number":3,"state":"closed"}"""))
        server.enqueue(MockResponse().setBody("""{"merged":true}"""))

        assertEquals("Thanks!", client.createComment("o", "r", 3, "Thanks!").body)
        assertEquals(false, client.setIssueState("o", "r", 3, open = false).isOpen)
        client.mergePull("o", "r", 3, "squash")

        server.takeRequest().let {
            assertEquals("POST /repos/o/r/issues/3/comments", "${it.method} ${it.path}")
            assertEquals("""{"body":"Thanks!"}""", it.body.readUtf8())
        }
        server.takeRequest().let {
            assertEquals("PATCH /repos/o/r/issues/3", "${it.method} ${it.path}")
            assertEquals("""{"state":"closed"}""", it.body.readUtf8())
        }
        server.takeRequest().let {
            assertEquals("PUT /repos/o/r/pulls/3/merge", "${it.method} ${it.path}")
            assertEquals("""{"merge_method":"squash"}""", it.body.readUtf8())
        }
    }

    @Test
    fun mergeFailureCarriesGitHubsReason() = runTest {
        server.enqueue(MockResponse().setResponseCode(405).setBody("""{"message":"Pull Request is not mergeable"}"""))
        try {
            client.mergePull("o", "r", 3, "merge")
            fail("Expected GitHubException")
        } catch (e: GitHubException) {
            assertEquals("Pull Request is not mergeable", e.message)
        }
    }

    @Test
    fun directoryListsFoldersFirstAndEncodesPaths() = runTest {
        server.enqueue(
            MockResponse().setBody(
                """[{"name":"b.txt","path":"my dir/b.txt","type":"file"},
                    {"name":"Zeta","path":"my dir/Zeta","type":"dir"},
                    {"name":"a.txt","path":"my dir/a.txt","type":"file"}]""",
            ),
        )
        val items = client.directory("o", "r", "my dir", ref = "v1.0")
        assertEquals(listOf("Zeta", "a.txt", "b.txt"), items.map { it.name })
        assertEquals("/repos/o/r/contents/my%20dir?ref=v1.0", server.takeRequest().path)
    }

    @Test
    fun stargazersUseTheStarMediaType() = runTest {
        server.enqueue(MockResponse().setBody("""[{"starred_at":"2026-01-01T00:00:00Z","user":{"login":"bob"}}]"""))
        val page = client.stargazers("o", "r", page = 2)
        assertEquals("bob", page.items.single().user.login)
        val request = server.takeRequest()
        assertEquals("application/vnd.github.star+json", request.getHeader("Accept"))
        assertEquals("2", request.requestUrl!!.queryParameter("page"))
    }

    @Test
    fun searchPassesQueryAndSort() = runTest {
        server.enqueue(MockResponse().setBody("""{"total_count":1234,"items":[{"id":1,"name":"r","full_name":"o/r","owner":{"login":"o"}}]}"""))
        val results = client.searchRepos("language:kotlin fastgh", sort = "stars")
        assertEquals(1234, results.totalCount)
        val url = server.takeRequest().requestUrl!!
        assertEquals("/search/repositories", url.encodedPath)
        assertEquals("language:kotlin fastgh", url.queryParameter("q"))
        assertEquals("stars", url.queryParameter("sort"))
    }

    @Test
    fun deviceFlowPollsUntilApproved() = runTest {
        val sleeps = mutableListOf<Long>()
        val auth = DeviceFlowAuth(http, server.url("").toString().trimEnd('/'), sleep = { sleeps += it })
        server.enqueue(MockResponse().setBody("""{"error":"authorization_pending"}"""))
        server.enqueue(MockResponse().setBody("""{"error":"slow_down"}"""))
        server.enqueue(MockResponse().setBody("""{"access_token":"tok","token_type":"bearer"}"""))

        val token = auth.awaitToken(DeviceCode("dev", "ABCD-1234", "https://github.com/login/device", 900, 5))

        assertEquals("tok", token)
        assertEquals(listOf(5000L, 5000L, 10000L), sleeps)
        val body = server.takeRequest().body.readUtf8()
        assertTrue(body.contains("device_code=dev"))
        assertTrue(body.contains("grant_type=urn%3Aietf%3Aparams%3Aoauth%3Agrant-type%3Adevice_code"))
    }

    @Test
    fun deviceFlowKeepsPollingThroughNetworkErrors() = runTest {
        // Android blocks a backgrounded app's network while the user approves in the browser.
        val auth = DeviceFlowAuth(http, server.url("").toString().trimEnd('/'), sleep = {})
        server.enqueue(MockResponse().setSocketPolicy(SocketPolicy.DISCONNECT_AT_START))
        server.enqueue(MockResponse().setBody("""{"error":"authorization_pending"}"""))
        server.enqueue(MockResponse().setBody("""{"access_token":"tok","token_type":"bearer"}"""))

        assertEquals("tok", auth.awaitToken(DeviceCode("dev", "ABCD-1234", "https://github.com/login/device")))
    }

    @Test
    fun deviceFlowReportsDenial() = runTest {
        val auth = DeviceFlowAuth(http, server.url("").toString().trimEnd('/'), sleep = {})
        server.enqueue(MockResponse().setBody("""{"error":"access_denied"}"""))
        try {
            auth.awaitToken(DeviceCode("dev", "ABCD-1234", "https://github.com/login/device"))
            fail("Expected AuthException")
        } catch (e: AuthException) {
            assertEquals("Sign-in was cancelled on GitHub.", e.message)
        }
    }

    @Test
    fun requestCodeSendsClientIdAndScopes() = runTest {
        val auth = DeviceFlowAuth(http, server.url("").toString().trimEnd('/'), sleep = {})
        server.enqueue(
            MockResponse().setBody(
                """{"device_code":"dev","user_code":"WDJB-MJHT","verification_uri":"https://github.com/login/device",
                   "expires_in":900,"interval":5}""",
            ),
        )
        val code = auth.requestCode()
        assertEquals("WDJB-MJHT", code.userCode)
        val request = server.takeRequest()
        assertEquals("/login/device/code", request.path)
        val body = request.body.readUtf8()
        assertTrue(body, body.contains("client_id=Ov23liErbWGLzAKTlLFW"))
        assertTrue(body, body.contains("scope=repo+user+notifications"))
    }
}
