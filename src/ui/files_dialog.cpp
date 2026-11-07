// Browsing a repository's files and reading one (a port of GUI/files.py).

#include "ui/dialogs.h"
#include "ui/ui_common.h"

#include "core/app.h"
#include "core/github.h"
#include "core/models.h"
#include "core/util.h"

#include <algorithm>
#include <map>
#include <memory>
#include <optional>
#include <string>
#include <vector>

namespace {

// Directory listings and file texts already fetched, by ref and path, so going
// back, up, or re-opening a file is instant. Shared with the file viewers.
struct ContentCache {
    std::map<std::string, std::vector<ContentItem>> dirs;
    std::map<std::string, std::string> files;
    static std::string Key(const std::string& ref, const std::string& path) { return ref + '\n' + path; }
};

std::string ParentPath(const std::string& path) {
    size_t slash = path.rfind('/');
    return slash == std::string::npos ? "" : path.substr(0, slash);
}

// "name.ext", "name (1).ext"... the first that doesn't exist in `dir`.
std::string FreeName(const std::string& dir, const std::string& name) {
    std::string path = JoinPath(dir, name);
    if (!PathExists(path)) return path;
    size_t dot = name.rfind('.');
    std::string stem = (dot == std::string::npos || dot == 0) ? name : name.substr(0, dot);
    std::string ext = (dot == std::string::npos || dot == 0) ? "" : name.substr(dot);
    for (int i = 1;; ++i) {
        path = JoinPath(dir, stem + " (" + std::to_string(i) + ")" + ext);
        if (!PathExists(path)) return path;
    }
}

// Downloads a file to `dest` (an empty `dest` means the download folder), then
// says where it went and offers to show it. `owner` must outlive the message.
void DownloadFile(wxWindow* owner, const ContentItem& item, std::string dest) {
    auto account = app::Current();
    if (!account) return;
    if (item.downloadUrl.empty()) {
        ShowError(owner, "This item has no download link.");
        return;
    }
    if (dest.empty()) {
        std::string dir = app::Prefs().GetString("download_location", JoinPath(HomeDir(), "Downloads"));
        MakeDirs(dir);
        dest = FreeName(dir, item.name);
    }
    std::string url = item.downloadUrl, name = item.name;
    SetStatus(U8("Downloading " + name + "..."));
    RunAsync(
        owner,
        [=]() -> std::string {
            return account->DownloadUrl(url, dest) ? "" : GitHubAccount::LastError();
        },
        [owner, dest, name](std::string error) {
            if (!error.empty()) {
                SetStatus(U8("Download of " + name + " failed"));
                ShowError(owner, U8("Couldn't download " + name + ": " + error));
                return;
            }
            SetStatus(U8("Downloaded " + name));
            if (AskYesNo(owner, U8("Downloaded " + name + " to " + dest + ".\n\nShow it in the file manager?"),
                         "Download Complete"))
                RevealInFileManager(U8(dest));
        });
}

void DownloadFileAs(wxWindow* owner, const ContentItem& item) {
    std::string dir = app::Prefs().GetString("download_location", JoinPath(HomeDir(), "Downloads"));
    wxString path = AskSavePath(owner, U8(dir), U8(item.name));
    if (!path.empty()) DownloadFile(owner, item, ToU8(path));
}

// --- One file's text ---
class FileViewDialog : public BaseDialog {
public:
    FileViewDialog(wxWindow* parent, const Repository& repo, const ContentItem& item, const std::string& ref,
                   std::shared_ptr<ContentCache> cache)
        : BaseDialog(parent, U8("View: " + item.name), wxSize(850, 650)),
          m_repo(repo), m_item(item), m_ref(ref), m_cache(std::move(cache)) {
        wxPanel* p = Panel();
        std::string about = "Path: " + item.path + "    Size: " + item.GetSizeStr();
        if (!ref.empty()) about += "    Branch: " + ref;
        Sizer()->Add(new wxStaticText(p, wxID_ANY, U8(about)), 0, wxALL, 5);
        m_text = new wxTextCtrl(p, wxID_ANY, "Loading...", wxDefaultPosition, wxDefaultSize,
                                wxTE_MULTILINE | wxTE_READONLY | wxTE_RICH2 | wxTE_DONTWRAP | wxHSCROLL);
        m_text->SetFont(wxFont(wxFontInfo(11).Family(wxFONTFAMILY_TELETYPE)));
        AddLabeled("&Contents:", m_text, 1);

        auto hasUrl = [this] { return !m_item.htmlUrl.empty(); };
        auto canDownload = [this] { return !m_item.downloadUrl.empty(); };
        m_actions = new ActionBar(p);  // as documented in ui_common.h
        m_actions->Add({"Co&py Contents", [this] { CopyContents(); }, true,
                        [this] { return m_loaded.has_value(); }});
        m_actions->Add({"&Download", [this] { DownloadFile(this, m_item, ""); }, true, canDownload})
            .Shortcut('D', wxMOD_CONTROL);
        m_actions->Add({"&Open in Browser", [this] { OpenUrl(m_item.htmlUrl); }, true, hasUrl})
            .Shortcut('O', wxMOD_CONTROL);
        m_actions->Add({"Download &As...", [this] { DownloadFileAs(this, m_item); }, false, canDownload});
        m_actions->Add({"Open &Raw File in Browser", [this] { OpenUrl(m_item.downloadUrl); }, false, canDownload});
        m_actions->AddSeparator();
        m_actions->Add({"Copy &URL", [this] { CopyToClipboard(U8(m_item.htmlUrl)); }, false, hasUrl});
        m_actions->Add({"Copy Pa&th", [this] { CopyToClipboard(U8(m_item.path)); }});
        Sizer()->Add(m_actions->CreateButtons(), 0, wxALL | wxALIGN_CENTER_HORIZONTAL, 5);
        m_actions->AttachContextMenu(m_text);
        m_actions->Update();

        Finish();
        m_text->SetFocus();
        Load();
    }

private:
    void Load() {
        std::string key = ContentCache::Key(m_ref, m_item.path);
        auto it = m_cache->files.find(key);
        if (it != m_cache->files.end()) {
            ShowContent(it->second);
            return;
        }
        auto account = app::Current();
        if (!account) return;
        std::string owner = m_repo.owner, name = m_repo.name, path = m_item.path, ref = m_ref;
        RunAsync(this, [=] { return account->GetFileContent(owner, name, path, ref); },
                 [this, key](std::optional<std::string> text) {
                     if (!text) {
                         ShowUnreadable();
                         return;
                     }
                     m_cache->files[key] = *text;
                     ShowContent(*text);
                 });
    }

