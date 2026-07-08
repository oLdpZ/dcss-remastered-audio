#include <windows.h>
#include <GL/gl.h>
#include "gl_forwarders.h"

/* Sovrascriviamo glViewport per conoscere la risoluzione del framebuffer.
   Nome decorato __stdcall: 4 argomenti da 4 byte -> @16. */
#pragma comment(linker, "/EXPORT:glViewport=_glViewport@16")

static HMODULE g_real = NULL;
int g_vp_w = 0, g_vp_h = 0;   /* aggiornati da glViewport, letti dal postprocess */

typedef void (WINAPI *glViewport_t)(GLint, GLint, GLsizei, GLsizei);

static HMODULE real_gl(void) {
    if (!g_real) g_real = LoadLibraryW(L"opengl32_orig.dll");
    return g_real;
}

void WINAPI glViewport(GLint x, GLint y, GLsizei w, GLsizei h) {
    g_vp_w = (int)w; g_vp_h = (int)h;
    HMODULE hm = real_gl();
    if (hm) {
        glViewport_t real = (glViewport_t)GetProcAddress(hm, "glViewport");
        if (real) real(x, y, w, h);
    }
}

BOOL WINAPI DllMain(HINSTANCE h, DWORD reason, LPVOID unused) {
    (void)unused;
    if (reason == DLL_PROCESS_ATTACH) DisableThreadLibraryCalls(h);
    return TRUE;
}
