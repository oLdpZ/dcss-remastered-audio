/* Harness standalone per validare il post-process shader-based (Task 5)
   SENZA lanciare crawl.exe. Crea una finestra Win32 + contesto GL, disegna
   una scena colorata di test ogni frame, poi chiama pp_draw() con uno
   GfxState hardcoded (tinta verde, desaturazione, vignetta). Stampa su
   stdout una riga machine-readable "PP_INIT: OK/FAIL" al primo frame per
   permettere una verifica headless (nessun giudizio visivo automatico).
   Sottosistema console (entry point main): stdout funziona senza AllocConsole,
   la finestra GL viene comunque creata e mostrata per la verifica umana. */

#include <windows.h>
#include <GL/gl.h>
#include <stdio.h>
#include "../postprocess.h"
#include "../shared_state.h"

static LRESULT CALLBACK WndProc(HWND hwnd, UINT msg, WPARAM wp, LPARAM lp) {
    switch (msg) {
        case WM_CLOSE:
            DestroyWindow(hwnd);
            return 0;
        case WM_DESTROY:
            PostQuitMessage(0);
            return 0;
    }
    return DefWindowProcW(hwnd, msg, wp, lp);
}

static void draw_test_scene(int w, int h) {
    glViewport(0, 0, w, h);
    glClearColor(0.15f, 0.15f, 0.2f, 1.0f);
    glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT);

    glMatrixMode(GL_PROJECTION);
    glLoadIdentity();
    glOrtho(0, 1, 0, 1, -1, 1);
    glMatrixMode(GL_MODELVIEW);
    glLoadIdentity();

    glDisable(GL_TEXTURE_2D);
    glDisable(GL_DEPTH_TEST);
    glDisable(GL_BLEND);

    /* quadrato rosso in alto a sinistra */
    glColor3f(1.0f, 0.1f, 0.1f);
    glBegin(GL_QUADS);
        glVertex2f(0.05f, 0.55f); glVertex2f(0.45f, 0.55f);
        glVertex2f(0.45f, 0.95f); glVertex2f(0.05f, 0.95f);
    glEnd();

    /* quadrato blu in basso a destra */
    glColor3f(0.1f, 0.3f, 1.0f);
    glBegin(GL_QUADS);
        glVertex2f(0.55f, 0.05f); glVertex2f(0.95f, 0.05f);
        glVertex2f(0.95f, 0.45f); glVertex2f(0.55f, 0.45f);
    glEnd();

    /* quadrato giallo al centro */
    glColor3f(1.0f, 1.0f, 0.1f);
    glBegin(GL_QUADS);
        glVertex2f(0.35f, 0.35f); glVertex2f(0.65f, 0.35f);
        glVertex2f(0.65f, 0.65f); glVertex2f(0.35f, 0.65f);
    glEnd();
}

int main(void) {
    const int W = 640, H = 480;

    WNDCLASSW wc = {0};
    wc.lpfnWndProc = WndProc;
    wc.hInstance = GetModuleHandleW(NULL);
    wc.lpszClassName = L"PPHarnessWndClass";
    wc.hCursor = LoadCursorW(NULL, (LPCWSTR)IDC_ARROW);
    RegisterClassW(&wc);

    RECT r = {0, 0, W, H};
    AdjustWindowRect(&r, WS_OVERLAPPEDWINDOW, FALSE);
    HWND hwnd = CreateWindowW(wc.lpszClassName, L"pp_draw shader harness (Task 5)",
        WS_OVERLAPPEDWINDOW, CW_USEDEFAULT, CW_USEDEFAULT,
        r.right - r.left, r.bottom - r.top, NULL, NULL, wc.hInstance, NULL);
    if (!hwnd) {
        printf("PP_INIT: FAIL (CreateWindow failed, err=%lu)\n", GetLastError());
        return 1;
    }
    ShowWindow(hwnd, SW_SHOW);

    HDC hdc = GetDC(hwnd);

    PIXELFORMATDESCRIPTOR pfd = {0};
    pfd.nSize = sizeof(pfd);
    pfd.nVersion = 1;
    pfd.dwFlags = PFD_DRAW_TO_WINDOW | PFD_SUPPORT_OPENGL | PFD_DOUBLEBUFFER;
    pfd.iPixelType = PFD_TYPE_RGBA;
    pfd.cColorBits = 32;
    pfd.cDepthBits = 24;
    pfd.iLayerType = PFD_MAIN_PLANE;

    int pf = ChoosePixelFormat(hdc, &pfd);
    if (!pf || !SetPixelFormat(hdc, pf, &pfd)) {
        printf("PP_INIT: FAIL (pixel format setup failed)\n");
        return 1;
    }

    HGLRC hglrc = wglCreateContext(hdc);
    if (!hglrc || !wglMakeCurrent(hdc, hglrc)) {
        printf("PP_INIT: FAIL (wglCreateContext/MakeCurrent failed)\n");
        return 1;
    }

    /* GfxState di test hardcoded: tinta verde, desaturazione parziale,
       vignetta moderata, effetto attivo a piena intensita'. */
    GfxState fake = {0};
    fake.version = 1;
    fake.master_enable = 1;
    fake.master_intensity = 1.0f;
    fake.tint_r = 0.1f; fake.tint_g = 1.0f; fake.tint_b = 0.1f;
    fake.grade_strength = 0.35f;
    fake.desaturate = 0.5f;
    fake.vignette = 0.3f;

    int first_frame = 1;
    int running = 1;
    int frame_count = 0;
    MSG msg;
    while (running) {
        while (PeekMessageW(&msg, NULL, 0, 0, PM_REMOVE)) {
            if (msg.message == WM_QUIT) { running = 0; break; }
            TranslateMessage(&msg);
            DispatchMessageW(&msg);
        }
        if (!running) break;

        /* Ogni ~90 frame (~1.5s a 60fps) fa scattare a turno flash, shake
           e bloom bumpando il rispettivo seq counter, cosi' si vede la
           envelope decadere senza input umano (Task 8 harness). */
        frame_count++;
        int phase = (frame_count / 90) % 3;
        if (frame_count % 90 == 1) {
            if (phase == 0) {
                fake.flash_seq++;
                fake.flash_r = 1.0f; fake.flash_g = 1.0f; fake.flash_b = 1.0f;
                fake.flash_intensity = 0.8f;
            } else if (phase == 1) {
                fake.shake_seq++;
                fake.shake_intensity = 1.0f;
            } else {
                fake.bloom_seq++;
                fake.bloom_r = 1.0f; fake.bloom_g = 0.85f; fake.bloom_b = 0.3f;
                fake.bloom_intensity = 1.0f;
            }
        }

        draw_test_scene(W, H);
        pp_draw(&fake, W, H);

        if (first_frame) {
            first_frame = 0;
            int ok = pp_init();
            if (ok) {
                printf("PP_INIT: OK\n");
            } else {
                printf("PP_INIT: FAIL\n");
            }
            fflush(stdout);
        }

        SwapBuffers(hdc);
    }

    wglMakeCurrent(NULL, NULL);
    wglDeleteContext(hglrc);
    ReleaseDC(hwnd, hdc);
    return 0;
}