    void ShowContent(const std::string& raw) {
        // Binary (a NUL byte, or not UTF-8, which U8 turns into nothing) can't be shown.
        wxString text = U8(ReplaceAll(raw, "\r\n", "\n"));
        if (raw.find('\0') != std::string::npos || (text.empty() && !raw.empty())) {
            ShowUnreadable();
            return;
        }
        m_loaded = text;
        m_text->ChangeValue(text.empty() ? wxString("(empty file)") : text);
        m_text->SetInsertionPoint(0);
        m_actions->Update();
    }

    void ShowUnreadable() {
        m_loaded.reset();
        m_text->ChangeValue("Unable to display file content.\n\n"
                            "This may be a binary file or the file is too large.\n"
                            "Use Open in Browser or Download to get the file.");
        m_text->SetInsertionPoint(0);
        m_actions->Update();
    }

    void CopyContents() {
        if (m_loaded && !m_loaded->empty())
            CopyToClipboard(*m_loaded);
        else
            ShowError(this, "No content to copy.");
    }

    Repository m_repo;
    ContentItem m_item;
    std::string m_ref;
    std::shared_ptr<ContentCache> m_cache;
    std::optional<wxString> m_loaded;  // set once readable text is shown
    wxTextCtrl* m_text;
    ActionBar* m_actions;
};

// --- Browsing folders ---
class FilesDialog : public BaseDialog {
public:
    FilesDialog(wxWindow* parent, const Repository& repo)
        : BaseDialog(parent, U8("Files: " + repo.fullName), wxSize(750, 550)), m_repo(repo) {
        wxPanel* p = Panel();
        m_branch = new wxChoice(p, wxID_ANY);
        m_branch->Append(repo.defaultBranch.empty() ? wxString("Loading...") : U8(repo.defaultBranch));
        m_branch->SetSelection(0);
        AddLabeled("Bra&nch:", m_branch);
        m_location = new wxTextCtrl(p, wxID_ANY, "/", wxDefaultPosition, wxDefaultSize, wxTE_READONLY);
        AddLabeled("&Location:", m_location);
        m_list = new wxListBox(p, wxID_ANY, wxDefaultPosition, wxDefaultSize, 0, nullptr, wxLB_SINGLE);
        AddLabeled("&Files:", m_list, 1);
        m_summary = new wxStaticText(p, wxID_ANY, "");
        Sizer()->Add(m_summary, 0, wxALL, 5);

        auto hasItem = [this] { return SelectedItem() != nullptr; };
        auto isFile = [this] {
            const ContentItem* i = SelectedItem();
            return i && i->type != "dir" && !i->downloadUrl.empty();
        };
        auto hasUrl = [this] {
            const ContentItem* i = SelectedItem();
            return i && !i->htmlUrl.empty();
        };
        m_actions = new ActionBar(p);  // as documented in ui_common.h
        // Enter / double click: into a folder, or read a file.
        m_actions->Add({"&View", [this] { Activate(); }, true, hasItem});
        m_actions->Add({"&Back", [this] { Back(); }, true, [this] { return !m_history.empty(); }})
            .Shortcut(WXK_BACK);
        m_actions->Add({"&Download",
                        [this] {
                            if (const ContentItem* i = SelectedItem()) DownloadFile(this, *i, "");
                        },
                        true, isFile})
            .Shortcut('D', wxMOD_CONTROL);
        m_actions->Add({"&Open in Browser",
                        [this] {
                            if (const ContentItem* i = SelectedItem()) OpenUrl(i->htmlUrl);
                        },
                        true, hasUrl})
            .Shortcut('O', wxMOD_CONTROL);
#ifdef __WXMAC__
        const int upModifier = wxMOD_CONTROL;  // Cmd+Up, as in Finder
#else
        const int upModifier = wxMOD_ALT;      // Alt+Up, as in Explorer
#endif
        m_actions->Add({"&Up to Parent Folder", [this] { Up(); }, false, [this] { return !m_path.empty(); }})
            .Shortcut(WXK_UP, upModifier);
        // Alt+R was the Root button's access key in the Python dialog.
        m_actions->Add({"&Root Folder", [this] { NavigateTo(""); }, false, [this] { return !m_path.empty(); }})
            .Shortcut('R', wxMOD_ALT);
        m_actions->Add({"Download &As...",
                        [this] {
                            if (const ContentItem* i = SelectedItem()) DownloadFileAs(this, *i);
                        },
                        false, isFile});
        m_actions->Add({"&Refresh", [this] { Reload(); }}).Shortcut(WXK_F5);
        m_actions->AddSeparator();
        // Alt+U was Copy URL's access key in the Python dialog.
        m_actions->Add({"Copy &URL",
                        [this] {
                            if (const ContentItem* i = SelectedItem()) CopyToClipboard(U8(i->htmlUrl));
                        },
                        false, hasUrl})
            .Shortcut('U', wxMOD_ALT);
        m_actions->Add({"Copy Pa&th",
                        [this] {
                            if (const ContentItem* i = SelectedItem()) CopyToClipboard(U8(i->path));
                        },
                        false, hasItem});
        m_actions->Add({"Copy Ra&w URL",
                        [this] {
                            if (const ContentItem* i = SelectedItem()) CopyToClipboard(U8(i->downloadUrl));
                        },
                        false, isFile});
        Sizer()->Add(m_actions->CreateButtons(), 0, wxALL | wxALIGN_CENTER_HORIZONTAL, 5);
        m_actions->AttachContextMenu(m_list);
        m_actions->AttachActivate(m_list);

        m_list->Bind(wxEVT_LISTBOX, [this](wxCommandEvent&) { m_actions->Update(); });
        m_branch->Bind(wxEVT_CHOICE, [this](wxCommandEvent&) {
            int i = m_branch->GetSelection();
            if (i == wxNOT_FOUND || i >= (int)m_branches.size()) return;
            std::string ref = m_branches[i].isDefault ? "" : m_branches[i].name;
            if (ref == m_ref) return;
            m_ref = ref;
            // The same folder on the other branch; Back and Root still work if it isn't there.
            Load(m_path, "");
        });

        Finish();
        m_list->SetFocus();

        // The root listing and the branches at the same time.
        Load("", "");
        LoadBranches();
    }

private:
    const ContentItem* SelectedItem() const {
        int i = Selected(m_list);
        return i >= 0 && i < (int)m_items.size() ? &m_items[i] : nullptr;
    }

