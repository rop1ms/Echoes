#include <windows.h>
#include <cstdlib>
#include <filesystem>
#include <string>

int WINAPI wWinMain(HINSTANCE, HINSTANCE, PWSTR, int) {
    // The signed setup installs this executable beside the embedded runtime.
    const HMODULE python = LoadLibraryExW(
        L"python3.dll", nullptr, LOAD_LIBRARY_SEARCH_APPLICATION_DIR | LOAD_LIBRARY_SEARCH_SYSTEM32);
    using PythonMain = int(__cdecl *)(int, wchar_t **);
    const auto run = python ? reinterpret_cast<PythonMain>(GetProcAddress(python, "Py_Main")) : nullptr;
    if (!run) {
        MessageBoxW(nullptr, L"The embedded Echoes runtime could not be loaded. Please run Echoes Setup.",
                    L"Echoes", MB_OK | MB_ICONERROR);
        return 1;
    }

    // Relaunches and Python workers keep the normal interpreter command line.
    if (__argc > 1) {
        return run(__argc, __wargv);
    }

    std::wstring image(32768, L'\0');
    const DWORD length = GetModuleFileNameW(nullptr, image.data(), static_cast<DWORD>(image.size()));
    if (!length || length >= image.size()) {
        return 1;
    }
    image.resize(length);
    const auto app = std::filesystem::path(image).parent_path().parent_path() / L"app";
    auto script = (app / L"main.py").wstring();
    if (!SetCurrentDirectoryW(app.c_str())) {
        return 1;
    }
    wchar_t *args[] = {image.data(), script.data(), nullptr};
    return run(2, args);
}
