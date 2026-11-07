#pragma once

// Running other programs (git) without a console window, from any thread.

#include <functional>
#include <string>
#include <vector>

struct ProcessResult {
    bool started = false;  // false: the program could not be run at all
    int exitCode = -1;
    std::string output;    // stdout and stderr, interleaved, UTF-8
};

// Runs `args` (args[0] is looked up on PATH) in `cwd` and waits for it.
// `onOutput`, when given, is called on the calling thread with each chunk of
// output as it arrives (for progress, e.g. "git clone --progress").
ProcessResult RunProcess(const std::vector<std::string>& args, const std::string& cwd,
                         const std::function<void(const std::string& chunk)>& onOutput = nullptr);

// Whether a program is on PATH ("git", "pwsh").
std::string FindOnPath(const std::string& program);
