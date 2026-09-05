(function () {
  var table = document.getElementById("photometry-table");
  var sortWavelength = document.getElementById("photometry-sort-wavelength");
  var sortComment = document.getElementById("photometry-sort-comment");
  var vizierCenter = document.getElementById("vizier-center");
  var vizierRadius = document.getElementById("vizier-radius-arcsec");
  var vizierTableIds = document.getElementById("vizier-table-ids");
  var vizierAppendButton = document.getElementById("photometry-append-vizier");
  if (!table || !sortWavelength || !sortComment) {
    return;
  }

  function submitViaVizierAppend() {
    if (!vizierAppendButton || !vizierAppendButton.form) {
      return;
    }
    if (typeof vizierAppendButton.form.requestSubmit === "function") {
      vizierAppendButton.form.requestSubmit(vizierAppendButton);
      return;
    }
    vizierAppendButton.click();
  }

  function bindEnterToVizierAppend(input) {
    if (!input) {
      return;
    }
    input.addEventListener("keydown", function (event) {
      if (event.key !== "Enter") {
        return;
      }
      event.preventDefault();
      submitViaVizierAppend();
    });
  }

  bindEnterToVizierAppend(vizierCenter);
  bindEnterToVizierAppend(vizierRadius);
  bindEnterToVizierAppend(vizierTableIds);

  function parseSortableLine(rawLine, originalIndex) {
    var line = String(rawLine || "");
    var commentIndex = line.indexOf("#");
    var dataPart = commentIndex >= 0 ? line.slice(0, commentIndex) : line;
    var commentPart = commentIndex >= 0 ? line.slice(commentIndex + 1).trim().toLowerCase() : "";
    var trimmedData = dataPart.trim();
    if (!trimmedData) {
      return null;
    }
    var tokens = trimmedData.split(/\s+/);
    if (!tokens.length) {
      return null;
    }
    var wavelength = Number(tokens[0]);
    if (!Number.isFinite(wavelength)) {
      return null;
    }
    return {
      rawLine: line,
      originalIndex: originalIndex,
      wavelength: wavelength,
      comment: commentPart
    };
  }

  function compareByWavelength(a, b) {
    if (a.wavelength !== b.wavelength) {
      return a.wavelength - b.wavelength;
    }
    if (a.comment < b.comment) {
      return -1;
    }
    if (a.comment > b.comment) {
      return 1;
    }
    return a.originalIndex - b.originalIndex;
  }

  function compareByComment(a, b) {
    var aHasComment = a.comment.length > 0;
    var bHasComment = b.comment.length > 0;
    if (aHasComment && !bHasComment) {
      return -1;
    }
    if (!aHasComment && bHasComment) {
      return 1;
    }
    if (a.comment < b.comment) {
      return -1;
    }
    if (a.comment > b.comment) {
      return 1;
    }
    if (a.wavelength !== b.wavelength) {
      return a.wavelength - b.wavelength;
    }
    return a.originalIndex - b.originalIndex;
  }

  function sortRows(compareFn) {
    var normalizedText = String(table.value || "").replace(/\r\n?/g, "\n");
    var hasTrailingNewline = normalizedText.length > 0 && normalizedText.charAt(normalizedText.length - 1) === "\n";
    var lines = normalizedText.split("\n");
    if (hasTrailingNewline && lines.length && lines[lines.length - 1] === "") {
      lines.pop();
    }

    var sortableRows = [];
    for (var lineIndex = 0; lineIndex < lines.length; lineIndex += 1) {
      var parsed = parseSortableLine(lines[lineIndex], lineIndex);
      if (parsed) {
        parsed.targetIndex = lineIndex;
        sortableRows.push(parsed);
      }
    }
    if (sortableRows.length < 2) {
      return;
    }

    var sortedRows = sortableRows.slice().sort(compareFn);
    for (var rowIndex = 0; rowIndex < sortableRows.length; rowIndex += 1) {
      lines[sortableRows[rowIndex].targetIndex] = sortedRows[rowIndex].rawLine;
    }

    table.value = lines.join("\n") + (hasTrailingNewline ? "\n" : "");
    if (typeof Event === "function") {
      table.dispatchEvent(new Event("input", { bubbles: true }));
    }
  }

  sortWavelength.addEventListener("click", function () {
    sortRows(compareByWavelength);
  });
  sortComment.addEventListener("click", function () {
    sortRows(compareByComment);
  });
})();
