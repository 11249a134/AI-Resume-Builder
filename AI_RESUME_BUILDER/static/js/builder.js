/* Resume builder interactions: repeatable rows, skill chips, AI objective, progress. */
(function () {
  "use strict";

  var form = document.getElementById("resume-form");
  if (!form) return;

  /* ----------------------------- repeatable rows ----------------------- */
  function wireRemove(row) {
    var button = row.querySelector("[data-remove-row]");
    if (!button) return;
    button.addEventListener("click", function () {
      var list = row.parentElement;
      row.remove();
      reindexCertifications();
      refreshProgress();
      var first = list ? list.querySelector("input, textarea") : null;
      if (first) first.focus({ preventScroll: true });
    });
  }

  document.querySelectorAll("[data-row]").forEach(wireRemove);

  document.querySelectorAll("[data-add-row]").forEach(function (button) {
    button.addEventListener("click", function () {
      var list = document.getElementById(button.getAttribute("data-add-row"));
      var template = document.getElementById(button.getAttribute("data-template"));
      if (!list || !template) return;
      var index = list.querySelectorAll("[data-row]").length;
      var html = template.innerHTML.replace(/__INDEX__/g, String(index));
      var holder = document.createElement("div");
      holder.innerHTML = html.trim();
      var row = holder.firstElementChild;
      if (!row) return;
      list.appendChild(row);
      wireRemove(row);
      reindexCertifications();
      refreshProgress();
      var focusTarget = row.querySelector("input, textarea");
      if (focusTarget) focusTarget.focus({ preventScroll: true });
    });
  });

  function reindexCertifications() {
    var list = document.getElementById("certifications-list");
    if (!list) return;
    list.querySelectorAll("[data-cert-row]").forEach(function (row, index) {
      var file = row.querySelector('input[type="file"]');
      if (file) file.name = "cert_file_" + index;
      var remove = row.querySelector('input[name^="cert_remove_attachment_"]');
      if (remove) remove.name = "cert_remove_attachment_" + index;
    });
  }

  /* ----------------------------- helpers ------------------------------- */
  function splitValues(value) {
    return String(value || "")
      .split(/[,;\n|]+/)
      .map(function (item) { return item.trim(); })
      .filter(Boolean);
  }

  form.addEventListener("chips:change", refreshProgress);

  /* ----------------------------- experience toggle --------------------- */
  var panel = document.getElementById("experience-panel");
  var fresherNote = document.getElementById("fresher-note");
  document.querySelectorAll("[data-experience-toggle]").forEach(function (radio) {
    radio.addEventListener("change", function () {
      var hasExperience = radio.value === "has" && radio.checked;
      if (panel) panel.hidden = !hasExperience;
      if (fresherNote) fresherNote.hidden = hasExperience;
    });
  });

  /* ----------------------------- photo preview ------------------------- */
  var photoInput = document.getElementById("photo-input");
  var photoPreview = document.getElementById("photo-preview");
  if (photoInput && photoPreview) {
    photoInput.addEventListener("change", function () {
      var file = photoInput.files && photoInput.files[0];
      if (!file) return;
      if (!/^image\/(jpeg|png)$/.test(file.type)) {
        photoPreview.textContent = "Use JPG or PNG";
        photoInput.value = "";
        return;
      }
      var reader = new FileReader();
      reader.onload = function (event) {
        photoPreview.innerHTML = "";
        var image = document.createElement("img");
        image.alt = "Selected profile photo";
        image.src = String(event.target.result);
        photoPreview.appendChild(image);
      };
      reader.readAsDataURL(file);
    });
  }

  /* ----------------------------- objective helper ---------------------- */
  var objective = document.getElementById("objective");
  var objectiveCount = document.getElementById("objective-count");
  function countWords(text) {
    var matches = String(text || "").match(/[A-Za-z0-9][A-Za-z0-9'+#./-]*/g);
    return matches ? matches.length : 0;
  }
  function refreshWordCount() {
    if (objective && objectiveCount) {
      var count = countWords(objective.value);
      objectiveCount.textContent = String(count);
      objectiveCount.style.color = count > 85 ? "#be123c" : count >= 40 ? "#047857" : "";
    }
  }
  if (objective) {
    objective.addEventListener("input", refreshWordCount);
    refreshWordCount();
  }

  var aiStatus = document.getElementById("ai-status");
  var aiEndpoint = form.getAttribute("data-ai-endpoint");
  function collectProfile() {
    var education = {};
    var eduRow = document.querySelector("#education-list [data-row]");
    if (eduRow) {
      var degree = eduRow.querySelector('input[name="edu_degree"]');
      var department = eduRow.querySelector('input[name="edu_department"]');
      education.degree = degree ? degree.value : "";
      education.department = department ? department.value : "";
    }
    var statusRadio = form.querySelector('input[name="experience_status"]:checked');
    return {
      name: fieldValue("full_name"),
      qualification: statusRadio && statusRadio.value === "fresher" ? "Student / fresher" : "",
      degree: education.degree,
      department: education.department,
      skills: hiddenValue("skills_technical"),
      soft_skills: hiddenValue("skills_soft"),
      target_role: fieldValue("target_role"),
      experience_status: statusRadio ? statusRadio.value : "fresher",
      interests: fieldValue("target_role")
    };
  }
  function fieldValue(name) {
    var element = form.querySelector('[name="' + name + '"]');
    return element ? element.value : "";
  }
  function hiddenValue(name) {
    var element = form.querySelector('[name="' + name + '"]');
    return element ? element.value : "";
  }

  async function runAi(mode) {
    if (!aiEndpoint) return;
    if (mode === "improve" && objective && !objective.value.trim()) {
      setStatus("Write a draft objective first, then choose “Improve what I wrote”.", false);
      objective.focus();
      return;
    }
    var buttons = [document.getElementById("ai-generate"), document.getElementById("ai-improve")];
    buttons.forEach(function (button) { if (button) button.disabled = true; });
    setStatus('<span class="ai-spinner" aria-hidden="true"></span> Generating a professional objective…', true);

    var payload = collectProfile();
    payload.mode = mode;
    payload.text = objective ? objective.value : "";

    try {
      var response = await fetch(aiEndpoint, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload)
      });
      if (!response.ok) throw new Error("Request failed with status " + response.status);
      var data = await response.json();
      if (objective && data.text) {
        objective.value = data.text;
        refreshWordCount();
        objective.dispatchEvent(new Event("input"));
      }
      var suffix = data.note ? " " + data.note : "";
      setStatus((data.label || "Objective updated.") + suffix, data.source !== "ai", data.source === "ai");
      refreshProgress();
    } catch (error) {
      setStatus("The objective service could not be reached. You can keep writing manually — nothing was lost.", false);
    } finally {
      buttons.forEach(function (button) { if (button) button.disabled = false; });
    }
  }

  function setStatus(html, isRules, isAi) {
    if (!aiStatus) return;
    aiStatus.innerHTML = html;
    aiStatus.classList.toggle("is-rules", Boolean(isRules));
    aiStatus.classList.toggle("is-ai", Boolean(isAi));
  }

  var generateButton = document.getElementById("ai-generate");
  var improveButton = document.getElementById("ai-improve");
  if (generateButton) generateButton.addEventListener("click", function () { runAi("generate"); });
  if (improveButton) improveButton.addEventListener("click", function () { runAi("improve"); });

  /* ----------------------------- live progress ------------------------- */
  function hasValue(name) {
    var element = form.querySelector('[name="' + name + '"]');
    return element ? element.value.trim().length > 0 : false;
  }
  function rowCount(listId) {
    var list = document.getElementById(listId);
    if (!list) return 0;
    return Array.prototype.filter.call(list.querySelectorAll("[data-row]"), function (row) {
      return Array.prototype.some.call(row.querySelectorAll("input, textarea"), function (input) {
        return input.type !== "file" && input.value && input.value.trim().length > 1;
      });
    }).length;
  }
  function setDot(section, done) {
    var dot = document.querySelector('[data-dot="' + section + '"]');
    if (dot) dot.classList.toggle("done", Boolean(done));
  }
  function setCount(section, value) {
    var link = document.querySelector('.aside-nav a[href="#' + section + '"] .count');
    if (link) link.textContent = String(value);
  }
  function refreshProgress() {
    var skills = splitValues(hiddenValue("skills_technical")).length + splitValues(hiddenValue("skills_soft")).length;
    var education = rowCount("education-list");
    var projects = rowCount("projects-list");
    var certifications = rowCount("certifications-list");
    var experience = rowCount("experience-list");
    var personalDone = hasValue("full_name") && /\S+@\S+\.\S+/.test(fieldValue("email"));
    setDot("personal", personalDone);
    setDot("objective", hasValue("objective"));
    setDot("education", education > 0);
    setDot("skills", skills > 0);
    setDot("projects", projects > 0);
    setDot("certifications", certifications > 0);
    setDot("experience", experience > 0);
    setCount("education", education);
    setCount("skills", skills);
    setCount("projects", projects);
    setCount("certifications", certifications);
    setCount("experience", experience);
  }
  form.addEventListener("input", refreshProgress);
  form.addEventListener("change", refreshProgress);
  refreshProgress();

  /* ----------------------------- submit guard -------------------------- */
  form.addEventListener("submit", function (event) {
    var missing = [];
    if (!hasValue("full_name")) missing.push("full name");
    if (!/\S+@\S+\.\S+/.test(fieldValue("email"))) missing.push("valid email");
    if (!splitValues(hiddenValue("skills_technical")).length && !splitValues(hiddenValue("skills_soft")).length) {
      missing.push("at least one skill");
    }
    if (missing.length) {
      event.preventDefault();
      showFormError("Please add your " + missing.join(", ") + " before generating.");
    }
  });

  function showFormError(message) {
    var existing = document.getElementById("client-form-error");
    if (existing) existing.remove();
    var box = document.createElement("div");
    box.id = "client-form-error";
    box.className = "callout warning";
    box.style.cssText = "border-color:#be123c;background:#fff1f2;margin-bottom:1.2rem;";
    box.innerHTML = "<strong></strong>";
    box.querySelector("strong").textContent = message;
    form.insertBefore(box, form.firstChild);
    box.scrollIntoView({ behavior: "smooth", block: "center" });
  }
})();
