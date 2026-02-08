(function () {
    const table = document.getElementById("files-table");
    if (!table || !table.tBodies.length) {
        return;
    }

    const tbody = table.tBodies[0];
    const headers = Array.from(table.querySelectorAll(".table-sort"));

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

    function readValue(row, key, type) {
        const raw = row.dataset[key];
        if (type === "number") {
            const numeric = Number(raw);
            if (Number.isNaN(numeric)) {
                return Number.NEGATIVE_INFINITY;
            }
            return numeric;
        }
        return String(raw || "").toLowerCase();
    }

    function applySort(header) {
        const key = header.dataset.key;
        const type = header.dataset.type || "string";
        const wasActive = header.classList.contains("active");
        const currentDirection = header.dataset.direction || "asc";
        const direction = wasActive && currentDirection === "asc" ? "desc" : "asc";
        const factor = direction === "asc" ? 1 : -1;

        const rows = Array.from(tbody.querySelectorAll("tr[data-entry]"));
        rows.sort((left, right) => {
            const leftValue = readValue(left, key, type);
            const rightValue = readValue(right, key, type);

            if (leftValue < rightValue) {
                return -1 * factor;
            }
            if (leftValue > rightValue) {
                return 1 * factor;
            }

            const leftName = readValue(left, "name", "string");
            const rightName = readValue(right, "name", "string");
            if (leftName < rightName) {
                return -1;
            }
            if (leftName > rightName) {
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
})();
