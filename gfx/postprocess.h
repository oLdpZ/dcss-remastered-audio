#pragma once
#include "shared_state.h"
void pp_draw(const GfxState *st, int w, int h);

/* Lazy init dello shader/texture di cattura. Ritorna 1 se pronto, 0 su
   fallimento (nessuna estensione GL2 / errore di compilazione shader).
   Esposta per la harness standalone che deve riportarne l'esito. */
int pp_init(void);
