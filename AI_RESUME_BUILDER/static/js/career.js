/* CareerGuide form validation; chip inputs come from chips.js. */
(function () {
  "use strict";

  var form = document.getElementById("career-form");
  if (!form) return;

  var errorBox = document.getElementById("cg-client-error");

  function values(name) {
    var field = form.querySelector('[name="' + name + '"]');
    return field ? field.value.trim() : "";
  }

  function showError(message, targetId) {
    if (!errorBox) return;
    errorBox.hidden = false;
    errorBox.textContent = message;
    errorBox.scrollIntoView({ behavior: "smooth", block: "center" });
    if (targetId) {
      var target = form.querySelector(targetId);
      if (target) target.focus({ preventScroll: true });
    }
  }

  form.addEventListener("submit", function (event) {
    if (errorBox) errorBox.hidden = true;

    if (!values("name")) {
      event.preventDefault();
      showError("Please enter your name so the recommendations can be personalised.", "#cg-name");
      return;
    }
    if (!values("qualification")) {
      event.preventDefault();
      showError("Please choose your educational qualification.", "#cg-qualification");
      return;
    }
    if (!values("degree")) {
      event.preventDefault();
      showError("Please enter your degree or department.", "#cg-degree");
      return;
    }
    if (!values("skills")) {
      event.preventDefault();
      showError("Add at least one skill — type it and press Enter.", "#career-form .chip-field");
      return;
    }
    if (!values("interests")) {
      event.preventDefault();
      showError("Add at least one interest — type it and press Enter.", "#career-form .chip-field");
      return;
    }
  });

  /* Keep the chip inputs in sync when the form is submitted via Enter. */
  form.addEventListener("keydown", function (event) {
    if (event.key === "Enter" && event.target.matches(".chip-input")) {
      event.preventDefault();
    }
  });
})();
