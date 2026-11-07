#pragma once

// A list box that loads a page at a time, as the commits list always has: the
// first page shows at once, and when the selection reaches the last item the
// next page is fetched behind a "Loading more..." row. Someone who had arrowed
// onto that row lands on the first new item when it arrives.
//
//   m_issues = new PagedList<Issue>(m_list, "issues", [](const Issue& i) { return U8(i.FormatDisplay()); });
//   m_issues->OnSelect([this] { m_actions->Update(); });
//   m_issues->Load([account, owner, name, state](int page) {
//       return account->GetIssuesPage(owner, name, state, page);
//   });
//
// The PagedList belongs to the list box and is deleted with it: create it with new
// and never delete it. Fetches run on worker threads; a fetch started before the
// last Load() is ignored when it returns.

#include "core/github.h"
#include "ui/ui_common.h"

#include <future>
#include <memory>

template <typename T>
class PagedList {
public:
    using Fetch = std::function<Page<T>(int page)>;  // runs on a worker thread
    using Format = std::function<wxString(const T&)>;
    using Filter = std::function<bool(const T&)>;

    // `noun` names the items in the status rows ("issues": "Loading more issues...", "No issues").
    PagedList(wxListBox* list, const wxString& noun, Format format)
        : m_list(list), m_noun(noun), m_format(std::move(format)) {
        list->Bind(wxEVT_DESTROY, [this, list](wxWindowDestroyEvent& event) {
            event.Skip();
            if (event.GetEventObject() == list) delete this;
        });
        list->Bind(wxEVT_LISTBOX, [this](wxCommandEvent& event) {
            event.Skip();
            if (m_onSelect) m_onSelect();
            MaybeLoadMore();
        });
    }

    // Called after the selection changes (by the reader or a load).
    void OnSelect(std::function<void()> fn) { m_onSelect = std::move(fn); }
    // Called after a page arrives; `first` is true for page 1 (or a refresh).
    void OnLoaded(std::function<void(bool first)> fn) { m_onLoaded = std::move(fn); }
    // Only items passing the filter are shown (the activity feed's event filters).
    void SetFilter(Filter filter) {
        m_filter = std::move(filter);
        Render(true);
    }

    // Moves the focus to the list when its first page arrives (once), as the commits
    // list always did: before then the dialog has nothing to focus but its other controls.
    void FocusWhenLoaded() { m_focusWhenLoaded = true; }

    // Starts again from page 1 with `fetch` (call again when a filter or sort changes).
    void Load(Fetch fetch) {
        m_fetch = std::move(fetch);
        ++m_token;
        m_all.clear();
        m_shown.clear();
        m_nextPage = 1;
        m_hasMore = false;
        m_loading = false;
        m_error.clear();
        SetListItems(m_list, {"Loading..."});
        m_statusRow = true;
        FetchNext();
    }

    // Fetches the pages already loaded again (all at once), keeping the reader's
    // place: for refreshing a list someone may be partway down.
    void Refresh() {
        if (!m_fetch || m_loading) return;
        int pages = std::max(1, m_nextPage - 1);
        int token = ++m_token;
        m_loading = true;
        Fetch fetch = m_fetch;
        RunAsync(
            m_list,
            [fetch, pages] {
                std::vector<std::future<Page<T>>> futures;
                for (int p = 1; p <= pages; p++) futures.push_back(std::async(std::launch::async, fetch, p));
                Result r;
                for (size_t i = 0; i < futures.size(); i++) {
                    Page<T> page = futures[i].get();
                    if (i == 0 && page.items.empty() && !page.hasMore) r.error = GitHubAccount::LastError();
                    r.page.items.insert(r.page.items.end(), std::make_move_iterator(page.items.begin()),
                                        std::make_move_iterator(page.items.end()));
                    r.page.hasMore = page.hasMore;
                    if (!page.hasMore) break;
                }
                return r;
            },
            [this, token, pages](Result r) {
                if (token != m_token) return;
                m_loading = false;
                // A failed refresh leaves what is shown alone.
                if (!r.error.empty() && !m_all.empty()) return;
                m_all = std::move(r.page.items);
                m_hasMore = r.page.hasMore;
                m_nextPage = pages + 1;
                m_error = r.error;
                Render(true);
                if (m_onLoaded) m_onLoaded(true);
            });
    }

    // Re-formats every row (after items changed in place, e.g. a title filled in).
    void Rerender() { Render(true); }