    void LoadBranches() {
        auto account = app::Current();
        if (!account) return;
        std::string owner = m_repo.owner, name = m_repo.name;
        RunAsync(this, [=] { return account->GetBranches(owner, name); }, [this](std::vector<Branch> branches) {
            if (branches.empty()) {
                if (m_repo.defaultBranch.empty()) {
                    m_branch->SetString(0, "(default branch)");
                }
                return;
            }
            bool anyDefault = false;
            for (const auto& b : branches) anyDefault |= b.isDefault;
            if (!anyDefault)
                for (auto& b : branches)
                    if (b.name == m_repo.defaultBranch) b.isDefault = true;
            m_branches = std::move(branches);
            wxArrayString names;
            int select = 0;
            for (size_t i = 0; i < m_branches.size(); ++i) {
                names.Add(U8(m_branches[i].name));
                if ((m_branches[i].isDefault ? "" : m_branches[i].name) == m_ref) select = (int)i;
            }
            m_branch->Set(names);
            m_branch->SetSelection(select);
        });
    }

    // Opens a folder, remembering where we were for Back.
    void NavigateTo(const std::string& path, const std::string& select = "") {
        if (path == m_path && !m_items.empty()) return;
        m_history.push_back(m_path);
        Load(path, select);
    }

    void Activate() {
        const ContentItem* item = SelectedItem();
        if (!item) return;
        if (item->type == "dir") {
            NavigateTo(item->path);
        } else {
            ContentItem copy = *item;
            ShowModalDialog<FileViewDialog>(this, m_repo, copy, m_ref, m_cache);
        }
    }

