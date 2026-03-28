(function () {
    const catalogosConsultaState = {
        catalogosDisponibles: [],
        catalogoConsultaActivoId: "",
        detallePorId: new Map(),
        busquedaEntes: "",
        busquedaFuentes: "",
    };

    function normalizeSearchText(value) {
        const replacements = {
            "\u00e1": "a",
            "\u00e9": "e",
            "\u00ed": "i",
            "\u00f3": "o",
            "\u00fa": "u",
            "\u00fc": "u",
            "\u00f1": "n",
        };

        return String(value || "")
            .trim()
            .toLowerCase()
            .replace(/[\u00e1\u00e9\u00ed\u00f3\u00fa\u00fc\u00f1]/g, (match) => replacements[match] || match)
            .replace(/\s+/g, " ");
    }

    function escapeHtml(value) {
        return String(value || "")
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;")
            .replace(/'/g, "&#39;");
    }

    function formatReferenceValue(value, fallback = "-") {
        const normalized = String(value || "").trim();
        return normalized || fallback;
    }

    function getCatalogosConsultaModule() {
        return document.getElementById("catalogosConsultaModule");
    }

    function getCatalogoConsultaDetalleActivo() {
        return catalogosConsultaState.detallePorId.get(catalogosConsultaState.catalogoConsultaActivoId) || null;
    }

    async function fetchCatalogosConsultaJson(url) {
        const response = await fetch(url);
        let payload = {};
        try {
            payload = await response.json();
        } catch (error) {
            payload = {};
        }

        if (!response.ok) {
            throw new Error(payload.error || "No se pudo cargar el cat\u00e1logo de consulta");
        }

        return payload;
    }

    function setCatalogosConsultaLoadingState(message) {
        const loadingNode = document.getElementById("catalogosConsultaLoading");
        const emptyNode = document.getElementById("catalogosConsultaEmpty");
        const contentNode = document.getElementById("catalogosConsultaContent");

        if (loadingNode) {
            loadingNode.hidden = false;
            loadingNode.querySelector("p").textContent = message;
        }
        if (emptyNode) {
            emptyNode.hidden = true;
            emptyNode.textContent = "";
        }
        if (contentNode) {
            contentNode.hidden = true;
        }
    }

    function setCatalogosConsultaEmptyState(message) {
        const loadingNode = document.getElementById("catalogosConsultaLoading");
        const emptyNode = document.getElementById("catalogosConsultaEmpty");
        const contentNode = document.getElementById("catalogosConsultaContent");
        const controlsNode = document.getElementById("catalogosConsultaControls");

        if (loadingNode) {
            loadingNode.hidden = true;
        }
        if (contentNode) {
            contentNode.hidden = true;
        }
        if (controlsNode) {
            controlsNode.hidden = true;
        }
        if (emptyNode) {
            emptyNode.hidden = false;
            emptyNode.textContent = message;
        }
    }

    function syncCatalogoConsultaSelect() {
        const selectNode = document.getElementById("catalogoConsultaSelect");
        if (!selectNode) {
            return;
        }
        selectNode.value = catalogosConsultaState.catalogoConsultaActivoId || "";
    }

    function renderCatalogosConsultaControls() {
        const controlsNode = document.getElementById("catalogosConsultaControls");
        const tabsNode = document.getElementById("catalogosConsultaTabs");
        const selectNode = document.getElementById("catalogoConsultaSelect");
        const catalogosDisponibles = catalogosConsultaState.catalogosDisponibles;

        if (!controlsNode || !tabsNode || !selectNode) {
            return;
        }

        tabsNode.innerHTML = "";
        selectNode.innerHTML = "";

        if (!catalogosDisponibles.length) {
            controlsNode.hidden = true;
            return;
        }

        catalogosDisponibles.forEach((catalogoConsulta) => {
            const tabButton = document.createElement("button");
            tabButton.type = "button";
            tabButton.className = "catalogos-consulta-tab";
            tabButton.textContent = catalogoConsulta.nombre || catalogoConsulta.id;
            tabButton.setAttribute("role", "tab");
            tabButton.setAttribute("data-catalogo-consulta-id", catalogoConsulta.id);
            tabButton.setAttribute(
                "aria-selected",
                String(catalogosConsultaState.catalogoConsultaActivoId === catalogoConsulta.id)
            );
            tabButton.classList.toggle(
                "is-active",
                catalogosConsultaState.catalogoConsultaActivoId === catalogoConsulta.id
            );
            tabButton.addEventListener("click", () => {
                activateCatalogoConsulta(catalogoConsulta.id);
            });
            tabsNode.appendChild(tabButton);

            const optionNode = document.createElement("option");
            optionNode.value = catalogoConsulta.id;
            optionNode.textContent = catalogoConsulta.nombre || catalogoConsulta.id;
            selectNode.appendChild(optionNode);
        });

        controlsNode.hidden = catalogosDisponibles.length <= 1;
        syncCatalogoConsultaSelect();
    }

    function filterCatalogoConsultaEntes(entesReferencia) {
        const query = normalizeSearchText(catalogosConsultaState.busquedaEntes);
        if (!query) {
            return entesReferencia;
        }

        return entesReferencia.filter((enteReferencia) => {
            const haystack = normalizeSearchText([
                enteReferencia.numero_referencia,
                enteReferencia.dd_referencia,
                enteReferencia.siglas,
                enteReferencia.nombre,
                enteReferencia.clasificacion,
                enteReferencia.ambito,
            ].join(" "));
            return haystack.includes(query);
        });
    }

    function filterCatalogoConsultaFuentes(fuentesReferencia) {
        const query = normalizeSearchText(catalogosConsultaState.busquedaFuentes);
        if (!query) {
            return fuentesReferencia;
        }

        return fuentesReferencia.filter((fuenteReferencia) => {
            const haystack = normalizeSearchText([
                fuenteReferencia.ff,
                fuenteReferencia.fuente,
                fuenteReferencia.id_fuente,
                fuenteReferencia.alfa,
                fuenteReferencia.descripcion,
                fuenteReferencia.ramo_federal,
                fuenteReferencia.fondo_ingreso,
            ].join(" "));
            return haystack.includes(query);
        });
    }

    function renderCatalogoConsultaEntes(entesReferencia) {
        const bodyNode = document.getElementById("catalogoConsultaEntesBody");
        const emptyNode = document.getElementById("catalogoConsultaEntesEmpty");
        if (!bodyNode || !emptyNode) {
            return;
        }

        bodyNode.innerHTML = "";

        if (!entesReferencia.length) {
            emptyNode.hidden = false;
            return;
        }

        emptyNode.hidden = true;
        bodyNode.innerHTML = entesReferencia.map((enteReferencia) => `
            <tr>
                <td class="catalogos-consulta-cell-strong">${escapeHtml(formatReferenceValue(enteReferencia.numero_referencia))}</td>
                <td>${escapeHtml(formatReferenceValue(enteReferencia.dd_referencia))}</td>
                <td class="catalogos-consulta-cell-strong">${escapeHtml(formatReferenceValue(enteReferencia.siglas))}</td>
                <td>${escapeHtml(formatReferenceValue(enteReferencia.nombre))}</td>
                <td class="catalogos-consulta-cell-muted">${escapeHtml(formatReferenceValue(enteReferencia.clasificacion))}</td>
            </tr>
        `).join("");
    }

    function renderCatalogoConsultaFuentes(fuentesReferencia) {
        const bodyNode = document.getElementById("catalogoConsultaFuentesBody");
        const emptyNode = document.getElementById("catalogoConsultaFuentesEmpty");
        if (!bodyNode || !emptyNode) {
            return;
        }

        bodyNode.innerHTML = "";

        if (!fuentesReferencia.length) {
            emptyNode.hidden = false;
            return;
        }

        emptyNode.hidden = true;
        bodyNode.innerHTML = fuentesReferencia.map((fuenteReferencia) => `
            <tr>
                <td class="catalogos-consulta-cell-strong">${escapeHtml(formatReferenceValue(fuenteReferencia.ff))}</td>
                <td>${escapeHtml(formatReferenceValue(fuenteReferencia.fuente))}</td>
                <td>${escapeHtml(formatReferenceValue(fuenteReferencia.id_fuente))}</td>
                <td>${escapeHtml(formatReferenceValue(fuenteReferencia.alfa))}</td>
                <td>${escapeHtml(formatReferenceValue(fuenteReferencia.descripcion))}</td>
                <td>${escapeHtml(formatReferenceValue(fuenteReferencia.ramo_federal))}</td>
                <td>${escapeHtml(formatReferenceValue(fuenteReferencia.fondo_ingreso))}</td>
            </tr>
        `).join("");
    }

    function renderCatalogoConsultaDetalle() {
        const loadingNode = document.getElementById("catalogosConsultaLoading");
        const emptyNode = document.getElementById("catalogosConsultaEmpty");
        const contentNode = document.getElementById("catalogosConsultaContent");
        const detalleActivo = getCatalogoConsultaDetalleActivo();

        if (!detalleActivo || !detalleActivo.catalogo_consulta) {
            setCatalogosConsultaEmptyState("No se pudo cargar el detalle del cat\u00e1logo de consulta.");
            return;
        }

        const catalogoConsulta = detalleActivo.catalogo_consulta;
        const entesFiltrados = filterCatalogoConsultaEntes(catalogoConsulta.entes_referencia || []);
        const fuentesFiltradas = filterCatalogoConsultaFuentes(
            catalogoConsulta.fuentes_financiamiento_referencia || []
        );

        document.getElementById("catalogoConsultaNombreActivo").textContent =
            catalogoConsulta.nombre || "-";
        document.getElementById("catalogoConsultaDescripcionActiva").textContent =
            catalogoConsulta.descripcion || "";
        document.getElementById("catalogoConsultaTotalEntes").textContent =
            Number(catalogoConsulta.totales?.entes_referencia || 0).toLocaleString("es-MX");
        document.getElementById("catalogoConsultaTotalFuentes").textContent =
            Number(catalogoConsulta.totales?.fuentes_financiamiento_referencia || 0).toLocaleString("es-MX");

        renderCatalogoConsultaEntes(entesFiltrados);
        renderCatalogoConsultaFuentes(fuentesFiltradas);

        if (loadingNode) {
            loadingNode.hidden = true;
        }
        if (emptyNode) {
            emptyNode.hidden = true;
        }
        if (contentNode) {
            contentNode.hidden = false;
        }

        renderCatalogosConsultaControls();
    }

    async function activateCatalogoConsulta(catalogoConsultaId) {
        if (!catalogoConsultaId) {
            return;
        }

        catalogosConsultaState.catalogoConsultaActivoId = catalogoConsultaId;
        catalogosConsultaState.busquedaEntes = "";
        catalogosConsultaState.busquedaFuentes = "";

        const searchEntesNode = document.getElementById("catalogoConsultaBusquedaEntes");
        const searchFuentesNode = document.getElementById("catalogoConsultaBusquedaFuentes");
        if (searchEntesNode) {
            searchEntesNode.value = "";
        }
        if (searchFuentesNode) {
            searchFuentesNode.value = "";
        }

        renderCatalogosConsultaControls();

        if (catalogosConsultaState.detallePorId.has(catalogoConsultaId)) {
            renderCatalogoConsultaDetalle();
            return;
        }

        setCatalogosConsultaLoadingState("Cargando detalle del cat\u00e1logo de consulta...");

        try {
            const detalleCatalogoConsulta = await fetchCatalogosConsultaJson(
                `/api/catalogos-consulta/${encodeURIComponent(catalogoConsultaId)}`
            );
            catalogosConsultaState.detallePorId.set(catalogoConsultaId, detalleCatalogoConsulta);
            renderCatalogoConsultaDetalle();
        } catch (error) {
            setCatalogosConsultaEmptyState(error.message);
        }
    }

    async function initCatalogosConsultaModule() {
        if (!getCatalogosConsultaModule()) {
            return;
        }

        try {
            setCatalogosConsultaLoadingState("Cargando cat\u00e1logos de consulta...");
            const catalogosConsultaPayload = await fetchCatalogosConsultaJson("/api/catalogos-consulta");
            catalogosConsultaState.catalogosDisponibles =
                catalogosConsultaPayload.catalogos_consulta_disponibles || [];

            if (!catalogosConsultaState.catalogosDisponibles.length) {
                setCatalogosConsultaEmptyState(
                    "No hay cat\u00e1logos de consulta habilitados para tu usuario."
                );
                return;
            }

            catalogosConsultaState.catalogoConsultaActivoId =
                catalogosConsultaPayload.catalogo_consulta_inicial ||
                catalogosConsultaState.catalogosDisponibles[0].id;

            renderCatalogosConsultaControls();
            await activateCatalogoConsulta(catalogosConsultaState.catalogoConsultaActivoId);
        } catch (error) {
            setCatalogosConsultaEmptyState(error.message);
        }
    }

    function bindCatalogosConsultaEvents() {
        const selectNode = document.getElementById("catalogoConsultaSelect");
        const searchEntesNode = document.getElementById("catalogoConsultaBusquedaEntes");
        const searchFuentesNode = document.getElementById("catalogoConsultaBusquedaFuentes");

        if (selectNode) {
            selectNode.addEventListener("change", async (event) => {
                await activateCatalogoConsulta(event.target.value);
            });
        }

        if (searchEntesNode) {
            searchEntesNode.addEventListener("input", (event) => {
                catalogosConsultaState.busquedaEntes = event.target.value || "";
                renderCatalogoConsultaDetalle();
            });
        }

        if (searchFuentesNode) {
            searchFuentesNode.addEventListener("input", (event) => {
                catalogosConsultaState.busquedaFuentes = event.target.value || "";
                renderCatalogoConsultaDetalle();
            });
        }
    }

    function bootstrapCatalogosConsultaModule() {
        if (!getCatalogosConsultaModule()) {
            return;
        }

        bindCatalogosConsultaEvents();
        initCatalogosConsultaModule();
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", bootstrapCatalogosConsultaModule);
    } else {
        bootstrapCatalogosConsultaModule();
    }
})();
