cmake_minimum_required(VERSION 2.8.11)

# override default c/c++ flags, add /MT to link VC++ runtime statically.
# NOTE: these two lines should go before the project() command according to CMake FAQ:
# https://cmake.org/Wiki/CMake_FAQ#Make_Override_Files
set(CMAKE_USER_MAKE_RULES_OVERRIDE	${CMAKE_CURRENT_SOURCE_DIR}/cmake/c_flag_overrides.cmake)
set(CMAKE_USER_MAKE_RULES_OVERRIDE_CXX	${CMAKE_CURRENT_SOURCE_DIR}/cmake/cxx_flag_overrides.cmake)

project(PIME)

# load current number from file
file(READ "version.txt" PIME_VERSION)
# we use semantic versioning: <major>.<minor>.<patch>[-<some suffix>]
# convert the version string into a list (separated by ;)
string(REGEX MATCHALL "[0-9]+" PIME_VERSION_PARTS "${PIME_VERSION}")
list(GET PIME_VERSION_PARTS 0 PIME_VERSION_MAJOR)
list(GET PIME_VERSION_PARTS 1 PIME_VERSION_MINOR)
list(GET PIME_VERSION_PARTS 2 PIME_VERSION_PATCH)

# http://www.utf8everywhere.org/
add_definitions(
	/D_UNICODE=1 /DUNICODE=1 # do Unicode build
	/D_CRT_SECURE_NO_WARNINGS # disable warnings about old libc functions
	/GR- # turn off C++ RTTI
    -DWIN32_LEAN_AND_MEAN
    -D_WIN32_WINNT=0x0600
)

add_subdirectory(${PROJECT_SOURCE_DIR}/libIME2)

# PIME 1.3.0 links the TSF client against jsoncpp. Keep the library while
# excluding the unrelated launcher executable from this UI-only rebuild.
set(JSONCPP_WITH_TESTS OFF CACHE BOOL "")
set(JSONCPP_WITH_POST_BUILD_UNITTEST OFF CACHE BOOL "")
set(JSONCPP_WITH_PKGCONFIG_SUPPORT OFF CACHE BOOL "")
add_subdirectory(${PROJECT_SOURCE_DIR}/jsoncpp)

add_subdirectory(${PROJECT_SOURCE_DIR}/PIMETextService)

# The Smart Priority UI build only needs the TSF DLL. PIMELauncher is retained
# from the signed PIME installer and is intentionally not rebuilt here.

enable_testing()
