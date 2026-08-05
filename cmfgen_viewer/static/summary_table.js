(function () {
    const table = document.getElementById("summary-table");
    if (!table || !table.tBodies.length) {
        return;
    }

    const tbody = table.tBodies[0];
    const headers = Array.from(table.querySelectorAll(".table-sort"));
    const copyButton = document.getElementById("summary-copy-btn");
    const scatterPlot = document.getElementById("summary-scatter-plot");
    const modeHrButton = document.getElementById("summary-scatter-plot-mode-hr");
    const modeGenericButton = document.getElementById("summary-scatter-plot-mode-generic");
    const genericControls = document.getElementById("summary-scatter-plot-generic-controls");
    const hrInfo = document.getElementById("summary-scatter-plot-hr-info");
    const hrAxisWrap = document.getElementById("summary-scatter-plot-hr-axis-wrap");
    const hrAxisLogButton = document.getElementById("summary-scatter-plot-hr-axis-log-values");
    const hrAxisLog10Button = document.getElementById("summary-scatter-plot-hr-axis-log10-values");
    const hrOverlayWrap = document.getElementById("summary-scatter-plot-hr-overlay-wrap");
    const hrOverlayToggle = document.getElementById("summary-scatter-plot-hr-overlay-toggle");
    const hrOverlayDataNode = document.getElementById("summary-scatter-plot-hr-overlay-data");
    const xColumnSelect = document.getElementById("summary-scatter-plot-xcol");
    const yColumnSelect = document.getElementById("summary-scatter-plot-ycol");
    const xScaleSelect = document.getElementById("summary-scatter-plot-xscale");
    const yScaleSelect = document.getElementById("summary-scatter-plot-yscale");
    const plotHint = document.getElementById("summary-scatter-plot-hint");
    const selectionClearButton = document.getElementById("summary-scatter-plot-selection-clear");
    const selectionStatus = document.getElementById("summary-scatter-plot-selection-status");
    let currentPlotMode = "generic";
    let currentHrAxisMode = "log_values";
    let openModelOnClick = false;
    let selectedEntryIndexes = null;
    let hrOverlayData = null;
    if (hrOverlayDataNode) {
        try {
            const parsed = JSON.parse(hrOverlayDataNode.textContent || "null");
            if (parsed && Array.isArray(parsed.points) && parsed.points.length) {
                hrOverlayData = parsed;
            }
        } catch (err) {
            hrOverlayData = null;
        }
    }
    if (!headers.length) {
        return;
    }

    const columnCount = headers.length;
    const rowEntries = Array.from(tbody.querySelectorAll("tr[data-entry]")).map(function (row, index) {
        const rawValues = [];
        for (let column = 0; column < columnCount; column += 1) {
            rawValues.push(String(row.dataset["col" + column] || "").trim());
        }
        const entry = {
            row: row,
            index: index,
            modelKey: (rawValues[0] || "").toLowerCase(),
            modelUrl: String(row.dataset.modelUrl || "").trim(),
            rawValues: rawValues,
            stringKeys: new Array(columnCount),
            numericKeys: new Array(columnCount),
            numericReady: new Array(columnCount).fill(false),
        };
        row.__summaryEntry = entry;
        return entry;
    });

    function resetIndicators() {
        headers.forEach((header) => {
            header.classList.remove("active");
            header.dataset.direction = "";
            const indicator = header.querySelector(".sort-indicator");
            if (indicator) {
                indicator.textContent = "";
            }
        });
    }

    function compareModelOrder(leftEntry, rightEntry) {
        if (leftEntry.modelKey < rightEntry.modelKey) {
            return -1;
        }
        if (leftEntry.modelKey > rightEntry.modelKey) {
            return 1;
        }
        return leftEntry.index - rightEntry.index;
    }

    function readStringValue(entry, column) {
        const cached = entry.stringKeys[column];
        if (cached !== undefined) {
            return cached;
        }
        const value = (entry.rawValues[column] || "").toLowerCase();
        entry.stringKeys[column] = value;
        return value;
    }

    function readNumericValueFromEntry(entry, column) {
        if (entry.numericReady[column]) {
            return entry.numericKeys[column];
        }
        const numeric = Number(entry.rawValues[column] || "");
        const value = Number.isFinite(numeric) ? numeric : null;
        entry.numericKeys[column] = value;
        entry.numericReady[column] = true;
        return value;
    }

    function applySortedRows(entries) {
        const fragment = document.createDocumentFragment();
        entries.forEach(function (entry) {
            fragment.appendChild(entry.row);
        });
        tbody.appendChild(fragment);
    }

    function applySort(header) {
        const column = Number(header.dataset.column || "0");
        const type = header.dataset.type || "string";
        const wasActive = header.classList.contains("active");
        const currentDirection = header.dataset.direction || "asc";
        const direction = wasActive && currentDirection === "asc" ? "desc" : "asc";
        const factor = direction === "asc" ? 1 : -1;
        let nextEntries = [];
        if (type === "number") {
            const withValues = [];
            const missingValues = [];
            rowEntries.forEach(function (entry) {
                const value = readNumericValueFromEntry(entry, column);
                if (value === null) {
                    missingValues.push(entry);
                } else {
                    withValues.push(entry);
                }
            });

            withValues.sort(function (leftEntry, rightEntry) {
                const leftValue = readNumericValueFromEntry(leftEntry, column);
                const rightValue = readNumericValueFromEntry(rightEntry, column);
                if (leftValue < rightValue) {
                    return -1 * factor;
                }
                if (leftValue > rightValue) {
                    return 1 * factor;
                }
                return compareModelOrder(leftEntry, rightEntry);
            });
            missingValues.sort(compareModelOrder);
            nextEntries = withValues.concat(missingValues);
        } else {
            nextEntries = rowEntries.slice();
            nextEntries.sort(function (leftEntry, rightEntry) {
                const leftValue = readStringValue(leftEntry, column);
                const rightValue = readStringValue(rightEntry, column);
                if (leftValue < rightValue) {
                    return -1 * factor;
                }
                if (leftValue > rightValue) {
                    return 1 * factor;
                }
                return compareModelOrder(leftEntry, rightEntry);
            });
        }

        rowEntries.length = 0;
        nextEntries.forEach(function (entry) {
            rowEntries.push(entry);
        });
        applySortedRows(rowEntries);

        resetIndicators();
        header.classList.add("active");
        header.dataset.direction = direction;
        const indicator = header.querySelector(".sort-indicator");
        if (indicator) {
            indicator.textContent = direction === "asc" ? "▲" : "▼";
        }
    }

    headers.forEach((header) => {
        header.addEventListener("click", function () {
            applySort(header);
        });
    });

    function normalizeText(value) {
        return String(value || "").replace(/\s+/g, " ").trim();
    }

    function buildExportText() {
        const lines = [];
        const headerCells = Array.from(table.tHead.rows[0].cells);
        const headerValues = headerCells.map((cell) => {
            const code = cell.querySelector("code");
            return normalizeText(code ? code.textContent : cell.textContent);
        });
        lines.push(headerValues.join(" "));

        rowEntries.forEach(function (entry) {
            if (entry.row.hidden) {
                return;
            }
            const values = Array.from(entry.row.cells).map((cell) => {
                const code = cell.querySelector("code");
                return normalizeText(code ? code.textContent : cell.textContent);
            });
            lines.push(values.join(" "));
        });
        return lines.join("\n");
    }

    function copyWithFallback(text) {
        const textarea = document.createElement("textarea");
        textarea.value = text;
        textarea.setAttribute("readonly", "readonly");
        textarea.style.position = "fixed";
        textarea.style.left = "-9999px";
        document.body.appendChild(textarea);
        textarea.select();
        let copied = false;
        try {
            copied = document.execCommand("copy");
        } catch (err) {
            copied = false;
        }
        document.body.removeChild(textarea);
        return copied;
    }

    function flashCopyState(message, className) {
        if (!copyButton) {
            return;
        }
        const original = copyButton.dataset.label || "Copy as Text";
        copyButton.textContent = message;
        copyButton.classList.remove("btn-outline-primary", "btn-outline-danger", "btn-outline-success");
        copyButton.classList.add(className);
        window.setTimeout(function () {
            copyButton.textContent = original;
            copyButton.classList.remove("btn-outline-danger", "btn-outline-success");
            copyButton.classList.add("btn-outline-primary");
        }, 1200);
    }

    if (copyButton) {
        copyButton.dataset.label = normalizeText(copyButton.textContent) || "Copy as Text";
        copyButton.addEventListener("click", function () {
            const text = buildExportText();
            if (!text) {
                flashCopyState("Nothing to Copy", "btn-outline-danger");
                return;
            }
            if (navigator.clipboard && window.isSecureContext) {
                navigator.clipboard.writeText(text).then(
                    function () {
                        flashCopyState("Copied", "btn-outline-success");
                    },
                    function () {
                        const copied = copyWithFallback(text);
                        flashCopyState(copied ? "Copied" : "Copy Failed", copied ? "btn-outline-success" : "btn-outline-danger");
                    },
                );
                return;
            }
            const copied = copyWithFallback(text);
            flashCopyState(copied ? "Copied" : "Copy Failed", copied ? "btn-outline-success" : "btn-outline-danger");
        });
    }

    function bindVerticalResize(plotElement) {
        const container = plotElement.closest(".plotly-resizable");
        if (!container) {
            return;
        }
        if (window.ResizeObserver && !plotElement.__plotResizeObserver) {
            let frameId = null;
            const observer = new ResizeObserver(function () {
                if (frameId !== null) {
                    window.cancelAnimationFrame(frameId);
                }
                frameId = window.requestAnimationFrame(function () {
                    if (plotElement.data) {
                        Plotly.Plots.resize(plotElement);
                    }
                });
            });
            observer.observe(container);
            plotElement.__plotResizeObserver = observer;
        }

        const handle = container.querySelector(".plot-resize-handle");
        if (!handle || handle.__plotDragBound) {
            return;
        }
        handle.__plotDragBound = true;

        let dragState = null;
        const minHeight = 320;

        function setHeight(nextHeight) {
            container.style.height = Math.max(minHeight, Math.round(nextHeight)) + "px";
            if (plotElement.data) {
                Plotly.Plots.resize(plotElement);
            }
        }

        function finishDrag(event) {
            if (!dragState || event.pointerId !== dragState.pointerId) {
                return;
            }
            if (handle.releasePointerCapture) {
                handle.releasePointerCapture(event.pointerId);
            }
            dragState = null;
            document.body.classList.remove("plot-resizing");
        }

        handle.addEventListener("pointerdown", function (event) {
            if (event.button !== 0) {
                return;
            }
            event.preventDefault();
            dragState = {
                pointerId: event.pointerId,
                startY: event.clientY,
                startHeight: container.getBoundingClientRect().height,
            };
            if (handle.setPointerCapture) {
                handle.setPointerCapture(event.pointerId);
            }
            document.body.classList.add("plot-resizing");
        });

        handle.addEventListener("pointermove", function (event) {
            if (!dragState || event.pointerId !== dragState.pointerId) {
                return;
            }
            setHeight(dragState.startHeight + (event.clientY - dragState.startY));
        });

        handle.addEventListener("pointerup", finishDrag);
        handle.addEventListener("pointercancel", finishDrag);
    }

    function readNumericValue(row, column) {
        const entry = row && row.__summaryEntry ? row.__summaryEntry : null;
        if (entry) {
            return readNumericValueFromEntry(entry, Number(column));
        }
        const raw = String(row.dataset["col" + column] || "").trim();
        const numeric = Number(raw);
        return Number.isFinite(numeric) ? numeric : null;
    }

    function labelForColumn(column, fallback) {
        const targetColumn = String(column);
        const header = headers.find((candidate) => String(candidate.dataset.column || "") === targetColumn);
        if (header) {
            return normalizeText(header.dataset.label || header.textContent || "");
        }
        return String(fallback || targetColumn);
    }

    function selectedColumnLabel(selectElement) {
        if (!selectElement) {
            return "";
        }
        const option = selectElement.options[selectElement.selectedIndex];
        return normalizeText(option ? option.textContent : "");
    }

    function setPlotHint(message, isError) {
        if (!plotHint) {
            return;
        }
        plotHint.textContent = message;
        plotHint.classList.toggle("text-danger", !!isError);
        plotHint.classList.toggle("text-muted", !isError);
    }

    function currentRows() {
        return rowEntries.map(function (entry) {
            return entry.row;
        });
    }

    function readPlotPoints(xColumn, yColumn, options) {
        const requirePositive = !!(options && options.requirePositive);
        const transformX =
            options && typeof options.transformX === "function"
                ? options.transformX
                : function (value) {
                      return value;
                  };
        const transformY =
            options && typeof options.transformY === "function"
                ? options.transformY
                : function (value) {
                      return value;
                  };
        const points = {
            xValues: [],
            yValues: [],
            labels: [],
            entryIndexes: [],
            modelUrls: [],
            skippedNonNumeric: 0,
            skippedScale: 0,
        };

        currentRows().forEach((row) => {
            const xValue = readNumericValue(row, xColumn);
            const yValue = readNumericValue(row, yColumn);
            if (xValue === null || yValue === null) {
                points.skippedNonNumeric += 1;
                return;
            }
            if (requirePositive && (xValue <= 0 || yValue <= 0)) {
                points.skippedScale += 1;
                return;
            }
            const xMapped = transformX(xValue);
            const yMapped = transformY(yValue);
            if (!Number.isFinite(xMapped) || !Number.isFinite(yMapped)) {
                points.skippedScale += 1;
                return;
            }
            points.xValues.push(xMapped);
            points.yValues.push(yMapped);
            points.labels.push(String(row.dataset.col0 || "").trim());
            const entry = row.__summaryEntry;
            points.entryIndexes.push(entry ? entry.index : -1);
            points.modelUrls.push(entry ? entry.modelUrl : "");
        });

        return points;
    }

    function renderSummaryScatter(mode) {
        if (!scatterPlot || !xColumnSelect || !yColumnSelect || !xScaleSelect || !yScaleSelect) {
            return;
        }
        if (!window.Plotly) {
            scatterPlot.innerHTML = '<p class="text-muted small mb-0">Plotly failed to load.</p>';
            return;
        }

        const plotContainer = scatterPlot.closest(".plotly-resizable");
        const fallbackHrX = Number(xColumnSelect.value);
        const fallbackHrY = Number(yColumnSelect.value);
        const hrXColumn = plotContainer ? Number(plotContainer.dataset.hrXCol || fallbackHrX) : fallbackHrX;
        const hrYColumn = plotContainer ? Number(plotContainer.dataset.hrYCol || fallbackHrY) : fallbackHrY;

        const isHrMode = mode === "hr";
        const hrLog10Mode = isHrMode && currentHrAxisMode === "log10_linear";
        const xColumn = isHrMode ? hrXColumn : Number(xColumnSelect.value);
        const yColumn = isHrMode ? hrYColumn : Number(yColumnSelect.value);
        const xScale = isHrMode ? (hrLog10Mode ? "linear" : "log") : xScaleSelect.value || "linear";
        const yScale = isHrMode ? (hrLog10Mode ? "linear" : "log") : yScaleSelect.value || "linear";
        const showZeroLines = !(isHrMode && hrLog10Mode);
        const baseXLabel = isHrMode ? labelForColumn(xColumn, "T_*") : selectedColumnLabel(xColumnSelect);
        const baseYLabel = isHrMode ? labelForColumn(yColumn, "LSTAR") : selectedColumnLabel(yColumnSelect);
        const xLabel = isHrMode && hrLog10Mode ? "log10(" + baseXLabel + ")" : baseXLabel;
        const yLabel = isHrMode && hrLog10Mode ? "log10(" + baseYLabel + ")" : baseYLabel;
        const requirePositive = isHrMode ? true : xScale === "log" || yScale === "log";
        const transformX =
            isHrMode && hrLog10Mode
                ? function (value) {
                      return Math.log10(value);
                  }
                : function (value) {
                      return value;
                  };
        const transformY =
            isHrMode && hrLog10Mode
                ? function (value) {
                      return Math.log10(value);
                  }
                : function (value) {
                      return value;
                  };

        const { xValues, yValues, labels, entryIndexes, modelUrls, skippedNonNumeric, skippedScale } = readPlotPoints(xColumn, yColumn, {
            requirePositive: requirePositive,
            transformX: transformX,
            transformY: transformY,
        });

        const plotData = [];
        let overlayAdded = false;
        if (xValues.length) {
            plotData.push({
                type: "scatter",
                mode: "markers",
                name: "Models",
                x: xValues,
                y: yValues,
                text: labels,
                customdata: entryIndexes.map(function (entryIndex, pointIndex) {
                    return [entryIndex, modelUrls[pointIndex]];
                }),
                selectedpoints:
                    selectedEntryIndexes === null
                        ? null
                        : entryIndexes.reduce(function (pointIndexes, entryIndex, pointIndex) {
                              if (selectedEntryIndexes.has(entryIndex)) {
                                  pointIndexes.push(pointIndex);
                              }
                              return pointIndexes;
                          }, []),
                marker: {
                    size: 8,
                    color: "#0d6efd",
                    line: {
                        color: "#084298",
                        width: 0.8,
                    },
                },
                selected: {
                    marker: {
                        opacity: 1,
                        size: 10,
                    },
                },
                unselected: {
                    marker: {
                        opacity: 0.25,
                    },
                },
                hovertemplate:
                    "%{text}<br>" +
                    xLabel +
                    ": %{x:.6g}<br>" +
                    yLabel +
                    ": %{y:.6g}<extra></extra>",
            });
        }
        const overlayEnabled =
            isHrMode &&
            !!hrOverlayToggle &&
            hrOverlayToggle.checked &&
            !!hrOverlayData &&
            Array.isArray(hrOverlayData.points);
        if (overlayEnabled) {
            const overlayPoints = hrOverlayData.points
                .map(function (point) {
                    const teff = Number(point.teff);
                    const luminosity = Number(point.luminosity);
                    const spt = String(point.spt || "").trim();
                    if (!Number.isFinite(teff) || !Number.isFinite(luminosity) || teff <= 0 || luminosity <= 0) {
                        return null;
                    }
                    if (requirePositive && (teff <= 0 || luminosity <= 0)) {
                        return null;
                    }
                    const xMapped = transformX(teff);
                    const yMapped = transformY(luminosity);
                    if (!Number.isFinite(xMapped) || !Number.isFinite(yMapped)) {
                        return null;
                    }
                    return { x: xMapped, y: yMapped, spt: spt };
                })
                .filter(function (point) {
                    return point !== null;
                });
            if (overlayPoints.length >= 2) {
                plotData.push({
                    type: "scatter",
                    mode: "lines",
                    name: String(hrOverlayData.name || "Mamajek dwarf sequence"),
                    x: overlayPoints.map(function (point) {
                        return point.x;
                    }),
                    y: overlayPoints.map(function (point) {
                        return point.y;
                    }),
                    text: overlayPoints.map(function (point) {
                        return point.spt;
                    }),
                    line: {
                        color: "#c65d00",
                        width: 1.8,
                    },
                    hovertemplate:
                        "%{text}<br>" +
                        xLabel +
                        ": %{x:.6g}<br>" +
                        yLabel +
                        ": %{y:.6g}<br>" +
                        "<extra>Mamajek</extra>",
                });
                overlayAdded = true;
            }
        }

        const layout = {
            margin: { l: 74, r: 18, t: 18, b: 64 },
            xaxis: {
                title: xLabel,
                type: xScale,
                automargin: true,
                autorange: isHrMode ? "reversed" : true,
                zeroline: showZeroLines,
            },
            yaxis: { title: yLabel, type: yScale, automargin: true, zeroline: showZeroLines },
            hovermode: "closest",
            meta: { modelclick: openModelOnClick ? "on" : "off" },
            showlegend: overlayAdded,
            legend: overlayAdded
                ? {
                      orientation: "h",
                      yanchor: "bottom",
                      y: 1.02,
                      xanchor: "right",
                      x: 1,
                  }
                : undefined,
        };

        if (!xValues.length && !overlayAdded) {
            layout.annotations = [
                {
                    text: isHrMode
                        ? "No plottable points for HR diagram preset."
                        : "No plottable points for selected columns and axis scales.",
                    showarrow: false,
                    xref: "paper",
                    yref: "paper",
                    x: 0.5,
                    y: 0.5,
                    font: { size: 13, color: "#6c757d" },
                },
            ];
            setPlotHint(
                isHrMode ? "No plottable points for HR diagram preset." : "No plottable points for current selection.",
                true,
            );
        } else if (!xValues.length && overlayAdded) {
            setPlotHint("No model points are plottable; showing Mamajek overlay only.", false);
        } else {
            const skippedTotal = skippedNonNumeric + skippedScale;
            const overlaySuffix = overlayAdded ? " Overlay: Mamajek dwarf sequence." : "";
            const skippedScaleReason =
                isHrMode && hrLog10Mode
                    ? "non-positive for log10 transform"
                    : xScale === "log" || yScale === "log"
                      ? "incompatible with log scale"
                      : "not plottable after transform";
            if (skippedTotal > 0) {
                setPlotHint(
                    (isHrMode ? "HR diagram: plotted " : "Plotted ") +
                        xValues.length +
                        " model(s); skipped " +
                        skippedTotal +
                        " (non-numeric: " +
                        skippedNonNumeric +
                        ", " +
                        skippedScaleReason +
                        ": " +
                        skippedScale +
                        ")." +
                        overlaySuffix,
                    false,
                );
            } else {
                setPlotHint((isHrMode ? "HR diagram: plotted " : "Plotted ") + xValues.length + " model(s)." + overlaySuffix, false);
            }
        }

        const config = {
            responsive: true,
            displaylogo: false,
            modeBarButtonsToAdd: [
                {
                    name: "togglemodelopen",
                    title: "Toggle opening a model when clicking its point",
                    icon: {
                        width: 512,
                        height: 512,
                        path: "M48 112h176l48 56h192v264H48zM304 232h56v48h48v56h-48v48h-56v-48h-48v-56h48z",
                    },
                    attr: "meta.modelclick",
                    val: "on",
                    click: function () {
                        setOpenModelOnClick(!openModelOnClick);
                    },
                },
            ],
        };

        const renderResult = Plotly.react(scatterPlot, plotData, layout, config);
        if (renderResult && typeof renderResult.then === "function") {
            renderResult.then(function () {
                bindScatterInteractions();
            });
        } else {
            bindScatterInteractions();
        }
    }

    function updateSelectionStatus() {
        if (selectedEntryIndexes === null) {
            if (selectionStatus) {
                selectionStatus.textContent = "All " + rowEntries.length + " models shown";
            }
            if (selectionClearButton) {
                selectionClearButton.disabled = true;
            }
            return;
        }
        if (selectionStatus) {
            selectionStatus.textContent =
                selectedEntryIndexes.size + " of " + rowEntries.length + " models shown from plot selection";
        }
        if (selectionClearButton) {
            selectionClearButton.disabled = false;
        }
    }

    function applyPointSelectionFilter(entryIndexes) {
        selectedEntryIndexes = entryIndexes && entryIndexes.size ? new Set(entryIndexes) : null;
        rowEntries.forEach(function (entry) {
            entry.row.hidden = selectedEntryIndexes !== null && !selectedEntryIndexes.has(entry.index);
        });
        updateSelectionStatus();
    }

    function clearPointSelectionFilter() {
        applyPointSelectionFilter(null);
        if (!scatterPlot || !scatterPlot.data || !window.Plotly) {
            return;
        }
        const modelTraceIndexes = [];
        scatterPlot.data.forEach(function (trace, traceIndex) {
            if (Array.isArray(trace.customdata)) {
                modelTraceIndexes.push(traceIndex);
            }
        });
        Plotly.update(scatterPlot, {}, { selections: [] });
        if (modelTraceIndexes.length) {
            Plotly.restyle(scatterPlot, { selectedpoints: [null] }, modelTraceIndexes);
        }
    }

    function customDataFromPoint(point) {
        const customData = point && point.customdata;
        if (!Array.isArray(customData) || customData.length < 2) {
            return null;
        }
        const entryIndex = Number(customData[0]);
        if (!Number.isInteger(entryIndex) || entryIndex < 0) {
            return null;
        }
        return {
            entryIndex: entryIndex,
            modelUrl: String(customData[1] || "").trim(),
        };
    }

    function bindScatterInteractions() {
        if (!scatterPlot || scatterPlot.__summaryInteractionsBound || typeof scatterPlot.on !== "function") {
            return;
        }
        scatterPlot.__summaryInteractionsBound = true;
        scatterPlot.on("plotly_click", function (eventData) {
            if (!openModelOnClick || !eventData || !Array.isArray(eventData.points)) {
                return;
            }
            const pointData = eventData.points.map(customDataFromPoint).find(function (item) {
                return item !== null && !!item.modelUrl;
            });
            if (!pointData) {
                return;
            }
            const sourceEvent = eventData.event;
            if (sourceEvent && (sourceEvent.ctrlKey || sourceEvent.metaKey)) {
                window.open(pointData.modelUrl, "_blank", "noopener");
                return;
            }
            window.location.assign(pointData.modelUrl);
        });
        scatterPlot.on("plotly_selected", function (eventData) {
            if (!eventData || !Array.isArray(eventData.points) || !eventData.points.length) {
                clearPointSelectionFilter();
                return;
            }
            const selectedIndexes = new Set();
            eventData.points.forEach(function (point) {
                const pointData = customDataFromPoint(point);
                if (pointData) {
                    selectedIndexes.add(pointData.entryIndex);
                }
            });
            if (selectedIndexes.size) {
                applyPointSelectionFilter(selectedIndexes);
            }
        });
        scatterPlot.on("plotly_deselect", clearPointSelectionFilter);
        scatterPlot.on("plotly_doubleclick", function () {
            window.setTimeout(clearPointSelectionFilter, 0);
        });
    }

    function setOpenModelOnClick(enabled) {
        openModelOnClick = !!enabled;
        if (scatterPlot) {
            scatterPlot.classList.toggle("summary-plot-open-mode", openModelOnClick);
        }
        if (scatterPlot && scatterPlot.data && window.Plotly) {
            Plotly.relayout(scatterPlot, { "meta.modelclick": openModelOnClick ? "on" : "off" });
        }
    }

    function setHrAxisMode(mode) {
        const isLog10Linear = mode === "log10_linear";
        currentHrAxisMode = isLog10Linear ? "log10_linear" : "log_values";
        if (hrAxisLogButton) {
            hrAxisLogButton.classList.toggle("btn-primary", !isLog10Linear);
            hrAxisLogButton.classList.toggle("btn-outline-primary", isLog10Linear);
        }
        if (hrAxisLog10Button) {
            hrAxisLog10Button.classList.toggle("btn-primary", isLog10Linear);
            hrAxisLog10Button.classList.toggle("btn-outline-primary", !isLog10Linear);
        }
        if (currentPlotMode === "hr") {
            renderSummaryScatter("hr");
        }
    }

    function setPlotMode(mode) {
        const isHrMode = mode !== "generic";
        currentPlotMode = isHrMode ? "hr" : "generic";
        if (modeHrButton) {
            modeHrButton.classList.toggle("btn-primary", isHrMode);
            modeHrButton.classList.toggle("btn-outline-primary", !isHrMode);
        }
        if (modeGenericButton) {
            modeGenericButton.classList.toggle("btn-primary", !isHrMode);
            modeGenericButton.classList.toggle("btn-outline-primary", isHrMode);
        }
        if (genericControls) {
            genericControls.classList.toggle("d-none", isHrMode);
        }
        if (hrInfo) {
            hrInfo.classList.toggle("d-none", !isHrMode);
        }
        if (hrAxisWrap) {
            hrAxisWrap.classList.toggle("d-none", !isHrMode);
        }
        if (hrOverlayWrap) {
            hrOverlayWrap.classList.toggle("d-none", !isHrMode);
        }
        renderSummaryScatter(currentPlotMode);
    }

    if (scatterPlot && xColumnSelect && yColumnSelect && xScaleSelect && yScaleSelect) {
        bindVerticalResize(scatterPlot);
        updateSelectionStatus();
        setHrAxisMode("log_values");
        setPlotMode("hr");
        xColumnSelect.addEventListener("change", function () {
            setPlotMode("generic");
        });
        yColumnSelect.addEventListener("change", function () {
            setPlotMode("generic");
        });
        xScaleSelect.addEventListener("change", function () {
            setPlotMode("generic");
        });
        yScaleSelect.addEventListener("change", function () {
            setPlotMode("generic");
        });
        if (modeHrButton) {
            modeHrButton.addEventListener("click", function () {
                setPlotMode("hr");
            });
        }
        if (modeGenericButton) {
            modeGenericButton.addEventListener("click", function () {
                setPlotMode("generic");
            });
        }
        if (hrAxisLogButton) {
            hrAxisLogButton.addEventListener("click", function () {
                setHrAxisMode("log_values");
            });
        }
        if (hrAxisLog10Button) {
            hrAxisLog10Button.addEventListener("click", function () {
                setHrAxisMode("log10_linear");
            });
        }
        if (hrOverlayToggle) {
            hrOverlayToggle.addEventListener("change", function () {
                renderSummaryScatter(currentPlotMode);
            });
        }
        if (selectionClearButton) {
            selectionClearButton.addEventListener("click", clearPointSelectionFilter);
        }
    }
})();
