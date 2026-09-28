/* Configurazione del runtime Tailwind (/static/vendor/tailwind.min.js), letta al primo
   scan delle classi: era uno <script> inline nel template, spostata qui per la CSP. */
    /* Tailwind punta a CSS variables: le classi (bg-slate-900, text-blue-400, ecc.)
       sono generate UNA volta sola con `var(--...)` come valore colore. Il cambio
       tema (:root[data-theme]) aggiorna le variabili e ridipinge tutto senza
       rigenerare le classi Tailwind -> è così che funziona il live-flip. */
    tailwind.config = {
      theme: {
        extend: {
          colors: {
            brand:  { 50:'var(--brand-50)',100:'var(--brand-100)',200:'var(--brand-200)',300:'var(--brand-300)',400:'var(--brand-400)',500:'var(--brand-500)',600:'var(--brand-600)',700:'var(--brand-700)',800:'var(--brand-800)',900:'var(--brand-900)',950:'var(--brand-950)' },
            slate:  { 50:'var(--slate-50)', 100:'var(--slate-100)',200:'var(--slate-200)',300:'var(--slate-300)',400:'var(--slate-400)',500:'var(--slate-500)',600:'var(--slate-600)',700:'var(--slate-700)',800:'var(--slate-800)',900:'var(--slate-900)',950:'var(--slate-950)' },
            blue:   { 50:'var(--blue-50)',  100:'var(--blue-100)', 200:'var(--blue-200)', 300:'var(--blue-300)', 400:'var(--blue-400)', 500:'var(--blue-500)', 600:'var(--blue-600)', 700:'var(--blue-700)', 800:'var(--blue-800)', 900:'var(--blue-900)', 950:'var(--blue-950)' },
            purple: { 50:'var(--purple-50)',100:'var(--purple-100)',200:'var(--purple-200)',300:'var(--purple-300)',400:'var(--purple-400)',500:'var(--purple-500)',600:'var(--purple-600)',700:'var(--purple-700)',800:'var(--purple-800)',900:'var(--purple-900)',950:'var(--purple-950)' },
          },
          fontFamily: { sans: ['var(--font-main)'] }
        }
      }
    }
