// Runs before first paint (loaded without defer) so a saved Light/Dark choice
// never flashes the wrong theme. "Auto" means: follow the operating system.
(function () {
  "use strict";
  try {
    var saved = localStorage.getItem("theme");
    if (saved === "light" || saved === "dark") {
      document.documentElement.setAttribute("data-theme", saved);
    }
  } catch (e) {
    /* storage blocked: follow the OS */
  }
})();
