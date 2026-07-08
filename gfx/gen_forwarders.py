"""Genera gl_forwarders.h dai nomi export della opengl32 reale (SysWOW64).
Ogni export viene inoltrato a opengl32_orig.<name>, TRANNE quelli che
sovrascriviamo noi (OVERRIDES)."""
import pefile, os

REAL = r"C:\Windows\SysWOW64\opengl32.dll"
OVERRIDES = {"glViewport"}   # implementati in gl_proxy.c
HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "gl_forwarders.h")

pe = pefile.PE(REAL, fast_load=True)
pe.parse_data_directories(directories=[pefile.DIRECTORY_ENTRY['IMAGE_DIRECTORY_ENTRY_EXPORT']])
lines = ["/* AUTO-GENERATO da gen_forwarders.py -- non modificare a mano */\n"]
n = 0
for exp in pe.DIRECTORY_ENTRY_EXPORT.symbols:
    if not exp.name:
        continue  # export solo-ordinale: opengl32 non ne ha di rilevanti
    name = exp.name.decode()
    if name in OVERRIDES:
        continue
    lines.append('#pragma comment(linker, "/EXPORT:%s=opengl32_orig.%s")\n' % (name, name))
    n += 1
open(OUT, "w", encoding="ascii").write("".join(lines))
print("scritti %d forwarder in %s" % (n, OUT))
