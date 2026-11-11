// Small progressive enhancements. Every page works without JavaScript.
(function () {
  "use strict";

  // Disclosure buttons: <button data-toggle-target="id" aria-controls="id" aria-expanded="false">
  document.addEventListener("click", function (event) {
    var button = event.target.closest("[data-toggle-target]");
    if (!button) return;
    var target = document.getElementById(button.getAttribute("data-toggle-target"));
    if (!target) return;
    var expanded = button.getAttribute("aria-expanded") === "true";
    button.setAttribute("aria-expanded", String(!expanded));
    target.classList.toggle("hidden", expanded);
  });

  // Filter forms: <form data-autosubmit> submits when a select changes.
  document.addEventListener("change", function (event) {
    var form = event.target.closest("form[data-autosubmit]");
    if (form && event.target.matches("select, input[type=checkbox]")) form.requestSubmit();
  });

  // Confirm buttons: <button data-confirm="Are you sure?">
  document.addEventListener("submit", function (event) {
    var submitter = event.submitter;
    var message = submitter && submitter.getAttribute("data-confirm");
    if (message && !window.confirm(message)) event.preventDefault();
  });
})();
