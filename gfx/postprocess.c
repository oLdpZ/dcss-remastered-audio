#include <windows.h>
#include <GL/gl.h>
#include <math.h>
#include "postprocess.h"

/* --- entry point GL2 caricati a runtime --- */
typedef char GLcharx;
typedef GLuint (WINAPI *PFNGLCREATESHADER)(GLenum);
typedef void   (WINAPI *PFNGLSHADERSOURCE)(GLuint, GLsizei, const GLcharx* const*, const GLint*);
typedef void   (WINAPI *PFNGLCOMPILESHADER)(GLuint);
typedef GLuint (WINAPI *PFNGLCREATEPROGRAM)(void);
typedef void   (WINAPI *PFNGLATTACHSHADER)(GLuint, GLuint);
typedef void   (WINAPI *PFNGLLINKPROGRAM)(GLuint);
typedef void   (WINAPI *PFNGLUSEPROGRAM)(GLuint);
typedef GLint  (WINAPI *PFNGLGETUNIFORMLOCATION)(GLuint, const GLcharx*);
typedef void   (WINAPI *PFNGLUNIFORM1F)(GLint, GLfloat);
typedef void   (WINAPI *PFNGLUNIFORM2F)(GLint, GLfloat, GLfloat);
typedef void   (WINAPI *PFNGLUNIFORM3F)(GLint, GLfloat, GLfloat, GLfloat);
typedef void   (WINAPI *PFNGLUNIFORM1I)(GLint, GLint);
typedef void   (WINAPI *PFNGLGETSHADERIV)(GLuint, GLenum, GLint*);

static PFNGLCREATESHADER   pglCreateShader;
static PFNGLSHADERSOURCE   pglShaderSource;
static PFNGLCOMPILESHADER  pglCompileShader;
static PFNGLCREATEPROGRAM  pglCreateProgram;
static PFNGLATTACHSHADER   pglAttachShader;
static PFNGLLINKPROGRAM    pglLinkProgram;
static PFNGLUSEPROGRAM     pglUseProgram;
static PFNGLGETUNIFORMLOCATION pglGetUniformLocation;
static PFNGLUNIFORM1F      pglUniform1f;
static PFNGLUNIFORM2F      pglUniform2f;
static PFNGLUNIFORM3F      pglUniform3f;
static PFNGLUNIFORM1I      pglUniform1i;
static PFNGLGETSHADERIV    pglGetShaderiv;

#ifndef GL_FRAGMENT_SHADER
#define GL_FRAGMENT_SHADER 0x8B30
#endif
#ifndef GL_COMPILE_STATUS
#define GL_COMPILE_STATUS  0x8B81
#endif

static const char *FRAG_SRC =
"uniform sampler2D tex;\n"
"uniform vec3 tint; uniform float strength;\n"
"uniform float desat; uniform float vignette;\n"
"uniform vec2 res;\n"
"void main(){\n"
"  vec2 uv = gl_FragCoord.xy / res;\n"
"  vec3 c = texture2D(tex, uv).rgb;\n"
"  float l = dot(c, vec3(0.299,0.587,0.114));\n"
"  c = mix(c, vec3(l), desat);\n"
"  c = mix(c, tint, strength);\n"
"  float d = distance(uv, vec2(0.5));\n"
"  c *= 1.0 - vignette * smoothstep(0.35, 0.75, d);\n"
"  gl_FragColor = vec4(c, 1.0);\n"
"}\n";

static int g_ready = -1;   /* -1 unknown, 0 failed, 1 ok */
static GLuint g_prog = 0, g_tex = 0;
static GLint u_tint, u_strength, u_desat, u_vignette, u_res, u_tex;

#define LOAD(var,type,name) var=(type)wglGetProcAddress(name); if(!var) return 0;

