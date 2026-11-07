package me.masonasons.fastgh

import me.masonasons.fastgh.model.Event
import me.masonasons.fastgh.model.EventRepo
import me.masonasons.fastgh.model.Owner
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * Checks the Kotlin port of the feed descriptions against the fixture the desktop
 * app is also tested against (tests/event_parity.cpp), so both word the feed alike.
 */
class EventParityTest {
    @Test
    fun descriptionsAndLinksMatchDesktop() {
        val text = javaClass.classLoader!!.getResource("event_parity.json").readText()
        val cases = Json.parseToJsonElement(text) as JsonArray
        assertTrue(cases.size > 50)

        val mismatches = cases.mapNotNull { element ->
            val case = element.jsonObject
            val event = Event(
                type = case["type"]!!.jsonPrimitive.content,
                actor = Owner("alice"),
                repo = EventRepo("owner/repo"),
                payload = case["payload"]!!.jsonObject,
            )
            val expected = case["description"]!!.jsonPrimitive.content to case["webUrl"]!!.jsonPrimitive.content
            val actual = event.description to event.webUrl
            if (expected != actual) "${event.type} ${event.payload}\n  expected $expected\n  actual   $actual" else null
        }
        assertEquals("Mismatches:\n" + mismatches.joinToString("\n"), 0, mismatches.size)
    }
}
