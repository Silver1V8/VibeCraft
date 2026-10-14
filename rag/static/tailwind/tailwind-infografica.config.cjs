/* Configurazione della build CSS statica (scripts/build_css.sh): sostituisce il runtime
   Tailwind che generava il CSS nel browser a ogni caricamento. I colori puntano a CSS
   variables: il cambio tema (:root[data-theme]) cambia le variabili, non le classi.
   `content` elenca dove compaiono le classi, anche quelle scritte da JS. */
module.exports = {
  content: ["./templates/infografica.unified.html", "./static/pages/infografica.js", "./static/shared.js"],
  theme: {
          extend: {
            colors: {
              white:  'var(--white)',
              slate:  { 50:'var(--slate-50)',100:'var(--slate-100)',200:'var(--slate-200)',300:'var(--slate-300)',400:'var(--slate-400)',500:'var(--slate-500)',600:'var(--slate-600)',700:'var(--slate-700)',800:'var(--slate-800)',900:'var(--slate-900)',950:'var(--slate-950)' },
              blue:   { 50:'var(--blue-50)',  100:'var(--blue-100)', 200:'var(--blue-200)', 300:'var(--blue-300)', 400:'var(--blue-400)', 500:'var(--blue-500)', 600:'var(--blue-600)', 700:'var(--blue-700)', 800:'var(--blue-800)', 900:'var(--blue-900)', 950:'var(--blue-950)' },
              purple: { 50:'var(--purple-50)',100:'var(--purple-100)',200:'var(--purple-200)',300:'var(--purple-300)',400:'var(--purple-400)',500:'var(--purple-500)',600:'var(--purple-600)',700:'var(--purple-700)',800:'var(--purple-800)',900:'var(--purple-900)',950:'var(--purple-950)' },
              emerald:{ 50:'var(--emerald-50)',100:'var(--emerald-100)',200:'var(--emerald-200)',300:'var(--emerald-300)',400:'var(--emerald-400)',500:'var(--emerald-500)',600:'var(--emerald-600)',700:'var(--emerald-700)',800:'var(--emerald-800)',900:'var(--emerald-900)',950:'var(--emerald-950)' },
              orange: { 50:'var(--orange-50)',100:'var(--orange-100)',200:'var(--orange-200)',300:'var(--orange-300)',400:'var(--orange-400)',500:'var(--orange-500)',600:'var(--orange-600)',700:'var(--orange-700)',800:'var(--orange-800)',900:'var(--orange-900)',950:'var(--orange-950)' },
              pink:   { 600:'var(--pink-600)' },
              gray:   { 200:'var(--gray-200)' },
            },
            fontFamily: { sans: ['var(--font-main)'] }
          }
        }
      };