    void Back() {
        if (m_history.empty()) return;
        std::string from = m_path;
        std::string to = m_history.back();
        m_history.pop_back();
        Load(to, ChildOf(to, from));
    }

    void Up() {
        if (m_path.empty()) return;
        std::string from = m_path;
        NavigateTo(ParentPath(from), from);
    }

    void Reload() {
        m_cache->dirs.erase(ContentCache::Key(m_ref, m_path));
        const ContentItem* item = SelectedItem();
        std::string select = item ? item->path : "";
        if (item) m_cache->files.erase(ContentCache::Key(m_ref, item->path));
        Load(m_path, select);
    }

    // When going back from `from` to `to`, the entry in `to` that leads to
    // `from` (to select it), or "".
    static std::string ChildOf(const std::string& to, const std::string& from) {
        if (to.empty()) return from.substr(0, from.find('/'));
        if (!StartsWith(from, to + "/")) return "";
        std::string rest = from.substr(to.size() + 1);
        return to + "/" + rest.substr(0, rest.find('/'));
    }

    // Shows the folder `path` (from the cache when we have it), selecting the
    // entry whose path is `select`.
    void Load(const std::string& path, const std::string& select) {
        m_path = path;
        m_location->ChangeValue(U8("/" + path));
        std::string key = ContentCache::Key(m_ref, path);
        auto it = m_cache->dirs.find(key);
        if (it != m_cache->dirs.end()) {
            ShowContent(it->second, select);
            return;
        }

        int token = ++m_loadToken;
        m_items.clear();
        SetListItems(m_list, {"Loading..."});
        m_summary->SetLabel("Loading...");
        m_actions->Update();

        auto account = app::Current();
        if (!account) {
            SetListItems(m_list, {"Not signed in"});
            return;
        }
        std::string owner = m_repo.owner, name = m_repo.name, ref = m_ref;
        struct Result {
            std::optional<std::vector<ContentItem>> items;
            std::string error;
        };
        RunAsync(
            this,
            [=] {
                Result r{account->GetContents(owner, name, path, ref), ""};
                if (!r.items) r.error = GitHubAccount::LastError();
                return r;
            },
            [this, token, key, path, select](Result r) {
                if (token != m_loadToken) return;  // they went somewhere else meanwhile
                if (!r.items) {
                    m_items.clear();
                    std::string why = r.error.empty() ? "" : ": " + r.error;
                    SetListItems(m_list, {U8("Failed to load this folder" + why)});
                    m_summary->SetLabel("Failed to load contents");
                    m_actions->Update();
                    return;
                }
                auto items = std::move(*r.items);
                // A path that is a file comes back as that one file: read it.
                if (items.size() == 1 && items[0].path == path && items[0].type == "file") {
                    ContentItem file = items[0];
                    Back();
                    ShowModalDialog<FileViewDialog>(this, m_repo, file, m_ref, m_cache);
                    return;
                }
                // Folders first, so they are together when arrowing through.
                std::stable_partition(items.begin(), items.end(),
                                      [](const ContentItem& i) { return i.type == "dir"; });
                m_cache->dirs[key] = items;
                ShowContent(items, select);
            });
    }

