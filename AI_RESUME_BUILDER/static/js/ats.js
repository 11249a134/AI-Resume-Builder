/* ATS analyser: switch between the saved resume and an uploaded file. */
(function () {
  "use strict";

  var form = document.getElementById("ats-form");
  if (!form) return;

  var toggles = form.querySelectorAll("[data-source-toggle]");
  var fileInput = form.querySelector('input[name="resume_file"]');
  var panels = form.querySelectorAll("[data-source-panel]");

  function currentSource() {
    var checked = form.querySelector('input[name="source"]:checked');
    return checked ? checked.value : "stored";
  }

  function sync() {
    var source = currentSource();
    panels.forEach(function (panel) {
      panel.hidden = panel.getAttribute("data-source-panel") !== source;
    });
    if (fileInput) {
      fileInput.required = source === "upload";
      if (source !== "upload") fileInput.value = "";
    }
  }

  toggles.forEach(function (toggle) {
    toggle.addEventListener("change", sync);
  });
  sync();
})();
