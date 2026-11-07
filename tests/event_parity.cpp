// The activity feed's wording, checked against the fixture the Android app's
// EventParityTest also uses (android/app/src/test/resources/event_parity.json),
// so both apps describe the feed identically:
//   cmake --build build --target fastgh_tests && build/fastgh_tests android/app/src/test/resources/event_parity.json
// When the wording changes on purpose, update the fixture's "description" /
// "webUrl" for the cases concerned and keep both apps passing.

#include "core/models.h"

#include <fstream>
#include <iostream>

int main(int argc, char** argv) {
    if (argc < 2) {
        std::cerr << "usage: fastgh_tests <event_parity.json>\n";
        return 2;
    }
    std::ifstream in(argv[1]);
    json cases = json::parse(in, nullptr, false);
    if (!cases.is_array()) {
        std::cerr << "could not read " << argv[1] << "\n";
        return 2;
    }
    int failures = 0;
    auto check = [&](const std::string& what, const std::string& got, const std::string& want) {
        if (got == want) return;
        failures++;
        std::cout << "FAIL " << what << "\n  got:  " << got << "\n  want: " << want << "\n";
    };
    for (const json& c : cases) {
        json data = {{"id", "1"},
                     {"type", c["type"]},
                     {"actor", {{"login", "alice"}}},
                     {"repo", {{"name", "owner/repo"}}},
                     {"payload", c["payload"]},
                     {"created_at", "2026-03-01T12:00:00Z"}};
        Event e = Event::FromJson(data);
        std::string name = c["type"].get<std::string>() + " " + c["payload"].dump();
        check(name + " (description)", e.GetActionDescription(), c["description"].get<std::string>());
        check(name + " (web URL)", e.GetWebUrl(), c["webUrl"].get<std::string>());
    }
    std::cout << cases.size() << " event cases, " << failures << " failure(s)\n";
    return failures ? 1 : 0;
}