    // The items shown (filtered), in list order.
    const std::vector<T>& Items() const { return m_shown; }
    // Every item loaded, before filtering; change them and call Rerender().
    std::vector<T>& AllItems() { return m_all; }
    const T* Selected() const {
        int i = ::Selected(m_list);
        return i >= 0 && i < static_cast<int>(m_shown.size()) ? &m_shown[i] : nullptr;
    }
    int SelectedIndex() const {
        int i = ::Selected(m_list);
        return i < static_cast<int>(m_shown.size()) ? i : -1;
    }
    bool IsLoading() const { return m_loading; }
    bool HasLoaded() const { return m_nextPage > 1; }
    bool HasMore() const { return m_hasMore; }
    wxListBox* List() const { return m_list; }

private:
    struct Result {
        Page<T> page;
        std::string error;
    };

    void FetchNext() {
        if (!m_fetch) return;
        m_loading = true;
        int page = m_nextPage, token = m_token;
        Fetch fetch = m_fetch;
        RunAsync(
            m_list,
            [fetch, page] {
                Result r{fetch(page), ""};
                if (r.page.items.empty() && !r.page.hasMore) r.error = GitHubAccount::LastError();
                return r;
            },
            [this, token](Result r) {
                if (token != m_token) return;  // from before the last Load()
                m_loading = false;
                bool first = m_nextPage == 1;
                m_nextPage++;
                m_hasMore = r.page.hasMore;
                m_error = r.error;
                AddPage(std::move(r.page.items), first);
                if (first && m_focusWhenLoaded) {
                    m_focusWhenLoaded = false;
                    // Only within its own window: never take the focus from another one.
                    wxWindow* focus = wxWindow::FindFocus();
                    if (!focus || wxGetTopLevelParent(focus) == wxGetTopLevelParent(m_list)) m_list->SetFocus();
                }
                if (m_onLoaded) m_onLoaded(first);
                // A page whose items were all filtered out: keep going.
                if (m_hasMore && !m_shown.empty() && ::Selected(m_list) >= static_cast<int>(m_shown.size()) - 1)
                    MaybeLoadMore();
                else if (m_hasMore && m_shown.empty()) FetchNext();
            });
    }

    void AddPage(std::vector<T> items, bool first) {
        size_t firstNew = m_shown.size();
        bool wasOnStatus = m_statusRow && ::Selected(m_list) == static_cast<int>(m_list->GetCount()) - 1;
        m_all.insert(m_all.end(), items.begin(), items.end());
        if (first) {
            Render(false);
            if (!m_shown.empty()) m_list->SetSelection(0);
            if (m_onSelect) m_onSelect();
            return;
        }
        // Later pages are appended, so the reader's place and the list's scroll stay put.
        if (m_statusRow) {
            m_list->Delete(m_list->GetCount() - 1);
            m_statusRow = false;
        }
        wxArrayString rows;
        for (auto& item : items) {
            if (m_filter && !m_filter(item)) continue;
            rows.Add(m_format(item));
            m_shown.push_back(std::move(item));
        }
        if (!rows.empty()) m_list->Append(rows);
        if (rows.empty() && !m_error.empty()) {
            m_list->Append("Failed to load more " + m_noun + ": " + U8(m_error));
            m_statusRow = true;
        }
        if (wasOnStatus && m_shown.size() > firstNew) {
            m_list->SetSelection(static_cast<int>(firstNew));
            if (m_onSelect) m_onSelect();
        }
    }

    // Shows m_all (filtered) in one go; `keepPlace` keeps the selection index.
    void Render(bool keepPlace) {
        m_shown.clear();
        std::vector<wxString> rows;
        for (const auto& item : m_all) {
            if (m_filter && !m_filter(item)) continue;
            m_shown.push_back(item);
            rows.push_back(m_format(item));
        }
        m_statusRow = rows.empty();
        if (rows.empty()) {
            if (!m_error.empty()) rows.push_back("Failed to load " + m_noun + ": " + U8(m_error));
            else if (m_loading || !HasLoaded()) rows.push_back("Loading...");
            else rows.push_back("No " + m_noun);
        }
        if (!keepPlace) m_list->Clear();
        SetListItems(m_list, rows);
    }

    void MaybeLoadMore() {
        if (m_loading || !m_hasMore || m_shown.empty()) return;
        int i = ::Selected(m_list);
        if (i < static_cast<int>(m_shown.size()) - 1) return;
        m_list->Append("Loading more " + m_noun + "...");
        m_statusRow = true;
        FetchNext();
    }

    wxListBox* m_list;
    wxString m_noun;
    Format m_format;
    Filter m_filter;
    Fetch m_fetch;
    std::function<void()> m_onSelect;
    std::function<void(bool)> m_onLoaded;
    std::vector<T> m_all;
    std::vector<T> m_shown;
    int m_nextPage = 1;
    int m_token = 0;
    bool m_hasMore = false;
    bool m_loading = false;
    bool m_statusRow = false;  // the last row is a status, not an item
    bool m_focusWhenLoaded = false;
    std::string m_error;
};