static int load_entrypoints(void) {
    LOAD(pglCreateShader, PFNGLCREATESHADER, "glCreateShader");
    LOAD(pglShaderSource, PFNGLSHADERSOURCE, "glShaderSource");
    LOAD(pglCompileShader, PFNGLCOMPILESHADER, "glCompileShader");
    LOAD(pglCreateProgram, PFNGLCREATEPROGRAM, "glCreateProgram");
    LOAD(pglAttachShader, PFNGLATTACHSHADER, "glAttachShader");
    LOAD(pglLinkProgram, PFNGLLINKPROGRAM, "glLinkProgram");
    LOAD(pglUseProgram, PFNGLUSEPROGRAM, "glUseProgram");
    LOAD(pglGetUniformLocation, PFNGLGETUNIFORMLOCATION, "glGetUniformLocation");
    LOAD(pglUniform1f, PFNGLUNIFORM1F, "glUniform1f");
    LOAD(pglUniform2f, PFNGLUNIFORM2F, "glUniform2f");
    LOAD(pglUniform3f, PFNGLUNIFORM3F, "glUniform3f");
    LOAD(pglUniform1i, PFNGLUNIFORM1I, "glUniform1i");
    LOAD(pglGetShaderiv, PFNGLGETSHADERIV, "glGetShaderiv");
    return 1;
}

/* Lazy init: compila lo shader, linka il programma, crea la texture di
   cattura. Ritorna 0 su QUALSIASI fallimento -> pp_draw diventa passthrough
   (nessun crash, nessun effetto). Risultato cacheato: eseguito una sola volta. */
int pp_init(void) {
    if (g_ready >= 0) return g_ready;
    g_ready = 0;
    if (!load_entrypoints()) return 0;

    GLuint fs = pglCreateShader(GL_FRAGMENT_SHADER);
    if (!fs) return 0;
    pglShaderSource(fs, 1, &FRAG_SRC, NULL);
    pglCompileShader(fs);
    GLint ok = 0;
    pglGetShaderiv(fs, GL_COMPILE_STATUS, &ok);
    if (!ok) return 0;

    g_prog = pglCreateProgram();
    if (!g_prog) return 0;
    pglAttachShader(g_prog, fs);
    pglLinkProgram(g_prog);
    pglUseProgram(g_prog);
    u_tint = pglGetUniformLocation(g_prog, "tint");
    u_strength = pglGetUniformLocation(g_prog, "strength");
    u_desat = pglGetUniformLocation(g_prog, "desat");
    u_vignette = pglGetUniformLocation(g_prog, "vignette");
    u_res = pglGetUniformLocation(g_prog, "res");
    u_tex = pglGetUniformLocation(g_prog, "tex");
    pglUseProgram(0);

    glGenTextures(1, &g_tex);
    g_ready = 1;
    return 1;
}

/* Cattura il back buffer in una texture e applica tint*desaturazione*vignetta
   in un unico pass a schermo intero via fragment shader.
   Salva/ripristina rigorosamente lo stato GL per non corrompere DCSS. */
void pp_draw(const GfxState *st, int w, int h) {
    if (!st || !st->master_enable || w <= 0 || h <= 0) return;
    if (!pp_init()) return;                 /* fallback: nessun effetto */
    float mi = st->master_intensity;

    glPushAttrib(GL_ALL_ATTRIB_BITS);
    glMatrixMode(GL_PROJECTION); glPushMatrix(); glLoadIdentity(); glOrtho(0, 1, 0, 1, -1, 1);
    glMatrixMode(GL_MODELVIEW);  glPushMatrix(); glLoadIdentity();
    glDisable(GL_DEPTH_TEST); glDisable(GL_LIGHTING); glDisable(GL_BLEND);
    glEnable(GL_TEXTURE_2D);

    /* Cattura il back buffer nella texture. */
    glBindTexture(GL_TEXTURE_2D, g_tex);
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_LINEAR);
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_LINEAR);
    glCopyTexImage2D(GL_TEXTURE_2D, 0, GL_RGB, 0, 0, w, h, 0);

    pglUseProgram(g_prog);
    pglUniform1i(u_tex, 0);
    pglUniform3f(u_tint, st->tint_r, st->tint_g, st->tint_b);
    pglUniform1f(u_strength, st->grade_strength * mi);
    pglUniform1f(u_desat, st->desaturate * mi);
    pglUniform1f(u_vignette, st->vignette * mi);
    pglUniform2f(u_res, (float)w, (float)h);

    glBegin(GL_QUADS);
        glTexCoord2f(0, 0); glVertex2f(0, 0);
        glTexCoord2f(1, 0); glVertex2f(1, 0);
        glTexCoord2f(1, 1); glVertex2f(1, 1);
        glTexCoord2f(0, 1); glVertex2f(0, 1);
    glEnd();
    pglUseProgram(0);

    glMatrixMode(GL_PROJECTION); glPopMatrix();
    glMatrixMode(GL_MODELVIEW);  glPopMatrix();
    glPopAttrib();
}
