/* Shared tag/chip input used by the resume builder and CareerGuide form. */
(function () {
  "use strict";

  function splitValues(value) {
    return String(value || "")
      .split(/[,;\n|]+/)
      .map(function (item) { return item.trim(); })
      .filter(Boolean);
  }

  function setup(field) {
    var list = field.querySelector("[data-chip-list]");
    var input = field.querySelector("[data-chip-input]");
    var hidden = field.querySelector("[data-chip-hidden]");
    if (!list || !input || !hidden) return;

    var values = [];
    splitValues(hidden.value).forEach(function (item) {
      if (!values.some(function (existing) { return existing.toLowerCase() === item.toLowerCase(); })) {
        values.push(item);
      }
    });

    function notify() {
      field.dispatchEvent(new CustomEvent("chips:change", { bubbles: true }));
    }

    function render() {
      list.innerHTML = "";
      values.forEach(function (value) {
        var chip = document.createElement("span");
        chip.className = "chip";
        chip.textContent = value;
        var remove = document.createElement("button");
        remove.type = "button";
        remove.textContent = "×";
        remove.setAttribute("aria-label", "Remove " + value);
        remove.addEventListener("click", function () {
          values = values.filter(function (item) { return item !== value; });
          render();
          notify();
        });
        chip.appendChild(remove);
        list.appendChild(chip);
      });
      hidden.value = values.join(", ");
      notify();
    }

    function addFromInput() {
      var parts = splitValues(input.value);
      if (!parts.length) return;
      parts.forEach(function (part) {
        var clean = part.slice(0, 80);
        if (!values.some(function (existing) { return existing.toLowerCase() === clean.toLowerCase(); })) {
          values.push(clean);
        }
      });
      input.value = "";
      render();
    }

    input.addEventListener("keydown", function (event) {
      if (event.key === "Enter" || event.key === ",") {
        event.preventDefault();
        addFromInput();
      } else if (event.key === "Backspace" && !input.value && values.length) {
        values.pop();
        render();
      }
    });
    input.addEventListener("blur", addFromInput);
    field.addEventListener("click", function (event) {
      if (event.target === field || event.target === list) input.focus();
    });
    render();
  }

  function initAll() {
    document.querySelectorAll("[data-chip-field]").forEach(setup);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", initAll);
  } else {
    initAll();
  }
})();