    void ShowContent(const std::vector<ContentItem>& items, const std::string& select) {
        ++m_loadToken;  // anything still loading is no longer wanted
        m_items = items;
        std::vector<wxString> rows;
        int selectIndex = 0, dirs = 0;
        for (size_t i = 0; i < items.size(); ++i) {
            const ContentItem& item = items[i];
            std::string row = item.GetDisplayName();
            if (item.type == "dir") {
                ++dirs;
            } else {
                std::string size = item.GetSizeStr();
                if (!size.empty()) row += " (" + size + ")";
            }
            rows.push_back(U8(row));
            if (!select.empty() && item.path == select) selectIndex = (int)i;
        }
        int files = (int)items.size() - dirs;
        if (rows.empty()) rows.push_back("This folder is empty");
        SetListItems(m_list, rows);
        m_list->SetSelection(selectIndex);
        m_summary->SetLabel(wxString::Format("%d folder%s, %d file%s", dirs, Plural(dirs), files, Plural(files)));
        m_actions->Update();
    }

    Repository m_repo;
    std::string m_ref;   // the branch; empty for the default
    std::string m_path;  // the folder shown; empty for the root
    std::vector<std::string> m_history;
    std::vector<ContentItem> m_items;
    std::vector<Branch> m_branches;
    std::shared_ptr<ContentCache> m_cache = std::make_shared<ContentCache>();
    int m_loadToken = 0;

    wxChoice* m_branch;
    wxTextCtrl* m_location;
    wxListBox* m_list;
    wxStaticText* m_summary;
    ActionBar* m_actions;
};

}  // namespace

void ShowFilesDialog(wxWindow* parent, const Repository& repo) {
    ShowModalDialog<FilesDialog>(parent, repo);
}
