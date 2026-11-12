// Runs before first paint (loaded without defer), so saved display settings
// apply without a visible jump:
// - a saved Light/Dark choice ("Auto" means: follow the operating system);
// - the bottom bar's remembered safe-area gap (see app.js, "Steady bottom bar").
(function () {
  "use strict";
  var root = document.documentElement;
  try {
    var saved = localStorage.getItem("theme");
    if (saved === "light" || saved === "dark") {
      root.setAttribute("data-theme", saved);
    }
    var gap = parseInt(localStorage.getItem("dock-safe-max"), 10);
    if (gap > 0 && gap <= 100) {
      root.style.setProperty("--dock-safe-max", gap + "px");
    }
  } catch (e) {
    /* storage blocked: follow the OS; the bar uses the live inset */
  }
})();
