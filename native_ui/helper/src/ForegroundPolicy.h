// Decides whether the candidate window may appear over the current foreground
// application.
//
// This product exists because an unsigned text-service DLL loaded into a game
// process got that game killed by its anti-cheat. The helper never enters
// another process, but drawing a topmost window over a protected game and
// synthesising keystrokes there would invite exactly the kind of scrutiny the
// redesign was meant to avoid. So it stays out of those applications entirely
// and lets PIME's own signed candidate window serve them.
//
// This is not evasion: the goal is for nothing of ours to be near the game.

#ifndef SMARTPRIORITY_FOREGROUND_POLICY_H
#define SMARTPRIORITY_FOREGROUND_POLICY_H

#ifndef NOMINMAX
#define NOMINMAX
#endif

#include <windows.h>

namespace SmartPriority {

// True when the helper may draw over, and accept clicks for, the window that
// currently has focus.
bool foregroundAllowsCandidateWindow();

// Exposed for the decision to be exercised directly rather than only through
// whatever happens to be in the foreground during a test.
bool processNameIsBlocked(const wchar_t* imageName);

} // namespace SmartPriority

#endif
