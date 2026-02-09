(function () {
    const table = document.getElementById("summary-table");
    if (!table || !table.tBodies.length) {
        return;
    }

    const tbody = table.tBodies[0];
    const headers = Array.from(table.querySelectorAll(".table-sort"));
    const copyButton = document.getElementById("summary-copy-btn");
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
})();
