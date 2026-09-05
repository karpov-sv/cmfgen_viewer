/* Plot controls shared by the single, bulk, and uploaded spectrum pages. */
(function () {
  "use strict";
  function bindVerticalResize(plotElement) {
    var container = plotElement.closest(".plotly-resizable");
    if (!container) {
      return;
    }
    if (window.ResizeObserver && !plotElement.__plotResizeObserver) {
      var frameId = null;
      var observer = new ResizeObserver(function () {
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

    var handle = container.querySelector(".plot-resize-handle");
    if (!handle || handle.__plotDragBound) {
      return;
    }
    handle.__plotDragBound = true;

    var dragState = null;
    var minHeight = 320;

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
        startHeight: container.getBoundingClientRect().height
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

  function setAxisScale(target, xScale, yScale) {
    return Plotly.relayout(target, { "xaxis.type": xScale, "yaxis.type": yScale });
  }
  window.CmfgenSpectrumControls = { bindVerticalResize: bindVerticalResize, setAxisScale: setAxisScale };
})();
