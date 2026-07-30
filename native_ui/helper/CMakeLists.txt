cmake_minimum_required(VERSION 3.20)

project(SmartPriorityCandidateUI LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

# The helper runs in its own process and never loads into a host application,
# so it needs no TSF, no libIME2, and no COM plumbing -- only Win32 and GDI.
add_executable(SmartPriorityCandidateUI WIN32
    src/main.cpp
    src/CandidateRenderer.cpp
    src/PipeServer.cpp
)

target_compile_definitions(SmartPriorityCandidateUI PRIVATE
    UNICODE
    _UNICODE
    NOMINMAX
    WIN32_LEAN_AND_MEAN
)

# Sources are UTF-8 without a BOM and contain Chinese literals. Without this,
# MSVC decodes them as the system ANSI codepage and mangles the strings.
if(MSVC)
    target_compile_options(SmartPriorityCandidateUI PRIVATE /utf-8)
endif()

target_link_libraries(SmartPriorityCandidateUI PRIVATE user32 gdi32 shell32)
