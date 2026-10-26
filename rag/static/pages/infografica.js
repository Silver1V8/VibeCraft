/* Script della pagina infografica.unified.html, servito da /static/pages/ (era inline nel
   template): la CSP della console vieta gli script inline (vedi
   api/deps.CONTENT_SECURITY_POLICY). Indentazione lasciata com'era nel template. */
      /* themeVar / startMatrixRain / stopMatrixRain: vedi /static/shared.js.
         Al cambio tema shared.js invoca window.onThemeChange -> ridisegna Mermaid. */
      window.onThemeChange = function () { renderMermaidDiagram(); };
      window.onLangChange = function () {
        document.title = t('infografica.docTitle');
        renderMermaidDiagram();
      };

      /* ──────────── MERMAID: diagramma ricostruito a runtime dai colori del tema ──────────── */
      let mermaidRenderSeq = 0;
      let mermaidRenderPending = true;
      let mermaidRendering = false;
      mermaid.initialize({ startOnLoad: false });
      function buildMermaidSource() {
        const userFill = themeVar('--mm-user-fill'),         userStroke = themeVar('--mm-user-stroke'),         userText = themeVar('--mm-user-text');
        const apiFill  = themeVar('--mm-fastapi-fill'),       apiStroke  = themeVar('--mm-fastapi-stroke'),      apiText  = themeVar('--mm-fastapi-text');
        const qFill    = themeVar('--mm-qdrant-fill'),        qStroke    = themeVar('--mm-qdrant-stroke'),       qText    = themeVar('--mm-qdrant-text');
        const nxFill   = themeVar('--mm-networkx-fill'),      nxStroke   = themeVar('--mm-networkx-stroke'),     nxText   = themeVar('--mm-networkx-text');
        const olFill   = themeVar('--mm-ollama-fill'),        olStroke   = themeVar('--mm-ollama-stroke'),       olText   = themeVar('--mm-ollama-text');
        const font     = themeVar('--mm-font', 'ui-sans-serif, system-ui');

        return `%%{init: {'theme': 'base', 'themeVariables': { 'fontFamily': '${font}'}}}%%
graph TD
    classDef user fill:${userFill},stroke:${userStroke},stroke-width:2px,color:${userText};
    classDef fastapi fill:${apiFill},stroke:${apiStroke},stroke-width:2px,color:${apiText};
    classDef qdrant fill:${qFill},stroke:${qStroke},stroke-width:2px,color:${qText};
    classDef networkx fill:${nxFill},stroke:${nxStroke},stroke-width:2px,color:${nxText};
    classDef ollama fill:${olFill},stroke:${olStroke},stroke-width:2px,color:${olText};

    U["${t('infografica.mm.U')}"]:::user
    S("${t('infografica.mm.S')}"):::fastapi
    RT{"${t('infografica.mm.RT')}"}:::fastapi
    GA[("${t('infografica.mm.GA')}")]:::networkx
    K{"${t('infografica.mm.K')}"}:::fastapi
    V{"${t('infografica.mm.V')}"}:::fastapi
    Q[("${t('infografica.mm.Q')}")]:::qdrant
    NPY[("${t('infografica.mm.NPY')}")]:::fastapi
    CB{"${t('infografica.mm.CB')}"}:::fastapi
    CS[("${t('infografica.mm.CS')}")]:::fastapi
    G[("${t('infografica.mm.G')}")]:::networkx
    C["${t('infografica.mm.C')}"]:::fastapi
    O{"${t('infografica.mm.O')}"}:::ollama
    R["${t('infografica.mm.R')}"]:::user

    U -->|"${t('infografica.mm.eUS')}"| S
    S -->|"${t('infografica.mm.eSRT')}"| RT
    RT -->|"${t('infografica.mm.eRTGA')}"| GA
    GA -->|"${t('infografica.mm.eGAR')}"| R
    RT -->|"${t('infografica.mm.eRTK')}"| K
    K -->|"${t('infografica.mm.eKR')}"| R
    K -->|"${t('infografica.mm.eKV')}"| V
    V -->|"${t('infografica.mm.eVQ')}"| Q
    Q -->|"${t('infografica.mm.eQCB')}"| CB
    NPY -->|"${t('infografica.mm.eNPYCB')}"| CB
    V -->|"${t('infografica.mm.eVCS')}"| CS
    CS -->|"${t('infografica.mm.eCSC')}"| C
    CB -->|"${t('infografica.mm.eCBG')}"| G
    G -->|"${t('infografica.mm.eGC')}"| C
    C -->|"${t('infografica.mm.eCO')}"| O
    O -->|"${t('infografica.mm.eOS')}"| S
    S -->|"${t('infografica.mm.eSR')}"| R`;
      }

      async function renderMermaidDiagram() {
        const container = document.getElementById('rag-mermaid');
        mermaidRenderPending = true;
        // La shell carica srcdoc nascosti: Mermaid richiede geometria reale per le frecce.
        if (mermaidRendering || !container.getBoundingClientRect().width) return;
        mermaidRenderPending = false;
        mermaidRendering = true;
        const seq = ++mermaidRenderSeq;
        const renderId = 'rag-mermaid-svg-' + seq;
        mermaid.initialize({
          startOnLoad: false,
          theme: 'base',
          themeVariables: {
            primaryColor: themeVar('--mm-primary'),
            primaryTextColor: themeVar('--mm-primary-text'),
            primaryBorderColor: themeVar('--mm-primary-border'),
            lineColor: themeVar('--mm-line'),
            secondaryColor: themeVar('--mm-secondary'),
            tertiaryColor: themeVar('--mm-tertiary'),
            edgeLabelBackground: themeVar('--mm-edge-bg'),
            background: themeVar('--mm-bg'),
            fontFamily: themeVar('--mm-font', 'ui-sans-serif, system-ui'),
            fontSize: '15px',
          },
          // Spaziatura di default (~50px) comprimeva gli 11 nodi in una colonna
          // stretta: piu respiro fra un livello e l'altro del flusso TD.
          flowchart: { nodeSpacing: 40, rankSpacing: 65, padding: 12 },
        });
        const source = buildMermaidSource();
        try {
          const { svg } = await mermaid.render(renderId, source);
          if (!container.getBoundingClientRect().width) mermaidRenderPending = true;
          if (!mermaidRenderPending) container.innerHTML = svg;
        } catch (e) {
          if (!container.getBoundingClientRect().width) mermaidRenderPending = true;
          if (!mermaidRenderPending) container.innerHTML = `<p style="color:#f87171">${escapeHtml(t('infografica.mermaid.error', { msg: e.message }))}</p>`;
        } finally {
          // Mermaid lascia il proprio wrapper nel body quando il layout fallisce.
          document.getElementById('d' + renderId)?.remove();
          mermaidRendering = false;
          if (mermaidRenderPending) renderMermaidDiagram();
        }
      }

      document.addEventListener('DOMContentLoaded', () => {
        new ResizeObserver(entries => {
          if (!entries[0].contentRect.width) mermaidRenderPending = true;
          else if (mermaidRenderPending && !mermaidRendering) renderMermaidDiagram();
        }).observe(document.getElementById('rag-mermaid'));
        // Un frame nascosto sospende ResizeObserver; al ritorno può avere la stessa larghezza.
        if (window.frameElement) new MutationObserver(() => renderMermaidDiagram())
          .observe(window.frameElement, { attributes: true, attributeFilter: ['hidden'] });
        renderMermaidDiagram();
      });
