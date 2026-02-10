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
    const xColumnSelect = document.getElementById("summary-scatter-plot-xcol");
    const yColumnSelect = document.getElementById("summary-scatter-plot-ycol");
    const xScaleSelect = document.getElementById("summary-scatter-plot-xscale");
    const yScaleSelect = document.getElementById("summary-scatter-plot-yscale");
    const plotHint = document.getElementById("summary-scatter-plot-hint");
    if (!headers.length) {
        return;
    }

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

    function readValue(row, column, type) {
        const raw = String(row.dataset["col" + column] || "").trim();
        if (type === "number") {
            const numeric = Number(raw);
            return Number.isFinite(numeric) ? numeric : null;
        }
        return raw.toLowerCase();
    }

    function applySort(header) {
        const column = header.dataset.column;
        const type = header.dataset.type || "string";
        const wasActive = header.classList.contains("active");
        const currentDirection = header.dataset.direction || "asc";
        const direction = wasActive && currentDirection === "asc" ? "desc" : "asc";
        const factor = direction === "asc" ? 1 : -1;

        const rows = Array.from(tbody.querySelectorAll("tr[data-entry]"));
        rows.sort((left, right) => {
            const leftValue = readValue(left, column, type);
            const rightValue = readValue(right, column, type);

            if (type === "number") {
                const leftMissing = leftValue === null;
                const rightMissing = rightValue === null;
                if (leftMissing !== rightMissing) {
                    return leftMissing ? 1 : -1;
                }
            }

            if (leftValue < rightValue) {
                return -1 * factor;
            }
            if (leftValue > rightValue) {
                return 1 * factor;
            }

            const leftModel = readValue(left, "0", "string");
            const rightModel = readValue(right, "0", "string");
            if (leftModel < rightModel) {
                return -1;
            }
            if (leftModel > rightModel) {
                return 1;
            }
            return 0;
        });

        rows.forEach((row) => tbody.appendChild(row));

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

        const rows = Array.from(tbody.querySelectorAll("tr[data-entry]"));
        rows.forEach((row) => {
            const values = Array.from(row.cells).map((cell) => {
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
        return Array.from(tbody.querySelectorAll("tr[data-entry]"));
    }

    function readPlotPoints(xColumn, yColumn, xScale, yScale) {
        const points = {
            xValues: [],
            yValues: [],
            labels: [],
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
            if ((xScale === "log" && xValue <= 0) || (yScale === "log" && yValue <= 0)) {
                points.skippedScale += 1;
                return;
            }
            points.xValues.push(xValue);
            points.yValues.push(yValue);
            points.labels.push(String(row.dataset.col0 || "").trim());
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
        const xColumn = isHrMode ? hrXColumn : Number(xColumnSelect.value);
        const yColumn = isHrMode ? hrYColumn : Number(yColumnSelect.value);
        const xScale = isHrMode ? "log" : xScaleSelect.value || "linear";
        const yScale = isHrMode ? "log" : yScaleSelect.value || "linear";
        const xLabel = isHrMode ? labelForColumn(xColumn, "T_*") : selectedColumnLabel(xColumnSelect);
        const yLabel = isHrMode ? labelForColumn(yColumn, "LSTAR") : selectedColumnLabel(yColumnSelect);

        const { xValues, yValues, labels, skippedNonNumeric, skippedScale } = readPlotPoints(
            xColumn,
            yColumn,
            xScale,
            yScale,
        );

        const plotData = [];
        if (xValues.length) {
            plotData.push({
                type: "scatter",
                mode: "markers",
                x: xValues,
                y: yValues,
                text: labels,
                marker: {
                    size: 8,
                    color: "#0d6efd",
                    line: {
                        color: "#084298",
                        width: 0.8,
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

        const layout = {
            margin: { l: 74, r: 18, t: 18, b: 64 },
            xaxis: {
                title: xLabel,
                type: xScale,
                automargin: true,
                autorange: isHrMode ? "reversed" : true,
            },
            yaxis: { title: yLabel, type: yScale, automargin: true },
            hovermode: "closest",
            showlegend: false,
        };

        if (!xValues.length) {
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
        } else {
            const skippedTotal = skippedNonNumeric + skippedScale;
            if (skippedTotal > 0) {
                setPlotHint(
                    (isHrMode ? "HR diagram: plotted " : "Plotted ") +
                        xValues.length +
                        " model(s); skipped " +
                        skippedTotal +
                        " (non-numeric: " +
                        skippedNonNumeric +
                        ", incompatible with log scale: " +
                        skippedScale +
                        ").",
                    false,
                );
            } else {
                setPlotHint((isHrMode ? "HR diagram: plotted " : "Plotted ") + xValues.length + " model(s).", false);
            }
        }

        const config = {
            responsive: true,
            displaylogo: false,
        };

        Plotly.react(scatterPlot, plotData, layout, config);
    }

    function setPlotMode(mode) {
        const isHrMode = mode !== "generic";
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
        renderSummaryScatter(isHrMode ? "hr" : "generic");
    }

    if (scatterPlot && xColumnSelect && yColumnSelect && xScaleSelect && yScaleSelect) {
        bindVerticalResize(scatterPlot);
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
    }
})();
