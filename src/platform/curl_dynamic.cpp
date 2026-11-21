// Linux: the libcurl functions http_curl.cpp calls, found at run time in the
// system's libcurl.so.4 rather than linked at build time.
//
// A build linked on Debian or Ubuntu asks for their versioned curl symbols
// (CURL_OPENSSL_4), which Fedora's and Arch's libcurl don't have, so it would
// not start there. Every distribution has a libcurl.so.4 with these functions
// (the soname has been stable since 2006), and the system's curl brings the
// system's own TLS and certificate setup with it.

// curl.h would otherwise make curl_easy_setopt and the like macros (GCC type checks).
#define CURL_DISABLE_TYPECHECK
#include <curl/curl.h>

#include <dlfcn.h>

#include <cstdarg>
#include <cstdio>
#include <cstdlib>
#include <initializer_list>
#include <mutex>

namespace {

struct Curl {
    CURLcode (*global_init)(long);
    CURL* (*easy_init)();
    CURLcode (*easy_setopt)(CURL*, CURLoption, ...);
    CURLcode (*easy_perform)(CURL*);
    CURLcode (*easy_getinfo)(CURL*, CURLINFO, ...);
    void (*easy_cleanup)(CURL*);
    const char* (*easy_strerror)(CURLcode);
    CURLSH* (*share_init)();
    CURLSHcode (*share_setopt)(CURLSH*, CURLSHoption, ...);
    curl_slist* (*slist_append)(curl_slist*, const char*);
    void (*slist_free_all)(curl_slist*);
};

const Curl& Lib() {
    static Curl curl;
    static std::once_flag once;
    std::call_once(once, [] {
        void* lib = nullptr;
        for (const char* name : {"libcurl.so.4", "libcurl-gnutls.so.4", "libcurl.so"}) {
            if ((lib = dlopen(name, RTLD_NOW | RTLD_LOCAL))) break;
        }
        auto get = [lib](const char* name) {
            void* sym = lib ? dlsym(lib, name) : nullptr;
            if (!sym) {
                std::fprintf(stderr, "FastGH needs libcurl (libcurl.so.4), which could not be loaded%s%s\n",
                             lib ? ": missing " : ".", lib ? name : "");
                std::exit(1);
            }
            return sym;
        };
        curl.global_init = reinterpret_cast<decltype(curl.global_init)>(get("curl_global_init"));
        curl.easy_init = reinterpret_cast<decltype(curl.easy_init)>(get("curl_easy_init"));
        curl.easy_setopt = reinterpret_cast<decltype(curl.easy_setopt)>(get("curl_easy_setopt"));
        curl.easy_perform = reinterpret_cast<decltype(curl.easy_perform)>(get("curl_easy_perform"));
        curl.easy_getinfo = reinterpret_cast<decltype(curl.easy_getinfo)>(get("curl_easy_getinfo"));
        curl.easy_cleanup = reinterpret_cast<decltype(curl.easy_cleanup)>(get("curl_easy_cleanup"));
        curl.easy_strerror = reinterpret_cast<decltype(curl.easy_strerror)>(get("curl_easy_strerror"));
        curl.share_init = reinterpret_cast<decltype(curl.share_init)>(get("curl_share_init"));
        curl.share_setopt = reinterpret_cast<decltype(curl.share_setopt)>(get("curl_share_setopt"));
        curl.slist_append = reinterpret_cast<decltype(curl.slist_append)>(get("curl_slist_append"));
        curl.slist_free_all = reinterpret_cast<decltype(curl.slist_free_all)>(get("curl_slist_free_all"));
    });
    return curl;
}

}  // namespace

// The variadic ones take exactly one argument, whose type follows from the
// option's number, as curl reads it itself.
extern "C" {

CURLcode curl_global_init(long flags) { return Lib().global_init(flags); }
CURL* curl_easy_init() { return Lib().easy_init(); }
CURLcode curl_easy_perform(CURL* curl) { return Lib().easy_perform(curl); }
void curl_easy_cleanup(CURL* curl) { Lib().easy_cleanup(curl); }
const char* curl_easy_strerror(CURLcode code) { return Lib().easy_strerror(code); }
CURLSH* curl_share_init() { return Lib().share_init(); }
curl_slist* curl_slist_append(curl_slist* list, const char* s) { return Lib().slist_append(list, s); }
void curl_slist_free_all(curl_slist* list) { Lib().slist_free_all(list); }

CURLcode curl_easy_setopt(CURL* curl, CURLoption option, ...) {
    va_list args;
    va_start(args, option);
    CURLcode result;
    if (option < CURLOPTTYPE_OBJECTPOINT) {
        long value = va_arg(args, long);
        result = Lib().easy_setopt(curl, option, value);
    } else if (option < CURLOPTTYPE_OFF_T) {
        void* value = va_arg(args, void*);  // objects and functions alike
        result = Lib().easy_setopt(curl, option, value);
    } else if (option < CURLOPTTYPE_BLOB) {
        curl_off_t value = va_arg(args, curl_off_t);
        result = Lib().easy_setopt(curl, option, value);
    } else {
        void* value = va_arg(args, void*);
        result = Lib().easy_setopt(curl, option, value);
    }
    va_end(args);
    return result;
}

CURLcode curl_easy_getinfo(CURL* curl, CURLINFO info, ...) {
    va_list args;
    va_start(args, info);
    void* out = va_arg(args, void*);  // always a pointer to the answer
    va_end(args);
    return Lib().easy_getinfo(curl, info, out);
}

CURLSHcode curl_share_setopt(CURLSH* share, CURLSHoption option, ...) {
    va_list args;
    va_start(args, option);
    CURLSHcode result;
    if (option == CURLSHOPT_SHARE || option == CURLSHOPT_UNSHARE) {
        int value = va_arg(args, int);
        result = Lib().share_setopt(share, option, value);
    } else {
        void* value = va_arg(args, void*);
        result = Lib().share_setopt(share, option, value);
    }
    va_end(args);
    return result;
}

}  // extern "C"
