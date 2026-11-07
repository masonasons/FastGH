#pragma once

// Activity feed filtering (a port of models/feed_filter.py), stored in each
// account's config under the same keys.

#include "core/config.h"
#include "core/models.h"

#include <map>
#include <optional>
#include <set>
#include <string>
#include <utility>
#include <vector>

namespace feedfilter {

extern const std::vector<std::string> kAllEventTypes;
// Event type -> its filterable actions (types missing here have none).
extern const std::map<std::string, std::vector<std::string>> kEventTypeActions;
// Group label (with "&&" for a literal ampersand) -> event types.
extern const std::vector<std::pair<std::string, std::vector<std::string>>> kFilterGroups;

// nullopt: never configured (show everything).
std::optional<std::set<std::string>> LoadVisibleTypes(const Config& accountPrefs);
void SaveVisibleTypes(Config& accountPrefs, const std::set<std::string>& visible);
std::optional<std::set<std::string>> LoadMutedRepos(const Config& accountPrefs);
void SaveMutedRepos(Config& accountPrefs, const std::set<std::string>& muted);
// username (lowercase) -> visible "Type" / "Type:action" keys; empty set mutes the user.
std::optional<std::map<std::string, std::set<std::string>>> LoadUserFilters(const Config& accountPrefs);
void SaveUserFilters(Config& accountPrefs, const std::map<std::string, std::set<std::string>>& filters);

std::string GetEventAction(const Event& event);
bool IsEventVisible(const Event& event, const std::optional<std::set<std::string>>& visible);
std::vector<Event> FilterFeed(const std::vector<Event>& events,
                              const std::optional<std::set<std::string>>& visible,
                              const std::optional<std::set<std::string>>& mutedRepos,
                              const std::optional<std::map<std::string, std::set<std::string>>>& userFilters);

}  // namespace feedfilter
